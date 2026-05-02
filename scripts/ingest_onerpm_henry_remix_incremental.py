import hashlib
import os
from datetime import datetime
from pathlib import Path

import polars as pl


# =========================
# CONFIG
# =========================
INPUT_DIR = Path(r"C:\royalties_pipeline\input_raw\onerpm\henry_remix")
REGISTRY_PATH = Path(r"C:\royalties_pipeline\warehouse\registry\processed_files.parquet")
DETAIL_PATH = Path(r"C:\royalties_pipeline\warehouse\detail\royalties_detail.parquet")

SOURCE = "onerpm"
ACCOUNT = "henry_remix"
SHEET_NAME = "Masters"


# =========================
# HELPERS
# =========================
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


def save_registry(df: pl.DataFrame):
    df.write_parquet(REGISTRY_PATH)


def load_detail() -> pl.DataFrame:
    if not DETAIL_PATH.exists():
        print("Detalle no existe. Se inicia vacío.")
        return pl.DataFrame()

    try:
        df = pl.read_parquet(DETAIL_PATH)

        if df.width == 0:
            print("Detalle vacío detectado. Se ignora.")
            return pl.DataFrame()

        return df

    except Exception as e:
        print(f"Detalle corrupto o inválido. Se ignora. Error: {e}")
        return pl.DataFrame()

def save_detail(df: pl.DataFrame):
    df.write_parquet(DETAIL_PATH)


def extract_statement_period(file_name: str) -> str:
    """
    Ejemplo:
    2026-01-01 00_00_00-details.xlsx -> 2026-01

    Si después cambia el naming, esta función se ajusta.
    """
    base = Path(file_name).stem
    if len(base) >= 7 and base[4] == "-" and base[7] == "-":
        return base[:7]
    return "unknown"


def clean_column_names(df: pl.DataFrame) -> pl.DataFrame:
    rename_map = {col: col.strip() for col in df.columns}
    return df.rename(rename_map)


def normalize_numeric_columns(df: pl.DataFrame) -> pl.DataFrame:
    numeric_cols = [
        "Gross (Original Currency)",
        "Exchange Rate",
        "Gross",
        "Quantity",
        "Average Unit Gross",
        "% Share",
        "Fees",
        "Net",
    ]

    existing = [c for c in numeric_cols if c in df.columns]

    for col in existing:
        df = df.with_columns(
            pl.col(col)
            .cast(pl.Utf8)
            .str.replace_all(",", ".")
            .str.strip_chars()
            .replace("", None)
            .cast(pl.Float64, strict=False)
            .alias(col)
        )

    return df


def infer_transaction_month_expr():
    """
    Busca algunas variantes comunes.
    Ajustamos después cuando veamos el Excel real consolidado.
    """
    possible_cols = [
        "Transaction Month",
        "Transaction month",
        "Sales Month",
        "Month",
        "Reporting Period",
    ]
    return possible_cols


def build_artist_statement_style(df: pl.DataFrame) -> pl.DataFrame:
    """
    Crea artist_statement_style desde columna Artists,
    quedándose solo con los '(performer)' y preservando el orden original.
    """
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


def detect_transaction_month(df: pl.DataFrame) -> pl.DataFrame:
    possible_cols = infer_transaction_month_expr()

    found_col = None
    for col in possible_cols:
        if col in df.columns:
            found_col = col
            break

    if found_col:
        return df.with_columns(
            pl.col(found_col).cast(pl.Utf8).alias("transaction_month")
        )

    return df.with_columns(pl.lit(None).alias("transaction_month"))


def standardize_output(df: pl.DataFrame, file_path: Path, file_hash: str) -> pl.DataFrame:
    statement_period = extract_statement_period(file_path.name)
    ingested_at = datetime.now().isoformat(timespec="seconds")

    df = clean_column_names(df)
    df = normalize_numeric_columns(df)
    df = detect_transaction_month(df)
    df = build_artist_statement_style(df)

    df = df.with_columns([
        pl.lit(SOURCE).alias("source"),
        pl.lit(ACCOUNT).alias("account"),
        pl.lit(file_path.name).alias("statement_file_name"),
        pl.lit(str(file_path)).alias("statement_file_path"),
        pl.lit(file_hash).alias("statement_file_hash"),
        pl.lit(statement_period).alias("statement_period"),
        pl.lit(ingested_at).alias("ingested_at"),
    ])

    # Renombrado interno estable
    rename_map = {}
    if "Net" in df.columns:
        rename_map["Net"] = "net_amount"
    if "Artists" in df.columns:
        rename_map["Artists"] = "artists_raw"

    df = df.rename(rename_map)

    return df


def read_excel_masters(file_path: Path) -> pl.DataFrame:
    return pl.read_excel(file_path, sheet_name=SHEET_NAME)


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
        if p.is_file() and p.suffix.lower() in [".xlsx", ".xlsm"]
    ])

    if not excel_files:
        print("No se encontraron archivos Excel.")
        return

    print(f"Se encontraron {len(excel_files)} archivo(s).")

    for file_path in excel_files:
        print(f"\nRevisando: {file_path.name}")

        file_hash = sha256_file(file_path)

        if file_hash in existing_hashes:
            print("  - Ya procesado (mismo contenido). Se omite.")
            continue

        try:
            df = read_excel_masters(file_path)
            df = standardize_output(df, file_path, file_hash)

            row_count = df.height
            new_detail_frames.append(df)

            registry_rows.append({
                "file_hash": file_hash,
                "file_name": file_path.name,
                "file_path": str(file_path),
                "source": SOURCE,
                "account": ACCOUNT,
                "sheet_name": SHEET_NAME,
                "statement_period": extract_statement_period(file_path.name),
                "processed_at": datetime.now().isoformat(timespec="seconds"),
                "row_count": row_count,
            })

            print(f"  - Procesado OK. Filas: {row_count}")

        except Exception as e:
            print(f"  - Error procesando {file_path.name}: {e}")

    if not new_detail_frames:
        print("\nNo hubo archivos nuevos para agregar.")
        return

    detail_new = pl.concat(new_detail_frames, how="diagonal_relaxed")

    if detail_existing.height > 0:
        detail_final = pl.concat([detail_existing, detail_new], how="diagonal_relaxed")
    else:
        detail_final = detail_new

    if detail_final.height > 0:
        save_detail(detail_final)
    else:
        print("No se guarda detalle porque está vacío.")

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