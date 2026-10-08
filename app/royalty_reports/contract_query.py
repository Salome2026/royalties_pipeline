from __future__ import annotations

import os

from google.cloud import bigquery

from app.bigquery_dashboard import normalize_search_text, personalization_factor_sql, month_date


def query_contract_income(request, manifest: dict, policy: dict) -> list[dict]:
    release = manifest.get("release_id")
    snapshot = manifest.get("contract_snapshot") or {}
    if not release or snapshot.get("schema_version") != 1 or not snapshot.get("artists"):
        raise ValueError("Falta la versión de datos o la copia de contratos del pedido.")
    project = os.environ.get("VPO_BIGQUERY_PROJECT", "vpo-corp-royalties")
    dataset = os.environ.get("VPO_BIGQUERY_DATASET", "royalties_analytics")
    client = bigquery.Client(project=project, location=os.environ.get("VPO_BIGQUERY_LOCATION", "US"))
    norm = r"REGEXP_REPLACE(NORMALIZE_AND_CASEFOLD(COALESCE(search_text, ''), NFD), r'\pM', '')"
    # Match the dashboard search, including compact hashtags. ISRC scope preserves collaborations.
    sql = rf"""
WITH base AS (
 SELECT *, {norm} AS normalized_search
 FROM `{project}.{dataset}.royalty_dashboard_rankings`
 WHERE release_id = @release_id
   AND (@source IS NULL OR source = @source) AND (@account IS NULL OR account = @account)
   AND (@start_month IS NULL OR statement_month >= @start_month)
   AND (@end_month IS NULL OR statement_month <= @end_month)
)
SELECT isrc, upc, artist, title, source, account, FORMAT_DATE('%Y-%m', statement_month) AS statement_month,
 SUM(COALESCE(amount_usd, 0) * ({personalization_factor_sql(policy)})) AS amount_usd,
 SUM(COALESCE(units, 0)) AS units, SUM(COALESCE(raw_rows, 0)) AS raw_rows
FROM base
WHERE (isrc IN UNNEST(@isrcs) OR EXISTS (
 SELECT 1 FROM UNNEST(@artists) token
 WHERE STRPOS(normalized_search, token) > 0
 OR STRPOS(REGEXP_REPLACE(normalized_search, r'[\s_-]+', ''), REGEXP_REPLACE(token, r'[\s_-]+', '')) > 0))
 AND (COALESCE(ARRAY_LENGTH(@keywords), 0) = 0 OR EXISTS (
 SELECT 1 FROM UNNEST(@keywords) token WHERE STRPOS(normalized_search, token) > 0))
GROUP BY isrc, upc, artist, title, source, account, statement_month
ORDER BY statement_month, isrc, upc, title, artist, source, account
"""
    params = [bigquery.ScalarQueryParameter("release_id", "STRING", release),
              bigquery.ArrayQueryParameter("isrcs", "STRING", [row["isrc"] for row in snapshot["catalog"]]),
              bigquery.ArrayQueryParameter("artists", "STRING", [normalize_search_text(name) for name in snapshot["artists"]]),
              bigquery.ArrayQueryParameter("keywords", "STRING", [normalize_search_text(name) for name in request.keywords]),
              bigquery.ScalarQueryParameter("source", "STRING", request.source),
              bigquery.ScalarQueryParameter("account", "STRING", request.account),
              bigquery.ScalarQueryParameter("start_month", "DATE", month_date(request.start_month)),
              bigquery.ScalarQueryParameter("end_month", "DATE", month_date(request.end_month))]
    result = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params,
                          maximum_bytes_billed=int(os.environ.get("VPO_BIGQUERY_MAX_BYTES_BILLED", "5000000000")))).result(timeout=300)
    rows = [dict(row.items()) for row in result]
    if not rows:
        raise ValueError("No hay ingresos para los artistas y el período seleccionados.")
    return rows
