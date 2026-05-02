import hashlib
from datetime import datetime
from pathlib import Path

import polars as pl


INPUT_DIR = Path(r"C:\royalties_pipeline\input_raw\orchard")
REGISTRY_PATH = Path(r"C:\royalties_pipeline\warehouse\registry\processed_files.parquet")
DETAIL_PATH = Path(r"C:\royalties_pipeline\warehouse\detail\royalties_detail.parquet")

SOURCE = "orchard"


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


def normalize_decimal(col_name: str) -> pl.Expr:
    return (
        pl.col(col_name)
        .cast(pl.Utf8)
        .str.replace_all(",", ".")
        .str.strip_chars()
        .replace("", None)
        .cast(pl.Float64, strict=False)
    )


def normalize_statement_period() -> pl.Expr:
    return (
        pl.col("STATEMENT PERIOD")
        .str.strptime(pl.Date, format="%B %Y", strict=False)
        .dt.strftime("%Y-%m")
    )


def read_orchard_csv(file_path: Path) -> pl.DataFrame:
    return pl.read_csv(
        file_path,
        separator=",",
        quote_char='"',
        ignore_errors=True,
        infer_schema_length=10000,
    )


def standardize_orchard(df: pl.DataFrame, file_path: Path, file_hash: str) -> pl.DataFrame:
    ingested_at = datetime.now().isoformat(timespec="seconds")

    df = df.rename({
    col: col.replace('\ufeff', '').replace('"', '').strip()
    for col in df.columns
})

    amount_usd = normalize_decimal("NET SHARE ACCOUNT CURRENCY")

    df = df.with_columns([
        amount_usd.alias("net_amount"),
        amount_usd.alias("net_amount_usd"),

        normalize_statement_period().alias("statement_period"),

        pl.col("TRANSACTION DATE")
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.slice(0, 7)
        .alias("transaction_month"),

        pl.when(
            pl.col("TRACK ARTIST").is_not_null()
            & (pl.col("TRACK ARTIST").cast(pl.Utf8).str.strip_chars() != "")
        )
        .then(pl.col("TRACK ARTIST").cast(pl.Utf8))
        .otherwise(pl.col("PRODUCT ARTIST").cast(pl.Utf8))
        .alias("artist_statement_style"),

        pl.col("ACCOUNT NAME").cast(pl.Utf8).str.strip_chars().alias("account"),

        pl.lit(SOURCE).alias("source"),
        pl.lit(file_path.name).alias("statement_file_name"),
        pl.lit(str(file_path)).alias("statement_file_path"),
        pl.lit(file_hash).alias("statement_file_hash"),
        pl.lit(ingested_at).alias("ingested_at"),
    ])

    return df


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

    csv_files = sorted(INPUT_DIR.glob("*.csv"))

    if not csv_files:
        print("No se encontraron archivos CSV en input_raw\\orchard")
        return

    print(f"Se encontraron {len(csv_files)} archivo(s) Orchard.")

    for file_path in csv_files:
        print(f"\nRevisando: {file_path.name}")

        file_hash = sha256_file(file_path)

        if file_hash in existing_hashes:
            print("  - Ya procesado. Se omite.")
            continue

        try:
            df = read_orchard_csv(file_path)
            df = standardize_orchard(df, file_path, file_hash)

            row_count = df.height
            statement_periods = df.select("statement_period").drop_nulls().unique().to_series().to_list()
            account_values = df.select("account").drop_nulls().unique().to_series().to_list()

            account_for_registry = account_values[0] if account_values else "unknown"
            statement_for_registry = ",".join(sorted(statement_periods)) if statement_periods else "unknown"

            new_frames.append(df)

            registry_rows.append({
                "file_hash": file_hash,
                "file_name": file_path.name,
                "file_path": str(file_path),
                "source": SOURCE,
                "account": account_for_registry,
                "sheet_name": None,
                "statement_period": statement_for_registry,
                "processed_at": datetime.now().isoformat(timespec="seconds"),
                "row_count": row_count,
            })

            print(f"  - Procesado OK. Filas: {row_count}")
            print(f"  - Account: {account_for_registry}")
            print(f"  - Statement period(s): {statement_for_registry}")

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