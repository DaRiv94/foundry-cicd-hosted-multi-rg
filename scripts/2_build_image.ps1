# 2_build_image.ps1 - build the agent container image in the dev registry (dev) or copy the exact
# same image from the dev registry into this environment's registry (test, prod). The build runs
# inside Azure Container Registry, so no Docker is needed here. Nothing is rebuilt for test or prod:
# az acr import copies the image by digest, so all three environments run identical bytes.
# Usage:  .\scripts\2_build_image.ps1 -Env dev -Tag v1
param(
    [Parameter(Mandatory = $true)][ValidateSet("dev", "test", "prod")][string]$Env,
    [Parameter(Mandatory = $true)][string]$Tag
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (Test-Path (Join-Path $root ".env")) {
    Get-Content (Join-Path $root ".env") | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
        $k, $v = $_ -split '=', 2; Set-Item -Path "Env:$($k.Trim())" -Value $v.Trim()
    }
}
if (-not $env:AZURE_SUBSCRIPTION_ID -or $env:AZURE_SUBSCRIPTION_ID -like "*<*") {
    throw "Edit .env first: AZURE_SUBSCRIPTION_ID is still a placeholder."
}
az account set --subscription $env:AZURE_SUBSCRIPTION_ID
$registry = "acrais$($env:REGION_CODE)$($env:WORKLOAD)$Env"
$devRegistry = "acrais$($env:REGION_CODE)$($env:WORKLOAD)dev"
$repo = "frankies-bakery-support"

if ($Env -eq "dev") {
    Write-Host "Building $repo`:$Tag in $registry (remote build, about two minutes) ..."
    az acr build --registry $registry --image "$repo`:$Tag" (Join-Path $root "agent") --no-logs --output none
} else {
    Write-Host "Importing $repo`:$Tag from $devRegistry into $registry (same digest, no rebuild) ..."
    # The source is given by resource id, so the import pulls with the caller's own Azure identity
    # (AcrPull on the dev group). A bare login server would be treated as an anonymous external registry.
    $devRegistryId = "/subscriptions/$($env:AZURE_SUBSCRIPTION_ID)/resourceGroups/rg-ais-$($env:REGION_CODE)-$($env:WORKLOAD)-dev/providers/Microsoft.ContainerRegistry/registries/$devRegistry"
    az acr import --name $registry --registry $devRegistryId --source "$repo`:$Tag" --image "$repo`:$Tag" --force --output none
}
Write-Host "image=$registry.azurecr.io/$repo`:$Tag"
