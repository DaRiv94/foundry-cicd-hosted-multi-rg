# Hosted agent CI/CD, three resource groups (recommended topology)

This project promotes a Microsoft Foundry hosted agent from dev to test to prod when each environment is its own resource group with its own Foundry account, project, and container registry. The agent is your own code: `agent/main.py` runs inside a container on Foundry Agent Service and serves the Responses protocol. It is a Frankies Bakery customer service agent that reads `agent/instructions.md`, with no tools.

The agent has the same name in every environment. What differs is the project it lives in. The image is built once, in dev, and copied by digest into the test and prod registries, so all three environments run identical bytes. Prod is pinned to the version that passed the gate.

```
rg-ais-eus-hamulti-dev                   rg-ais-eus-hamulti-test                  rg-ais-eus-hamulti-prod
  msf-ais-eus-hamulti-dev                  msf-ais-eus-hamulti-test                 msf-ais-eus-hamulti-prod
    chat-model                               chat-model                               chat-model (capacity 20)
    prj-ais-eus-hamulti-dev                  prj-ais-eus-hamulti-test                 prj-ais-eus-hamulti-prod
      frankies-bakery-support                  frankies-bakery-support                  frankies-bakery-support
      endpoint serves latest                   evaluation gate runs here                endpoint PINNED
  acraiseushamultidev  (build here)          acraiseushamultitest  (import)           acraiseushamultiprod  (import)
  id-ais-eus-hamulti-cicd-dev              id-ais-eus-hamulti-cicd-test             id-ais-eus-hamulti-cicd-prod
```

Zero secrets. Each GitHub Environment signs in to Azure with OpenID Connect as the managed identity that lives in its own resource group. The dev identity cannot touch prod. The Foundry accounts have local auth disabled and the registries have no admin user, so there is no key to leak.

## What is different from a prompt agent

A prompt agent is a definition: a model name plus instructions. A hosted agent is a container image plus settings. That adds exactly these things to the project:

- `agent/main.py`, `agent/requirements.txt`, `agent/Dockerfile`: the code and how to package it.
- A container registry per environment in `infra/main.bicep`, and a role assignment so each Foundry project can pull from its own registry.
- `scripts/2_build_image`: one more step between infra and deploy. Dev builds inside its registry. Test and prod import the same digest from the dev registry into theirs.
- Two more roles for each pipeline identity. Foundry Owner cannot create a registry or grant the pull role, so each identity also gets Contributor and Role Based Access Control Administrator on its group. The test and prod identities also get Reader and AcrPull on the dev group, because the import reads from there.
- A wait. A new version pulls the image and starts a sandbox before it reports active, which takes a few minutes. The deploy script polls for it.

Everything else is the same: the three GitHub Environments, the reusable stage, the evaluation gate, the pin, the rollback.

## How promotion works

| Stage | Trigger | What runs | Gate |
|---|---|---|---|
| dev | push to any branch except `main` | deploy infra into the dev group, build the image tagged with the commit sha, create a new agent version, smoke test | none |
| test | push to `main` (job 2 of the Release run) | deploy infra into the test group, import the image from the dev registry, new version, smoke test, evaluation gate | 6-row evaluation, 80 percent must pass |
| prod | push to `main` (job 3 of the Release run) | wait for the reviewer, deploy infra into the prod group, import the image, new version, pin the endpoint, smoke test the pin | a person approves |

The Release run moves the same commit through dev, test, and prod. The image is built once, in the dev job, and test and prod import that digest. The prod job waits because the `prod` GitHub Environment has a required reviewer. The evaluation gate blocks prod because the prod job declares `needs: test`.

## Prerequisites

Azure

- A subscription where you can create resource groups and role assignments.
- Quota for `gpt-5-nano` GlobalStandard in East US: 10K tokens per minute for dev and test, 20K for prod, 40K in total.
- East US, or another region where hosted agents are available.

Local machine

- Azure CLI 2.80 or later with Bicep (`az bicep upgrade`).
- GitHub CLI (`gh auth login` with the `repo` and `workflow` scopes).
- Python 3.12 or later.
- PowerShell 7 or Bash. Every script has both.
- No Docker. The registry builds the image.

