import hashlib
import re
import shutil
from datetime import datetime
from pathlib import Path

import polars as pl

from lib.statement_period import from_column


BASE = Path(r"C:\royalties_pipeline")

INPUT_DIR = BASE / "input_raw" / "soundon"
OUTPUT_PATH = BASE / "warehouse" / "marts" / "standardized_raw_soundon.parquet"
TEMP_DIR = BASE / "staging" / "standardized_raw_parts" / "soundon"

SOURCE = "soundon"
ACCOUNT = "soundon"


def ensure_dirs():
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_file_info(file_path: Path) -> tuple[str, str]:
    match = re.search(
        r"SoundOn_royalty_monthly_statement_(\d{4})_(\d{2})_(.+)\.csv$",
        file_path.name,
        flags=re.IGNORECASE,
    )

    if not match:
        return "unknown", "unknown"

    statement_period = f"{match.group(1)}-{match.group(2)}"
    statement_type = match.group(3).strip().lower().replace(" ", "_")

    return statement_period, statement_type


def decimal_expr(col: str) -> pl.Expr:
    return (
        pl.col(col)
        .cast(pl.Utf8)
        .str.replace_all(",", ".")
        .str.strip_chars()
        .replace("", None)
        .cast(pl.Float64, strict=False)
    )


def read_soundon_csv(file_path: Path) -> pl.DataFrame:
    return pl.read_csv(
        file_path,
        infer_schema_length=10000,
        ignore_errors=True,
        encoding="utf8-lossy",
    )


def standardize_detail_file(df: pl.DataFrame, file_path: Path, statement_type: str) -> pl.DataFrame:
    statement_period, _ = parse_file_info(file_path)
    file_hash = sha256_file(file_path)
    ingested_at = datetime.now().isoformat(timespec="seconds")
    statement_period_source, statement_period_note = from_column(
        "Reporting Period",
        "SoundOn filename also includes YYYY_MM and is used as a file-level cross-check.",
    )

    amount = decimal_expr("Final Royalty")
    units = decimal_expr("Units of Sold")

    currency_col = "Currency" if "Currency" in df.columns else "Final Royalty Currency"
    revenue_basis = "share_transfer" if statement_type in ["share_in", "share_out"] else "master_earning"

    include_in_cash_view = statement_type in ["my_royalty", "share_in", "share_out"]
    include_in_catalog_view = statement_type == "my_royalty"
    include_in_statement_view = include_in_cash_view
    possible_internal_transfer = statement_type in ["share_in", "share_out"]

    return df.with_columns([
        amount.alias("amount_usd"),
        amount.alias("net_amount"),
        amount.alias("net_amount_usd"),
        units.alias("units"),

        decimal_expr("Gross revenue").alias("gross_revenue_usd")
        if "Gross revenue" in df.columns
        else pl.lit(None).cast(pl.Float64).alias("gross_revenue_usd"),

        decimal_expr("Artist Share").alias("artist_share_usd")
        if "Artist Share" in df.columns
        else pl.lit(None).cast(pl.Float64).alias("artist_share_usd"),

        pl.col(currency_col).cast(pl.Utf8).str.strip_chars().str.to_uppercase().alias("currency_original")
        if currency_col in df.columns
        else pl.lit("USD").alias("currency_original"),

        pl.lit(1.0).alias("fx_to_usd_rate"),
        pl.lit(statement_period).alias("fx_rate_date"),

        pl.col("Reporting Period").cast(pl.Utf8).str.strip_chars().alias("statement_period"),
        pl.col("Reporting Period").cast(pl.Utf8).str.strip_chars().alias("transaction_month"),
        pl.col("Sales Period").alias("sales_period"),

        pl.col("Track Artists").cast(pl.Utf8).str.strip_chars().alias("artist_statement_style"),
        pl.col("Track Title").alias("track_statement_style"),
        pl.col("ISRC").alias("asset_isrc"),
        pl.col("Track ID").alias("track_id"),
        pl.col("UPC Code").alias("product_upc"),
        pl.col("Album Title").alias("album_title"),
        pl.col("Release Date").alias("release_date"),
        pl.col("Royalty Type").alias("royalty_type"),
        pl.col("Store Name").alias("store_name"),
        pl.col("Sales Region").alias("territory"),
        pl.col("Sales Type").alias("sales_type"),
        pl.col("Sales Sub Type").alias("sales_sub_type"),

        pl.col("Payee").alias("payee")
        if "Payee" in df.columns
        else pl.lit(None).cast(pl.Utf8).alias("payee"),

        pl.lit(SOURCE).alias("source"),
        pl.lit(ACCOUNT).alias("account"),
        pl.lit(statement_type).alias("source_sheet"),
        pl.lit(revenue_basis).alias("revenue_basis"),
        pl.lit(include_in_cash_view).alias("include_in_cash_view"),
        pl.lit(include_in_catalog_view).alias("include_in_catalog_view"),
        pl.lit(include_in_statement_view).alias("include_in_statement_view"),
        pl.lit(possible_internal_transfer).alias("possible_internal_transfer"),
        pl.lit(file_path.name).alias("statement_file_name"),
        pl.lit(statement_period_source).alias("statement_period_source"),
        pl.lit(statement_period_note).alias("statement_period_note"),
        pl.lit(str(file_path)).alias("statement_file_path"),
        pl.lit(file_hash).alias("statement_file_hash"),
        pl.lit(ingested_at).alias("ingested_at"),
    ])


