from __future__ import annotations

import os
from pathlib import Path

import polars as pl

try:
    from lib.distributor_policy_store import load_distributor_policy_document
except ModuleNotFoundError:
    from scripts.lib.distributor_policy_store import load_distributor_policy_document


BASE = Path(os.environ.get("VPO_PROJECT_ROOT", Path(__file__).resolve().parents[2]))
MARTS_DIR = BASE / "warehouse" / "marts"
REGISTRY_DIR = BASE / "warehouse" / "registry"

CATALOG_MASTER_PATH = MARTS_DIR / "catalog_master.parquet"
CATALOG_STATUS_PATH = REGISTRY_DIR / "catalog_status.parquet"
GENERATION_REVENUE_BASIS = {"generation", "correction", "legacy_generation"}
LEGACY_GENERATION_REVENUE_BASIS = {
    "master_earning",
    "youtube_channel_earning",
    "master_earning_external_account",
    "youtube_channel_earning_external_account",
}
NON_GENERATION_REVENUE_BASIS = {"transfer", "summary", "share_transfer"}


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


def normalized_key(expr: pl.Expr) -> pl.Expr:
    return normalized_text(expr).str.replace_all(" ", "_")


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
        "title",
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
        "artist",
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


def distributor_policy_rules() -> pl.DataFrame:
    payload = load_distributor_policy_document()
    personalization = payload.get("report_personalization") or {}
    personalization_enabled = bool(personalization.get("enabled", False))
    rows: list[dict] = []
    for entry in payload.get("entries", []):
        source = str(entry.get("source") or "").strip().lower()
        account = str(entry.get("account") or "").strip().lower()
        if not source or not account:
            continue
        report_net_adjustment_pct = float(entry.get("report_net_adjustment_pct") or 0.0)
        for source_sheet, rule in (entry.get("sheet_rules") or {}).items():
            if not isinstance(rule, dict):
                continue
            rows.append({
                "_policy_source": source,
                "_policy_account": account,
                "_policy_source_sheet": str(source_sheet or "").strip(),
                "policy_catalog_view": rule.get("catalog_view"),
                "policy_statement_view": str(rule.get("statement_view")),
                "policy_cash_view": str(rule.get("cash_view")),
                "policy_audit_view": bool(rule.get("audit_view", False)),
                "policy_revenue_basis": rule.get("revenue_basis"),
                "policy_report_personalization_enabled": personalization_enabled,
                "policy_report_net_adjustment_pct": report_net_adjustment_pct,
            })

    if not rows:
        raise ValueError("Cloud SQL distributor policy has no sheet rules.")

    return pl.DataFrame(rows).with_columns([
        pl.col("_policy_source").cast(pl.Utf8),
        pl.col("_policy_account").cast(pl.Utf8),
        pl.col("_policy_source_sheet").cast(pl.Utf8),
        pl.col("policy_catalog_view").cast(pl.Boolean, strict=False),
        pl.col("policy_statement_view").cast(pl.Utf8, strict=False),
        pl.col("policy_cash_view").cast(pl.Utf8, strict=False),
        pl.col("policy_audit_view").cast(pl.Boolean, strict=False),
        pl.col("policy_revenue_basis").cast(pl.Utf8, strict=False),
        pl.col("policy_report_personalization_enabled").cast(pl.Boolean, strict=False).fill_null(False),
        pl.col("policy_report_net_adjustment_pct").cast(pl.Float64, strict=False).fill_null(0.0),
    ])


def row_source_expr(schema: set[str]) -> pl.Expr:
    return normalized_key(coalesce_text(schema, ["source", "Fuente", "SOURCE"]))


def row_account_expr(schema: set[str]) -> pl.Expr:
    return normalized_key(coalesce_text(schema, ["account", "Cuenta", "ACCOUNT"]))


def row_source_sheet_expr(schema: set[str]) -> pl.Expr:
    direct = coalesce_text(schema, ["source_sheet", "sheet_name", "Sheet", "SHEET"])
    statement_type = coalesce_text(schema, ["statement_type", "statement_kind"])
    file_name = coalesce_text(schema, ["statement_file_name", "mart_source_file", "source_file"])
    source = row_source_expr(schema)

    direct_clean = clean_text(direct)
    statement_clean = clean_text(statement_type)
    statement_lower = statement_clean.fill_null("").str.to_lowercase()
    file_lower = clean_text(file_name).fill_null("").str.to_lowercase()

    return (
        pl.when(direct_clean.is_not_null() & (direct_clean != ""))
        .then(direct_clean)
        .when(source == "dashgo")
        .then(pl.lit("detail"))
        .when(
            (source == "fuga")
            & (
                statement_lower.str.contains("correction", literal=True)
                | file_lower.str.contains("correction", literal=True)
            )
        )
        .then(pl.lit("correction_csv"))
        .when(source == "fuga")
        .then(pl.lit("standard_statement_csv"))
        .when(
            (source == "orchard")
            & statement_lower.str.contains("legacy", literal=True)
        )
        .then(pl.lit("legacy_altafonte"))
        .when(source == "orchard")
        .then(pl.lit("revenue_detail"))
        .when(source == "soundon")
        .then(
            pl.when(statement_clean.is_not_null() & (statement_clean != ""))
            .then(statement_clean)
            .otherwise(pl.lit("my_royalty"))
        )
        .otherwise(pl.lit(None).cast(pl.Utf8))
    )


