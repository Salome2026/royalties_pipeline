import argparse
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import polars as pl

from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


BASE = Path(r"C:\royalties_pipeline")
MARTS = BASE / "warehouse" / "marts"
REPORTS = BASE / "reports"

SONG_PATH = MARTS / "song_level_all_sources.parquet"
STANDARDIZED_PATH = MARTS / "standardized_raw_all_sources.parquet"


SEARCH_COLUMNS_SONG = [
    "asset_isrc",
    "track_statement_style",
    "asset_title_statement",
    "artist_statement_style",
    "asset_artist_statement",
    "source",
    "account",
    "content_type",
    "source_sheet",
    "revenue_basis",
]

SEARCH_COLUMNS_STANDARDIZED = [
    "asset_isrc",
    "ISRC",
    "Track Title",
    "Asset Title",
    "Product Title",
    "track_statement_style",
    "asset_title_statement",
    "artist_statement_style",
    "asset_artist_statement",
    "Track Artists",
    "Artist Name",
    "Product Artist",
    "TRACK ARTIST",
    "TRACK",
    "source",
    "account",
    "store_name",
    "Store",
    "DSP",
    "territory",
]


HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)
TOTAL_FILL = PatternFill(start_color="BDD7EE", end_color="BDD7EE", fill_type="solid")
TOTAL_FONT = Font(bold=True)
CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")

DISPLAY_HEADERS = {
    "keywords": "Filtro",
    "mode": "Coincidencia",
    "start_month": "Desde",
    "end_month": "Hasta",
    "song_level_rows": "Filas song level",
    "song_level_amount_usd": "Ingresos USD",
    "raw_sample_rows": "Filas raw",
    "generated_at": "Generado el",
    "source": "Fuente",
    "account": "Cuenta",
    "transaction_month": "Mes",
    "amount_usd": "Ingresos USD",
    "units": "Unidades",
    "rows": "Filas",
    "asset_isrc": "ISRC",
    "track_statement_style": "Tema",
    "asset_title_statement": "Asset title",
    "artist_statement_style": "Artista",
    "asset_artist_statement": "Asset artist",
    "content_type": "Tipo de contenido",
    "first_month": "Desde",
    "last_month": "Hasta",
    "source_sheet": "Hoja origen",
    "revenue_basis": "Base ingreso",
    "match_text": "Texto coincidente",
    "statement_period": "Periodo statement",
    "net_amount": "Importe neto",
    "store_name": "Tienda",
    "territory": "Territorio",
    "statement_file_name": "Archivo statement",
    "hoja": "Hoja",
    "contenido": "Contenido",
    "resultado": "Resultado",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Genera un reporte dinamico de royalties por palabras clave."
    )
    parser.add_argument(
        "keywords",
        nargs="*",
        help="Palabras clave. Si no se pasan, el script las pide por consola.",
    )
    parser.add_argument(
        "--mode",
        choices=["any", "all"],
        default="any",
        help="any = matchea cualquier keyword; all = exige todas.",
    )
    parser.add_argument(
        "--raw-limit",
        type=int,
        default=5000,
        help="Maximo de filas en la hoja raw_matches_sample.",
    )
    parser.add_argument(
        "--start-month",
        help="Mes inicial YYYY-MM. Filtra por transaction_month.",
    )
    parser.add_argument(
        "--end-month",
        help="Mes final YYYY-MM. Filtra por transaction_month.",
    )
    return parser.parse_args()


def normalize_keywords(raw_keywords: list[str]) -> list[str]:
    keywords = []

    for item in raw_keywords:
        parts = [part.strip() for part in re.split(r"[;,]", item) if part.strip()]
        keywords.extend(parts)

    return keywords


def prompt_keywords() -> list[str]:
    raw = input("Palabras clave a buscar, separadas por coma: ").strip()
    return normalize_keywords([raw])


def existing_columns(path: Path) -> set[str]:
    return set(pl.scan_parquet(path).collect_schema().names())


def contains_expr(columns: set[str], search_columns: list[str], keyword: str) -> pl.Expr:
    exprs = []

    for col in search_columns:
        if col in columns:
            exprs.append(
                pl.col(col)
                .cast(pl.Utf8)
                .str.to_lowercase()
                .str.contains(keyword.lower(), literal=True)
                .fill_null(False)
            )

    if not exprs:
        return pl.lit(False)

    result = exprs[0]
    for expr in exprs[1:]:
        result = result | expr

    return result


def build_filter(columns: set[str], search_columns: list[str], keywords: list[str], mode: str) -> pl.Expr:
    exprs = [contains_expr(columns, search_columns, keyword) for keyword in keywords]

    result = exprs[0]

    for expr in exprs[1:]:
        if mode == "all":
            result = result & expr
        else:
            result = result | expr

    return result


