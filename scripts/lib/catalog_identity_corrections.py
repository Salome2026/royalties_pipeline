"""Evidence-scoped recording identity corrections. Never rewrite native statement fields."""
from __future__ import annotations
import json
from pathlib import Path
import re
import polars as pl

REGISTRY = Path(__file__).with_suffix(".json")


def corrections():
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if document.get("version") != 1:
        raise ValueError("Unsupported recording identity registry")
    seen = set()
    for rule in document["corrections"]:
        scope = (rule["source"], rule["account"], rule["reported_isrc"])
        if scope in seen or not rule.get("confirmed_by"):
            raise ValueError("Conflicting or unconfirmed recording identity correction")
        seen.add(scope)
        for column in ("reported_isrc", "canonical_isrc"):
            if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}\d{7}", rule[column]):
                raise ValueError("Invalid ISRC in recording identity correction")
    return document["corrections"]


def text(schema, names):
    columns = [pl.col(name).cast(pl.String).str.strip_chars().replace("", None) for name in names if name in schema]
    return pl.coalesce(columns) if columns else pl.lit(None, dtype=pl.String)


def normalize(value):
    return value.fill_null("").str.to_lowercase().str.replace_all(r"\s+", " ").str.strip_chars()


def correct_recording_identity(frame, *, code_column="asset_isrc", strict=True):
    eager = isinstance(frame, pl.DataFrame)
    lf = frame.lazy() if eager else frame
    schema = set(lf.collect_schema().names())
    if not {"source", "account", code_column} <= schema:
        return frame
    workspace = (pl.col("scope").fill_null("habitual") == "habitual") if "scope" in schema else pl.lit(True)
    if "scope" in schema and lf.filter(workspace).select(pl.len()).collect().item() == 0:
        return frame
    artist = text(schema, ["asset_artist_statement", "Asset Artist", "artist_catalog_style", "artist_statement_style",
        "artist", "artist_statement", "lookup_artist"])
    title = text(schema, ["asset_title_statement", "Asset Title", "track_statement_style", "title", "track_title", "lookup_title"])
    reference = text(schema, ["asset_reference", "Asset Reference"])
    current = pl.col(code_column).cast(pl.String)
    reported = "reported_" + code_column
    if reported not in schema:
        lf = lf.with_columns(current.alias(reported))
    if "catalog_identity_correction" not in schema:
        lf = lf.with_columns(pl.lit(None, dtype=pl.String).alias("catalog_identity_correction"))
    for rule in corrections():
        scope = (pl.col("source") == rule["source"]) & (pl.col("account") == rule["account"])
        scope = scope & workspace
        legacy = current == rule["reported_isrc"]
        native = reference == rule["native_asset_reference"]
        exact_credit = normalize(artist) == rule["artist"].casefold()
        exact_title = normalize(title) == rule["title"].casefold()
        proof = ((native & (exact_credit | artist.is_null())) |
                 (reference.is_null() & exact_credit & exact_title)).fill_null(False)
        matched = (scope & legacy & proof).fill_null(False)
        canonical_proof = ((exact_credit & exact_title) | (native & exact_credit)).fill_null(False)
        canonical_row = (workspace & (current == rule["canonical_isrc"])).fill_null(False)
        if strict:
            unresolved = lf.filter((scope & legacy & ~proof).fill_null(False)).select(pl.len()).collect().item()
            if unresolved:
                raise ValueError(f"Identidad de grabacion sin evidencia suficiente ({rule['id']}): {unresolved} filas. No se reasignan ingresos.")
            unregistered = lf.filter((workspace & legacy & exact_credit & exact_title & ~scope).fill_null(False)).select(pl.len()).collect().item()
            if unregistered:
                raise ValueError(f"La grabacion corregida aparece en una fuente no registrada: {unregistered} filas; revisar la evidencia antes de asociar.")
            contradicted_new = lf.filter(canonical_row & ~canonical_proof).select(pl.len()).collect().item()
            if contradicted_new:
                raise ValueError(f"El nuevo ISRC trae credito o titulo incompatibles con la grabacion confirmada: {contradicted_new} filas; revisar antes de unir.")
        lf = lf.with_columns(
            pl.when(matched).then(pl.lit(rule["canonical_isrc"])).otherwise(current).alias(code_column),
            pl.when(matched | (canonical_row & canonical_proof)).then(pl.lit(rule["id"])).otherwise(pl.col("catalog_identity_correction")).alias("catalog_identity_correction"))
    return lf.collect() if eager else lf


def correct_extended_identity(metadata):
    if not {"principal_asset_isrc", "YouTube Video ID"} <= set(metadata.columns):
        return metadata
    result = metadata
    for rule in corrections():
        proof = pl.col("YouTube Video ID").is_in(rule["video_ids"])
        if "reported_principal_asset_isrc" not in result.columns:
            result = result.with_columns(pl.col("principal_asset_isrc").alias("reported_principal_asset_isrc"))
        result = result.with_columns(pl.when(proof & (pl.col("principal_asset_isrc") == rule["reported_isrc"]))
            .then(pl.lit(rule["canonical_isrc"])).otherwise(pl.col("principal_asset_isrc")).alias("principal_asset_isrc"))
    return result


def correct_release_metadata(metadata):
    required = {"lookup_isrc", "lookup_upc", "lookup_artist", "lookup_title"}
    if not required <= set(metadata.columns):
        return metadata
    result = metadata
    for rule in corrections():
        legacy = pl.col("lookup_isrc") == rule["reported_isrc"]
        recording = (normalize(pl.col("lookup_artist")) == rule["artist"].casefold()) & (
            normalize(pl.col("lookup_title")) == rule["title"].casefold())
        native_upc = pl.col("lookup_upc").is_in(rule["upcs"])
        if result.filter((legacy & recording & ~native_upc.fill_null(False)).fill_null(False)).height:
            raise ValueError("Metadata externa de la grabacion corregida sin UPC confirmado; no trasladar a otra grabacion.")
        if "reported_lookup_isrc" not in result.columns:
            result = result.with_columns(pl.col("lookup_isrc").alias("reported_lookup_isrc"))
        result = result.with_columns(pl.when((legacy & recording & native_upc).fill_null(False))
            .then(pl.lit(rule["canonical_isrc"])).otherwise(pl.col("lookup_isrc")).alias("lookup_isrc"))
    return result


def corrected_legacy_is_not_video_alias(code, evidence):
    return any(code == rule["reported_isrc"] and evidence
        and all(row.get("YouTube Video ID") in rule["video_ids"] and row.get("principal_asset_isrc") == rule["canonical_isrc"] for row in evidence)
        for rule in corrections())
