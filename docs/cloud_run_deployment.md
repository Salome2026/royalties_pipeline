# VPO Corp en Google Cloud Run

## Arquitectura vigente

- Vercel aloja el frontend Next.js.
- `vpo-corp-api` expone la API FastAPI y atiende operacion liviana.
- `vpo-royalty-report-job` genera los reportes pesados en ejecuciones aisladas.
- Cloud SQL PostgreSQL es la unica base operativa viva.
- Google Cloud Storage contiene marts publicados y resultados temporales.

La API y el Job usan la misma imagen inmutable, pero tienen comandos, recursos
e identidades diferentes. No existe worker HTTP, Cloud Tasks, thread local ni
ruta sincrona alternativa para reportes de regalias.

## API `vpo-corp-api`

Configuracion validada el `2026-09-03`:

- region: `us-central1`;
- imagen:
  `sha256:b30b9a60a63745efca6b5f44527c18c45152511d254a72815af2c87200180d2c`;
- service account:
  `vpo-marts-publisher@vpo-corp-royalties.iam.gserviceaccount.com`;
- `1 CPU`, `2 GiB`, concurrencia `4`;
- minimo `0`, maximo `1`, facturacion por request;
- timeout `1800 s` para endpoints operativos existentes;
- Cloud SQL por socket a `vpo-corp-postgres-ssd`;
- trafico al `100%` sobre la ultima revision.

Variables del circuito de reportes:

- `VPO_REPORT_JOB_PROJECT=vpo-corp-royalties`
- `VPO_REPORT_JOB_LOCATION=us-central1`
- `VPO_REPORT_JOB_NAME=vpo-royalty-report-job`
- `VPO_REPORT_DOWNLOAD_TTL_MINUTES=10`
- `VPO_REPORT_SIGNER_SERVICE_ACCOUNT=vpo-marts-publisher@vpo-corp-royalties.iam.gserviceaccount.com`

La identidad de la API tiene permiso para ejecutar el Job con override de
`VPO_REPORT_RUN_ID` y para firmar las descargas como ella misma. No posee token
compartido de worker.

## Job `vpo-royalty-report-job`

Configuracion vigente:

- region: `us-central1`;
- misma imagen inmutable que la API;
- comando: `python -m app.royalty_reports.job_main`;
- entrada por ejecucion: solamente `VPO_REPORT_RUN_ID`;
- service account:
  `vpo-royalty-report-job@vpo-corp-royalties.iam.gserviceaccount.com`;
- `2 CPU`, `4 GiB`, timeout `3600 s`;
- una tarea, paralelismo `1`, `maxRetries=0`;
- Cloud SQL por socket;
- lectura de las generaciones congeladas bajo `marts/`;
- escritura bajo `reports/jobs/<report_run_id>/`;
- secretos: password de PostgreSQL y token OAuth para Google Sheets.

## Variables operativas comunes

- `GCS_BUCKET=vpo-corp-royalties-marts`
- `GCS_PREFIX=marts`
- `VPO_OPERATIONAL_DB_DRIVER=postgres`
- `VPO_POSTGRES_CONNECT_MODE=cloudsql_socket`
- `VPO_CLOUDSQL_CONNECTION_NAME=vpo-corp-royalties:us-central1:vpo-corp-postgres-ssd`
- `VPO_OPERATIONAL_DB_NAME=vpo_corp`
- `VPO_OPERATIONAL_DB_USER=postgres`
- `VPO_OPERATIONAL_DB_PASSWORD` desde Secret Manager.
- limites de pool segun `postgres_runtime_access.md`.

La API tambien recibe `VPO_API_KEY`. El Job no la necesita. Los secretos no se
escriben en archivos de despliegue ni en Git.

## Flujo de un reporte

1. La API valida usuario, permiso y parametros.
2. Congela las generaciones de marts y la policy activa.
3. Registra el pedido en `report_runs`.
4. Ejecuta el Job con el identificador del pedido.
5. El Job construye y publica el resultado en GCS.
6. La API autoriza al usuario y genera una URL V4 de corta duracion.
7. El navegador descarga directamente desde GCS.

Vercel no recibe el archivo y la API no lo copia a `/tmp` para entregarlo.

## Despliegue y verificacion

Cada despliegue debe usar un digest, no depender de una etiqueta mutable. API y
Job se actualizan al mismo digest y luego se verifican:

- `/health` de la API;
- ausencia de rutas sincronas y `/reports/jobs/<id>/execute` en OpenAPI;
- creacion de un trabajo desde localhost y desde cloud;
- finalizacion del Job y metadata completa en PostgreSQL;
- descarga directa por URL firmada;
- coincidencia de tamano y SHA-256 entre PostgreSQL, GCS y el archivo recibido.

El despliegue automatico rector se define en `cloudbuild.yaml`. El trigger de
produccion observa `main` en `Salome2026/royalties_pipeline`, construye una sola
imagen por commit y actualiza con ella tanto `vpo-corp-api` como
`vpo-royalty-report-job`. No se mantienen configuraciones inline ni triggers
contra propietarios anteriores del repositorio.

El mismo despliegue fija `application_name` y los limites del pool: 1 a 4 para
la API y 0 a 2 para cada ejecucion del Job.

El frontend conserva:

- `VPO_API_URL=https://vpo-corp-api-259971998447.us-central1.run.app`
- `VPO_API_KEY`
- `VPO_SESSION_SECRET`

## Costos

La API mantiene `min instances=0`. Los reportes consumen recursos solamente
durante una ejecucion del Job. La concurrencia inicial del Job es uno y solo se
aumenta con mediciones. Los artefactos bajo `reports/jobs/` tienen retencion
limitada y la auditoria permanece en PostgreSQL.
