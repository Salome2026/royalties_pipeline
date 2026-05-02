import hashlib
import re
from datetime import datetime
from pathlib import Path

import polars as pl


INPUT_DIR = Path(r"C:\royalties_pipeline\input_raw\soundon")
REGISTRY_PATH = Path(r"C:\royalties_pipeline\warehouse\registry\processed_files.parquet")
DETAIL_PATH = Path(r"C:\royalties_pipeline\warehouse\detail\royalties_detail.parquet")

SOURCE = "soundon"
ACCOUNT = "soundon"
SHEET_NAME = "My Royalty"


def ensure_dirs():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
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
    match = re.search(
        r"SoundOn_royalty_monthly_statement_(\d{4})_(\d{2})_My Royalty\.csv$",
        file_name,
        flags=re.IGNORECASE,
    )

    if not match:
        return "unknown"

    return f"{match.group(1)}-{match.group(2)}"


def normalize_decimal(col_name: str) -> pl.Expr:
    return (
        pl.col(col_name)
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


def standardize_soundon(df: pl.DataFrame, file_path: Path, file_hash: str) -> pl.DataFrame:
    statement_period = extract_statement_period(file_path.name)
    ingested_at = datetime.now().isoformat(timespec="seconds")

    df = df.rename({col: str(col).strip() for col in df.columns})

    required_cols = [
        "Reporting Period",
        "Track Title",
        "ISRC",
        "Track Artists",
        "Units of Sold",
        "Currency",
        "Final Royalty",
    ]

    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas requeridas: {missing}. Columnas disponibles: {df.columns}")

    amount = normalize_decimal("Final Royalty")

    df = df.with_columns([
        amount.alias("net_amount"),
        amount.alias("net_amount_usd"),

        normalize_decimal("Units of Sold").alias("units"),

        normalize_decimal("Gross revenue").alias("gross_revenue_usd")
        if "Gross revenue" in df.columns
        else pl.lit(None).cast(pl.Float64).alias("gross_revenue_usd"),

        normalize_decimal("Artist Share").alias("artist_share_usd")
        if "Artist Share" in df.columns
        else pl.lit(None).cast(pl.Float64).alias("artist_share_usd"),

        pl.col("Currency").cast(pl.Utf8).str.strip_chars().str.to_uppercase().alias("currency_original"),
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

        pl.lit(SOURCE).alias("source"),
        pl.lit(ACCOUNT).alias("account"),
        pl.lit(SHEET_NAME).alias("source_sheet"),
        pl.lit(file_path.name).alias("statement_file_name"),
        pl.lit(str(file_path)).alias("statement_file_path"),
        pl.lit(file_hash).alias("statement_file_hash"),
        pl.lit(ingested_at).alias("ingested_at"),
    ])

    return df


def main():
    print("Iniciando ingest SoundOn...")

    ensure_dirs()

    csv_files = sorted(INPUT_DIR.glob("*_My Royalty.csv"))

    print(f"Archivos My Royalty encontrados: {len(csv_files)}")

    if not csv_files:
        print(r"No se encontraron archivos SoundOn My Royalty en input_raw\soundon")
        return

    registry = load_registry()
    existing_hashes = set(registry["file_hash"].to_list()) if registry.height > 0 else set()
    detail_existing = load_detail()

    new_frames = []
    registry_rows = []

    for file_path in csv_files:
        print(f"\nRevisando: {file_path.name}")

        file_hash = sha256_file(file_path)

        if file_hash in existing_hashes:
            print("  - Ya procesado. Se omite.")
            continue

        try:
            df = read_soundon_csv(file_path)
            print(f"  - Leido OK. Filas crudas: {df.height}")

            df = standardize_soundon(df, file_path, file_hash)

            row_count = df.height
            statement_period = extract_statement_period(file_path.name)

            new_frames.append(df)
            registry_rows.append({
                "file_hash": file_hash,
                "file_name": file_path.name,
                "file_path": str(file_path),
                "source": SOURCE,
                "account": ACCOUNT,
                "sheet_name": SHEET_NAME,
                "statement_period": statement_period,
                "processed_at": datetime.now().isoformat(timespec="seconds"),
                "row_count": row_count,
            })

            print(f"  - Procesado OK. Filas: {row_count}")
            print(f"  - Statement period: {statement_period}")

        except Exception as e:
            print(f"  - ERROR procesando {file_path.name}: {e}")

    if not new_frames:
        print("\nNo hubo archivos nuevos para agregar.")
        return

    print("\nConsolidando filas nuevas...")

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
    print(f"Total USD agregado: {detail_new['net_amount_usd'].sum()}")


if __name__ == "__main__":
    main()
