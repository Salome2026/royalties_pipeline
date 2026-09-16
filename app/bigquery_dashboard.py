from __future__ import annotations

import re
import unicodedata
from datetime import date
from functools import lru_cache
from typing import Any, Iterable

from google.cloud import bigquery


DEFAULT_PROJECT = "vpo-corp-royalties"
DEFAULT_DATASET = "royalties_analytics"
DEFAULT_LOCATION = "US"
RANKING_CATEGORIES = [
    "sources",
    "dsp",
    "monetization",
    "content_origin",
    "territory",
    "sale_type",
    "artist",
    "title",
    "label",
]
YOUTUBE_RANKING_CATEGORIES = ["monetization", "content_origin", "title", "territory"]


def normalize_search_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip()


def sql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def month_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(f"{value}-01")


def month_text(value: date | None) -> str | None:
    return value.strftime("%Y-%m") if value else None


def personalization_factor_sql(policy_document: dict[str, Any]) -> str:
    personalization = policy_document.get("report_personalization") or {}
    if not bool(personalization.get("enabled", False)):
        return "1.0"
    clauses: list[str] = []
    for entry in reversed(policy_document.get("entries") or []):
        source = str(entry.get("source") or "").strip().lower().replace(" ", "_")
        account = str(entry.get("account") or "").strip().lower().replace(" ", "_")
        adjustment = float(entry.get("report_net_adjustment_pct") or 0.0)
        if not source or not account or adjustment == 0:
            continue
        factor = 1 - adjustment / 100
        clauses.append(
            f"WHEN source = '{sql_string(source)}' AND account = '{sql_string(account)}' THEN {factor:.12f}"
        )
    if not clauses:
        return "1.0"
    return "CASE " + " ".join(clauses) + " ELSE 1.0 END"