def add_match_text(lf: pl.LazyFrame, columns: set[str], search_columns: list[str]) -> pl.LazyFrame:
    usable = [col for col in search_columns if col in columns]

    if not usable:
        return lf.with_columns(pl.lit("").alias("match_text"))

    return lf.with_columns(
        pl.concat_str(
            [pl.col(col).cast(pl.Utf8).fill_null("") for col in usable],
            separator=" | ",
        ).alias("match_text")
    )


def safe_select(df: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
    existing = [col for col in columns if col in df.columns]
    return df.select(existing)


def display_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    return dataframe.rename(columns={col: DISPLAY_HEADERS.get(col, col) for col in dataframe.columns})


def prepare_sheet(ws):
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER

    amount_headers = {
        "amount_usd",
        "song_level_amount_usd",
        "net_amount",
        "Ingresos USD",
        "Importe neto",
    }
    integer_headers = {
        "units",
        "rows",
        "song_level_rows",
        "raw_sample_rows",
        "Unidades",
        "Filas",
        "Filas song level",
        "Filas raw",
    }

    header_by_column = {
        cell.column: str(cell.value) if cell.value is not None else ""
        for cell in ws[1]
    }

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            header = header_by_column.get(cell.column, "")
            if header in amount_headers:
                cell.number_format = '$#,##0.00'
            elif header in integer_headers:
                cell.number_format = '#,##0'

    for column_cells in ws.columns:
        col_letter = get_column_letter(column_cells[0].column)
        max_len = 0

        for cell in column_cells[:300]:
            if cell.value is not None:
                max_len = max(max_len, len(str(cell.value)))

        ws.column_dimensions[col_letter].width = min(max_len + 2, 50)


def add_period_filter(lf: pl.LazyFrame, columns: set[str], start_month: str | None, end_month: str | None) -> pl.LazyFrame:
    if "transaction_month" not in columns:
        return lf

    if start_month:
        lf = lf.filter(pl.col("transaction_month").cast(pl.Utf8) >= start_month)

    if end_month:
        lf = lf.filter(pl.col("transaction_month").cast(pl.Utf8) <= end_month)

    return lf


def style_workbook(writer):
    for ws in writer.book.worksheets:
        prepare_sheet(ws)


def instructions_dataframe() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "hoja": "overview",
            "contenido": "Resumen de parametros usados, cantidad de filas encontradas, total USD y fecha de generacion.",
        },
        {
            "hoja": "source_summary",
            "contenido": "Totales agrupados por compania/source y account.",
        },
        {
            "hoja": "monthly_summary",
            "contenido": "Totales agrupados por mes de transaccion.",
        },
        {
            "hoja": "track_summary",
            "contenido": "Totales por tema/asset, ISRC, artista, tipo de contenido y periodo encontrado.",
        },
        {
            "hoja": "song_matches",
            "contenido": "Detalle agregado a nivel tema usado para calcular los totales del reporte.",
        },
        {
            "hoja": "raw_matches_sample",
            "contenido": "Muestra de filas crudas normalizadas para auditoria. Esta hoja puede estar limitada por raw_limit.",
        },
    ])


