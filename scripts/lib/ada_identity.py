from __future__ import annotations

import polars as pl


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
    return pl.coalesce([
        text_field(schema, ["catalog_number", "Catalog Number", "Catalogue Number"]),
        text_field(schema, ["gpid", "GPID"]),
    ])


def ada_native_code_type_expr(schema: set[str]) -> pl.Expr:
    catalog = text_field(schema, ["catalog_number", "Catalog Number", "Catalogue Number"])
    gpid = text_field(schema, ["gpid", "GPID"])
    return pl.when(catalog.is_not_null()).then(pl.lit("ADA Catalog Number")).when(gpid.is_not_null()).then(pl.lit("ADA GPID")).otherwise(None)


def ada_catalog_key_expr(schema: set[str]) -> pl.Expr:
    account = text_field(schema, ["ada_account_id", "Account"])
    account = pl.coalesce([
        account,
        text_field(schema, ["account"]).replace({"mawz": "99205", "indyana_records": "99500"}),
    ])
    isrc = ada_isrc_expr(schema)
    catalog = text_field(schema, ["catalog_number", "Catalog Number", "Catalogue Number"])
    gpid = text_field(schema, ["gpid", "GPID"])
    return (
        pl.when(~ada_source_expr(schema).fill_null(False)).then(None)
        .when(isrc.is_not_null()).then(pl.concat_str([pl.lit("ISRC:"), isrc]))
        .when(catalog.is_not_null()).then(pl.concat_str([pl.lit("ADA:"), account, pl.lit(":CATALOG:"), catalog]))
        .when(gpid.is_not_null()).then(pl.concat_str([pl.lit("ADA:"), account, pl.lit(":GPID:"), gpid]))
        .otherwise(None)
    )