def dashboard_sql(
    *,
    project: str,
    dataset: str,
    period_basis: str,
    policy_document: dict[str, Any],
) -> str:
    if period_basis == "transaction_month":
        period_column = "transaction_month"
    elif period_basis == "statement_period":
        period_column = "statement_month"
    else:
        raise ValueError(f"Base temporal no soportada: {period_basis}")
    factor_sql = personalization_factor_sql(policy_document)
    table = f"`{project}.{dataset}.royalty_dashboard_current`"
    ranking_unions = [
        ("sources", "source"),
        ("dsp", "dsp"),
        ("monetization", "monetization"),
        ("content_origin", "content_origin"),
        ("territory", "territory"),
        ("sale_type", "sale_type"),
        ("artist", "artist"),
        ("title", "title"),
        ("label", "label"),
    ]
    ranking_sql = "\nUNION ALL\n".join(
        f"SELECT '{category}' AS category, {field} AS name, amount_usd, units, raw_rows FROM scoped"
        for category, field in ranking_unions
    )
    youtube_ranking_sql = "\nUNION ALL\n".join(
        f"SELECT '{category}' AS category, {field} AS name, amount_usd, units, raw_rows FROM youtube_scope"
        for category, field in ranking_unions
        if category in YOUTUBE_RANKING_CATEGORIES
    )
    return rf"""
WITH option_base AS (
  SELECT source, account, {period_column} AS period_month
  FROM {table}
  WHERE ARRAY_LENGTH(@artist_scope_tokens) = 0
    OR EXISTS (
      SELECT 1
      FROM UNNEST(@artist_scope_tokens) AS token
      WHERE STRPOS(
        REGEXP_REPLACE(NORMALIZE_AND_CASEFOLD(COALESCE(artist, ''), NFD), r'\pM', ''),
        token
      ) > 0
        OR STRPOS(
          REGEXP_REPLACE(REGEXP_REPLACE(NORMALIZE_AND_CASEFOLD(COALESCE(artist, ''), NFD), r'\pM', ''), r'[\s_-]+', ''),
          REGEXP_REPLACE(token, r'[\s_-]+', '')
        ) > 0
    )
),
base AS (
  SELECT
    {period_column} AS period_month,
    source,
    account,
    artist,
    title,
    dsp,
    monetization,
    content_origin,
    territory,
    sale_type,
    label,
    COALESCE(amount_usd, 0) * ({factor_sql}) AS amount_usd,
    COALESCE(units, 0) AS units,
    COALESCE(raw_rows, 0) AS raw_rows,
    REGEXP_REPLACE(NORMALIZE_AND_CASEFOLD(COALESCE(search_text, ''), NFD), r'\pM', '') AS normalized_search
  FROM {table}
  WHERE {period_column} IS NOT NULL
    AND (
      ARRAY_LENGTH(@artist_scope_tokens) = 0
      OR EXISTS (
        SELECT 1
        FROM UNNEST(@artist_scope_tokens) AS token
        WHERE STRPOS(
          REGEXP_REPLACE(NORMALIZE_AND_CASEFOLD(COALESCE(artist, ''), NFD), r'\pM', ''),
          token
        ) > 0
          OR STRPOS(
            REGEXP_REPLACE(REGEXP_REPLACE(NORMALIZE_AND_CASEFOLD(COALESCE(artist, ''), NFD), r'\pM', ''), r'[\s_-]+', ''),
            REGEXP_REPLACE(token, r'[\s_-]+', '')
          ) > 0
      )
    )
),
filtered AS (
  SELECT *
  FROM base
  WHERE (@source IS NULL OR source = @source)
    AND (@account IS NULL OR account = @account)
    AND (@start_month IS NULL OR period_month >= @start_month)
    AND (@end_month IS NULL OR period_month <= @end_month)
    AND NOT EXISTS (
      SELECT 1
      FROM UNNEST(@search_tokens) AS token
      WHERE STRPOS(normalized_search, token) = 0
        AND STRPOS(REGEXP_REPLACE(normalized_search, r'[\s_-]+', ''), REGEXP_REPLACE(token, r'[\s_-]+', '')) = 0
    )
),
available_months AS (
  SELECT DISTINCT period_month FROM filtered
),
selected_months AS (
  SELECT period_month
  FROM available_months
  QUALIFY @use_all_months OR ROW_NUMBER() OVER (ORDER BY period_month DESC) <= @month_limit
),
scoped AS (
  SELECT filtered.*
  FROM filtered
  JOIN selected_months USING (period_month)
),
totals AS (
  SELECT
    ROUND(COALESCE(SUM(amount_usd), 0), 2) AS amount_usd,
    ROUND(COALESCE(SUM(units), 0), 0) AS units,
    COALESCE(SUM(raw_rows), 0) AS row_count,
    COUNT(DISTINCT period_month) AS month_count,
    COUNT(DISTINCT source) AS source_count,
    COUNT(DISTINCT account) AS account_count,
    COUNT(DISTINCT title) AS titles,
    COUNT(DISTINCT artist) AS artists,
    MIN(period_month) AS first_month,
    MAX(period_month) AS last_month
  FROM scoped
),
monthly AS (
  SELECT
    period_month AS month,
    ROUND(SUM(amount_usd), 2) AS amount_usd,
    ROUND(SUM(units), 0) AS units,
    SUM(raw_rows) AS row_count
  FROM scoped
  GROUP BY period_month
),
matrix_totals AS (
  SELECT
    source,
    account,
    ROUND(SUM(amount_usd), 2) AS amount_usd,
    ROUND(SUM(units), 0) AS units,
    SUM(raw_rows) AS row_count,
    COUNT(DISTINCT artist) AS artists,
    COUNT(DISTINCT title) AS titles
  FROM scoped
  GROUP BY source, account
),
matrix_months AS (
  SELECT source, account, period_month AS month, ROUND(SUM(amount_usd), 2) AS amount_usd
  FROM scoped
  GROUP BY source, account, period_month
),
ranking_expanded AS (
  {ranking_sql}
),
ranking_aggregated AS (
  SELECT
    category,
    name,
    ROUND(SUM(amount_usd), 2) AS amount_usd,
    ROUND(SUM(units), 0) AS units,
    SUM(raw_rows) AS row_count
  FROM ranking_expanded
  WHERE name IS NOT NULL AND name != ''
  GROUP BY category, name
),
ranking_totals AS (
  SELECT *
  FROM ranking_aggregated
  QUALIFY ROW_NUMBER() OVER (PARTITION BY category ORDER BY amount_usd DESC, name) <= @ranking_limit
),
youtube_scope AS (
  SELECT * FROM scoped WHERE dsp = 'YouTube'
),
youtube_totals AS (
  SELECT
    ROUND(COALESCE(SUM(amount_usd), 0), 2) AS amount_usd,
    ROUND(COALESCE(SUM(units), 0), 0) AS units,
    COALESCE(SUM(raw_rows), 0) AS row_count,
    COUNT(DISTINCT title) AS titles,
    COUNT(DISTINCT artist) AS artists
  FROM youtube_scope
),
youtube_ranking_expanded AS (
  {youtube_ranking_sql}
),
youtube_ranking_aggregated AS (
  SELECT
    category,
    name,
    ROUND(SUM(amount_usd), 2) AS amount_usd,
    ROUND(SUM(units), 0) AS units,
    SUM(raw_rows) AS row_count
  FROM youtube_ranking_expanded
  WHERE name IS NOT NULL AND name != ''
  GROUP BY category, name
),
youtube_ranking_totals AS (
  SELECT *
  FROM youtube_ranking_aggregated
  QUALIFY ROW_NUMBER() OVER (PARTITION BY category ORDER BY amount_usd DESC, name) <= @ranking_limit
),
output AS (
  SELECT 'option_pair' AS section, CAST(NULL AS STRING) AS category, CAST(NULL AS STRING) AS name,
    source, account, CAST(NULL AS DATE) AS month, CAST(NULL AS FLOAT64) AS amount_usd,
    CAST(NULL AS FLOAT64) AS units, CAST(NULL AS INT64) AS row_count, CAST(NULL AS INT64) AS artists,
    CAST(NULL AS INT64) AS titles, CAST(NULL AS INT64) AS month_count, CAST(NULL AS INT64) AS source_count,
    CAST(NULL AS INT64) AS account_count, CAST(NULL AS DATE) AS first_month, CAST(NULL AS DATE) AS last_month
  FROM (SELECT DISTINCT source, account FROM option_base WHERE source IS NOT NULL AND account IS NOT NULL)
  UNION ALL
  SELECT 'option_bounds', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
    MIN(period_month), MAX(period_month) FROM option_base WHERE period_month IS NOT NULL
  UNION ALL
  SELECT 'selected_month', NULL, NULL, NULL, NULL, period_month, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
  FROM selected_months
  UNION ALL
  SELECT 'totals', NULL, NULL, NULL, NULL, NULL, amount_usd, units, row_count, artists, titles, month_count,
    source_count, account_count, first_month, last_month FROM totals
  UNION ALL
  SELECT 'monthly', NULL, NULL, NULL, NULL, month, amount_usd, units, row_count, NULL, NULL, NULL, NULL, NULL, NULL, NULL
  FROM monthly
  UNION ALL
  SELECT 'matrix', NULL, NULL, source, account, NULL, amount_usd, units, row_count, artists, titles, NULL, NULL, NULL, NULL, NULL
  FROM matrix_totals
  UNION ALL
  SELECT 'matrix_month', NULL, NULL, source, account, month, amount_usd, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
  FROM matrix_months
  UNION ALL
  SELECT 'ranking', category, name, NULL, NULL, NULL, amount_usd, units, row_count, NULL, NULL, NULL, NULL, NULL, NULL, NULL
  FROM ranking_totals
  UNION ALL
  SELECT 'youtube_totals', NULL, NULL, NULL, NULL, NULL, amount_usd, units, row_count, artists, titles, NULL, NULL, NULL, NULL, NULL
  FROM youtube_totals
  UNION ALL
  SELECT 'youtube_ranking', category, name, NULL, NULL, NULL, amount_usd, units, row_count, NULL, NULL, NULL, NULL, NULL, NULL, NULL
  FROM youtube_ranking_totals
)
SELECT * FROM output
ORDER BY section, category, amount_usd DESC, month, source, account, name
""".strip()


