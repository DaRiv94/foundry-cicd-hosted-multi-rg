# Adding capabilities: hosted agent, three resource groups

The baseline agent is `agent/main.py`: an Agent Framework agent on `FoundryChatClient` with instructions and no tools, packaged by `agent/Dockerfile`, built once into the dev registry, imported by digest into the test and prod registries, and deployed by `scripts/3_deploy_agent.py` as `HostedAgentDefinition(container_configuration=ContainerConfiguration(image=...), environment_variables={...})`. Dev, test, and prod are three Foundry projects in three resource groups. Each group has its own pipeline identity holding Contributor, Role Based Access Control Administrator, and Foundry Owner on that group.

Each section below adds ONE capability to that baseline, alone. The last section covers what changes only when all five are added together.

## Where a tool can live in a hosted agent

A prompt agent has one place for tools: the definition. A hosted agent has three, and the choice decides what a later change costs.

| Path | Where the tool is defined | What a tool change costs | Credentials |
|---|---|---|---|
| Toolbox | a Foundry toolbox version in the project; the code only knows the toolbox name | a new toolbox version and a default-version bump, no new image, no new agent version | project connections |
| In-code Foundry tool | `main.py` passes a Foundry tool (web search, file search, AI Search, code interpreter) to the agent; the project's model service runs it | a new image, so a new agent version | project connections |
| In-container client | `main.py` calls the external service itself, for example an MCP client | a new image for the package, a new agent version for any environment variable | a placeholder in `environment_variables` that Foundry resolves from a connection at sandbox start |

The toolbox is the path Microsoft recommends for Foundry-managed tools. The agent code adds `FoundryToolbox()` to `Agent(tools=[...])`, reads the toolbox name from `TOOLBOX_NAME`, and reaches the toolbox through one MCP endpoint in its own project, `{project endpoint}/toolboxes/{name}/mcp?api-version=v1`, authenticating with its own agent identity. Every tool section below uses it unless stated.

Which layer absorbs a change:

| Change | New image | New agent version | New toolbox version |
|---|---|---|---|
| `main.py` or `requirements.txt` | yes, built in dev and imported | yes, in every environment | no |
| an environment variable only (new endpoint, new toolbox name) | no, same digest | yes | no |
| a tool inside the toolbox | no | no | yes, plus a default-version bump |
| Bicep only (search service, connection, roles) | no | no | no |

The pin protects agent versions. It does not protect a toolbox default version. In this topology each project has its own toolbox, so a dev bump cannot reach prod. The prod job's toolbox step is a prod change, and it sits behind the same reviewer approval as everything else in that job.

| Capability | New Azure resource | New project connection | Code or definition change | Copies in this topology | Evaluation rows | Idle cost |
|---|---|---|---|---|---|---|
| Web search | none | none | toolbox with the web search tool, `FoundryToolbox()` in the code, `TOOLBOX_NAME` in the version | three toolboxes, one per project | answers change daily, so check a stable phrase or add a judge | none |
| File search | none, the vector store is a data-plane object | none | upload step, then the file search tool in the toolbox | three vector stores, three toolboxes | substring checks keep working | about zero |
| RAG with Azure AI Search | one search service per group plus four role assignments each | one `search-conn` per project | the AI Search tool in the toolbox, plus an index step | three services, three connections, three indexes | substring checks keep working | about $75 per month, three times |
| MCP server | none | one `bakery-orders-conn` per project when the server needs a key | `MCPStreamableHTTPTool` in `main.py`, URL and key placeholder in the version | three connections, three secrets | substring checks work against your own seeded server | none |
| Code execution | none | none | the code interpreter tool in the toolbox, or the hosted code interpreter tool in the code | three toolboxes | deterministic math rows | per session while it runs |

## 1. Web search

Bicep: no change.

Toolbox: a new step in `3_deploy_agent.py` before `create_version`.

