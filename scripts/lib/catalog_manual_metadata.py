from __future__ import annotations

import json
import re
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


def materialize_confirmed_references(catalog: pl.DataFrame, *, corrections_path: Path = CORRECTIONS_PATH) -> pl.DataFrame:
    """Keep owner-confirmed external recordings without inventing their revenue."""
    document = json.loads(corrections_path.read_text(encoding="utf-8"))
    if document.get("version") != 1:
        raise ValueError("Unsupported manual catalog metadata version.")
    refs = document.get("recording_references", [])
    if not refs:
        return catalog
    for name, dtype in {
        "catalog_artists": pl.List(pl.String), "catalog_artist_statement": pl.String,
        "catalog_artist_evidence": pl.String, "catalog_artist_rule": pl.String,
        "catalog_identity_rule": pl.String, "catalog_identity_evidence": pl.String,
        "catalog_identity_reference_only": pl.Boolean,
    }.items():
        if name not in catalog.columns:
            catalog = catalog.with_columns(pl.lit(None, dtype=dtype).alias(name))
    seen = set()
    present = set(catalog["asset_isrc"].drop_nulls())
    additions = []
    zeros = {"amount_usd", "observed_amount_usd", "transfer_amount_usd", "policy_unmatched_amount_usd",
             "units", "song_level_rows", "source_count", "account_count", "identity_amount_usd", "identity_rows"}
    for reference in refs:
        code = reference.get("isrc", "")
        if code in seen or not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}", code) or not reference.get("confirmed_by"):
            raise ValueError("An external recording reference requires a unique ISRC and owner confirmation.")
        seen.add(code)
        if code in present:
            continue
        artists = reference.get("artists")
        if not artists or not all(isinstance(a, str) and a.strip() for a in artists):
            raise ValueError("External reference artists must be explicitly confirmed.")
        row = {name: (0 if name in zeros else None) for name in catalog.columns}
        title, artist = reference["title"], " / ".join(artists)
        values = dict(catalog_key="ISRC:" + code, asset_isrc=code, track_title=title, artist_statement=artist,
                      track_title_normalized=" ".join(title.casefold().split()), artist_statement_normalized=" ".join(artist.casefold().split()),
                      catalog_artists=artists, catalog_artist_statement=artist, isrcs=code,
                      catalog_artist_evidence=json.dumps([{"source": "manual", "field": "confirmed_external_recording", **reference}]),
                      catalog_artist_rule="CONFIRMED-EXTERNAL-REFERENCE-1", catalog_identity_rule="CONFIRMED-EXTERNAL-REFERENCE-1",
                      catalog_identity_reference_only=True, catalog_identity_evidence=json.dumps(reference),
                      catalog_aliases=[], video_isrcs=[], catalog_identity_upcs=[],
                      external_match_url=reference.get("match_url"), external_metadata_status="manually_confirmed_external_reference")
        row.update({k: v for k, v in values.items() if k in row})
        additions.append(row)
    if not additions:
        return catalog
    result = pl.concat([catalog, pl.DataFrame(additions, schema=catalog.schema)], how="vertical")
    if result["catalog_key"].n_unique() != result.height:
        raise ValueError("Conflicting external recording reference key.")
    return result


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
