$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$web = Join-Path $root "web"
$webEnv = Join-Path $web ".env.local"

if (-not (Test-Path (Join-Path $web "package.json"))) {
    throw "No existe package.json en: $web"
}

$env:VPO_API_URL = "http://127.0.0.1:8011"
if (-not $env:VPO_API_KEY -and (Test-Path $webEnv)) {
    $webApiKeyLine = Get-Content $webEnv | Where-Object { $_ -match '^VPO_API_KEY=' } | Select-Object -First 1
    if ($webApiKeyLine) {
        $env:VPO_API_KEY = ($webApiKeyLine -replace '^VPO_API_KEY=', '').Trim('"').Trim("'")
    }
}
if (-not $env:VPO_API_KEY) {
    throw "Falta VPO_API_KEY. Configuralo en web\.env.local o en el entorno antes de iniciar la web."
}

Write-Host "VPO Web local"
Write-Host "API: http://127.0.0.1:8011"
Write-Host "URL: http://localhost:3000"

Set-Location $web
npm run dev
