from pathlib import Path

import polars as pl


BASE = Path(r"C:\royalties_pipeline")

STD_PATH = BASE / "warehouse" / "marts" / "standardized_raw_soundon.parquet"
SONG_PATH = BASE / "warehouse" / "marts" / "song_level_soundon.parquet"
INPUT_DIR = BASE / "input_raw" / "soundon"


def print_df(df: pl.DataFrame):
    pl.Config.set_tbl_formatting("ASCII_FULL")
    print(df)


def main():
    print("Audit SoundOn")

    std = pl.read_parquet(STD_PATH)
    song = pl.read_parquet(SONG_PATH)

    print("\n=== STANDARDIZED TOTALS ===")
    print("Rows:", std.height)
    print("All amount_usd:", std["amount_usd"].sum())
    print(
        "Statement amount_usd:",
        std.filter(pl.col("include_in_statement_view") == True)["amount_usd"].sum(),
    )

    print("\n=== MY ROYALTY VS SUMMARY ===")
    my = (
        std
        .filter(pl.col("source_sheet") == "my_royalty")
        .group_by("statement_period")
        .agg(pl.sum("amount_usd").alias("my_royalty_usd"))
    )

    summary_frames = []

    for file_path in sorted(INPUT_DIR.glob("*_Summary.csv")):
        df_summary = pl.read_csv(
            file_path,
            infer_schema_length=1000,
            ignore_errors=True,
            encoding="utf8-lossy",
        )

        if df_summary.height == 0:
            continue

        summary_frames.append(
            df_summary
            .with_columns(
                pl.col("Final Royalty")
                .cast(pl.Utf8)
                .str.replace_all(",", ".")
                .str.strip_chars()
                .replace("", None)
                .cast(pl.Float64, strict=False)
                .alias("_final_royalty")
            )
            .group_by("Reporting Period")
            .agg(pl.sum("_final_royalty").alias("summary_usd"))
            .rename({"Reporting Period": "statement_period"})
        )

    summary = (
        pl.concat(summary_frames, how="diagonal_relaxed")
        if summary_frames
        else pl.DataFrame(schema={"statement_period": pl.Utf8, "summary_usd": pl.Float64})
    )

    print_df(
        my
        .join(summary, on="statement_period", how="full", coalesce=True)
        .with_columns((pl.col("my_royalty_usd") - pl.col("summary_usd")).alias("diff"))
        .sort("statement_period")
    )

    print("\n=== SONG VS STANDARDIZED CATALOG ===")
    catalog_total = std.filter(pl.col("include_in_catalog_view") == True)["amount_usd"].sum()
    print("Song amount_usd:", song["amount_usd"].sum())
    print("Catalog standardized amount_usd:", catalog_total)
    print("Diff:", song["amount_usd"].sum() - catalog_total)

    print("\n=== CONTENT TYPE ===")
    print_df(
        song
        .group_by("content_type")
        .agg([
            pl.sum("amount_usd").alias("amount_usd"),
            pl.sum("units").alias("units"),
            pl.len().alias("rows"),
        ])
        .sort("amount_usd", descending=True)
    )

    print("\n=== TOP TRACKS ===")
    print_df(
        song
        .group_by(["asset_isrc", "track_statement_style", "artist_statement_style"])
        .agg([
            pl.sum("amount_usd").alias("amount_usd"),
            pl.sum("units").alias("units"),
        ])
        .sort("amount_usd", descending=True)
        .head(20)
    )

    print("\n=== MONTHLY ===")
    print_df(
        song
        .group_by("transaction_month")
        .agg(pl.sum("amount_usd").alias("amount_usd"))
        .sort("transaction_month")
    )


if __name__ == "__main__":
    main()
