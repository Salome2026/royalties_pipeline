from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl

from lib.identity import valid_youtube_channel_id_expr
from lib.distributor_policy_store import load_distributor_policy_document


BASE = Path(r"C:\royalties_pipeline")
MARTS_DIR = BASE / "warehouse" / "marts"
REGISTRY_DIR = BASE / "warehouse" / "registry"

SONG_LEVEL_PATH = MARTS_DIR / "song_level_all_sources.parquet"
RELEASE_METADATA_PATH = MARTS_DIR / "catalog_release_metadata.parquet"
OUTPUT_PATH = MARTS_DIR / "catalog_master.parquet"
CATALOG_REVENUE_BASIS = {"generation", "correction", "legacy_generation"}
STANDARDIZED_PATHS = [
    MARTS_DIR / "standardized_raw_fuga.parquet",
    MARTS_DIR / "standardized_raw_dashgo.parquet",
    MARTS_DIR / "standardized_raw_orchard.parquet",
    MARTS_DIR / "standardized_raw_soundon.parquet",
    MARTS_DIR / "standardized_raw_onerpm.parquet",
    MARTS_DIR / "standardized_raw_ada.parquet",
]


def clean_text(expr: pl.Expr) -> pl.Expr:
    return expr.cast(pl.Utf8, strict=False).str.strip_chars()


def has_col(schema: set[str], name: str) -> bool:
    return name in schema


def coalesce_text(schema: set[str], columns: list[str]) -> pl.Expr:
    candidates = [clean_text(pl.col(col)) for col in columns if has_col(schema, col)]
    if not candidates:
        return pl.lit(None).cast(pl.Utf8)
    return pl.coalesce(candidates)


def amount_expr(schema: set[str]) -> pl.Expr:
    for col in ["amount_usd", "net_amount_usd", "net_amount"]:
        if has_col(schema, col):
            return pl.col(col).cast(pl.Float64, strict=False)
    return pl.lit(0.0)


def units_expr(schema: set[str]) -> pl.Expr:
    for col in ["units", "streams", "Quantity", "quantity"]:
        if has_col(schema, col):
            return pl.col(col).cast(pl.Float64, strict=False)
    return pl.lit(0.0)


def normalized_text(expr: pl.Expr) -> pl.Expr:
    return (
        expr
        .fill_null("")
        .cast(pl.Utf8, strict=False)
        .str.to_lowercase()
        .str.replace_all(r"\s+", " ")
        .str.strip_chars()
    )


def normalized_label_expr(expr: pl.Expr) -> pl.Expr:
    cleaned = (
        expr
        .fill_null("")
        .cast(pl.Utf8, strict=False)
        .str.strip_chars()
        .str.replace_all(r"(?i)^\s*(?:\([pc]\)|[℗©])\.?\s*", "")
        .str.replace_all(r"(?i)^\s*[pc]\.?\s+((?:19|20)\d{2}\b)", "$1")
        .str.replace_all(r"^\s*(?:19|20)\d{2}\s*", "")
        .str.replace_all(r"(?i)^\s*(?:\([pc]\)|[℗©])\.?\s*", "")
        .str.replace_all(r"(?i)^\s*[pc]\.?\s+((?:19|20)\d{2}\b)", "$1")
        .str.replace_all(r"^\s*(?:19|20)\d{2}\s*", "")
        .str.replace_all(r"\s+", " ")
        .str.strip_chars(" -–—")
    )
    return (
        pl.when(cleaned == "")
        .then(pl.lit(None).cast(pl.Utf8))
        .otherwise(cleaned)
    )


def clean_identifier(expr: pl.Expr) -> pl.Expr:
    return expr.cast(pl.Utf8, strict=False).str.strip_chars()