def row_revenue_basis_expr(schema: set[str]) -> pl.Expr:
    return normalized_key(coalesce_text(schema, ["revenue_basis", "Base ingreso"]))


def with_distributor_policy(lf: pl.LazyFrame, schema: set[str] | None = None) -> pl.LazyFrame:
    schema = schema or set(lf.collect_schema().names())
    rules = distributor_policy_rules()
    return (
        lf
        .with_columns([
            row_source_expr(schema).alias("_policy_source"),
            row_account_expr(schema).alias("_policy_account"),
            row_source_sheet_expr(schema).alias("_policy_source_sheet"),
            row_revenue_basis_expr(schema).alias("_row_revenue_basis"),
        ])
        .join(
            rules.lazy(),
            on=["_policy_source", "_policy_account", "_policy_source_sheet"],
            how="left",
        )
        .with_columns([
            pl.coalesce([
                normalized_key(pl.col("policy_revenue_basis")),
                pl.col("_row_revenue_basis"),
            ]).alias("_effective_revenue_basis"),
            pl.col("policy_revenue_basis").is_not_null().alias("_policy_matched"),
        ])
    )


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


def filter_reportable_generation(lf: pl.LazyFrame, schema: set[str] | None = None) -> pl.LazyFrame:
    schema = schema or set(lf.collect_schema().names())
    enriched = with_distributor_policy(with_catalog_report_status(lf, schema), schema)
    policy_statement_view = pl.col("policy_statement_view").fill_null("").str.to_lowercase()
    return enriched.filter(
        (pl.col("include_in_reports") == True)
        & (
            pl.when(pl.col("_policy_matched"))
            .then(
                (pl.col("policy_catalog_view") == True)
                & (~policy_statement_view.is_in(["false", "0", "no", "none"]))
                & pl.col("_effective_revenue_basis").is_in(GENERATION_REVENUE_BASIS)
            )
            .otherwise(
                pl.col("_effective_revenue_basis").is_in(LEGACY_GENERATION_REVENUE_BASIS)
                | (
                    pl.col("_effective_revenue_basis").is_not_null()
                    & (~pl.col("_effective_revenue_basis").is_in(NON_GENERATION_REVENUE_BASIS))
                )
            )
        )
    )


def apply_report_net_personalization(
    lf: pl.LazyFrame,
    schema: set[str] | None = None,
    amount_col: str = "amount_usd",
) -> pl.LazyFrame:
    schema = schema or set(lf.collect_schema().names())
    if amount_col not in schema:
        return lf
    policy = load_distributor_policy_document()
    personalization = policy.get("report_personalization") or {}
    if not bool(personalization.get("enabled", False)):
        return lf

    source = row_source_expr(schema)
    account = row_account_expr(schema)
    factor = pl.lit(1.0)
    for entry in reversed(policy.get("entries", [])):
        policy_source = str(entry.get("source") or "").strip().lower().replace(" ", "_")
        policy_account = str(entry.get("account") or "").strip().lower().replace(" ", "_")
        adjustment = float(entry.get("report_net_adjustment_pct") or 0.0)
        if not policy_source or not policy_account or adjustment == 0:
            continue
        factor = (
            pl.when((source == policy_source) & (account == policy_account))
            .then(pl.lit(1 - adjustment / 100))
            .otherwise(factor)
        )

    amount = pl.col(amount_col).cast(pl.Float64, strict=False).fill_null(0.0)
    return lf.with_columns((amount * factor).alias(amount_col))


def filter_reportable_cash(lf: pl.LazyFrame, schema: set[str] | None = None) -> pl.LazyFrame:
    schema = schema or set(lf.collect_schema().names())
    enriched = with_distributor_policy(with_catalog_report_status(lf, schema), schema)
    policy_cash_view = pl.col("policy_cash_view").fill_null("").str.to_lowercase()
    return enriched.filter(
        (pl.col("include_in_reports") == True)
        & (
            pl.when(pl.col("_policy_matched"))
            .then(~policy_cash_view.is_in(["false", "0", "no", "none"]))
            .otherwise(True)
        )
    )
