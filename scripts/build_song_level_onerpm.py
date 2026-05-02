from pathlib import Path

import polars as pl


BASE = Path(r"C:\royalties_pipeline")

INPUT_PATH = BASE / "warehouse" / "marts" / "standardized_raw_onerpm.parquet"
OUTPUT_PATH = BASE / "warehouse" / "marts" / "song_level_onerpm.parquet"


def optional_col(name: str, dtype=pl.Utf8) -> pl.Expr:
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
        pl.coalesce([
            optional_col("ISRC"),
            optional_col("ID"),
            optional_col("Parent ID"),
        ]).alias("asset_isrc"),

        pl.coalesce([
            optional_col("Track Title"),
            optional_col("Title"),
            optional_col("Album Title"),
        ]).alias("track_statement_style"),

        optional_col("UPC").alias("product_upc"),
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
        pl.when(pl.col("source_sheet") == "Shares In & Out")
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
