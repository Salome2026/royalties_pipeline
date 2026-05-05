from __future__ import annotations

from pathlib import Path

import polars as pl


BASE = Path(r"C:\royalties_pipeline")
INPUT_PATH = BASE / "warehouse" / "booking" / "standardized" / "standardized_booking_movements.parquet"
REPORT_DIR = BASE / "reports" / "booking"
OUTPUT_PATH = REPORT_DIR / "audit_booking_shows.csv"


def main() -> None:
    print("Audit booking shows")

    if not INPUT_PATH.exists():
        print("No existe input:")
        print(INPUT_PATH)
        return

    df = pl.read_parquet(INPUT_PATH)

    booking_show = df.filter(
        (pl.col("business_area") == "booking")
        & (pl.col("movement_subcategory").str.to_lowercase() == "show")
    ).with_columns(
        [
            pl.when(pl.col("movement_type") == "income")
            .then(pl.col("amount_ars"))
            .otherwise(0)
            .alias("income_ars_value"),
            pl.when(pl.col("movement_type") == "expense")
            .then(pl.col("amount_ars"))
            .otherwise(0)
            .alias("expense_ars_value"),
            pl.when(pl.col("movement_type") == "income")
            .then(pl.col("amount_usd"))
            .otherwise(0)
            .alias("income_usd_value"),
            pl.when(pl.col("movement_type") == "expense")
            .then(pl.col("amount_usd"))
            .otherwise(0)
            .alias("expense_usd_value"),
            (pl.col("movement_type") == "income").cast(pl.UInt32).alias("income_line_value"),
            (pl.col("movement_type") == "expense").cast(pl.UInt32).alias("expense_line_value"),
        ]
    )

    print("Movimientos booking/show:", booking_show.height)

    grouped = (
        booking_show
        .group_by([
            "source_file_name",
            "artist_statement",
            "movement_date",
            "event_detail",
        ])
        .agg([
            pl.sum("income_ars_value").alias("income_ars"),
            pl.sum("expense_ars_value").alias("expense_ars"),
            pl.sum("income_usd_value").alias("income_usd"),
            pl.sum("expense_usd_value").alias("expense_usd"),
            pl.sum("income_line_value").alias("income_lines"),
            pl.sum("expense_line_value").alias("expense_lines"),
            pl.len().alias("movement_lines"),
            pl.col("concept").drop_nulls().str.join(" | ").alias("concepts"),
            pl.col("standardization_status").drop_nulls().str.join(" | ").alias("statuses"),
        ])
        .with_columns([
            pl.col("income_ars").fill_null(0),
            pl.col("expense_ars").fill_null(0),
            pl.col("income_usd").fill_null(0),
            pl.col("expense_usd").fill_null(0),
            pl.col("income_lines").fill_null(0),
            pl.col("expense_lines").fill_null(0),
        ])
        .with_columns([
            (pl.col("income_ars") - pl.col("expense_ars")).alias("net_ars"),
            (pl.col("income_usd") - pl.col("expense_usd")).alias("net_usd"),
            pl.concat_str(
                [
                    pl.when(pl.col("movement_date").is_null())
                    .then(pl.lit("missing_date"))
                    .otherwise(None),
                    pl.when(pl.col("income_lines") == 0)
                    .then(pl.lit("missing_income"))
                    .otherwise(None),
                    pl.when(pl.col("expense_lines") == 0)
                    .then(pl.lit("missing_expense"))
                    .otherwise(None),
                    pl.when((pl.col("income_ars") == 0) & (pl.col("income_usd") == 0))
                    .then(pl.lit("zero_income"))
                    .otherwise(None),
                    pl.when(pl.col("statuses").str.contains("needs_review", literal=True))
                    .then(pl.lit("has_needs_review_rows"))
                    .otherwise(None),
                ],
                separator="; ",
                ignore_nulls=True,
            )
            .replace("", None)
            .alias("audit_flags"),
        ])
        .sort(["source_file_name", "artist_statement", "movement_date", "event_detail"])
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    grouped.write_csv(OUTPUT_PATH)

    print("Shows agrupados:", grouped.height)
    print("Output:", OUTPUT_PATH)

    print("\nTotales:")
    print("  Income ARS:", grouped["income_ars"].sum())
    print("  Expense ARS:", grouped["expense_ars"].sum())
    print("  Net ARS:", grouped["net_ars"].sum())
    print("  Income USD:", grouped["income_usd"].sum())
    print("  Expense USD:", grouped["expense_usd"].sum())
    print("  Net USD:", grouped["net_usd"].sum())

    print("\nAlertas:")
    flags = (
        grouped
        .filter(pl.col("audit_flags").is_not_null())
        .select("audit_flags")
        .with_columns(pl.col("audit_flags").str.split("; "))
        .explode("audit_flags")
        .group_by("audit_flags")
        .agg(pl.len().alias("rows"))
        .sort("rows", descending=True)
    )

    for row in flags.to_dicts():
        print(f"  - {row['audit_flags']}: {row['rows']}")


if __name__ == "__main__":
    main()
