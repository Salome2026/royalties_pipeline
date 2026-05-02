import hashlib
import calendar
from datetime import datetime, date
from pathlib import Path

import polars as pl
import requests


INPUT_DIR = Path(r"C:\royalties_pipeline\input_raw\onerpm\gusty_dj")
REGISTRY_PATH = Path(r"C:\royalties_pipeline\warehouse\registry\processed_files.parquet")
DETAIL_PATH = Path(r"C:\royalties_pipeline\warehouse\detail\royalties_detail.parquet")
FX_PATH = Path(r"C:\royalties_pipeline\warehouse\registry\exchange_rates.parquet")

SOURCE = "onerpm"
ACCOUNT = "gusty_dj"

SHEET_MASTERS = "Masters"
SHEET_SHARES = "Shares In & Out"


def ensure_dirs():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
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

            rate = None

            if isinstance(data, dict):
                rate = data.get("rates", {}).get("USD")

            elif isinstance(data, list) and len(data) > 0:
                rate = data[0].get("rate")

            if rate is not None:
                rates.append(float(rate))

        except Exception:
            continue

    if not rates:
        raise ValueError(f"No se encontraron tasas {from_currency}/USD para {statement_period}")

    avg_rate = sum(rates) / len(rates)

    print(f"  - FX promedio {from_currency}/USD {statement_period}: {avg_rate}")

    return avg_rate


def get_or_fetch_avg_to_usd_rate(statement_period: str, from_currency: str):
    from_currency = str(from_currency).upper().strip()

    if from_currency in ["", "NONE", "NULL", "NAN"]:
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
        if currency:
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


def prepare_share_flags(df_shares: pl.DataFrame) -> pl.DataFrame:
    """
    Gusty DJ:
    Shares In & Out NO se suma ni se resta.
    Solo se usa para marcar en Masters si existe alguna relación.
    """
    if df_shares.height == 0:
        return pl.DataFrame(
            schema={
                "share_match_key": pl.Utf8,
                "share_in_count": pl.Int64,
                "share_out_count": pl.Int64,
                "share_total_count": pl.Int64,
            }
        )

    df_shares = clean_column_names(df_shares)

    if "ID" not in df_shares.columns and "Parent ID" not in df_shares.columns:
        print("  - Shares leído, pero no tiene ID ni Parent ID para matchear.")
        return pl.DataFrame(
            schema={
                "share_match_key": pl.Utf8,
                "share_in_count": pl.Int64,
                "share_out_count": pl.Int64,
                "share_total_count": pl.Int64,
            }
        )

    df_shares = normalize_numeric_columns(df_shares)

    share_key_frames = []

    if "ID" in df_shares.columns:
        share_key_frames.append(
            df_shares.with_columns([
                pl.col("ID")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_uppercase()
                .alias("share_match_key")
            ])
        )

    if "Parent ID" in df_shares.columns:
        share_key_frames.append(
            df_shares.with_columns([
                pl.col("Parent ID")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_uppercase()
                .alias("share_match_key")
            ])
        )

    shares_keys = pl.concat(share_key_frames, how="diagonal_relaxed")

    shares_keys = shares_keys.filter(
        pl.col("share_match_key").is_not_null()
        & (pl.col("share_match_key") != "")
        & (pl.col("share_match_key") != "NULL")
        & (pl.col("share_match_key") != "NAN")
    )

    if shares_keys.height == 0:
        return pl.DataFrame(
            schema={
                "share_match_key": pl.Utf8,
                "share_in_count": pl.Int64,
                "share_out_count": pl.Int64,
                "share_total_count": pl.Int64,
            }
        )

    share_type_col = None
    for col in ["Share Type", "Share type", "Type", "Movement Type"]:
        if col in shares_keys.columns:
            share_type_col = col
            break

    if share_type_col:
        shares_keys = shares_keys.with_columns(
            pl.col(share_type_col)
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("_share_type_norm")
        )
    else:
        shares_keys = shares_keys.with_columns(
            pl.lit("").alias("_share_type_norm")
        )

    flags = (
        shares_keys
        .group_by("share_match_key")
        .agg([
            (
                pl.col("_share_type_norm").str.contains("in", literal=False).sum()
            ).alias("share_in_count"),
            (
                pl.col("_share_type_norm").str.contains("out", literal=False).sum()
            ).alias("share_out_count"),
            pl.len().alias("share_total_count"),
        ])
    )

    return flags


