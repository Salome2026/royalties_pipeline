import hashlib
import calendar
from datetime import datetime, date
from pathlib import Path

import polars as pl
import requests


INPUT_DIR = Path(r"C:\royalties_pipeline\input_raw\fuga")
REGISTRY_PATH = Path(r"C:\royalties_pipeline\warehouse\registry\processed_files.parquet")
DETAIL_PATH = Path(r"C:\royalties_pipeline\warehouse\detail\royalties_detail.parquet")

SOURCE = "fuga"
ACCOUNT = "indyana_records"
FX_PATH = Path(r"C:\royalties_pipeline\warehouse\registry\exchange_rates.parquet")

def ensure_dirs():
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    DETAIL_PATH.parent.mkdir(parents=True, exist_ok=True)


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


def load_detail() -> pl.DataFrame:
    if DETAIL_PATH.exists():
        return pl.read_parquet(DETAIL_PATH)
    return pl.DataFrame()


def save_registry(df: pl.DataFrame):
    df.write_parquet(REGISTRY_PATH)


def save_detail(df: pl.DataFrame):
    df.write_parquet(DETAIL_PATH)


def extract_statement_period(file_name: str) -> str:
    name = file_name.lower()

    months = {
        "january": "01",
        "february": "02",
        "march": "03",
        "april": "04",
        "may": "05",
        "june": "06",
        "july": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "november": "11",
        "december": "12",
    }

    for month_name, month_num in months.items():
        if month_name in name:
            pos = name.find(month_name)
            after_month = name[pos + len(month_name):]
            year = after_month[:4]

            if year.isdigit():
                return f"{year}-{month_num}"

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


def fetch_avg_eur_usd_rate(statement_period: str) -> float:
    print(f"  - Buscando FX promedio EUR/USD para {statement_period}...")

    year, month = map(int, statement_period.split("-"))
    last_day = calendar.monthrange(year, month)[1]

    rates = []

    for day in range(1, last_day + 1):
        rate_date = date(year, month, day).isoformat()
        url = f"https://api.frankfurter.dev/v2/rates?date={rate_date}&base=EUR&quotes=USD"

        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            data = r.json()

            if isinstance(data, list) and len(data) > 0 and "rate" in data[0]:
                rates.append(float(data[0]["rate"]))

        except Exception:
            continue

    if not rates:
        raise ValueError(f"No se encontraron tasas EUR/USD para {statement_period}")

    avg_rate = sum(rates) / len(rates)

    print(f"  - FX promedio {statement_period}: {avg_rate}")

    return avg_rate


def get_or_fetch_avg_eur_usd_rate(statement_period: str) -> float:
    fx_table = load_fx_table()

    existing = fx_table.filter(
        (pl.col("fx_month") == statement_period) &
        (pl.col("from_currency") == "EUR") &
        (pl.col("to_currency") == "USD") &
        (pl.col("rate_type") == "monthly_avg")
    )

    if existing.height > 0:
        rate = float(existing.select("rate").item())
        print(f"  - FX cacheado {statement_period}: {rate}")
        return rate

    rate = fetch_avg_eur_usd_rate(statement_period)

    new_row = pl.DataFrame([{
        "fx_month": statement_period,
        "from_currency": "EUR",
        "to_currency": "USD",
        "rate_type": "monthly_avg",
        "rate": rate,
        "source": "frankfurter",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }])

    fx_table = pl.concat([fx_table, new_row], how="diagonal_relaxed")
    save_fx_table(fx_table)

    return rate

def last_day_of_statement(statement_period: str) -> str:
    if statement_period == "unknown":
        raise ValueError("No se pudo detectar statement_period desde el nombre del archivo")

    year, month = map(int, statement_period.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day).isoformat()


def get_month_dates(statement_period: str) -> tuple[str, str]:
    year, month = map(int, statement_period.split("-"))
    first_day = date(year, month, 1).isoformat()
    last_day = date(year, month, calendar.monthrange(year, month)[1]).isoformat()
    return first_day, last_day