GitHub

- A public repo. Required reviewers on Environments are free only on public repos.

## Files in this folder

- `agent/main.py` is the agent. It builds an Agent Framework agent on `FoundryChatClient` and serves it with `ResponsesHostServer` on port 8088.
- `agent/instructions.md` is what the agent reads at startup. Edit this file to change the agent, then promote it.
- `agent/requirements.txt` and `agent/Dockerfile` package the agent. The platform injects the project endpoint into the container; the model deployment name is the one setting the deploy script passes in.
- `evals/bakery-eval-set.jsonl` holds six questions with the phrase each answer must contain.
- `infra/main.bicep` creates a Foundry account, a project, the `chat-model` deployment, a container registry, and two role assignments for ONE environment. Nothing in it is environment specific.
- `infra/main.dev.bicepparam`, `main.test.bicepparam`, `main.prod.bicepparam` are the only per-environment files. Each sets `env`. Prod also raises `chatCapacity`.
- `scripts/0_prepare` creates the three resource groups and grants you Foundry Owner on each.
- `scripts/0b_pipeline_identity` creates one managed identity per group, its federated credential, its roles, the GitHub Environments, and the variables.
- `scripts/1_deploy_infra` runs the Bicep deployment for one environment. The pipeline runs this same file.
- `scripts/2_build_image` builds the image in the dev registry, or imports it by digest into the test or prod registry.
- `scripts/3_deploy_agent.py` creates a new immutable version of the hosted agent in one environment's project and waits for it to become active.
- `scripts/4_smoke_test.py` asks the agent endpoint one question and fails on an empty answer. It retries, because the first call after a deploy starts a sandbox.
- `scripts/5_evaluate.py` runs the evaluation gate against one version and exits 1 below 80 percent.
- `scripts/6_pin_version.py` routes 100 percent of the prod endpoint to one version. Rollback uses the same script.
- `scripts/99_teardown` deletes the three resource groups.
- `.github/workflows/deploy-stage.yml` is the one reusable stage. `dev.yml` and `release.yml` call it and pass the commit sha as the image tag.
- `adding-capabilities.md` explains what changes when you add web search, file search, Azure AI Search, an MCP server, or code execution.

## Set up

Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
az login
```

Mac / Linux (Bash)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
az login
```

Open `.env` and replace the two placeholders: your subscription id and, for later, your GitHub repo as `owner/name`. Every script refuses to run while a placeholder is still there. The two keys at the bottom are only for running the agent code on your machine, and they point at the dev project.

## Run the agent code on your machine

Do this once so you know what the container does. It needs the dev model deployment, so run `0_prepare` and `1_deploy_infra -Env dev` first (next section), then come back.

Windows (PowerShell)

```powershell
pip install -r agent\requirements.txt
python agent\main.py
# in a second terminal
Invoke-RestMethod -Method Post -Uri http://localhost:8088/responses -ContentType "application/json" -Body '{"input":"What time do you open on Saturday?","stream":false}' | Select-Object -ExpandProperty output | Where-Object type -eq message | ForEach-Object { $_.content.text }
```

Mac / Linux (Bash)

```bash
pip install -r agent/requirements.txt
python agent/main.py
# in a second terminal
curl -s -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input":"What time do you open on Saturday?","stream":false}'
```

The server prints its OpenTelemetry setup, then answers in about ten seconds the first time. `GET http://localhost:8088/readiness` returns 200 while it runs. Stop it with Ctrl+C. In the cloud, the platform runs this same process and calls the same two URLs.

## Run it locally first

Do the whole promotion by hand once. It is the same sequence the pipeline runs, so when the pipeline runs later you already know every step. Pick a tag such as `v1` for the image. The pipeline uses the commit sha instead.

Windows (PowerShell)

