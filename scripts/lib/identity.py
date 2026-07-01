from __future__ import annotations

import polars as pl


def clean_text_expr(expr: pl.Expr) -> pl.Expr:
    return expr.cast(pl.Utf8, strict=False).str.strip_chars()


def non_empty_expr(expr: pl.Expr) -> pl.Expr:
    cleaned = clean_text_expr(expr)
    return (
        pl.when(cleaned.is_not_null() & ~cleaned.str.to_uppercase().is_in(["", "NULL", "NAN", "NONE"]))
        .then(cleaned)
        .otherwise(pl.lit(None).cast(pl.Utf8))
    )


def optional_text_expr(schema: set[str], name: str) -> pl.Expr:
    if name not in schema:
        return pl.lit(None).cast(pl.Utf8)
    return non_empty_expr(pl.col(name))


def coalesce_text_expr(schema: set[str], names: list[str]) -> pl.Expr:
    candidates = [optional_text_expr(schema, name) for name in names if name in schema]
    if not candidates:
        return pl.lit(None).cast(pl.Utf8)
    return pl.coalesce(candidates)


def normalized_text_expr(expr: pl.Expr) -> pl.Expr:
    return (
        expr
        .fill_null("")
        .cast(pl.Utf8, strict=False)
        .str.to_lowercase()
        .str.replace_all(r"\s+", " ")
        .str.strip_chars()
    )


def valid_isrc_expr(expr: pl.Expr) -> pl.Expr:
    cleaned = (
        clean_text_expr(expr)
        .str.to_uppercase()
        .str.replace_all(r"[^A-Z0-9]", "")
    )
    return (
        pl.when(cleaned.str.contains(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$"))
        .then(cleaned)
        .otherwise(pl.lit(None).cast(pl.Utf8))
    )


def valid_upc_expr(expr: pl.Expr) -> pl.Expr:
    cleaned = clean_text_expr(expr).str.replace_all(r"[^0-9]", "")
    return (
        pl.when(cleaned.str.len_chars().is_between(8, 14))
        .then(cleaned)
        .otherwise(pl.lit(None).cast(pl.Utf8))
    )


def valid_youtube_video_id_expr(expr: pl.Expr) -> pl.Expr:
    cleaned = clean_text_expr(expr)
    return (
        pl.when(cleaned.str.contains(r"^[A-Za-z0-9_-]{11}$"))
        .then(cleaned)
        .otherwise(pl.lit(None).cast(pl.Utf8))
    )


def valid_youtube_channel_id_expr(expr: pl.Expr) -> pl.Expr:
    cleaned = clean_text_expr(expr)
    return (
        pl.when(cleaned.str.contains(r"^UC[A-Za-z0-9_-]{20,22}$"))
        .then(cleaned)
        .otherwise(pl.lit(None).cast(pl.Utf8))
    )


def first_valid_isrc_expr(schema: set[str], names: list[str]) -> pl.Expr:
    candidates = [valid_isrc_expr(optional_text_expr(schema, name)) for name in names if name in schema]
    if not candidates:
        return pl.lit(None).cast(pl.Utf8)
    return pl.coalesce(candidates)


def first_valid_upc_expr(schema: set[str], names: list[str]) -> pl.Expr:
    candidates = [valid_upc_expr(optional_text_expr(schema, name)) for name in names if name in schema]
    if not candidates:
        return pl.lit(None).cast(pl.Utf8)
    return pl.coalesce(candidates)


def first_valid_youtube_video_id_expr(schema: set[str], names: list[str]) -> pl.Expr:
    candidates = [valid_youtube_video_id_expr(optional_text_expr(schema, name)) for name in names if name in schema]
    if not candidates:
        return pl.lit(None).cast(pl.Utf8)
    return pl.coalesce(candidates)


def first_valid_youtube_channel_id_expr(schema: set[str], names: list[str]) -> pl.Expr:
    candidates = [valid_youtube_channel_id_expr(optional_text_expr(schema, name)) for name in names if name in schema]
    if not candidates:
        return pl.lit(None).cast(pl.Utf8)
    return pl.coalesce(candidates)


def build_catalog_key_expr(isrc_col: str, video_col: str, title_col: str, artist_col: str) -> pl.Expr:
    return (
        pl.when(pl.col(isrc_col).is_not_null() & (pl.col(isrc_col) != ""))
        .then(pl.concat_str([pl.lit("ISRC:"), pl.col(isrc_col)]))
        .when(pl.col(video_col).is_not_null() & (pl.col(video_col) != ""))
        .then(pl.concat_str([pl.lit("VIDEO:"), pl.col(video_col)]))
        .otherwise(pl.concat_str([pl.lit("TEXT:"), pl.col(title_col), pl.lit("|"), pl.col(artist_col)]))
    )