def add_share_flags_to_masters(df_masters: pl.DataFrame, df_shares: pl.DataFrame) -> pl.DataFrame:
    """
    Agrega flags a Masters.
    No toca importes.
    No agrega filas de Shares.
    """
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

    master_key_frames = []

    if "ISRC" in df_masters.columns:
        master_key_frames.append(
            df_masters
            .with_row_index("_master_row_id")
            .select([
                "_master_row_id",
                pl.col("ISRC")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_uppercase()
                .alias("share_match_key")
            ])
        )

    if "UPC" in df_masters.columns:
        master_key_frames.append(
            df_masters
            .with_row_index("_master_row_id")
            .select([
                "_master_row_id",
                pl.col("UPC")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_uppercase()
                .alias("share_match_key")
            ])
        )

    if not master_key_frames:
        return df_masters.with_columns([
            pl.lit(False).alias("has_share_in_out"),
            pl.lit(0).cast(pl.Int64).alias("share_in_count"),
            pl.lit(0).cast(pl.Int64).alias("share_out_count"),
            pl.lit(0).cast(pl.Int64).alias("share_total_count"),
            pl.lit("No hay ISRC/UPC en Masters para matchear Shares").alias("share_note"),
        ])

    master_keys = pl.concat(master_key_frames, how="diagonal_relaxed")

    master_keys = master_keys.filter(
        pl.col("share_match_key").is_not_null()
        & (pl.col("share_match_key") != "")
        & (pl.col("share_match_key") != "NULL")
        & (pl.col("share_match_key") != "NAN")
    )

    matched = (
        master_keys
        .join(flags, on="share_match_key", how="left")
        .group_by("_master_row_id")
        .agg([
            pl.col("share_in_count").fill_null(0).sum().alias("share_in_count"),
            pl.col("share_out_count").fill_null(0).sum().alias("share_out_count"),
            pl.col("share_total_count").fill_null(0).sum().alias("share_total_count"),
        ])
    )

    df_masters = df_masters.with_row_index("_master_row_id")

    df_masters = df_masters.join(matched, on="_master_row_id", how="left")

    df_masters = df_masters.with_columns([
        pl.col("share_in_count").fill_null(0).cast(pl.Int64),
        pl.col("share_out_count").fill_null(0).cast(pl.Int64),
        pl.col("share_total_count").fill_null(0).cast(pl.Int64),
    ])

    df_masters = df_masters.with_columns([
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

    df_masters = df_masters.drop("_master_row_id")

    return df_masters


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
    """
    Se deja la función original por compatibilidad / referencia,
    pero en Gusty DJ ya NO se usa para cargar Shares al detail.
    """
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


def main():
    print("Iniciando ingest ONErpm Gusty DJ...")

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

    print(f"Se encontraron {len(excel_files)} archivo(s) ONErpm Gusty DJ.")

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
            df_masters_raw = read_excel_sheet(file_path, SHEET_MASTERS)

            try:
                df_shares_raw = read_excel_sheet(file_path, SHEET_SHARES)
                print(f"  - Shares In & Out leído SOLO para flags. Filas: {df_shares_raw.height}")
            except Exception as e:
                print(f"  - Shares In & Out no leído para flags: {e}")
                df_shares_raw = pl.DataFrame()

            df_masters_raw = add_share_flags_to_masters(df_masters_raw, df_shares_raw)
            df_masters = standardize_masters(df_masters_raw, file_path, file_hash)

            file_frames.append(df_masters)
            row_count += df_masters.height
            sheets_processed.append("Masters + Shares flags")

            flagged_count = (
                df_masters
                .filter(pl.col("has_share_in_out") == True)
                .height
                if "has_share_in_out" in df_masters.columns
                else 0
            )

            print(f"  - Masters procesado OK. Filas: {df_masters.height}")
            print(f"  - Filas Masters con alerta Shares In/Out: {flagged_count}")
            print("  - IMPORTANTE: Shares In & Out NO se agregan al detail ni impactan montos.")

        except Exception as e:
            print(f"  - Masters no procesado: {e}")

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

        print(f"  - Archivo procesado OK. Filas totales agregadas al detail: {row_count}")
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