```python
from azure.ai.projects.models import WebSearchToolboxTool
toolbox = project.toolboxes.create_version(name="bakery-tools", tools=[WebSearchToolboxTool()])
project.toolboxes.update(name=toolbox.name, default_version=toolbox.version)
```

Code: `agent/requirements.txt` keeps `agent-framework-foundry-hosting`, which exports `FoundryToolbox`. In `main.py`:

```python
from agent_framework_foundry_hosting import FoundryToolbox
agent = Agent(client=client, instructions=..., tools=[FoundryToolbox()], default_options={"store": False})
```

Definition: `environment_variables` gains `"TOOLBOX_NAME": "bakery-tools"`. That is a new agent version the first time and never again for web search changes. The name is the same in all three projects because each project has its own toolbox.

Scripts and pipeline: the toolbox step runs inside the deploy script, so no new workflow step, variable, or output. The instructions must say when to search, or the model answers from memory and never calls the tool.

Evaluation gate: a web answer is different every day, so a substring check on the answer text is fragile. Check a phrase the instructions force regardless of the search result, or add an LLM-judged criterion, which is the moment a judge model deployment enters Bicep, and `main.test.bicepparam` is where a test-only judge belongs.

Smoke test: the host wraps tool calls, so assert on content (a date or a URL in the answer) rather than on output item types.

This topology and agent type: the image is rebuilt once for the dependency, imported twice, and each project gets one new version for the environment variable. After that, web search changes are toolbox versions only. Three toolboxes in three projects means a dev toolbox bump cannot reach prod, and the prod toolbox step runs behind the prod approval.

Cost: per search call, nothing idle.

What does not change: Bicep, the parameter files, the identities, connections, cpu and memory, the protocol, the pin.

## 2. File search

Bicep: no change. A vector store lives inside a project's data plane.

New file: `agent/policies.md`.

New step, before the toolbox version:

```python
openai = project.get_openai_client()
store = openai.vector_stores.create(name="bakery-policies")
with open(ROOT / "agent" / "policies.md", "rb") as handle:
    openai.vector_stores.files.upload_and_poll(vector_store_id=store.id, file=handle)
```

Toolbox: `FileSearchToolboxTool(vector_store_ids=[store.id])` in the project's toolbox version.

Code and definition: no change once `FoundryToolbox()` is wired. No new image, no new agent version.

Scripts and pipeline: no new workflow step, variable, or output.

Evaluation gate: rows whose expected phrase comes from `policies.md`. Substring checks keep working because the data is yours.

Smoke test: a question only the policy file answers.

This topology and agent type: the store id lives in the toolbox version, not in the agent version, so rolling back the agent does not roll back the data. To roll back data, point the project's toolbox default at the older toolbox version. Vector stores are project scoped and the projects are separate, so the upload runs once per stage and ids never cross environments. The prod store is created after the reviewer approves.

Cost: storage after the first free gigabyte, so a few kilobytes cost nothing.

What does not change: Bicep, connections, the identities, the image, the workflows.

## 3. RAG with Azure AI Search

Bicep: add a search service, a project connection, and four role assignments to `infra/main.bicep`. Because the template is deployed once per group, every environment gets its own copy.

```bicep
resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: 'srch-ais-${regionCode}-${workload}-${env}'
  location: location
  sku: { name: 'basic' }
  identity: { type: 'SystemAssigned' }
  properties: { replicaCount: 1, partitionCount: 1, disableLocalAuth: true, semanticSearch: 'free' }
}
resource searchConn 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: 'search-conn'
  properties: { category: 'CognitiveSearch', authType: 'AAD', target: 'https://${search.name}.search.windows.net', isSharedToAll: true, metadata: { ApiType: 'Azure', ResourceId: search.id } }
}
```

