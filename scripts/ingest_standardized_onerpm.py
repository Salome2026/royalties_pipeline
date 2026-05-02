import hashlib
import shutil
from datetime import datetime
from pathlib import Path

import polars as pl

from lib.fx import get_monthly_fx, normalize_currency


BASE = Path(r"C:\royalties_pipeline")

INPUT_ROOT = BASE / "input_raw" / "onerpm"
OUTPUT_PATH = BASE / "warehouse" / "marts" / "standardized_raw_onerpm.parquet"
TEMP_DIR = BASE / "staging" / "standardized_raw_parts" / "onerpm"

SOURCE = "onerpm"
SHEET_MASTERS = "Masters"
SHEET_SHARES = "Shares In & Out"


ACCOUNTS = {
    "henry_remix": {
        "load_masters": True,
        "load_shares_as_rows": False,
        "use_shares_as_flags": False,
    },
    "gusty_dj": {
        "load_masters": True,
        "load_shares_as_rows": False,
        "use_shares_as_flags": True,
    },
    "mawzrecords": {
        "load_masters": True,
        "load_shares_as_rows": True,
        "use_shares_as_flags": False,
    },
}


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


def extract_statement_period(file_name: str) -> str:
    base = Path(file_name).stem
    if len(base) >= 7 and base[4] == "-" and base[7] == "-":
        return base[:7]
    return "unknown"


def clean_column_names(df: pl.DataFrame) -> pl.DataFrame:
    return df.rename({col: str(col).strip() for col in df.columns})


def normalize_decimal(col_name: str) -> pl.Expr:
    return (
        pl.col(col_name)
        .cast(pl.Utf8)
        .str.replace_all(",", ".")
        .str.strip_chars()
        .replace("", None)
        .cast(pl.Float64, strict=False)
    )


def normalize_numeric_columns(df: pl.DataFrame) -> pl.DataFrame:
    numeric_cols = [
        "Gross (Original Currency)",
        "Exchange Rate",
        "Gross",
        "Quantity",
        "Average Unit Gross",
        "% Share",
        "% Share In/Out",
        "Fees",
        "Net",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df = df.with_columns(normalize_decimal(col).alias(col))

    return df


def detect_transaction_month(df: pl.DataFrame) -> pl.DataFrame:
    possible_cols = [
        "Transaction Month",
        "Transaction month",
        "Sales Month",
        "Month",
        "Reporting Period",
    ]

    found_col = next((col for col in possible_cols if col in df.columns), None)

    if found_col:
        return df.with_columns(
            pl.col(found_col)
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.slice(0, 7)
            .alias("transaction_month")
        )

    return df.with_columns(pl.lit(None).cast(pl.Utf8).alias("transaction_month"))


def get_or_fetch_avg_to_usd_rate(statement_period: str, from_currency: str):
    currency = normalize_currency(from_currency)

    if currency in ["", "NONE", "NULL", "NAN"]:
        return None

    if statement_period == "unknown":
        return None

    return get_monthly_fx(
        fx_month=statement_period,
        from_currency=currency,
        to_currency="USD",
    )


def add_usd_conversion(df: pl.DataFrame, statement_period: str) -> pl.DataFrame:
    if "Currency" not in df.columns:
        return df.with_columns([
            pl.lit(None).cast(pl.Utf8).alias("currency_original"),
            pl.lit(None).cast(pl.Float64).alias("fx_to_usd_rate"),
            pl.lit(statement_period).alias("fx_rate_date"),
            pl.col("net_amount").alias("net_amount_usd"),
        ])

    df = df.with_columns(
        pl.col("Currency")
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.to_uppercase()
        .replace({"RUR": "RUB"})
        .alias("currency_original")
    )

    currencies = (
        df.select("currency_original")
        .drop_nulls()
        .unique()
        .get_column("currency_original")
        .to_list()
    )

    rate_rows = []
    for currency in currencies:
        rate_rows.append({
            "currency_original": currency,
            "fx_to_usd_rate": get_or_fetch_avg_to_usd_rate(statement_period, currency),
        })

    if not rate_rows:
        return df.with_columns([
            pl.lit(None).cast(pl.Float64).alias("fx_to_usd_rate"),
            pl.lit(statement_period).alias("fx_rate_date"),
            pl.lit(None).cast(pl.Float64).alias("net_amount_usd"),
        ])

    fx_df = pl.DataFrame(rate_rows)

    return (
        df
        .join(fx_df, on="currency_original", how="left")
        .with_columns([
            pl.lit(statement_period).alias("fx_rate_date"),
            (pl.col("net_amount") * pl.col("fx_to_usd_rate")).alias("net_amount_usd"),
        ])
    )


def build_artist_statement_style_from_masters(df: pl.DataFrame) -> pl.DataFrame:
    if "Artists" not in df.columns:
        return df.with_columns(pl.lit(None).cast(pl.Utf8).alias("artist_statement_style"))

    result = []

    for raw in df.get_column("Artists").to_list():
        if raw is None:
            result.append(None)
            continue

        parts = [part.strip() for part in str(raw).split(",")]
        performers = []

        for part in parts:
            if "(performer)" in part.lower():
                cleaned = (
                    part.replace("(performer)", "")
                    .replace("(Performer)", "")
                    .strip()
                )
                if cleaned:
                    performers.append(cleaned)

        result.append(", ".join(performers) if performers else None)

    return df.with_columns(pl.Series("artist_statement_style", result))


def prepare_share_flags(df_shares: pl.DataFrame) -> pl.DataFrame:
    if df_shares.height == 0:
        return empty_share_flags()

    df_shares = clean_column_names(df_shares)

    if "ID" not in df_shares.columns and "Parent ID" not in df_shares.columns:
        return empty_share_flags()

    df_shares = normalize_numeric_columns(df_shares)
    key_frames = []

    for col in ["ID", "Parent ID"]:
        if col in df_shares.columns:
            key_frames.append(
                df_shares.with_columns(
                    pl.col(col)
                    .cast(pl.Utf8)
                    .str.strip_chars()
                    .str.to_uppercase()
                    .alias("share_match_key")
                )
            )

    shares_keys = pl.concat(key_frames, how="diagonal_relaxed").filter(
        pl.col("share_match_key").is_not_null()
        & (pl.col("share_match_key") != "")
        & (pl.col("share_match_key") != "NULL")
        & (pl.col("share_match_key") != "NAN")
    )

    if shares_keys.height == 0:
        return empty_share_flags()

    share_type_col = next(
        (col for col in ["Share Type", "Share type", "Type", "Movement Type"] if col in shares_keys.columns),
        None,
    )

    if share_type_col:
        shares_keys = shares_keys.with_columns(
            pl.col(share_type_col)
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("_share_type_norm")
        )
    else:
        shares_keys = shares_keys.with_columns(pl.lit("").alias("_share_type_norm"))

    return (
        shares_keys
        .group_by("share_match_key")
        .agg([
            pl.col("_share_type_norm").str.contains("in", literal=False).sum().alias("share_in_count"),
            pl.col("_share_type_norm").str.contains("out", literal=False).sum().alias("share_out_count"),
            pl.len().alias("share_total_count"),
        ])
    )


def empty_share_flags() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "share_match_key": pl.Utf8,
            "share_in_count": pl.Int64,
            "share_out_count": pl.Int64,
            "share_total_count": pl.Int64,
        }
    )


