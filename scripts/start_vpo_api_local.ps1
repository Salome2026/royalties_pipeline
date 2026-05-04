$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "No existe Python virtualenv: $python"
}

$env:VPO_API_KEY = if ($env:VPO_API_KEY) { $env:VPO_API_KEY } else { "vpo_juanmanuelfornasari" }
$env:VPO_LOCAL_MARTS_DIR = Join-Path $root "warehouse\marts"
$env:VPO_API_CACHE_DIR = Join-Path $root "cache\local_api"
$env:VPO_API_REPORTS_DIR = Join-Path $root "reports\api_local"
$env:GCS_BUCKET = ""
$env:GCS_PREFIX = "marts"

Write-Host "VPO API local"
Write-Host "Marts: $env:VPO_LOCAL_MARTS_DIR"
Write-Host "URL:   http://127.0.0.1:8011"

Set-Location $root
& $python -m uvicorn app.vpo_corp_api:app --host 127.0.0.1 --port 8011 --reload
