# Vercel Frontend Notes

The VPO Corp frontend lives in:

```text
web/
```

Current production flow:

```text
Browser -> Vercel API route -> Cloud Run API -> Cloud SQL / GCS marts
```

Vercel must not keep its own user list. Login is delegated to Cloud Run:

```text
Vercel /api/login -> Cloud Run /auth/login -> Cloud SQL app_users
```

## Local Development

Use the project launcher from the repo root:

```powershell
C:\royalties_pipeline\scripts\start_vpo_local.ps1
```

That starts:

- local FastAPI on `http://127.0.0.1:8011`
- local Next.js on `http://localhost:3000`
- Cloud SQL proxy for operational reads/writes

## Local Web Environment

`web/.env.local` should contain:

```text
VPO_API_URL=http://127.0.0.1:8011
VPO_API_KEY=<same local/cloud API key>
VPO_SESSION_SECRET=<stable local session secret>
```

Do not use `VPO_WEB_USERS_JSON` or `VPO_WEB_PASSWORD`.

## Vercel Production Environment

Required:

```text
VPO_API_URL=https://vpo-corp-api-259971998447.us-central1.run.app
VPO_API_KEY=<same value as Google Secret Manager vpo-api-key>
VPO_SESSION_SECRET=<stable production session secret>
```

The web menu is controlled by module/user permissions from the operational
database. Do not use environment variables to hide cards outside the permission
model.

## Vercel Project Settings

```text
Framework Preset: Next.js
Root Directory: web
Build Command: npm run build
Output Directory: .next
Install Command: npm install
```