def valid_isrc_expr(expr: pl.Expr) -> pl.Expr:
    cleaned = clean_identifier(expr).str.to_uppercase().str.replace_all(r"[^A-Z0-9]", "")
    return (
        pl.when(cleaned.str.contains(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$"))
        .then(cleaned)
        .otherwise(pl.lit(None).cast(pl.Utf8))
    )


def clean_upc_expr(expr: pl.Expr) -> pl.Expr:
    cleaned = clean_identifier(expr).str.replace_all(r"[^0-9]", "")
    return (
        pl.when(cleaned.str.len_chars().is_between(8, 14))
        .then(cleaned)
        .otherwise(pl.lit(None).cast(pl.Utf8))
    )


def clean_video_id_expr(expr: pl.Expr) -> pl.Expr:
    cleaned = clean_identifier(expr)
    return (
        pl.when(cleaned.str.contains(r"^[A-Za-z0-9_-]{11}$"))
        .then(cleaned)
        .otherwise(pl.lit(None).cast(pl.Utf8))
    )


def list_join_expr(col_name: str) -> pl.Expr:
    return (
        pl.col(col_name)
        .drop_nulls()
        .cast(pl.Utf8)
        .unique()
        .sort()
        .str.join(" | ")
    )


def first_mode_expr(col_name: str) -> pl.Expr:
    return pl.col(col_name).drop_nulls().mode().first()


def load_account_policy_rules() -> pl.DataFrame:
    payload = load_distributor_policy_document()
    rows = []
    for entry in payload.get("entries", []):
        source = entry.get("source")
        account = entry.get("account")
        for source_sheet, rule in entry.get("sheet_rules", {}).items():
            rows.append({
                "source": source,
                "account": account,
                "source_sheet": source_sheet,
                "policy_catalog_view": rule.get("catalog_view"),
                "policy_statement_view": str(rule.get("statement_view")),
                "policy_cash_view": str(rule.get("cash_view")),
                "policy_audit_view": bool(rule.get("audit_view", False)),
                "policy_revenue_basis": rule.get("revenue_basis"),
            })

    if not rows:
        raise ValueError("Cloud SQL distributor policy has no sheet rules.")

    return pl.DataFrame(rows).with_columns([
        pl.col("source").cast(pl.Utf8),
        pl.col("account").cast(pl.Utf8),
        pl.col("source_sheet").cast(pl.Utf8),
        pl.col("policy_catalog_view").cast(pl.Boolean, strict=False),
        pl.col("policy_revenue_basis").cast(pl.Utf8, strict=False),
    ])


def assert_policy_coverage(prepared: pl.LazyFrame) -> None:
    unmatched = (
        prepared
        .filter(
            pl.col("policy_revenue_basis").is_null()
            & (pl.col("observed_amount_usd").fill_null(0.0) != 0.0)
        )
        .group_by(["source", "account", "source_sheet", "revenue_basis"])
        .agg([
            pl.len().alias("rows"),
            pl.sum("observed_amount_usd").round(6).alias("amount_usd"),
        ])
        .sort("amount_usd", descending=True)
        .collect()
    )
    if not unmatched.is_empty():
        raise ValueError(
            "Hay filas de song_level sin policy de catalogo. "
            "Alinear source/account/source_sheet antes de construir catalog_master:\n"
            f"{unmatched}"
        )


def build_catalog_key_expr(isrc_col: str, video_col: str, title_col: str, artist_col: str) -> pl.Expr:
    return (
        pl.when(pl.col(isrc_col).is_not_null() & (pl.col(isrc_col) != ""))
        .then(pl.concat_str([pl.lit("ISRC:"), pl.col(isrc_col)]))
        .when(pl.col(video_col).is_not_null() & (pl.col(video_col) != ""))
        .then(pl.concat_str([pl.lit("VIDEO:"), pl.col(video_col)]))
        .otherwise(pl.concat_str([pl.lit("TEXT:"), pl.col(title_col), pl.lit("|"), pl.col(artist_col)]))
    )


def standardized_identity_frame(path: Path) -> pl.LazyFrame | None:
    if not path.exists():
        return None

    lf = pl.scan_parquet(path)
    schema = set(lf.collect_schema().names())

    source = coalesce_text(schema, ["source"])
    account = coalesce_text(schema, ["account"])
    source_sheet = coalesce_text(schema, ["source_sheet"])
    isrc_raw = coalesce_text(schema, ["asset_isrc", "ISRC", "Asset ISRC", "YouTube Asset ISRC"])
    upc_raw = coalesce_text(schema, [
        "product_upc",
        "UPC",
        "Product UPC",
        "DISPLAY UPC",
        "Display UPC",
        "MANUFACTURER UPC",
        "UPC Code",
    ])
    direct_video_raw = coalesce_text(schema, [
        "video_id",
        "Video ID",
        "VideoId",
        "YOUTUBE VIDEO ID",
        "YouTube Video ID",
        "YouTube Asset ID",
    ])
    onerpm_share_video_id = (
        pl.when(
            (source == "onerpm")
            & (source_sheet == "Shares In & Out")
            & clean_video_id_expr(coalesce_text(schema, ["ID"])).is_not_null()
        )
        .then(clean_video_id_expr(coalesce_text(schema, ["ID"])))
        .otherwise(pl.lit(None).cast(pl.Utf8))
    )
    channel_raw = coalesce_text(schema, ["channel_id", "Channel ID", "ChannelId", "Parent ID"])
    track_id_raw = coalesce_text(schema, ["track_id", "label_track_id", "Label Track ID", "Track ID"])
    title = coalesce_text(schema, [
        "track_statement_style",
        "asset_title_statement",
        "Track Title",
        "Title",
        "Video Title",
        "Product Title",
        "Album Title",
        "YouTube Video Title",
    ])
    artist = coalesce_text(schema, [
        "artist_statement_style",
        "asset_artist_statement",
        "artist_best_available",
        "Artists",
        "Track Artists",
        "Product Artist",
        "Channel Name",
    ])
    transaction_month = coalesce_text(schema, ["transaction_month"])
    amount = amount_expr(schema)

    return (
        lf
        .with_columns([
            source.alias("source"),
            account.alias("account"),
            source_sheet.alias("source_sheet"),
            valid_isrc_expr(isrc_raw).alias("identity_isrc"),
            clean_upc_expr(upc_raw).alias("identity_upc"),
            pl.coalesce([clean_video_id_expr(direct_video_raw), onerpm_share_video_id]).alias("identity_video_id"),
            valid_youtube_channel_id_expr(channel_raw).alias("identity_channel_id"),
            clean_identifier(track_id_raw).alias("identity_track_id"),
            title.alias("identity_title"),
            artist.alias("identity_artist"),
            transaction_month.alias("transaction_month"),
            amount.alias("identity_amount_usd"),
        ])
        .with_columns([
            normalized_text(pl.col("identity_title")).alias("_title_norm"),
            normalized_text(pl.col("identity_artist")).alias("_artist_norm"),
        ])
        .select([
            "source",
            "account",
            "source_sheet",
            "identity_isrc",
            "identity_upc",
            "identity_video_id",
            "identity_channel_id",
            "identity_track_id",
            "identity_title",
            "identity_artist",
            "transaction_month",
            "identity_amount_usd",
            "_title_norm",
            "_artist_norm",
        ])
    )


def identity_frames() -> list[pl.LazyFrame]:
    return [frame for path in STANDARDIZED_PATHS if (frame := standardized_identity_frame(path)) is not None]


def identity_with_canonical_key() -> pl.LazyFrame | None:
    frames = [frame for path in STANDARDIZED_PATHS if (frame := standardized_identity_frame(path)) is not None]
    if not frames:
        return None

    all_identity = pl.concat(frames, how="diagonal_relaxed")
    upc_isrc_map = (
        all_identity
        .filter(pl.col("identity_upc").is_not_null() & pl.col("identity_isrc").is_not_null())
        .group_by("identity_upc")
        .agg(pl.col("identity_isrc").drop_nulls().unique().alias("_isrcs_for_upc"))
        .filter(pl.col("_isrcs_for_upc").list.len() == 1)
        .select([
            "identity_upc",
            pl.col("_isrcs_for_upc").list.first().alias("_mapped_isrc"),
        ])
    )

    return (
        all_identity
        .join(upc_isrc_map, on="identity_upc", how="left")
        .with_columns(
            pl.coalesce(["identity_isrc", "_mapped_isrc"]).alias("effective_isrc")
        )
        .with_columns(
            build_catalog_key_expr("effective_isrc", "identity_video_id", "_title_norm", "_artist_norm")
            .alias("catalog_key")
        )
        .filter(pl.col("catalog_key").is_not_null() & (pl.col("catalog_key") != "TEXT:|"))
    )


def build_identity_alias_lookup() -> pl.DataFrame:
    identity = identity_with_canonical_key()
    if identity is None:
        return pl.DataFrame({
            "alias_catalog_key": pl.Series([], dtype=pl.Utf8),
            "canonical_catalog_key": pl.Series([], dtype=pl.Utf8),
        })

    text_aliases = (
        identity
        .filter(
            pl.col("effective_isrc").is_not_null()
            & (pl.col("_title_norm") != "")
            & (pl.col("_artist_norm") != "")
        )
        .with_columns([
            pl.concat_str([pl.lit("TEXT:"), pl.col("_title_norm"), pl.lit("|"), pl.col("_artist_norm")]).alias("alias_catalog_key"),
            pl.concat_str([pl.lit("ISRC:"), pl.col("effective_isrc")]).alias("canonical_catalog_key"),
        ])
        .select(["alias_catalog_key", "canonical_catalog_key"])
    )

    upc_aliases = (
        identity
        .filter(pl.col("effective_isrc").is_not_null() & pl.col("identity_upc").is_not_null())
        .with_columns([
            pl.concat_str([pl.lit("UPC:"), pl.col("identity_upc")]).alias("alias_catalog_key"),
            pl.concat_str([pl.lit("ISRC:"), pl.col("effective_isrc")]).alias("canonical_catalog_key"),
        ])
        .select(["alias_catalog_key", "canonical_catalog_key"])
    )

    video_aliases = (
        identity
        .filter(pl.col("effective_isrc").is_not_null() & pl.col("identity_video_id").is_not_null())
        .with_columns([
            pl.concat_str([pl.lit("VIDEO:"), pl.col("identity_video_id")]).alias("alias_catalog_key"),
            pl.concat_str([pl.lit("ISRC:"), pl.col("effective_isrc")]).alias("canonical_catalog_key"),
        ])
        .select(["alias_catalog_key", "canonical_catalog_key"])
    )

    return (
        pl.concat([text_aliases, upc_aliases, video_aliases], how="diagonal_relaxed")
        .group_by("alias_catalog_key")
        .agg(pl.col("canonical_catalog_key").unique().alias("_canonical_keys"))
        .filter(pl.col("_canonical_keys").list.len() == 1)
        .select([
            "alias_catalog_key",
            pl.col("_canonical_keys").list.first().alias("canonical_catalog_key"),
        ])
        .collect()
    )


def build_identity_lookup() -> pl.DataFrame:
    identity = identity_with_canonical_key()
    if identity is None:
        return pl.DataFrame({"catalog_key": pl.Series([], dtype=pl.Utf8)})

    return (
        identity
        .group_by("catalog_key")
        .agg([
            first_mode_expr("effective_isrc").alias("identity_asset_isrc"),
            first_mode_expr("identity_upc").alias("primary_upc"),
            first_mode_expr("identity_video_id").alias("identity_video_id"),
            first_mode_expr("identity_track_id").alias("identity_track_id"),
            first_mode_expr("identity_title").alias("identity_track_title"),
            first_mode_expr("identity_artist").alias("identity_artist_statement"),
            pl.min("transaction_month").alias("identity_first_transaction_month"),
            pl.max("transaction_month").alias("identity_last_transaction_month"),
            pl.sum("identity_amount_usd").round(6).alias("identity_amount_usd"),
            pl.len().alias("identity_rows"),
            list_join_expr("effective_isrc").alias("isrcs"),
            list_join_expr("identity_upc").alias("upcs"),
            list_join_expr("identity_video_id").alias("video_ids"),
            list_join_expr("identity_channel_id").alias("channel_ids"),
            list_join_expr("identity_track_id").alias("track_ids"),
            list_join_expr("source").alias("identity_sources"),
            list_join_expr("account").alias("identity_accounts"),
            list_join_expr("source_sheet").alias("identity_source_sheets"),
            list_join_expr("identity_title").alias("identity_title_variants"),
            list_join_expr("identity_artist").alias("identity_artist_variants"),
        ])
        .collect()
    )


def build_release_lookup() -> pl.DataFrame:
    if not RELEASE_METADATA_PATH.exists():
        return pl.DataFrame({
            "catalog_key": pl.Series([], dtype=pl.Utf8),
            "external_release_date": pl.Series([], dtype=pl.Utf8),
            "external_release_year_month": pl.Series([], dtype=pl.Utf8),
            "external_match_url": pl.Series([], dtype=pl.Utf8),
            "external_label": pl.Series([], dtype=pl.Utf8),
            "external_metadata_status": pl.Series([], dtype=pl.Utf8),
        })

    metadata = pl.read_parquet(RELEASE_METADATA_PATH)
    if metadata.is_empty():
        return pl.DataFrame({
            "catalog_key": pl.Series([], dtype=pl.Utf8),
            "external_release_date": pl.Series([], dtype=pl.Utf8),
            "external_release_year_month": pl.Series([], dtype=pl.Utf8),
            "external_match_url": pl.Series([], dtype=pl.Utf8),
            "external_label": pl.Series([], dtype=pl.Utf8),
            "external_metadata_status": pl.Series([], dtype=pl.Utf8),
        })
    if "external_label" not in metadata.columns:
        metadata = metadata.with_columns(pl.lit(None).cast(pl.Utf8).alias("external_label"))

    by_isrc = (
        metadata
        .filter(pl.col("lookup_isrc").is_not_null() & (pl.col("lookup_isrc") != ""))
        .with_columns(pl.concat_str([pl.lit("ISRC:"), pl.col("lookup_isrc").str.to_uppercase()]).alias("catalog_key"))
        .group_by("catalog_key")
        .agg([
            pl.col("release_date").drop_nulls().min().alias("external_release_date"),
            pl.col("release_year_month").drop_nulls().min().alias("external_release_year_month"),
            pl.col("match_url").drop_nulls().first().alias("external_match_url"),
            pl.col("external_label").drop_nulls().first().alias("external_label"),
            pl.col("metadata_status").drop_nulls().first().alias("external_metadata_status"),
        ])
    )

    by_video = (
        metadata
        .filter(
            (pl.col("lookup_isrc").is_null() | (pl.col("lookup_isrc") == ""))
            & pl.col("lookup_video_id").is_not_null()
            & (pl.col("lookup_video_id") != "")
        )
        .with_columns(pl.concat_str([pl.lit("VIDEO:"), pl.col("lookup_video_id")]).alias("catalog_key"))
        .group_by("catalog_key")
        .agg([
            pl.col("release_date").drop_nulls().min().alias("external_release_date"),
            pl.col("release_year_month").drop_nulls().min().alias("external_release_year_month"),
            pl.col("match_url").drop_nulls().first().alias("external_match_url"),
            pl.col("external_label").drop_nulls().first().alias("external_label"),
            pl.col("metadata_status").drop_nulls().first().alias("external_metadata_status"),
        ])
    )

    by_upc = (
        metadata
        .filter(
            (pl.col("lookup_isrc").is_null() | (pl.col("lookup_isrc") == ""))
            & (pl.col("lookup_video_id").is_null() | (pl.col("lookup_video_id") == ""))
            & pl.col("lookup_upc").is_not_null()
            & (pl.col("lookup_upc") != "")
        )
        .with_columns(pl.concat_str([pl.lit("UPC:"), pl.col("lookup_upc")]).alias("catalog_key"))
        .group_by("catalog_key")
        .agg([
            pl.col("release_date").drop_nulls().min().alias("external_release_date"),
            pl.col("release_year_month").drop_nulls().min().alias("external_release_year_month"),
            pl.col("match_url").drop_nulls().first().alias("external_match_url"),
            pl.col("external_label").drop_nulls().first().alias("external_label"),
            pl.col("metadata_status").drop_nulls().first().alias("external_metadata_status"),
        ])
    )

    return pl.concat([by_isrc, by_video, by_upc], how="diagonal_relaxed").unique("catalog_key")


def build_catalog_master() -> pl.DataFrame:
    if not SONG_LEVEL_PATH.exists():
        raise FileNotFoundError(f"No existe {SONG_LEVEL_PATH}")

    lf = pl.scan_parquet(SONG_LEVEL_PATH)
    schema = set(lf.collect_schema().names())

    source = coalesce_text(schema, ["source"])
    account = coalesce_text(schema, ["account"])
    isrc_raw = coalesce_text(schema, ["asset_isrc", "ISRC"])
    track_id = coalesce_text(schema, ["track_id", "video_id", "label_track_id", "Label Track ID", "Track ID", "Video ID"])
    title = coalesce_text(schema, ["track_statement_style", "asset_title_statement", "Track Title", "Title", "Video Title"])
    artist = coalesce_text(schema, ["artist_statement_style", "asset_artist_statement", "Artists", "Channel Name"])
    content_type = coalesce_text(schema, ["content_type"])
    source_sheet = coalesce_text(schema, ["source_sheet"])
    revenue_basis = coalesce_text(schema, ["revenue_basis"])
    transaction_month = coalesce_text(schema, ["transaction_month"])
    amount = amount_expr(schema)
    units = units_expr(schema)
    identity_alias_lookup = build_identity_alias_lookup()
    policy_rules = load_account_policy_rules()

    prepared = (
        lf
        .with_columns([
            source.alias("source"),
            account.alias("account"),
            valid_isrc_expr(isrc_raw).alias("asset_isrc"),
            clean_video_id_expr(track_id).alias("track_id"),
            title.alias("track_title"),
            artist.alias("artist_statement"),
            content_type.alias("content_type"),
            source_sheet.alias("source_sheet"),
            revenue_basis.alias("revenue_basis"),
            transaction_month.alias("transaction_month"),
            amount.alias("observed_amount_usd"),
            units.alias("units"),
        ])
        .join(policy_rules.lazy(), on=["source", "account", "source_sheet"], how="left")
        .with_columns([
            pl.when(
                (pl.col("policy_catalog_view") == True)
                & pl.col("policy_revenue_basis").is_in(CATALOG_REVENUE_BASIS)
            )
            .then(pl.col("observed_amount_usd"))
            .otherwise(0.0)
            .alias("amount_usd"),
            pl.when(pl.col("policy_revenue_basis") == "transfer")
            .then(pl.col("observed_amount_usd"))
            .otherwise(0.0)
            .alias("transfer_amount_usd"),
            pl.when(pl.col("policy_revenue_basis").is_null())
            .then(pl.col("observed_amount_usd"))
            .otherwise(0.0)
            .alias("policy_unmatched_amount_usd"),
        ])
        .with_columns([
            normalized_text(pl.col("track_title")).alias("_title_norm"),
            normalized_text(pl.col("artist_statement")).alias("_artist_norm"),
        ])
        .with_columns(
            build_catalog_key_expr("asset_isrc", "track_id", "_title_norm", "_artist_norm")
            .alias("catalog_key")
        )
        .filter(pl.col("catalog_key").is_not_null() & (pl.col("catalog_key") != "TEXT:|"))
    )
    assert_policy_coverage(prepared)
    if not identity_alias_lookup.is_empty():
        prepared = (
            prepared
            .join(
                identity_alias_lookup.lazy(),
                left_on="catalog_key",
                right_on="alias_catalog_key",
                how="left",
            )
            .with_columns(
                pl.coalesce(["canonical_catalog_key", "catalog_key"]).alias("catalog_key")
            )
            .drop("canonical_catalog_key", strict=False)
        )

    catalog = (
        prepared
        .group_by("catalog_key")
        .agg([
            first_mode_expr("asset_isrc").alias("asset_isrc"),
            first_mode_expr("track_id").alias("track_id"),
            first_mode_expr("track_title").alias("track_title"),
            first_mode_expr("artist_statement").alias("artist_statement"),
            pl.min("transaction_month").alias("first_transaction_month"),
            pl.max("transaction_month").alias("last_transaction_month"),
            pl.sum("amount_usd").round(6).alias("amount_usd"),
            pl.sum("observed_amount_usd").round(6).alias("observed_amount_usd"),
            pl.sum("transfer_amount_usd").round(6).alias("transfer_amount_usd"),
            pl.sum("policy_unmatched_amount_usd").round(6).alias("policy_unmatched_amount_usd"),
            pl.sum("units").round(6).alias("units"),
            pl.len().alias("song_level_rows"),
            pl.n_unique("source").alias("source_count"),
            pl.n_unique("account").alias("account_count"),
            list_join_expr("source").alias("sources"),
            list_join_expr("account").alias("accounts"),
            list_join_expr("content_type").alias("content_types"),
            list_join_expr("source_sheet").alias("source_sheets"),
            list_join_expr("revenue_basis").alias("revenue_basis_values"),
            list_join_expr("policy_revenue_basis").alias("policy_revenue_basis_values"),
            list_join_expr("track_title").alias("title_variants"),
            list_join_expr("artist_statement").alias("artist_variants"),
        ])
        .with_columns([
            normalized_text(pl.col("track_title")).alias("track_title_normalized"),
            normalized_text(pl.col("artist_statement")).alias("artist_statement_normalized"),
            pl.lit(datetime.now().isoformat(timespec="seconds")).alias("catalog_built_at"),
        ])
        .collect()
    )

    identity_lookup = build_identity_lookup()
    if not identity_lookup.is_empty():
        catalog = (
            catalog
            .join(identity_lookup, on="catalog_key", how="full", coalesce=True)
            .with_columns([
                pl.coalesce(["asset_isrc", "identity_asset_isrc"]).alias("asset_isrc"),
                pl.coalesce(["track_id", "identity_video_id", "identity_track_id"]).alias("track_id"),
                pl.coalesce(["track_title", "identity_track_title"]).alias("track_title"),
                pl.coalesce(["artist_statement", "identity_artist_statement"]).alias("artist_statement"),
                pl.coalesce(["first_transaction_month", "identity_first_transaction_month"]).alias("first_transaction_month"),
                pl.coalesce(["last_transaction_month", "identity_last_transaction_month"]).alias("last_transaction_month"),
                pl.coalesce(["amount_usd", pl.lit(0.0)]).alias("amount_usd"),
                pl.coalesce(["observed_amount_usd", pl.lit(0.0)]).alias("observed_amount_usd"),
                pl.coalesce(["transfer_amount_usd", pl.lit(0.0)]).alias("transfer_amount_usd"),
                pl.coalesce(["policy_unmatched_amount_usd", pl.lit(0.0)]).alias("policy_unmatched_amount_usd"),
                pl.coalesce(["units", pl.lit(0.0)]).alias("units"),
                pl.coalesce(["song_level_rows", pl.lit(0)]).alias("song_level_rows"),
                pl.coalesce(["sources", "identity_sources"]).alias("sources"),
                pl.coalesce(["accounts", "identity_accounts"]).alias("accounts"),
                pl.coalesce(["source_sheets", "identity_source_sheets"]).alias("source_sheets"),
                pl.coalesce(["title_variants", "identity_title_variants"]).alias("title_variants"),
                pl.coalesce(["artist_variants", "identity_artist_variants"]).alias("artist_variants"),
            ])
        )

    release_lookup = build_release_lookup()
    if not release_lookup.is_empty():
        catalog = catalog.join(release_lookup, on="catalog_key", how="left")
        if "upcs" in catalog.columns:
            upc_release_lookup = release_lookup.filter(pl.col("catalog_key").str.starts_with("UPC:"))
            if not upc_release_lookup.is_empty():
                upc_release_lookup = upc_release_lookup.rename({
                    "catalog_key": "_release_upc_key",
                    "external_release_date": "_upc_external_release_date",
                    "external_release_year_month": "_upc_external_release_year_month",
                    "external_match_url": "_upc_external_match_url",
                    "external_label": "_upc_external_label",
                    "external_metadata_status": "_upc_external_metadata_status",
                })
                catalog = (
                    catalog
                    .with_columns(
                        pl.concat_str([pl.lit("UPC:"), pl.col("primary_upc")]).alias("_release_upc_key")
                    )
                    .join(upc_release_lookup, on="_release_upc_key", how="left")
                    .with_columns([
                        pl.coalesce(["external_release_date", "_upc_external_release_date"]).alias("external_release_date"),
                        pl.coalesce(["external_release_year_month", "_upc_external_release_year_month"]).alias("external_release_year_month"),
                        pl.coalesce(["external_match_url", "_upc_external_match_url"]).alias("external_match_url"),
                        pl.coalesce(["external_label", "_upc_external_label"]).alias("external_label"),
                        pl.coalesce(["external_metadata_status", "_upc_external_metadata_status"]).alias("external_metadata_status"),
                    ])
                    .drop([
                        "_release_upc_key",
                        "_upc_external_release_date",
                        "_upc_external_release_year_month",
                        "_upc_external_match_url",
                        "_upc_external_label",
                        "_upc_external_metadata_status",
                    ], strict=False)
                )
    else:
        catalog = catalog.with_columns([
            pl.lit(None).cast(pl.Utf8).alias("external_release_date"),
            pl.lit(None).cast(pl.Utf8).alias("external_release_year_month"),
            pl.lit(None).cast(pl.Utf8).alias("external_match_url"),
            pl.lit(None).cast(pl.Utf8).alias("external_label"),
            pl.lit(None).cast(pl.Utf8).alias("external_metadata_status"),
        ])

    catalog = catalog.with_columns([
        normalized_label_expr(pl.col("external_label")).alias("label_normalized_auto"),
    ]).with_columns([
        pl.coalesce(["label_normalized_auto", "external_label"]).alias("label_normalized"),
    ])

    return catalog.sort("amount_usd", descending=True)


def main() -> None:
    MARTS_DIR.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog_master()
    catalog.write_parquet(OUTPUT_PATH)
    print("Catalog master generado")
    print(f"Filas: {catalog.height}")
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
