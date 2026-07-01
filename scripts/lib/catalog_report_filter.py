from __future__ import annotations

import os
from pathlib import Path

import polars as pl


BASE = Path(os.environ.get("VPO_PROJECT_ROOT", Path(__file__).resolve().parents[2]))
MARTS_DIR = BASE / "warehouse" / "marts"
REGISTRY_DIR = BASE / "warehouse" / "registry"

CATALOG_MASTER_PATH = MARTS_DIR / "catalog_master.parquet"
CATALOG_STATUS_PATH = REGISTRY_DIR / "catalog_status.parquet"


def current_catalog_master_path() -> Path:
    return Path(os.environ.get("VPO_CATALOG_MASTER_PATH", CATALOG_MASTER_PATH))


def current_catalog_status_path() -> Path:
    return Path(os.environ.get("VPO_CATALOG_STATUS_PATH", CATALOG_STATUS_PATH))


def has_col(schema: set[str], name: str) -> bool:
    return name in schema


def clean_text(expr: pl.Expr) -> pl.Expr:
    return expr.cast(pl.Utf8, strict=False).str.strip_chars()


def non_blank(expr: pl.Expr) -> pl.Expr:
    value = clean_text(expr)
    return pl.when(value.is_not_null() & (value != "")).then(value).otherwise(None)


def coalesce_text(schema: set[str], columns: list[str]) -> pl.Expr:
    candidates = [non_blank(pl.col(col)) for col in columns if has_col(schema, col)]
    if not candidates:
        return pl.lit(None).cast(pl.Utf8)
    return pl.coalesce(candidates)


def normalized_text(expr: pl.Expr) -> pl.Expr:
    return (
        expr
        .fill_null("")
        .cast(pl.Utf8, strict=False)
        .str.to_lowercase()
        .str.replace_all(r"\s+", " ")
        .str.strip_chars()
    )


