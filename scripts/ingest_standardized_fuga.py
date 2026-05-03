import sys
import hashlib
from datetime import datetime
from pathlib import Path

import polars as pl


# =========================
# PATH SETUP
# =========================

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

from lib.fx import get_monthly_fx
from lib.statement_period import from_fuga_filename, fuga_correction


# =========================
# CONFIG
# =========================

BASE_DIR = Path(r"C:\royalties_pipeline")

INPUT_DIR = BASE_DIR / "input_raw" / "fuga"
OUTPUT_PATH = BASE_DIR / "warehouse" / "marts" / "standardized_raw_fuga.parquet"
TEMP_DIR = BASE_DIR / "staging" / "standardized_raw_parts" / "fuga"

SOURCE = "fuga"
ACCOUNT = "indyana_records"

# Del script de correction recuperado
CORRECTION_STATEMENT_PERIOD = "2025-12"


# =========================
# HELPERS
# =========================

def ensure_dirs():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_statement_period(file_name: str) -> str:
    return from_fuga_filename(file_name).period


def read_fuga_csv(file_path: Path) -> pl.DataFrame:
    return pl.read_csv(
        file_path,
        separator=",",
        quote_char='"',
        ignore_errors=True,
        infer_schema_length=10000,
    )


def clean_columns(df: pl.DataFrame) -> pl.DataFrame:
    return df.rename({col: str(col).strip() for col in df.columns})


def text_expr(col_name: str, cols: set[str]) -> pl.Expr:
    if col_name not in cols:
        return pl.lit(None).cast(pl.Utf8)

    return (
        pl.col(col_name)
        .cast(pl.Utf8)
        .str.strip_chars()
        .replace("", None)
    )


def decimal_expr(col_name: str, cols: set[str]) -> pl.Expr:
    if col_name not in cols:
        return pl.lit(None).cast(pl.Float64)

    return (
        pl.col(col_name)
        .cast(pl.Utf8)
        .str.replace_all(",", ".")
        .str.strip_chars()
        .replace("", None)
        .cast(pl.Float64, strict=False)
    )


def first_non_empty(cols: set[str], *col_names: str) -> pl.Expr:
    expr = None

    for col_name in col_names:
        value = text_expr(col_name, cols)
        condition = value.is_not_null() & (value != "")

        if expr is None:
            expr = pl.when(condition).then(value)
        else:
            expr = expr.when(condition).then(value)

    return expr.otherwise(None)


# =========================
# STANDARDIZE
# =========================

def standardize_fuga_file(
    df: pl.DataFrame,
    file_path: Path,
    statement_type: str,
    statement_period: str,
    statement_period_source: str,
    statement_period_note: str,
) -> pl.DataFrame:

    if df.height == 0:
        return df

    file_hash = sha256_file(file_path)
    ingested_at = datetime.now().isoformat(timespec="seconds")

    df = clean_columns(df)
    cols = set(df.columns)

    if "Reported Royalty" not in cols:
        raise ValueError(f"Falta Reported Royalty en {file_path.name}")

    if "Sale Start date" not in cols:
        raise ValueError(f"Falta Sale Start date en {file_path.name}")

    if statement_period == "unknown":
        raise ValueError(f"No se pudo detectar statement_period para {file_path.name}")

    # Igual que el ingest original:
    # FX por statement_period, no por cada Sale Start date.
    fx_rate = get_monthly_fx(
        fx_month=statement_period,
        from_currency="EUR",
        to_currency="USD",
    )

    reported_royalty_eur = decimal_expr("Reported Royalty", cols)

    df = df.with_columns([
        # =========================
        # FECHAS
        # =========================
        text_expr("Sale Start date", cols)
            .str.slice(0, 7)
            .alias("transaction_month"),

        text_expr("Sale Start date", cols).alias("sale_start_date"),
        text_expr("Sale End date", cols).alias("sale_end_date"),

        # =========================
        # IMPORTES - lógica original
        # =========================
        reported_royalty_eur.alias("amount_original"),
        text_expr("Currency", cols).alias("currency_original"),

        reported_royalty_eur.alias("net_amount"),
        reported_royalty_eur.alias("net_amount_eur"),

        pl.lit(statement_period).alias("fx_rate_date"),
        pl.lit(fx_rate).alias("fx_eur_usd_rate"),

        (reported_royalty_eur * fx_rate).alias("amount_usd"),
        (reported_royalty_eur * fx_rate).alias("net_amount_usd"),

        # =========================
        # IMPORTES RAW NUMÉRICOS ÚTILES
        # =========================
        decimal_expr("Original Gross Income", cols).alias("original_gross_income_num"),
        text_expr("Original currency", cols).alias("original_currency"),
        decimal_expr("Exchange Rate", cols).alias("original_exchange_rate"),
        decimal_expr("Converted Gross Income", cols).alias("converted_gross_income_num"),
        decimal_expr("Product Quantity", cols).alias("product_quantity_num"),
        decimal_expr("Asset Quantity", cols).alias("asset_quantity_num"),

        # =========================
        # PRODUCT / RELEASE
        # =========================
        text_expr("Product Label", cols).alias("label_statement_style"),

        text_expr("Product Artist", cols).alias("product_artist_statement"),
        text_expr("Product Title", cols).alias("product_title_statement"),
        text_expr("Product UPC", cols).alias("product_upc"),
        text_expr("Product Reference", cols).alias("product_reference"),
        text_expr("Product Catalog Number", cols).alias("product_catalog_number"),

        # =========================
        # ASSET / TRACK
        # =========================
        text_expr("Asset Artist", cols).alias("asset_artist_statement"),
        text_expr("Asset Title", cols).alias("asset_title_statement"),
        text_expr("Asset Version", cols).alias("asset_version_statement"),
        text_expr("Asset Duration", cols).alias("asset_duration_statement"),
        text_expr("Asset ISRC", cols).alias("asset_isrc"),
        text_expr("Asset Reference", cols).alias("asset_reference"),
        text_expr("Asset/Product", cols).alias("asset_product_type"),

        # =========================
        # CLAVE LEGACY PARA CERRAR CON PIPELINE ACTUAL
        # Igual que ingest_fuga_incremental.py:
        # Product Artist fallback Product Title
        # =========================
        first_non_empty(cols, "Product Artist", "Product Title")
            .alias("artist_statement_style"),

        # =========================
        # CAMPOS NUEVOS PARA FUTURO
        # =========================
        first_non_empty(cols, "Asset Artist", "Product Artist", "Product Title")
            .alias("artist_best_available"),

        first_non_empty(cols, "Asset Title", "Product Title")
            .alias("track_statement_style"),

        text_expr("Product Title", cols).alias("release_statement_style"),

        # =========================
        # COMERCIAL / DSP
        # =========================
        text_expr("DSP", cols).alias("dsp"),
        text_expr("Sale Store Name", cols).alias("store_name"),
        text_expr("Sale Type", cols).alias("sale_type"),
        text_expr("Sale User Type", cols).alias("sale_user_type"),
        text_expr("Territory", cols).alias("territory"),
        text_expr("Audio Format", cols).alias("audio_format"),
        text_expr("Contract deal term", cols).alias("contract_deal_term"),

        # =========================
        # IDS
        # =========================
        text_expr("Sale ID", cols).alias("sale_id"),
        text_expr("Report ID", cols).alias("report_id"),
        text_expr("Report Run ID", cols).alias("report_run_id"),

        # =========================
        # METADATA
        # =========================
        pl.lit(SOURCE).alias("source"),
        pl.lit(ACCOUNT).alias("account"),
        pl.lit(statement_type).alias("statement_type"),
        pl.lit(statement_period).alias("statement_period"),
        pl.lit(statement_period_source).alias("statement_period_source"),
        pl.lit(statement_period_note).alias("statement_period_note"),

        pl.lit(file_path.name).alias("statement_file_name"),
        pl.lit(str(file_path)).alias("statement_file_path"),
        pl.lit(file_hash).alias("statement_file_hash"),
        pl.lit(ingested_at).alias("ingested_at"),
    ])

    return df