def add_share_flags_to_masters(df_masters: pl.DataFrame, df_shares: pl.DataFrame) -> pl.DataFrame:
    df_masters = clean_column_names(df_masters)
    flags = prepare_share_flags(df_shares)

    if flags.height == 0:
        return df_masters.with_columns([
            pl.lit(False).alias("has_share_in_out"),
            pl.lit(0).cast(pl.Int64).alias("share_in_count"),
            pl.lit(0).cast(pl.Int64).alias("share_out_count"),
            pl.lit(0).cast(pl.Int64).alias("share_total_count"),
            pl.lit("").alias("share_note"),
        ])

    key_frames = []

    for col in ["ISRC", "UPC"]:
        if col in df_masters.columns:
            key_frames.append(
                df_masters
                .with_row_index("_master_row_id")
                .select([
                    "_master_row_id",
                    pl.col(col)
                    .cast(pl.Utf8)
                    .str.strip_chars()
                    .str.to_uppercase()
                    .alias("share_match_key"),
                ])
            )

    if not key_frames:
        return df_masters.with_columns([
            pl.lit(False).alias("has_share_in_out"),
            pl.lit(0).cast(pl.Int64).alias("share_in_count"),
            pl.lit(0).cast(pl.Int64).alias("share_out_count"),
            pl.lit(0).cast(pl.Int64).alias("share_total_count"),
            pl.lit("No hay ISRC/UPC en Masters para matchear Shares").alias("share_note"),
        ])

    matched = (
        pl.concat(key_frames, how="diagonal_relaxed")
        .filter(
            pl.col("share_match_key").is_not_null()
            & (pl.col("share_match_key") != "")
            & (pl.col("share_match_key") != "NULL")
            & (pl.col("share_match_key") != "NAN")
        )
        .join(flags, on="share_match_key", how="left")
        .group_by("_master_row_id")
        .agg([
            pl.col("share_in_count").fill_null(0).sum().alias("share_in_count"),
            pl.col("share_out_count").fill_null(0).sum().alias("share_out_count"),
            pl.col("share_total_count").fill_null(0).sum().alias("share_total_count"),
        ])
    )

    df_masters = (
        df_masters
        .with_row_index("_master_row_id")
        .join(matched, on="_master_row_id", how="left")
        .with_columns([
            pl.col("share_in_count").fill_null(0).cast(pl.Int64),
            pl.col("share_out_count").fill_null(0).cast(pl.Int64),
            pl.col("share_total_count").fill_null(0).cast(pl.Int64),
        ])
        .with_columns([
            (pl.col("share_total_count") > 0).alias("has_share_in_out"),
            pl.when(pl.col("share_total_count") > 0)
            .then(
                pl.concat_str([
                    pl.lit("Revisar Shares In/Out - In: "),
                    pl.col("share_in_count").cast(pl.Utf8),
                    pl.lit(" / Out: "),
                    pl.col("share_out_count").cast(pl.Utf8),
                    pl.lit(" / Total: "),
                    pl.col("share_total_count").cast(pl.Utf8),
                ])
            )
            .otherwise(pl.lit(""))
            .alias("share_note"),
        ])
        .drop("_master_row_id")
    )

    return df_masters


