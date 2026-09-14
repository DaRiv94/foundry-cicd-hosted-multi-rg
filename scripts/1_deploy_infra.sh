#!/usr/bin/env bash
# 1_deploy_infra.sh - deploy ONE environment from the shared template plus that environment's
# parameter file into that environment's resource group. Idempotent: rerunning changes nothing
# that already matches. The pipeline runs this same file.
# Usage:  ./scripts/1_deploy_infra.sh dev
set -euo pipefail
ENV="${1:?usage: 1_deploy_infra.sh dev|test|prod}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$ROOT/.env" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"; [[ -z "$line" || "$line" == \#* ]] && continue; export "${line%%=*}=${line#*=}"
  done < "$ROOT/.env"
fi
[[ -n "${AZURE_SUBSCRIPTION_ID:-}" && "$AZURE_SUBSCRIPTION_ID" != *"<"* ]] || { echo "Edit .env first: AZURE_SUBSCRIPTION_ID is still a placeholder."; exit 1; }
az account set --subscription "$AZURE_SUBSCRIPTION_ID"
rg="rg-ais-${REGION_CODE}-${WORKLOAD}-${ENV}"

echo "Deploying infra/main.${ENV}.bicepparam into $rg ..."
az deployment group create --resource-group "$rg" --name "infra-${ENV}-$(date +%Y%m%d%H%M%S)" \
  --parameters "$ROOT/infra/main.${ENV}.bicepparam" --parameters workload="$WORKLOAD" regionCode="$REGION_CODE" \
  --query "properties.outputs.projectEndpoint.value" -o tsv | sed 's/^/Project endpoint : /'
