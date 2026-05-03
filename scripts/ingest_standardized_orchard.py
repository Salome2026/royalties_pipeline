import hashlib
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import polars as pl

from lib.statement_period import from_column, legacy_manual


BASE_DIR = Path(r"C:\royalties_pipeline")

ORCHARD_INPUT_DIR = BASE_DIR / "input_raw" / "orchard"
ALTAFONTE_LEGACY_FILE = BASE_DIR / "input_raw" / "altafonte" / "altafonte.xlsx"

OUTPUT_PATH = BASE_DIR / "warehouse" / "marts" / "standardized_raw_orchard.parquet"
TEMP_DIR = BASE_DIR / "staging" / "standardized_raw_parts" / "orchard"

SOURCE = "orchard"
ORCHARD_STATEMENT_TYPE = "orchard_statement"
ALTAFONTE_STATEMENT_TYPE = "altafonte_legacy"
ALTAFONTE_ACCOUNT = "mawzrecords"


def ensure_dirs():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_orchard_csv(file_path: Path) -> pl.DataFrame:
    return pl.read_csv(
        file_path,
        separator=",",
        quote_char='"',
        ignore_errors=True,
        infer_schema_length=10000,
        encoding="utf8-lossy",
    )


def clean_columns(df: pl.DataFrame) -> pl.DataFrame:
    return df.rename({
        col: col.replace("\ufeff", "").replace('"', "").strip()
        for col in df.columns
    })


def decimal_expr(col: str) -> pl.Expr:
    return (
        pl.col(col)
        .cast(pl.Utf8)
        .str.replace_all(",", ".")
        .str.strip_chars()
        .replace("", None)
        .cast(pl.Float64, strict=False)
    )


def clean_amount(value) -> float:
    if pd.isna(value):
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if text == "":
        return 0.0

    text = (
        text.replace("US$", "")
        .replace("USD", "")
        .replace("$", "")
        .replace(" ", "")
        .strip()
    )

    if "," in text:
        text = text.replace(".", "").replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return 0.0


def normalize_month(value):
    if pd.isna(value):
        return None

    text = str(value).strip()

    if re.match(r"^20\d{2}-\d{2}$", text):
        return text

    dt = pd.to_datetime(value, errors="coerce")
    if not pd.isna(dt):
        return dt.strftime("%Y-%m")

    return None


def find_altafonte_header_row(raw: pd.DataFrame) -> int:
    for idx, row in raw.iterrows():
        values = [str(v).strip() for v in row.tolist()]
        if "Artista" in values:
            return idx

    raise ValueError("No encontre una fila de encabezados que contenga 'Artista'.")


def read_altafonte_legacy_excel(file_path: Path) -> pd.DataFrame:
    xl = pd.ExcelFile(file_path)

    preferred_sheets = [
        "altafonte",
        "Altafonte",
        "ALTAFONTE",
        "data_altafonte",
    ]

    sheet_to_use = next(
        (sheet for sheet in preferred_sheets if sheet in xl.sheet_names),
        xl.sheet_names[0],
    )

    raw = pd.read_excel(file_path, sheet_name=sheet_to_use, header=None)
    header_row = find_altafonte_header_row(raw)

    headers = raw.iloc[header_row].tolist()
    df = raw.iloc[header_row + 1:].copy()
    df.columns = [str(col).strip() if not pd.isna(col) else "" for col in headers]

    return df


def standardize_orchard(df: pl.DataFrame, file_path: Path) -> pl.DataFrame:
    df = clean_columns(df)

    file_hash = sha256_file(file_path)
    ingested_at = datetime.now().isoformat(timespec="seconds")
    statement_period_source, statement_period_note = from_column(
        "STATEMENT PERIOD",
        "Orchard modern files also include the period in filename, but the column is the authoritative source.",
    )
    amount = decimal_expr("NET SHARE ACCOUNT CURRENCY")

    return df.with_columns([
        amount.alias("amount_usd"),
        amount.alias("net_amount"),
        amount.alias("net_amount_usd"),

        pl.col("TRANSACTION DATE")
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.slice(0, 7)
        .alias("transaction_month"),

        pl.col("TRANSACTION DATE").alias("transaction_date"),

        pl.col("STATEMENT PERIOD")
        .str.strptime(pl.Date, format="%B %Y", strict=False)
        .dt.strftime("%Y-%m")
        .alias("statement_period"),

        pl.when(
            pl.col("TRACK ARTIST").is_not_null()
            & (pl.col("TRACK ARTIST").cast(pl.Utf8).str.strip_chars() != "")
        )
        .then(pl.col("TRACK ARTIST").cast(pl.Utf8))
        .otherwise(pl.col("PRODUCT ARTIST").cast(pl.Utf8))
        .alias("artist_statement_style"),

        pl.col("TRACK").alias("track_statement_style"),
        pl.col("ISRC").alias("asset_isrc"),
        pl.col("DISPLAY UPC").alias("product_upc"),

        pl.col("STORE").alias("store_name"),
        pl.col("SALE COUNTRY").alias("territory"),
        pl.col("SERVICE DETAIL").alias("service_detail"),

        decimal_expr("QUANTITY").alias("units"),

        pl.col("ACCOUNT NAME").cast(pl.Utf8).str.strip_chars().alias("account"),
        pl.col("LABEL IMPRINT").alias("label"),

        pl.lit(SOURCE).alias("source"),
        pl.lit(ORCHARD_STATEMENT_TYPE).alias("statement_type"),
        pl.lit(statement_period_source).alias("statement_period_source"),
        pl.lit(statement_period_note).alias("statement_period_note"),
        pl.lit(file_path.name).alias("statement_file_name"),
        pl.lit(str(file_path)).alias("statement_file_path"),
        pl.lit(file_hash).alias("statement_file_hash"),
        pl.lit(ingested_at).alias("ingested_at"),
    ])


