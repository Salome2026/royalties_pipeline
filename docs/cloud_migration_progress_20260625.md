# Cloud Migration Progress - 2026-06-25

> ESTADO DEL DOCUMENTO: historico/no normativo.
>
> Este archivo registra la migracion y conserva contexto de decisiones pasadas.
> No debe usarse para disenar funcionalidad nueva. La regla vigente esta en
> `production_guardrails.md`, `cloud_environment_policy.md` y
> `secure_operational_db_connection.md`: Cloud SQL Postgres es la unica base viva
> y SQLite no recibe funcionalidades nuevas.

## Estado actual operativo

Desde el 2026-06-25 la direccion correcta es cloud operativo, no entornos paralelos.

Fuente cloud operativa:

- Proyecto: `vpo-corp-royalties`
- Instancia Cloud SQL: `vpo-corp-postgres`
- Database: `vpo_corp`
- Connection name: `vpo-corp-royalties:us-central1:vpo-corp-postgres`
- Estado validado: `RUNNABLE`
- Deletion protection: activa
- Redes autorizadas directas: ninguna despues de la carga

Carga operativa inicial:

- Export usado: `C:\royalties_pipeline\migration_exports\cloud_postgres\20260625_125400`
- Filas cargadas: 5522
- Usuarios activos: 9
- Admin activo: `rubene`
- `jfornasari`: 0 filas
- `ruben` y `admin`: desactivados como legacy, no operativos

Regla de lenguaje y arquitectura:

- No llamar a esta base `dev`.
- No llamar a esta etapa con nombres temporales.
- Si una pantalla todavia lee snapshot, se documenta explicitamente como snapshot temporal de lectura, no como entorno paralelo.
- La instancia anterior `vpo-corp-postgres-dev` queda como prueba historica y debe eliminarse cuando Ruben confirme.

## Objetivo historico

Preparar, en aquel momento, el paso desde la operacion local previa hacia una
base operacional unica en Cloud SQL PostgreSQL sin tocar todavia la base viva ni
crear recursos cloud.

Nota historica: en ese momento la SQLite local se consideraba productiva para la
operacion diaria. Ese criterio quedo superado por el corte cloud. Actualmente
Cloud SQL Postgres es la unica base operativa viva.

## Foto segura

- Backup local: `C:\royalties_pipeline\backups\cloud_start_20260625_114101`
- Base SQLite incluida: `booking_live.sqlite`
- Documento de arquitectura incluido: `cloud_operational_schema_v1.md`
- Esquema Postgres inicial incluido: `postgres_schema_v1.sql`
- Esquema Postgres corregido por dry-run incluido: `postgres_schema_v1.updated.sql`

## Artefactos creados

- Esquema destino: `C:\royalties_pipeline\database\postgres_schema_v1.sql`
- Migrador en seco: `C:\royalties_pipeline\scripts\migrate_sqlite_to_postgres_dry_run.py`
- Ultima salida dry-run vigente: `C:\royalties_pipeline\migration_exports\cloud_postgres\20260625_115710`
- Salida dry-run anterior con nombre confuso: `C:\royalties_pipeline\staging\cloud_migration\20260625_114437`

## Resultado del dry-run

- Tablas SQLite operativas: 23
- Tablas Postgres v1: 39
- Tablas mapeadas/exportadas: 23
- Filas exportadas para migracion: 5523
- Tablas fuente sin mapeo: 0
- Columnas fuente no cargadas: 0
- Tabla reference-only validada: `booking_artist_ledger`

## Decision manual pendiente

`booking_artist_ledger` tiene 9 filas legacy. No se migra automaticamente porque representa movimientos anteriores a la capa financiera oficial. Debe revisarse contra:

- `finance_movements`
- `finance_recoverables`
- `booking_current_account_entries`

La regla es no duplicar saldos ni convertir historial viejo en deuda viva sin conciliacion.

## Decision validada - booking_artist_ledger

La tabla `booking_artist_ledger` queda como referencia legacy/auditoria y no se carga como cuenta corriente oficial en Cloud SQL v1.

Motivo:

- Las 9 filas son recuperos historicos de Virrshi.
- Esos recuperos ya estan mejor representados en `finance_recovery_applications`.
- En `finance_recovery_applications` quedaron aplicados contra proyectos concretos (`Mix RKT #3`, `Previa Party 11`) con metodo `before_split`.
- Migrarlos de nuevo como saldo financiero duplicaria recuperos y ensuciaria la cuenta corriente.

Tratamiento:

- No se pierde la informacion: la foto SQLite de corte y el backup conservan la tabla.
- Para Cloud SQL v1, el dato vivo es `finance_recovery_applications`.
- Si mas adelante se quiere exposicion historica, debe hacerse como vista/auditoria legacy, no como saldo.

## Ajustes detectados por validacion

El dry-run mostro que el primer borrador de Postgres no preservaba algunos campos existentes en SQLite. Se agregaron al esquema destino:

- `employees.legal_name`
- `booking_shows.booking_commission_exempt`
- `booking_shows.booking_commission_notes`
- `booking_shows.venue_shortfall_policy`

Esto no modifica datos vivos; solo evita perdida de informacion en la futura migracion.

## Tablas nuevas sin fuente directa

Estas tablas existen en Postgres v1 para ordenar el negocio, pero no nacen de una tabla SQLite directa:

