import hashlib
import re
import shutil
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import polars as pl


INPUT_FILE = Path(r"C:\royalties_pipeline\input_raw\altafonte\altafonte.xlsx")

ARCHIVE_DIR = Path(r"C:\royalties_pipeline\warehouse\archive\orchard_legacy_altafonte")
DETAIL_PATH = Path(r"C:\royalties_pipeline\warehouse\detail\royalties_detail.parquet")

TEMP_LEGACY_PATH = Path(r"C:\royalties_pipeline\warehouse\detail\altafonte_legacy_temp.parquet")
TEMP_FINAL_PATH = Path(r"C:\royalties_pipeline\warehouse\detail\royalties_detail_updated.parquet")
BACKUP_PATH = Path(r"C:\royalties_pipeline\warehouse\detail\royalties_detail_backup_before_altafonte.parquet")

SOURCE = "orchard"
ACCOUNT = "mawzrecords"
STATEMENT_TYPE = "altafonte_legacy"


def sha256_file(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_to_archive():
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = ARCHIVE_DIR / f"{timestamp}_{INPUT_FILE.name}"
    shutil.copy(INPUT_FILE, dest)
    print(f"Archivo archivado en: {dest}")


def clean_amount(val) -> float:
    if pd.isna(val):
        return 0.0

    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()

    if s == "":
        return 0.0

    s = (
        s.replace("US$", "")
        .replace("USD", "")
        .replace("$", "")
        .replace(" ", "")
        .strip()
    )

    # Formato latino: 1.234,56
    if "," in s:
        s = s.replace(".", "").replace(",", ".")

    try:
        return float(s)
    except ValueError:
        return 0.0


def normalize_month(col):
    if pd.isna(col):
        return None

    s = str(col).strip()

    # 2025-04
    if re.match(r"^20\d{2}-\d{2}$", s):
        return s

    # 2025-04-01 / Timestamp / Excel date
    dt = pd.to_datetime(col, errors="coerce")
    if not pd.isna(dt):
        return dt.strftime("%Y-%m")

    return None


def find_header_row(raw: pd.DataFrame) -> int:
    for idx, row in raw.iterrows():
        values = [str(v).strip() for v in row.tolist()]
        if "Artista" in values:
            return idx

    raise ValueError("No encontré una fila de encabezados que contenga 'Artista'.")


def read_altafonte_excel():
    xl = pd.ExcelFile(INPUT_FILE)

    print("Hojas detectadas:")
    print(xl.sheet_names)

    preferred_sheets = [
        "altafonte",
        "Altafonte",
        "ALTAFONTE",
        "data_altafonte",
    ]

    sheet_to_use = None

    for sheet in preferred_sheets:
        if sheet in xl.sheet_names:
            sheet_to_use = sheet
            break

    if sheet_to_use is None:
        sheet_to_use = xl.sheet_names[0]

    print(f"Hoja usada: {sheet_to_use}")

    raw = pd.read_excel(INPUT_FILE, sheet_name=sheet_to_use, header=None)
    header_row = find_header_row(raw)

    print(f"Fila de encabezados detectada: {header_row}")

    headers = raw.iloc[header_row].tolist()
    df = raw.iloc[header_row + 1:].copy()
    df.columns = [str(c).strip() if not pd.isna(c) else "" for c in headers]

    print("Columnas detectadas:")
    print(df.columns.tolist())

    return df


def main():
    if not INPUT_FILE.exists():
        print("No existe el archivo:")
        print(INPUT_FILE)
        return

    print("Leyendo Excel Altafonte...")

    copy_to_archive()

    df = read_altafonte_excel()

    if "Artista" not in df.columns:
        print("ERROR: No existe columna Artista.")
        return

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

    month_cols = list(month_map.keys())

    print("Meses detectados:")
    print(list(month_map.values()))

    if not month_cols:
        print("ERROR: No detecté columnas de meses.")
        print("Columnas disponibles:")
        print(df.columns.tolist())
        return

    records = []
    file_hash = sha256_file(INPUT_FILE)
    ingested_at = datetime.now().isoformat(timespec="seconds")

    for _, row in df.iterrows():
        artist = str(row["Artista"]).strip()

        for col in month_cols:
            amount = clean_amount(row[col])

            if amount == 0:
                continue

            records.append({
                "artist_statement_style": artist,
                "transaction_month": month_map[col],
                "statement_period": month_map[col],
                "net_amount": amount,
                "net_amount_usd": amount,
                "source": SOURCE,
                "account": ACCOUNT,
                "statement_type": STATEMENT_TYPE,
                "statement_file_name": INPUT_FILE.name,
                "statement_file_path": str(INPUT_FILE),
                "statement_file_hash": file_hash,
                "ingested_at": ingested_at,
            })

    df_final = pl.DataFrame(records)

    print("Filas generadas:", df_final.height)

    if df_final.height == 0:
        print("ERROR: Altafonte generó 0 filas. No se modifica el detail.")
        return

    df_final.write_parquet(TEMP_LEGACY_PATH)

    con = duckdb.connect()

    print("Creando backup del detail actual...")

    con.execute(
        f"""
        COPY (
            SELECT *
            FROM read_parquet('{str(DETAIL_PATH).replace("'", "''")}')
        )
        TO '{str(BACKUP_PATH).replace("'", "''")}'
        (FORMAT PARQUET)
        """
    )

    print("Actualizando detail sin duplicar Altafonte legacy...")

    con.execute(
        f"""
        COPY (
            SELECT *
            FROM read_parquet('{str(DETAIL_PATH).replace("'", "''")}')
            WHERE NOT (
                source = '{SOURCE}'
                AND account = '{ACCOUNT}'
                AND statement_file_name = '{INPUT_FILE.name}'
            )

            UNION ALL BY NAME

            SELECT *
            FROM read_parquet('{str(TEMP_LEGACY_PATH).replace("'", "''")}')
        )
        TO '{str(TEMP_FINAL_PATH).replace("'", "''")}'
        (FORMAT PARQUET)
        """
    )

    DETAIL_PATH.unlink()
    TEMP_FINAL_PATH.rename(DETAIL_PATH)

    if TEMP_LEGACY_PATH.exists():
        TEMP_LEGACY_PATH.unlink()

    print("Altafonte integrado como histórico de Orchard correctamente.")
    print("Backup creado en:")
    print(BACKUP_PATH)


if __name__ == "__main__":
    main()