Role assignments on the search service: the project identity needs BOTH Search Index Data Reader and Search Service Contributor. The pipeline identity needs Search Service Contributor and Search Index Data Contributor to create the index and upload documents. Each pipeline identity already holds Contributor and Role Based Access Control Administrator on its group, so nothing changes in `0b_pipeline_identity`. Compare with the prompt agent projects, where this capability is the one that forces the identities to grow.

New file: `agent/faq.jsonl`. New step: create the index `bakery-faq` and upload the rows with `azure-search-documents`. The index name is the same in every project because each project has its own search service.

Toolbox:

```python
conn_id = project.connections.get("search-conn").id
AzureAISearchToolboxTool(azure_ai_search=AzureAISearchToolResource(indexes=[
    AISearchIndexResource(project_connection_id=conn_id, index_name="bakery-faq", query_type=AzureAISearchQueryType.SIMPLE)
]))
```

Code and definition: no change once `FoundryToolbox()` is wired. The hosted agent sees the index as one more tool from the toolbox.

Scripts and pipeline: `requirements.txt` gains `azure-search-documents`. Role propagation takes one to five minutes, so the first smoke test after a fresh deployment may need its retries.

Evaluation gate: rows whose expected phrase comes from `faq.jsonl`. Substring checks keep working.

Smoke test: a question only the index answers.

This topology and agent type: three search services, three connections, three indexes with the same name. Nothing keeps the three indexes identical except running the index step in every stage from the same `faq.jsonl`, which is the point of a pipeline. The agent identity needs no search role, because the toolbox calls the search service with the project identity. A direct `azure-search-documents` call from `main.py` would need Search Index Data Reader for the agent identity, which is created at deploy time and cannot be granted ahead by Bicep, which is why the toolbox is the path here.

Cost: Basic tier idles at about $75 per month per service. This topology pays it three times, about $225 per month for a learning project, which is the loudest difference between the two topologies.

What does not change: agent name, `chat-model`, the image, the workflows, the pin.

## 4. MCP server

Bicep: nothing for a public server. For a server that needs a key, one project connection per environment.

```bicep
param mcpServerUrl string
@secure()
param mcpServerKey string
resource ordersConn 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: 'bakery-orders-conn'
  properties: { category: 'CustomKeys', authType: 'CustomKeys', target: mcpServerUrl, isSharedToAll: true, credentials: { keys: { 'x-functions-key': mcpServerKey } } }
}
```

`mcpServerUrl` goes into each parameter file, so dev, test, and prod can point at three server instances or at one.

Code, in-container client path:

```python
from agent_framework import MCPStreamableHTTPTool
orders = MCPStreamableHTTPTool(
    name="bakery-orders",
    url=os.environ["MCP_SERVER_URL"],
    headers={"x-functions-key": os.environ["MCP_SERVER_KEY"]},
    allowed_tools=["get_order_status", "list_locations"],
    approval_mode="never_require",
)
agent = Agent(client=client, instructions=..., tools=[orders], default_options={"store": False})
```

Definition: `environment_variables` gains `"MCP_SERVER_URL": url` and `"MCP_SERVER_KEY": "${{connections.bakery-orders-conn.credentials.x-functions-key}}"`. Foundry resolves the placeholder from that project's connection when the sandbox starts, so the key never enters the image and never appears in a `GET` on the version.

Scripts and pipeline: `agent/requirements.txt` gains the MCP client package, so a new image, built once and imported twice. `deploy-stage.yml` passes `--parameters mcpServerKey="${{ secrets.MCP_SERVER_KEY }}"` to the infra script, one secret per GitHub Environment and the first secrets in the project. The alternative, `MCPToolboxTool` in the toolbox, avoids the rebuild and the environment variables.

Evaluation gate: `approval_mode="never_require"` is forced by the gate, not a style choice. With approval required the evaluation run cannot answer the approval request and the row errors. Rows against your own seeded server keep substring checks valid.

Smoke test: a question the server answers, such as the status of a seeded order.

