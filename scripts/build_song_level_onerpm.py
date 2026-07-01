from pathlib import Path

import polars as pl

from lib.identity import (
    first_valid_isrc_expr,
    first_valid_upc_expr,
    first_valid_youtube_channel_id_expr,
    first_valid_youtube_video_id_expr,
    optional_text_expr,
)


BASE = Path(r"C:\royalties_pipeline")

INPUT_PATH = BASE / "warehouse" / "marts" / "standardized_raw_onerpm.parquet"
OUTPUT_PATH = BASE / "warehouse" / "marts" / "song_level_onerpm.parquet"


def optional_col(name: str, dtype=pl.Utf8) -> pl.Expr:
    if dtype == pl.Utf8:
        return optional_text_expr(INPUT_COLUMNS, name)
    return pl.col(name).cast(dtype, strict=False) if name in INPUT_COLUMNS else pl.lit(None).cast(dtype)


INPUT_COLUMNS = set()


def main():
    global INPUT_COLUMNS

    print("Cargando standardized ONErpm...")

    df = pl.read_parquet(INPUT_PATH)
    INPUT_COLUMNS = set(df.columns)

    print(f"Filas input: {df.height}")

    df = df.filter(pl.col("amount_usd").is_not_null())

    df = df.with_columns([
        first_valid_isrc_expr(INPUT_COLUMNS, ["ISRC", "ID", "Parent ID"]).alias("asset_isrc"),

        pl.when(pl.col("source_sheet") == "Youtube Channels")
        .then(first_valid_youtube_video_id_expr(INPUT_COLUMNS, ["Video ID"]))
        .when(pl.col("source_sheet") == "Shares In & Out")
        .then(first_valid_youtube_video_id_expr(INPUT_COLUMNS, ["ID"]))
        .otherwise(pl.lit(None).cast(pl.Utf8))
        .alias("track_id"),

        pl.when(pl.col("source_sheet").is_in(["Youtube Channels", "Shares In & Out"]))
        .then(first_valid_youtube_channel_id_expr(INPUT_COLUMNS, ["Channel ID", "Parent ID"]))
        .otherwise(pl.lit(None).cast(pl.Utf8))
        .alias("channel_id"),

        pl.coalesce([
            optional_col("Track Title"),
            optional_col("Title"),
            optional_col("Video Title"),
            optional_col("Album Title"),
        ]).alias("track_statement_style"),

        first_valid_upc_expr(INPUT_COLUMNS, ["UPC", "Parent ID"]).alias("product_upc"),
        optional_col("Store").alias("store_name"),
        optional_col("Territory").alias("territory"),
        optional_col("Sale Type").alias("sale_type"),
        optional_col("Label").alias("label"),
        optional_col("Product Type").alias("product_type"),
        optional_col("Quantity", pl.Float64).alias("units"),
    ])

    song_level = (
        df
        .group_by([
            "source",
            "account",
            "source_sheet",
            "revenue_basis",
            "include_in_cash_view",
            "include_in_catalog_view",
            "include_in_statement_view",
            "possible_internal_transfer",
            "asset_isrc",
            "track_id",
            "channel_id",
            "track_statement_style",
            "artist_statement_style",
            "transaction_month",
        ])
        .agg([
            pl.sum("amount_usd").alias("amount_usd"),
            pl.sum("net_amount").alias("net_amount"),
            pl.sum("units").alias("units"),
        ])
    )

    song_level = song_level.with_columns([
        pl.when(pl.col("source_sheet") == "Youtube Channels")
        .then(pl.lit("youtube_channel"))
        .when(pl.col("source_sheet") == "Shares In & Out")
        .then(pl.lit("share_transfer"))
        .when(pl.col("asset_isrc").is_null() | (pl.col("asset_isrc").str.strip_chars() == ""))
        .then(pl.lit("unidentified"))
        .otherwise(pl.lit("catalog"))
        .alias("content_type")
    ])

    print(f"Filas song level: {song_level.height}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    song_level.write_parquet(OUTPUT_PATH)

    print("\nListo.")
    print(f"Archivo generado: {OUTPUT_PATH}")
    print(f"Total amount_usd: {song_level['amount_usd'].sum()}")


if __name__ == "__main__":
    main()
