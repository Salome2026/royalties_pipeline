from pathlib import Path

import polars as pl


BASE = Path(r"C:\royalties_pipeline")
MARTS = BASE / "warehouse" / "marts"

STANDARDIZED_PATH = MARTS / "standardized_raw_all_sources.parquet"
SONG_PATH = MARTS / "song_level_all_sources.parquet"


def print_df(df: pl.DataFrame):
    pl.Config.set_tbl_formatting("ASCII_FULL")
    print(df)


def main():
    print("Audit consolidated marts")

    std = pl.read_parquet(STANDARDIZED_PATH)
    song = pl.read_parquet(SONG_PATH)

    print("\n=== FILES ===")
    print(STANDARDIZED_PATH)
    print(SONG_PATH)

    print("\n=== ROWS ===")
    print("standardized rows:", std.height)
    print("song rows:", song.height)

    print("\n=== STANDARDIZED BY SOURCE ===")
    print_df(
        std
        .group_by("source")
        .agg([
            pl.sum("amount_usd").alias("amount_usd"),
            pl.len().alias("rows"),
        ])
        .sort("source")
    )

    print("\n=== SONG BY SOURCE ===")
    print_df(
        song
        .group_by("source")
        .agg([
            pl.sum("amount_usd").alias("amount_usd"),
            pl.len().alias("rows"),
        ])
        .sort("source")
    )

    print("\n=== COMPARE BY SOURCE ===")
    std_summary = (
        std
        .group_by("source")
        .agg(pl.sum("amount_usd").alias("standardized_usd"))
    )

    song_summary = (
        song
        .group_by("source")
        .agg(pl.sum("amount_usd").alias("song_usd"))
    )

    print_df(
        std_summary
        .join(song_summary, on="source", how="full", coalesce=True)
        .with_columns((pl.col("song_usd") - pl.col("standardized_usd")).alias("diff"))
        .sort("source")
    )

    print("\nNota: SoundOn Summary no se carga al standardized principal; audit_soundon lo lee desde input_raw.")


if __name__ == "__main__":
    main()
