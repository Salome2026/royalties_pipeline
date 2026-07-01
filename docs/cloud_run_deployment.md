# VPO Corp API - Google Cloud Run

## Arquitectura

- Vercel: frontend Next.js.
- Google Cloud Storage: marts publicados.
- Google Cloud Run: API FastAPI.
- Cloud SQL Postgres: base operativa viva unica.

## Configuracion recomendada

- Region: `us-central1`
- CPU: `1`
- Memoria: `2Gi` para empezar. Si los reportes grandes siguen fallando, subir a `4Gi`.
- Timeout: `600s`
- Concurrency: `1`
- Min instances: `0`
- Max instances: `1`
- Billing: request-based.

## Variables necesarias

Usar los mismos valores que Render:

- `GCS_BUCKET=vpo-corp-royalties-marts`
- `GCS_PREFIX=marts`
- `VPO_API_CACHE_DIR=/tmp/vpo-corp/gcs_marts`
- `VPO_API_REPORTS_DIR=/tmp/vpo-corp/reports`
- `VPO_API_KEY`
- `GOOGLE_SHEETS_SHARE_EMAIL`
- `GOOGLE_DRIVE_FOLDER_ID`
- `GOOGLE_OAUTH_TOKEN_JSON`
- `VPO_OPERATIONAL_DB_DRIVER=postgres`
- `VPO_POSTGRES_CONNECT_MODE=cloudsql_socket`
- `VPO_CLOUDSQL_CONNECTION_NAME=vpo-corp-royalties:us-central1:vpo-corp-postgres`
- `VPO_OPERATIONAL_DB_NAME=vpo_corp`
- `VPO_OPERATIONAL_DB_USER=postgres`
- `VPO_OPERATIONAL_DB_PASSWORD` desde Secret Manager.

Para leer Google Cloud Storage en Cloud Run, preferimos usar el service account adjunto al servicio. Ese service account necesita permiso sobre el bucket, por ejemplo `Storage Object Viewer`.
Para Cloud SQL, el servicio debe tener asociada la instancia con
`--add-cloudsql-instances`.

## Deploy inicial desde la raiz del repo

```powershell
gcloud run deploy vpo-corp-api `
  --source C:\royalties_pipeline `
  --region us-central1 `
  --allow-unauthenticated `
  --cpu 1 `
  --memory 2Gi `
  --timeout 600 `
  --concurrency 1 `
  --min-instances 0 `
  --max-instances 1 `
  --add-cloudsql-instances vpo-corp-royalties:us-central1:vpo-corp-postgres `
  --set-env-vars GCS_BUCKET=vpo-corp-royalties-marts,GCS_PREFIX=marts,VPO_API_CACHE_DIR=/tmp/vpo-corp/gcs_marts,VPO_API_REPORTS_DIR=/tmp/vpo-corp/reports
```

Despues cargar las variables secretas desde la consola de Cloud Run o con `gcloud run services update`.

Variables secretas a cargar:

- `VPO_API_KEY`
- `GOOGLE_OAUTH_TOKEN_JSON`
- `GOOGLE_SHEETS_SHARE_EMAIL`
- `GOOGLE_DRIVE_FOLDER_ID`

## Verificacion

```powershell
curl https://TU-CLOUD-RUN-URL/health
```

Luego cambiar en Vercel:

- `VPO_API_URL=https://TU-CLOUD-RUN-URL`

Mantener:

- `VPO_API_KEY` igual que en Cloud Run.

## Nota de costos

Con `min instances = 0`, Cloud Run no queda prendido todo el mes. Para uso interno y reportes eventuales, deberia ser mucho mas economico que un servidor fijo.
