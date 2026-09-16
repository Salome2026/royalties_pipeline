CREATE SCHEMA IF NOT EXISTS `{project}.{dataset}`
OPTIONS(
  location = '{location}',
  description = 'VPO royalties analytics shadow dataset',
  labels = [('environment', 'shadow'), ('system', 'vpo')]
);

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.analytics_releases` (
  release_id STRING NOT NULL,
  manifest_generation STRING NOT NULL,
  published_at TIMESTAMP,
  loaded_at TIMESTAMP NOT NULL,
  status STRING NOT NULL,
  source_manifest_uri STRING NOT NULL,
  source_files INT64 NOT NULL,
  source_rows INT64 NOT NULL,
  source_amount_usd FLOAT64 NOT NULL,
  dashboard_rows INT64 NOT NULL,
  dashboard_amount_usd FLOAT64 NOT NULL,
  notes STRING
)
CLUSTER BY status, release_id
OPTIONS(description = 'Versiones analiticas cargadas desde releases inmutables de GCS');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.royalty_statement_fact` (
  release_id STRING NOT NULL,
  statement_month DATE,
  transaction_month DATE,
  source STRING,
  account STRING,
  source_sheet STRING,
  revenue_basis STRING,
  artist STRING,
  title STRING,
  asset_isrc STRING,
  product_upc STRING,
  track_id STRING,
  video_id STRING,
  channel_id STRING,
  label STRING,
  dsp STRING,
  store_name STRING,
  territory STRING,
  sale_type STRING,
  use_type STRING,
  monetization STRING,
  content_origin STRING,
  classification_status STRING,
  content_type STRING,
  amount_usd FLOAT64,
  units FLOAT64,
  include_in_statement_view BOOL,
  include_in_cash_view BOOL,
  include_in_catalog_view BOOL,
  possible_internal_transfer BOOL,
  statement_file_name STRING,
  statement_file_hash STRING
)
PARTITION BY statement_month
CLUSTER BY release_id, source, account, asset_isrc
OPTIONS(description = 'Detalle curado particionado por mes de statement');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.royalty_transaction_fact`
LIKE `{project}.{dataset}.royalty_statement_fact`
PARTITION BY transaction_month
CLUSTER BY release_id, source, account, asset_isrc
OPTIONS(description = 'Detalle curado particionado por mes de consumo');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.royalty_dashboard_rankings` (
  release_id STRING NOT NULL,
  statement_month DATE,
  transaction_month DATE,
  source STRING,
  account STRING,
  source_sheet STRING,
  artist STRING,
  title STRING,
  isrc STRING,
  upc STRING,
  dsp STRING,
  territory STRING,
  sale_type STRING,
  monetization STRING,
  content_origin STRING,
  classification_status STRING,
  label STRING,
  search_text STRING,
  amount_usd FLOAT64,
  units FLOAT64,
  raw_rows INT64
)
PARTITION BY statement_month
CLUSTER BY release_id, source, account, artist
OPTIONS(description = 'Agregado dimensional para dashboard y rankings');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.royalty_dashboard_monthly` (
  release_id STRING NOT NULL,
  statement_month DATE,
  transaction_month DATE,
  source STRING,
  account STRING,
  amount_usd FLOAT64,
  units FLOAT64,
  raw_rows INT64,
  artists INT64,
  titles INT64,
  isrcs INT64
)
PARTITION BY statement_month
CLUSTER BY release_id, source, account
OPTIONS(description = 'Totales mensuales por distribuidora y cuenta');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.royalty_song_level` (
  release_id STRING NOT NULL,
  transaction_month DATE,
  source STRING,
  account STRING,
  source_sheet STRING,
  revenue_basis STRING,
  include_in_cash_view BOOL,
  include_in_catalog_view BOOL,
  include_in_statement_view BOOL,
  possible_internal_transfer BOOL,
  asset_isrc STRING,
  track_id STRING,
  title STRING,
  artist STRING,
  amount_usd FLOAT64,
  units FLOAT64,
  content_type STRING,
  video_id STRING,
  channel_id STRING,
  statement_type STRING
)
PARTITION BY transaction_month
CLUSTER BY release_id, source, account, asset_isrc
OPTIONS(description = 'Agregado por tema del release');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.royalty_catalog` (
  release_id STRING NOT NULL,
  catalog_key STRING,
  asset_isrc STRING,
  track_id STRING,
  track_title STRING,
  artist_statement STRING,
  first_transaction_month DATE,
  last_transaction_month DATE,
  amount_usd FLOAT64,
  units FLOAT64,
  song_level_rows INT64,
  source_count INT64,
  account_count INT64,
  sources STRING,
  accounts STRING,
  title_variants STRING,
  artist_variants STRING,
  primary_upc STRING,
  isrcs STRING,
  upcs STRING,
  video_ids STRING,
  track_ids STRING,
  external_release_date DATE,
  external_label STRING,
  label_normalized STRING
)
CLUSTER BY release_id, catalog_key, asset_isrc
OPTIONS(description = 'Catalogo consolidado versionado');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.digital_income_summary` (
  release_id STRING NOT NULL,
  statement_month DATE,
  source STRING,
  account STRING,
  artist STRING,
  title STRING,
  search_text STRING,
  total_usd FLOAT64,
  has_share_in_out BOOL,
  raw_rows INT64
)
PARTITION BY statement_month
CLUSTER BY release_id, source, account, artist
OPTIONS(description = 'Resumen de ingresos digitales sin ajustes internos');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.analytics_reconciliation_runs` (
  run_id STRING NOT NULL,
  release_id STRING NOT NULL,
  started_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP NOT NULL,
  status STRING NOT NULL,
  amount_tolerance_usd FLOAT64 NOT NULL,
  units_tolerance FLOAT64 NOT NULL,
  group_count INT64 NOT NULL,
  mismatch_count INT64 NOT NULL,
  report_uri STRING,
  results_uri STRING,
  notes STRING
)
CLUSTER BY release_id, status, run_id
OPTIONS(description = 'Ejecuciones de conciliacion Parquet contra BigQuery');

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.analytics_reconciliation_results` (
  run_id STRING NOT NULL,
  release_id STRING NOT NULL,
  period_basis STRING NOT NULL,
  source STRING,
  account STRING,
  period_month DATE,
  parquet_rows INT64 NOT NULL,
  bigquery_rows INT64 NOT NULL,
  parquet_amount_usd FLOAT64 NOT NULL,
  bigquery_amount_usd FLOAT64 NOT NULL,
  amount_difference_usd FLOAT64 NOT NULL,
  parquet_units FLOAT64 NOT NULL,
  bigquery_units FLOAT64 NOT NULL,
  units_difference FLOAT64 NOT NULL,
  parquet_isrcs INT64 NOT NULL,
  bigquery_isrcs INT64 NOT NULL,
  parquet_missing_isrc_rows INT64 NOT NULL,
  bigquery_missing_isrc_rows INT64 NOT NULL,
  parquet_multi_isrc_title_groups INT64 NOT NULL,
  bigquery_multi_isrc_title_groups INT64 NOT NULL,
  status STRING NOT NULL,
  mismatch_reasons STRING
)
PARTITION BY period_month
CLUSTER BY release_id, period_basis, source, account
OPTIONS(description = 'Resultado de conciliacion por fuente, cuenta y mes');

CREATE OR REPLACE VIEW `{project}.{dataset}.current_release` AS
SELECT *
FROM `{project}.{dataset}.analytics_releases`
WHERE status = 'ready'
QUALIFY ROW_NUMBER() OVER (ORDER BY published_at DESC, loaded_at DESC) = 1;

CREATE OR REPLACE VIEW `{project}.{dataset}.royalty_report_detail` AS
SELECT fact.*
FROM `{project}.{dataset}.royalty_statement_fact` AS fact
WHERE fact.release_id = (SELECT release_id FROM `{project}.{dataset}.current_release`);

CREATE OR REPLACE VIEW `{project}.{dataset}.royalty_dashboard_current` AS
SELECT rankings.*
FROM `{project}.{dataset}.royalty_dashboard_rankings` AS rankings
WHERE rankings.release_id = (SELECT release_id FROM `{project}.{dataset}.current_release`);