```powershell
.\scripts\0_prepare.ps1

# dev: build once, deploy
.\scripts\1_deploy_infra.ps1 -Env dev
.\scripts\2_build_image.ps1 -Env dev -Tag v1
python scripts\3_deploy_agent.py --env dev --image-tag v1
python scripts\4_smoke_test.py --env dev

# test: import the same image, the gate runs here
.\scripts\1_deploy_infra.ps1 -Env test
.\scripts\2_build_image.ps1 -Env test -Tag v1
python scripts\3_deploy_agent.py --env test --image-tag v1
python scripts\4_smoke_test.py --env test
python scripts\5_evaluate.py --env test --agent-version 1

# prod: import the same image, pin, then prove the pin
.\scripts\1_deploy_infra.ps1 -Env prod
.\scripts\2_build_image.ps1 -Env prod -Tag v1
python scripts\3_deploy_agent.py --env prod --image-tag v1
python scripts\6_pin_version.py --env prod --agent-version 1
python scripts\4_smoke_test.py --env prod
```

Mac / Linux (Bash)

```bash
./scripts/0_prepare.sh

# dev: build once, deploy
./scripts/1_deploy_infra.sh dev
./scripts/2_build_image.sh dev v1
python scripts/3_deploy_agent.py --env dev --image-tag v1
python scripts/4_smoke_test.py --env dev

# test: import the same image, the gate runs here
./scripts/1_deploy_infra.sh test
./scripts/2_build_image.sh test v1
python scripts/3_deploy_agent.py --env test --image-tag v1
python scripts/4_smoke_test.py --env test
python scripts/5_evaluate.py --env test --agent-version 1

# prod: import the same image, pin, then prove the pin
./scripts/1_deploy_infra.sh prod
./scripts/2_build_image.sh prod v1
python scripts/3_deploy_agent.py --env prod --image-tag v1
python scripts/6_pin_version.py --env prod --agent-version 1
python scripts/4_smoke_test.py --env prod
```

What you see

- `1_deploy_infra` prints that environment's project endpoint. Each environment takes two to three minutes the first time and seconds after that.
- `2_build_image -Env dev` uploads the `agent` folder to the dev registry and builds there, about two minutes. `-Env test` and `-Env prod` import the tag from the dev registry in a few seconds and print the same digest.
- `3_deploy_agent` prints `frankies-bakery-support version 1 created from acraiseushamultidev.azurecr.io/frankies-bakery-support:v1`, then a `status: creating` line every five seconds until `status: active`. Expect under a minute; the platform pulls the image and prepares the sandbox. A `status: failed` with `ImageError` means the project identity cannot pull from its registry (the AcrPull role assignment in Bicep is what allows it). Version numbers count per project, so dev, test, and prod each start at 1.
- `4_smoke_test` may print `attempt 1 failed` once while the sandbox starts, then the answer.
- `5_evaluate` polls for about two minutes, prints one line per question, then `Pass rate 6/6 = 100% (minimum 80%)` and `GATE PASSED`.
- `6_pin_version` prints which version the prod endpoint now serves.

Where to look: in the Foundry portal you have three projects, each with one hosted agent and its own version history showing the image reference and the `git_sha` and `env` metadata. In the Azure portal, each registry shows the same repository with the same tag, and `az acr repository show-manifests` shows the same digest in all three.

## Wire up GitHub

1. Create a public repo and push this folder to its `main` branch.
2. Put the repo name in `.env` as `GITHUB_REPO=owner/name`.
3. Run the bootstrap script. It needs `az login` and `gh auth login`.

Windows (PowerShell)

```powershell
.\scripts\0b_pipeline_identity.ps1
```

Mac / Linux (Bash)

```bash
./scripts/0b_pipeline_identity.sh
```

It creates one managed identity in each resource group with one federated credential each. The dev credential trusts only jobs that run inside the `dev` GitHub Environment, and the same for test and prod. Each identity gets three roles on its own group, and each one pays for one pipeline step: Contributor creates the registry and runs the build or the import, Role Based Access Control Administrator writes the pull role for the project identity, and Foundry Owner creates the Foundry resources and the agent versions. The test and prod identities also get Reader and AcrPull on the dev group, the one cross-environment permission in the project, because `az acr import` reads the source registry and pulls from it.

4. Wait about ten minutes for the role assignments to propagate, then push a change or start the Release workflow from the Actions tab. If the first run fails at the login step with "No subscriptions found", it was too early. Rerun it.

