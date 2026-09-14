#!/usr/bin/env bash
# 0_prepare.sh - create the three resource groups and let the signed-in user create agents in them.
# Usage:  ./scripts/0_prepare.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%$'\r'}"; [[ -z "$line" || "$line" == \#* ]] && continue; export "${line%%=*}=${line#*=}"
done < "$ROOT/.env"
[[ -n "${AZURE_SUBSCRIPTION_ID:-}" && "$AZURE_SUBSCRIPTION_ID" != *"<"* ]] || { echo "Edit .env first: AZURE_SUBSCRIPTION_ID is still a placeholder."; exit 1; }
az account set --subscription "$AZURE_SUBSCRIPTION_ID"
me="$(az ad signed-in-user show --query id -o tsv)"

for e in dev test prod; do
  rg="rg-ais-${REGION_CODE}-${WORKLOAD}-${e}"
  az group create --name "$rg" --location "$AZURE_LOCATION" --tags workload="$WORKLOAD" env="$e" purpose=foundry-cicd-learning \
    --query "{name:name, state:properties.provisioningState}" -o tsv
  # Owner on the subscription has no data-plane rights. Foundry Owner on the group is what
  # lets your own account create agents and run evaluations from this machine.
  MSYS_NO_PATHCONV=1 az role assignment create --assignee-object-id "$me" --assignee-principal-type User --role "Foundry Owner" \
    --scope "/subscriptions/$AZURE_SUBSCRIPTION_ID/resourceGroups/$rg" --query id -o tsv > /dev/null
  echo "Foundry Owner granted to you on $rg."
done
echo "Next: ./scripts/1_deploy_infra.sh dev"
