# Cloud environment policy

Este documento define como usamos cloud sin mezclar laboratorio local,
snapshots historicos y operacion viva.

## Idea central

- Cloud SQL Postgres es la unica base operativa viva.
- Local sigue siendo el taller pesado: ingesta de excels, marts, parquets,
  catalogo, reportes y herramientas administrativas.
- Cuando local lee o escribe datos operativos, tambien debe hacerlo contra
  Cloud SQL.
- SQLite local queda como foto historica o backup de corte, no como segunda
  base viva.
- Modulo nuevo operativo = Postgres-only. No se agrega schema, columnas ni
  fallback SQLite para funcionalidades nuevas.
- Las policies editables de distribuidoras tambien son operacion viva: viven
  exclusivamente en Cloud SQL. No se mantiene un JSON paralelo como fallback.
- Los snapshots en GCS pueden existir para datos analiticos o catalogo, pero
  no reemplazan la base operativa.

## Servicios actuales

### Vercel

Frontend Next.js:

- URL: `https://vpo-corp.vercel.app/`
- Proyecto: `vpo-corp`
- Branch: `main`
- Root directory: `web`

Variables importantes:

- `VPO_API_URL=https://vpo-corp-api-259971998447.us-central1.run.app`
- `VPO_API_KEY`
- `VPO_SESSION_SECRET`

El login web debe validarse siempre contra Cloud Run y Cloud SQL. No usar
usuarios hardcodeados ni `VPO_WEB_USERS_JSON`.

El menu web se define por permisos de usuario/modulo. No hay modo temporal paralelo.

### Google Cloud Run

Backend FastAPI:

- Servicio: `vpo-corp-api`
- Proyecto: `vpo-corp-royalties`
- Region: `us-central1`
- Min instances: `0`
- Max instances: `1`
- Billing: request-based

Variables operativas:

- `VPO_OPERATIONAL_DB_DRIVER=postgres`
- `VPO_POSTGRES_CONNECT_MODE=cloudsql_socket`
- `VPO_CLOUDSQL_CONNECTION_NAME=vpo-corp-royalties:us-central1:vpo-corp-postgres`
- `VPO_OPERATIONAL_DB_NAME=vpo_corp`
- `VPO_OPERATIONAL_DB_USER=postgres`
- `VPO_OPERATIONAL_DB_PASSWORD` desde Secret Manager.

Con esta configuracion, Cloud Run usa Cloud SQL como base viva. No debe leer
booking desde SQLite/GCS para operacion.

### Google Cloud Storage

Bucket:

- `vpo-corp-royalties-marts`

Objetos principales:

- `marts/`: marts de regalias publicados.
- `marts/catalog_master.parquet`: snapshot validado del Catalogo General para lectura compartida.
- `marts/catalog_release_metadata.parquet`: metadata externa del catalogo, si esta disponible.
- `marts/catalog_status.parquet`: decisiones activo/inactivo y entrada a reportes.
- `booking/live/booking_live.sqlite`: snapshot historico/legacy de booking. No usar para operacion viva.

Regla: subir solo artefactos elegidos. No subir carpetas crudas, backups locales ni archivos de prueba.

## Booking operativo

Booking ya no se publica como snapshot temporal. Las cargas, ediciones,
empleados, permisos, finanzas y liquidaciones operativas deben ir a Cloud SQL.

## Estado validado 2026-06-27

- Cloud SQL `vpo_corp` es la base viva.
- Cloud Run `vpo-corp-api` valida login contra Cloud SQL.
- Vercel ya no debe autenticar usuarios desde variables propias como
  `VPO_WEB_USERS_JSON`; debe llamar a `/auth/login`.
- Localhost, levantado con `scripts\start_vpo_local.ps1`, usa API local contra
  Cloud SQL por proxy.
- `jfornasari` fue retirado de la base viva y debe ser rechazado tanto en web
  como en localhost.
- SQLite operativo esta bloqueado por defecto en el adapter. Para abrir la foto
  historica como recuperacion controlada se requiere
  `VPO_ALLOW_LEGACY_SQLITE_OPERATIONAL=1`.

## Publicar catalogo compartido

El Catalogo General en cloud puede funcionar como snapshot controlado de lectura
mientras no habilitemos edicion cloud de catalogo. Eso no cambia la regla:
booking, empleados, permisos y finanzas operativas viven en Cloud SQL.

Publicar solo cuando el catalogo local este revisado:

```powershell
C:\royalties_pipeline\.venv\Scripts\python.exe C:\royalties_pipeline\scripts\publish_catalog_snapshot_to_gcs.py --apply
```

Esto sube, si existen:

- `warehouse\marts\catalog_master.parquet` -> `marts/catalog_master.parquet`
- `warehouse\marts\catalog_release_metadata.parquet` -> `marts/catalog_release_metadata.parquet`
- `warehouse\registry\catalog_status.parquet` -> `marts/catalog_status.parquet`

La web compartida debe usar este catalogo solo en lectura para usuarios `viewer`.
Los cambios de activo/inactivo se hacen localmente y luego se publica un nuevo
snapshot, salvo que se habilite una etapa futura de edicion controlada en cloud.

Para que la tarjeta funcione en Vercel, Cloud Run debe tener desplegado el
endpoint `/catalog`. Si Cloud Run conserva cache de marts en `/tmp`, se puede
forzar lectura nueva con `refresh_cache=true` o redeploy/reiniciar revision.

## Que no se sube

- `input_raw/`
- `reports/`
- `exports/`
- `warehouse/detail/`
- `warehouse/registry/`
- backups SQLite sueltos
- `.env`, `.env.local`
- `.secrets/`
- service account JSON
- scripts experimentales sin validar
- cambios locales de laboratorio en booking

## Regla para commits cloud

No usar `git add .` para deploy.

Para cambios de cloud, preferir un worktree limpio como:

```powershell
C:\royalties_pipeline_deploy
```

Checklist antes de push:

- Ver que `git status` no tenga archivos inesperados.
- Stagear solo los archivos necesarios.
- Probar build o endpoint relevante.
- Hacer commit chico y claro.
- Push a `main`.

## Control de costos

- Cloud Run debe quedar con `min instances = 0`.
- No dejar jobs o servidores locales replicando datos a cloud en loop.
- No subir reportes grandes temporales a GCS.
- Mantener `max instances = 1` mientras el uso sea interno y acotado.
- Para vistas compartidas puntuales, publicar snapshots chicos y estables.

## Estado produccion

Desde el corte 2026-06-27, el proyecto pasa a base operativa cloud unica. Las
viejas rutas temporales pueden quedar como referencia historica, pero no deben guiar
la operacion nueva.

## Regla anti-ramas viejas

Cuando un cambio toca base de datos:

1. Revisar `docs/production_guardrails.md`.
2. Confirmar si es operacion viva o snapshot analitico.
3. Si es operacion viva, implementar solo sobre Postgres/Cloud SQL.
4. No extender `init_booking_db()` ni helpers SQLite para ese cambio.
5. Si aparece una rama SQLite nueva en `git diff`, detenerse y justificarla antes
   de continuar.
