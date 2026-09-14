# 99_teardown.ps1 - delete the three resource groups. Each one holds its Foundry account, project,
# model deployment, agent, and pipeline identity. The GitHub repo and its Environments are left
# alone (they cost nothing).
# Usage:  .\scripts\99_teardown.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Get-Content (Join-Path $root ".env") | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2; Set-Item -Path "Env:$($k.Trim())" -Value $v.Trim()
}
if (-not $env:AZURE_SUBSCRIPTION_ID -or $env:AZURE_SUBSCRIPTION_ID -like "*<*") {
    throw "Edit .env first: AZURE_SUBSCRIPTION_ID is still a placeholder."
}
az account set --subscription $env:AZURE_SUBSCRIPTION_ID
$groups = @("dev", "test", "prod") | ForEach-Object { "rg-ais-$($env:REGION_CODE)-$($env:WORKLOAD)-$_" }
Write-Host "This will DELETE:"
foreach ($g in $groups) { Write-Host "  $g (exists: $(az group exists --name $g))" }
if ((Read-Host "Type DELETE to continue") -ne "DELETE") { Write-Host "Aborted."; exit 0 }
foreach ($g in $groups) {
    if ((az group exists --name $g) -eq "true") { az group delete --name $g --yes --no-wait; Write-Host "Deleting $g ..." }
}
Write-Host "Deletion started; it finishes in the background in a few minutes."
