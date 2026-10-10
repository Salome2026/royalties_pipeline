"""Private guard for ranking slots whose raw-fact identity was normalized differently."""
from __future__ import annotations

from functools import lru_cache
import json
import re

from google.cloud import storage
import polars as pl
import pyarrow.parquet as pq


# Track ISRC is not retained by the producer's needed_columns projection.
_PRODUCER_ISRC = ("asset_isrc", "isrc", "ISRC", "Asset ISRC")
_PRODUCER_VIDEO = (
    "video_id", "Video ID", "VideoId", "YOUTUBE VIDEO ID", "YouTube Video ID",
    "YouTube Asset ID", "ID", "Parent ID", "track_id",
)
_FACT_VIDEO = ("video_id", "Video ID", "VideoId")
_FACT_TRACK = ("track_id", "Label Track ID", "Track ID", "gpid")
_ADA_TRACK = ("source_asset_id", "catalog_number")
_PRODUCER_UPC = ("upc", "UPC", "Product UPC", "Release UPC")
_FACT_UPC = ("product_upc", "UPC Code", "UPC")
_PRODUCER_SHEET = ("source_sheet", "sheet_name", "Sheet", "SHEET")
_IDENTITY_COLUMNS = frozenset((
    "source", "account", "statement_period", *_PRODUCER_ISRC, *_PRODUCER_VIDEO,
    *_FACT_TRACK, *_ADA_TRACK, *_PRODUCER_UPC, *_FACT_UPC, *_PRODUCER_SHEET,
))


def _text(columns: set[str], names: tuple[str, ...]) -> pl.Expr:
    values = [pl.col(name).cast(pl.String, strict=False).str.strip_chars().replace("", None)
              for name in names if name in columns]
    return pl.coalesce(values) if values else pl.lit(None, dtype=pl.String)


def _unsafe_slots(frame: pl.DataFrame) -> list[tuple]:
    columns = set(frame.columns)
    frame = frame.filter(_text(columns, _PRODUCER_ISRC).is_null())
    fact_track = pl.when(_text(columns, ("source",)) == "ada").then(
        _text(columns, _ADA_TRACK)).otherwise(_text(columns, _FACT_TRACK))
    normalized = frame.select(
        _text(columns, ("source",)).fill_null("").alias("source"),
        _text(columns, ("account",)).fill_null("").alias("account"),
        _text(columns, _PRODUCER_SHEET).fill_null("").alias("sheet"),
        _text(columns, ("source_sheet",)).fill_null("").alias("fact_sheet"),
        _text(columns, ("statement_period",)).str.slice(0, 7).str.to_date("%Y-%m", strict=False)
        .dt.strftime("%Y-%m").alias("month"),
        _text(columns, _PRODUCER_ISRC).fill_null("").alias("isrc"),
        _text(columns, _PRODUCER_VIDEO).fill_null("").alias("slot"),
        pl.coalesce(_text(columns, _FACT_VIDEO), fact_track).fill_null("").alias("fact_slot"),
        _text(columns, _PRODUCER_UPC).fill_null("").alias("upc"),
        _text(columns, _FACT_UPC).fill_null("").alias("fact_upc"),
    ).filter(
        (pl.col("source") != "") & (pl.col("account") != "")
        & pl.col("month").is_not_null() & (pl.col("isrc") == "")
    )
    sheet_mismatch = pl.col("sheet") != pl.col("fact_sheet")
    unsafe = normalized.filter(
        ((pl.col("slot") != "") & ((pl.col("slot") != pl.col("fact_slot")) | sheet_mismatch))
        | ((pl.col("slot") == "") & (pl.col("upc") != "")
           & ((pl.col("fact_slot") != "") | (pl.col("upc") != pl.col("fact_upc")) | sheet_mismatch))
    ).select(
        "source", "account", "sheet", "month",
        pl.when(pl.col("slot") != "").then(pl.lit("ID")).otherwise(pl.lit("UPC")).alias("kind"),
        pl.when(pl.col("slot") != "").then(pl.col("slot").str.to_lowercase().str.split(" ").list.first())
        .otherwise(pl.col("upc")).alias("code"),
    ).unique()
    return unsafe.rows()