def standardize_summary_file(df: pl.DataFrame, file_path: Path, statement_type: str) -> pl.DataFrame:
    statement_period, _ = parse_file_info(file_path)
    file_hash = sha256_file(file_path)
    ingested_at = datetime.now().isoformat(timespec="seconds")
    statement_period_source, statement_period_note = from_column(
        "Reporting Period",
        "SoundOn summary is not loaded into the principal standardized mart; kept for audit paths only.",
    )

    return df.with_columns([
        decimal_expr("Final Royalty").alias("amount_usd"),
        decimal_expr("Final Royalty").alias("net_amount"),
        decimal_expr("Final Royalty").alias("net_amount_usd"),
        decimal_expr("Units of Sold").alias("units"),
        decimal_expr("Gross revenue").alias("gross_revenue_usd"),
        pl.lit(None).cast(pl.Float64).alias("artist_share_usd"),
        pl.col("Final Royalty Currency").cast(pl.Utf8).str.strip_chars().str.to_uppercase().alias("currency_original"),
        pl.lit(1.0).alias("fx_to_usd_rate"),
        pl.lit(statement_period).alias("fx_rate_date"),
        pl.col("Reporting Period").cast(pl.Utf8).str.strip_chars().alias("statement_period"),
        pl.col("Reporting Period").cast(pl.Utf8).str.strip_chars().alias("transaction_month"),
        pl.lit(None).cast(pl.Utf8).alias("sales_period"),
        pl.lit(None).cast(pl.Utf8).alias("artist_statement_style"),
        pl.lit(None).cast(pl.Utf8).alias("track_statement_style"),
        pl.lit(None).cast(pl.Utf8).alias("asset_isrc"),
        pl.lit(None).cast(pl.Utf8).alias("track_id"),
        pl.lit(None).cast(pl.Utf8).alias("product_upc"),
        pl.lit(None).cast(pl.Utf8).alias("album_title"),
        pl.lit(None).cast(pl.Utf8).alias("release_date"),
        pl.lit(None).cast(pl.Utf8).alias("royalty_type"),
        pl.col("Store Name").alias("store_name"),
        pl.lit(None).cast(pl.Utf8).alias("territory"),
        pl.lit(None).cast(pl.Utf8).alias("sales_type"),
        pl.lit(None).cast(pl.Utf8).alias("sales_sub_type"),
        pl.lit(None).cast(pl.Utf8).alias("payee"),
        pl.lit(SOURCE).alias("source"),
        pl.lit(ACCOUNT).alias("account"),
        pl.lit(statement_type).alias("source_sheet"),
        pl.lit("summary").alias("revenue_basis"),
        pl.lit(False).alias("include_in_cash_view"),
        pl.lit(False).alias("include_in_catalog_view"),
        pl.lit(False).alias("include_in_statement_view"),
        pl.lit(False).alias("possible_internal_transfer"),
        pl.lit(file_path.name).alias("statement_file_name"),
        pl.lit(statement_period_source).alias("statement_period_source"),
        pl.lit(statement_period_note).alias("statement_period_note"),
        pl.lit(str(file_path)).alias("statement_file_path"),
        pl.lit(file_hash).alias("statement_file_hash"),
        pl.lit(ingested_at).alias("ingested_at"),
    ])


def main():
    ensure_dirs()

    files = sorted(INPUT_DIR.glob("*.csv"))

    print("SoundOn standardized ingest")
    print(f"Archivos: {len(files)}")

    parts = []

    for file_path in files:
        statement_period, statement_type = parse_file_info(file_path)
        print(f"\nProcesando {statement_period} / {statement_type}: {file_path.name}")

        try:
            df = read_soundon_csv(file_path)

            if statement_type == "summary":
                print("  Summary se omite del standardized principal; se usa solo en auditorias.")
                continue

            if statement_type == "discovery_mode":
                print("  Discovery Mode se omite: detalla una deduccion ya incluida en My Royalty.")
                continue

            df_std = standardize_detail_file(df, file_path, statement_type)

            part_path = TEMP_DIR / f"{file_path.stem}.parquet"
            df_std.write_parquet(part_path)
            parts.append(part_path)

            print(f"  OK filas: {df_std.height}")

        except Exception as e:
            print(f"  ERROR: {e}")

    if not parts:
        print("\nNo se generaron datos.")
        return

    print("\nConsolidando...")

    final = pl.concat([pl.read_parquet(part) for part in parts], how="diagonal_relaxed")
    final.write_parquet(OUTPUT_PATH)

    print("\nListo.")
    print(f"Archivo: {OUTPUT_PATH}")
    print(f"Filas: {final.height}")
    print(f"Total amount_usd all: {final['amount_usd'].sum()}")
    print(
        "Total amount_usd statement view:",
        final.filter(pl.col("include_in_statement_view") == True)["amount_usd"].sum(),
    )


if __name__ == "__main__":
    main()