def report_output_path(
    keywords: list[str],
    start_month: str | None,
    end_month: str | None,
    output_dir: Path,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", "_".join(keywords)).strip("_").lower()[:60]
    period_slug = ""
    if start_month or end_month:
        period_slug = f"_{start_month or 'start'}_to_{end_month or 'end'}"
    return output_dir / f"keyword_royalty_report_{slug}{period_slug}_{timestamp}.xlsx"


def build_report_tables(
    keywords: list[str],
    mode: str,
    raw_limit: int,
    start_month: str | None = None,
    end_month: str | None = None,
    song_path: Path = SONG_PATH,
    standardized_path: Path = STANDARDIZED_PATH,
) -> dict[str, pd.DataFrame]:
    song_cols = existing_columns(song_path)
    song_filter = build_filter(song_cols, SEARCH_COLUMNS_SONG, keywords, mode)

    song = (
        add_period_filter(
            add_match_text(pl.scan_parquet(song_path), song_cols, SEARCH_COLUMNS_SONG),
            song_cols,
            start_month,
            end_month,
        )
        .filter(song_filter)
        .collect()
    )

    if song.height == 0:
        print("No hubo matches en song_level_all_sources.")
        return {
            "instructions": display_dataframe(instructions_dataframe()),
            "overview": display_dataframe(pd.DataFrame([{
                "keywords": ", ".join(keywords),
                "mode": mode,
                "start_month": start_month or "",
                "end_month": end_month or "",
                "song_level_rows": 0,
                "song_level_amount_usd": 0,
                "raw_sample_rows": 0,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            }])),
            "sin_resultados": display_dataframe(pd.DataFrame([{
                "resultado": "Sin coincidencias para los parametros ingresados."
            }])),
        }

    source_summary = (
        song
        .group_by(["source", "account"])
        .agg([
            pl.sum("amount_usd").alias("amount_usd"),
            pl.sum("units").alias("units"),
            pl.len().alias("rows"),
        ])
        .sort("amount_usd", descending=True)
    )

    monthly_summary = (
        song
        .group_by(["transaction_month"])
        .agg([
            pl.sum("amount_usd").alias("amount_usd"),
            pl.sum("units").alias("units"),
            pl.len().alias("rows"),
        ])
        .sort("transaction_month")
    )

    track_summary = (
        song
        .group_by([
            "source",
            "account",
            "asset_isrc",
            "track_statement_style",
            "asset_title_statement",
            "artist_statement_style",
            "asset_artist_statement",
            "content_type",
        ])
        .agg([
            pl.sum("amount_usd").alias("amount_usd"),
            pl.sum("units").alias("units"),
            pl.min("transaction_month").alias("first_month"),
            pl.max("transaction_month").alias("last_month"),
            pl.len().alias("rows"),
        ])
        .sort("amount_usd", descending=True)
    )

    raw_sample = pl.DataFrame()
    if standardized_path.exists():
        raw_cols = existing_columns(standardized_path)
        raw_filter = build_filter(raw_cols, SEARCH_COLUMNS_STANDARDIZED, keywords, mode)

        raw_sample = (
            add_period_filter(
                add_match_text(pl.scan_parquet(standardized_path), raw_cols, SEARCH_COLUMNS_STANDARDIZED),
                raw_cols,
                start_month,
                end_month,
            )
            .filter(raw_filter)
            .select([
                col for col in [
                    "source",
                    "account",
                    "statement_period",
                    "transaction_month",
                    "artist_statement_style",
                    "track_statement_style",
                    "asset_isrc",
                    "amount_usd",
                    "net_amount",
                    "units",
                    "store_name",
                    "territory",
                    "statement_file_name",
                    "match_text",
                ]
                if col in raw_cols or col == "match_text"
            ])
            .limit(raw_limit)
            .collect()
        )

    tables = {
        "instructions": display_dataframe(instructions_dataframe()),
        "overview": display_dataframe(pd.DataFrame([{
            "keywords": ", ".join(keywords),
            "mode": mode,
            "start_month": start_month or "",
            "end_month": end_month or "",
            "song_level_rows": song.height,
            "song_level_amount_usd": song["amount_usd"].sum(),
            "raw_sample_rows": raw_sample.height if raw_sample.height > 0 else 0,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }])),
        "source_summary": display_dataframe(source_summary.to_pandas()),
        "monthly_summary": display_dataframe(monthly_summary.to_pandas()),
        "track_summary": display_dataframe(track_summary.to_pandas()),
        "song_matches": display_dataframe(safe_select(
            song.sort("amount_usd", descending=True),
            [
                "source",
                "account",
                "transaction_month",
                "asset_isrc",
                "track_statement_style",
                "asset_title_statement",
                "artist_statement_style",
                "asset_artist_statement",
                "content_type",
                "amount_usd",
                "units",
                "source_sheet",
                "revenue_basis",
                "match_text",
            ],
        ).to_pandas()),
    }

    if raw_sample.height > 0:
        tables["raw_matches_sample"] = display_dataframe(raw_sample.to_pandas())

    return tables


def build_report(
    keywords: list[str],
    mode: str,
    raw_limit: int,
    start_month: str | None = None,
    end_month: str | None = None,
    song_path: Path = SONG_PATH,
    standardized_path: Path = STANDARDIZED_PATH,
    output_dir: Path = REPORTS,
) -> Path:
    output_path = report_output_path(keywords, start_month, end_month, output_dir)
    tables = build_report_tables(
        keywords=keywords,
        mode=mode,
        raw_limit=raw_limit,
        start_month=start_month,
        end_month=end_month,
        song_path=song_path,
        standardized_path=standardized_path,
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, dataframe in tables.items():
            dataframe.to_excel(writer, index=False, sheet_name=sheet_name)

        style_workbook(writer)

    return output_path


def main():
    args = parse_args()
    keywords = normalize_keywords(args.keywords) if args.keywords else prompt_keywords()

    if not keywords:
        print("No ingresaste palabras clave.")
        raise SystemExit(1)

    print("Buscando:", ", ".join(keywords))
    print("Modo:", args.mode)

    output_path = build_report(
        keywords=keywords,
        mode=args.mode,
        raw_limit=args.raw_limit,
        start_month=args.start_month,
        end_month=args.end_month,
    )

    print("\nReporte generado:")
    print(output_path)


if __name__ == "__main__":
    main()
