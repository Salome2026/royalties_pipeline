"""Additional contract income only; existing royalty readers are not changed."""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
import json
from typing import Any

from google.cloud import bigquery

from app.bigquery_dashboard import DEFAULT_DATASET, DEFAULT_LOCATION, DEFAULT_PROJECT, dashboard_client
from app.master_contract_associations import association_key, candidates
from app.operational_db import is_postgres_connection


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
      SUM(amount_usd) AS amount_usd
    FROM `{prefix}.royalty_statement_fact`
    WHERE release_id = @release_id AND COALESCE(asset_isrc, '') = ''
      AND statement_month IS NOT NULL
    GROUP BY source, account, source_sheet, revenue_basis, artist, title, asset_isrc,
      product_upc, video_id, track_id, catalog_number, statement_period
    """
    rows = [dict(row) for row in client.query(sql, job_config=config, location=DEFAULT_LOCATION).result(timeout=60)]
    sql = f"""
    WITH facts AS (
      SELECT source, account, asset_isrc, product_upc, video_id, track_id, catalog_number, title, artist
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
    GROUP BY c.kind, c.value, c.source, c.account
    """
    evidence = [dict(row) for row in client.query(sql, job_config=config, location=DEFAULT_LOCATION).result(timeout=60)]
    return rows, evidence


def read_choices(conn: Any) -> dict[str, list[dict]]:
    if not is_postgres_connection(conn):
        raise ValueError("Los ingresos asociados usan exclusivamente Cloud SQL Postgres.")
    rows = conn.execute("SELECT isrc, payload_json FROM master_contract_splits").fetchall()
    return {row["isrc"]: json.loads(row["payload_json"]).get("code_association_overrides") or [] for row in rows}


def consolidate_associated_income(
    rows: list[dict], evidence: list[dict], aliases: dict[str, str],
    choices: dict[str, list[dict]], claims: dict[str, str], cutoff: str,
) -> dict[str, dict]:
    scopes: dict[tuple, list[dict]] = defaultdict(list)
    for item in evidence:
        scope = (item["kind"], item["code"])
        if item["kind"] == "TRACK":
            scope += (item["source"], item["account"])
        scopes[scope].append(item)
    target_evidence: dict[str, dict[str, dict]] = defaultdict(dict)
    for scope, items in scopes.items():
        roots = {value for item in items for value in item.get("isrcs") or []}
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
    for root, items in target_evidence.items():
        for item in candidates(root, list(items.values()), aliases, choices.get(root, []), claims):
            if item["included"]:
                included[item["key"]].add(root)
            if item["status"] == "excluded":
                excluded[item["key"]].add(root)
    months: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    breakdown: dict[str, dict[tuple, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        # A native ADA product is never absorbed into a recording, even through another ID.
        if row.get("asset_isrc") or (row["source"] == "ada" and row.get("catalog_number")):
            continue
        month = row.get("statement_period")
        if not month:
            continue
        keys = [association_key(kind, row[field], row["source"], row["account"])
                for kind, field in [("UPC", "product_upc"), ("VIDEO", "video_id"), ("TRACK", "track_id")]
                if row.get(field)]
        roots = set().union(*(included[key] for key in keys))
        vetoed = set().union(*(excluded[key] for key in keys))
        roots -= vetoed
        # Conflicting identifiers do not authorize allocating the same economic row twice.
        if len(roots) != 1:
            continue
        root = next(iter(roots))
        amount = float(row.get("amount_usd") or 0)
        months[root][month] += amount
        if month <= cutoff:
            matched = tuple(sorted(key for key in keys if root in included[key]))
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
