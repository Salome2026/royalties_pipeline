from __future__ import annotations

import re
import unicodedata

import polars as pl


SEARCH_EQUIVALENT_CHARS = {
    "a": "[aàáâãäå]",
    "c": "[cç]",
    "e": "[eèéêë]",
    "i": "[iìíîï]",
    "n": "[nñ]",
    "o": "[oòóôõö]",
    "u": "[uùúûü]",
    "y": "[yýÿ]",
}


def normalize_search_text(value: object) -> str:
    """Normalize user-facing search text without changing stored business data."""
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip()


def searchable_text_expr(expr: pl.Expr) -> pl.Expr:
    return (
        expr
        .fill_null("")
        .cast(pl.Utf8, strict=False)
        .str.to_lowercase()
        .str.replace_all(r"\s+", " ")
        .str.strip_chars()
    )


def search_regex_pattern(value: object) -> str:
    normalized = normalize_search_text(value)
    return "".join(SEARCH_EQUIVALENT_CHARS.get(char, re.escape(char)) for char in normalized)


def contains_search_expr(expr: pl.Expr, value: object) -> pl.Expr:
    normalized = normalize_search_text(value)
    searchable = searchable_text_expr(expr)
    match = searchable.str.contains(search_regex_pattern(normalized))
    compact = re.sub(r"[\s_-]+", "", normalized)
    if not compact:
        return match
    return match | (
        searchable
        .str.replace_all(r"[\s_-]+", "")
        .str.contains(search_regex_pattern(compact))
    )