def valid_isrc_expr(expr: pl.Expr) -> pl.Expr:
    cleaned = clean_text(expr).str.to_uppercase().str.replace_all(r"[^A-Z0-9]", "")
    return (
        pl.when(cleaned.str.contains(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$"))
        .then(cleaned)
        .otherwise(pl.lit(None).cast(pl.Utf8))
    )


def clean_upc_expr(expr: pl.Expr) -> pl.Expr:
    cleaned = clean_text(expr).str.replace_all(r"[^0-9]", "")
    return (
        pl.when(cleaned.str.len_chars().is_between(8, 14))
        .then(cleaned)
        .otherwise(pl.lit(None).cast(pl.Utf8))
    )


def clean_video_id_expr(expr: pl.Expr) -> pl.Expr:
    cleaned = clean_text(expr).str.replace_all(r"[^A-Za-z0-9_-]", "")
    return (
        pl.when(cleaned.str.len_chars().is_between(8, 32))
        .then(cleaned)
        .otherwise(pl.lit(None).cast(pl.Utf8))
    )


def row_catalog_key_expr(schema: set[str]) -> pl.Expr:
    isrc = valid_isrc_expr(coalesce_text(schema, ["asset_isrc", "ISRC", "Asset ISRC", "YouTube Asset ISRC"]))
    upc = clean_upc_expr(coalesce_text(schema, [
        "product_upc",
        "UPC",
        "Product UPC",
        "DISPLAY UPC",
        "Display UPC",
        "MANUFACTURER UPC",
        "UPC Code",
    ]))
    video = clean_video_id_expr(coalesce_text(schema, [
        "video_id",
        "asset_isrc",
        "Video ID",
        "VideoId",
        "YOUTUBE VIDEO ID",
        "YouTube Video ID",
        "YouTube Asset ID",
        "ID",
        "Parent ID",
        "track_id",
    ]))
    title = normalized_text(coalesce_text(schema, [
        "track_statement_style",
        "asset_title_statement",
        "Track Title",
        "Title",
        "Video Title",
        "Product Title",
        "Album Title",
        "YouTube Video Title",
        "TRACK",
        "PRODUCT",
    ]))
    artist = normalized_text(coalesce_text(schema, [
        "artist_statement_style",
        "asset_artist_statement",
        "artist_best_available",
        "Artists",
        "Track Artists",
        "Product Artist",
        "Channel Name",
        "TRACK ARTIST",
        "PRODUCT ARTIST",
    ]))

    return (
        pl.when(isrc.is_not_null() & (isrc != ""))
        .then(pl.concat_str([pl.lit("ISRC:"), isrc]))
        .when(upc.is_not_null() & (upc != ""))
        .then(pl.concat_str([pl.lit("UPC:"), upc]))
        .when(video.is_not_null() & (video != ""))
        .then(pl.concat_str([pl.lit("VIDEO:"), video]))
        .otherwise(pl.concat_str([pl.lit("TEXT:"), title, pl.lit("|"), artist]))
    )


def catalog_alias_lookup(catalog_path: Path | None = None) -> pl.DataFrame:
    catalog_path = catalog_path or current_catalog_master_path()
    if not catalog_path.exists():
        return pl.DataFrame({
            "alias_catalog_key": pl.Series([], dtype=pl.Utf8),
            "catalog_key": pl.Series([], dtype=pl.Utf8),
        })

    catalog = pl.read_parquet(catalog_path)
    rows: list[pl.DataFrame] = []

    if "catalog_key" in catalog.columns:
        rows.append(catalog.select([
            pl.col("catalog_key").alias("alias_catalog_key"),
            pl.col("catalog_key"),
        ]))

    if {"isrcs", "catalog_key"}.issubset(set(catalog.columns)):
        isrc_aliases = (
            catalog
            .select(["catalog_key", "isrcs"])
            .with_columns(pl.col("isrcs").fill_null("").str.split(" | ").alias("_ids"))
            .explode("_ids")
            .with_columns(valid_isrc_expr(pl.col("_ids")).alias("_id"))
            .filter(pl.col("_id").is_not_null())
            .select([
                pl.concat_str([pl.lit("ISRC:"), pl.col("_id")]).alias("alias_catalog_key"),
                "catalog_key",
            ])
        )
        rows.append(isrc_aliases)

    if {"upcs", "catalog_key"}.issubset(set(catalog.columns)):
        upc_aliases = (
            catalog
            .select(["catalog_key", "upcs"])
            .with_columns(pl.col("upcs").fill_null("").str.split(" | ").alias("_ids"))
            .explode("_ids")
            .with_columns(clean_upc_expr(pl.col("_ids")).alias("_id"))
            .filter(pl.col("_id").is_not_null())
            .select([
                pl.concat_str([pl.lit("UPC:"), pl.col("_id")]).alias("alias_catalog_key"),
                "catalog_key",
            ])
        )
        rows.append(upc_aliases)

    if {"video_ids", "catalog_key"}.issubset(set(catalog.columns)):
        video_aliases = (
            catalog
            .select(["catalog_key", "video_ids"])
            .with_columns(pl.col("video_ids").fill_null("").str.split(" | ").alias("_ids"))
            .explode("_ids")
            .with_columns(clean_video_id_expr(pl.col("_ids")).alias("_id"))
            .filter(pl.col("_id").is_not_null())
            .select([
                pl.concat_str([pl.lit("VIDEO:"), pl.col("_id")]).alias("alias_catalog_key"),
                "catalog_key",
            ])
        )
        rows.append(video_aliases)

    if not rows:
        return pl.DataFrame({
            "alias_catalog_key": pl.Series([], dtype=pl.Utf8),
            "catalog_key": pl.Series([], dtype=pl.Utf8),
        })

    return (
        pl.concat(rows, how="diagonal_relaxed")
        .filter(pl.col("alias_catalog_key").is_not_null() & pl.col("catalog_key").is_not_null())
        .unique(["alias_catalog_key", "catalog_key"])
        .group_by("alias_catalog_key")
        .agg(pl.col("catalog_key").unique().alias("_keys"))
        .filter(pl.col("_keys").list.len() == 1)
        .select([
            "alias_catalog_key",
            pl.col("_keys").list.first().alias("catalog_key"),
        ])
    )


def catalog_status_for_reports(status_path: Path | None = None) -> pl.DataFrame:
    status_path = status_path or current_catalog_status_path()
    if not status_path.exists():
        return pl.DataFrame({
            "catalog_key": pl.Series([], dtype=pl.Utf8),
            "catalog_active": pl.Series([], dtype=pl.Boolean),
            "include_in_reports": pl.Series([], dtype=pl.Boolean),
            "catalog_business_status": pl.Series([], dtype=pl.Utf8),
            "catalog_status_notes": pl.Series([], dtype=pl.Utf8),
        })

    status = pl.read_parquet(status_path)
    if status.is_empty():
        return pl.DataFrame({
            "catalog_key": pl.Series([], dtype=pl.Utf8),
            "catalog_active": pl.Series([], dtype=pl.Boolean),
            "include_in_reports": pl.Series([], dtype=pl.Boolean),
            "catalog_business_status": pl.Series([], dtype=pl.Utf8),
            "catalog_status_notes": pl.Series([], dtype=pl.Utf8),
        })

    columns = set(status.columns)
    include_expr = (
        pl.col("include_in_reports").cast(pl.Boolean, strict=False)
        if "include_in_reports" in columns
        else pl.col("active").cast(pl.Boolean, strict=False)
    )
    business_expr = (
        pl.col("catalog_business_status").cast(pl.Utf8, strict=False)
        if "catalog_business_status" in columns
        else pl.lit(None).cast(pl.Utf8)
    )
    notes_expr = (
        pl.col("status_notes").cast(pl.Utf8, strict=False)
        if "status_notes" in columns
        else pl.lit(None).cast(pl.Utf8)
    )
    return status.select([
        pl.col("catalog_key").cast(pl.Utf8, strict=False),
        pl.col("active").cast(pl.Boolean, strict=False).fill_null(True).alias("catalog_active"),
        include_expr.fill_null(True).alias("include_in_reports"),
        business_expr.alias("catalog_business_status"),
        notes_expr.alias("catalog_status_notes"),
    ])


def with_catalog_report_status(lf: pl.LazyFrame, schema: set[str] | None = None) -> pl.LazyFrame:
    schema = schema or set(lf.collect_schema().names())
    alias_lookup = catalog_alias_lookup()
    status = catalog_status_for_reports()

    out = (
        lf
        .with_columns(row_catalog_key_expr(schema).alias("_catalog_alias_key"))
    )
    if not alias_lookup.is_empty():
        out = (
            out
            .join(alias_lookup.lazy(), left_on="_catalog_alias_key", right_on="alias_catalog_key", how="left")
            .with_columns(pl.coalesce(["catalog_key", "_catalog_alias_key"]).alias("catalog_key"))
        )
    else:
        out = out.with_columns(pl.col("_catalog_alias_key").alias("catalog_key"))

    if not status.is_empty():
        out = (
            out
            .join(status.lazy(), on="catalog_key", how="left")
            .with_columns([
                pl.col("catalog_active").fill_null(True),
                pl.col("include_in_reports").fill_null(True),
                pl.col("catalog_business_status").fill_null("vpo_catalog"),
                pl.col("catalog_status_notes").cast(pl.Utf8, strict=False),
            ])
        )
    else:
        out = out.with_columns([
            pl.lit(True).alias("catalog_active"),
            pl.lit(True).alias("include_in_reports"),
            pl.lit("vpo_catalog").alias("catalog_business_status"),
            pl.lit(None).cast(pl.Utf8).alias("catalog_status_notes"),
        ])

    return out


def filter_reportable_catalog(lf: pl.LazyFrame, schema: set[str] | None = None) -> pl.LazyFrame:
    return with_catalog_report_status(lf, schema).filter(pl.col("include_in_reports") == True)