# =========================
# MAIN
# =========================

def main():
    ensure_dirs()

    if not INPUT_DIR.exists():
        print(f"No existe carpeta: {INPUT_DIR}")
        return

    all_files = sorted(INPUT_DIR.glob("*.csv"))

    regular_files = [
        p for p in all_files
        if "correction" not in p.name.lower()
    ]

    correction_files = [
        p for p in all_files
        if "correction" in p.name.lower()
    ]

    print("FUGA standardized ingest")
    print(f"Archivos regulares: {len(regular_files)}")
    print(f"Archivos correction: {len(correction_files)}")
    print(f"Output: {OUTPUT_PATH}")
    print(f"Temp: {TEMP_DIR}")

    part_paths = []

    # =========================
    # REGULAR
    # =========================

    for file_path in regular_files:
        print(f"\nProcesando REGULAR: {file_path.name}")

        try:
            df = read_fuga_csv(file_path)

            if df.height == 0:
                print("  - Archivo sin filas. Se omite.")
                continue

            statement_info = from_fuga_filename(file_path.name)

            df_std = standardize_fuga_file(
                df=df,
                file_path=file_path,
                statement_type="regular",
                statement_period=statement_info.period,
                statement_period_source=statement_info.source,
                statement_period_note=statement_info.note,
            )

            if df_std.height == 0:
                print("  - Sin filas standardized. Se omite.")
                continue

            part_path = TEMP_DIR / f"regular_{file_path.stem}_{sha256_file(file_path)[:12]}.parquet"
            df_std.write_parquet(part_path)

            part_paths.append(part_path)

            print(f"  OK filas: {df_std.height}")

        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    # =========================
    # CORRECTION
    # =========================

    for file_path in correction_files:
        print(f"\nProcesando CORRECTION: {file_path.name}")

        try:
            df = read_fuga_csv(file_path)

            if df.height == 0:
                print("  - Archivo correction sin filas. Se omite.")
                continue

            statement_info = fuga_correction(CORRECTION_STATEMENT_PERIOD)

            df_std = standardize_fuga_file(
                df=df,
                file_path=file_path,
                statement_type="correction",
                statement_period=statement_info.period,
                statement_period_source=statement_info.source,
                statement_period_note=statement_info.note,
            )

            if df_std.height == 0:
                print("  - Sin filas standardized. Se omite.")
                continue

            part_path = TEMP_DIR / f"correction_{file_path.stem}_{sha256_file(file_path)[:12]}.parquet"
            df_std.write_parquet(part_path)

            part_paths.append(part_path)

            print(f"  OK filas: {df_std.height}")

        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    if not part_paths:
        print("\nNo se generaron partes.")
        return

    print("\nConsolidando standardized_raw_fuga...")

    frames = [pl.read_parquet(p) for p in part_paths]
    final_df = pl.concat(frames, how="diagonal_relaxed")

    final_df.write_parquet(OUTPUT_PATH)

    print("\nListo.")
    print(f"Archivo generado: {OUTPUT_PATH}")
    print(f"Filas totales: {final_df.height}")
    print(f"Columnas totales: {len(final_df.columns)}")


if __name__ == "__main__":
    main()
