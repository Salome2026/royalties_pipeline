import hashlib
from datetime import datetime
from pathlib import Path

import duckdb
import polars as pl


# =========================
# CONFIG
# =========================

INPUT_FILE = Path(
    r"C:\royalties_pipeline\input_raw\fuga\YouTubeAdsupportedCorrectionStatementRun_INDYANARECORDSLLC-royalty_product_and_asset.csv"
)

DETAIL_PATH = Path(r"C:\royalties_pipeline\warehouse\detail\royalties_detail.parquet")

SOURCE = "fuga"
ACCOUNT = "indyana_records"
STATEMENT_PERIOD = "2025-12"   # 🔥 AJUSTALO SI QUERÉS


# =========================

def sha256_file(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_decimal(col_name: str) -> pl.Expr:
    return (
        pl.col(col_name)
        .cast(pl.Utf8)
        .str.replace_all(",", ".")
        .str.strip_chars()
        .cast(pl.Float64, strict=False)
    )


def main():
    if not INPUT_FILE.exists():
        print("No existe archivo:")
        print(INPUT_FILE)
        return

    print("Leyendo archivo corrección...")

    df = pl.read_csv(
        INPUT_FILE,
        separator=",",
        quote_char='"',
        ignore_errors=True,
        infer_schema_length=10000,
    )

    df = df.rename({col: col.strip() for col in df.columns})

    print("Filas archivo:", df.height)

    # =========================
    # FILTRAR SOLO NUEVOS (por Sale ID)
    # =========================

    con = duckdb.connect()

    existing = con.execute(
        """
        SELECT DISTINCT CAST("Sale ID" AS VARCHAR) AS sale_id
        FROM read_parquet(?)
        WHERE source = 'fuga'
          AND "Sale ID" IS NOT NULL
        """,
        [str(DETAIL_PATH)]
    ).fetchdf()

    existing_ids = set(existing["sale_id"])

    df = df.with_columns(
        pl.col("Sale ID").cast(pl.Utf8).alias("sale_id")
    )

    df_new = df.filter(~pl.col("sale_id").is_in(existing_ids))

    print("Filas nuevas:", df_new.height)

    if df_new.height == 0:
        print("No hay registros nuevos. No se carga nada.")
        return

    # =========================
    # STANDARDIZE
    # =========================

    df_new = df_new.with_columns([
        normalize_decimal("Reported Royalty").alias("net_amount"),
        normalize_decimal("Reported Royalty").alias("net_amount_eur"),

        pl.when(
            pl.col("Product Artist").is_not_null() &
            (pl.col("Product Artist").str.strip_chars() != "")
        )
        .then(pl.col("Product Artist"))
        .otherwise(pl.col("Product Title"))
        .alias("artist_statement_style"),

        pl.col("Sale Start date")
            .cast(pl.Utf8)
            .str.slice(0, 7)
            .alias("transaction_month"),

        pl.lit(SOURCE).alias("source"),
        pl.lit(ACCOUNT).alias("account"),
        pl.lit(STATEMENT_PERIOD).alias("statement_period"),
        pl.lit("correction").alias("statement_type"),

        pl.lit(INPUT_FILE.name).alias("statement_file_name"),
        pl.lit(str(INPUT_FILE)).alias("statement_file_path"),
        pl.lit(sha256_file(INPUT_FILE)).alias("statement_file_hash"),
        pl.lit(datetime.now().isoformat(timespec="seconds")).alias("ingested_at"),
    ])

    # =========================
    # APPEND AL DETAIL
    # =========================

    detail = pl.read_parquet[str(DETAIL_PATH)]

    detail_final = pl.concat([detail, df_new], how="diagonal_relaxed")

    detail_final.write_parquet[str(DETAIL_PATH)]

    print("Corrección cargada correctamente.")
    print("Filas agregadas:", df_new.height)


if __name__ == "__main__":
    main()