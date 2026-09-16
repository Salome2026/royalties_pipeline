from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl


LOCAL_ROOT = Path(__file__).resolve().parents[1]
if str(LOCAL_ROOT) not in sys.path:
    sys.path.insert(0, str(LOCAL_ROOT))

from scripts.load_bigquery_release import (
    ENV_PATH,
    ROOT,
    SOURCE_FILES,
    bq_load,
    bq_query_json,
    build_detail,
    ensure_source_file,
    executable,
    load_local_env,
    load_manifest,
    run,
    sql_string,
    storage_client,
    upload_immutable,
)


RESULT_FIELDS = [
    "run_id",
    "release_id",
    "period_basis",
    "source",
    "account",
    "period_month",
    "parquet_rows",
    "bigquery_rows",
    "parquet_amount_usd",
    "bigquery_amount_usd",
    "amount_difference_usd",
    "parquet_units",
    "bigquery_units",
    "units_difference",
    "parquet_isrcs",
    "bigquery_isrcs",
    "parquet_missing_isrc_rows",
    "bigquery_missing_isrc_rows",
    "parquet_multi_isrc_title_groups",
    "bigquery_multi_isrc_title_groups",
    "status",
    "mismatch_reasons",
]

INTEGER_METRICS = ["rows", "isrcs", "missing_isrc_rows", "multi_isrc_title_groups"]
FLOAT_METRICS = ["amount_usd", "units"]


def aggregate_local(detail_path: Path, period_column: str, period_basis: str) -> list[dict[str, Any]]:
    keys = ["source", "account", "period_month"]
    base = (
        pl.scan_parquet(detail_path)
        .select(
            pl.col(period_column).alias("period_month"),
            pl.col("source").fill_null("").alias("source"),
            pl.col("account").fill_null("").alias("account"),
            pl.col("title").fill_null("").alias("title"),
            pl.col("asset_isrc").fill_null("").alias("asset_isrc"),
            pl.col("amount_usd").fill_null(0.0).alias("amount_usd"),
            pl.col("units").fill_null(0.0).alias("units"),
        )
        .filter(pl.col("period_month").is_not_null())
    )
    totals = base.group_by(keys).agg(
        pl.len().cast(pl.Int64).alias("rows"),
        pl.col("amount_usd").sum().alias("amount_usd"),
        pl.col("units").sum().alias("units"),
        pl.col("asset_isrc").filter(pl.col("asset_isrc") != "").n_unique().cast(pl.Int64).alias("isrcs"),
        (pl.col("asset_isrc") == "").sum().cast(pl.Int64).alias("missing_isrc_rows"),
    )
    collisions = (
        base.filter((pl.col("title") != "") & (pl.col("asset_isrc") != ""))
        .group_by([*keys, "title"])
        .agg(pl.col("asset_isrc").n_unique().alias("title_isrcs"))
        .filter(pl.col("title_isrcs") > 1)
        .group_by(keys)
        .agg(pl.len().cast(pl.Int64).alias("multi_isrc_title_groups"))
    )
    rows = (
        totals.join(collisions, on=keys, how="left")
        .with_columns(
            pl.lit(period_basis).alias("period_basis"),
            pl.col("multi_isrc_title_groups").fill_null(0),
        )
        .collect()
        .to_dicts()
    )
    return rows


