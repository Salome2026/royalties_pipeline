import hashlib
import re
from datetime import datetime
from pathlib import Path

import polars as pl


INPUT_DIR = Path(r"C:\royalties_pipeline\input_raw\dashgo")
REGISTRY_PATH = Path(r"C:\royalties_pipeline\warehouse\registry\processed_files.parquet")
DETAIL_PATH = Path(r"C:\royalties_pipeline\warehouse\detail\royalties_detail.parquet")

SOURCE = "dashgo"
ACCOUNT = "mawzrecords"


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
    name = Path(file_name).stem
    match = re.search(r"-(\d{2})-(\d{2})$", name)

    if not match:
        return "unknown"

    month = match.group(1)
    year = match.group(2)

    return f"20{year}-{month}"


def normalize_decimal(col_name: str) -> pl.Expr:
    return (
        pl.col(col_name)
        .cast(pl.Utf8)
        .str.replace_all(",", ".")
        .str.strip_chars()
        .replace("", None)
        .cast(pl.Float64, strict=False)
    )


def read_dashgo_csv(file_path: Path) -> pl.DataFrame:
    return pl.read_csv(
        file_path,
        separator=",",
        quote_char='"',
        ignore_errors=True,
        infer_schema_length=10000,
        encoding="utf8-lossy",
    )


def standardize_dashgo(df: pl.DataFrame, file_path: Path, file_hash: str) -> pl.DataFrame:
    statement_period = extract_statement_period(file_path.name)
    ingested_at = datetime.now().isoformat(timespec="seconds")

    df = df.rename({col: col.strip() for col in df.columns})

    required_cols = [
        "Transaction Date",
        "Artist Name",
        "Track Title",
        "Payable",
    ]

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas requeridas: {missing}. Columnas disponibles: {df.columns}")

    payable = normalize_decimal("Payable")

    df = df.with_columns([
        payable.alias("net_amount"),
        payable.alias("net_amount_usd"),

        pl.col("Transaction Date")
        .cast(pl.Utf8)
        .str.slice(0, 7)
        .alias("transaction_month"),

        pl.when(
            pl.col("Artist Name").is_not_null()
    &       (pl.col("Artist Name").cast(pl.Utf8).str.strip_chars() != "")
        )
        .then(pl.col("Artist Name").cast(pl.Utf8).str.strip_chars())
        .when(
            pl.col("Track Title").is_not_null()
            & (pl.col("Track Title").cast(pl.Utf8).str.strip_chars() != "")
            & pl.col("Track Title")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_lowercase()
                .str.starts_with("auto generated asset")
        )
        .then(pl.lit("No Identificado"))
        .otherwise(pl.col("Track Title").cast(pl.Utf8).str.strip_chars())
        .alias("artist_statement_style"),

        pl.lit(SOURCE).alias("source"),
        pl.lit(ACCOUNT).alias("account"),
        pl.lit(file_path.name).alias("statement_file_name"),
        pl.lit(str(file_path)).alias("statement_file_path"),
        pl.lit(file_hash).alias("statement_file_hash"),
        pl.lit(statement_period).alias("statement_period"),
        pl.lit(ingested_at).alias("ingested_at"),
    ])

    return df


def main():
    print("Iniciando ingest DashGo...")

    ensure_dirs()

    print(f"Buscando CSV en: {INPUT_DIR}")

    csv_files = sorted(INPUT_DIR.glob("*.csv"))

    print(f"Archivos encontrados: {len(csv_files)}")

    if not csv_files:
        print(r"No se encontraron archivos CSV en input_raw\dashgo")
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
            df = read_dashgo_csv(file_path)
            print(f"  - Leído OK. Filas crudas: {df.height}")
            print(f"  - Columnas: {df.columns}")

            df = standardize_dashgo(df, file_path, file_hash)

            row_count = df.height
            statement_period = extract_statement_period(file_path.name)

            new_frames.append(df)

            registry_rows.append({
                "file_hash": file_hash,
                "file_name": file_path.name,
                "file_path": str(file_path),
                "source": SOURCE,
                "account": ACCOUNT,
                "sheet_name": None,
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


if __name__ == "__main__":
    main()