"""Keep native video identity and quantities independently of catalog identity."""
from __future__ import annotations

import polars as pl

from .identity import optional_text_expr, valid_youtube_video_id_expr, valid_youtube_channel_id_expr
from .store_taxonomy import add_store_dimensions

VIDEO_DIMENSIONS = [
    "video_id", "channel_id", "video_id_source", "dsp_normalized",
    "monetization_normalized", "content_origin_normalized", "classification_status",
]


def video_group_keys(keys: list[str]) -> list[str]:
    return list(dict.fromkeys([*keys, *VIDEO_DIMENSIONS]))
_VIDEO_FIELDS = ["video_id", "Video ID", "VideoId", "YOUTUBE VIDEO ID", "YouTube Video ID"]


def native_video_exprs(columns: set[str]) -> tuple[pl.Expr, pl.Expr]:
    source = optional_text_expr(columns, "source").fill_null("").str.to_lowercase()
    sheet = optional_text_expr(columns, "source_sheet").fill_null("").str.to_lowercase()
    candidates = [(valid_youtube_video_id_expr(pl.col(name)), name)
                  for name in _VIDEO_FIELDS if name in columns]
    if "DSP Container ID" in columns:
        candidates.append((pl.when(source == "fuga").then(
            valid_youtube_video_id_expr(pl.col("DSP Container ID"))), "DSP Container ID"))
    for name in ["Product Reference", "product_reference"]:
        if name in columns:
            candidates.append((pl.when(source == "fuga").then(valid_youtube_video_id_expr(
                pl.col(name).cast(pl.String).str.extract(r"^YT-V-([A-Za-z0-9_-]{11})$", 1))), name))
    # Mixed IDs are video identifiers only in the source's explicit video sheets.
    for name in ["ID", "track_id"]:
        if name in columns:
            candidates.append((pl.when((source == "onerpm") & sheet.is_in(
                ["youtube channels", "shares in & out"])).then(
                    valid_youtube_video_id_expr(pl.col(name))), name))
    video = pl.coalesce([expr for expr, _ in candidates]) if candidates else pl.lit(None, dtype=pl.String)
    provenance = pl.lit(None, dtype=pl.String)
    for expr, name in reversed(candidates):
        label = (pl.coalesce([optional_text_expr(columns, "video_id_source"), pl.lit(name)])
                 if name == "video_id" else pl.lit(name))
        provenance = pl.when(expr.is_not_null()).then(label).otherwise(provenance)
    return video, provenance


def native_channel_expr(columns: set[str]) -> pl.Expr:
    expressions = [valid_youtube_channel_id_expr(pl.col(name)) for name in
                   ["channel_id", "Channel ID", "ChannelId", "YOUTUBE CHANNEL ID"] if name in columns]
    return pl.coalesce(expressions) if expressions else pl.lit(None, dtype=pl.String)


def source_units_expr(columns: set[str]) -> pl.Expr:
    def number(name):
        return pl.col(name).cast(pl.Float64, strict=False) if name in columns else pl.lit(None, dtype=pl.Float64)
    source = optional_text_expr(columns, "source")
    reported = (pl.when(source == "onerpm").then(number("Quantity"))
        .when(source == "dashgo").then(number("Units"))
        .when(source == "orchard").then(number("QUANTITY"))
        .when(source == "soundon").then(number("Units of Sold"))
        .when(source.is_in(["ada", "wml"])).then(pl.coalesce([number("Sales"), number("Sale Units")])))
    fallback = pl.coalesce([number("units"), number("streams"), reported])
    kind = pl.coalesce([optional_text_expr(columns, name) for name in ["Asset/Product", "asset_product_type"]])
    fuga_units = pl.when(kind == "Product").then(pl.coalesce([
        number("Product Quantity"), number("product_quantity_num")])).otherwise(pl.coalesce([
        number("Asset Quantity"), number("asset_quantity_num")]))
    return pl.when(source == "fuga").then(
        pl.coalesce([fuga_units, fallback])).otherwise(fallback)


def preserve_video_context(frame: pl.DataFrame | pl.LazyFrame):
    eager = isinstance(frame, pl.DataFrame)
    lf = frame.lazy() if eager else frame
    columns = set(lf.collect_schema().names())
    video, provenance = native_video_exprs(columns)
    lf = lf.with_columns(video.alias("video_id"), provenance.alias("video_id_source"),
                         native_channel_expr(columns).alias("channel_id"), source_units_expr(columns).alias("units"))
    # Existing business dimensions are authoritative; never reinterpret a projection.
    if not {"dsp_normalized", "monetization_normalized", "content_origin_normalized"}.issubset(columns):
        lf = add_store_dimensions(lf, set(lf.collect_schema().names()))
    if "classification_status" not in lf.collect_schema().names():
        lf = lf.with_columns(pl.lit("partial").alias("classification_status"))
    return lf.collect() if eager else lf


def separate_channel_video_expr(columns: set[str]) -> pl.Expr:
    """Only native channel/video revenue gets the report exception, never Art Track/UGC."""
    video, _ = native_video_exprs(columns)
    origin = optional_text_expr(columns, "content_origin_normalized")
    return pl.when((origin == "Video / Channel") & video.is_not_null()).then(
        pl.concat_str([pl.lit("VIDEO:"), video]))
