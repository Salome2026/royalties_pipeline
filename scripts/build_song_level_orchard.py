from pathlib import Path

import polars as pl


BASE = Path(r"C:\royalties_pipeline")

INPUT_PATH = BASE / "warehouse" / "marts" / "standardized_raw_orchard.parquet"
OUTPUT_PATH = BASE / "warehouse" / "marts" / "song_level_orchard.parquet"

ALTAFONTE_STATEMENT_TYPE = "altafonte_legacy"


def main():
    print("Cargando standardized Orchard...")

    df = pl.read_parquet(INPUT_PATH)

    print(f"Filas input: {df.height}")

    df = df.filter(pl.col("amount_usd").is_not_null())

    song_level = (
        df
        .group_by([
            "source",
            "account",
            "statement_type",
            "asset_isrc",
            "track_statement_style",
            "artist_statement_style",
            "transaction_month",
        ])
        .agg([
            pl.sum("amount_usd").alias("amount_usd"),
            pl.sum("units").alias("units"),
        ])
    )

    song_level = song_level.with_columns([
        pl.when(pl.col("statement_type") == ALTAFONTE_STATEMENT_TYPE)
        .then(pl.lit("legacy"))
        .when(pl.col("asset_isrc").is_null())
        .then(pl.lit("ugc"))
        .otherwise(pl.lit("catalog"))
        .alias("content_type")
    ])

    print(f"Filas song level: {song_level.height}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    song_level.write_parquet(OUTPUT_PATH)

    print("\nListo.")
    print(f"Archivo generado: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
