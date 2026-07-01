# Secure Operational DB Connection

## Principio

Cloud SQL Postgres es la unica base viva operativa.

SQLite local queda congelada como foto historica/respaldo del corte y no debe
recibir nuevas escrituras operativas.

El entorno local sigue existiendo para procesar archivos pesados, marts,
parquets, reportes y herramientas administrativas, pero cuando lee o escribe
datos operativos debe hacerlo contra Cloud SQL.

## Regla de seguridad

Conexiones permitidas:

- Local: Postgres operativo mediante Cloud SQL Auth Proxy escuchando en `127.0.0.1`.
- Cloud Run: Postgres mediante Cloud SQL connector/socket `/cloudsql/<connection-name>`.

Conexiones bloqueadas por defecto:

- Postgres por TCP directo a IP publica.

Solo se puede permitir TCP directo con `VPO_ALLOW_DIRECT_POSTGRES_TCP=1`, y eso queda reservado para migraciones controladas y temporales.

## Variables del adapter

```text
VPO_OPERATIONAL_DB_DRIVER=sqlite|postgres
VPO_POSTGRES_CONNECT_MODE=cloudsql_socket|local_proxy|direct_tcp
VPO_OPERATIONAL_DB_NAME=vpo_corp
VPO_OPERATIONAL_DB_USER=postgres
VPO_OPERATIONAL_DB_PASSWORD=...
VPO_CLOUDSQL_CONNECTION_NAME=vpo-corp-royalties:us-central1:vpo-corp-postgres
VPO_POSTGRES_LOCAL_PROXY_HOST=127.0.0.1
VPO_POSTGRES_LOCAL_PROXY_PORT=5432
VPO_ALLOW_DIRECT_POSTGRES_TCP=
VPO_ALLOW_LEGACY_SQLITE_OPERATIONAL=
```

Si `VPO_OPERATIONAL_DB_DRIVER` no esta definido, el sistema asume `postgres`.
SQLite operativo esta bloqueado por defecto para evitar abrir una segunda base
viva por accidente. Solo se permite con
`VPO_ALLOW_LEGACY_SQLITE_OPERATIONAL=1` y debe usarse unicamente para
recuperacion historica controlada.

## Local operativo

Usar Cloud SQL Auth Proxy:

```powershell
cloud-sql-proxy vpo-corp-royalties:us-central1:vpo-corp-postgres --port 5432
```

Luego:

```text
VPO_OPERATIONAL_DB_DRIVER=postgres
VPO_POSTGRES_CONNECT_MODE=local_proxy
VPO_OPERATIONAL_DB_NAME=vpo_corp
VPO_OPERATIONAL_DB_USER=postgres
VPO_OPERATIONAL_DB_PASSWORD=<secret>
VPO_POSTGRES_LOCAL_PROXY_HOST=127.0.0.1
VPO_POSTGRES_LOCAL_PROXY_PORT=5432
```

## Cloud Run futuro

Configurar Cloud Run con la instancia Cloud SQL asociada:

```text
vpo-corp-royalties:us-central1:vpo-corp-postgres
```

Variables:

```text
VPO_OPERATIONAL_DB_DRIVER=postgres
VPO_POSTGRES_CONNECT_MODE=cloudsql_socket
VPO_CLOUDSQL_CONNECTION_NAME=vpo-corp-royalties:us-central1:vpo-corp-postgres
VPO_OPERATIONAL_DB_NAME=vpo_corp
VPO_OPERATIONAL_DB_USER=postgres
VPO_OPERATIONAL_DB_PASSWORD=<secret>
```

## Estado actual 2026-06-27

- Cloud SQL operativo creado y cargado como base viva.
- Validacion SQLite congelada vs Postgres operativo: OK.
- Redes autorizadas directas: cerradas.
- Adapter creado: `C:\royalties_pipeline\app\operational_db.py`.
- `/health` muestra `operational_db` sin revelar contrasenas.
- API local arranca con `start_vpo_api_local.ps1` contra Cloud SQL via proxy.
- Rutas reales principales validadas contra Cloud SQL: booking, resumen,
  finanzas artista, movimientos financieros, empleados, liquidaciones
  compuestas y caserio.
- Cloud Run `vpo-corp-api` redeployado contra Cloud SQL socket.
- Secretos de Cloud Run movidos a Secret Manager.
- Cloud Run validado con `/health`, `/booking/artists`, `/booking/shows` y
  `/artist-finance/summary`.

## Proximo paso

Mantener el servicio cloud real con:

```text
VPO_OPERATIONAL_DB_DRIVER=postgres
VPO_POSTGRES_CONNECT_MODE=cloudsql_socket
VPO_CLOUDSQL_CONNECTION_NAME=vpo-corp-royalties:us-central1:vpo-corp-postgres
VPO_OPERATIONAL_DB_NAME=vpo_corp
VPO_OPERATIONAL_DB_USER=postgres
VPO_OPERATIONAL_DB_PASSWORD=<secret>
```

No crear bases paralelas para la operacion viva.
