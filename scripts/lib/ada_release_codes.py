from __future__ import annotations

import re

import polars as pl

from lib.ada_identity import ada_isrc_expr, text_field


def valid_gtin(value: str | None) -> bool:
    if value is None or not re.fullmatch(r"(?:[0-9]{8}|[0-9]{12,14})", value):
        return False
    if not int(value):
        return False
    total = sum(int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(value[-2::-1]))
    return (total + int(value[-1])) % 10 == 0


def add_ada_release_codes(frame: pl.DataFrame) -> pl.DataFrame:
    fields = [("ada_explicit_upc", "UPC"), ("parent_product_id", "Parent Product ID")]
    candidates = []
    for name, label in fields:
        raw = text_field(set(frame.columns), [name] if name == label else [name, label])
        values = frame.select(raw.alias(name))[name].drop_nulls().unique().to_list()
        accepted = {value: value for value in values if valid_gtin(value)}
        candidates.append(raw.replace_strict(accepted, default=None, return_dtype=pl.String).alias(f"_upc_{name}"))
    result = frame.with_columns(candidates)
    names = [f"_upc_{name}" for name, _ in fields]
    normalized = [pl.col(name).str.pad_start(14, "0") for name in names]
    conflict = pl.any_horizontal([
        normalized[left].is_not_null() & normalized[right].is_not_null() & (normalized[left] != normalized[right])
        for left in range(len(names)) for right in range(left + 1, len(names))
    ])
    if result.select(conflict.any()).item():
        raise ValueError("ADA contiene UPC y Parent Product ID validos pero contradictorios; revisar antes de publicar.")
    result = result.with_columns([
        pl.coalesce(names).alias("product_upc"),
        pl.coalesce([
            pl.when(pl.col(name).is_not_null()).then(pl.lit(label))
            for name, (_, label) in zip(names, fields)
        ]).alias("product_upc_source"),
    ]).drop(names)
    result = result.with_columns(
        pl.when(pl.col("product_upc").is_not_null()).then(pl.lit("reported"))
        .otherwise(pl.lit("unavailable")).alias("product_upc_status")
    )
    # An Excel album row can omit the parent code carried by its tracks. Only
    # complete it from one exact release/artist pair in this same statement.
    context = ["Project Title", "Artist Name"]
    if set(context + ["Catalogue Title"]).issubset(result.columns):
        evidence = (
            result.filter(ada_isrc_expr(set(result.columns)).is_not_null() & pl.col("product_upc").is_not_null())
            .group_by(context).agg(
                pl.col("product_upc").str.pad_start(14, "0").n_unique().alias("_upc_count"),
                pl.col("product_upc").sort().first().alias("_release_upc"),
            ).filter(pl.col("_upc_count") == 1).drop("_upc_count")
        )
        result = result.join(evidence, on=context, how="left", maintain_order="left")
        eligible = (
            ada_isrc_expr(set(result.columns)).is_null() & pl.col("product_upc").is_null()
            & (pl.col("Catalogue Title") == pl.col("Project Title"))
            & pl.col("Project Title").is_not_null() & (pl.col("Project Title").str.strip_chars() != "")
            & pl.col("Artist Name").is_not_null() & (pl.col("Artist Name").str.strip_chars() != "")
            & pl.col("_release_upc").is_not_null()
        ).fill_null(False)
        result = result.with_columns([
            pl.when(eligible).then(pl.col("_release_upc")).otherwise(pl.col("product_upc")).alias("product_upc"),
            pl.when(eligible).then(pl.lit("same_statement_release")).otherwise(pl.col("product_upc_source")).alias("product_upc_source"),
            pl.when(eligible).then(pl.lit("derived_release")).otherwise(pl.col("product_upc_status")).alias("product_upc_status"),
        ]).drop("_release_upc")
    return result
