from __future__ import annotations

import json
import math
import os
import re
from collections import defaultdict

from google.cloud import bigquery

from app.bigquery_dashboard import normalize_search_text, personalization_factor_sql, month_date


def ranking_association_key(row: dict, snapshot: dict) -> str | None:
    if row.get("isrc"):
        return None
    # The published producer serializes these four fields, then the native ID slot.
    # Decode that slot only; never search titles or other metadata for an identifier.
    prefix = " ".join(str(row.get(key) or "").lower() for key in ("artist", "title", "isrc", "upc")) + " "
    search = row.get("search_text") or ""
    if not search.startswith(prefix):
        return None
    code = search[len(prefix):].partition(" ")[0]
    index = snapshot["associations"]
    if code:
        scope = json.dumps([code, row["source"], row["account"]], separators=(",", ":"))
        if not index["search_codes"].get(scope):
            return None
    elif not row.get("upc"):
        return None
    return json.dumps([row["source"], row["account"], row.get("source_sheet") or "", row["statement_month"],
                       "ID" if code else "UPC", code or row["upc"]], separators=(",", ":"))


def select_associated_rankings(rows: list[dict], request, snapshot: dict) -> list[dict]:
    tracks = {row["isrc"]: row for row in snapshot["catalog"]}
    artists = [normalize_search_text(name) for name in snapshot["artists"]]
    keywords = [normalize_search_text(name) for name in request.keywords]
    owners = snapshot["associations"]["ranking_owners"]
    observed: dict[str, dict] = defaultdict(lambda: {"amount_usd": 0.0, "raw_rows": 0})
    for row in rows:
        key = ranking_association_key(row, snapshot)
        if key in owners:
            observed[key]["amount_usd"] += float(row["gross_amount_usd"] or 0)
            observed[key]["raw_rows"] += int(row["raw_rows"] or 0)
    reconciled = set()
    for key, total in observed.items():
        expected = owners[key]
        if total["raw_rows"] == expected["raw_rows"] and math.isclose(
            total["amount_usd"], expected["amount_usd"], rel_tol=1e-9, abs_tol=0.00001):
            reconciled.add(key)
    selected = []
    for row in rows:
        key = ranking_association_key(row, snapshot)
        root = owners[key]["isrc"] if key in reconciled else None
        original_search = row["normalized_search"]
        compact = re.sub(r"[\s_-]+", "", original_search)
        original_scope = row.get("isrc") in tracks or any(
            token in original_search or re.sub(r"[\s_-]+", "", token) in compact for token in artists)
        if not original_scope and root not in tracks:
            continue
        canonical = normalize_search_text(f"{root} {tracks[root]['title']}") if root in tracks else ""
        if keywords and not any(token in original_search or token in canonical for token in keywords):
            continue
        selected.append({**row, "isrc": root if root in tracks else row.get("isrc")})
    return selected


def association_query_parameter(snapshot: dict, request):
    fields = ("source", "account", "sheet", "month", "kind", "code")
    selected = {row["isrc"] for row in snapshot["catalog"]}
    codes = set()
    index = snapshot["associations"]
    for key, owner in index["ranking_owners"].items():
        if owner["isrc"] not in selected:
            continue
        source, account, sheet, month, kind, code = json.loads(key)
        if not source or not account or (request.source and source != request.source) or (request.account and account != request.account):
            continue
        if (request.start_month and month < request.start_month) or (request.end_month and month > request.end_month):
            continue
        if kind == "ID":
            scope = json.dumps([code, source, account], separators=(",", ":"))
            if not index["search_codes"].get(scope):
                continue
        codes.add((source, account, sheet, month, kind, code))
    struct_type = bigquery.StructQueryParameterType(
        *(bigquery.ScalarQueryParameterType("STRING", name=name) for name in fields))
    values = [bigquery.StructQueryParameter(None, *(
        bigquery.ScalarQueryParameter(name, "STRING", value) for name, value in zip(fields, item)))
        for item in sorted(codes)]
    return bigquery.ArrayQueryParameter("associated_codes", struct_type, values)


