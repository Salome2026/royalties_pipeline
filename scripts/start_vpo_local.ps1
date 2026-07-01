$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$apiScript = Join-Path $root "scripts\start_vpo_api_local.ps1"
$webScript = Join-Path $root "scripts\start_vpo_web_local.ps1"
$webUrl = "http://localhost:3000"
$apiUrl = "http://127.0.0.1:8011/health"

function Test-HttpOk {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 45
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpOk -Url $Url) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

Write-Host "Levantando VPO local..."
Write-Host "API: $apiUrl"
Write-Host "Web: $webUrl"

if (Test-HttpOk -Url $apiUrl) {
    Write-Host "API ya estaba levantada."
} else {
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-File", $apiScript
    ) -WorkingDirectory $root -WindowStyle Hidden
    [void](Wait-HttpOk -Url $apiUrl -TimeoutSeconds 45)
}

if (Test-HttpOk -Url $webUrl) {
    Write-Host "Web ya estaba levantada."
} else {
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-File", $webScript
    ) -WorkingDirectory $root -WindowStyle Hidden
    [void](Wait-HttpOk -Url $webUrl -TimeoutSeconds 60)
}

Start-Process "msedge.exe" $webUrl
