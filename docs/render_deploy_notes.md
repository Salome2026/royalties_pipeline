# Render Deploy Notes

This deploys the VPO Corp FastAPI backend.

## Service

Use Render Blueprint or create a Web Service from GitHub.

Repository:

```text
https://github.com/riuchy1976/royalties_pipeline
```

Render can use:

```text
render.yaml
```

## Build

```text
pip install -r requirements.txt
```

## Start

```text
uvicorn app.vpo_corp_api:app --host 0.0.0.0 --port $PORT
```

## Environment Variables

Non-secret:

```text
GCS_BUCKET=vpo-corp-royalties-marts
GCS_PREFIX=marts
VPO_API_CACHE_DIR=/tmp/vpo-corp/gcs_marts
VPO_API_REPORTS_DIR=/tmp/vpo-corp/reports
```

Secrets:

```text
VPO_API_KEY=<choose-a-long-random-secret>
GCS_SERVICE_ACCOUNT_JSON=<paste the full Google service account JSON>
```

Do not commit service account JSON to GitHub.

## Health Check

```powershell
Invoke-WebRequest https://YOUR_RENDER_URL/health -UseBasicParsing
```

## Generate Report

```powershell
$headers = @{ "X-VPO-API-Key" = "YOUR_API_KEY" }
$body = @{
  keywords = @("juli savioli")
  start_month = "2025-01"
  end_month = "2026-02"
  mode = "any"
  raw_limit = 5000
  refresh_cache = $false
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri https://YOUR_RENDER_URL/reports/keyword `
  -Method POST `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body `
  -OutFile C:\royalties_pipeline\reports\render_test.xlsx
```

The first request can take longer because the service downloads marts from GCS into `/tmp`.

