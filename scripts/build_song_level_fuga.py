from pathlib import Path
import polars as pl


BASE = Path(r"C:\royalties_pipeline")

INPUT_PATH = BASE / "warehouse/marts/standardized_raw_fuga.parquet"
OUTPUT_PATH = BASE / "warehouse/marts/song_level_fuga.parquet"


def main():

    print("Cargando standardized FUGA...")

    df = pl.read_parquet(INPUT_PATH)

    print(f"Filas input: {df.height}")

    # =========================
    # FILTRADO BÁSICO
    # =========================

    df = df.filter(
        pl.col("amount_usd").is_not_null()
    )

    df = df.with_columns([
        pl.when(pl.col("statement_type") == "correction")
        .then(pl.lit("correction_csv"))
        .otherwise(pl.lit("standard_statement_csv"))
        .alias("source_sheet"),
        pl.when(pl.col("statement_type") == "correction")
        .then(pl.lit("correction"))
        .otherwise(pl.lit("generation"))
        .alias("revenue_basis"),
        pl.lit(True).alias("include_in_cash_view"),
        pl.lit(True).alias("include_in_catalog_view"),
        pl.lit(True).alias("include_in_statement_view"),
        pl.lit(False).alias("possible_internal_transfer"),
    ])

    # =========================
    # GROUP BY SONG LEVEL
    # =========================

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
            "video_id",
            "asset_title_statement",
            "asset_artist_statement",
            "transaction_month",
        ])
        .agg([
            pl.sum("amount_usd").alias("amount_usd"),
            pl.sum("net_amount_eur").alias("amount_eur"),
            pl.sum("asset_quantity_num").alias("streams"),
            pl.col("video_id_source").drop_nulls().first().alias("video_id_source"),
        ])
    )

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