def aggregate_bigquery_sql(
    *,
    project: str,
    dataset: str,
    release_id: str,
    period_column: str,
    period_basis: str,
) -> str:
    fact_table = {
        "statement_month": "royalty_statement_fact",
        "transaction_month": "royalty_transaction_fact",
    }.get(period_column)
    if not fact_table:
        raise ValueError(f"Periodo no soportado: {period_column}")
    release = sql_string(release_id)
    basis = sql_string(period_basis)
    return f"""
WITH base AS (
  SELECT
    {period_column} AS period_month,
    COALESCE(source, '') AS source,
    COALESCE(account, '') AS account,
    COALESCE(title, '') AS title,
    COALESCE(asset_isrc, '') AS asset_isrc,
    COALESCE(amount_usd, 0) AS amount_usd,
    COALESCE(units, 0) AS units
  FROM `{project}.{dataset}.{fact_table}`
  WHERE release_id = '{release}' AND {period_column} IS NOT NULL
),
totals AS (
  SELECT
    source,
    account,
    period_month,
    COUNT(*) AS `rows`,
    SUM(amount_usd) AS amount_usd,
    SUM(units) AS units,
    COUNT(DISTINCT NULLIF(asset_isrc, '')) AS isrcs,
    COUNTIF(asset_isrc = '') AS missing_isrc_rows
  FROM base
  GROUP BY source, account, period_month
),
title_isrcs AS (
  SELECT source, account, period_month, title
  FROM base
  WHERE title != '' AND asset_isrc != ''
  GROUP BY source, account, period_month, title
  HAVING COUNT(DISTINCT asset_isrc) > 1
),
collisions AS (
  SELECT source, account, period_month, COUNT(*) AS multi_isrc_title_groups
  FROM title_isrcs
  GROUP BY source, account, period_month
)
SELECT
  '{basis}' AS period_basis,
  totals.source,
  totals.account,
  CAST(totals.period_month AS STRING) AS period_month,
  totals.`rows` AS `rows`,
  totals.amount_usd,
  totals.units,
  totals.isrcs,
  totals.missing_isrc_rows,
  COALESCE(collisions.multi_isrc_title_groups, 0) AS multi_isrc_title_groups
FROM totals
LEFT JOIN collisions USING (source, account, period_month)
ORDER BY source, account, period_month
""".strip()


def aggregate_bigquery(
    *,
    bq: str,
    project: str,
    dataset: str,
    location: str,
    release_id: str,
    period_column: str,
    period_basis: str,
) -> list[dict[str, Any]]:
    sql = aggregate_bigquery_sql(
        project=project,
        dataset=dataset,
        release_id=release_id,
        period_column=period_column,
        period_basis=period_basis,
    )
    rows = bq_query_json(bq, project, location, sql)
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "period_basis": str(row["period_basis"]),
                "source": str(row.get("source") or ""),
                "account": str(row.get("account") or ""),
                "period_month": date.fromisoformat(str(row["period_month"])),
                **{name: int(row[name]) for name in INTEGER_METRICS},
                **{name: float(row[name]) for name in FLOAT_METRICS},
            }
        )
    return normalized


def row_key(row: dict[str, Any]) -> tuple[str, str, str, date]:
    return (
        str(row["period_basis"]),
        str(row.get("source") or ""),
        str(row.get("account") or ""),
        row["period_month"],
    )


def reconcile_rows(
    *,
    local_rows: list[dict[str, Any]],
    bigquery_rows: list[dict[str, Any]],
    release_id: str,
    run_id: str,
    amount_tolerance: float,
    units_tolerance: float,
) -> list[dict[str, Any]]:
    local = {row_key(row): row for row in local_rows}
    remote = {row_key(row): row for row in bigquery_rows}
    results: list[dict[str, Any]] = []
    for key in sorted(set(local) | set(remote), key=lambda value: (value[0], value[1], value[2], value[3])):
        parquet = local.get(key, {})
        bigquery = remote.get(key, {})
        reasons: list[str] = []
        for metric in INTEGER_METRICS:
            if int(parquet.get(metric, 0)) != int(bigquery.get(metric, 0)):
                reasons.append(metric)
        parquet_amount = float(parquet.get("amount_usd", 0.0))
        bigquery_amount = float(bigquery.get("amount_usd", 0.0))
        amount_difference = bigquery_amount - parquet_amount
        if abs(amount_difference) > amount_tolerance:
            reasons.append("amount_usd")
        parquet_units = float(parquet.get("units", 0.0))
        bigquery_units = float(bigquery.get("units", 0.0))
        units_difference = bigquery_units - parquet_units
        if abs(units_difference) > units_tolerance:
            reasons.append("units")
        results.append(
            {
                "run_id": run_id,
                "release_id": release_id,
                "period_basis": key[0],
                "source": key[1],
                "account": key[2],
                "period_month": key[3],
                "parquet_rows": int(parquet.get("rows", 0)),
                "bigquery_rows": int(bigquery.get("rows", 0)),
                "parquet_amount_usd": parquet_amount,
                "bigquery_amount_usd": bigquery_amount,
                "amount_difference_usd": amount_difference,
                "parquet_units": parquet_units,
                "bigquery_units": bigquery_units,
                "units_difference": units_difference,
                "parquet_isrcs": int(parquet.get("isrcs", 0)),
                "bigquery_isrcs": int(bigquery.get("isrcs", 0)),
                "parquet_missing_isrc_rows": int(parquet.get("missing_isrc_rows", 0)),
                "bigquery_missing_isrc_rows": int(bigquery.get("missing_isrc_rows", 0)),
                "parquet_multi_isrc_title_groups": int(parquet.get("multi_isrc_title_groups", 0)),
                "bigquery_multi_isrc_title_groups": int(bigquery.get("multi_isrc_title_groups", 0)),
                "status": "mismatch" if reasons else "match",
                "mismatch_reasons": ",".join(reasons),
            }
        )
    return results


