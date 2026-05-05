from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

import polars as pl
import pandas as pd


BASE = Path(r"C:\royalties_pipeline")

INPUT_DIR = BASE / "input_raw" / "booking"
OWNER_REPORT_PATH = Path(r"C:\Users\ruben\Downloads\Ingresos x Booking Indyana-MAWZ.xlsx")
OUTPUT_DIR = BASE / "warehouse" / "booking" / "raw"


STATIC_SOURCES = [
    {
        "file_path": INPUT_DIR / "booking_google_sample.xlsx",
        "dataset": "operations",
        "sheets": {
            "Ingresos": {"dataset_name": "booking_raw_ingresos", "header_row": 1},
            "Egresos": {"dataset_name": "booking_raw_egresos", "header_row": 1},
            "Presentaciones": {"dataset_name": "booking_raw_presentaciones", "header_row": 1},
            "Sheet18": {"dataset_name": "booking_raw_special_cases", "header_row": None},
            "Artistas": {"dataset_name": "booking_raw_artists", "header_row": 0},
            "Categorias": {"dataset_name": "booking_raw_categories", "header_row": None},
            "Resumen booking": {"dataset_name": "booking_raw_booking_summary", "header_row": 1},
        },
    },
    {
        "file_path": OWNER_REPORT_PATH,
        "dataset": "owner_report",
        "sheets": {
            "Indyana": {"dataset_name": "booking_raw_owner_indyana", "header_row": 0},
            "EL COLO": {"dataset_name": "booking_raw_owner_seller_colo", "header_row": 0},
            "Booking Mauro Detalle": {"dataset_name": "booking_raw_owner_partner_mauro", "header_row": 2},
            "El Caserio 2024": {"dataset_name": "booking_raw_owner_caserio", "header_row": 0},
        },
    },
]


PM_SHEET_CONFIGS = {
    "Artistas": {"dataset_name": "booking_raw_pm_artists", "header_row": 0},
    "Presentaciones": {"dataset_name": "booking_raw_pm_presentaciones", "header_row": 1},
    "Caja": {"dataset_name": "booking_raw_pm_caja", "header_row": 1},
    "Ingresos": {"dataset_name": "booking_raw_pm_ingresos", "header_row": 1},
    "Egresos": {"dataset_name": "booking_raw_pm_egresos", "header_row": 1},
    "Categorias": {"dataset_name": "booking_raw_pm_categories", "header_row": None},
    "Resumen booking": {"dataset_name": "booking_raw_pm_booking_summary", "header_row": 1},
    "Sheet18": {"dataset_name": "booking_raw_pm_special_cases", "header_row": None},
    "test": {"dataset_name": "booking_raw_pm_special_cases", "header_row": None},
    "Caja Artista": {"dataset_name": "booking_raw_pm_artist_cash", "header_row": 2},
    "Raw": {"dataset_name": "booking_raw_pm_raw", "header_row": 0},
    "GASTOS - INDYANA RECORDS": {"dataset_name": "booking_raw_pm_indyana_expenses", "header_row": 0},
}


def build_sources() -> list[dict]:
    sources = list(STATIC_SOURCES)

    for file_path in sorted(INPUT_DIR.glob("PM*.xlsx")):
        sources.append({
            "file_path": file_path,
            "dataset": "pm_report",
            "sheets": PM_SHEET_CONFIGS,
        })

    return sources


def clean_column_names(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    cleaned = []

    for idx, raw_col in enumerate(columns, start=1):
        col = str(raw_col).strip()

        if col == "" or col.lower().startswith("unnamed:"):
            col = f"column_{idx}"

        if col in seen:
            seen[col] += 1
            col = f"{col}_{seen[col]}"
        else:
            seen[col] = 1

        cleaned.append(col)

    return cleaned


def read_sheet(file_path: Path, sheet_name: str, header_row: int | None) -> pl.DataFrame:
    pdf = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row)

    if header_row is None:
        pdf.columns = [f"column_{idx}" for idx in range(1, len(pdf.columns) + 1)]

    pdf = pdf.dropna(how="all")
    pdf = pdf.astype("object").where(pd.notna(pdf), None)

    for col in pdf.columns:
        pdf[col] = pdf[col].map(lambda value: None if value is None else str(value))

    df = pl.from_pandas(pdf)

    if df.height == 0 and len(df.columns) == 0:
        return df

    return df.rename(dict(zip(df.columns, clean_column_names(df.columns))))


def add_trace_columns(
    df: pl.DataFrame,
    *,
    source_file: Path,
    source_sheet: str,
    source_dataset: str,
    source_row_offset: int,
    ingested_at: str,
) -> pl.DataFrame:
    return df.with_row_index("source_row", offset=source_row_offset).with_columns([
        pl.lit(source_dataset).alias("source_dataset"),
        pl.lit(source_file.name).alias("source_file_name"),
        pl.lit(str(source_file)).alias("source_file_path"),
        pl.lit(source_sheet).alias("source_sheet"),
        pl.lit(ingested_at).alias("ingested_at"),
    ])


def write_dataset(dataset_name: str, frames: list[pl.DataFrame]) -> None:
    if not frames:
        print(f"  - {dataset_name}: sin datos")
        return

    output_path = OUTPUT_DIR / f"{dataset_name}.parquet"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    final = pl.concat(frames, how="diagonal_relaxed")
    final.write_parquet(output_path)

    print(f"  - {dataset_name}: {final.height} filas -> {output_path}")


def main() -> None:
    ingested_at = datetime.now().isoformat(timespec="seconds")
    grouped: dict[str, list[pl.DataFrame]] = {}
    sources = build_sources()

    print("Booking raw ingest")
    print("Output:", OUTPUT_DIR)

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    for source in sources:
        file_path = source["file_path"]
        source_dataset = source["dataset"]

        if not file_path.exists():
            print(f"\nNo existe archivo: {file_path}")
            continue

        print(f"\nLeyendo: {file_path}")

        available_sheets = set(pd.ExcelFile(file_path).sheet_names)

        for sheet_name, sheet_config in source["sheets"].items():
            if sheet_name not in available_sheets:
                continue

            dataset_name = sheet_config["dataset_name"]
            header_row = sheet_config["header_row"]
            source_row_offset = (header_row + 2) if header_row is not None else 1

            try:
                df = read_sheet(file_path, sheet_name, header_row)

                if df.height == 0 and len(df.columns) == 0:
                    print(f"  - {sheet_name}: vacia")
                    continue

                df = add_trace_columns(
                    df,
                    source_file=file_path,
                    source_sheet=sheet_name,
                    source_dataset=source_dataset,
                    source_row_offset=source_row_offset,
                    ingested_at=ingested_at,
                )

                grouped.setdefault(dataset_name, []).append(df)
                print(f"  - {sheet_name}: {df.height} filas")

            except Exception as e:
                print(f"  - {sheet_name}: ERROR {e}")

    print("\nGuardando datasets raw...")

    for dataset_name in sorted(grouped):
        write_dataset(dataset_name, grouped[dataset_name])

    print("\nListo.")


if __name__ == "__main__":
    main()