@lru_cache(maxsize=4)
def dashboard_client(project: str, location: str) -> bigquery.Client:
    return bigquery.Client(project=project, location=location)


def query_rows(
    *,
    sql: str,
    project: str,
    location: str,
    source: str | None,
    account: str | None,
    start_month: str | None,
    end_month: str | None,
    search_tokens: list[str],
    artist_scope_tokens: list[str],
    use_all_months: bool,
    month_limit: int,
    ranking_limit: int,
    maximum_bytes_billed: int | None,
    client: bigquery.Client | None = None,
) -> list[dict[str, Any]]:
    query_client = client or dashboard_client(project, location)
    config = bigquery.QueryJobConfig(
        maximum_bytes_billed=maximum_bytes_billed,
        query_parameters=[
            bigquery.ScalarQueryParameter("source", "STRING", source),
            bigquery.ScalarQueryParameter("account", "STRING", account),
            bigquery.ScalarQueryParameter("start_month", "DATE", month_date(start_month)),
            bigquery.ScalarQueryParameter("end_month", "DATE", month_date(end_month)),
            bigquery.ArrayQueryParameter("search_tokens", "STRING", search_tokens),
            bigquery.ArrayQueryParameter("artist_scope_tokens", "STRING", artist_scope_tokens),
            bigquery.ScalarQueryParameter("use_all_months", "BOOL", use_all_months),
            bigquery.ScalarQueryParameter("month_limit", "INT64", month_limit),
            bigquery.ScalarQueryParameter("ranking_limit", "INT64", ranking_limit),
        ]
    )
    return [dict(row.items()) for row in query_client.query(sql, job_config=config, location=location).result()]