def result_frame(results: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(results).select(RESULT_FIELDS)


def persist_results(
    *,
    bq: str,
    project: str,
    dataset: str,
    location: str,
    release_id: str,
    run_id: str,
    started_at: datetime,
    completed_at: datetime,
    amount_tolerance: float,
    units_tolerance: float,
    mismatch_count: int,
    report_uri: str,
    results_uri: str,
) -> None:
    suffix = re.sub(r"[^a-zA-Z0-9]", "", run_id)[-24:].lower()
    stage = f"_stage_reconciliation_{suffix}"
    bq_load(
        bq=bq,
        project=project,
        dataset=dataset,
        location=location,
        table=stage,
        uri=results_uri,
    )
    target_status = "ready" if mismatch_count == 0 else "reconciliation_failed"
    notes = "BQ-003 reconciliation passed" if mismatch_count == 0 else "BQ-003 reconciliation found mismatches"
    columns = ", ".join(f"`{name}`" for name in RESULT_FIELDS)
    sql = f"""
BEGIN TRANSACTION;
DELETE FROM `{project}.{dataset}.analytics_reconciliation_results` WHERE run_id = '{sql_string(run_id)}';
INSERT INTO `{project}.{dataset}.analytics_reconciliation_results` ({columns})
SELECT {columns} FROM `{project}.{dataset}.{stage}`;
DELETE FROM `{project}.{dataset}.analytics_reconciliation_runs` WHERE run_id = '{sql_string(run_id)}';
INSERT INTO `{project}.{dataset}.analytics_reconciliation_runs` (
  run_id, release_id, started_at, completed_at, status,
  amount_tolerance_usd, units_tolerance, group_count, mismatch_count,
  report_uri, results_uri, notes
) VALUES (
  '{sql_string(run_id)}',
  '{sql_string(release_id)}',
  TIMESTAMP('{started_at.isoformat()}'),
  TIMESTAMP('{completed_at.isoformat()}'),
  '{target_status}',
  {amount_tolerance},
  {units_tolerance},
  (SELECT COUNT(*) FROM `{project}.{dataset}.{stage}`),
  {mismatch_count},
  '{sql_string(report_uri)}',
  '{sql_string(results_uri)}',
  '{notes}'
);
UPDATE `{project}.{dataset}.analytics_releases`
SET status = '{target_status}', notes = '{notes}'
WHERE release_id = '{sql_string(release_id)}';
COMMIT TRANSACTION;
""".strip()
    try:
        run(
            [
                bq,
                f"--project_id={project}",
                "query",
                f"--location={location}",
                "--use_legacy_sql=false",
            ],
            input_text=sql,
        )
    finally:
        run([bq, f"--project_id={project}", "rm", "-f", "-t", f"{project}:{dataset}.{stage}"])


def json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"No se puede serializar {type(value).__name__}")