def get_avg_eur_usd_rate(statement_period: str) -> float:
    year, month = map(int, statement_period.split("-"))
    last_day = calendar.monthrange(year, month)[1]

    rates = []

    for day in range(1, last_day + 1):
        rate_date = date(year, month, day).isoformat()

        url = f"https://api.frankfurter.dev/v2/rates?date={rate_date}&base=EUR&quotes=USD"

        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()

            data = r.json()

            if isinstance(data, list) and len(data) > 0 and "rate" in data[0]:
                rates.append(float(data[0]["rate"]))

        except Exception:
            # fines de semana, feriados o días sin cotización
            continue

    if not rates:
        raise ValueError(f"No se encontraron tasas EUR/USD para {statement_period}")

    return sum(rates) / len(rates)


def standardize_fuga(df: pl.DataFrame, file_path: Path, file_hash: str) -> pl.DataFrame:
    statement_period = extract_statement_period(file_path.name)
    ingested_at = datetime.now().isoformat(timespec="seconds")

    fx_rate_date = statement_period
    fx_eur_usd_rate = get_or_fetch_avg_eur_usd_rate(statement_period)

    df = df.rename({col: col.strip() for col in df.columns})

    royalty_eur = normalize_decimal("Reported Royalty")

    df = df.with_columns([
        royalty_eur.alias("net_amount"),  # EUR original de FUGA, se mantiene por compatibilidad
        royalty_eur.alias("net_amount_eur"),
        pl.lit(fx_rate_date).alias("fx_rate_date"),
        pl.lit(fx_eur_usd_rate).alias("fx_eur_usd_rate"),
        (royalty_eur * fx_eur_usd_rate).alias("net_amount_usd"),

        pl.when(
            pl.col("Product Artist").is_not_null()
            & (pl.col("Product Artist").cast(pl.Utf8).str.strip_chars() != "")
        )
        .then(pl.col("Product Artist").cast(pl.Utf8))
        .otherwise(pl.col("Product Title").cast(pl.Utf8))
        .alias("artist_statement_style"),

        pl.col("Sale Start date")
        .cast(pl.Utf8)
        .str.slice(0, 7)
        .alias("transaction_month"),

        pl.lit(SOURCE).alias("source"),
        pl.lit(ACCOUNT).alias("account"),
        pl.lit(file_path.name).alias("statement_file_name"),
        pl.lit(str(file_path)).alias("statement_file_path"),
        pl.lit(file_hash).alias("statement_file_hash"),
        pl.lit(statement_period).alias("statement_period"),
        pl.lit(ingested_at).alias("ingested_at"),
    ])

    return df


def read_fuga_csv(file_path: Path) -> pl.DataFrame:
    return pl.read_csv(
        file_path,
        separator=",",
        quote_char='"',
        ignore_errors=True,
        infer_schema_length=10000,
    )


def main():
    ensure_dirs()

    if not INPUT_DIR.exists():
        print(f"No existe la carpeta: {INPUT_DIR}")
        return

    registry = load_registry()
    existing_hashes = set(registry["file_hash"].to_list()) if registry.height > 0 else set()

    detail_existing = load_detail()

    new_frames = []
    registry_rows = []

    csv_files = sorted([
    p for p in INPUT_DIR.glob("*.csv")
    if "correction" not in p.name.lower()
    ])

    if not csv_files:
        print("No se encontraron archivos CSV en input_raw\\fuga")
        return

    print(f"Se encontraron {len(csv_files)} archivo(s) FUGA.")

    for file_path in csv_files:
        print(f"\nRevisando: {file_path.name}")

        file_hash = sha256_file(file_path)

        if file_hash in existing_hashes:
            print("  - Ya procesado. Se omite.")
            continue

        try:
            df = read_fuga_csv(file_path)
            df = standardize_fuga(df, file_path, file_hash)

            row_count = df.height
            new_frames.append(df)

            registry_rows.append({
                "file_hash": file_hash,
                "file_name": file_path.name,
                "file_path": str(file_path),
                "source": SOURCE,
                "account": ACCOUNT,
                "sheet_name": None,
                "statement_period": extract_statement_period(file_path.name),
                "processed_at": datetime.now().isoformat(timespec="seconds"),
                "row_count": row_count,
            })

            print(f"  - Procesado OK. Filas: {row_count}")

        except Exception as e:
            print(f"  - Error procesando {file_path.name}: {e}")

    if not new_frames:
        print("\nNo hubo archivos nuevos para agregar.")
        return

    detail_new = pl.concat(new_frames, how="diagonal_relaxed")

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