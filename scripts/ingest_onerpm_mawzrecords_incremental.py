import hashlib
import calendar
from datetime import datetime, date
from pathlib import Path

import polars as pl
import requests


# =========================
# CONFIG
# =========================
INPUT_DIR = Path(r"C:\royalties_pipeline\input_raw\onerpm\mawzrecords")
REGISTRY_PATH = Path(r"C:\royalties_pipeline\warehouse\registry\processed_files.parquet")
DETAIL_PATH = Path(r"C:\royalties_pipeline\warehouse\detail\royalties_detail.parquet")
FX_PATH = Path(r"C:\royalties_pipeline\warehouse\registry\exchange_rates.parquet")

SOURCE = "onerpm"
ACCOUNT = "mawzrecords"

SHEET_MASTERS = "Masters"
SHEET_SHARES = "Shares In & Out"


# =========================
# HELPERS
# =========================
def ensure_dirs():
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    DETAIL_PATH.parent.mkdir(parents=True, exist_ok=True)
    FX_PATH.parent.mkdir(parents=True, exist_ok=True)


def sha256_file(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_registry() -> pl.DataFrame:
    if REGISTRY_PATH.exists():
        return pl.read_parquet(REGISTRY_PATH)

    return pl.DataFrame(
        schema={
            "file_hash": pl.Utf8,
            "file_name": pl.Utf8,
            "file_path": pl.Utf8,
            "source": pl.Utf8,
            "account": pl.Utf8,
            "sheet_name": pl.Utf8,
            "statement_period": pl.Utf8,
            "processed_at": pl.Utf8,
            "row_count": pl.Int64,
        }
    )


def save_registry(df: pl.DataFrame):
    df.write_parquet(REGISTRY_PATH)


def load_detail() -> pl.DataFrame:
    if DETAIL_PATH.exists():
        return pl.read_parquet(DETAIL_PATH)
    return pl.DataFrame()


def save_detail(df: pl.DataFrame):
    df.write_parquet(DETAIL_PATH)


def load_fx_table() -> pl.DataFrame:
    if FX_PATH.exists():
        return pl.read_parquet(FX_PATH)

    return pl.DataFrame(
        schema={
            "fx_month": pl.Utf8,
            "from_currency": pl.Utf8,
            "to_currency": pl.Utf8,
            "rate_type": pl.Utf8,
            "rate": pl.Float64,
            "source": pl.Utf8,
            "fetched_at": pl.Utf8,
        }
    )


def save_fx_table(df: pl.DataFrame):
    df.write_parquet(FX_PATH)


def extract_statement_period(file_name: str) -> str:
    base = Path(file_name).stem

    # Ej: 2025-09-01 00_00_00-details.xlsx -> 2025-09
    if len(base) >= 7 and base[4] == "-" and base[7] == "-":
        return base[:7]

    return "unknown"


def normalize_decimal(col_name: str) -> pl.Expr:
    return (
        pl.col(col_name)
        .cast(pl.Utf8)
        .str.replace_all(",", ".")
        .str.strip_chars()
        .replace("", None)
        .cast(pl.Float64, strict=False)
    )


def clean_column_names(df: pl.DataFrame) -> pl.DataFrame:
    return df.rename({col: col.strip() for col in df.columns})


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

    found_col = None

    for col in possible_cols:
        if col in df.columns:
            found_col = col
            break

    if found_col:
        return df.with_columns(
            pl.col(found_col)
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.slice(0, 7)
            .alias("transaction_month")
        )

    return df.with_columns(pl.lit(None).alias("transaction_month"))


# =========================
# FX
# =========================
def fetch_avg_to_usd_rate(statement_period: str, from_currency: str) -> float:
    from_currency = from_currency.upper().strip()

    if from_currency == "USD":
        return 1.0

    if statement_period == "unknown":
        raise ValueError("No se pudo detectar statement_period para calcular FX.")

    print(f"  - Buscando FX promedio {from_currency}/USD para {statement_period}...")

    year, month = map(int, statement_period.split("-"))
    last_day = calendar.monthrange(year, month)[1]

    rates = []

    for day in range(1, last_day + 1):
        rate_date = date(year, month, day).isoformat()
        url = f"https://api.frankfurter.dev/v2/rates?date={rate_date}&base={from_currency}&quotes=USD"

        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()

            if isinstance(data, list) and len(data) > 0 and "rate" in data[0]:
                rates.append(float(data[0]["rate"]))

        except Exception:
            continue

    if not rates:
        raise ValueError(f"No se encontraron tasas {from_currency}/USD para {statement_period}")

    avg_rate = sum(rates) / len(rates)

    print(f"  - FX promedio {from_currency}/USD {statement_period}: {avg_rate}")

    return avg_rate


def get_or_fetch_avg_to_usd_rate(statement_period: str, from_currency: str) -> float:
    from_currency = str(from_currency).upper().strip()

    if from_currency == "" or from_currency == "NONE":
        return None

    if from_currency == "USD":
        return 1.0

    fx_table = load_fx_table()

    existing = fx_table.filter(
        (pl.col("fx_month") == statement_period) &
        (pl.col("from_currency") == from_currency) &
        (pl.col("to_currency") == "USD") &
        (pl.col("rate_type") == "monthly_avg")
    )

    if existing.height > 0:
        rate = float(existing.select("rate").item())
        print(f"  - FX cacheado {from_currency}/USD {statement_period}: {rate}")
        return rate

    rate = fetch_avg_to_usd_rate(statement_period, from_currency)

    new_row = pl.DataFrame([{
        "fx_month": statement_period,
        "from_currency": from_currency,
        "to_currency": "USD",
        "rate_type": "monthly_avg",
        "rate": rate,
        "source": "frankfurter",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }])

    fx_table = pl.concat([fx_table, new_row], how="diagonal_relaxed")
    save_fx_table(fx_table)

    return rate


def add_usd_conversion(df: pl.DataFrame, statement_period: str) -> pl.DataFrame:
    if "Currency" not in df.columns:
        return df.with_columns([
            pl.lit("USD").alias("currency_original"),
            pl.col("net_amount").alias("net_amount_usd"),
            pl.lit(statement_period).alias("fx_rate_date"),
            pl.lit(1.0).alias("fx_to_usd_rate"),
        ])

    df = df.with_columns(
        pl.col("Currency")
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.to_uppercase()
        .alias("currency_original")
    )

    currencies = (
        df.select("currency_original")
        .drop_nulls()
        .unique()
        .get_column("currency_original")
        .to_list()
    )

    fx_map = {}

    for currency in currencies:
        if currency in [None, ""]:
            continue
        fx_map[currency] = get_or_fetch_avg_to_usd_rate(statement_period, currency)

    rate_rows = [
        {"currency_original": currency, "fx_to_usd_rate": rate}
        for currency, rate in fx_map.items()
    ]

    fx_df = pl.DataFrame(rate_rows)

    if fx_df.height == 0:
        return df.with_columns([
            pl.lit(None).cast(pl.Float64).alias("fx_to_usd_rate"),
            pl.lit(statement_period).alias("fx_rate_date"),
            pl.lit(None).cast(pl.Float64).alias("net_amount_usd"),
        ])

    df = df.join(fx_df, on="currency_original", how="left")

    df = df.with_columns([
        pl.lit(statement_period).alias("fx_rate_date"),
        (pl.col("net_amount") * pl.col("fx_to_usd_rate")).alias("net_amount_usd"),
    ])

    return df


# =========================
# ARTIST LOGIC
# =========================
def build_artist_statement_style_from_masters(df: pl.DataFrame) -> pl.DataFrame:
    if "Artists" not in df.columns:
        return df.with_columns(pl.lit(None).alias("artist_statement_style"))

    artist_values = df.get_column("Artists").to_list()
    result = []

    for raw in artist_values:
        if raw is None:
            result.append(None)
            continue

        parts = [p.strip() for p in str(raw).split(",")]
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

        artist = ", ".join(performers) if performers else None
        result.append(artist)

    return df.with_columns(pl.Series("artist_statement_style", result))


# =========================
# STANDARDIZE
# =========================
def standardize_masters(df: pl.DataFrame, file_path: Path, file_hash: str) -> pl.DataFrame:
    statement_period = extract_statement_period(file_path.name)
    ingested_at = datetime.now().isoformat(timespec="seconds")

    df = clean_column_names(df)
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
        pl.lit(ACCOUNT).alias("account"),
        pl.lit(SHEET_MASTERS).alias("source_sheet"),
        pl.lit(file_path.name).alias("statement_file_name"),
        pl.lit(str(file_path)).alias("statement_file_path"),
        pl.lit(file_hash).alias("statement_file_hash"),
        pl.lit(statement_period).alias("statement_period"),
        pl.lit(ingested_at).alias("ingested_at"),
    ])

    return df


