"""6_pin_version.py - route 100 percent of the agent endpoint's traffic to one version.

By default an endpoint serves whatever version was created last. Production should never
depend on that, so the prod stage pins the endpoint to the version that passed the gate.
Rollback is this same script with the previous version number. A pin cannot be removed,
only re-pointed.

Usage:  python scripts/6_pin_version.py --env prod --agent-version 3
"""
import argparse
import os
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (AgentEndpointConfig, FixedRatioVersionSelectionRule,
                                      ProtocolConfiguration, ResponsesProtocolConfiguration,
                                      VersionSelector)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
parser = argparse.ArgumentParser()
parser.add_argument("--env", required=True, choices=["dev", "test", "prod"])
parser.add_argument("--agent-version", required=True)
args = parser.parse_args()

rc, wl = os.environ["REGION_CODE"], os.environ["WORKLOAD"]
endpoint = f"https://msf-ais-{rc}-{wl}-{args.env}.services.ai.azure.com/api/projects/prj-ais-{rc}-{wl}-{args.env}"
agent = os.environ["AGENT_NAME"]  # same agent name in every environment; the project differs
project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

project.agents.update_details(
    agent_name=agent,
    agent_endpoint=AgentEndpointConfig(
        version_selector=VersionSelector(version_selection_rules=[
            FixedRatioVersionSelectionRule(agent_version=str(args.agent_version), traffic_percentage=100)]),
        protocol_configuration=ProtocolConfiguration(responses=ResponsesProtocolConfiguration()),
    ),
)
print(f"{agent} endpoint now serves version {args.agent_version} only. "
      f"Rollback: rerun with the previous version number.")
