from pathlib import Path
from datetime import datetime

import polars as pl


BASE = Path(r"C:\royalties_pipeline")

INPUT_PATH = BASE / "warehouse" / "marts" / "song_level_all_sources.parquet"
OUTPUT_PATH = BASE / "warehouse" / "marts" / "catalog_candidates.parquet"
REPORT_PATH = BASE / "reports" / "catalog_candidates_review.xlsx"


def clean_text_expr(col: str) -> pl.Expr:
    return (
        pl.col(col)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.replace_all(r"\s+", " ")
    )


def main():
    print("Construyendo catalog candidates...")

    df = pl.read_parquet(INPUT_PATH)

    df = df.with_columns([
        clean_text_expr("asset_isrc").str.to_uppercase().alias("isrc_norm"),
        pl.coalesce([
            clean_text_expr("track_statement_style"),
            clean_text_expr("asset_title_statement"),
        ]).alias("track_title_statement"),
        pl.coalesce([
            clean_text_expr("artist_statement_style"),
            clean_text_expr("asset_artist_statement"),
        ]).alias("artist_statement"),
        pl.coalesce([
            pl.col("units").cast(pl.Float64, strict=False),
            pl.col("streams").cast(pl.Float64, strict=False),
        ]).alias("usage_units"),
    ])

    df = df.with_columns([
        pl.when(pl.col("isrc_norm").is_null() | (pl.col("isrc_norm") == ""))
        .then(pl.lit(None).cast(pl.Utf8))
        .otherwise(pl.col("isrc_norm"))
        .alias("isrc_norm"),

        pl.when(pl.col("track_title_statement").is_null() | (pl.col("track_title_statement") == ""))
        .then(pl.lit("SIN TITULO"))
        .otherwise(pl.col("track_title_statement"))
        .alias("track_title_statement"),

        pl.when(pl.col("artist_statement").is_null() | (pl.col("artist_statement") == ""))
        .then(pl.lit("SIN ARTISTA"))
        .otherwise(pl.col("artist_statement"))
        .alias("artist_statement"),
    ])

    df = df.with_columns([
        pl.when(pl.col("isrc_norm").is_not_null())
        .then(pl.concat_str([pl.lit("ISRC:"), pl.col("isrc_norm")]))
        .otherwise(
            pl.concat_str([
                pl.lit("NOISRC:"),
                pl.col("track_title_statement").str.to_lowercase(),
                pl.lit("|"),
                pl.col("artist_statement").str.to_lowercase(),
            ])
        )
        .alias("catalog_candidate_key")
    ])

    candidates = (
        df
        .group_by("catalog_candidate_key")
        .agg([
            pl.first("isrc_norm").alias("asset_isrc"),
            pl.first("track_title_statement").alias("track_title"),
            pl.first("artist_statement").alias("artist_statement"),
            pl.sum("amount_usd").alias("amount_usd"),
            pl.sum("usage_units").alias("units"),
            pl.min("transaction_month").alias("first_month"),
            pl.max("transaction_month").alias("last_month"),
            pl.n_unique("source").alias("source_count"),
            pl.n_unique("account").alias("account_count"),
            pl.n_unique("track_title_statement").alias("title_variant_count"),
            pl.n_unique("artist_statement").alias("artist_variant_count"),
            pl.col("source").drop_nulls().unique().sort().str.join(", ").alias("sources"),
            pl.col("account").drop_nulls().unique().sort().str.join(", ").alias("accounts"),
            pl.col("content_type").drop_nulls().unique().sort().str.join(", ").alias("content_types"),
            pl.col("track_title_statement").drop_nulls().unique().sort().head(5).str.join(" | ").alias("title_variants_sample"),
            pl.col("artist_statement").drop_nulls().unique().sort().head(5).str.join(" | ").alias("artist_variants_sample"),
            pl.len().alias("song_level_rows"),
        ])
        .with_columns([
            pl.when(pl.col("asset_isrc").is_null())
            .then(pl.lit(True))
            .otherwise(pl.lit(False))
            .alias("needs_isrc_review"),

            (pl.col("title_variant_count") > 1).alias("needs_title_review"),
            (pl.col("artist_variant_count") > 1).alias("needs_artist_review"),
            (
                pl.col("asset_isrc").is_null()
                | (pl.col("title_variant_count") > 1)
                | (pl.col("artist_variant_count") > 1)
            ).alias("needs_catalog_review"),
        ])
        .sort("amount_usd", descending=True)
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    candidates.write_parquet(OUTPUT_PATH)

    review = candidates.to_pandas()
    needs_review = candidates.filter(pl.col("needs_catalog_review") == True).to_pandas()
    top_no_isrc = (
        candidates
        .filter(pl.col("needs_isrc_review") == True)
        .sort("amount_usd", descending=True)
        .head(200)
        .to_pandas()
    )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with pl.Config(tbl_cols=-1):
        print("\n=== RESUMEN ===")
        print("Candidates:", candidates.height)
        print("Needs review:", candidates.filter(pl.col("needs_catalog_review") == True).height)
        print("No ISRC:", candidates.filter(pl.col("needs_isrc_review") == True).height)
        print("Total amount_usd:", candidates["amount_usd"].sum())

    excel_path = REPORT_PATH

    try:
        writer_ctx = __import__("pandas").ExcelWriter(excel_path, engine="openpyxl")
    except PermissionError:
        excel_path = REPORT_PATH.with_name(
            f"{REPORT_PATH.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{REPORT_PATH.suffix}"
        )
        print(f"\nNo se pudo sobrescribir el Excel. Se genera copia: {excel_path}")
        writer_ctx = __import__("pandas").ExcelWriter(excel_path, engine="openpyxl")

    with writer_ctx as writer:
        review.to_excel(writer, index=False, sheet_name="catalog_candidates")
        needs_review.to_excel(writer, index=False, sheet_name="needs_review")
        top_no_isrc.to_excel(writer, index=False, sheet_name="top_no_isrc")

    print("\nListo.")
    print(f"Parquet: {OUTPUT_PATH}")
    print(f"Excel: {excel_path}")


if __name__ == "__main__":
    main()
