from pathlib import Path

import polars as pl


BASE = Path(r"C:\royalties_pipeline")

INPUT_PATH = BASE / "warehouse" / "marts" / "standardized_raw_soundon.parquet"
OUTPUT_PATH = BASE / "warehouse" / "marts" / "song_level_soundon.parquet"


def main():
    print("Cargando standardized SoundOn...")

    df = pl.read_parquet(INPUT_PATH)

    print(f"Filas input: {df.height}")

    df = df.filter(
        (pl.col("include_in_catalog_view") == True)
        & pl.col("amount_usd").is_not_null()
    )

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
            "track_statement_style",
            "artist_statement_style",
            "transaction_month",
        ])
        .agg([
            pl.sum("amount_usd").alias("amount_usd"),
            pl.sum("net_amount").alias("net_amount"),
            pl.sum("gross_revenue_usd").alias("gross_revenue_usd"),
            pl.sum("artist_share_usd").alias("artist_share_usd"),
            pl.sum("units").alias("units"),
        ])
    )

    song_level = song_level.with_columns([
        pl.when(pl.col("asset_isrc").is_null() | (pl.col("asset_isrc").str.strip_chars() == ""))
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
