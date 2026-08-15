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
GOOGLE_SHEETS_SHARE_EMAIL=<your-google-email>
GOOGLE_DRIVE_FOLDER_ID=<google-drive-folder-id>
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

## Optional Google Sheets Output

Before using Google Sheets output, enable these APIs in the same Google Cloud project:

- Google Sheets API
- Google Drive API

Then add:

```text
GOOGLE_SHEETS_SHARE_EMAIL=<your-google-email>
GOOGLE_DRIVE_FOLDER_ID=<google-drive-folder-id>
```

Create a Google Drive folder for generated reports and share it as Editor with:

```text
vpo-marts-publisher@vpo-corp-royalties.iam.gserviceaccount.com
```

Then copy the folder id from the Drive URL and use it as `GOOGLE_DRIVE_FOLDER_ID`.

The service account creates the Sheet inside that folder and shares it with `GOOGLE_SHEETS_SHARE_EMAIL`.
