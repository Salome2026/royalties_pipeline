# Cloud cutover freeze - 2026-06-27

## Decision

Desde esta fecha la base local SQLite queda congelada como foto de origen para
pasar la operacion viva a Cloud SQL.

Ruben confirmo que las cargas realizadas durante la preparacion de migracion son
correctas, incluyendo los ultimos shows de Aneley.

## Fuente local congelada

- SQLite: `C:\royalties_pipeline\warehouse\booking\live\booking_live.sqlite`
- Backup local previo: `C:\royalties_pipeline\backups\pre_cloud_cutover_20260627_210726`
- Export usado: `C:\royalties_pipeline\migration_exports\cloud_postgres\20260627_205243`

## Carga cloud

- Proyecto: `vpo-corp-royalties`
- Instancia: `vpo-corp-postgres`
- Database: `vpo_corp`
- Connection name: `vpo-corp-royalties:us-central1:vpo-corp-postgres`
- Metodo de conexion local: Cloud SQL Auth Proxy con `gcloud-auth`
- Cloud SQL backup on-demand creado antes de resetear/cargar.

## Resultado de migracion

- Export validado sin warnings.
- Filas exportadas/cargadas inicialmente: `5616`
- Durante la conexion de rutas reales se detecto que `booking_artist_ledger`
  seguia siendo leida por Finanzas Artista y no estaba en Cloud SQL.
- Decision aplicada: `booking_artist_ledger` queda incorporada al schema
  operativo y al flujo normal de export/load.
- Export operativo actualizado: `C:\royalties_pipeline\migration_exports\cloud_postgres\20260627_213511`
- Filas exportadas/cargadas actualizadas: `5625`
- `booking_artist_ledger`: `9`

## Validacion

Archivo QA:

`C:\royalties_pipeline\reports\qa\cloud_postgres_operational_validation_20260627_2118.json`

Resultado:

- `ok: true`
- secciones chequeadas iniciales: `20`
- diferencias: `0`

Validacion posterior al agregado de `booking_artist_ledger`:

- comando: `validate_cloud_postgres_against_sqlite.py --host 127.0.0.1`
- `ok: true`
- secciones chequeadas: `21`
- diferencias: `0`

Conteos clave:

- `booking_shows`: `614`
- `booking_show_expenses`: `1419`
- `booking_movements`: `3111`
- `booking_artist_ledger`: `9`
- `booking_composite_events`: `10`
- `finance_movements`: `98`
- `finance_projects`: `43`
- `finance_recovery_applications`: `12`
- `app_users`: `9`
- `module_permissions`: `56`

Casos testigo validados:

- Virrshi Dj
- Aneley
- G Sony
- Gusty DJ
- Laalo DJ
- Bianca Lif
- liquidaciones compuestas

## Regla operativa posterior

A partir de esta foto, no se debe seguir cargando operacion viva en SQLite como
si fuera una base paralela. El siguiente paso es conectar la app local/cloud a
Cloud SQL como unica verdad operativa, manteniendo local solo para procesos
pesados, marts, parquets, reportes y herramientas de administracion.

La API local ya esta preparada para usar Cloud SQL mediante Cloud SQL Proxy,
leyendo secretos desde `C:\royalties_pipeline\.secrets\cloudsql_operational.env`
sin guardar passwords en scripts.

## Cloud Run operativo

El servicio `vpo-corp-api` fue redeployado contra la base viva Cloud SQL.

- Revision validada: `vpo-corp-api-00067-7xw`
- URL publica estable: `https://vpo-corp-api-259971998447.us-central1.run.app`
- Modo DB: `VPO_OPERATIONAL_DB_DRIVER=postgres`
- Conexion: `VPO_POSTGRES_CONNECT_MODE=cloudsql_socket`
- Instancia adjunta: `vpo-corp-royalties:us-central1:vpo-corp-postgres`
- Secretos movidos a Secret Manager:
  - `vpo-operational-db-password`
  - `vpo-api-key`
  - `vpo-google-oauth-token-json`
- Service account: `vpo-marts-publisher@vpo-corp-royalties.iam.gserviceaccount.com`
- Permiso agregado: `roles/cloudsql.client`

Validaciones cloud:

- `/health`: `operational_db.status = ok`
- `/booking/artists` con usuario `rubene`: `21` artistas
- `/booking/shows?limit=3`: responde shows desde Postgres
- `/artist-finance/summary?artist=Aneley`: responde finanzas desde Postgres

Correccion aplicada durante la validacion:

- `booking_artist_options()` ya no depende de que exista el archivo SQLite para
  leer artistas. Si el driver operativo es Postgres, consulta Cloud SQL.
