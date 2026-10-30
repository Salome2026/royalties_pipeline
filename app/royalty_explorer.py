"""Read-only contractual dashboard: pinned identities, closed rules, SQL aggregation.

The ordinary dashboard is untouched. Monetary measures alone are apportioned;
units always belong to the underlying income rows. Access is checked by the API
before consulting these server-side caches or producing a response.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
import os
import threading
import time
from zoneinfo import ZoneInfo

from google.cloud import bigquery, storage

from app.bigquery_dashboard import (dashboard_client, month_date,
                                   normalize_search_text, personalization_factor_sql)
from app.master_contracts import validate_split, _period_start, _period_end
from app.royalty_reports.contractual import allocation_rows, beneficiary_key, round_money, settle_amounts
from app.royalty_reports.contract_snapshot import (published_catalog_frame, contract_catalog_rows,
                                                 freeze_contract_associations)
from app.royalty_reports.excel_contracts import _contract_names, _credit_names
from app.royalty_reports.manifests import build_gcs_input_manifest

PROJECT = os.environ.get("VPO_BIGQUERY_PROJECT", "vpo-corp-royalties")
DATASET = os.environ.get("VPO_BIGQUERY_DATASET", "royalties_analytics")
LOCATION = os.environ.get("VPO_BIGQUERY_LOCATION", "US")
DIMENSIONS = {"dsp": "dsp", "monetization": "monetization", "content_origin": "content_origin",
              "territory": "territory", "artist": "artist", "label": "label", "source": "source",
              "account": "account", "month": "period_month", "track": "identity_key"}
_LOCK = threading.RLock()
# Historical portal permission labels are separate from economic beneficiaries.
# This explicit equivalence preserves the existing Candu login without granting
# access by substring, or renaming recipients in any saved contract.
PORTAL_SCOPE_LABELS = {"candu": "candu dominguez"}


def scope_keys(scope: set[str] | None) -> set[str] | None:
    if scope is None:
        return None
    return {PORTAL_SCOPE_LABELS.get(beneficiary_key(name), beneficiary_key(name)) for name in scope}


def registry_rows(conn) -> list[dict]:
    return [{"isrc": r["isrc"], "split": json.loads(r["payload_json"]), "is_closed": bool(r["is_closed"]),
             "future_reports_selected": bool(r["future_reports_selected"]), "version": int(r["version"])}
            for r in conn.execute("SELECT isrc,payload_json,is_closed,future_reports_selected,version FROM master_contract_splits ORDER BY isrc").fetchall()]


def participant_names(catalog: list[dict], contracts: list[dict]) -> dict[str, str]:
    names = {}
    for row in catalog:
        for name in _credit_names(row):
            names.setdefault(beneficiary_key(name), name.strip())
    for record in contracts:
        for name in _contract_names(record["split"]):
            names.setdefault(beneficiary_key(name), name.strip())
    return {key: name for key, name in names.items() if key}


def authorize_beneficiary(value: str | None, names: dict[str, str], scope: set[str] | None) -> str | None:
    key = beneficiary_key(value or "")
    allowed = scope_keys(scope)
    if allowed is not None:
        if not key and len(allowed) == 1:
            key = next(iter(allowed))
        if not key or key not in allowed:
            raise PermissionError("Elegí uno de tus artistas habilitados.")
    if key and key not in names:
        raise ValueError("Elegí un beneficiario del catálogo o de los contratos.")
    return names.get(key) if key else None


@lru_cache(maxsize=2)
def _manifest(bucket: str, prefix: str, clock_slot: int) -> str:
    from app.catalog_refresh import pin_report_dashboard
    document = build_gcs_input_manifest(client=storage.Client(), bucket_name=bucket, prefix=prefix,
        filenames=["catalog_master.parquet", "catalog_status.parquet", "standardized_raw_all_sources.parquet",
                   "catalog_release_metadata.parquet"])
    pin_report_dashboard(document)
    return json.dumps(document, sort_keys=True)


def current_manifest() -> str:
    return _manifest(os.environ["GCS_BUCKET"], os.environ.get("GCS_PREFIX", "marts"), int(time.time() // 30))


@lru_cache(maxsize=2)
def catalog_data(manifest_json: str) -> tuple[list[dict], list[dict]]:
    frame = published_catalog_frame(storage.Client(), json.loads(manifest_json))
    return frame.to_dicts(), contract_catalog_rows(frame)


def read_options(contracts: list[dict], scope: set[str] | None, keyword: str | None = None) -> dict:
    catalog, _ = catalog_data(current_manifest())
    names = participant_names(catalog, contracts)
    allowed = scope_keys(scope)
    if keyword is not None:
        # Contextual actions come from actual contractual recipients, never a
        # compound catalog credit or an arbitrary channel/title string.
        recipients = {}
        for record in contracts:
            for agreement in record["split"].get("agreements") or []:
                try:
                    for share in allocation_rows(agreement, record["split"]):
                        key = beneficiary_key(share["artist"])
                        if key and share["percent"] > 0 and (allowed is None or key in allowed):
                            recipients.setdefault(key, names.get(key, share["artist"]))
                except (ValueError, TypeError, KeyError, ZeroDivisionError):
                    continue
        key = beneficiary_key(keyword)
        key = PORTAL_SCOPE_LABELS.get(key, key)
        if allowed is not None and len(allowed) == 1 and not key:
            key = next(iter(allowed))
        return {"participant": recipients.get(key), "restricted": scope is not None}
    return {"beneficiaries": sorted([name for key, name in names.items() if allowed is None or key in allowed], key=beneficiary_key),
            "restricted": scope is not None}


def native_columns() -> str:
    prefix = "CONCAT(LOWER(COALESCE(artist,'')), ' ', LOWER(COALESCE(title,'')), ' ', LOWER(COALESCE(isrc,'')), ' ', LOWER(COALESCE(upc,'')), ' ')"
    return f"IF(STARTS_WITH(search_text,{prefix}),SPLIT(SUBSTR(search_text,LENGTH({prefix})+1),' ')[SAFE_OFFSET(0)],NULL)"


def _execute_job(sql: str, params: list, client):
    config = bigquery.QueryJobConfig(query_parameters=params,
        maximum_bytes_billed=int(os.environ.get("VPO_BIGQUERY_MAX_BYTES_BILLED", "5000000000")))
    return [dict(row) for row in client.query(sql, job_config=config, location=LOCATION).result(timeout=180)]


@lru_cache(maxsize=16)
def _cached_job(sql: str, parameters: str):
    # SQL and typed parameters contain the immutable release, saved rules and
    # server-enforced scope. Permission checks always run before this cache.
    params = [_parameter_from_api(value) for value in json.loads(parameters)]
    return _execute_job(sql, params, dashboard_client(PROJECT, LOCATION))


def _parameter_from_api(value):
    kind = value["parameterType"]["type"]
    if kind == "ARRAY":
        item = value["parameterType"]["arrayType"]
        if item["type"] == "STRUCT" and not value["parameterValue"].get("arrayValues"):
            return bigquery.ArrayQueryParameter(value.get("name"), bigquery.StructQueryParameterType.from_api_repr(item), [])
        return bigquery.ArrayQueryParameter.from_api_repr(value)
    factory = bigquery.StructQueryParameter if kind == "STRUCT" else bigquery.ScalarQueryParameter
    return factory.from_api_repr(value)


def _job(sql: str, params: list, *, client=None):
    if client is not None:
        return _execute_job(sql, params, client)
    return _cached_job(sql, json.dumps([p.to_api_repr() for p in params], sort_keys=True))


@lru_cache(maxsize=2)
def _context(manifest_json: str, registry_json: str) -> dict:
    manifest = json.loads(manifest_json)
    contracts = json.loads(registry_json)
    catalog, tracks = catalog_data(manifest_json)
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    snapshot = {"schema_version": 1, "artists": [], "catalog": tracks, "contracts": contracts, "as_of": today}
    frame = published_catalog_frame(storage.Client(), manifest)
    from app.royalty_reports.contract_identity import cached_ranking_guard
    guard = cached_ranking_guard(manifest)
    if guard is None:
        raise RuntimeError("La validación de identidades de esta publicación todavía se está preparando.")
    frozen = freeze_contract_associations(snapshot, frame, contracts, manifest["release_id"], input_manifest=manifest, ranking_guard=guard)
    table_name = "royalty_catalog_dashboard" if manifest.get("catalog_dashboard") else "royalty_dashboard_rankings"
    release = (manifest.get("catalog_dashboard") or {}).get("release_id") or manifest["release_id"]
    table = f"`{PROJECT}.{DATASET}.{table_name}`"
    # Reconcile whole native slots before any period/platform/territory drill.
    # A partial dimension must never turn a conflicting identity into a valid association.
    rows = _job(f"""WITH native AS (
      SELECT *, {native_columns()} AS slot FROM {table}
      WHERE release_id=@release AND COALESCE(isrc,'')=''
    ) SELECT source,account,COALESCE(source_sheet,'') AS sheet,
      FORMAT_DATE('%Y-%m',statement_month) AS month,
      IF(COALESCE(slot,'')!='','ID','UPC') AS kind,
      IF(COALESCE(slot,'')!='',slot,upc) AS code,
      SUM(amount_usd) AS amount_usd,SUM(raw_rows) AS raw_rows
    FROM native WHERE statement_month IS NOT NULL AND (COALESCE(slot,'')!='' OR COALESCE(upc,'')!='')
    GROUP BY source,account,sheet,month,kind,code""",
      [bigquery.ScalarQueryParameter("release", "STRING", release)])
    owners = frozen["associations"]["ranking_owners"]
    bindings = []
    for row in rows:
        key = json.dumps([row[name] for name in ("source", "account", "sheet", "month", "kind", "code")], separators=(",", ":"))
        owner = owners.get(key)
        if owner and int(row["raw_rows"] or 0) == owner["raw_rows"] and math.isclose(
                float(row["amount_usd"] or 0), owner["amount_usd"], rel_tol=1e-9, abs_tol=0.00001):
            bindings.append({**{k: row[k] for k in ("source", "account", "sheet", "month", "kind", "code")}, "root": owner["isrc"]})
    return {"snapshot": snapshot, "catalog": catalog, "names": participant_names(catalog, contracts),
            "bindings": bindings, "table": table, "release": release,
            "revision": hashlib.sha256(registry_json.encode()).hexdigest()[:16]}


def get_context(contracts: list[dict]) -> dict:
    # Single-flight protects cold starts from loading multiple raw identity guards.
    with _LOCK:
        return _context(current_manifest(), json.dumps(contracts, sort_keys=True))


def compiled_rules(context: dict, beneficiary: str | None, *, restrict_tracks: bool = True) -> tuple[list[dict], list[dict], dict]:
    key = beneficiary_key(beneficiary or "")
    records = {row["isrc"]: row for row in context["snapshot"]["contracts"]}
    metadata = {row["isrc"]: row for row in context["snapshot"]["catalog"]}
    credits = defaultdict(set)
    for row in context["catalog"]:
        if row.get("asset_isrc"):
            credits[row["asset_isrc"]].update(beneficiary_key(n) for n in _credit_names(row))
    selected, rules, all_rules = [], [], {}
    for root, track in metadata.items():
        saved = records.get(root) or {}
        split = saved.get("split") or {}
        names = credits[root] | {beneficiary_key(n) for n in _contract_names(split)}
        if restrict_tracks and key and key not in names:
            continue
        reason = ""
        if not saved.get("is_closed"):
            reason = "Contrato abierto o sin definir"
        else:
            try:
                validate_split(split, True, True)
                if not split.get("agreements"):
                    raise ValueError("Sin vigencia contractual")
                all_rules[root] = []
                for agreement in split["agreements"]:
                    shares = allocation_rows(agreement, split)
                    start = _period_start(agreement["effective_from"])
                    end = _period_end(agreement["effective_until"]) if agreement.get("effective_until") else date.max
                    rate = sum(s["percent"] for s in shares if beneficiary_key(s["artist"]) == key)
                    rules.append({"root": root, "start": start, "end": end, "percent": rate, "version": saved["version"]})
                    all_rules[root].append({"from": start.isoformat(), "until": agreement.get("effective_until"),
                        "end": end.isoformat(), "shares": shares, "version": saved["version"], "label": agreement.get("label") or "Contrato"})
            except (ValueError, TypeError, KeyError, ZeroDivisionError):
                reason = "Contrato inválido; requiere revisión"
                rules = [r for r in rules if r["root"] != root]
                all_rules.pop(root, None)
        selected.append({"root": root, "title": track["title"], "reason": reason})
    return selected, rules, all_rules


def _struct_array(name: str, fields: list[tuple[str, str]], rows: list[dict]):
    struct = bigquery.StructQueryParameterType(*[bigquery.ScalarQueryParameterType(kind, name=key) for key, kind in fields])
    values = [bigquery.StructQueryParameter(None, *[bigquery.ScalarQueryParameter(key, kind, row.get(key)) for key, kind in fields]) for row in rows]
    return bigquery.ArrayQueryParameter(name, struct, values)


def base_query(context: dict, policy: dict, beneficiary: str | None, *, measure: str, restricted: bool,
               period_basis: str, source: str | None, account: str | None, keyword: str,
               start_month: str | None, end_month: str | None, drill: dict,
               track_key: str | None = None, track_title: str | None = None):
    if period_basis not in {"statement_period", "transaction_month"}:
        raise ValueError("Base temporal inválida.")
    if set(drill) - set(DIMENSIONS) or any(not isinstance(v, str) or len(v) > 500 for v in drill.values()):
        raise ValueError("Filtro de exploración inválido.")
    for value in (start_month, end_month, drill.get("month")):
        if value:
            month_date(value)
    if start_month and end_month and start_month > end_month:
        raise ValueError("El rango de meses está invertido.")
    tracks, rules, full_rules = compiled_rules(context, beneficiary, restrict_tracks=restricted)
    roots = {row["root"] for row in tracks}
    bindings = [row for row in context["bindings"] if not restricted or row["root"] in roots]
    params = [bigquery.ScalarQueryParameter("release", "STRING", context["release"]),
              bigquery.ScalarQueryParameter("source", "STRING", source), bigquery.ScalarQueryParameter("account", "STRING", account),
              bigquery.ScalarQueryParameter("start", "DATE", month_date(start_month)), bigquery.ScalarQueryParameter("end", "DATE", month_date(end_month)),
              bigquery.ScalarQueryParameter("track_key", "STRING", track_key), bigquery.ScalarQueryParameter("track_title", "STRING", track_title),
              bigquery.ArrayQueryParameter("keywords", "STRING", normalize_search_text(keyword).split()),
              bigquery.ScalarQueryParameter("beneficiary_search", "STRING", normalize_search_text(beneficiary or "")),
              bigquery.ScalarQueryParameter("all_tracks", "BOOL", not restricted),
              bigquery.ScalarQueryParameter("restricted", "BOOL", restricted),
              bigquery.ArrayQueryParameter("roots", "STRING", sorted(roots)),
              _struct_array("tracks", [("root", "STRING"), ("title", "STRING"), ("reason", "STRING")], tracks),
              _struct_array("rules", [("root", "STRING"), ("start", "DATE"), ("end", "DATE"), ("percent", "FLOAT64"), ("version", "INT64")], rules),
              _struct_array("bindings", [(k, "STRING") for k in ("source", "account", "sheet", "month", "kind", "code", "root")], bindings)]
    for name in DIMENSIONS:
        params.append(bigquery.ScalarQueryParameter("drill_" + name, "DATE" if name == "month" else "STRING",
            month_date(drill[name]) if name == "month" and drill.get(name) else drill.get(name)))
    factor = personalization_factor_sql(policy)
    period_col = "transaction_month" if period_basis == "transaction_month" else "statement_month"
    amount = "COALESCE(r.percent,0) / 100" if measure == "contractual" else "1.0"
    # Restricted users are scoped to canonical tracks before any output, never by a caller's title substring.
    scope = "t.root IS NOT NULL" if restricted else "TRUE"
    name = "COALESCE(t.title,n.title)" if restricted else "n.title"
    filters = " AND ".join(f"(@drill_{key} IS NULL OR {column}=@drill_{key})" for key, column in DIMENSIONS.items() if key != "track")
    sql = f"""WITH native_all AS (
      SELECT *,{native_columns()} AS slot,
       REGEXP_REPLACE(NORMALIZE_AND_CASEFOLD(COALESCE(search_text,''),NFD),r'\\pM','') AS normalized_search
      FROM {context['table']} WHERE release_id=@release
    ), native_scope AS (
      SELECT *,{period_col} AS option_month FROM native_all n WHERE (@all_tracks OR n.isrc IN UNNEST(@roots)
       OR (COALESCE(n.isrc,'')='' AND (
        (NOT @restricted AND @beneficiary_search!='' AND STRPOS(normalized_search,@beneficiary_search)>0)
        OR EXISTS(SELECT 1 FROM UNNEST(@bindings) b WHERE b.source=n.source AND b.account=n.account
          AND b.sheet=COALESCE(n.source_sheet,'') AND b.month=FORMAT_DATE('%Y-%m',n.statement_month)
          AND ((b.kind='ID' AND b.code=n.slot) OR (b.kind='UPC' AND COALESCE(n.slot,'')='' AND b.code=n.upc))))))
    ), native AS (
      SELECT * FROM native_scope n WHERE (@source IS NULL OR n.source=@source) AND (@account IS NULL OR n.account=@account)
       AND (@start IS NULL OR n.{period_col}>=@start) AND (@end IS NULL OR n.{period_col}<=@end)
       AND NOT EXISTS(SELECT 1 FROM UNNEST(@keywords) token WHERE STRPOS(normalized_search,token)=0
         AND STRPOS(REGEXP_REPLACE(normalized_search,r'[\\s_-]+',''),REGEXP_REPLACE(token,r'[\\s_-]+',''))=0)
    ), resolved AS (
      SELECT n.*,COALESCE(NULLIF(n.isrc,''),b.root) AS root
      FROM native n LEFT JOIN UNNEST(@bindings) b ON COALESCE(n.isrc,'')=''
       AND b.source=n.source AND b.account=n.account AND b.sheet=COALESCE(n.source_sheet,'')
       AND b.month=FORMAT_DATE('%Y-%m',n.statement_month)
       AND ((b.kind='ID' AND b.code=n.slot) OR (b.kind='UPC' AND COALESCE(n.slot,'')='' AND b.code=n.upc))
    ), scoped_base AS (
      SELECT n.* EXCEPT(title,isrc,amount_usd), {name} AS title, n.root AS isrc,
       IF(n.root IS NOT NULL,CONCAT('ISRC:',n.root),CONCAT('REF:',TO_HEX(SHA256(CONCAT(COALESCE(n.source,''),'|',COALESCE(n.account,''),'|',COALESCE(n.source_sheet,''),'|',COALESCE(n.search_text,'')))))) AS identity_key,
       {period_col} AS period_month,
       COALESCE(n.amount_usd,0)*({factor}) AS base_amount_usd,
       COALESCE(n.amount_usd,0)*({factor})*({amount}) AS amount_usd,
       IF(r.root IS NULL,COALESCE(n.amount_usd,0)*({factor}),0) AS pending_amount_usd,
       IF(r.root IS NULL,COALESCE(NULLIF(t.reason,''),IF(n.root IS NULL,'Sin ISRC asociado válido',IF(t.root IS NULL,'ISRC fuera del catálogo de contratos','Fuera de la vigencia guardada'))),'') AS pending_reason,
       r.percent AS contract_percent,r.version AS contract_version
      FROM resolved n LEFT JOIN UNNEST(@tracks) t ON t.root=n.root
      LEFT JOIN UNNEST(@rules) r ON r.root=n.root AND n.statement_month BETWEEN r.start AND r.end
      WHERE {scope}
    ), filtered AS (
      SELECT * FROM scoped_base WHERE period_month IS NOT NULL
       AND (@source IS NULL OR source=@source) AND (@account IS NULL OR account=@account)
       AND (@start IS NULL OR period_month>=@start) AND (@end IS NULL OR period_month<=@end)
       AND NOT EXISTS(SELECT 1 FROM UNNEST(@keywords) token WHERE STRPOS(normalized_search,token)=0
         AND STRPOS(REGEXP_REPLACE(normalized_search,r'[\\s_-]+',''),REGEXP_REPLACE(token,r'[\\s_-]+',''))=0)
       AND {filters}
    )"""
    return sql, params, full_rules


def _period_sql(period_mode: str) -> str:
    if period_mode not in {"last_6_months", "last_12_months", "all", "single_month", "closed_range"}:
        raise ValueError("Período inválido.")
    tail = " LIMIT 6" if period_mode == "last_6_months" else " LIMIT 12" if period_mode == "last_12_months" else ""
    return f", selected_months AS (SELECT DISTINCT period_month FROM filtered ORDER BY period_month DESC{tail}), scoped AS (SELECT * FROM filtered WHERE period_month IN (SELECT period_month FROM selected_months) AND (@drill_track IS NULL OR identity_key=@drill_track) AND (@track_key IS NULL OR identity_key=@track_key) AND (@track_title IS NULL OR title=@track_title))"


def dashboard_sql(base: str, period_mode: str, limit: int) -> str:
    categories = {"sources": "source", "dsp": "dsp", "monetization": "monetization", "content_origin": "content_origin",
                  "territory": "territory", "sale_type": "sale_type", "artist": "artist", "title": "title", "label": "label"}
    unions = []
    for youtube, dataset in ((False, "scoped"), (True, "youtube")):
        for category, field in categories.items():
            if youtube and category not in {"monetization", "content_origin", "title", "territory"}:
                continue
            identity = "identity_key" if category == "title" else "CAST(NULL AS STRING)"
            group = f"{field},identity_key" if category == "title" else field
            unions.append(f"SELECT '{'youtube_ranking' if youtube else 'ranking'}' AS section,'{category}' AS category,{field} AS name,{identity} AS identity_key,"
                f"SUM(amount_usd) AS amount_usd,SUM(units) AS units,SUM(raw_rows) AS `rows`,SUM(pending_amount_usd) AS pending_amount_usd FROM {dataset} WHERE COALESCE({field},'')!='' GROUP BY {group}")
    rank_sql = " UNION ALL ".join(unions)
    stats = """ROUND(COALESCE(SUM(amount_usd),0),2) AS amount_usd,
      COALESCE(SUM(units),0) AS units,COALESCE(SUM(raw_rows),0) AS `rows`,
      COUNT(DISTINCT period_month) AS months,COUNT(DISTINCT source) AS sources,
      COUNT(DISTINCT account) AS accounts,
      COUNT(DISTINCT title) AS titles,COUNT(DISTINCT artist) AS artists,
      FORMAT_DATE('%Y-%m',MIN(period_month)) AS first_month,FORMAT_DATE('%Y-%m',MAX(period_month)) AS last_month"""
    return base + _period_sql(period_mode) + f""",
      youtube AS (SELECT * FROM scoped WHERE dsp='YouTube'),
      ranked AS ({rank_sql}),
      ranking AS (SELECT * FROM ranked QUALIFY ROW_NUMBER() OVER(PARTITION BY section,category ORDER BY amount_usd DESC,name,identity_key)<={max(3,min(limit,50))})
    SELECT 'totals' AS section,TO_JSON_STRING(t) AS payload FROM (SELECT {stats} FROM scoped) t
    UNION ALL SELECT 'youtube_totals',TO_JSON_STRING(t) FROM (SELECT {stats} FROM youtube) t
    UNION ALL SELECT 'monthly',TO_JSON_STRING(t) FROM (
      SELECT FORMAT_DATE('%Y-%m',period_month) AS month,SUM(amount_usd) AS amount_usd,SUM(units) AS units,SUM(raw_rows) AS `rows`
      FROM scoped GROUP BY period_month) t
    UNION ALL SELECT 'matrix',TO_JSON_STRING(t) FROM (
      SELECT source,account,SUM(amount_usd) AS amount_usd,SUM(units) AS units,SUM(raw_rows) AS `rows`,
        COUNT(DISTINCT title) AS titles,COUNT(DISTINCT artist) AS artists FROM scoped GROUP BY source,account) t
    UNION ALL SELECT 'matrix_month',TO_JSON_STRING(t) FROM (
      SELECT source,account,FORMAT_DATE('%Y-%m',period_month) AS month,SUM(amount_usd) AS amount_usd FROM scoped GROUP BY source,account,period_month) t
    UNION ALL SELECT section,TO_JSON_STRING(t) FROM ranking t
    UNION ALL SELECT 'option_pair',TO_JSON_STRING(t) FROM (SELECT DISTINCT source,account FROM native_scope) t
    UNION ALL SELECT 'option_bounds',TO_JSON_STRING(t) FROM (
      SELECT FORMAT_DATE('%Y-%m',MIN(option_month)) AS first_month,FORMAT_DATE('%Y-%m',MAX(option_month)) AS last_month FROM native_scope) t
    UNION ALL SELECT 'contract_summary',TO_JSON_STRING(t) FROM (
      SELECT ROUND(COALESCE(SUM(base_amount_usd),0),2) AS base_amount_usd,
      ROUND(COALESCE(SUM(pending_amount_usd),0),2) AS pending_amount_usd,
      COUNT(DISTINCT IF(pending_reason!='',identity_key,NULL)) AS pending_tracks FROM scoped) t
    UNION ALL SELECT 'pending',TO_JSON_STRING(t) FROM (
      SELECT identity_key,ANY_VALUE(title) AS title,pending_reason AS reason,
        SUM(pending_amount_usd) AS amount_usd FROM scoped WHERE pending_reason!=''
      GROUP BY identity_key,pending_reason) t"""


def format_dashboard(rows: list[dict], *, context: dict, policy: dict, beneficiary: str | None,
                     measure: str, restricted: bool, period_basis: str, keyword: str) -> dict:
    sections = defaultdict(list)
    for row in rows:
        sections[row["section"]].append(json.loads(row["payload"]))
    totals = sections["totals"][0]
    youtube_totals = sections["youtube_totals"][0]
    monthly = sorted(sections["monthly"], key=lambda r: r["month"])
    months = [r["month"] for r in monthly]
    matrix_months = {(r["source"], r["account"], r["month"]): r["amount_usd"] for r in sections["matrix_month"]}
    matrix = [{**row, "months": {m: matrix_months.get((row["source"], row["account"], m), 0) for m in months}}
              for row in sorted(sections["matrix"], key=lambda r: -r["amount_usd"])]
    def rankings(section, denominator):
        output = {k: [] for k in ("monetization", "content_origin", "title", "territory") if section == "youtube_ranking"}
        if section == "ranking":
            output = {k: [] for k in ("sources", "dsp", "monetization", "content_origin", "territory", "sale_type", "artist", "title", "label")}
        for row in sorted(sections[section], key=lambda r: (-r["amount_usd"], r["name"])):
            value = {k: row[k] for k in ("name", "units", "rows", "identity_key", "pending_amount_usd")}
            value.update(amount_usd=round_money(row["amount_usd"]), percentage=round(row["amount_usd"] / denominator * 100, 2) if denominator else 0)
            output[row["category"]].append(value)
        return output
    pairs = sorted(sections["option_pair"], key=lambda r: (r["source"] or "", r["account"] or ""))
    summary = sections["contract_summary"][0]
    pending = sorted(sections["pending"], key=lambda r: -abs(r["amount_usd"]))
    return {"report_personalization": {**policy.get("report_personalization", {}), "policy_version": policy.get("policy_version")},
        "period_basis": period_basis, "period_column": period_basis, "period_months": months, "keyword": keyword,
        "totals": totals, "monthly": monthly, "matrix": matrix,
        "rankings": rankings("ranking", totals["amount_usd"]),
        "youtube": {"totals": youtube_totals, **rankings("youtube_ranking", youtube_totals["amount_usd"])},
        "options": {"sources": sorted({r["source"] for r in pairs if r["source"]}),
                    "accounts": sorted({r["account"] for r in pairs if r["account"]}), "source_accounts": pairs,
                    **(sections["option_bounds"][0] if sections["option_bounds"] else {})},
        "catalog_refresh": {"status": "ready"},
        "explorer": {"measure": measure, "beneficiary": beneficiary, "restricted": restricted,
                     "registry_revision": context["revision"], "release_id": context["release"],
                     "computed_at": datetime.now(timezone.utc).isoformat(), **summary, "pending": pending}}


def dashboard(contracts: list[dict], policy: dict, scope: set[str] | None, *, measure="income", beneficiary=None,
              source=None, account=None, keyword="", period_basis="statement_period", period_mode="last_6_months",
              start_month=None, end_month=None, drill=None, limit=10) -> dict:
    context = get_context(contracts)
    beneficiary = authorize_beneficiary(beneficiary, context["names"], scope)
    if measure not in {"income", "contractual"} or (measure == "contractual" and not beneficiary):
        raise ValueError("Elegí un beneficiario para ver su parte según contrato.")
    base, params, _ = base_query(context, policy, beneficiary, measure=measure, restricted=scope is not None,
        period_basis=period_basis, source=source, account=account, keyword=keyword or "",
        start_month=start_month, end_month=end_month, drill=drill or {})
    rows = _job(dashboard_sql(base, period_mode, limit), params)
    return format_dashboard(rows, context=context, policy=policy, beneficiary=beneficiary, measure=measure,
                            restricted=scope is not None, period_basis=period_basis, keyword=keyword or "")



def _display_segments(segments: dict, beneficiary: str | None, restricted: bool) -> list[dict]:
    displayed_segments = []
    for segment in segments.values():
        agreement = segment["rule"]
        combined = defaultdict(lambda: {"name": "", "percent": 0.0, "origins": []})
        for share in agreement["shares"]:
            item = combined[beneficiary_key(share["artist"])]
            item["name"] = share["artist"]
            item["percent"] += share["percent"]
            item["origins"].append({"label": share["label"], "percent": share["percent"]})
        shares = list(combined.values())
        values = settle_amounts([segment["amount_usd"] * s["percent"] / 100 for s in shares], segment["amount_usd"])
        for share, value in zip(shares, values):
            share["amount_usd"] = value
        own = [s for s in shares if beneficiary_key(s["name"]) == beneficiary_key(beneficiary or "")]
        value = {"from": agreement["from"], "until": agreement["until"], "version": agreement["version"],
                 "label": agreement["label"], "months": sorted(segment["months"]),
                 "base_amount_usd": round_money(segment["amount_usd"])}
        if not restricted:
            value["shares"] = shares
        else:
            value["label"] = "Participación vigente"
            value["own_share"] = {"percent": sum(s["percent"] for s in own), "amount_usd": sum(s["amount_usd"] for s in own)}
        displayed_segments.append(value)
    return displayed_segments

def detail(contracts: list[dict], policy: dict, scope: set[str] | None, *, beneficiary=None, track_key=None,
           track_title=None, source=None, account=None, keyword="", period_basis="statement_period",
           period_mode="last_6_months", start_month=None, end_month=None, drill=None) -> dict:
    if not track_key and not track_title:
        raise ValueError("Elegí un tema del dashboard.")
    context = get_context(contracts)
    beneficiary = authorize_beneficiary(beneficiary, context["names"], scope)
    base, params, rules = base_query(context, policy, beneficiary, measure="income", restricted=scope is not None,
        period_basis=period_basis, source=source, account=account, keyword=keyword or "",
        start_month=start_month, end_month=end_month, drill=drill or {}, track_key=track_key, track_title=track_title)
    # Period bounds are selected before the topic drill, so last-six-month detail cannot jump into old history.
    sql = base + _period_sql(period_mode) + """ SELECT identity_key,isrc,title,
      FORMAT_DATE('%Y-%m',statement_month) AS statement_month,
      FORMAT_DATE('%Y-%m',transaction_month) AS transaction_month,
      source,account,dsp,territory,monetization,content_origin,contract_percent,contract_version,pending_reason,
      SUM(base_amount_usd) AS amount_usd,SUM(units) AS units,SUM(raw_rows) AS `rows`
      FROM scoped GROUP BY identity_key,isrc,title,statement_month,transaction_month,source,account,dsp,territory,
        monetization,content_origin,contract_percent,contract_version,pending_reason
      ORDER BY statement_month,source,account,dsp,territory LIMIT 50001"""
    rows = _job(sql, params)
    if len(rows) > 50000:
        raise ValueError("El detalle supera 50.000 grupos. Acotá el período o la plataforma.")
    groups = defaultdict(list)
    for row in rows:
        groups[row["identity_key"]].append(row)
    tracks = []
    for identity, income in groups.items():
        segments = defaultdict(lambda: {"amount_usd": 0.0, "units": 0.0, "months": set(), "rule": None})
        pending = defaultdict(float)
        for row in income:
            if row["pending_reason"]:
                pending[row["pending_reason"]] += row["amount_usd"]
                continue
            day = _period_start(row["statement_month"])
            agreement = next((r for r in rules.get(row["isrc"], []) if _period_start(r["from"]) <= day <= date.fromisoformat(r["end"])), None)
            if agreement is None:
                raise ValueError("El detalle no conserva la versión contractual de la consulta.")
            key = (agreement["from"], agreement["end"], agreement["version"])
            segment = segments[key]
            segment["amount_usd"] += row["amount_usd"]
            segment["units"] += row["units"] or 0
            segment["months"].add(row["statement_month"])
            segment["rule"] = agreement
        displayed_segments = _display_segments(segments, beneficiary, scope is not None)
        track = {"identity_key": identity, "isrc": income[0]["isrc"], "title": income[0]["title"],
                 "base_amount_usd": round_money(sum(r["amount_usd"] for r in income)),
                 "units": sum(r["units"] or 0 for r in income), "segments": displayed_segments,
                 "pending": [{"reason": reason, "amount_usd": round_money(amount)} for reason, amount in pending.items()]}
        if scope is None:
            track["records"] = [{k: r[k] for k in ("statement_month", "transaction_month", "source", "account", "dsp", "territory", "monetization", "content_origin", "amount_usd", "units", "rows")} for r in income]
        tracks.append(track)
    return {"tracks": tracks, "restricted": scope is not None, "beneficiary": beneficiary,
            "registry_revision": context["revision"], "period_basis": period_basis}
