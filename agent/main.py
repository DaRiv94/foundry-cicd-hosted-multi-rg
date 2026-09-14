"""main.py - the hosted agent. This process runs inside the container on Foundry Agent Service.

It reads the instructions file packaged next to it, talks to the project's model deployment
through FoundryChatClient, and serves the Responses protocol on port 8088.
Locally: python agent/main.py, then POST to http://localhost:8088/responses.
"""
import os
from pathlib import Path

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()  # finds the project's .env on your machine; does nothing in the container

client = FoundryChatClient(
    project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],  # injected by the platform in the cloud
    model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    credential=DefaultAzureCredential(),
)
agent = Agent(
    client=client,
    instructions=Path(__file__).with_name("instructions.md").read_text(encoding="utf-8"),
    default_options={"store": False},  # the host keeps conversation history, the model does not
)
ResponsesHostServer(agent).run()