def rank_rows(rows: Iterable[dict[str, Any]], denominator: float) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: (-float(item.get("amount_usd") or 0.0), str(item.get("name") or ""))):
        amount = float(row.get("amount_usd") or 0.0)
        output.append(
            {
                "name": row.get("name") or "-",
                "amount_usd": amount,
                "units": float(row.get("units") or 0.0),
                "rows": int(row.get("row_count") or 0),
                "percentage": round(amount / denominator * 100, 2) if denominator else 0.0,
            }
        )
    return output


def format_dashboard_response(
    *,
    rows: list[dict[str, Any]],
    policy_document: dict[str, Any],
    period_basis: str,
    keyword: str,
) -> dict[str, Any]:
    personalization = policy_document.get("report_personalization") or {}
    personalization_state = {
        **personalization,
        "policy_version": policy_document.get("policy_version"),
        "updated_at": policy_document.get("updated_at"),
    }
    by_section: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_section.setdefault(str(row["section"]), []).append(row)

    option_pairs = sorted(
        ({"source": str(row["source"]), "account": str(row["account"])} for row in by_section.get("option_pair", [])),
        key=lambda item: (item["source"], item["account"]),
    )
    bounds = (by_section.get("option_bounds") or [{}])[0]
    options = {
        "sources": sorted({item["source"] for item in option_pairs}),
        "accounts": sorted({item["account"] for item in option_pairs}),
        "source_accounts": option_pairs,
        "first_month": month_text(bounds.get("first_month")),
        "last_month": month_text(bounds.get("last_month")),
    }
    months = sorted(month_text(row.get("month")) for row in by_section.get("selected_month", []) if row.get("month"))
    period_column = "transaction_month" if period_basis == "transaction_month" else "statement_period"
    empty_totals = {
        "amount_usd": 0.0,
        "units": 0.0,
        "rows": 0,
        "months": 0,
        "sources": 0,
        "accounts": 0,
        "titles": 0,
        "artists": 0,
        "first_month": None,
        "last_month": None,
    }
    if not months:
        return {
            "report_personalization": personalization_state,
            "period_basis": period_basis,
            "period_column": period_column,
            "period_months": [],
            "keyword": keyword,
            "totals": empty_totals,
            "monthly": [],
            "matrix": [],
            "rankings": {category: [] for category in RANKING_CATEGORIES},
            "youtube": {
                "totals": empty_totals,
                **{category: [] for category in YOUTUBE_RANKING_CATEGORIES},
            },
            "options": options,
        }

    total = (by_section.get("totals") or [{}])[0]
    totals = {
        "amount_usd": float(total.get("amount_usd") or 0.0),
        "units": float(total.get("units") or 0.0),
        "rows": int(total.get("row_count") or 0),
        "months": int(total.get("month_count") or 0),
        "sources": int(total.get("source_count") or 0),
        "accounts": int(total.get("account_count") or 0),
        "titles": int(total.get("titles") or 0),
        "artists": int(total.get("artists") or 0),
        "first_month": month_text(total.get("first_month")),
        "last_month": month_text(total.get("last_month")),
    }
    monthly = [
        {
            "month": month_text(row.get("month")),
            "amount_usd": float(row.get("amount_usd") or 0.0),
            "units": float(row.get("units") or 0.0),
            "rows": int(row.get("row_count") or 0),
        }
        for row in sorted(by_section.get("monthly", []), key=lambda item: item["month"])
    ]
    matrix_month_values = {
        (str(row["source"]), str(row["account"]), month_text(row["month"])): float(row.get("amount_usd") or 0.0)
        for row in by_section.get("matrix_month", [])
    }
    matrix = []
    for row in sorted(
        by_section.get("matrix", []),
        key=lambda item: (-float(item.get("amount_usd") or 0.0), str(item.get("source") or ""), str(item.get("account") or "")),
    ):
        source = str(row["source"])
        account = str(row["account"])
        matrix.append(
            {
                "source": source,
                "account": account,
                "months": {month: matrix_month_values.get((source, account, month), 0.0) for month in months},
                "amount_usd": float(row.get("amount_usd") or 0.0),
                "units": float(row.get("units") or 0.0),
                "rows": int(row.get("row_count") or 0),
                "artists": int(row.get("artists") or 0),
                "titles": int(row.get("titles") or 0),
            }
        )
    ranking_source = by_section.get("ranking", [])
    rankings = {
        category: rank_rows((row for row in ranking_source if row.get("category") == category), totals["amount_usd"])
        for category in RANKING_CATEGORIES
    }
    youtube_total = (by_section.get("youtube_totals") or [{}])[0]
    youtube_totals = {
        "amount_usd": float(youtube_total.get("amount_usd") or 0.0),
        "units": float(youtube_total.get("units") or 0.0),
        "rows": int(youtube_total.get("row_count") or 0),
        "titles": int(youtube_total.get("titles") or 0),
        "artists": int(youtube_total.get("artists") or 0),
    }
    youtube_ranking_source = by_section.get("youtube_ranking", [])
    youtube_rankings = {
        category: rank_rows(
            (row for row in youtube_ranking_source if row.get("category") == category),
            youtube_totals["amount_usd"],
        )
        for category in YOUTUBE_RANKING_CATEGORIES
    }
    return {
        "report_personalization": personalization_state,
        "period_basis": period_basis,
        "period_column": period_column,
        "period_months": months,
        "keyword": keyword,
        "totals": totals,
        "monthly": monthly,
        "matrix": matrix,
        "rankings": rankings,
        "youtube": {"totals": youtube_totals, **youtube_rankings},
        "options": options,
    }


