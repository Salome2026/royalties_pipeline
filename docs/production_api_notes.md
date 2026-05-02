# VPO Corp Production API

This API is the production-oriented backend for VPO Corp royalties reports.

It reads generated marts from Google Cloud Storage, caches them locally, and returns formatted XLSX reports.

## Entrypoint

```text
app/vpo_corp_api.py
```

## Environment

Set these values in `.env` locally or in the hosting provider:

```text
GCS_BUCKET=vpo-corp-royalties-marts
GCS_PREFIX=marts
GOOGLE_APPLICATION_CREDENTIALS=C:\royalties_pipeline\secrets\gcs_service_account.json
VPO_API_KEY=change-me
VPO_API_CACHE_DIR=C:\royalties_pipeline\cache\gcs_marts
VPO_API_REPORTS_DIR=C:\royalties_pipeline\reports\api
```

For production hosting, do not commit or upload the service account JSON to Git.
Store it as a secret/environment file according to the host's recommended method.

## Local Run

```powershell
uvicorn app.vpo_corp_api:app --host 127.0.0.1 --port 8010
```

## Health Check

```powershell
Invoke-WebRequest http://127.0.0.1:8010/health -UseBasicParsing
```

## Generate Keyword Report

```powershell
$headers = @{ "X-VPO-API-Key" = "your-api-key" }
$body = @{
  keywords = @("juli savioli")
  start_month = "2025-01"
  end_month = "2026-02"
  mode = "any"
  raw_limit = 5000
  refresh_cache = $false
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri http://127.0.0.1:8010/reports/keyword `
  -Method POST `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body `
  -OutFile C:\royalties_pipeline\reports\api_test.xlsx
```

The first request may take longer because it downloads marts from GCS into the local cache.

