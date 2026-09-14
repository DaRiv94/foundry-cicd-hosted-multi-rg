"""5_evaluate.py - the promotion gate.

Uploads evals/bakery-eval-set.jsonl, runs it as a Foundry cloud evaluation against ONE agent
version, and exits 1 when fewer than 80 percent of the rows pass. The only criterion is a
case-insensitive substring check (string_check, ilike), so no judge model is needed.
The workflow runs this in the test stage; a non-zero exit blocks the prod job.

Usage:  python scripts/5_evaluate.py --env test --agent-version 3
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
parser.add_argument("--agent-version", required=True)
args = parser.parse_args()
MIN_PASS_RATE = 0.8

rc, wl = os.environ["REGION_CODE"], os.environ["WORKLOAD"]
endpoint = f"https://msf-ais-{rc}-{wl}-{args.env}.services.ai.azure.com/api/projects/prj-ais-{rc}-{wl}-{args.env}"
agent = os.environ["AGENT_NAME"]  # same agent name in every environment; the project differs
project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
openai = project.get_openai_client()

dataset = project.datasets.upload_file(
    name=f"bakery-eval-{args.env}", version=time.strftime("%Y%m%d%H%M%S"),
    file_path=str(ROOT / "evals" / "bakery-eval-set.jsonl"),
)
evaluation = openai.evals.create(
    name=f"bakery gate [{args.env}]",
    data_source_config={
        "type": "custom",
        "item_schema": {"type": "object", "properties": {"query": {"type": "string"}, "expected": {"type": "string"}},
                        "required": ["query", "expected"]},
        "include_sample_schema": True,
    },
    testing_criteria=[{"type": "string_check", "name": "expected_phrase", "operation": "ilike",
                       "input": "{{sample.output_text}}", "reference": "{{item.expected}}"}],
)
run = openai.evals.runs.create(
    eval_id=evaluation.id,
    name=f"{agent}:{args.agent_version}",
    data_source={
        "type": "azure_ai_target_completions",
        "source": {"type": "file_id", "id": dataset.id},
        "input_messages": {"type": "template", "template": [
            {"type": "message", "role": "user", "content": {"type": "input_text", "text": "{{item.query}}"}}]},
        "target": {"type": "azure_ai_agent", "name": agent, "version": str(args.agent_version)},
    },
)
print(f"Evaluating {agent} version {args.agent_version} (run {run.id})")
started = time.time()
while run.status not in ("completed", "failed", "canceled", "cancelled"):
    if time.time() - started > 900:
        sys.exit(f"GATE FAILED: timed out with status {run.status}")
    time.sleep(15)
    run = openai.evals.runs.retrieve(run_id=run.id, eval_id=evaluation.id)
    print(f"  {run.status} ({int(time.time() - started)}s)")
if run.status != "completed":
    sys.exit(f"GATE FAILED: evaluation run {run.status}")

passed = total = 0
lines = []
for item in openai.evals.runs.output_items.list(run_id=run.id, eval_id=evaluation.id):
    results = [r if isinstance(r, dict) else r.model_dump() for r in item.results]
    ok = all(r.get("passed") for r in results)
    total += 1
    passed += ok
    lines.append(f"| {'pass' if ok else 'FAIL'} | {item.datasource_item.get('query')} | {item.datasource_item.get('expected')} |")
rate = passed / total if total else 0.0
verdict = "PASSED" if rate >= MIN_PASS_RATE else "FAILED"
table = "| Result | Query | Expected phrase |\n|---|---|---|\n" + "\n".join(lines)
print(table.replace("|", " ").replace("---", ""))
print(f"Pass rate {passed}/{total} = {rate:.0%} (minimum {MIN_PASS_RATE:.0%})")
if getattr(run, "report_url", None):
    print(f"Report: {run.report_url}")
if os.environ.get("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
        handle.write(f"### Evaluation gate ({args.env}): {verdict}, {passed}/{total} rows passed\n\n{table}\n\n")
print(f"GATE {verdict}")
sys.exit(0 if verdict == "PASSED" else 1)
