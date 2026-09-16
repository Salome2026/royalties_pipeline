from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import polars as pl
from google.api_core.exceptions import PreconditionFailed
from google.cloud import storage


ROOT = Path(__file__).resolve().parents[1]
MARTS_DIR = ROOT / "warehouse" / "marts"
ENV_PATH = ROOT / ".env"

SOURCE_FILES = {
    "detail": "standardized_raw_all_sources.parquet",
    "dashboard": "royalties_dashboard_summary.parquet",
    "song": "song_level_all_sources.parquet",
    "catalog": "catalog_master.parquet",
    "digital": "digital_income_statement_summary.parquet",
}

DETAIL_FIELDS = [
    "release_id",
    "statement_month",
    "transaction_month",
    "source",
    "account",
    "source_sheet",
    "revenue_basis",
    "artist",
    "title",
    "asset_isrc",
    "product_upc",
    "track_id",
    "video_id",
    "channel_id",
    "label",
    "dsp",
    "store_name",
    "territory",
    "sale_type",
    "use_type",
    "monetization",
    "content_origin",
    "classification_status",
    "content_type",
    "amount_usd",
    "units",
    "include_in_statement_view",
    "include_in_cash_view",
    "include_in_catalog_view",
    "possible_internal_transfer",
    "statement_file_name",
    "statement_file_hash",
]

DASHBOARD_FIELDS = [
    "release_id",
    "statement_month",
    "transaction_month",
    "source",
    "account",
    "source_sheet",
    "artist",
    "title",
    "isrc",
    "upc",
    "dsp",
    "territory",
    "sale_type",
    "monetization",
    "content_origin",
    "classification_status",
    "label",
    "search_text",
    "amount_usd",
    "units",
    "raw_rows",
]

SONG_FIELDS = [
    "release_id",
    "transaction_month",
    "source",
    "account",
    "source_sheet",
    "revenue_basis",
    "include_in_cash_view",
    "include_in_catalog_view",
    "include_in_statement_view",
    "possible_internal_transfer",
    "asset_isrc",
    "track_id",
    "title",
    "artist",
    "amount_usd",
    "units",
    "content_type",
    "video_id",
    "channel_id",
    "statement_type",
]

CATALOG_FIELDS = [
    "release_id",
    "catalog_key",
    "asset_isrc",
    "track_id",
    "track_title",
    "artist_statement",
    "first_transaction_month",
    "last_transaction_month",
    "amount_usd",
    "units",
    "song_level_rows",
    "source_count",
    "account_count",
    "sources",
    "accounts",
    "title_variants",
    "artist_variants",
    "primary_upc",
    "isrcs",
    "upcs",
    "video_ids",
    "track_ids",
    "external_release_date",
    "external_label",
    "label_normalized",
]

DIGITAL_FIELDS = [
    "release_id",
    "statement_month",
    "source",
    "account",
    "artist",
    "title",
    "search_text",
    "total_usd",
    "has_share_in_out",
    "raw_rows",
]


def load_local_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def executable(name: str) -> str:
    resolved = shutil.which(name) or shutil.which(f"{name}.cmd")
    if not resolved:
        raise RuntimeError(f"No se encontro {name} en PATH.")
    return resolved


def run(
    command: list[str],
    *,
    capture: bool = False,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=capture,
        input=input_text,
        text=True,
    )