def add_view_flags(df: pl.DataFrame, account: str, source_sheet: str) -> pl.DataFrame:
    is_master = source_sheet == SHEET_MASTERS
    is_share = source_sheet == SHEET_SHARES

    include_in_statement_view = account in ["henry_remix", "mawzrecords"]
    include_in_cash_view = account in ["henry_remix", "mawzrecords"]
    include_in_catalog_view = is_master
    possible_internal_transfer = account == "mawzrecords" and is_share

    if account == "gusty_dj":
        revenue_basis = "master_earning_external_account"
    elif is_share:
        revenue_basis = "share_transfer"
    else:
        revenue_basis = "master_earning"

    return df.with_columns([
        pl.lit(revenue_basis).alias("revenue_basis"),
        pl.lit(include_in_statement_view).alias("include_in_statement_view"),
        pl.lit(include_in_cash_view).alias("include_in_cash_view"),
        pl.lit(include_in_catalog_view).alias("include_in_catalog_view"),
        pl.lit(possible_internal_transfer).alias("possible_internal_transfer"),
    ])


def finalize_amounts(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        pl.coalesce([pl.col("net_amount_usd"), pl.col("net_amount")]).alias("amount_usd")
    )


def standardize_masters(
    df: pl.DataFrame,
    file_path: Path,
    account: str,
    file_hash: str,
    df_shares_for_flags: pl.DataFrame | None = None,
) -> pl.DataFrame:
    statement_period = extract_statement_period(file_path.name)
    ingested_at = datetime.now().isoformat(timespec="seconds")

    df = clean_column_names(df)

    if df_shares_for_flags is not None:
        df = add_share_flags_to_masters(df, df_shares_for_flags)

    df = normalize_numeric_columns(df)
    df = detect_transaction_month(df)
    df = build_artist_statement_style_from_masters(df)

    if "Net" not in df.columns:
        raise ValueError("La hoja Masters no tiene columna Net.")

    df = df.rename({"Net": "net_amount"})
    df = add_usd_conversion(df, statement_period)

    if "Artists" in df.columns:
        df = df.rename({"Artists": "artists_raw"})

    df = df.with_columns([
        pl.lit(SOURCE).alias("source"),
        pl.lit(account).alias("account"),
        pl.lit(SHEET_MASTERS).alias("source_sheet"),
        pl.lit(file_path.name).alias("statement_file_name"),
        pl.lit(str(file_path)).alias("statement_file_path"),
        pl.lit(file_hash).alias("statement_file_hash"),
        pl.lit(statement_period).alias("statement_period"),
        pl.lit(ingested_at).alias("ingested_at"),
    ])

    if "has_share_in_out" not in df.columns:
        df = df.with_columns([
            pl.lit(False).alias("has_share_in_out"),
            pl.lit(0).cast(pl.Int64).alias("share_in_count"),
            pl.lit(0).cast(pl.Int64).alias("share_out_count"),
            pl.lit(0).cast(pl.Int64).alias("share_total_count"),
            pl.lit("").alias("share_note"),
        ])

    df = add_view_flags(df, account, SHEET_MASTERS)
    return finalize_amounts(df)