def standardize_altafonte_legacy(file_path: Path) -> pl.DataFrame:
    df = read_altafonte_legacy_excel(file_path)

    if "Artista" not in df.columns:
        raise ValueError("No existe columna Artista en Altafonte legacy.")

    df = df[df["Artista"].notna()].copy()
    df["Artista"] = df["Artista"].astype(str).str.strip()

    df = df[df["Artista"] != ""]
    df = df[df["Artista"].str.lower() != "suma total"]
    df = df[df["Artista"].str.lower() != "grand total"]
    df = df[df["Artista"] != "0"]

    month_map = {}
    for col in df.columns:
        month = normalize_month(col)
        if month:
            month_map[col] = month

    if not month_map:
        raise ValueError("No detecte columnas de meses en Altafonte legacy.")

    file_hash = sha256_file(file_path)
    ingested_at = datetime.now().isoformat(timespec="seconds")
    statement_period_source, statement_period_note = legacy_manual(
        "Altafonte legacy has no per-row statement file period; period is inferred from legacy month columns."
    )
    records = []

    for _, row in df.iterrows():
        artist = str(row["Artista"]).strip()

        for col, month in month_map.items():
            amount = clean_amount(row[col])
            if amount == 0:
                continue

            records.append({
                "Artista": artist,
                "legacy_month_column": str(col),
                "legacy_amount_raw": None if pd.isna(row[col]) else str(row[col]),
                "amount_usd": amount,
                "net_amount": amount,
                "net_amount_usd": amount,
                "transaction_month": month,
                "transaction_date": None,
                "statement_period": month,
                "artist_statement_style": artist,
                "track_statement_style": None,
                "asset_isrc": None,
                "product_upc": None,
                "store_name": None,
                "territory": None,
                "service_detail": None,
                "units": None,
                "account": ALTAFONTE_ACCOUNT,
                "label": None,
                "source": SOURCE,
                "statement_type": ALTAFONTE_STATEMENT_TYPE,
                "statement_period_source": statement_period_source,
                "statement_period_note": statement_period_note,
                "statement_file_name": file_path.name,
                "statement_file_path": str(file_path),
                "statement_file_hash": file_hash,
                "ingested_at": ingested_at,
            })

    return pl.DataFrame(records)


def main():
    ensure_dirs()

    parts = []
    files = sorted(ORCHARD_INPUT_DIR.glob("*.csv"))

    print("Orchard standardized ingest")
    print(f"Archivos Orchard modernos: {len(files)}")

    for file_path in files:
        print(f"\nProcesando Orchard: {file_path.name}")

        try:
            df = read_orchard_csv(file_path)

            if df.height == 0:
                print("  vacio")
                continue

            df_std = standardize_orchard(df, file_path)

            part_path = TEMP_DIR / f"{file_path.stem}.parquet"
            df_std.write_parquet(part_path)
            parts.append(part_path)

            print(f"  OK filas: {df_std.height}")

        except Exception as e:
            print(f"  ERROR: {e}")

    if ALTAFONTE_LEGACY_FILE.exists():
        print(f"\nProcesando legacy Altafonte: {ALTAFONTE_LEGACY_FILE.name}")

        try:
            df_legacy = standardize_altafonte_legacy(ALTAFONTE_LEGACY_FILE)

            part_path = TEMP_DIR / f"{ALTAFONTE_LEGACY_FILE.stem}_legacy.parquet"
            df_legacy.write_parquet(part_path)
            parts.append(part_path)

            print(f"  OK filas: {df_legacy.height}")

        except Exception as e:
            print(f"  ERROR legacy Altafonte: {e}")
    else:
        print("\nNo existe archivo Altafonte legacy. Se omite.")

    if not parts:
        print("No se generaron datos")
        return

    print("\nConsolidando...")

    final = pl.concat([pl.read_parquet(part) for part in parts], how="diagonal_relaxed")
    final.write_parquet(OUTPUT_PATH)

    print("\nListo.")
    print(f"Archivo: {OUTPUT_PATH}")
    print(f"Filas: {final.height}")
    print(f"Total USD: {final['amount_usd'].sum()}")


if __name__ == "__main__":
    main()