def file_md5_base64(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode("ascii")


def storage_client() -> storage.Client:
    credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if credentials:
        return storage.Client.from_service_account_json(credentials)
    return storage.Client()


def load_manifest(client: storage.Client, bucket_name: str, prefix: str) -> tuple[dict[str, Any], str]:
    object_name = f"{prefix.strip('/')}/release_manifest.json"
    blob = client.bucket(bucket_name).blob(object_name)
    blob.reload(client=client)
    payload = json.loads(blob.download_as_text(client=client))
    return payload, str(blob.generation)


def ensure_source_file(
    *,
    client: storage.Client,
    bucket_name: str,
    entry: dict[str, Any],
    filename: str,
    source_dir: Path,
) -> Path:
    expected_size = int(entry["size_bytes"])
    expected_md5 = str(entry["md5_hash"])
    canonical = MARTS_DIR / filename
    candidates = [canonical, source_dir / filename]
    for candidate in candidates:
        if candidate.exists() and candidate.stat().st_size == expected_size:
            if file_md5_base64(candidate) == expected_md5:
                return candidate

    target = source_dir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    blob = client.bucket(bucket_name).blob(str(entry["object_name"]))
    blob.download_to_filename(str(target), client=client)
    if target.stat().st_size != expected_size or file_md5_base64(target) != expected_md5:
        raise RuntimeError(f"El archivo descargado no coincide con el manifiesto: {filename}")
    return target


def text_expr(columns: set[str], names: list[str]) -> pl.Expr:
    expressions = [
        pl.col(name).cast(pl.String, strict=False).str.strip_chars().replace("", None)
        for name in names
        if name in columns
    ]
    return pl.coalesce(expressions) if expressions else pl.lit(None, dtype=pl.String)


def float_expr(columns: set[str], name: str) -> pl.Expr:
    if name not in columns:
        return pl.lit(0.0, dtype=pl.Float64)
    return pl.col(name).cast(pl.Float64, strict=False).fill_null(0.0)


def int_expr(columns: set[str], name: str) -> pl.Expr:
    if name not in columns:
        return pl.lit(0, dtype=pl.Int64)
    return pl.col(name).cast(pl.Int64, strict=False).fill_null(0)


def bool_expr(columns: set[str], name: str, default: bool) -> pl.Expr:
    if name not in columns:
        return pl.lit(default, dtype=pl.Boolean)
    return pl.col(name).cast(pl.Boolean, strict=False).fill_null(default)


def month_expr(columns: set[str], names: list[str]) -> pl.Expr:
    return text_expr(columns, names).str.to_date("%Y-%m", strict=False)


def day_expr(columns: set[str], names: list[str]) -> pl.Expr:
    return text_expr(columns, names).str.to_date("%Y-%m-%d", strict=False)


def write_lazy(frame: pl.LazyFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.parquet")
    if temporary.exists():
        temporary.unlink()
    frame.sink_parquet(temporary, compression="zstd", statistics=True)
    temporary.replace(path)


def build_detail(source: Path, target: Path, release_id: str) -> None:
    frame = pl.scan_parquet(source)
    columns = set(frame.collect_schema().names())
    write_lazy(
        frame.select(
            [
                pl.lit(release_id).alias("release_id"),
                month_expr(columns, ["statement_period"]).alias("statement_month"),
                month_expr(columns, ["transaction_month", "Transaction Month"]).alias("transaction_month"),
                text_expr(columns, ["source"]).alias("source"),
                text_expr(columns, ["account"]).alias("account"),
                text_expr(columns, ["source_sheet"]).alias("source_sheet"),
                text_expr(columns, ["revenue_basis"]).alias("revenue_basis"),
                text_expr(
                    columns,
                    [
                        "artist_best_available",
                        "asset_artist_statement",
                        "artist_statement_style",
                        "product_artist_statement",
                        "track_artist_statement",
                        "Artist Name",
                    ],
                ).alias("artist"),
                text_expr(
                    columns,
                    [
                        "asset_title_statement",
                        "track_statement_style",
                        "product_title_statement",
                        "Track Title",
                    ],
                ).alias("title"),
                text_expr(columns, ["asset_isrc", "Asset ISRC", "ISRC"]).alias("asset_isrc"),
                text_expr(columns, ["product_upc", "UPC Code", "UPC"]).alias("product_upc"),
                text_expr(columns, ["track_id", "Label Track ID", "Track ID", "gpid"]).alias("track_id"),
                text_expr(columns, ["video_id", "Video ID", "VideoId"]).alias("video_id"),
                text_expr(columns, ["channel_id", "Channel ID", "ChannelId"]).alias("channel_id"),
                text_expr(
                    columns,
                    ["label_normalized", "label_normalized_auto", "label_statement_style", "Product Label", "Label Name"],
                ).alias("label"),
                text_expr(columns, ["dsp_normalized", "dsp", "store_report_label", "store_name", "DSP", "Store"]).alias("dsp"),
                text_expr(columns, ["store_name", "Store Name", "Sale Store Name", "STORE"]).alias("store_name"),
                text_expr(columns, ["territory", "Territory", "Region", "SALE COUNTRY", "Country"]).alias("territory"),
                text_expr(columns, ["sale_type", "Sales Type", "Sale Type", "TRANSACTION TYPE"]).alias("sale_type"),
                text_expr(columns, ["use_type", "sale_user_type", "Sales Sub Type", "SERVICE DETAIL"]).alias("use_type"),
                text_expr(columns, ["monetization_normalized"]).alias("monetization"),
                text_expr(columns, ["content_origin_normalized"]).alias("content_origin"),
                text_expr(columns, ["classification_status"]).alias("classification_status"),
                text_expr(columns, ["content_type", "Product Type", "Config Type"]).alias("content_type"),
                float_expr(columns, "amount_usd").alias("amount_usd"),
                float_expr(columns, "units").alias("units"),
                bool_expr(columns, "include_in_statement_view", True).alias("include_in_statement_view"),
                bool_expr(columns, "include_in_cash_view", True).alias("include_in_cash_view"),
                bool_expr(columns, "include_in_catalog_view", True).alias("include_in_catalog_view"),
                bool_expr(columns, "possible_internal_transfer", False).alias("possible_internal_transfer"),
                text_expr(columns, ["statement_file_name"]).alias("statement_file_name"),
                text_expr(columns, ["statement_file_hash"]).alias("statement_file_hash"),
            ]
        ),
        target,
    )


def build_dashboard(source: Path, target: Path, release_id: str) -> None:
    frame = pl.scan_parquet(source)
    columns = set(frame.collect_schema().names())
    write_lazy(
        frame.select(
            [
                pl.lit(release_id).alias("release_id"),
                month_expr(columns, ["statement_period"]).alias("statement_month"),
                month_expr(columns, ["transaction_month"]).alias("transaction_month"),
                *[text_expr(columns, [name]).alias(name) for name in ["source", "account", "source_sheet", "artist", "title", "isrc", "upc", "dsp", "territory", "sale_type"]],
                text_expr(columns, ["monetization_normalized"]).alias("monetization"),
                text_expr(columns, ["content_origin_normalized"]).alias("content_origin"),
                text_expr(columns, ["classification_status"]).alias("classification_status"),
                text_expr(columns, ["label"]).alias("label"),
                text_expr(columns, ["search_text"]).alias("search_text"),
                float_expr(columns, "amount_usd").alias("amount_usd"),
                float_expr(columns, "units").alias("units"),
                int_expr(columns, "raw_rows").alias("raw_rows"),
            ]
        ),
        target,
    )


def build_song(source: Path, target: Path, release_id: str) -> None:
    frame = pl.scan_parquet(source)
    columns = set(frame.collect_schema().names())
    write_lazy(
        frame.select(
            [
                pl.lit(release_id).alias("release_id"),
                month_expr(columns, ["transaction_month"]).alias("transaction_month"),
                *[text_expr(columns, [name]).alias(name) for name in ["source", "account", "source_sheet", "revenue_basis"]],
                bool_expr(columns, "include_in_cash_view", True).alias("include_in_cash_view"),
                bool_expr(columns, "include_in_catalog_view", True).alias("include_in_catalog_view"),
                bool_expr(columns, "include_in_statement_view", True).alias("include_in_statement_view"),
                bool_expr(columns, "possible_internal_transfer", False).alias("possible_internal_transfer"),
                text_expr(columns, ["asset_isrc"]).alias("asset_isrc"),
                text_expr(columns, ["track_id"]).alias("track_id"),
                text_expr(columns, ["track_statement_style", "asset_title_statement"]).alias("title"),
                text_expr(columns, ["artist_statement_style", "asset_artist_statement"]).alias("artist"),
                float_expr(columns, "amount_usd").alias("amount_usd"),
                float_expr(columns, "units").alias("units"),
                text_expr(columns, ["content_type"]).alias("content_type"),
                text_expr(columns, ["video_id"]).alias("video_id"),
                text_expr(columns, ["channel_id"]).alias("channel_id"),
                text_expr(columns, ["statement_type"]).alias("statement_type"),
            ]
        ),
        target,
    )


def build_catalog(source: Path, target: Path, release_id: str) -> None:
    frame = pl.scan_parquet(source)
    columns = set(frame.collect_schema().names())
    write_lazy(
        frame.select(
            [
                pl.lit(release_id).alias("release_id"),
                *[text_expr(columns, [name]).alias(name) for name in ["catalog_key", "asset_isrc", "track_id", "track_title", "artist_statement"]],
                month_expr(columns, ["first_transaction_month"]).alias("first_transaction_month"),
                month_expr(columns, ["last_transaction_month"]).alias("last_transaction_month"),
                float_expr(columns, "amount_usd").alias("amount_usd"),
                float_expr(columns, "units").alias("units"),
                int_expr(columns, "song_level_rows").alias("song_level_rows"),
                int_expr(columns, "source_count").alias("source_count"),
                int_expr(columns, "account_count").alias("account_count"),
                *[text_expr(columns, [name]).alias(name) for name in ["sources", "accounts", "title_variants", "artist_variants", "primary_upc", "isrcs", "upcs", "video_ids", "track_ids"]],
                day_expr(columns, ["external_release_date"]).alias("external_release_date"),
                text_expr(columns, ["external_label"]).alias("external_label"),
                text_expr(columns, ["label_normalized"]).alias("label_normalized"),
            ]
        ),
        target,
    )


def build_digital(source: Path, target: Path, release_id: str) -> None:
    frame = pl.scan_parquet(source)
    columns = set(frame.collect_schema().names())
    write_lazy(
        frame.select(
            [
                pl.lit(release_id).alias("release_id"),
                month_expr(columns, ["statement_period"]).alias("statement_month"),
                *[text_expr(columns, [name]).alias(name) for name in ["source", "account", "artist", "title", "search_text"]],
                float_expr(columns, "total_usd").alias("total_usd"),
                bool_expr(columns, "has_share_in_out", False).alias("has_share_in_out"),
                int_expr(columns, "raw_rows").alias("raw_rows"),
            ]
        ),
        target,
    )


def parquet_summary(path: Path, amount_column: str) -> dict[str, Any]:
    row = (
        pl.scan_parquet(path)
        .select(
            pl.len().alias("rows"),
            pl.col(amount_column).sum().alias("amount"),
        )
        .collect()
        .to_dicts()[0]
    )
    return {"rows": int(row["rows"]), "amount": float(row["amount"] or 0.0)}


def upload_immutable(
    *,
    client: storage.Client,
    bucket_name: str,
    object_name: str,
    local_path: Path,
) -> str:
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    local_md5 = file_md5_base64(local_path)
    try:
        blob.upload_from_filename(str(local_path), if_generation_match=0)
    except PreconditionFailed:
        blob.reload(client=client)
        if int(blob.size or 0) != local_path.stat().st_size or blob.md5_hash != local_md5:
            raise RuntimeError(f"El objeto analitico inmutable ya existe con otro contenido: {object_name}")
    return f"gs://{bucket_name}/{object_name}"


def bq_load(
    *,
    bq: str,
    project: str,
    dataset: str,
    location: str,
    table: str,
    uri: str,
) -> None:
    run(
        [
            bq,
            f"--project_id={project}",
            "load",
            f"--location={location}",
            "--replace",
            "--autodetect",
            "--source_format=PARQUET",
            f"{project}:{dataset}.{table}",
            uri,
        ]
    )


def sql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def insert_sql(
    *,
    project: str,
    dataset: str,
    release_id: str,
    manifest_generation: str,
    published_at: str,
    manifest_uri: str,
    source_files: int,
    stages: dict[str, str],
) -> str:
    qualified = lambda table: f"`{project}.{dataset}.{table}`"
    fields = {
        "detail": DETAIL_FIELDS,
        "dashboard": DASHBOARD_FIELDS,
        "song": SONG_FIELDS,
        "catalog": CATALOG_FIELDS,
        "digital": DIGITAL_FIELDS,
    }
    release = sql_string(release_id)
    statements = ["BEGIN TRANSACTION;"]
    targets = {
        "royalty_statement_fact": "detail",
        "royalty_transaction_fact": "detail",
        "royalty_dashboard_rankings": "dashboard",
        "royalty_song_level": "song",
        "royalty_catalog": "catalog",
        "digital_income_summary": "digital",
    }
    for table, stage_key in targets.items():
        column_list = ", ".join(f"`{name}`" for name in fields[stage_key])
        statements.extend(
            [
                f"DELETE FROM {qualified(table)} WHERE release_id = '{release}';",
                f"INSERT INTO {qualified(table)} ({column_list}) SELECT {column_list} FROM {qualified(stages[stage_key])};",
            ]
        )
    statements.extend(
        [
            f"DELETE FROM {qualified('royalty_dashboard_monthly')} WHERE release_id = '{release}';",
            f"""
INSERT INTO {qualified('royalty_dashboard_monthly')}
SELECT
  release_id,
  statement_month,
  transaction_month,
  source,
  account,
  SUM(amount_usd) AS amount_usd,
  SUM(units) AS units,
  SUM(raw_rows) AS raw_rows,
  COUNT(DISTINCT NULLIF(artist, '')) AS artists,
  COUNT(DISTINCT NULLIF(title, '')) AS titles,
  COUNT(DISTINCT NULLIF(isrc, '')) AS isrcs
FROM {qualified(stages['dashboard'])}
GROUP BY release_id, statement_month, transaction_month, source, account;
""".strip(),
            f"DELETE FROM {qualified('analytics_releases')} WHERE release_id = '{release}';",
            f"""
INSERT INTO {qualified('analytics_releases')} (
  release_id, manifest_generation, published_at, loaded_at, status,
  source_manifest_uri, source_files, source_rows, source_amount_usd,
  dashboard_rows, dashboard_amount_usd, notes
)
SELECT
  '{release}',
  '{sql_string(manifest_generation)}',
  TIMESTAMP('{sql_string(published_at)}'),
  CURRENT_TIMESTAMP(),
  'ready',
  '{sql_string(manifest_uri)}',
  {source_files},
  (SELECT COUNT(*) FROM {qualified(stages['detail'])}),
  (SELECT COALESCE(SUM(amount_usd), 0) FROM {qualified(stages['detail'])}),
  (SELECT COUNT(*) FROM {qualified(stages['dashboard'])}),
  (SELECT COALESCE(SUM(amount_usd), 0) FROM {qualified(stages['dashboard'])}),
  'shadow load from immutable GCS release';
""".strip(),
            "COMMIT TRANSACTION;",
        ]
    )
    return "\n".join(statements)


def bq_query_json(bq: str, project: str, location: str, sql: str) -> list[dict[str, Any]]:
    result = run(
        [
            bq,
            f"--project_id={project}",
            "query",
            f"--location={location}",
            "--use_legacy_sql=false",
            "--format=json",
        ],
        capture=True,
        input_text=sql,
    )
    return json.loads(result.stdout or "[]")


def main() -> None:
    load_local_env(ENV_PATH)
    parser = argparse.ArgumentParser(description="Carga un release inmutable en BigQuery sombra.")
    parser.add_argument("--project", default="vpo-corp-royalties")
    parser.add_argument("--dataset", default="royalties_analytics")
    parser.add_argument("--location", default="US")
    parser.add_argument("--bucket", default=os.environ.get("GCS_BUCKET", "vpo-corp-royalties-marts"))
    parser.add_argument("--prefix", default=os.environ.get("GCS_PREFIX", "marts"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    client = storage_client()
    manifest, manifest_generation = load_manifest(client, args.bucket, args.prefix)
    release_id = str(manifest["release_id"])
    manifest_uri = f"gs://{args.bucket}/{args.prefix.strip('/')}/release_manifest.json"
    print(f"Release: {release_id}")
    print(f"Manifest generation: {manifest_generation}")
    if not args.apply:
        print(f"DRY RUN: cargaria {release_id} en {args.project}.{args.dataset}")
        return

    work_dir = ROOT / "staging" / "bigquery" / release_id
    source_dir = work_dir / "source"
    prepared_dir = work_dir / "prepared"
    source_paths: dict[str, Path] = {}
    for key, filename in SOURCE_FILES.items():
        source_paths[key] = ensure_source_file(
            client=client,
            bucket_name=args.bucket,
            entry=manifest["files"][filename],
            filename=filename,
            source_dir=source_dir,
        )
        print(f"SOURCE OK: {filename}")

    prepared = {
        "detail": prepared_dir / "royalty_detail.parquet",
        "dashboard": prepared_dir / "dashboard_rankings.parquet",
        "song": prepared_dir / "song_level.parquet",
        "catalog": prepared_dir / "catalog.parquet",
        "digital": prepared_dir / "digital_income.parquet",
    }
    build_detail(source_paths["detail"], prepared["detail"], release_id)
    build_dashboard(source_paths["dashboard"], prepared["dashboard"], release_id)
    build_song(source_paths["song"], prepared["song"], release_id)
    build_catalog(source_paths["catalog"], prepared["catalog"], release_id)
    build_digital(source_paths["digital"], prepared["digital"], release_id)

    local_detail = parquet_summary(prepared["detail"], "amount_usd")
    local_dashboard = parquet_summary(prepared["dashboard"], "amount_usd")
    print(json.dumps({"detail": local_detail, "dashboard": local_dashboard}, indent=2))

    analytics_prefix = f"{args.prefix.strip('/')}/analytics/releases/{release_id}"
    uris = {
        key: upload_immutable(
            client=client,
            bucket_name=args.bucket,
            object_name=f"{analytics_prefix}/{path.name}",
            local_path=path,
        )
        for key, path in prepared.items()
    }

    suffix = re.sub(r"[^a-zA-Z0-9]", "", release_id)[-20:].lower()
    stages = {key: f"_stage_{key}_{suffix}" for key in prepared}
    bq = executable("bq")
    for key, table in stages.items():
        bq_load(
            bq=bq,
            project=args.project,
            dataset=args.dataset,
            location=args.location,
            table=table,
            uri=uris[key],
        )

    sql = insert_sql(
        project=args.project,
        dataset=args.dataset,
        release_id=release_id,
        manifest_generation=manifest_generation,
        published_at=str(manifest["published_at"]),
        manifest_uri=manifest_uri,
        source_files=len(manifest["files"]),
        stages=stages,
    )
    run(
        [
            bq,
            f"--project_id={args.project}",
            "query",
            f"--location={args.location}",
            "--use_legacy_sql=false",
        ],
        input_text=sql,
    )

    validation_sql = f"""
SELECT
  (SELECT release_id FROM `{args.project}.{args.dataset}.current_release`) AS current_release_id,
  (SELECT COUNT(*) FROM `{args.project}.{args.dataset}.royalty_statement_fact` WHERE release_id = '{sql_string(release_id)}') AS detail_rows,
  (SELECT COALESCE(SUM(amount_usd), 0) FROM `{args.project}.{args.dataset}.royalty_statement_fact` WHERE release_id = '{sql_string(release_id)}') AS detail_amount,
  (SELECT COUNT(*) FROM `{args.project}.{args.dataset}.royalty_dashboard_rankings` WHERE release_id = '{sql_string(release_id)}') AS dashboard_rows,
  (SELECT COALESCE(SUM(amount_usd), 0) FROM `{args.project}.{args.dataset}.royalty_dashboard_rankings` WHERE release_id = '{sql_string(release_id)}') AS dashboard_amount
""".strip()
    validation = bq_query_json(bq, args.project, args.location, validation_sql)[0]
    if validation["current_release_id"] != release_id:
        raise RuntimeError(f"current_release no apunta al release cargado: {validation}")
    if int(validation["detail_rows"]) != local_detail["rows"]:
        raise RuntimeError(f"Filas de detalle no coinciden: {validation}")
    if int(validation["dashboard_rows"]) != local_dashboard["rows"]:
        raise RuntimeError(f"Filas de dashboard no coinciden: {validation}")
    if abs(float(validation["detail_amount"]) - local_detail["amount"]) > 0.01:
        raise RuntimeError(f"Importe de detalle no coincide: {validation}")
    if abs(float(validation["dashboard_amount"]) - local_dashboard["amount"]) > 0.01:
        raise RuntimeError(f"Importe de dashboard no coincide: {validation}")

    for table in stages.values():
        run([bq, f"--project_id={args.project}", "rm", "-f", "-t", f"{args.project}:{args.dataset}.{table}"])
    print(json.dumps({"ok": True, "release_id": release_id, "validation": validation}, indent=2))


if __name__ == "__main__":
    main()