Federated credential subjects: GitHub issues an immutable subject for repos created after July 2026, `repo:OWNER@OWNER-ID/REPO@REPO-ID:environment:NAME`. The script reads both ids with `gh api` and builds that subject.

## The promotion loop

This is the loop a developer runs every day.

1. Create a branch and edit `agent/instructions.md` or `agent/main.py`. For example, change Saturday closing time from 6 PM to 5 PM.
2. Push the branch. The Dev workflow builds an image tagged with the commit sha in the dev registry, deploys a new version into the dev project from it, and smoke tests it.
3. Open a pull request and merge it.
4. The Release workflow starts on `main`: the dev job builds the merge commit's image and deploys it, then the test job imports that image into the test registry, creates a version in the test project, and runs the evaluation gate, then the prod job waits.
5. Approve the prod job in the Actions tab. It imports the image into the prod registry, creates the prod version, pins the endpoint to it, and smoke tests the pinned endpoint. The smoke test output shows the new closing time.

Nothing reaches prod without a passing gate on the exact image and a human approval. The promoted artifact is real bytes: the digest built in the dev job is the digest running in prod, and each environment pulls it from a registry inside its own group.

## Break the gate

See the gate do its job once.

1. On a branch, delete rule 3 from `agent/instructions.md` (the "I will connect you with a team member" sentence) and change the Sunday hours to "9 AM to 2 PM Sunday".
2. Merge it. The test job's evaluation step fails two of six rows, prints `Pass rate 4/6 = 67%`, exits 1, and the prod job never starts. Prod keeps serving the pinned version, and the prod registry never receives the bad image.
3. Restore both edits and merge. The gate passes and prod gets the fixed version.

The gate tolerates one miss on purpose, so a single wrong row passes at 83 percent. Six rows is small. With a real evaluation set you raise the row count and the threshold together.

## Rollback

Prod serves one pinned version. To go back, pin the previous one. The old image is still in the prod registry and the old version still references it.

Windows (PowerShell)

```powershell
python scripts\6_pin_version.py --env prod --agent-version 1
```

Mac / Linux (Bash)

```bash
python scripts/6_pin_version.py --env prod --agent-version 1
```

A pin cannot be removed, only re-pointed.

## Where a bigger gate would go

The gate is one deterministic substring check per row, so it needs no judge model. To add an LLM-judged criterion such as task adherence, deploy a judge model in Bicep (`main.test.bicepparam` is where a test-only deployment belongs) and add a second entry to `testing_criteria` in `scripts/5_evaluate.py`. The pipeline does not change.

## Cost

Foundry accounts, projects, and agents cost nothing while idle, three times over. Each registry is Basic tier, about five dollars a month, so about fifteen dollars for the three. A hosted agent bills for sandbox compute (0.5 vCPU, 1 GiB here) only while a session is active, and a session ends fifteen minutes after its last request. Tokens are billed as usual. What triples is quota: three accounts reserve three model deployments.

## Teardown

Windows (PowerShell)

```powershell
.\scripts\99_teardown.ps1
```

Mac / Linux (Bash)

```bash
./scripts/99_teardown.sh
```

The script lists the three resource groups, asks you to type DELETE, and deletes them. The registries, the managed identities, and the role assignments live inside the groups, so nothing is left behind in Azure. The GitHub repo and its Environments stay and cost nothing.

## When to use this topology

Use three resource groups when the agent has real users. Each environment has its own account, quota, project, registry, identity, and role assignments. A developer with rights on the dev group cannot see or change prod. The prod registry only ever receives images that passed the gate.

Do not use it for a throwaway prototype where three groups slow you down. Project `04-hosted-agent-single-rg` shows the same agent in one project with one registry.

I recommend this topology for anything with real users because the isolation costs about ten dollars a month more than one group and the pipeline is the same three jobs either way. The only real differences are three parameter files, three identities, and one import step.

## Adding capabilities

See `adding-capabilities.md` for what changes when you add web search, file search, RAG with Azure AI Search, an MCP server, or code execution to a hosted agent.
