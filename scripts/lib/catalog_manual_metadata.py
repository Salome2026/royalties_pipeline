from __future__ import annotations

import json
from pathlib import Path

import polars as pl


CORRECTIONS_PATH = Path(__file__).with_suffix(".json")
METADATA_FIELDS = {
    "track_title": pl.String,
    "artist_statement": pl.String,
    "catalog_duration_seconds": pl.Int64,
}
AUDIT_FIELDS = {
    "catalog_manual_correction_id": "id",
    "catalog_manual_correction_reason": "reason",
    "catalog_manual_correction_confirmed_by": "confirmed_by",
    "catalog_manual_correction_confirmed_on": "confirmed_on",
}


def apply_catalog_manual_metadata(
    catalog: pl.DataFrame, *, corrections_path: Path = CORRECTIONS_PATH
) -> pl.DataFrame:
    document = json.loads(corrections_path.read_text(encoding="utf-8"))
    if document.get("version") != 1:
        raise ValueError("Unsupported manual catalog metadata version.")
    corrections = document["corrections"]
    keys = [row["catalog_key"] for row in corrections]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate manual catalog metadata correction.")

    result = catalog
    for correction in corrections:
        key = correction["catalog_key"]
        if not key.startswith("ISRC:") or not correction.get("confirmed_by"):
            raise ValueError("A manual catalog correction requires an ISRC and confirmation.")
        match = pl.col("catalog_key") == key
        if not result.select(match.any()).item():
            continue
        updates = []
        # Only display metadata can change; identity, evidence and money stay intact.
        for field, dtype in METADATA_FIELDS.items():
            if field in correction:
                previous = pl.col(field) if field in result.columns else pl.lit(None, dtype=dtype)
                updates.append(
                    pl.when(match).then(pl.lit(correction[field], dtype=dtype))
                    .otherwise(previous).alias(field)
                )
        for field, source_field in AUDIT_FIELDS.items():
            previous = pl.col(field) if field in result.columns else pl.lit(None, dtype=pl.String)
            updates.append(
                pl.when(match).then(pl.lit(correction[source_field]))
                .otherwise(previous).alias(field)
            )
        result = result.with_columns(updates)
        normalized = []
        for field in ("track_title", "artist_statement"):
            target = f"{field}_normalized"
            if field in correction and target in result.columns:
                normalized.append(
                    pl.when(match).then(
                        pl.col(field).str.to_lowercase().str.replace_all(r"\s+", " ").str.strip_chars()
                    ).otherwise(pl.col(target)).alias(target)
                )
        if normalized:
            result = result.with_columns(normalized)
    return result