- `artist_aliases`
- `attachments`
- `booking_current_account_entries`
- `business_areas`
- `catalog_label_overrides`
- `catalog_status`
- `categories`
- `counterparties`
- `custom_report_configs`
- `distributor_account_policies`
- `finance_account_entries`
- `finance_movement_lines`
- `finance_recoverables`
- `fx_rates`
- `report_runs`

Algunas seran seeds/configuracion, otras derivaciones futuras y otras se llenaran por operacion nueva.

## Proximo paso recomendado

1. Revisar el manifest: `C:\royalties_pipeline\migration_exports\cloud_postgres\20260625_115710\migration_manifest.json`
2. Crear una base Cloud SQL de desarrollo, no productiva.
3. Cargar el export de migracion en Cloud SQL operativo con `load_postgres_from_migration_export.py`.
4. Comparar conteos y saldos de casos testigo antes de conectar la app.

## Cloud SQL dev creada

Instancia dev:

- Proyecto: `vpo-corp-royalties`
- Instancia: `vpo-corp-postgres-dev`
- Connection name: `vpo-corp-royalties:us-central1:vpo-corp-postgres-dev`
- Region: `us-central1`
- Motor: PostgreSQL 16
- Tier: `db-f1-micro`
- Disco: 10 GB HDD
- Estado al crear: `RUNNABLE`

Base:

- Database: `vpo_corp_dev`
- Usuario usado para prueba: `postgres`
- Credenciales locales: `C:\royalties_pipeline\.secrets\cloudsql_dev.env`

Red:

- IP local autorizada temporalmente: `190.30.16.137/32`
- Esta apertura es solo para carga/validacion desde la PC local.
- Para operacion estable conviene cerrar esta regla y usar Cloud SQL connector/proxy o integracion Cloud Run.

## Primera carga Cloud SQL dev

Export usado:

- `C:\royalties_pipeline\migration_exports\cloud_postgres\20260625_115710`

Resultado:

- Filas cargadas: 5523
- Tablas verificadas: 23
- Diferencias de conteo: 0
- `booking_shows`: 604
- `finance_movements`: 98
- `app_users`: 12

Dependencia agregada:

- `psycopg[binary]` en `requirements.txt`

## Ajuste de precision

Durante la comparacion de casos testigo aparecio una diferencia de un centavo en Aneley. La causa no era un error de negocio: SQLite tenia prorrateos internos con mas de dos decimales en shows de febrero 2026 y el primer esquema Postgres los forzaba a `numeric(18,2)`.

Decision:

- Los importes operativos en Postgres quedan como `numeric(18,6)`.
- Las pantallas/reportes pueden mostrar 0 o 2 decimales segun corresponda.
- La base no debe perder precision interna, especialmente en prorrateos, recuperos y cajas.

## Validacion funcional Cloud SQL dev

Validador:

- `C:\royalties_pipeline\scripts\validate_cloud_postgres_against_sqlite.py`

Resultado:

- Archivo QA: `C:\royalties_pipeline\reports\qa\cloud_postgres_dev_validation_20260625_1228.json`
- Secciones verificadas: 20
- Diferencias: 0
- Casos incluidos: conteos principales, Virrshi, Aneley, Candu, G Sony, Gusty, Laalo, Bianca, liquidaciones compuestas y finanzas.

Siguiente paso:

Preparar el adapter de base de datos para que la app pudiera comparar la foto
SQLite de corte contra Postgres durante la migracion. Esa etapa ya no define la
arquitectura vigente.

## Adapter seguro creado

Archivo:

- `C:\royalties_pipeline\app\operational_db.py`

Regla:

- Default historico de esa etapa: foto SQLite de corte.
- Postgres: solo por Cloud SQL socket o proxy local.
- TCP directo a IP publica queda bloqueado salvo override temporal explicito.

La instancia Cloud SQL dev quedo sin redes autorizadas directas despues de la carga.

Documento:

- `C:\royalties_pipeline\docs\secure_operational_db_connection.md`

## Primeras rutas usando adapter

Rutas cambiadas para usar `operational_connect()`:

- `GET /employees`
- `POST /auth/login`
- `POST /auth/change-password`

Default local historico:

- En esa etapa seguia usando la foto SQLite de corte porque
  `VPO_OPERATIONAL_DB_DRIVER=sqlite` era el default.
- Ese comportamiento ya no es el criterio vigente para funcionalidades nuevas.

Cloud/Postgres:

- Las rutas quedan preparadas para Postgres, pero deben probarse por Cloud SQL Auth Proxy o Cloud Run socket.
- No se reabre IP publica para pruebas normales.

Validacion local:

- Lectura empleados: 9 empleados activos.
- Serializacion de permisos: OK.
- Usuario `rubene`: encontrado y serializado como admin.

## Limpieza usuarios local

Decision operativa:

- `rubene` queda como unico super-admin activo en `app_users`.
- `jfornasari` fue eliminado porque era un alias inactivo de Juan Manuel.
- `ruben` y `admin` quedan desactivados en `app_users` para no ensuciar el login operativo.
- El seed de `init_booking_db()` fue ajustado para no volver a reactivar `ruben` ni `admin`.

Backup previo:

- `C:\royalties_pipeline\backups\user_cleanup`

Sincronizacion Cloud SQL dev:

- Export usado: `C:\royalties_pipeline\migration_exports\cloud_postgres\20260625_125400`
- Filas cargadas: 5522
- Usuarios activos en Cloud SQL dev: 9
- Admin activo en Cloud SQL dev: `rubene`
- `jfornasari` en Cloud SQL dev: 0 filas
- Redes autorizadas directas al finalizar: ninguna