def main() -> None:
    load_local_env(ENV_PATH)
    parser = argparse.ArgumentParser(description="Concilia un release Parquet contra BigQuery por fuente, cuenta y mes.")
    parser.add_argument("--project", default="vpo-corp-royalties")
    parser.add_argument("--dataset", default="royalties_analytics")
    parser.add_argument("--location", default="US")
    parser.add_argument("--bucket", default=os.environ.get("GCS_BUCKET", "vpo-corp-royalties-marts"))
    parser.add_argument("--prefix", default=os.environ.get("GCS_PREFIX", "marts"))
    parser.add_argument("--release-id")
    parser.add_argument("--amount-tolerance", type=float, default=0.01)
    parser.add_argument("--units-tolerance", type=float, default=0.0001)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc)
    run_id = f"{started_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    client = storage_client()
    manifest, manifest_generation = load_manifest(client, args.bucket, args.prefix)
    release_id = str(args.release_id or manifest["release_id"])
    if release_id != str(manifest["release_id"]):
        raise RuntimeError("La conciliacion solo admite el release del manifiesto activo.")

    work_dir = ROOT / "staging" / "bigquery" / release_id
    source_dir = work_dir / "source"
    prepared_dir = work_dir / "prepared"
    filename = SOURCE_FILES["detail"]
    source_path = ensure_source_file(
        client=client,
        bucket_name=args.bucket,
        entry=manifest["files"][filename],
        filename=filename,
        source_dir=source_dir,
    )
    detail_path = prepared_dir / "royalty_detail.parquet"
    build_detail(source_path, detail_path, release_id)

    bq = executable("bq")
    local_rows: list[dict[str, Any]] = []
    bigquery_rows: list[dict[str, Any]] = []
    for period_column, period_basis in [
        ("statement_month", "statement"),
        ("transaction_month", "transaction"),
    ]:
        local_rows.extend(aggregate_local(detail_path, period_column, period_basis))
        bigquery_rows.extend(
            aggregate_bigquery(
                bq=bq,
                project=args.project,
                dataset=args.dataset,
                location=args.location,
                release_id=release_id,
                period_column=period_column,
                period_basis=period_basis,
            )
        )

    results = reconcile_rows(
        local_rows=local_rows,
        bigquery_rows=bigquery_rows,
        release_id=release_id,
        run_id=run_id,
        amount_tolerance=args.amount_tolerance,
        units_tolerance=args.units_tolerance,
    )
    mismatches = [row for row in results if row["status"] == "mismatch"]
    completed_at = datetime.now(timezone.utc)
    report = {
        "run_id": run_id,
        "release_id": release_id,
        "manifest_generation": manifest_generation,
        "started_at": started_at,
        "completed_at": completed_at,
        "status": "ready" if not mismatches else "reconciliation_failed",
        "asset_identity": "ISRC; title is descriptive and never deduplicates assets",
        "amount_tolerance_usd": args.amount_tolerance,
        "units_tolerance": args.units_tolerance,
        "group_count": len(results),
        "mismatch_count": len(mismatches),
        "multi_isrc_title_groups": sum(row["parquet_multi_isrc_title_groups"] for row in results),
        "mismatches": mismatches,
    }
    output_dir = work_dir / "reconciliation" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "reconciliation_results.parquet"
    report_path = output_dir / "reconciliation_report.json"
    result_frame(results).write_parquet(results_path, compression="zstd", statistics=True)
    report_path.write_text(json.dumps(report, indent=2, default=json_value), encoding="utf-8")

    report_uri = ""
    results_uri = ""
    if args.apply:
        object_prefix = f"{args.prefix.strip('/')}/analytics/releases/{release_id}/reconciliation/{run_id}"
        report_uri = upload_immutable(
            client=client,
            bucket_name=args.bucket,
            object_name=f"{object_prefix}/{report_path.name}",
            local_path=report_path,
        )
        results_uri = upload_immutable(
            client=client,
            bucket_name=args.bucket,
            object_name=f"{object_prefix}/{results_path.name}",
            local_path=results_path,
        )
        persist_results(
            bq=bq,
            project=args.project,
            dataset=args.dataset,
            location=args.location,
            release_id=release_id,
            run_id=run_id,
            started_at=started_at,
            completed_at=completed_at,
            amount_tolerance=args.amount_tolerance,
            units_tolerance=args.units_tolerance,
            mismatch_count=len(mismatches),
            report_uri=report_uri,
            results_uri=results_uri,
        )

    console_report = {
        **report,
        "mismatches": mismatches[:20],
        "mismatch_sample_truncated": len(mismatches) > 20,
        "report_uri": report_uri,
        "results_uri": results_uri,
    }
    print(json.dumps(console_report, indent=2, default=json_value))
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
