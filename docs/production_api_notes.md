# VPO Corp Production API

La API FastAPI atiende la operacion viva sobre Cloud SQL y solicita trabajos
pesados al Cloud Run Job de reportes. No genera reportes de regalias dentro de
la peticion HTTP.

## Entrypoint

```text
app/vpo_corp_api.py
```

## Entorno local

El inicio normal se realiza con `scripts/start_vpo_local.ps1`. La API local usa
Cloud SQL mediante el proxy y solicita el mismo Job cloud que produccion.

Variables relevantes:

```text
GCS_BUCKET=vpo-corp-royalties-marts
GCS_PREFIX=marts
GOOGLE_APPLICATION_CREDENTIALS=C:\royalties_pipeline\.secrets\gcs_service_account.json
VPO_API_KEY=change-me
VPO_REPORT_JOB_PROJECT=vpo-corp-royalties
VPO_REPORT_JOB_LOCATION=us-central1
VPO_REPORT_JOB_NAME=vpo-royalty-report-job
VPO_REPORT_DOWNLOAD_TTL_MINUTES=10
VPO_REPORT_SIGNER_SERVICE_ACCOUNT=vpo-marts-publisher@vpo-corp-royalties.iam.gserviceaccount.com
```

El JSON de la cuenta de servicio y las claves nunca se suben a Git.

## Health

```powershell
Invoke-WebRequest http://127.0.0.1:8010/health -UseBasicParsing
```

## Reportes de regalias

El unico contrato HTTP vigente es:

```text
POST /reports/jobs
GET  /reports/jobs
GET  /reports/jobs/{id}
GET  /reports/jobs/{id}/download
```

Los pedidos requieren `X-VPO-API-Key` y `X-VPO-Username`. La creacion valida
`royalty_reports.create`; consulta y descarga validan acceso y propiedad. El
endpoint de descarga devuelve una URL GCS firmada de corta duracion.

Formatos registrados:

- `excel`: reporte completo;
- `executive_pdf`: informe ejecutivo;
- `google_sheet`: documento compartido.

No existen endpoints sincronicos de diagnostico, `refresh_cache`, ejecucion
local ni endpoint HTTP de worker. El contrato completo vive en
`docs/royalty_report_jobs.md`.

## Google Sheets

El Job necesita Google Sheets API, Google Drive API y el token OAuth guardado en
Secret Manager. La carpeta y el correo de destino se configuran con:

```text
GOOGLE_SHEETS_SHARE_EMAIL=<correo-autorizado>
GOOGLE_DRIVE_FOLDER_ID=<id-carpeta>
```

El resultado externo queda registrado en `report_runs` igual que los demas
formatos.