def standardize_shares(df: pl.DataFrame, file_path: Path, file_hash: str) -> pl.DataFrame:
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
        pl.lit(ACCOUNT).alias("account"),
        pl.lit(SHEET_SHARES).alias("source_sheet"),
        pl.lit(file_path.name).alias("statement_file_name"),
        pl.lit(str(file_path)).alias("statement_file_path"),
        pl.lit(file_hash).alias("statement_file_hash"),
        pl.lit(statement_period).alias("statement_period"),
        pl.lit(ingested_at).alias("ingested_at"),
    ])

    return df


def read_excel_sheet(file_path: Path, sheet_name: str) -> pl.DataFrame:
    return pl.read_excel(file_path, sheet_name=sheet_name)


# =========================
# MAIN
# =========================
def main():
    ensure_dirs()

    if not INPUT_DIR.exists():
        print(f"No existe la carpeta de input: {INPUT_DIR}")
        return

    registry = load_registry()
    existing_hashes = set(registry["file_hash"].to_list()) if registry.height > 0 else set()

    detail_existing = load_detail()

    new_detail_frames = []
    registry_rows = []

    excel_files = sorted([
        p for p in INPUT_DIR.iterdir()
        if p.is_file()
        and p.suffix.lower() in [".xlsx", ".xlsm"]
        and not p.name.startswith("~$")
    ])

    if not excel_files:
        print("No se encontraron archivos Excel.")
        return

    print(f"Se encontraron {len(excel_files)} archivo(s) ONErpm MAWZ.")

    for file_path in excel_files:
        print(f"\nRevisando: {file_path.name}")

        file_hash = sha256_file(file_path)

        if file_hash in existing_hashes:
            print("  - Ya procesado (mismo contenido). Se omite.")
            continue

        file_frames = []
        row_count = 0
        sheets_processed = []

        try:
            df_masters = read_excel_sheet(file_path, SHEET_MASTERS)
            df_masters = standardize_masters(df_masters, file_path, file_hash)

            file_frames.append(df_masters)
            row_count += df_masters.height
            sheets_processed.append(SHEET_MASTERS)

            print(f"  - Masters procesado OK. Filas: {df_masters.height}")

        except Exception as e:
            print(f"  - Masters no procesado: {e}")

        try:
            df_shares = read_excel_sheet(file_path, SHEET_SHARES)
            df_shares = standardize_shares(df_shares, file_path, file_hash)

            file_frames.append(df_shares)
            row_count += df_shares.height
            sheets_processed.append(SHEET_SHARES)

            print(f"  - Shares In & Out procesado OK. Filas: {df_shares.height}")

        except Exception as e:
            print(f"  - Shares In & Out no procesado: {e}")

        if not file_frames:
            print("  - No se pudo procesar ninguna hoja útil. Se omite archivo.")
            continue

        file_detail = pl.concat(file_frames, how="diagonal_relaxed")
        new_detail_frames.append(file_detail)

        registry_rows.append({
            "file_hash": file_hash,
            "file_name": file_path.name,
            "file_path": str(file_path),
            "source": SOURCE,
            "account": ACCOUNT,
            "sheet_name": " + ".join(sheets_processed),
            "statement_period": extract_statement_period(file_path.name),
            "processed_at": datetime.now().isoformat(timespec="seconds"),
            "row_count": row_count,
        })

        existing_hashes.add(file_hash)

        print(f"  - Archivo procesado OK. Filas totales: {row_count}")
        print(f"  - Hojas procesadas: {', '.join(sheets_processed)}")

    if not new_detail_frames:
        print("\nNo hubo archivos nuevos para agregar.")
        return

    detail_new = pl.concat(new_detail_frames, how="diagonal_relaxed")

    if detail_existing.height > 0:
        detail_final = pl.concat([detail_existing, detail_new], how="diagonal_relaxed")
    else:
        detail_final = detail_new

    save_detail(detail_final)

    registry_new = pl.DataFrame(registry_rows)

    if registry.height > 0:
        registry_final = pl.concat([registry, registry_new], how="diagonal_relaxed")
    else:
        registry_final = registry_new

    save_registry(registry_final)

    print("\nListo.")
    print(f"Detalle consolidado: {DETAIL_PATH}")
    print(f"Registry actualizado: {REGISTRY_PATH}")
    print(f"Filas nuevas agregadas: {detail_new.height}")


if __name__ == "__main__":
    main()