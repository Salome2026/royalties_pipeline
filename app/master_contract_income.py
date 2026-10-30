"""Additional contract income only; existing royalty readers are not changed."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from functools import lru_cache
import json
from typing import Any

from google.cloud import bigquery

from app.bigquery_dashboard import DEFAULT_DATASET, DEFAULT_LOCATION, DEFAULT_PROJECT, dashboard_client
from app.master_contract_associations import association_key, candidates
from app.operational_db import is_postgres_connection


STATEMENT_WINDOW = "/* contract_statement_window */"


def _billing_limit(exc):
    return (any(item.get("reason") == "bytesBilledLimitExceeded" for item in getattr(exc, "errors", []) or [])
            or "Query exceeded limit for bytes billed:" in str(exc))


def _statement_rows(client, config, sql, *, alias="", include_undated=False):
    """Fall back to disjoint partitions without increasing the query budget."""
    from google.api_core.exceptions import GoogleAPICallError

    def read(predicate="", start=None, end=None):
        scoped = bigquery.QueryJobConfig.from_api_repr(config.to_api_repr())
        if start is not None:
            scoped.query_parameters = [*scoped.query_parameters,
                bigquery.ScalarQueryParameter("window_start", "DATE", start),
                bigquery.ScalarQueryParameter("window_end", "DATE", end)]
        return [dict(row) for row in client.query(sql.replace(STATEMENT_WINDOW, predicate),
            job_config=scoped, location=DEFAULT_LOCATION).result(timeout=60)]

    try:
        return read()
    except GoogleAPICallError as exc:
        if not _billing_limit(exc):
            raise
    prefix = f"{DEFAULT_PROJECT}.{DEFAULT_DATASET}"
    months = [row["month"] for row in client.query(f"""
        SELECT DISTINCT DATE_TRUNC(statement_month, MONTH) AS month
        FROM `{prefix}.royalty_statement_fact` WHERE release_id=@release_id
          AND statement_month IS NOT NULL ORDER BY month
        """, job_config=config, location=DEFAULT_LOCATION).result(timeout=60)]
    column = (alias + "." if alias else "") + "statement_month"
    predicate = f"AND {column} >= @window_start AND {column} < @window_end"
    rows = []
    for year in sorted({month.year for month in months}):
        try:
            rows.extend(read(predicate, date(year, 1, 1), date(year + 1, 1, 1)))
        except GoogleAPICallError as exc:
            if not _billing_limit(exc):
                raise
            for month in (value for value in months if value.year == year):
                end = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
                rows.extend(read(predicate, month, end))
    if include_undated:
        rows.extend(read(f"AND {column} IS NULL"))
    return rows


def _merge_statement_evidence(rows):
    merged = {}
    for row in rows:
        key = tuple(row[name] for name in ("kind", "code", "source", "account"))
        item = merged.setdefault(key, {**row, "isrcs": set(), "titles": set(), "artists": set(),
                                       "native_ada_product": False})
        for name in ("isrcs", "titles", "artists"):
            item[name].update(row.get(name) or [])
        item["native_ada_product"] |= bool(row.get("native_ada_product"))
    return [{**item, **{name: sorted(item[name]) for name in ("isrcs", "titles", "artists")}}
            for _, item in sorted(merged.items())]


@lru_cache(maxsize=2)
def published_unassigned_income(release_id: str) -> tuple[list[dict], list[dict]]:
    client = dashboard_client(DEFAULT_PROJECT, DEFAULT_LOCATION)
    prefix = f"{DEFAULT_PROJECT}.{DEFAULT_DATASET}"
    config = bigquery.QueryJobConfig(maximum_bytes_billed=5_000_000_000, query_parameters=[
        bigquery.ScalarQueryParameter("release_id", "STRING", release_id),
    ])
    published = next(iter(client.query(f"SELECT release_id FROM `{prefix}.current_release`",
        job_config=config, location=DEFAULT_LOCATION).result(timeout=30)), None)
    if published is None or published["release_id"] != release_id:
        raise RuntimeError("El catálogo y BigQuery todavía no tienen la misma versión publicada.")
    # Keep identifiers together: expanding them before summing would multiply revenue.
    sql = f"""
    SELECT source, account, source_sheet, revenue_basis, artist, title, asset_isrc,
      product_upc, video_id, track_id, catalog_number,
      FORMAT_DATE('%Y-%m', statement_month) AS statement_period,
      SUM(amount_usd) AS amount_usd, COUNT(*) AS raw_rows
    FROM `{prefix}.royalty_statement_fact`
    WHERE release_id = @release_id AND COALESCE(asset_isrc, '') = ''
      AND statement_month IS NOT NULL
      {STATEMENT_WINDOW}
    GROUP BY source, account, source_sheet, revenue_basis, artist, title, asset_isrc,
      product_upc, video_id, track_id, catalog_number, statement_period
    """
    rows = _statement_rows(client, config, sql)
    sql = f"""
    WITH facts AS (
      SELECT source, account, asset_isrc, product_upc, video_id, track_id, catalog_number, title, artist, statement_month
      FROM `{prefix}.royalty_statement_fact` WHERE release_id = @release_id
    ), codes AS (
      SELECT f.*, c.kind, c.value,
        IF(c.kind = 'TRACK', source, '') AS scope_source,
        IF(c.kind = 'TRACK', account, '') AS scope_account
      FROM facts f, UNNEST([
        STRUCT('UPC' AS kind, product_upc AS value),
        STRUCT('VIDEO' AS kind, video_id AS value),
        STRUCT('TRACK' AS kind, track_id AS value)
      ]) c WHERE c.value IS NOT NULL AND c.value != ''
    ), seeds AS (
      SELECT DISTINCT kind, value, scope_source, scope_account
      FROM codes WHERE COALESCE(asset_isrc, '') = ''
    )
    SELECT c.kind, c.value AS code, c.source, c.account,
      ARRAY_AGG(DISTINCT NULLIF(c.asset_isrc, '') IGNORE NULLS) AS isrcs,
      ARRAY_AGG(DISTINCT NULLIF(c.title, '') IGNORE NULLS) AS titles,
      ARRAY_AGG(DISTINCT NULLIF(c.artist, '') IGNORE NULLS) AS artists,
      LOGICAL_OR(c.source = 'ada' AND COALESCE(c.asset_isrc, '') = ''
        AND COALESCE(c.catalog_number, '') != '') AS native_ada_product
    FROM codes c JOIN seeds s USING (kind, value, scope_source, scope_account)
    WHERE TRUE {STATEMENT_WINDOW}
    GROUP BY c.kind, c.value, c.source, c.account
    """
    # Seeds intentionally remain global: a code without ISRC in one month can
    # identify an ISRC-bearing sale in a different month (including undated rows).
    evidence = _merge_statement_evidence(_statement_rows(client, config, sql, alias="c", include_undated=True))
    return rows, evidence


def read_choices(conn: Any) -> dict[str, list[dict]]:
    from app.royalty_scope import is_wml
    if is_wml():return {}
    if not is_postgres_connection(conn):
        raise ValueError("Los ingresos asociados usan exclusivamente Cloud SQL Postgres.")
    rows = conn.execute("SELECT isrc, payload_json FROM master_contract_splits").fetchall()
    return {row["isrc"]: json.loads(row["payload_json"]).get("code_association_overrides") or [] for row in rows}


def income_association_index(
    evidence: list[dict], aliases: dict[str, str], choices: dict[str, list[dict]], claims: dict[str, str],
    *, with_candidates: bool = False,
) -> dict[str, Any]:
    scopes: dict[tuple, list[dict]] = defaultdict(list)
    manual_roots: dict[tuple, set[str]] = defaultdict(set)
    for root, decisions in choices.items():
        for decision in decisions:
            if decision.get("manual"):
                kind, code, source, account = json.loads(decision["key"])
                manual_roots[(kind, code, source, account) if kind == "TRACK" else (kind, code)].add(root)
    for item in evidence:
        scope = (item["kind"], item["code"])
        if item["kind"] == "TRACK":
            scope += (item["source"], item["account"])
        scopes[scope].append(item)
    target_evidence: dict[str, dict[str, dict]] = defaultdict(dict)
    for scope, items in scopes.items():
        roots = {value for item in items for value in item.get("isrcs") or []}
        roots.update(manual_roots.get(scope, ()))
        roots.update(value for item in items for value in item.get("inferred_isrcs") or [])
        canonical = aliases.get(f"{scope[0]}:{scope[1]}")
        if canonical and canonical.startswith("ISRC:"):
            roots.add(canonical[5:])
        for item in items:
            owner = claims.get(association_key(item["kind"], item["code"], item["source"], item["account"]))
            if owner:
                roots.add(owner)
        for root in roots:
            for item in items:
                key = association_key(item["kind"], item["code"], item["source"], item["account"])
                target_evidence[root][key] = item
    included: dict[str, set[str]] = defaultdict(set)
    excluded: dict[str, set[str]] = defaultdict(set)
    proposed: dict[str, dict] = defaultdict(dict)
    for root, items in target_evidence.items():
        for item in candidates(root, list(items.values()), aliases, choices.get(root, []), claims):
            if with_candidates:
                proposed[item["key"]][root] = {"status": item["status"], "reason": item["reason"],
                    "included": item["included"], "selectable": item["selectable"]}
            if item["included"]:
                included[item["key"]].add(root)
            if item["status"] == "excluded":
                excluded[item["key"]].add(root)
    result = {"included": {key: sorted(roots) for key, roots in included.items()},
              "excluded": {key: sorted(roots) for key, roots in excluded.items()}}
    if with_candidates:
        result["proposed"] = dict(proposed)
    return result


def associated_income_isrc(row: dict, index: dict) -> str | None:
    if row.get("asset_isrc") or (row["source"] == "ada" and row.get("catalog_number")):
        return None
    keys = [association_key(kind, row[field], row["source"], row["account"])
            for kind, field in [("UPC", "product_upc"), ("VIDEO", "video_id"), ("TRACK", "track_id")]
            if row.get(field)]
    roots = {root for key in keys for root in index["included"].get(key, [])}
    roots -= {root for key in keys for root in index["excluded"].get(key, [])}
    return next(iter(roots)) if len(roots) == 1 else None


def consolidate_associated_income(
    rows: list[dict], evidence: list[dict], aliases: dict[str, str],
    choices: dict[str, list[dict]], claims: dict[str, str], cutoff: str,
) -> dict[str, dict]:
    index = income_association_index(evidence, aliases, choices, claims)
    months: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    breakdown: dict[str, dict[tuple, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        root = associated_income_isrc(row, index)
        if root is None:
            continue
        month = row.get("statement_period")
        if not month:
            continue
        keys = [association_key(kind, row[field], row["source"], row["account"])
                for kind, field in [("UPC", "product_upc"), ("VIDEO", "video_id"), ("TRACK", "track_id")]
                if row.get(field)]
        amount = float(row.get("amount_usd") or 0)
        months[root][month] += amount
        if month <= cutoff:
            matched = tuple(sorted(key for key in keys if root in index["included"].get(key, [])))
            breakdown[root][matched] += amount
    return {root: {
        "amount_usd": sum(amount for month, amount in values.items() if month <= cutoff),
        "statement_income": [{"statement_month": month, "amount_usd": amount} for month, amount in sorted(values.items())],
        "groups": [{"codes": [dict(zip(("kind", "code", "source", "account"), json.loads(key))) for key in keys],
                    "amount_usd": amount} for keys, amount in sorted(breakdown[root].items(), key=lambda item: -item[1])],
    } for root, values in months.items()}


def combined_income(base: float, extra: dict | None, primary_months: list[dict] | None = None) -> dict:
    extra = extra or {}
    months: dict[str, float] = defaultdict(float)
    for row in [*(primary_months or []), *extra.get("statement_income", [])]:
        months[row["statement_month"]] += float(row.get("amount_usd") or 0)
    associated = float(extra.get("amount_usd") or 0)
    return {"isrc_amount_usd": base, "associated_amount_usd": associated, "amount_usd": base + associated,
            "associated_income_groups": extra.get("groups", []),
            "statement_income": [{"statement_month": month, "amount_usd": value} for month, value in sorted(months.items())]}
