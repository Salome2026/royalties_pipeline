from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl


BASE = Path(r"C:\royalties_pipeline")
STANDARDIZED_PATH = BASE / "warehouse" / "booking" / "standardized" / "standardized_booking_movements.parquet"
PRESENTACIONES_PATH = BASE / "warehouse" / "booking" / "raw" / "booking_raw_pm_presentaciones.parquet"
REPORT_DIR = BASE / "reports" / "booking"
OUTPUT_CSV = REPORT_DIR / "booking_shows_report_base.csv"


def parse_number(value: object) -> float | None:
    if value is None:
        return None

    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return None

    text = (
        text.replace("$", "")
        .replace("u$s", "")
        .replace("usd", "")
        .replace("ars", "")
        .replace("%", "")
        .replace(" ", "")
    )

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def parse_date(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass

    return None


def normalize_text_expr(name: str) -> pl.Expr:
    return pl.col(name).cast(pl.Utf8).str.strip_chars().str.to_lowercase()


def pm_david_presentaciones_rows() -> pl.DataFrame:
    return (
        pl.read_parquet(PRESENTACIONES_PATH)
        .filter(pl.col("source_file_name") == "PM David Carbone (1).xlsx")
        .select([
            pl.col("Todos").cast(pl.Utf8).str.strip_chars().alias("artista"),
            pl.col("Todos.1").map_elements(parse_date, return_dtype=pl.Utf8).str.to_date().alias("fecha"),
            pl.col("Evento").cast(pl.Utf8).str.strip_chars().alias("venue_evento"),
            pl.col("Cachet $").map_elements(parse_number, return_dtype=pl.Float64).alias("cachet_show"),
            pl.col("Neto $").map_elements(parse_number, return_dtype=pl.Float64).alias("neto_planilla"),
            pl.col("Todos %").map_elements(parse_number, return_dtype=pl.Float64).alias("porcentaje_artista_raw"),
            pl.col("Todos $").map_elements(parse_number, return_dtype=pl.Float64).alias("se_lleva_artista"),
            pl.col("Indyana $").map_elements(parse_number, return_dtype=pl.Float64).alias("se_lleva_indyana"),
            pl.col("Cachet u$").map_elements(parse_number, return_dtype=pl.Float64).alias("cachet_show_usd"),
            pl.col("Neto U$").map_elements(parse_number, return_dtype=pl.Float64).alias("neto_show_usd"),
            pl.col("source_file_name").alias("archivo_origen"),
        ])
        .filter(
            pl.col("artista").is_not_null()
            & pl.col("fecha").is_not_null()
            & pl.col("venue_evento").is_not_null()
            & pl.col("cachet_show").is_not_null()
            & (pl.col("cachet_show") > 0)
        )
        .with_columns([
            pl.lit(0).cast(pl.Float64).alias("cachet_informado_no_contabilizado"),
            (pl.col("cachet_show") - pl.col("neto_planilla").fill_null(pl.col("cachet_show"))).alias("gastos"),
            pl.col("neto_planilla").fill_null(pl.col("cachet_show")).alias("neto_show"),
            pl.when(pl.col("porcentaje_artista_raw").is_not_null() & (pl.col("porcentaje_artista_raw") > 1))
            .then(pl.col("porcentaje_artista_raw") / 100)
            .otherwise(pl.col("porcentaje_artista_raw"))
            .alias("porcentaje_artista"),
            pl.lit(0).cast(pl.Float64).alias("gastos_usd"),
            pl.lit(1).cast(pl.Int64).alias("lineas_ingreso"),
            pl.lit(0).cast(pl.Int64).alias("lineas_gasto"),
            pl.lit(1).cast(pl.Int64).alias("lineas_total"),
            pl.lit("pm_david_presentaciones").alias("control"),
        ])
        .with_columns([
            (1 - pl.col("porcentaje_artista")).alias("porcentaje_productora"),
            pl.col("se_lleva_artista").alias("importe_artista_planilla"),
            pl.col("se_lleva_indyana").alias("importe_productora_planilla"),
            pl.col("se_lleva_artista").alias("se_lleva_artista_movimientos"),
        ])
        .select([
            "artista",
            "fecha",
            "venue_evento",
            "cachet_informado_no_contabilizado",
            "cachet_show",
            "gastos",
            "neto_show",
            "porcentaje_artista",
            "porcentaje_productora",
            "se_lleva_artista",
            "se_lleva_indyana",
            "importe_artista_planilla",
            "importe_productora_planilla",
            "se_lleva_artista_movimientos",
            "cachet_show_usd",
            "gastos_usd",
            "neto_show_usd",
            "lineas_ingreso",
            "lineas_gasto",
            "lineas_total",
            "control",
            "archivo_origen",
        ])
    )


def main() -> None:
    print("Building booking shows report base...")

    movements = pl.read_parquet(STANDARDIZED_PATH)

    show_movements = movements.filter(
        (pl.col("business_area") == "booking")
        & (pl.col("movement_subcategory").str.to_lowercase() == "show")
    ).with_columns(
        pl.col("concept").str.to_lowercase().str.strip_chars().alias("concept_key"),
    ).with_columns([
        pl.col("movement_date").is_null().alias("is_non_accountable"),
        pl.when((pl.col("movement_type") == "income") & pl.col("movement_date").is_null())
        .then(pl.col("amount_ars"))
        .otherwise(0)
        .alias("cachet_informado_no_contabilizado"),
        pl.when((pl.col("movement_type") == "income") & pl.col("movement_date").is_not_null())
        .then(pl.col("amount_ars"))
        .otherwise(0)
        .alias("cachet_show"),
        pl.when(
            (pl.col("movement_type") == "expense")
            & (pl.col("concept_key") != "cachet")
            & pl.col("movement_date").is_not_null()
        )
        .then(pl.col("amount_ars"))
        .otherwise(0)
        .alias("gastos_show"),
        pl.when(
            (pl.col("movement_type") == "expense")
            & (pl.col("concept_key") == "cachet")
            & pl.col("movement_date").is_not_null()
        )
        .then(pl.col("amount_ars"))
        .otherwise(0)
        .alias("artist_take_from_expenses"),
        pl.when((pl.col("movement_type") == "income") & pl.col("movement_date").is_not_null())
        .then(pl.col("amount_usd"))
        .otherwise(0)
        .alias("cachet_show_usd"),
        pl.when(
            (pl.col("movement_type") == "expense")
            & (pl.col("concept_key") != "cachet")
            & pl.col("movement_date").is_not_null()
        )
        .then(pl.col("amount_usd"))
        .otherwise(0)
        .alias("gastos_show_usd"),
        pl.when(
            (pl.col("movement_type") == "expense")
            & (pl.col("concept_key") == "cachet")
            & pl.col("movement_date").is_not_null()
        )
        .then(pl.col("amount_usd"))
        .otherwise(0)
        .alias("artist_take_usd_from_expenses"),
        (pl.col("movement_type") == "income").cast(pl.UInt32).alias("lineas_ingreso"),
        (pl.col("movement_type") == "expense").cast(pl.UInt32).alias("lineas_gasto"),
    ])

    grouped = (
        show_movements
        .group_by([
            "source_file_name",
            "artist_statement",
            "movement_date",
            "event_detail",
        ])
        .agg([
            pl.max("is_non_accountable").alias("is_non_accountable"),
            pl.sum("cachet_informado_no_contabilizado").alias("cachet_informado_no_contabilizado"),
            pl.sum("cachet_show").alias("cachet_show"),
            pl.sum("gastos_show").alias("gastos"),
            pl.sum("artist_take_from_expenses").alias("se_lleva_artista_movimientos"),
            pl.sum("cachet_show_usd").alias("cachet_show_usd"),
            pl.sum("gastos_show_usd").alias("gastos_usd"),
            pl.sum("artist_take_usd_from_expenses").alias("se_lleva_artista_usd_movimientos"),
            pl.sum("lineas_ingreso").alias("lineas_ingreso"),
            pl.sum("lineas_gasto").alias("lineas_gasto"),
            pl.len().alias("lineas_total"),
            pl.col("standardization_status").drop_nulls().str.join(" | ").alias("status_origen"),
        ])
        .with_columns([
            (pl.col("cachet_show") - pl.col("gastos")).alias("neto_show"),
            (pl.col("cachet_show_usd") - pl.col("gastos_usd")).alias("neto_show_usd"),
        ])
    )

    presentaciones = (
        pl.read_parquet(PRESENTACIONES_PATH)
        .select([
            pl.col("source_file_name"),
            pl.col("Todos").cast(pl.Utf8).str.strip_chars().alias("artist_statement_presentaciones"),
            pl.col("Todos.1").map_elements(parse_date, return_dtype=pl.Utf8).str.to_date().alias("movement_date_presentaciones"),
            pl.col("Evento").cast(pl.Utf8).str.strip_chars().alias("event_detail_presentaciones"),
            pl.col("Todos %").map_elements(parse_number, return_dtype=pl.Float64).alias("porcentaje_artista_raw"),
            pl.col("Todos $").map_elements(parse_number, return_dtype=pl.Float64).alias("artist_share_ars_presentaciones"),
            pl.col("Indyana $").map_elements(parse_number, return_dtype=pl.Float64).alias("productora_share_ars_presentaciones"),
        ])
        .filter(
            pl.col("artist_statement_presentaciones").is_not_null()
            & pl.col("movement_date_presentaciones").is_not_null()
            & pl.col("event_detail_presentaciones").is_not_null()
        )
        .with_columns([
            normalize_text_expr("artist_statement_presentaciones").alias("artist_key"),
            normalize_text_expr("event_detail_presentaciones").alias("event_key"),
        ])
        .group_by(["source_file_name", "artist_key", "movement_date_presentaciones", "event_key"])
        .agg([
            pl.max("porcentaje_artista_raw").alias("porcentaje_artista_raw"),
            pl.sum("artist_share_ars_presentaciones").alias("artist_share_ars_presentaciones"),
            pl.sum("productora_share_ars_presentaciones").alias("productora_share_ars_presentaciones"),
        ])
    )

    report = (
        grouped
        .with_columns([
            normalize_text_expr("artist_statement").alias("artist_key"),
            normalize_text_expr("event_detail").alias("event_key"),
        ])
        .join(
            presentaciones,
            left_on=["source_file_name", "artist_key", "movement_date", "event_key"],
            right_on=["source_file_name", "artist_key", "movement_date_presentaciones", "event_key"],
            how="left",
        )
        .with_columns([
            pl.when(pl.col("porcentaje_artista_raw").is_not_null() & (pl.col("porcentaje_artista_raw") > 1))
            .then(pl.col("porcentaje_artista_raw") / 100)
            .otherwise(pl.col("porcentaje_artista_raw"))
            .alias("porcentaje_artista"),
        ])
        .with_columns([
            (1 - pl.col("porcentaje_artista")).alias("porcentaje_productora"),
            pl.when(pl.col("is_non_accountable"))
            .then(0)
            .otherwise(
                pl.coalesce([
                    pl.col("artist_share_ars_presentaciones"),
                    pl.col("se_lleva_artista_movimientos"),
                ])
            )
            .alias("se_lleva_artista"),
            pl.when(pl.col("is_non_accountable"))
            .then(0)
            .otherwise(
                pl.coalesce([
                    pl.col("productora_share_ars_presentaciones"),
                    pl.col("neto_show") - pl.col("se_lleva_artista_movimientos"),
                ])
            )
            .alias("se_lleva_indyana"),
            pl.when(pl.col("is_non_accountable"))
            .then(pl.lit("no_contabiliza_sin_fecha"))
            .when(pl.col("porcentaje_artista").is_null())
            .then(pl.lit("sin_porcentaje_presentaciones"))
            .when(pl.col("cachet_show") == 0)
            .then(pl.lit("cachet_cero"))
            .when(pl.col("lineas_gasto") == 0)
            .then(pl.lit("sin_gastos"))
            .when(pl.col("status_origen").str.contains("needs_review", literal=True))
            .then(pl.lit("revisar_origen"))
            .otherwise(pl.lit("ok"))
            .alias("control"),
        ])
        .select([
            pl.col("artist_statement").alias("artista"),
            pl.col("movement_date").alias("fecha"),
            pl.col("event_detail").alias("venue_evento"),
            pl.col("cachet_informado_no_contabilizado"),
            pl.col("cachet_show"),
            pl.col("gastos"),
            pl.col("neto_show"),
            pl.col("porcentaje_artista"),
            pl.col("porcentaje_productora"),
            pl.col("se_lleva_artista"),
            pl.col("se_lleva_indyana"),
            pl.col("artist_share_ars_presentaciones").alias("importe_artista_planilla"),
            pl.col("productora_share_ars_presentaciones").alias("importe_productora_planilla"),
            pl.col("se_lleva_artista_movimientos"),
            pl.col("cachet_show_usd"),
            pl.col("gastos_usd"),
            pl.col("neto_show_usd"),
            pl.col("lineas_ingreso"),
            pl.col("lineas_gasto"),
            pl.col("lineas_total"),
            pl.col("control"),
            pl.col("source_file_name").alias("archivo_origen"),
        ])
        .sort(["artista", "fecha", "venue_evento", "archivo_origen"])
    )

    report = pl.concat([report, pm_david_presentaciones_rows()], how="diagonal_relaxed").sort([
        "artista",
        "fecha",
        "venue_evento",
        "archivo_origen",
    ])

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report.write_csv(OUTPUT_CSV)

    print("Rows:", report.height)
    print("Output:", OUTPUT_CSV)
    print("Cachet:", report["cachet_show"].sum())
    print("Gastos:", report["gastos"].sum())
    print("Neto:", report["neto_show"].sum())
    print("Controls:")
    for row in report.group_by("control").agg(pl.len().alias("rows")).sort("rows", descending=True).to_dicts():
        print(f"  - {row['control']}: {row['rows']}")


if __name__ == "__main__":
    main()
