"""3_deploy_agent.py - create a new immutable version of the hosted agent in one environment's project.

A hosted agent version is a container image reference plus its settings. Foundry pulls the
image from this environment's own registry with the project's identity, starts it in a
sandbox, and gives it an endpoint. The script waits until the version reports active.

Usage:  python scripts/3_deploy_agent.py --env dev --image-tag v1
"""
import argparse
import os
import sys
import time
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import ContainerConfiguration, HostedAgentDefinition, ProtocolVersionRecord
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
parser = argparse.ArgumentParser()
parser.add_argument("--env", required=True, choices=["dev", "test", "prod"])
parser.add_argument("--image-tag", required=True)
args = parser.parse_args()

rc, wl = os.environ["REGION_CODE"], os.environ["WORKLOAD"]
endpoint = f"https://msf-ais-{rc}-{wl}-{args.env}.services.ai.azure.com/api/projects/prj-ais-{rc}-{wl}-{args.env}"
agent = os.environ["AGENT_NAME"]  # same agent name in every environment; the project differs
image = f"acrais{rc}{wl}{args.env}.azurecr.io/frankies-bakery-support:{args.image_tag}"  # this environment's registry
project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

version = project.agents.create_version(
    agent_name=agent,
    definition=HostedAgentDefinition(
        container_configuration=ContainerConfiguration(image=image),
        cpu="0.5",
        memory="1Gi",
        protocol_versions=[ProtocolVersionRecord(protocol="responses", version="2.0.0")],
        environment_variables={"AZURE_AI_MODEL_DEPLOYMENT_NAME": "chat-model"},  # FOUNDRY_PROJECT_ENDPOINT is injected
    ),
    metadata={"env": args.env, "image": image, "git_sha": os.environ.get("GITHUB_SHA", "local")[:12]},
)
print(f"{version.name} version {version.version} created from {image}")

for _ in range(120):  # up to ten minutes; the first pull of a new image takes a few
    details = project.agents.get_version(agent_name=agent, agent_version=version.version)
    print(f"  status: {details['status']}")
    if details["status"] == "active":
        break
    if details["status"] == "failed":
        sys.exit(f"provisioning failed: {details.get('error')}")
    time.sleep(5)
else:
    sys.exit("timed out waiting for the version to become active")

if os.environ.get("GITHUB_OUTPUT"):  # hands the version number to the next workflow step
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
        handle.write(f"version={version.version}\n")