def standardize_shares(df: pl.DataFrame, file_path: Path, account: str, file_hash: str) -> pl.DataFrame:
    statement_period = extract_statement_period(file_path.name)
    ingested_at = datetime.now().isoformat(timespec="seconds")

    df = clean_column_names(df)
    df = normalize_numeric_columns(df)
    df = detect_transaction_month(df)

    if "Net" not in df.columns:
        raise ValueError("La hoja Shares In & Out no tiene columna Net.")

    if "Payer Name" not in df.columns:
        raise ValueError("La hoja Shares In & Out no tiene columna Payer Name.")

    df = df.rename({"Net": "net_amount"})
    df = df.with_columns(
        pl.col("Payer Name")
        .cast(pl.Utf8)
        .str.strip_chars()
        .alias("artist_statement_style")
    )
    df = add_usd_conversion(df, statement_period)

    if "Artists" in df.columns:
        df = df.rename({"Artists": "artists_raw"})

    df = df.with_columns([
        pl.lit(SOURCE).alias("source"),
        pl.lit(account).alias("account"),
        pl.lit(SHEET_SHARES).alias("source_sheet"),
        pl.lit(file_path.name).alias("statement_file_name"),
        pl.lit(str(file_path)).alias("statement_file_path"),
        pl.lit(file_hash).alias("statement_file_hash"),
        pl.lit(statement_period).alias("statement_period"),
        pl.lit(ingested_at).alias("ingested_at"),
        pl.lit(False).alias("has_share_in_out"),
        pl.lit(0).cast(pl.Int64).alias("share_in_count"),
        pl.lit(0).cast(pl.Int64).alias("share_out_count"),
        pl.lit(0).cast(pl.Int64).alias("share_total_count"),
        pl.lit("").alias("share_note"),
    ])

    df = add_view_flags(df, account, SHEET_SHARES)
    return finalize_amounts(df)


def read_excel_sheet(file_path: Path, sheet_name: str) -> pl.DataFrame:
    return pl.read_excel(file_path, sheet_name=sheet_name)


def process_account(account: str, config: dict) -> list[Path]:
    input_dir = INPUT_ROOT / account
    account_parts = []

    if not input_dir.exists():
        print(f"\nNo existe carpeta ONErpm {account}: {input_dir}")
        return account_parts

    files = sorted([
        path for path in input_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in [".xlsx", ".xlsm"]
        and not path.name.startswith("~$")
    ])

    print(f"\nONErpm {account}: {len(files)} archivo(s)")

    for file_path in files:
        print(f"  Procesando: {file_path.name}")
        file_hash = sha256_file(file_path)
        frames = []

        df_shares_raw = None

        if config["use_shares_as_flags"]:
            try:
                df_shares_raw = read_excel_sheet(file_path, SHEET_SHARES)
            except Exception:
                df_shares_raw = pl.DataFrame()

        if config["load_masters"]:
            try:
                df_masters = read_excel_sheet(file_path, SHEET_MASTERS)
                df_masters = standardize_masters(
                    df=df_masters,
                    file_path=file_path,
                    account=account,
                    file_hash=file_hash,
                    df_shares_for_flags=df_shares_raw,
                )
                frames.append(df_masters)
                print(f"    Masters OK: {df_masters.height}")
            except Exception as e:
                print(f"    Masters ERROR: {e}")

        if config["load_shares_as_rows"]:
            try:
                df_shares = read_excel_sheet(file_path, SHEET_SHARES)
                if df_shares.height > 0:
                    df_shares = standardize_shares(df_shares, file_path, account, file_hash)
                    frames.append(df_shares)
                    print(f"    Shares OK: {df_shares.height}")
                else:
                    print("    Shares vacio")
            except Exception as e:
                print(f"    Shares ERROR: {e}")

        if not frames:
            print("    Sin datos utiles")
            continue

        file_df = pl.concat(frames, how="diagonal_relaxed")
        part_path = TEMP_DIR / account / f"{file_path.stem}.parquet"
        part_path.parent.mkdir(parents=True, exist_ok=True)
        file_df.write_parquet(part_path)
        account_parts.append(part_path)

    return account_parts


def main():
    ensure_dirs()

    print("ONErpm standardized ingest")
    print("Output:", OUTPUT_PATH)

    parts = []

    for account, config in ACCOUNTS.items():
        parts.extend(process_account(account, config))

    if not parts:
        print("\nNo se generaron datos.")
        return

    print("\nConsolidando ONErpm...")
    final = pl.concat([pl.read_parquet(part) for part in parts], how="diagonal_relaxed")
    final.write_parquet(OUTPUT_PATH)

    print("\nListo.")
    print(f"Archivo: {OUTPUT_PATH}")
    print(f"Filas: {final.height}")
    print(f"Total amount_usd: {final['amount_usd'].sum()}")


if __name__ == "__main__":
    main()
