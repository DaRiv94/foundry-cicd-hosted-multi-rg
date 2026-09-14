#!/usr/bin/env bash
# 99_teardown.sh - delete the three resource groups. Each one holds its Foundry account, project,
# model deployment, agent, and pipeline identity. The GitHub repo and its Environments are left
# alone (they cost nothing).
# Usage:  ./scripts/99_teardown.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%$'\r'}"; [[ -z "$line" || "$line" == \#* ]] && continue; export "${line%%=*}=${line#*=}"
done < "$ROOT/.env"
[[ -n "${AZURE_SUBSCRIPTION_ID:-}" && "$AZURE_SUBSCRIPTION_ID" != *"<"* ]] || { echo "Edit .env first: AZURE_SUBSCRIPTION_ID is still a placeholder."; exit 1; }
az account set --subscription "$AZURE_SUBSCRIPTION_ID"
echo "This will DELETE:"
for e in dev test prod; do g="rg-ais-${REGION_CODE}-${WORKLOAD}-${e}"; echo "  $g (exists: $(az group exists --name "$g"))"; done
read -r -p "Type DELETE to continue: " answer
[[ "$answer" == "DELETE" ]] || { echo "Aborted."; exit 0; }
for e in dev test prod; do
  g="rg-ais-${REGION_CODE}-${WORKLOAD}-${e}"
  if [[ "$(az group exists --name "$g")" == "true" ]]; then az group delete --name "$g" --yes --no-wait; echo "Deleting $g ..."; fi
done
echo "Deletion started; it finishes in the background in a few minutes."
