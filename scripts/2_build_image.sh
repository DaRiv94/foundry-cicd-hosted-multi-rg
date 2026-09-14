#!/usr/bin/env bash
# 2_build_image.sh - build the agent container image in the dev registry (dev) or copy the exact
# same image from the dev registry into this environment's registry (test, prod). The build runs
# inside Azure Container Registry, so no Docker is needed here. Nothing is rebuilt for test or prod:
# az acr import copies the image by digest, so all three environments run identical bytes.
# The pipeline runs this same file.
# Usage:  ./scripts/2_build_image.sh dev v1
set -euo pipefail
ENV="${1:?usage: 2_build_image.sh dev|test|prod <tag>}"
TAG="${2:?usage: 2_build_image.sh dev|test|prod <tag>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$ROOT/.env" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"; [[ -z "$line" || "$line" == \#* ]] && continue; export "${line%%=*}=${line#*=}"
  done < "$ROOT/.env"
fi
[[ -n "${AZURE_SUBSCRIPTION_ID:-}" && "$AZURE_SUBSCRIPTION_ID" != *"<"* ]] || { echo "Edit .env first: AZURE_SUBSCRIPTION_ID is still a placeholder."; exit 1; }
az account set --subscription "$AZURE_SUBSCRIPTION_ID"
registry="acrais${REGION_CODE}${WORKLOAD}${ENV}"
dev_registry="acrais${REGION_CODE}${WORKLOAD}dev"
repo="frankies-bakery-support"

if [[ "$ENV" == "dev" ]]; then
  echo "Building $repo:$TAG in $registry (remote build, about two minutes) ..."
  az acr build --registry "$registry" --image "$repo:$TAG" "$ROOT/agent" --no-logs --output none
else
  echo "Importing $repo:$TAG from $dev_registry into $registry (same digest, no rebuild) ..."
  az acr import --name "$registry" --source "$dev_registry.azurecr.io/$repo:$TAG" --image "$repo:$TAG" --force --output none
fi
echo "image=$registry.azurecr.io/$repo:$TAG"
