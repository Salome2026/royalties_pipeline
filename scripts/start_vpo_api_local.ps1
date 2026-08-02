$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$webEnv = Join-Path $root "web\.env.local"
$secretPath = Join-Path $root ".secrets\cloudsql_operational.env"

if (-not (Test-Path $python)) {
    throw "No existe Python virtualenv: $python"
}

if (-not (Test-Path $secretPath)) {
    throw "No existe configuracion Cloud SQL operativa: $secretPath"
}

function Read-DotEnv {
    param([string]$Path)
    $values = @{}
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or $line -notmatch "=") {
            return
        }
        $key, $value = $line -split "=", 2
        $values[$key.Trim()] = $value.Trim().Trim('"').Trim("'")
    }
    return $values
}

function Test-PortOpen {
    param([int]$Port)
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        if (-not $task.Wait(1000)) {
            $client.Dispose()
            return $false
        }
        $client.Dispose()
        return $true
    } catch {
        return $false
    }
}

function Wait-PortOpen {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 20
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortOpen -Port $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

$cloudSql = Read-DotEnv -Path $secretPath
$cloudSqlPort = 5432

if (-not (Test-PortOpen -Port $cloudSqlPort)) {
    $proxy = Get-Command cloud-sql-proxy -ErrorAction Stop
    Start-Process -FilePath $proxy.Source -ArgumentList @(
        $cloudSql["CLOUDSQL_CONNECTION_NAME"],
        "--port", "$cloudSqlPort",
        "--gcloud-auth"
    ) -WindowStyle Hidden
    if (-not (Wait-PortOpen -Port $cloudSqlPort -TimeoutSeconds 30)) {
        throw "No se pudo levantar Cloud SQL Proxy en 127.0.0.1:$cloudSqlPort"
    }
}

if (-not $env:VPO_API_KEY -and (Test-Path $webEnv)) {
    $webApiKeyLine = Get-Content $webEnv | Where-Object { $_ -match '^VPO_API_KEY=' } | Select-Object -First 1
    if ($webApiKeyLine) {
        $env:VPO_API_KEY = ($webApiKeyLine -replace '^VPO_API_KEY=', '').Trim('"').Trim("'")
    }
}
if (-not $env:VPO_API_KEY) {
    throw "Falta VPO_API_KEY. Configuralo en web\.env.local o en el entorno antes de iniciar la API."
}
$env:VPO_LOCAL_MARTS_DIR = Join-Path $root "warehouse\marts"
$env:VPO_API_CACHE_DIR = Join-Path $root "cache\local_api"
$env:VPO_API_REPORTS_DIR = Join-Path $root "reports\api_local"
if (-not $env:GCS_PREFIX) {
    $env:GCS_PREFIX = "marts"
}
$env:VPO_OPERATIONAL_DB_DRIVER = "postgres"
$env:VPO_POSTGRES_CONNECT_MODE = "local_proxy"
$env:VPO_OPERATIONAL_DB_NAME = $cloudSql["CLOUDSQL_DATABASE"]
$env:VPO_OPERATIONAL_DB_USER = $cloudSql["CLOUDSQL_USER"]
$env:VPO_OPERATIONAL_DB_PASSWORD = $cloudSql["CLOUDSQL_PASSWORD"]
$env:VPO_CLOUDSQL_CONNECTION_NAME = $cloudSql["CLOUDSQL_CONNECTION_NAME"]
$env:VPO_POSTGRES_LOCAL_PROXY_HOST = "127.0.0.1"
$env:VPO_POSTGRES_LOCAL_PROXY_PORT = "$cloudSqlPort"

Write-Host "VPO API local"
Write-Host "Marts: $env:VPO_LOCAL_MARTS_DIR"
Write-Host "DB:    Cloud SQL $($cloudSql["CLOUDSQL_DATABASE"]) via proxy 127.0.0.1:$cloudSqlPort"
Write-Host "URL:   http://127.0.0.1:8011"

Set-Location $root
& $python -m uvicorn app.vpo_corp_api:app --host 127.0.0.1 --port 8011
