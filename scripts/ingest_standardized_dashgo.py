import hashlib
import sys
from datetime import datetime
from pathlib import Path

import polars as pl

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

from lib.statement_period import from_dashgo_filename


BASE_DIR = Path(r"C:\royalties_pipeline")

INPUT_DIR = BASE_DIR / "input_raw" / "dashgo"
OUTPUT_PATH = BASE_DIR / "warehouse" / "marts" / "standardized_raw_dashgo.parquet"
TEMP_DIR = BASE_DIR / "staging" / "standardized_raw_parts" / "dashgo"

SOURCE = "dashgo"
ACCOUNT = "mawzrecords"


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
    return from_dashgo_filename(file_name).period


def read_dashgo_csv(file_path: Path) -> pl.DataFrame:
    return pl.read_csv(
        file_path,
        separator=",",
        quote_char='"',
        ignore_errors=True,
        infer_schema_length=10000,
        encoding="utf8-lossy",
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


def standardize_dashgo(df: pl.DataFrame, file_path: Path) -> pl.DataFrame:
    df = clean_columns(df)
    cols = set(df.columns)

    required_cols = [
        "Transaction Date",
        "Artist Name",
        "Track Title",
        "Payable",
    ]

    missing = [c for c in required_cols if c not in cols]
    if missing:
        raise ValueError(f"Faltan columnas requeridas: {missing}")

    file_hash = sha256_file(file_path)
    statement_info = from_dashgo_filename(file_path.name)
    statement_period = statement_info.period
    ingested_at = datetime.now().isoformat(timespec="seconds")

    payable = decimal_expr("Payable", cols)

    artist_name = text_expr("Artist Name", cols)
    track_title = text_expr("Track Title", cols)

    artist_statement_style = (
        pl.when(
            artist_name.is_not_null()
            & (artist_name != "")
        )
        .then(artist_name)
        .when(
            track_title.is_not_null()
            & (track_title != "")
            & track_title.str.to_lowercase().str.starts_with("auto generated asset")
        )
        .then(pl.lit("No Identificado"))
        .otherwise(track_title)
    )

    df = df.with_columns([
        # =========================
        # Amounts - legacy logic
        # =========================
        payable.alias("amount_usd"),
        payable.alias("net_amount"),
        payable.alias("net_amount_usd"),

        text_expr("Currency", cols).alias("currency_original"),

        decimal_expr("Revenue", cols).alias("revenue_original"),
        decimal_expr("Exchange Rate", cols).alias("exchange_rate_original"),
        decimal_expr("USD Revenue", cols).alias("usd_revenue"),
        decimal_expr("Net Revenue", cols).alias("net_revenue"),
        decimal_expr("Payable", cols).alias("payable"),

        # =========================
        # Dates
        # =========================
        text_expr("Transaction Date", cols)
            .str.slice(0, 7)
            .alias("transaction_month"),

        text_expr("Transaction Date", cols).alias("transaction_date"),

        # =========================
        # Legacy artist logic
        # =========================
        artist_statement_style.alias("artist_statement_style"),

        # =========================
        # Music metadata
        # =========================
        text_expr("Artist Name", cols).alias("artist_name_statement"),
        text_expr("Track Artist", cols).alias("track_artist_statement"),
        text_expr("Track Title", cols).alias("track_statement_style"),
        text_expr("Album Name", cols).alias("album_statement_style"),
        text_expr("Label Name", cols).alias("label_statement_style"),

        text_expr("ISRC", cols).alias("asset_isrc"),
        text_expr("UPC", cols).alias("product_upc"),
        text_expr("Label Track ID", cols).alias("label_track_id"),
        text_expr("Composers", cols).alias("composers"),

        # =========================
        # Commercial dimensions
        # =========================
        text_expr("Store", cols).alias("store_name"),
        text_expr("Region", cols).alias("territory"),
        text_expr("Product Type", cols).alias("product_type"),
        text_expr("Use Type", cols).alias("use_type"),

        decimal_expr("Units", cols).alias("units"),

        text_expr("Deal Share", cols).alias("deal_share"),
        text_expr("Distribution Rate", cols).alias("distribution_rate"),
        text_expr("Revenue Split (Y/N)", cols).alias("revenue_split_flag"),
        text_expr("Noise Content (Y/N)", cols).alias("noise_content_flag"),
        text_expr("Spatial Availability Indicator (Y/N)", cols).alias("spatial_availability_flag"),
        text_expr("Cover Song", cols).alias("cover_song"),

        decimal_expr("Mechanical Royalty", cols).alias("mechanical_royalty"),
        decimal_expr("Pub Admin Fee", cols).alias("pub_admin_fee"),

        # =========================
        # IDs
        # =========================
        text_expr("VideoId", cols).alias("video_id"),
        text_expr("ChannelId", cols).alias("channel_id"),

        # =========================
        # Metadata
        # =========================
        pl.lit(SOURCE).alias("source"),
        pl.lit(ACCOUNT).alias("account"),
        pl.lit(statement_period).alias("statement_period"),
        pl.lit(statement_info.source).alias("statement_period_source"),
        pl.lit(statement_info.note).alias("statement_period_note"),
        pl.lit("regular").alias("statement_type"),

        pl.lit(file_path.name).alias("statement_file_name"),
        pl.lit(str(file_path)).alias("statement_file_path"),
        pl.lit(file_hash).alias("statement_file_hash"),
        pl.lit(ingested_at).alias("ingested_at"),
    ])

    return df


def main():
    ensure_dirs()

    if not INPUT_DIR.exists():
        print(f"No existe carpeta: {INPUT_DIR}")
        return

    csv_files = sorted(INPUT_DIR.glob("*.csv"))

    print("DashGo standardized ingest")
    print(f"Archivos encontrados: {len(csv_files)}")
    print(f"Output: {OUTPUT_PATH}")
    print(f"Temp: {TEMP_DIR}")

    if not csv_files:
        print(r"No se encontraron CSV en input_raw\dashgo")
        return

    part_paths = []

    for file_path in csv_files:
        print(f"\nProcesando: {file_path.name}")

        try:
            df = read_dashgo_csv(file_path)
            print(f"  Filas crudas: {df.height}")

            if df.height == 0:
                print("  Archivo vacío. Se omite.")
                continue

            df_std = standardize_dashgo(df, file_path)

            part_path = TEMP_DIR / f"dashgo_{file_path.stem}_{sha256_file(file_path)[:12]}.parquet"
            df_std.write_parquet(part_path)

            part_paths.append(part_path)

            print(f"  OK filas: {df_std.height}")

        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    if not part_paths:
        print("\nNo se generaron partes.")
        return

    print("\nConsolidando standardized_raw_dashgo...")

    frames = [pl.read_parquet(p) for p in part_paths]
    final_df = pl.concat(frames, how="diagonal_relaxed")

    final_df.write_parquet(OUTPUT_PATH)

    print("\nListo.")
    print(f"Archivo generado: {OUTPUT_PATH}")
    print(f"Filas totales: {final_df.height}")
    print(f"Columnas totales: {len(final_df.columns)}")


if __name__ == "__main__":
    main()
