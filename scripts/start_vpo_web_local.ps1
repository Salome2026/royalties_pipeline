$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$web = Join-Path $root "web"

if (-not (Test-Path (Join-Path $web "package.json"))) {
    throw "No existe package.json en: $web"
}

$env:VPO_API_URL = "http://127.0.0.1:8011"
$env:VPO_API_KEY = if ($env:VPO_API_KEY) { $env:VPO_API_KEY } else { "vpo_juanmanuelfornasari" }
$env:VPO_WEB_PASSWORD = if ($env:VPO_WEB_PASSWORD) { $env:VPO_WEB_PASSWORD } else { "vpo_local_web" }

Write-Host "VPO Web local"
Write-Host "API: http://127.0.0.1:8011"
Write-Host "URL: http://localhost:3000"

Set-Location $web
npm run dev
