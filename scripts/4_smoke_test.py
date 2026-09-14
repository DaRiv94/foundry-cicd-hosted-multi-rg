"""4_smoke_test.py - ask the agent's endpoint one question and fail only on an empty answer.

This calls the agent endpoint, the same URL applications call, so it honours the pin.
In prod it runs after 6_pin_version.py to prove customers get the promoted version.
A hosted agent's first call after a deploy starts a sandbox, so the call is retried.

Usage:  python scripts/4_smoke_test.py --env dev
"""
import argparse
import os
import sys
import time
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
parser = argparse.ArgumentParser()
parser.add_argument("--env", required=True, choices=["dev", "test", "prod"])
args = parser.parse_args()

rc, wl = os.environ["REGION_CODE"], os.environ["WORKLOAD"]
endpoint = f"https://msf-ais-{rc}-{wl}-{args.env}.services.ai.azure.com/api/projects/prj-ais-{rc}-{wl}-{args.env}"
agent = os.environ["AGENT_NAME"]  # same agent name in every environment; the project differs
project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential(), allow_preview=True)

question = "What time do you open on Saturday?"
openai = project.get_openai_client(agent_name=agent)  # bound to the agent endpoint
answer = ""
for attempt in range(1, 4):
    try:
        answer = (openai.responses.create(input=question).output_text or "").strip()
        break
    except Exception as error:  # the sandbox may still be starting
        print(f"attempt {attempt} failed: {str(error)[:160]}")
        time.sleep(20)
print(f"Agent: {agent}\nQ: {question}\nA: {answer}")
if not answer:
    sys.exit("SMOKE TEST FAILED: empty answer")
print("SMOKE TEST PASSED")
