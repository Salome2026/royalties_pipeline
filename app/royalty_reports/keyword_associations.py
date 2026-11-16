"""Expand exact ISRC search terms using the report's frozen contract decisions."""

from contextlib import contextmanager
from contextvars import ContextVar
import json
import re

import polars as pl

from app.contract_text_reference import ARTIST_FIELDS, TITLE_FIELDS


ISRC_PATTERN = re.compile(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}")
ASSOCIATED_ISRC = "_report_associated_isrc"
CURRENT = ContextVar("report_keyword_associations", default=None)
CODE_FIELDS = {
    "VIDEO": ("video_id", "Video ID", "VideoId"),
    "TRACK": ("track_id", "Label Track ID", "Track ID", "gpid", "source_asset_id", "catalog_number"),
    "UPC": ("product_upc", "UPC Code", "UPC"),
}
REFERENCE_FIELDS = {
    "source": ("source",),
    "account": ("account",),
    "asset_isrc": ("asset_isrc", "isrc", "ISRC", "Asset ISRC"),
    "product_upc": CODE_FIELDS["UPC"],
    "video_id": CODE_FIELDS["VIDEO"],
    "track_id": CODE_FIELDS["TRACK"][:4],
    "catalog_number": ("catalog_number",),
    "source_sheet": ("source_sheet",),
    "channel_id": ("channel_id", "Channel ID", "ChannelId", "YOUTUBE CHANNEL ID"),
    "title": TITLE_FIELDS,
    "artist": ARTIST_FIELDS,
    "product_type": ("product_type", "asset_product_type"),
    "content_type": ("content_type",),
}


def exact_isrc(keyword: str) -> str | None:
    value = keyword.strip().upper()
    return value if ISRC_PATTERN.fullmatch(value) else None


def candidate_keys(index: dict | None, keywords) -> list[list[str]]:
    if index is None:
        return []
    roots = {root for keyword in keywords if (root := exact_isrc(keyword))}
    return [json.loads(key) for key, targets in sorted(index["included"].items())
            if roots.intersection(targets)]


def report_index(manifest: dict, enabled: bool, keywords) -> dict | None:
    if not enabled:
        return None
    from app.royalty_reports.excel_contracts import require_snapshot

    snapshot = require_snapshot(manifest.get("excel_contract_snapshot"))
    if snapshot["release_id"] != manifest.get("release_id"):
        raise ValueError("Los asociados y los ingresos del Excel deben tener la misma versión publicada.")
    index = snapshot["associations"]
    return index if candidate_keys(index, keywords) else None


@contextmanager
def use_keyword_associations(index):
    token = CURRENT.set(index)
    try:
        yield
    finally:
        CURRENT.reset(token)


def _text(columns, names):
    values = [pl.col(name).cast(pl.String, strict=False).str.strip_chars().replace("", None)
              for name in names if name in columns]
    return pl.coalesce(values) if values else pl.lit(None, dtype=pl.String)


def reference_expressions(columns: set[str]) -> dict[str, pl.Expr]:
    """Read the same native identifiers and context used by the Excel split."""
    expressions = {field: _text(columns, names) for field, names in REFERENCE_FIELDS.items()}
    expressions["track_id"] = (
        pl.when(expressions["source"] == "ada").then(_text(columns, ("source_asset_id", "catalog_number")))
        .otherwise(expressions["track_id"])
    )
    for field in ("_income_product_pending", "_income_upc_pending"):
        expressions[field] = (
            pl.col(field).cast(pl.Boolean, strict=False).fill_null(False) if field in columns else pl.lit(False)
        )
    return expressions


def with_keyword_associations(frame: pl.LazyFrame, keywords) -> pl.LazyFrame:
    index = CURRENT.get()
    if index is None:
        return frame
    columns = set(frame.collect_schema().names())
    if ASSOCIATED_ISRC in columns:
        return frame

    keys = candidate_keys(index, keywords)
    if not keys or not {"source", "account"}.issubset(columns):
        return frame.with_columns(pl.lit(None, dtype=pl.String).alias(ASSOCIATED_ISRC))
    from app.master_contract_income import associated_income_isrc

    pairs = sorted({(source, account) for _, _, source, account in keys})
    fields = reference_expressions(columns)
    prefix = "_report_association_"
    temporary = [prefix + field for field in fields]
    source, account = fields["source"], fields["account"]
    scope = pl.any_horizontal([(source == s) & (account == a) for s, a in pairs])
    annotated = frame.with_columns([expr.alias(prefix + field) for field, expr in fields.items()])

    def resolve(row):
        return associated_income_isrc({field: row[prefix + field] for field in fields}, index)

    lookup = (annotated.filter(scope & fields["asset_isrc"].is_null())
              .select(temporary).unique()
              .with_columns(pl.struct(temporary).map_elements(resolve, return_dtype=pl.String).alias(ASSOCIATED_ISRC))
              .filter(pl.col(ASSOCIATED_ISRC).is_not_null()))
    return annotated.join(lookup, on=temporary, how="left", nulls_equal=True, maintain_order="left").drop(temporary)


def associated_match(columns: set[str], keyword: str) -> pl.Expr:
    root = exact_isrc(keyword) if ASSOCIATED_ISRC in columns else None
    return (pl.col(ASSOCIATED_ISRC) == root).fill_null(False) if root else pl.lit(False)
