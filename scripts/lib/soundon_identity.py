from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import polars as pl


REFERENCE_PATH = Path(__file__).resolve().parents[2] / "warehouse/registry/soundon_isrc_references.json"
ISRC_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")


def artist_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return " ".join("".join(c for c in value if not unicodedata.combining(c)).casefold().split())


def credit_parts(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def add_consumption_dates(frame: pl.DataFrame) -> pl.DataFrame:
    period = pl.col("Sales Period").cast(pl.Utf8).str.strip_chars()
    frame = frame.with_columns(
        period.str.extract(r"^(\d{4}-\d{2}-\d{2})~\d{4}-\d{2}-\d{2}$", 1)
        .str.to_date("%Y-%m-%d", strict=False).alias("_sale_start"),
        period.str.extract(r"^\d{4}-\d{2}-\d{2}~(\d{4}-\d{2}-\d{2})$", 1)
        .str.to_date("%Y-%m-%d", strict=False).alias("_sale_end"),
    )
    invalid = frame.filter(
        pl.col("_sale_start").is_null() | pl.col("_sale_end").is_null()
        | (pl.col("_sale_start") > pl.col("_sale_end"))
        | (pl.col("_sale_start").dt.strftime("%Y-%m") != pl.col("_sale_end").dt.strftime("%Y-%m"))
    )
    if invalid.height:
        raise ValueError(f"SoundOn: {invalid.height} filas con Sales Period invalido o de varios meses; no se infiere el consumo.")
    return frame.with_columns(
        pl.col("_sale_start").dt.strftime("%Y-%m-%d").alias("sale_start_date"),
        pl.col("_sale_end").dt.strftime("%Y-%m-%d").alias("sale_end_date"),
        pl.col("_sale_start").dt.strftime("%Y-%m").alias("transaction_month"),
    ).drop("_sale_start", "_sale_end")


def add_artist_reference(frame: pl.DataFrame, reference_path: Path = REFERENCE_PATH) -> pl.DataFrame:
    document = json.loads(reference_path.read_text(encoding="utf-8"))
    if document.get("version") != 1:
        raise ValueError("Version de referencias ISRC de SoundOn no soportada.")
    references = document["entries"]
    for isrc, reference in references.items():
        names = reference.get("artists") or []
        if not ISRC_PATTERN.fullmatch(isrc) or not names or any(not isinstance(name, str) or not name.strip() for name in names) or len(set(map(artist_key, names))) != len(names) or not reference.get("evidence"):
            raise ValueError(f"Referencia ISRC de SoundOn invalida: {isrc}")
    evidence = []
    for group in frame.select("asset_isrc", "Track Artists").unique().partition_by("asset_isrc"):
        isrc = group["asset_isrc"][0]
        credits = sorted(group["Track Artists"].drop_nulls().to_list())
        parts = [credit_parts(credit) for credit in credits]
        sets = {frozenset(map(artist_key, names)) for names in parts}
        reference = references.get(isrc)
        resolved = None
        status = "as_reported"
        location = None
        if reference:
            reference_parts = reference["artists"]
            expected = frozenset(map(artist_key, reference_parts))
            if sets == {expected}:
                resolved = ",".join(reference_parts)
                status = "verified_isrc_reference"
                location = reference["evidence"]
            else:
                status = "conflicting_participants"
        elif len(sets) > 1:
            status = "conflicting_participants"
        elif len({artist_key(names[0]) for names in parts if names}) > 1:
            status = "principal_unresolved"
        evidence.append({"asset_isrc": isrc, "artist_catalog_style": resolved,
                         "soundon_artist_credit_status": status,
                         "soundon_artist_credit_reference": location})
    derived = ["artist_catalog_style", "soundon_artist_credit_status", "soundon_artist_credit_reference"]
    if not evidence:
        return frame.with_columns([pl.lit(None, dtype=pl.Utf8).alias(name) for name in derived])
    table = pl.DataFrame(evidence, schema={"asset_isrc": pl.Utf8, **dict.fromkeys(derived, pl.Utf8)})
    return frame.drop([name for name in derived if name in frame.columns]).join(table, on="asset_isrc", how="left").with_columns(
        pl.col("Track Artists").alias("artist_statement_original"),
    )