This topology and agent type: three connections, three URLs in three parameter files, three secrets in three GitHub Environments. Rotating the key is a staged rollout: rotate dev, watch, rotate test, watch, rotate prod. The same imported digest becomes three different versions with three environment variable sets, which is what image promotion is for.

Cost: nothing in this project. The MCP server bills on its own.

What does not change: the model, the identities, cpu and memory, the protocol, the pin.

## 5. Code execution

A prompt agent gets code execution with one line, `tools=[CodeInterpreterTool()]`. A hosted agent has the same sandbox available, plus one more option when you need control.

Managed sandbox through the toolbox: add the code interpreter tool to the project's toolbox version. The agent code needs nothing beyond `FoundryToolbox()`. The Python runs in the Microsoft-managed sandbox, Azure Container Apps dynamic sessions under the hood, Hyper-V isolated, no outbound network, same region as the project. Two limits on this path today: user isolation is not supported, so all users of the project share the sandbox context, and files for the sandbox must be uploaded at the account-level Files endpoint with the `x-aml-project-id` header rather than the project-level endpoint.

Managed sandbox from the code: pass `HostedCodeInterpreterTool()` from `agent_framework` to `Agent(tools=[...])`. Execution still happens on the service side through the project's Responses API. This costs a new image, so use it when the toolbox is not already wired.

Bring your own sandbox: when you need packages the managed sandbox lacks, outbound network, or per-user isolation, create an Azure Container Apps dynamic sessions pool (a code interpreter pool, or a custom container pool with your own image) in Bicep and call it from `main.py` as a function tool. The agent identity needs the "Azure ContainerApps Session Executor" role on the pool, and the pool endpoint goes into `environment_variables`. A custom code interpreter MCP server attached as `MCPToolboxTool` is the same idea behind an MCP endpoint.

What not to do: run model-generated code inside this container with `exec()`. The container holds the agent identity and has outbound network. The managed sandbox has neither, which is the point of it.

Bicep: none for the managed sandbox. One session pool resource per group for bring your own, a third Bicep resource that triples.

Scripts and pipeline: none for the managed sandbox.

Evaluation gate: math rows are deterministic. "What is 17 percent of 84.50?" expecting "14.37" works with the substring check.

Smoke test: a calculation.

This topology and agent type: nothing per environment for the managed sandbox. A session pool per group keeps prod's code execution capacity prod's own.

Cost: a per-session charge while a managed session is active. A session pool bills for its ready sessions, three times over.

What does not change: the image (toolbox path), the identities, the workflows, the pin.

## 6. All five together

Only the interactions are listed here.

- One toolbox version per project carries web search, file search, AI Search, and the code interpreter. The in-container MCP client sits beside it in `Agent(tools=[...])`, so toolbox tool names and MCP tool names must not collide. Putting the MCP server in the toolbox too removes the collision and the image rebuild.
- Order of creation inside one stage: infra (search service, connections, roles), index documents, vector store, toolbox version and default bump, image build or import, agent version only if the image or an environment variable changed, smoke test, evaluation gate (test), pin (prod).
- Two lineages now exist, toolbox versions and agent versions, plus the image digest. Record all three in the job summary so a prod incident can be traced to one of them.
- Role assignments accumulate only from Azure AI Search and a session pool. The pipeline identities do not grow.
- The evaluation set grows to about six rows plus two per tool. Web search is the one tool that pulls a judge model into the test parameter file. A single 80 percent threshold across all rows can pass while every web row fails, which argues for one threshold per criterion.
- The smoke test becomes five prompts, one per tool, and the gate's first rows may hit a cold sandbox, so keep the retries.
- The toolbox default bump stays the one prod change the pin does not cover. Separate projects are what keep it staged, and the prod toolbox step runs behind the prod approval.
- Costs add up: three search services dominate. Nothing interacts.

Nothing else changes: cpu and memory, the protocol, three registries, three pipeline identities, the three GitHub Environments, one immutable version per deploy.