def _needs_guard_indices(frame: pl.DataFrame) -> list[int]:
    columns = set(frame.columns)
    return frame.with_row_index("_row").filter(
        _text(columns, _PRODUCER_ISRC).is_null()
        & (_text(columns, _FACT_VIDEO).is_null()
           | (_text(columns, _PRODUCER_SHEET).fill_null("")
              != _text(columns, ("source_sheet",)).fill_null("")))
    ).get_column("_row").to_list()


def _all_native(group, columns: list[str], name: str, pattern: str) -> bool:
    if name not in columns:
        return False
    stats = group.column(columns.index(name)).statistics
    return bool(stats is not None and stats.null_count == 0 and stats.has_min_max
                and isinstance(stats.min, str) and isinstance(stats.max, str)
                and re.fullmatch(pattern, stats.min) and re.fullmatch(pattern, stats.max))


def _native_id_layout(group, columns: list[str]) -> bool:
    if "source" not in columns:
        return False
    source = group.column(columns.index("source")).statistics
    if source is None or not source.has_min_max or not all(
        isinstance(value, str) and re.fullmatch(r"[A-Za-z_]+", value) for value in (source.min, source.max)
    ) or source.min < "adb":
        return False
    # Outside ADA, native track_id has identical precedence. Only legacy video
    # aliases or sheet aliases can override the fact identity in an ID slot.
    for name in (*_PRODUCER_VIDEO[3:-1], *_PRODUCER_SHEET[1:]):
        if name in columns:
            stats = group.column(columns.index(name)).statistics
            if stats is None or stats.null_count != group.num_rows:
                return False
    return True


@lru_cache(maxsize=2)
def unsafe_ranking_slot_keys(bucket_name: str, object_name: str, generation: int, *, include_upc: bool = True) -> frozenset[str]:
    """Read a pinned raw object's identities only; read failures propagate, never mean safe."""
    if not bucket_name or not object_name or not isinstance(generation, int) or generation <= 0:
        raise ValueError("A bucket, object and positive pinned generation are required.")
    blob = storage.Client().bucket(bucket_name).blob(object_name, generation=generation)
    keys: set[str] = set()
    with blob.open("rb", chunk_size=64 * 1024) as stream:
        parquet = pq.ParquetFile(stream)
        columns = set(parquet.schema_arrow.names)
        if not {"source", "account", "statement_period"}.issubset(columns) or not (
            columns & set((*_PRODUCER_VIDEO, *_PRODUCER_UPC))
        ):
            return frozenset()
        probe_columns = sorted(columns & set((*_PRODUCER_ISRC, *_FACT_VIDEO, *_PRODUCER_SHEET)))
        if not probe_columns:
            probe_columns = ["source"]
        remaining = sorted((columns & _IDENTITY_COLUMNS) - set(probe_columns))
        for number in range(parquet.metadata.num_row_groups):
            group = parquet.metadata.row_group(number)
            paths = [group.column(index).path_in_schema for index in range(group.num_columns)]
            if not include_upc and _native_id_layout(group, paths):
                continue
            if _all_native(group, paths, "asset_isrc", r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}"):
                continue
            if not (columns & set(_PRODUCER_SHEET[1:])) and _all_native(
                group, paths, "video_id", r"[A-Za-z0-9_-]{11}"):
                continue
            # Most rows have a primary ISRC or native video ID. Inspect only those
            # that can exercise different fallback precedence in the two producers.
            probe = parquet.read_row_group(number, columns=probe_columns)
            indices = _needs_guard_indices(pl.from_arrow(probe))
            if not indices:
                continue
            frame = pl.from_arrow(probe.take(indices))
            if remaining:
                extra = parquet.read_row_group(number, columns=remaining).take(indices)
                frame = frame.hstack(pl.from_arrow(extra))
            for start in range(0, frame.height, 65536):
                keys.update(json.dumps(list(row), separators=(",", ":"))
                            for row in _unsafe_slots(frame.slice(start, 65536)))
    return frozenset(keys)
