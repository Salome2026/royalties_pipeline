$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$apiScript = Join-Path $root "scripts\start_vpo_api_local.ps1"
$webScript = Join-Path $root "scripts\start_vpo_web_local.ps1"

Write-Host "Levantando VPO local..."
Write-Host "API: http://127.0.0.1:8011"
Write-Host "Web: http://localhost:3000"

Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", $apiScript
) -WorkingDirectory $root

Start-Sleep -Seconds 3

Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", $webScript
) -WorkingDirectory $root
