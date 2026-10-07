from __future__ import annotations

import polars as pl


def add_ada_artist_evidence(frame: pl.DataFrame) -> pl.DataFrame:
    """Complete a cut credit only with a unique longer credit for the same ISRC."""
    observations = frame.select("asset_isrc", "Artist Name", "statement_file_name").unique().sort(["asset_isrc", "Artist Name", "statement_file_name"]).to_dicts()
    by_isrc: dict[str, dict[str, tuple[str, str]]] = {}
    for row in observations:
        raw = str(row["Artist Name"] or "").strip()
        if row["asset_isrc"] and raw:
            by_isrc.setdefault(row["asset_isrc"], {}).setdefault(raw.casefold(), (raw, row["statement_file_name"]))
    resolved = []
    for row in frame.select("asset_isrc", "Artist Name").unique().iter_rows(named=True):
        raw = str(row["Artist Name"] or "").strip()
        matches = [value for key, value in by_isrc.get(row["asset_isrc"], {}).items()
                   if len(raw) == 30 and len(value[0]) > 30 and key.startswith(raw.casefold())]
        credit, evidence, status = raw or None, None, "as_reported"
        if len(matches) == 1:
            credit, evidence = matches[0]
            status = "confirmed_prefix"
        elif len(matches) > 1:
            status = "conflicting_prefix"
        elif len(raw) == 30:
            status = "possible_truncation"
        resolved.append({**row, "artist_catalog_style": credit, "artist_credit_status": status,
                         "artist_credit_evidence_file": evidence})
    evidence_frame = pl.DataFrame(resolved, schema={
        "asset_isrc": pl.String, "Artist Name": pl.String, "artist_catalog_style": pl.String,
        "artist_credit_status": pl.String, "artist_credit_evidence_file": pl.String,
    })
    original = text_field(set(frame.columns), ["artist_statement_original", "Artist Name", "artist_statement_style"])
    frame = frame.with_columns(original.alias("artist_statement_original")).drop(
        [name for name in ("artist_catalog_style", "artist_credit_status", "artist_credit_evidence_file") if name in frame.columns]
    )
    return frame.join(
        evidence_frame, on=["asset_isrc", "Artist Name"], how="left", nulls_equal=True, maintain_order="left"
    ).with_columns(
        pl.coalesce([pl.col("artist_catalog_style"), pl.col("artist_statement_original")]).alias("artist_statement_style")
    )


def text_field(schema: set[str], names: list[str]) -> pl.Expr:
    fields = [
        pl.col(name).cast(pl.Utf8, strict=False).str.strip_chars().replace("", None)
        for name in names if name in schema
    ]
    return pl.coalesce(fields) if fields else pl.lit(None).cast(pl.Utf8)


def ada_source_expr(schema: set[str]) -> pl.Expr:
    return text_field(schema, ["source"]).str.to_lowercase() == "ada"


def ada_isrc_expr(schema: set[str]) -> pl.Expr:
    value = text_field(schema, ["asset_isrc", "ISRC"]).str.to_uppercase().str.replace_all(r"[^A-Z0-9]", "")
    return pl.when(value.str.contains(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")).then(value).otherwise(None)


def ada_native_code_expr(schema: set[str]) -> pl.Expr:
    return text_field(schema, ["catalog_number", "Catalogue Number"])


def ada_native_code_type_expr(schema: set[str]) -> pl.Expr:
    catalog = ada_native_code_expr(schema)
    return pl.when(catalog.is_not_null()).then(pl.lit("ADA Catalog Number")).otherwise(None)


def ada_catalog_key_expr(schema: set[str]) -> pl.Expr:
    account = text_field(schema, ["ada_account_id"])
    account = pl.coalesce([
        account,
        text_field(schema, ["account"]).replace({"mawz": "99205", "indyana_records": "99500"}),
    ])
    isrc = ada_isrc_expr(schema)
    catalog = ada_native_code_expr(schema)
    return (
        pl.when(~ada_source_expr(schema).fill_null(False)).then(None)
        .when(isrc.is_not_null()).then(pl.concat_str([pl.lit("ISRC:"), isrc]))
        .when(catalog.is_not_null()).then(pl.concat_str([pl.lit("ADA:"), account, pl.lit(":CATALOG:"), catalog]))
        .otherwise(None)
    )
