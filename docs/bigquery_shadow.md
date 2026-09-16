# BigQuery analitico en modo sombra

## Objetivo

La capa `vpo-corp-royalties.royalties_analytics` permite validar rendimiento y
equivalencia antes de cambiar el dashboard o los reportes. Mientras no termine
`BQ-003`, ningun lector productivo debe depender de estas tablas.

## Componentes

- `sql/bigquery/analytics_schema.sql`: dataset, tablas, particiones, clustering
  y vistas.
- `scripts/bootstrap_bigquery_analytics.py`: crea el esquema y aplica permisos
  idempotentes.
- `scripts/load_bigquery_release.py`: toma el manifiesto activo de GCS, prepara
  archivos curados, los publica de forma inmutable, carga una version y exige
  la conciliacion antes de marcarla como lista.
- `scripts/reconcile_bigquery_release.py`: compara Parquet y BigQuery por
  fuente, cuenta y mes, y persiste la evidencia del control.
- `scripts/qa/qa_bigquery_release_transform.py`: prueba las transformaciones de
  los cinco marts de entrada.
- `scripts/qa/qa_bigquery_sql_contract.py`: verifica el contrato SQL y las
  propiedades de particionamiento.
- `scripts/qa/qa_bigquery_reconciliation.py`: prueba diferencias y confirma
  que un mismo titulo con ISRC distintos representa assets distintos.

## Ejecucion

Vista previa, sin cambios:

```powershell
.\.venv\Scripts\python.exe scripts\bootstrap_bigquery_analytics.py
.\.venv\Scripts\python.exe scripts\load_bigquery_release.py
.\.venv\Scripts\python.exe scripts\reconcile_bigquery_release.py
```

Creacion y carga:

```powershell
.\.venv\Scripts\python.exe scripts\bootstrap_bigquery_analytics.py --apply
.\.venv\Scripts\python.exe scripts\load_bigquery_release.py --apply
.\.venv\Scripts\python.exe scripts\reconcile_bigquery_release.py --apply
```

La carga es repetible para el mismo `release_id`: reemplaza esa version dentro
de una transaccion y no altera otras versiones. Los archivos curados se guardan
en `gs://vpo-corp-royalties-marts/marts/analytics/releases/<release_id>/`. Si un
objeto con el mismo nombre ya existe pero su contenido es distinto, el proceso
se detiene.

## Tablas y vistas

- `analytics_releases`: control de versiones y totales de cada carga.
- `analytics_reconciliation_runs` y `analytics_reconciliation_results`:
  ejecuciones y detalle de conciliacion por fuente, cuenta y mes.
- `royalty_statement_fact`: detalle por mes de statement.
- `royalty_transaction_fact`: el mismo detalle particionado por mes de
  transaccion.
- `royalty_dashboard_rankings`: agregado para rankings y filtros.
- `royalty_dashboard_monthly`: agregado compacto por fuente, cuenta y mes.
- `royalty_song_level`, `royalty_catalog`, `digital_income_summary`: marts
  curados para reportes, catalogo e Ingresos digitales.
- `current_release`, `royalty_report_detail`, `royalty_dashboard_current`:
  vistas que exponen solamente el ultimo release con estado `ready`.

## Controles

Una carga se considera correcta solo cuando:

1. Los cinco archivos de origen coinciden en tamano y MD5 con el manifiesto.
2. BigQuery contiene los mismos conteos que los Parquet curados.
3. Los importes de detalle y dashboard coinciden con tolerancia de USD 0.01.
4. `current_release` apunta al `release_id` cargado.
5. Las tablas temporales fueron eliminadas.

La identidad de una grabacion es su ISRC. El titulo es descriptivo: titulos
iguales con ISRC distintos se cuentan como assets distintos y no constituyen
un error. El control compara tambien filas sin ISRC y la cantidad de grupos de
titulo asociados a multiples ISRC para detectar transformaciones que pudieran
fusionarlos accidentalmente.

La carga deja primero el release en estado `loaded`. La conciliacion lo cambia
a `ready` cuando no hay diferencias o a `reconciliation_failed` cuando alguna
metrica excede su tolerancia. `DASH-001` ya expone el contrato completo en
`/royalties-dashboard/bigquery-shadow`; desde DASH-002 el frontend usa la ruta
principal con BigQuery y la ruta sombra queda disponible para diagnostico. El
fallback automatico conserva Parquet como respaldo operativo.
