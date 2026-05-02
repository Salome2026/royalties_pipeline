from pathlib import Path
import polars as pl


BASE = Path(r"C:\royalties_pipeline")

INPUT_PATH = BASE / "warehouse/marts/standardized_raw_dashgo.parquet"
OUTPUT_PATH = BASE / "warehouse/marts/song_level_dashgo.parquet"


def main():

    print("Cargando standardized DashGo...")

    df = pl.read_parquet(INPUT_PATH)

    print(f"Filas input: {df.height}")

    # =========================
    # FILTRAR
    # =========================

    df = df.filter(
        pl.col("amount_usd").is_not_null()
    )

    # =========================
    # GROUP BY SONG LEVEL
    # =========================

    song_level = (
        df
        .group_by([
            "source",
            "account",
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

    # =========================
    # CLASIFICACIÓN (igual que FUGA)
    # =========================

    song_level = song_level.with_columns([
        pl.when(pl.col("asset_isrc").is_null())
        .then(pl.lit("ugc"))
        .otherwise(pl.lit("catalog"))
        .alias("content_type")
    ])

    print(f"Filas song level: {song_level.height}")

    # =========================
    # SAVE
    # =========================

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    song_level.write_parquet(OUTPUT_PATH)

    print("\nListo.")
    print(f"Archivo generado: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()