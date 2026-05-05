from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl


BASE = Path(r"C:\royalties_pipeline")
RAW_DIR = BASE / "warehouse" / "booking" / "raw"
OUTPUT_DIR = BASE / "warehouse" / "booking" / "standardized"
OUTPUT_PATH = OUTPUT_DIR / "standardized_booking_movements.parquet"


STANDARD_INCOME_FILES = [
    # The standalone google sample is preserved in raw, but PM Lautaro contains the
    # same operational rows. Using both here would double count those shows.
    RAW_DIR / "booking_raw_pm_ingresos.parquet",
]

STANDARD_EXPENSE_FILES = [
    # See note above: the non-PM operational sample remains available for audit.
    RAW_DIR / "booking_raw_pm_egresos.parquet",
]

PM_DAVID_EXPENSE_FILES = [
    RAW_DIR / "booking_raw_pm_raw.parquet",
    RAW_DIR / "booking_raw_pm_indyana_expenses.parquet",
]


def parse_number(value: object) -> float | None:
    if value is None:
        return None

    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return None

    text = (
        text.replace("$", "")
        .replace("u$s", "")
        .replace("usd", "")
        .replace("ars", "")
        .replace(" ", "")
    )

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def parse_date(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return None

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass

    return None


def read_existing(paths: list[Path]) -> pl.DataFrame:
    frames = []

    for path in paths:
        if path.exists():
            frames.append(pl.read_parquet(path))

    if not frames:
        return pl.DataFrame()

    return pl.concat(frames, how="diagonal_relaxed")


def optional_col(name: str) -> pl.Expr:
    return pl.col(name) if name in current_columns else pl.lit(None)


def parse_number_col(name: str) -> pl.Expr:
    return optional_col(name).map_elements(parse_number, return_dtype=pl.Float64)


def parse_date_col(name: str) -> pl.Expr:
    return optional_col(name).map_elements(parse_date, return_dtype=pl.Utf8).str.to_date()


def clean_text_col(name: str) -> pl.Expr:
    return (
        optional_col(name)
        .cast(pl.Utf8)
        .str.strip_chars()
        .replace("", None)
    )


def normalize_business_area() -> pl.Expr:
    category = pl.col("movement_category").str.to_lowercase()

    return (
        pl.when(category == "booking")
        .then(pl.lit("booking"))
        .when(category == "label")
        .then(pl.lit("label"))
        .when(category == "management")
        .then(pl.lit("management"))
        .otherwise(pl.lit("unknown"))
    )


def normalize_is_recoverable() -> pl.Expr:
    recoverable = pl.col("raw_recoverable").str.to_lowercase()

    return (
        pl.when(recoverable.is_in(["si", "sí", "yes", "true", "1", "recuperable"]))
        .then(pl.lit(True))
        .when(recoverable.is_in(["no", "false", "0"]))
        .then(pl.lit(False))
        .otherwise(None)
    )


def add_status_notes(base_status: str) -> list[pl.Expr]:
    return [
        pl.when(pl.col("movement_date").is_null())
        .then(pl.lit("needs_review_missing_date"))
        .when(pl.col("artist_statement").is_null())
        .then(pl.lit("needs_review_missing_artist"))
        .when(pl.col("amount_ars").is_null() & pl.col("amount_usd").is_null())
        .then(pl.lit("needs_review_missing_amount"))
        .when((pl.col("amount_ars") == 0) & (pl.col("amount_usd") == 0))
        .then(pl.lit("needs_review_zero_amount"))
        .otherwise(pl.lit(base_status))
        .alias("standardization_status"),
        pl.concat_str(
            [
                pl.when(pl.col("movement_category").is_null())
                .then(pl.lit("missing_category"))
                .otherwise(None),
                pl.when(pl.col("movement_subcategory").is_null())
                .then(pl.lit("missing_subcategory"))
                .otherwise(None),
                pl.when(pl.col("business_area") != "booking")
                .then(pl.concat_str([pl.lit("business_area="), pl.col("business_area")]))
                .otherwise(None),
            ],
            separator="; ",
            ignore_nulls=True,
        )
        .replace("", None)
        .alias("standardization_notes"),
    ]


def standardize_standard_frame(df: pl.DataFrame, movement_type: str) -> pl.DataFrame:
    global current_columns
    current_columns = set(df.columns)

    out = df.select([
        clean_text_col("source_file_name").alias("source_file_name"),
        clean_text_col("source_file_path").alias("source_file_path"),
        clean_text_col("source_sheet").alias("source_sheet"),
        optional_col("source_row").cast(pl.UInt32, strict=False).alias("source_row"),
        clean_text_col("source_dataset").alias("source_dataset"),
        pl.lit(movement_type).alias("movement_type"),
        parse_date_col("FECHA").alias("movement_date"),
        clean_text_col("ARTISTA").alias("artist_statement"),
        clean_text_col("Categoria").alias("movement_category"),
        clean_text_col("Sub Categoria").alias("movement_subcategory"),
        clean_text_col("Evento / Detalle").alias("event_detail"),
        clean_text_col("CONCEPTO").alias("concept"),
        parse_number_col("Importe en $").alias("amount_ars"),
        parse_number_col("Importe en u$").alias("amount_usd"),
        parse_number_col("T/C").alias("fx_rate"),
        clean_text_col("Estado").alias("payment_status"),
        clean_text_col("Medio").alias("payment_method"),
        clean_text_col("Origen").alias("payer_or_origin"),
        clean_text_col("Beneficiario").alias("payee_or_beneficiary"),
        parse_number_col("Porcentaje").alias("percentage"),
        clean_text_col("Recuperable").alias("raw_recoverable"),
    ])

    return (
        out.with_columns([
            normalize_business_area().alias("business_area"),
            normalize_is_recoverable().alias("is_recoverable"),
        ])
        .with_columns(add_status_notes("ok"))
        .with_columns(
            pl.concat_str(
                [
                    pl.lit("booking"),
                    pl.col("movement_type"),
                    pl.col("source_file_name"),
                    pl.col("source_sheet"),
                    pl.col("source_row").cast(pl.Utf8),
                ],
                separator=":",
            ).alias("movement_id")
        )
    )


def standardize_pm_david_expenses(df: pl.DataFrame, business_area: str) -> pl.DataFrame:
    global current_columns
    current_columns = set(df.columns)

    out = df.select([
        clean_text_col("source_file_name").alias("source_file_name"),
        clean_text_col("source_file_path").alias("source_file_path"),
        clean_text_col("source_sheet").alias("source_sheet"),
        optional_col("source_row").cast(pl.UInt32, strict=False).alias("source_row"),
        clean_text_col("source_dataset").alias("source_dataset"),
        pl.lit("expense").alias("movement_type"),
        parse_date_col("FECHA").alias("movement_date"),
        clean_text_col("ARTISTA").alias("artist_statement"),
        pl.lit(business_area).alias("business_area"),
        clean_text_col("CATEGORIA").alias("movement_category"),
        clean_text_col("column_5").alias("movement_subcategory"),
        clean_text_col("DETALLE").alias("event_detail"),
        clean_text_col("CONCEPTO").alias("concept"),
        parse_number_col("ARS").alias("amount_ars"),
        pl.lit(None, dtype=pl.Float64).alias("amount_usd"),
        parse_number_col("T/C").alias("fx_rate"),
        pl.lit(None, dtype=pl.Utf8).alias("payment_status"),
        pl.lit(None, dtype=pl.Utf8).alias("payment_method"),
        pl.lit(None, dtype=pl.Utf8).alias("payer_or_origin"),
        pl.lit(None, dtype=pl.Utf8).alias("payee_or_beneficiary"),
        pl.lit(None, dtype=pl.Float64).alias("percentage"),
        pl.lit(None, dtype=pl.Utf8).alias("raw_recoverable"),
        pl.lit(None, dtype=pl.Boolean).alias("is_recoverable"),
    ])

    return (
        out.with_columns(add_status_notes("needs_review_pm_david_variant"))
        .with_columns(
            pl.concat_str(
                [
                    pl.lit("booking"),
                    pl.col("movement_type"),
                    pl.col("source_file_name"),
                    pl.col("source_sheet"),
                    pl.col("source_row").cast(pl.Utf8),
                ],
                separator=":",
            ).alias("movement_id")
        )
    )


def main() -> None:
    print("Building standardized booking movements...")

    income = read_existing(STANDARD_INCOME_FILES)
    expenses = read_existing(STANDARD_EXPENSE_FILES)
    pm_david_raw = read_existing([PM_DAVID_EXPENSE_FILES[0]])
    pm_david_indyana = read_existing([PM_DAVID_EXPENSE_FILES[1]])

    frames = []

    if income.height:
        frames.append(standardize_standard_frame(income, "income"))

    if expenses.height:
        frames.append(standardize_standard_frame(expenses, "expense"))

    if pm_david_raw.height:
        frames.append(standardize_pm_david_expenses(pm_david_raw, "unknown"))

    if pm_david_indyana.height:
        frames.append(standardize_pm_david_expenses(pm_david_indyana, "label"))

    if not frames:
        print("No input rows found.")
        return

    final = pl.concat(frames, how="diagonal_relaxed").select([
        "movement_id",
        "movement_type",
        "movement_date",
        "artist_statement",
        "business_area",
        "movement_category",
        "movement_subcategory",
        "event_detail",
        "concept",
        "amount_ars",
        "amount_usd",
        "fx_rate",
        "payment_status",
        "payment_method",
        "payer_or_origin",
        "payee_or_beneficiary",
        "percentage",
        "is_recoverable",
        "standardization_status",
        "standardization_notes",
        "source_file_name",
        "source_sheet",
        "source_row",
        "source_dataset",
        "source_file_path",
    ])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    final.write_parquet(OUTPUT_PATH)

    print("Rows:", final.height)
    print("Output:", OUTPUT_PATH)
    print("\nBy movement type:")
    for row in final.group_by("movement_type").agg(pl.len().alias("rows")).sort("movement_type").to_dicts():
        print(f"  - {row['movement_type']}: {row['rows']}")

    print("\nBy status:")
    for row in (
        final.group_by("standardization_status")
        .agg(pl.len().alias("rows"))
        .sort("rows", descending=True)
        .to_dicts()
    ):
        print(f"  - {row['standardization_status']}: {row['rows']}")


if __name__ == "__main__":
    main()