def royalties_dashboard_bigquery(
    *,
    policy_document: dict[str, Any],
    source: str | None = None,
    account: str | None = None,
    keyword: str | None = None,
    artist_keyword: str | None = None,
    artist_scope: Iterable[str] | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
    period_basis: str = "statement_period",
    period_mode: str = "last_6_months",
    limit: int = 10,
    project: str = DEFAULT_PROJECT,
    dataset: str = DEFAULT_DATASET,
    location: str = DEFAULT_LOCATION,
    maximum_bytes_billed: int | None = 2_500_000_000,
    client: bigquery.Client | None = None,
) -> dict[str, Any]:
    safe_limit = max(3, min(int(limit or 10), 50))
    search = normalize_search_text(keyword or artist_keyword or "")
    search_tokens = [part for part in search.split() if part]
    artist_scope_tokens = sorted({
        normalized
        for value in (artist_scope or [])
        for normalized in [normalize_search_text(value)]
        if normalized
    })
    use_all_months = bool(start_month or end_month or period_mode in {"single_month", "closed_range", "all"})
    month_limit = 12 if period_mode == "last_12_months" else 6
    sql = dashboard_sql(
        project=project,
        dataset=dataset,
        period_basis=period_basis,
        policy_document=policy_document,
    )
    rows = query_rows(
        sql=sql,
        project=project,
        location=location,
        source=source.strip() if source else None,
        account=account.strip() if account else None,
        start_month=start_month,
        end_month=end_month,
        search_tokens=search_tokens,
        artist_scope_tokens=artist_scope_tokens,
        use_all_months=use_all_months,
        month_limit=month_limit,
        ranking_limit=safe_limit,
        maximum_bytes_billed=maximum_bytes_billed,
        client=client,
    )
    return format_dashboard_response(
        rows=rows,
        policy_document=policy_document,
        period_basis=period_basis,
        keyword=search,
    )
