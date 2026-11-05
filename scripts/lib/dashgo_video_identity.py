"""Derived video grouping from complete DashGo evidence, independent of contracts.

Native IDs and economic rows stay unchanged. A full title is usable only within
its source account and native channel, with one observed native video and a
code-free counterpart. Presentation/version words remain in the matching key.
"""
from __future__ import annotations

import polars as pl

from .identity import optional_text_expr
from .video_context import native_video_exprs, native_channel_expr


SUMMARY_VIDEO = "_summary_video_id"
SUMMARY_TITLE = "_summary_video_title"
KEYS = ["_dg_account", "_dg_channel", "_dg_title"]
SCHEMA = {**{name: pl.String for name in KEYS}, "_dg_video": pl.String}


def _text(columns, *names):
    values = [optional_text_expr(columns, name) for name in names if name in columns]
    return pl.coalesce(values) if values else pl.lit(None, dtype=pl.String)


def _context(columns):
    title = _text(columns, "Track Title", "track_statement_style", "asset_title_statement")
    return [
        _text(columns, "account").alias(KEYS[0]),
        native_channel_expr(columns).alias(KEYS[1]),
        title.str.replace_all(r"\s+", " ").str.strip_chars().alias(KEYS[2]),
    ]


def _complete_title():
    title = pl.col(KEYS[2])
    # The matching key keeps these labels. Removing them here only detects an
    # empty title such as "Artist - (Official Video)"; it never matches versions.
    content = title.str.replace(
        r"(?i)\s*[\(\[]\s*(?:official(?: music)? video|video oficial|official audio|audio oficial)\s*[\)\]]\s*$", ""
    ).str.strip_chars()
    return (title.is_not_null() & (title != "")
            & ~title.str.contains(r"(?i)^auto generated asset\b")
            & ~content.str.contains(r"[-|–—]\s*$")
            & ~content.str.contains(r"(?i)^(?:official(?: music)? video|video oficial|untitled|sin titulo)$"))


def _row_flags(columns):
    source = _text(columns, "source") == "dashgo"
    dsp = _text(columns, "dsp_normalized")
    store = _text(columns, "store_name", "Store", "store")
    youtube = pl.coalesce([
        dsp.str.to_lowercase() == "youtube",
        store.str.to_lowercase().str.starts_with("youtube"),
    ]).fill_null(False)
    isrc = _text(columns, "asset_isrc", "ISRC", "Asset ISRC")
    upc = _text(columns, "product_upc", "UPC", "Product UPC")
    track = _text(columns, "track_id", "label_track_id", "Label Track ID")
    reported_video = _text(columns, "video_id", "VideoId", "Video ID")
    label_track = _text(columns, "label_track_id", "Label Track ID")
    video, _ = native_video_exprs(columns)
    no_recording_or_product = isrc.is_null() & upc.is_null()
    uncoded = no_recording_or_product & reported_video.is_null() & track.is_null()
    native = no_recording_or_product & video.is_not_null() & label_track.is_null() & (track.is_null() | (track == video))
    return source & youtube, video, uncoded, native


def compile_video_groups(evidence: pl.LazyFrame) -> pl.DataFrame:
    """Use full pinned history, before keyword, period or monetization filters."""
    columns = set(evidence.collect_schema().names())
    if "source" not in columns or "account" not in columns:
        return pl.DataFrame(schema=SCHEMA)
    scope, video, uncoded, native = _row_flags(columns)
    facts = evidence.filter(_text(columns, "source") == "dashgo").select(
        *_context(columns), video.alias("_dg_video"),
        (scope & uncoded).alias("_dg_uncoded"), (scope & native).alias("_dg_native"),
    ).filter(
        pl.col(KEYS[0]).is_not_null() & pl.col(KEYS[1]).is_not_null() & _complete_title()
    )
    # Inspect every native video at this context, including identified recordings:
    # a second ID vetoes the proposed relationship. Never use contract ownership.
    return facts.group_by(KEYS).agg(
        pl.col("_dg_video").drop_nulls().n_unique().alias("_dg_count"),
        pl.col("_dg_video").drop_nulls().first(),
        pl.col("_dg_uncoded").any(), pl.col("_dg_native").any(),
    ).filter(
        (pl.col("_dg_count") == 1) & pl.col("_dg_uncoded") & pl.col("_dg_native")
    ).select(list(SCHEMA)).collect(engine="streaming").sort(KEYS)


def with_video_groups(frame: pl.LazyFrame, groups: pl.DataFrame) -> pl.LazyFrame:
    """Add only a summary key; preserve raw identity, measures and dimensions."""
    if groups.is_empty():
        return frame
    columns = set(frame.collect_schema().names())
    scope, video, uncoded, native = _row_flags(columns)
    eligible = scope & pl.col("_dg_video").is_not_null() & (uncoded | (native & (video == pl.col("_dg_video"))))
    result = frame.with_columns(*_context(columns)).join(
        groups.lazy(), on=KEYS, how="left", validate="m:1", maintain_order="left",
    ).with_columns(
        pl.when(eligible).then(pl.col("_dg_video"))
        .otherwise(pl.lit(None, dtype=pl.String)).alias(SUMMARY_VIDEO),
        pl.when(eligible).then(pl.col("_dg_title"))
        .otherwise(pl.lit(None, dtype=pl.String)).alias(SUMMARY_TITLE),
    )
    return result.drop(*KEYS, "_dg_video")
