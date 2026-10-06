from pathlib import Path

import polars as pl

from lib.ada_identity import ada_native_code_expr


BASE = Path(r"C:\royalties_pipeline")
INPUT_PATH = BASE / "warehouse" / "marts" / "standardized_raw_ada.parquet"
OUTPUT_PATH = BASE / "warehouse" / "marts" / "song_level_ada.parquet"


def main() -> None:
    frame = pl.read_parquet(INPUT_PATH).filter(pl.col("amount_usd").is_not_null())

    song_level = (
        frame
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
            "asset_title_statement",
            "release_statement_style",
            "gpid",
            "catalog_number",
            "ada_account_id",
            "parent_product_id",
            "artist_statement_style",
            "transaction_month",
        ])
        .agg([
            pl.sum("amount_usd").alias("amount_usd"),
            pl.sum("net_amount").alias("net_amount"),
            pl.sum("gross_royalty_usd").alias("gross_royalty_usd"),
            pl.sum("deductible_fees_usd").alias("deductible_fees_usd"),
            pl.sum("units").alias("units"),
        ])
        .with_columns(
            [
                ada_native_code_expr({"catalog_number", "gpid"}).alias("source_asset_id"),
                ada_native_code_expr({"catalog_number", "gpid"}).alias("track_id"),
                pl.when(pl.col("asset_isrc").is_null() | (pl.col("asset_isrc").str.strip_chars() == ""))
                .then(pl.lit("product"))
                .otherwise(pl.lit("catalog"))
                .alias("content_type"),
            ]
        )
    )

    temporary_output = OUTPUT_PATH.with_name(f"{OUTPUT_PATH.name}.tmp")
    song_level.write_parquet(temporary_output)
    temporary_output.replace(OUTPUT_PATH)

    print(f"Archivo: {OUTPUT_PATH}")
    print(f"Filas input: {frame.height}")
    print(f"Filas song level: {song_level.height}")
    print(f"Total USD: {song_level['amount_usd'].sum()}")


if __name__ == "__main__":
    main()