def query_contract_income(request, manifest: dict, policy: dict) -> list[dict]:
    release = manifest.get("release_id")
    snapshot = manifest.get("contract_snapshot") or {}
    version = snapshot.get("schema_version")
    if not release or version not in {1, 2} or not snapshot.get("artists"):
        raise ValueError("Falta la versión de datos o la copia de contratos del pedido.")
    if version == 2:
        index = snapshot.get("associations") or {}
        if index.get("release_id") != release or any(
            not isinstance(index.get(name), dict) for name in ("included", "excluded", "search_codes", "ranking_owners")) or index.get("ranking_layout") != "artist-title-isrc-upc-id-v1":
            raise ValueError("Falta la validacion de asociados de la version de datos del pedido.")
    project = os.environ.get("VPO_BIGQUERY_PROJECT", "vpo-corp-royalties")
    dataset = os.environ.get("VPO_BIGQUERY_DATASET", "royalties_analytics")
    client = bigquery.Client(project=project, location=os.environ.get("VPO_BIGQUERY_LOCATION", "US"))
    norm = r"REGEXP_REPLACE(NORMALIZE_AND_CASEFOLD(COALESCE(search_text, ''), NFD), r'\pM', '')"
    prefix = "CONCAT(LOWER(COALESCE(artist, '')), ' ', LOWER(COALESCE(title, '')), ' ', LOWER(COALESCE(isrc, '')), ' ', LOWER(COALESCE(upc, '')), ' ')"
    code_column = f", IF(STARTS_WITH(search_text, {prefix}), SPLIT(SUBSTR(search_text, LENGTH({prefix}) + 1), ' ')[SAFE_OFFSET(0)], NULL) AS serialized_code" if version == 2 else ""
    association_scope = """OR (COALESCE(isrc, '') = '' AND EXISTS (
 SELECT 1 FROM UNNEST(@associated_codes) code
 WHERE code.source = ranking.source AND code.account = ranking.account
 AND code.sheet = COALESCE(ranking.source_sheet, '')
 AND code.month = FORMAT_DATE('%Y-%m', ranking.statement_month)
 AND ((code.kind = 'UPC' AND code.code = ranking.upc AND ranking.serialized_code = '')
 OR (code.kind = 'ID' AND code.code = ranking.serialized_code))))""" if version == 2 else ""
    identity_columns = ", source_sheet, search_text, normalized_search" if version == 2 else ""
    gross_column = ", SUM(COALESCE(amount_usd, 0)) AS gross_amount_usd" if version == 2 else ""
    keyword_scope = """(COALESCE(ARRAY_LENGTH(@keywords), 0) = 0 OR EXISTS (
 SELECT 1 FROM UNNEST(@keywords) token WHERE STRPOS(normalized_search, token) > 0))""" if version == 1 else "TRUE"
    # Keep the original eligible ranking measures, search text, units and net discounts.
    sql = rf"""
WITH base AS (
 SELECT *, {norm} AS normalized_search {code_column}
 FROM `{project}.{dataset}.royalty_dashboard_rankings`
 WHERE release_id = @release_id
   AND (@source IS NULL OR source = @source) AND (@account IS NULL OR account = @account)
   AND (@start_month IS NULL OR statement_month >= @start_month)
   AND (@end_month IS NULL OR statement_month <= @end_month)
)
SELECT isrc, upc, artist, title, source, account {identity_columns},
 FORMAT_DATE('%Y-%m', statement_month) AS statement_month,
 SUM(COALESCE(amount_usd, 0) * ({personalization_factor_sql(policy)})) AS amount_usd,
 SUM(COALESCE(units, 0)) AS units, SUM(COALESCE(raw_rows, 0)) AS raw_rows {gross_column}
FROM base AS ranking
WHERE (isrc IN UNNEST(@isrcs) OR EXISTS (
 SELECT 1 FROM UNNEST(@artists) token
 WHERE STRPOS(normalized_search, token) > 0
 OR STRPOS(REGEXP_REPLACE(normalized_search, r'[\s_-]+', ''), REGEXP_REPLACE(token, r'[\s_-]+', '')) > 0)
 {association_scope})
 AND {keyword_scope}
GROUP BY isrc, upc, artist, title, source, account, statement_month {identity_columns}
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
    if version == 2:
        params.append(association_query_parameter(snapshot, request))
    result = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params,
                          maximum_bytes_billed=int(os.environ.get("VPO_BIGQUERY_MAX_BYTES_BILLED", "5000000000")))).result(timeout=300)
    rows = [dict(row.items()) for row in result]
    if version == 2:
        rows = select_associated_rankings(rows, request, snapshot)
    if not rows:
        raise ValueError("No hay ingresos para los artistas y el período seleccionados.")
    return rows
