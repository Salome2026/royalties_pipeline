import argparse
import re
import tempfile
from copy import copy
from datetime import datetime
from pathlib import Path

import pandas as pd
import polars as pl
from scripts.lib.catalog_artist_dictionary import display_credit, search_terms
from scripts.lib.dashgo_video_identity import compile_video_groups, with_video_groups, SUMMARY_VIDEO, SUMMARY_TITLE
try:
    from lib.product_income import scan_income
except ModuleNotFoundError:
    from scripts.lib.product_income import scan_income
try:
    from lib.video_context import source_units_expr, preserve_video_context, separate_channel_video_expr
    from lib.report_presentation import YOUTUBE_CHANNEL_LABEL, youtube_video_url
except ModuleNotFoundError:
    from scripts.lib.video_context import source_units_expr, preserve_video_context, separate_channel_video_expr
    from scripts.lib.report_presentation import YOUTUBE_CHANNEL_LABEL, youtube_video_url

try:
    from lib.ada_identity import ada_isrc_expr, ada_native_code_expr, ada_native_code_type_expr, ada_source_expr
except ModuleNotFoundError:
    from scripts.lib.ada_identity import ada_isrc_expr, ada_native_code_expr, ada_native_code_type_expr, ada_source_expr

from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

try:
    from lib.catalog_report_filter import apply_report_net_personalization, filter_reportable_generation
    from lib.store_taxonomy import build_normalized_store_summary
    from lib.text_search import contains_search_expr, normalize_search_text
except ModuleNotFoundError:
    from scripts.lib.catalog_report_filter import apply_report_net_personalization, filter_reportable_generation
    from scripts.lib.store_taxonomy import build_normalized_store_summary
    from scripts.lib.text_search import contains_search_expr, normalize_search_text


BASE = Path(r"C:\royalties_pipeline")
MARTS = BASE / "warehouse" / "marts"
REPORTS = BASE / "reports"

SONG_PATH = MARTS / "song_level_all_sources.parquet"
STANDARDIZED_PATH = MARTS / "standardized_raw_all_sources.parquet"


SEARCH_COLUMNS_SONG = [
    "_income_origin_search",
    "asset_isrc",
    "track_statement_style",
    "asset_title_statement",
    "release_statement_style",
    "artist_statement_style",
    "asset_artist_statement",
    "source",
    "account",
    "content_type",
    "source_sheet",
    "revenue_basis",
]

SEARCH_COLUMNS_STANDARDIZED = [
    "_income_origin_search",
    "asset_isrc",
    "ISRC",
    "Track Title",
    "Title",
    "Video Title",
    "Asset Title",
    "Product Title",
    "track_statement_style",
    "asset_title_statement",
    "release_statement_style",
    "artist_statement_style",
    "asset_artist_statement",
    "Track Artists",
    "Artist Name",
    "Channel Name",
    "Product Artist",
    "TRACK ARTIST",
    "TRACK",
    "artists_raw",
    "Composers",
    "composers",
    "Payee",
    "payee",
    "source",
    "account",
    "store_name",
    "Store",
    "DSP",
    "territory",
    "Territory",
    "SALE COUNTRY",
    "Region",
    "Sales Region",
]


TERRITORY_CANDIDATES = [
    "territory",
    "Territory",
    "SALE COUNTRY",
    "Region",
    "Sales Region",
]


CODE_CANDIDATES = [
    ("asset_isrc", "ISRC"),
    ("ISRC", "ISRC"),
    ("Asset ISRC", "ISRC"),
    ("track_id", "Track ID"),
    ("Track ID", "Track ID"),
    ("Label Track ID", "Label Track ID"),
    ("label_track_id", "Label Track ID"),
    ("Asset Reference", "Asset Reference"),
    ("asset_reference", "Asset Reference"),
    ("FUGA Asset ID", "FUGA Asset ID"),
    ("Video ID", "Video ID"),
    ("VideoId", "Video ID"),
    ("video_id", "Video ID"),
    ("YOUTUBE VIDEO ID", "Video ID"),
    ("Product Reference", "Product Reference"),
    ("product_reference", "Product Reference"),
    ("DSP Unit ID", "DSP Unit ID"),
    ("DSP Container ID", "DSP Container ID"),
    ("ID", "ID"),
    ("Sale ID", "Sale ID"),
    ("sale_id", "Sale ID"),
]


HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)
TOTAL_FILL = PatternFill(start_color="BDD7EE", end_color="BDD7EE", fill_type="solid")
TOTAL_FONT = Font(bold=True)
CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")

DISPLAY_HEADERS = {
    "distributor": "Distribuidora",
    "keywords": "Filtro",
    "mode": "Coincidencia",
    "period_basis": "Criterio periodo",
    "start_month": "Desde",
    "end_month": "Hasta",
    "excluded_isrcs": "ISRC excluidos",
    "song_level_rows": "Filas resultado",
    "song_level_amount_usd": "Ingresos USD",
    "song_level_units": "Unidades",
    "raw_sample_rows": "Filas raw",
    "generated_at": "Generado el",
    "source": "Fuente",
    "account": "Cuenta",
    "transaction_month": "Mes",
    "period_month": "Mes",
    "amount_usd": "Ingresos USD",
    "units": "Unidades",
    "rows": "Filas",
    "report_territory": "Territorio",
    "report_code": "Codigo",
    "report_code_source": "Tipo codigo",
    "original_codes": "Codigos originales",
    "content_types": "Tipo de contenido",
    "asset_isrc": "ISRC",
    "track_statement_style": "Tema",
    "asset_title_statement": "Asset title",
    "artist_statement_style": "Artista",
    "asset_artist_statement": "Asset artist",
    "content_type": "Tipo de contenido",
    "store_raw": "Store original",
    "dsp_normalized": "DSP / Store",
    "monetization_normalized": "Monetizacion",
    "content_origin_normalized": "Origen",
    "classification_status": "Clasificacion",
    "usage_type": "Tipo",
    "first_month": "Desde",
    "last_month": "Hasta",
    "source_sheet": "Hoja origen",
    "revenue_basis": "Base ingreso",
    "match_text": "Texto coincidente",
    "statement_period": "Periodo statement",
    "currency_original": "Moneda original",
    "fx_to_usd_rate": "FX USD",
    "store_name": "Tienda",
    "territory": "Territorio",
    "statement_file_name": "Archivo statement",
    "hoja": "Hoja",
    "contenido": "Contenido",
    "resultado": "Resultado",
}

PUBLIC_DETAIL_COLUMNS = [
    "statement_period",
    "transaction_month",
    "artist_statement_style",
    "track_statement_style",
    "report_code",
    "report_code_source",
    "asset_isrc",
    "report_territory",
    "dsp_normalized",
    "monetization_normalized",
    "content_origin_normalized",
    "classification_status",
    "store_raw",
    "usage_type",
    "amount_usd",
    "currency_original",
    "fx_to_usd_rate",
    "units",
    "territory",
    "statement_file_name",
    "match_text",
    "source",
    "account",
]

STATEMENT_DETAIL_METADATA_COLUMNS = [
    "catalog_key",
    "catalog_business_status",
]

DERIVED_DETAIL_COLUMNS = {
    "match_text",
    "store",
    "store_raw",
    "usage_type",
    "usage_raw",
    "report_code",
    "report_code_source",
    "report_territory",
    "catalog_key",
    "catalog_business_status",
}

PRIVATE_REPORT_AMOUNT_COLUMNS = {
    "gross_amount",
    "gross_amount_usd",
    "net_amount",
    "net_amount_usd",
    "policy_report_net_adjustment_pct",
}

PERIOD_BASIS_LABELS = {
    "transaction_month": "Performance / mes de consumo",
    "statement_period": "Liquidacion / mes de statement",
}

DETAIL_MODE_LIMITED = "limited"
DETAIL_MODE_TOP_COUNTRIES = "top_countries"
DETAIL_MODE_FULL = "full"
DETAIL_MODES = {
    DETAIL_MODE_LIMITED,
    DETAIL_MODE_TOP_COUNTRIES,
    DETAIL_MODE_FULL,
}
EXCEL_MAX_DATA_ROWS = 1_048_575
TOP_COUNTRY_LIMIT = 5
COUNTRY_DISPLAY_NAMES = {
    "AR": "Argentina",
    "BR": "Brasil",
    "CL": "Chile",
    "CO": "Colombia",
    "DE": "Alemania",
    "ES": "España",
    "FR": "Francia",
    "GB": "Reino Unido",
    "IT": "Italia",
    "MX": "México",
    "PE": "Perú",
    "US": "Estados Unidos",
    "UY": "Uruguay",
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
        help="Maximo de filas en la hoja detalle.",
    )
    parser.add_argument(
        "--start-month",
        help="Mes inicial YYYY-MM. Filtra por transaction_month.",
    )
    parser.add_argument(
        "--end-month",
        help="Mes final YYYY-MM.",
    )
    parser.add_argument(
        "--period-basis",
        choices=["transaction_month", "statement_period"],
        default="transaction_month",
        help="transaction_month = performance; statement_period = liquidacion.",
    )
    parser.add_argument(
        "--exclude-isrc",
        action="append",
        default=[],
        help="ISRC a excluir del reporte. Se puede repetir o pasar separados por coma/semicolon.",
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
    return set(scan_income(path).collect_schema().names())


def filter_report_keyword_values(frame: pl.DataFrame,keywords: list[str],mode: str) -> pl.DataFrame:
    """Apply the existing search to distinct values, avoiding repeated text normalization."""
    if not keywords or frame.is_empty():return frame
    columns=set(frame.columns)
    ordinary=[name for name in SEARCH_COLUMNS_STANDARDIZED if name in columns]
    scoped=[name for name in ['catalog_number','gpid','Catalog Number','Catalogue Number','GPID'] if name in columns]
    ada=frame.select(ada_source_expr(columns).fill_null(False)).to_series() if scoped else None
    cache={}
    result=None
    for keyword in keywords:
        mask=pl.Series('_match',[False]*frame.height,dtype=pl.Boolean)
        for name in [*ordinary,*scoped]:
            if name not in cache:
                values=frame[name].cast(pl.String,strict=False).fill_null('')
                cache[name]=(values,values.unique().to_frame('_value'))
            values,unique=cache[name]
            matches=unique.filter(pl.any_horizontal([contains_search_expr(pl.col('_value'),term) for term in search_terms(keyword)]))['_value']
            if matches.is_empty():continue
            found=values.is_in(matches.implode())
            if name in scoped and name not in ordinary:found=found & ada
            mask=mask | found
            if mask.all():break
        result=mask if result is None else (result & mask if mode=='all' else result | mask)
        if mode=='all' and not result.any():return frame.head(0)
        if mode!='all' and result.all():return frame
    return frame.filter(result)


def prepare_keyword_source(source: Path, output: Path, keywords: list[str], mode: str, *, batch_size: int = 65536) -> Path:
    """Materialize a bounded, already allocated selection for the report job only."""
    import pyarrow.parquet as pq
    from lib.product_income import current_index,allocate_income,MEASURES
    index=current_index(source)
    signature=(source.stat().st_size,source.stat().st_mtime_ns)
    schema=dict(pl.scan_parquet(source).collect_schema())
    if index is not None:
        for name in MEASURES:
            if name in schema and schema[name].is_numeric():schema[name]=pl.Float64
        schema.update({'asset_isrc':pl.String,'track_statement_style':pl.String,'artist_statement_style':pl.String,
            '_income_key':pl.String,'_income_reference_upc':pl.String,'_income_position':pl.Int64,'_income_tracks':pl.Int64,
            '_income_product_pending':pl.Boolean,'_income_upc_pending':pl.Boolean,
            '_income_origin_search':pl.String,'_income_original_isrc':pl.String})
    schema['_income_allocated']=pl.Boolean
    output.parent.mkdir(parents=True,exist_ok=True)
    paths=[output.with_name(output.stem+'.native.parquet'),output.with_name(output.stem+'.products.parquet')]
    writers=[None,None]
    try:
        for batch in pq.ParquetFile(source).iter_batches(batch_size=batch_size,use_threads=False):
            original=pl.from_arrow(batch)
            frame=allocate_income(original.lazy(),index).collect(engine='streaming') if index is not None else original
            missing=[pl.lit(None,dtype=dtype).alias(name) for name,dtype in schema.items() if name not in frame.columns]
            frame=frame.with_columns(missing).select(list(schema))
            # Contract-only searches must not materialize the entire catalogue first.
            from app.royalty_reports.contract_filter import CURRENT,filter_income
            if CURRENT.get() is not None:
                from lib.catalog_report_filter import with_catalog_report_status
                frame=filter_income(with_catalog_report_status(frame.lazy())).select(list(schema)).collect(engine='streaming')
            frame=filter_report_keyword_values(frame,keywords,mode).cast(schema,strict=False)
            candidate=pl.col('_income_allocated').is_not_null()
            for part,condition in enumerate([~candidate,candidate]):
                selected=frame.filter(condition)
                if selected.is_empty():continue
                table=selected.to_arrow()
                if writers[part] is None:writers[part]=pq.ParquetWriter(paths[part],table.schema,compression='zstd')
                writers[part].write_table(table)
    finally:
        for writer in writers:
            if writer is not None:writer.close()
    if signature!=(source.stat().st_size,source.stat().st_mtime_ns):
        raise ValueError('Cambió el histórico mientras se seleccionaban los ingresos del reporte.')
    # Preserve the logical view order: untouched native rows, then product rows.
    combined=None
    try:
        for path,writer in zip(paths,writers):
            if writer is None:continue
            for batch in pq.ParquetFile(path).iter_batches(batch_size=batch_size,use_threads=False):
                if combined is None:combined=pq.ParquetWriter(output,batch.schema,compression='zstd')
                combined.write_batch(batch)
    finally:
        if combined is not None:combined.close()
    if combined is None:pl.DataFrame(schema=schema).write_parquet(output)
    return output


def normalize_isrcs(raw_isrcs: list[str] | None) -> list[str]:
    if not raw_isrcs:
        return []

    isrcs = []
    for item in raw_isrcs:
        parts = [part.strip().upper() for part in re.split(r"[;,\s]+", item) if part.strip()]
        isrcs.extend(parts)

    return sorted(set(isrcs))


def exclude_isrc_expr(columns: set[str], excluded_isrcs: list[str]) -> pl.Expr:
    if not excluded_isrcs:
        return pl.lit(True)

    exprs = []
    for col in ["asset_isrc", "ISRC"]:
        if col in columns:
            exprs.append(
                pl.col(col)
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_uppercase()
                .is_in(excluded_isrcs)
                .fill_null(False)
            )

    if not exprs:
        return pl.lit(True)

    excluded = exprs[0]
    for expr in exprs[1:]:
        excluded = excluded | expr

    return ~excluded


def contains_expr(columns: set[str], search_columns: list[str], keyword: str) -> pl.Expr:
    exprs = []
    normalized_keyword = normalize_search_text(keyword)
    for col in search_columns:
        if col in columns:
            match = pl.any_horizontal([contains_search_expr(pl.col(col), term) for term in search_terms(normalized_keyword)])
            exprs.append(match.fill_null(False))
    for col in ["catalog_number", "gpid", "Catalog Number", "Catalogue Number", "GPID"]:
        if col in columns:
            exprs.append((ada_source_expr(columns) & contains_search_expr(pl.col(col), normalized_keyword)).fill_null(False))

    if not exprs:
        return pl.lit(False)

    result = exprs[0]
    for expr in exprs[1:]:
        result = result | expr

    return result


def build_filter(columns: set[str], search_columns: list[str], keywords: list[str], mode: str) -> pl.Expr:
    exprs = [contains_expr(columns, search_columns, keyword) for keyword in keywords]

    if not exprs:
        return pl.lit(True)

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


def non_empty_code_expr(col_name: str) -> pl.Expr:
    value = pl.col(col_name).cast(pl.Utf8, strict=False).str.strip_chars()
    return pl.when(value.is_not_null() & (value != "")).then(value).otherwise(None)


def report_code_expr(columns: set[str]) -> pl.Expr:
    candidates = [non_empty_code_expr(col) for col, _label in CODE_CANDIDATES if col in columns]

    if not candidates:
        return pl.lit(None).cast(pl.Utf8)

    return pl.coalesce(candidates)


def report_code_source_expr(columns: set[str]) -> pl.Expr:
    expr = pl.lit(None).cast(pl.Utf8)

    for col, label in reversed([(col, label) for col, label in CODE_CANDIDATES if col in columns]):
        value = pl.col(col).cast(pl.Utf8, strict=False).str.strip_chars()
        expr = pl.when(value.is_not_null() & (value != "")).then(pl.lit(label)).otherwise(expr)

    return expr


def add_report_code(lf: pl.LazyFrame, columns: set[str]) -> pl.LazyFrame:
    ada_product = ada_source_expr(columns).fill_null(False) & ada_isrc_expr(columns).is_null()
    return lf.with_columns([
        pl.when(ada_product).then(ada_native_code_expr(columns)).otherwise(report_code_expr(columns)).alias("report_code"),
        pl.when(ada_product).then(ada_native_code_type_expr(columns)).otherwise(report_code_source_expr(columns)).alias("report_code_source"),
        report_territory_expr(columns).alias("report_territory"),
    ])


def _summary_text_expr(columns: set[str], names: list[str]) -> pl.Expr:
    candidates = []
    for name in names:
        if name not in columns:
            continue
        value = pl.col(name).cast(pl.Utf8, strict=False).str.strip_chars()
        candidates.append(pl.when(value.is_not_null() & (value != "")).then(value).otherwise(None))
    if not candidates:
        return pl.lit(None).cast(pl.Utf8)
    return pl.coalesce(candidates)


def report_identity_expr(columns: set[str]) -> pl.Expr:
    title = _summary_text_expr(columns, ["track_statement_style", "asset_title_statement"])
    raw_artist = _summary_text_expr(columns, ["artist_statement_style", "asset_artist_statement"])
    artist = (
        pl.when(
            raw_artist.fill_null("").str.to_lowercase().str.replace_all(r"\s+", " ").str.strip_chars()
            == title.fill_null("").str.to_lowercase().str.replace_all(r"\s+", " ").str.strip_chars()
        )
        .then(None)
        .otherwise(raw_artist)
    )
    catalog_key = _summary_text_expr(columns, ["catalog_key"])
    asset_isrc = _summary_text_expr(columns, ["asset_isrc"])
    report_code = _summary_text_expr(columns, ["report_code"])
    report_code_source = _summary_text_expr(columns, ["report_code_source"])

    normalized_title = (
        title.fill_null("").str.to_lowercase().str.replace_all(r"\s+", " ").str.strip_chars()
    )
    normalized_artist = (
        artist.fill_null("").str.to_lowercase().str.replace_all(r"\s+", " ").str.strip_chars()
    )
    fallback_identity = (
        pl.when(asset_isrc.is_not_null())
        .then(pl.concat_str([pl.lit("ISRC:"), asset_isrc.str.to_uppercase()]))
        .when(report_code.is_not_null())
        .then(pl.concat_str([
            pl.lit("CODE:"),
            report_code_source.fill_null("unknown"),
            pl.lit(":"),
            report_code,
        ]))
        .otherwise(pl.concat_str([
            pl.lit("TEXT:"),
            normalized_title,
            pl.lit("|"),
            normalized_artist,
        ]))
    )
    summary_video = (
        pl.concat_str([pl.lit("VIDEO:"), pl.col(SUMMARY_VIDEO)])
        if SUMMARY_VIDEO in columns else pl.lit(None, dtype=pl.String)
    )
    return pl.coalesce([summary_video, separate_channel_video_expr(columns), catalog_key, fallback_identity]).alias("_report_identity")


DASHGO_GROUP_TITLE = "Agrupación por ingresos menores a 10 centavos"
DASHGO_GROUP_ARTIST = "Intérpretes agrupados"


def dashgo_summary_metadata(columns: set[str]) -> list[pl.Expr]:
    dashgo = _summary_text_expr(columns, ["source"]).fill_null("") == "dashgo"
    return [dashgo.all().alias("_dashgo_only")]


def present_dashgo_summary(table: pd.DataFrame, summary: pl.DataFrame) -> pd.DataFrame:
    """Apply the existing small-income presentation rule without inferring identities."""
    if not summary["_dashgo_only"].any():
        return table
    result = table.copy()
    attrs = dict(table.attrs)
    contract_amounts = [
        table.columns[position - 1]
        for position, fmt in attrs.get("contract_formats", {}).items()
        if fmt != "0.00%"
    ]
    measures = ["Ingresos USD", "Unidades", *contract_amounts]
    eligible = pd.Series(summary["_dashgo_only"].to_list(), index=table.index)

    def combine(indices, labels):
        selected = result.loc[indices]
        row = {column: None for column in table.columns}
        for column in measures:
            row[column] = selected[column].sum(min_count=1)
        for column, aggregate in (("Desde", min), ("Hasta", max)):
            dates = selected[column].dropna().tolist()
            row[column] = aggregate(dates) if dates else None
        row.update(labels)
        return pd.DataFrame([row], columns=table.columns)

    small = result.index[
        eligible.reindex(result.index, fill_value=False)
        & result["Ingresos USD"].between(0, 0.10, inclusive="left")
        & result["Unidades"].between(0, 100, inclusive="left")
    ]
    if len(small):
        row = combine(small, {"Tema": DASHGO_GROUP_TITLE, "Artista": DASHGO_GROUP_ARTIST})
        result = pd.concat([result.drop(small), row], ignore_index=True)
    result.attrs = attrs
    return result


def build_track_summary_lf(base_lf: pl.LazyFrame, *, include_identity: bool = False, include_dashgo_metadata: bool = False) -> pl.LazyFrame:
    """Build one economic row per resolved catalog identity."""
    columns = set(base_lf.collect_schema().names())
    title = _summary_text_expr(columns, ["track_statement_style", "asset_title_statement"])
    raw_artist = _summary_text_expr(columns, ["artist_statement_style", "asset_artist_statement"])
    artist = pl.when(
        raw_artist.fill_null("").str.to_lowercase().str.replace_all(r"\s+", " ").str.strip_chars()
        == title.fill_null("").str.to_lowercase().str.replace_all(r"\s+", " ").str.strip_chars()
    ).then(None).otherwise(raw_artist)
    report_code = _summary_text_expr(columns, ["report_code"])
    report_code_source = _summary_text_expr(columns, ["report_code_source"])
    trusted_code = (
        pl.when(
            report_code.is_not_null()
            & ~report_code_source.fill_null("").is_in(["Sale ID", "ID"])
        )
        .then(report_code)
        .otherwise(None)
    )
    channel_video = (
        (_summary_text_expr(columns, ["dsp_normalized"]) == "YouTube")
        & (_summary_text_expr(columns, ["content_origin_normalized"]) == "Video / Channel")
    ).fill_null(False)
    best_title = pl.col("_summary_title").sort_by(pl.col("amount_usd").abs(), descending=True).drop_nulls().first()
    if SUMMARY_TITLE in columns:
        best_title = pl.coalesce([pl.col(SUMMARY_TITLE).drop_nulls().first(), best_title])

    grouped = (
        base_lf
        .with_columns([
            report_identity_expr(columns),
            title.alias("_summary_title"),
            artist.alias("_summary_artist"),
            trusted_code.alias("_trusted_original_code"),
            report_code_source.alias("_summary_code_source"),
            _summary_text_expr(columns, ["content_type"]).alias("_summary_content_type"),
            channel_video.alias("_summary_channel_video"),
        ])
        .group_by("_report_identity")
        .agg([
            *(dashgo_summary_metadata(columns) if include_dashgo_metadata else []),
            pl.col("_summary_channel_video").all().alias("_all_channel_video"),
            best_title.alias("track_statement_style"),
            pl.col("_summary_artist")
            .sort_by(pl.col("amount_usd").abs(), descending=True)
            .drop_nulls()
            .first()
            .alias("artist_statement_style"),
            pl.col("_trusted_original_code")
            .drop_nulls()
            .unique()
            .sort()
            .str.join(" | ")
            .alias("original_codes"),
            pl.col("_summary_content_type")
            .drop_nulls()
            .unique()
            .sort()
            .str.join(" | ")
            .alias("content_types"),
            pl.col("_trusted_original_code")
            .sort_by(pl.col("amount_usd").abs(), descending=True)
            .drop_nulls()
            .first()
            .alias("_best_original_code"),
            pl.col("_summary_code_source")
            .sort_by(pl.col("amount_usd").abs(), descending=True)
            .drop_nulls()
            .first()
            .alias("_best_code_source"),
            pl.sum("amount_usd").alias("amount_usd"),
            pl.sum("units").alias("units"),
            pl.min("period_month").alias("first_month"),
            pl.max("period_month").alias("last_month"),
        ])
        .with_columns([
            pl.when(pl.col("_all_channel_video"))
            .then(
                pl.when(pl.col("content_types").fill_null("") == "")
                .then(pl.lit(YOUTUBE_CHANNEL_LABEL))
                .otherwise(pl.concat_str([
                    pl.lit(YOUTUBE_CHANNEL_LABEL), pl.col("content_types")
                ], separator=" | "))
            )
            .otherwise(pl.col("content_types"))
            .alias("content_types"),
            pl.when(pl.col("_report_identity").str.starts_with("ISRC:"))
            .then(pl.col("_report_identity").str.replace(r"^ISRC:", ""))
            .when(pl.col("_report_identity").str.starts_with("VIDEO:"))
            .then(pl.col("_report_identity").str.replace(r"^VIDEO:", ""))
            .when(pl.col("_report_identity").str.starts_with("UPC:"))
            .then(pl.col("_report_identity").str.replace(r"^UPC:", ""))
            .otherwise(pl.col("_best_original_code"))
            .alias("report_code"),
            pl.when(pl.col("_report_identity").str.starts_with("ISRC:"))
            .then(pl.lit("ISRC"))
            .when(pl.col("_report_identity").str.starts_with("VIDEO:"))
            .then(pl.lit("Video ID"))
            .when(pl.col("_report_identity").str.starts_with("UPC:"))
            .then(pl.lit("UPC"))
            .otherwise(pl.col("_best_code_source"))
            .alias("report_code_source"),
            pl.col("track_statement_style")
            .fill_null("")
            .str.to_lowercase()
            .alias("_sort_tema"),
            pl.col("track_statement_style")
            .fill_null("")
            .str.strip_chars()
            .eq("")
            .cast(pl.Int8)
            .alias("_sort_tema_empty"),
        ])
        .sort([
            "_sort_tema_empty",
            "_sort_tema",
            "track_statement_style",
            "artist_statement_style",
            "report_code",
        ])
        .select([
            *(["_report_identity"] if include_identity else []),
            *(["_dashgo_only"] if include_dashgo_metadata else []),
            "track_statement_style",
            "artist_statement_style",
            "report_code",
            "report_code_source",
            "original_codes",
            "content_types",
            "amount_usd",
            "units",
            "first_month",
            "last_month",
        ])
    )
    return grouped


def report_territory_expr(columns: set[str]) -> pl.Expr:
    candidates = []
    for col in TERRITORY_CANDIDATES:
        if col in columns:
            value = pl.col(col).cast(pl.Utf8, strict=False).str.strip_chars()
            candidates.append(pl.when(value.is_not_null() & (value != "")).then(value).otherwise(None))

    if not candidates:
        return pl.lit(None).cast(pl.Utf8)

    return pl.coalesce(candidates)


def add_report_territory(lf: pl.LazyFrame, columns: set[str]) -> pl.LazyFrame:
    return lf.with_columns(report_territory_expr(columns).alias("report_territory"))


def normalize_report_territory_expr() -> pl.Expr:
    value = pl.col("report_territory").cast(pl.Utf8, strict=False).str.strip_chars()
    return (
        pl.when(value.is_null() | (value == ""))
        .then(pl.lit("Sin territorio"))
        .otherwise(value)
    )


def report_units_expr(columns: set[str]) -> pl.Expr:
    candidates = []
    for col in [
        "units",
        "streams",
        "asset_quantity_num",
        "Asset Quantity",
        "product_quantity_num",
        "Product Quantity",
        "Quantity",
        "QUANTITY",
        "Units of Sold",
    ]:
        if col in columns:
            candidates.append(pl.col(col).cast(pl.Float64, strict=False))

    if not candidates:
        return pl.lit(None).cast(pl.Float64)

    return pl.coalesce(candidates)


def normalize_report_units(lf: pl.LazyFrame, columns: set[str]) -> pl.LazyFrame:
    return preserve_video_context(lf)


def store_raw_expr(columns: set[str]) -> pl.Expr:
    candidates = []
    for col in [
        "store_name",
        "Store",
        "DSP",
        "Sale Store Name",
        "STORE",
        "service_detail",
        "SERVICE DETAIL",
        "Store Name",
    ]:
        if col in columns:
            candidates.append(pl.col(col).cast(pl.Utf8, strict=False).str.strip_chars())

    if not candidates:
        return pl.lit(None).cast(pl.Utf8)

    return pl.coalesce(candidates)


def normalize_store_expr(raw_store: pl.Expr) -> pl.Expr:
    value = raw_store.fill_null("").str.to_lowercase()

    return (
        pl.when(value.str.contains("spotify", literal=True))
        .then(pl.lit("spotify"))
        .when(value.str.contains("youtube", literal=True) | value.str.contains("yt ", literal=True))
        .then(
            pl.when(
                value.str.contains("art track", literal=True)
                | value.str.contains("youtube music", literal=True)
                | value.str.contains("yt audio", literal=True)
            )
            .then(pl.lit("youtube_music"))
            .otherwise(pl.lit("youtube_video"))
        )
        .when(value.str.contains("tiktok", literal=True))
        .then(pl.lit("tiktok"))
        .when(value.str.contains("apple", literal=True) | value.str.contains("itunes", literal=True))
        .then(pl.lit("apple_music"))
        .when(value.str.contains("amazon", literal=True))
        .then(pl.lit("amazon"))
        .when(value.str.contains("facebook", literal=True) | value.str.contains("instagram", literal=True))
        .then(pl.lit("meta"))
        .when(value.str.contains("deezer", literal=True))
        .then(pl.lit("deezer"))
        .when(value.str.contains("pandora", literal=True))
        .then(pl.lit("pandora"))
        .when(value.str.contains("tidal", literal=True))
        .then(pl.lit("tidal"))
        .when(value.str.contains("audiomack", literal=True))
        .then(pl.lit("audiomack"))
        .when(value.str.contains("qobuz", literal=True))
        .then(pl.lit("qobuz"))
        .when(value.str.contains("soundcloud", literal=True))
        .then(pl.lit("soundcloud"))
        .when(raw_store.is_null() | (raw_store == ""))
        .then(pl.lit("unknown"))
        .otherwise(value.str.replace_all(r"[^a-z0-9]+", "_").str.strip_chars("_"))
    )


def normalize_report_store(lf: pl.LazyFrame, columns: set[str]) -> pl.LazyFrame:
    raw_store = store_raw_expr(columns)
    normalized_store = (
        pl.col("dsp_normalized").cast(pl.Utf8, strict=False).str.strip_chars()
        if "dsp_normalized" in columns
        else normalize_store_expr(raw_store)
    )
    return lf.with_columns([
        raw_store.alias("store_raw"),
        normalized_store.alias("store"),
    ])


def usage_raw_expr(columns: set[str]) -> pl.Expr:
    candidates = []
    for col in [
        "Sale Type",
        "sale_type",
        "Sales Type",
        "Use Type",
        "use_type",
        "Product Type",
        "product_type",
        "ROYALTY TYPE",
        "Royalty Type",
        "royalty_type",
        "TRANSACTION TYPE",
        "TRANSACTION SUBTYPE",
        "SERVICE DETAIL",
        "service_detail",
        "source_sheet",
    ]:
        if col in columns:
            candidates.append(pl.col(col).cast(pl.Utf8, strict=False).str.strip_chars())

    if not candidates:
        return pl.lit(None).cast(pl.Utf8)

    return pl.coalesce(candidates)


def normalize_usage_expr(raw_usage: pl.Expr, raw_store: pl.Expr, source_sheet: pl.Expr) -> pl.Expr:
    value = pl.concat_str([
        raw_usage.fill_null(""),
        raw_store.fill_null(""),
        source_sheet.fill_null(""),
    ], separator=" | ").str.to_lowercase()
    store_value = raw_store.fill_null("").str.to_lowercase()
    usage_value = raw_usage.fill_null("").str.to_lowercase()
    sheet_value = source_sheet.fill_null("").str.to_lowercase()

    return (
        pl.when(value.str.contains("short", literal=True))
        .then(pl.lit("short_video"))
        .when(value.str.contains("download", literal=True))
        .then(pl.lit("download"))
        .when(
            store_value.str.contains("youtube premium", literal=True)
            & usage_value.str.contains("stream", literal=True)
            & sheet_value.is_in(["masters", "shares in & out"])
        )
        .then(pl.lit("youtube_premium_stream"))
        .when(
            store_value.str.contains("youtube", literal=True)
            & usage_value.str.contains("stream", literal=True)
            & sheet_value.is_in(["masters", "shares in & out"])
        )
        .then(pl.lit("youtube_master_stream"))
        .when(
            value.str.contains("ugc", literal=True)
            | value.str.contains("content id", literal=True)
            | value.str.contains("channel income", literal=True)
        )
        .then(pl.lit("video_ugc"))
        .when(
            value.str.contains("video", literal=True)
            | value.str.contains("youtube", literal=True)
            | value.str.contains("vevo", literal=True)
        )
        .then(pl.lit("video_stream"))
        .when(value.str.contains("stream", literal=True))
        .then(pl.lit("audio_stream"))
        .when(value.str.contains("tiktok", literal=True))
        .then(pl.lit("short_video"))
        .when(raw_usage.is_null() | (raw_usage == ""))
        .then(pl.lit("unknown"))
        .otherwise(value.str.replace_all(r"[^a-z0-9]+", "_").str.strip_chars("_"))
    )


def normalize_report_usage(lf: pl.LazyFrame, columns: set[str]) -> pl.LazyFrame:
    raw_usage = usage_raw_expr(columns)
    raw_store = store_raw_expr(columns)
    source_sheet = (
        pl.col("source_sheet").cast(pl.Utf8, strict=False).str.strip_chars()
        if "source_sheet" in columns
        else pl.lit(None).cast(pl.Utf8)
    )
    normalized_usage = (
        pl.col("content_origin_normalized").cast(pl.Utf8, strict=False).str.strip_chars()
        if "content_origin_normalized" in columns
        else normalize_usage_expr(raw_usage, raw_store, source_sheet)
    )
    return lf.with_columns([
        raw_usage.alias("usage_raw"),
        normalized_usage.alias("usage_type"),
    ])


def display_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    from app.royalty_scope import is_wml
    result = dataframe.copy()
    if not is_wml():
        for column in ("artist_statement_style", "asset_artist_statement", "artist", "artist_statement", "catalog_artist_statement"):
            if column in result.columns:
                result[column] = result[column].map(display_credit)
    return result.rename(columns={col: DISPLAY_HEADERS.get(col, col) for col in result.columns})


def public_detail_columns(
    source_columns: set[str],
    *,
    include_statement_metadata: bool = False,
) -> list[str]:
    wanted = list(PUBLIC_DETAIL_COLUMNS)
    if include_statement_metadata:
        wanted.extend(STATEMENT_DETAIL_METADATA_COLUMNS)
    selected = [
        column
        for column in wanted
        if column in source_columns or column in DERIVED_DETAIL_COLUMNS
    ]
    exposed_private = PRIVATE_REPORT_AMOUNT_COLUMNS.intersection(selected)
    if exposed_private:
        raise RuntimeError(
            "El detalle publico intenta exponer importes internos: "
            + ", ".join(sorted(exposed_private))
        )
    return selected


def prepare_sheet(ws):
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    if ws.title == "resumen por tema" and ws.cell(ws.max_row, 1).value == DASHGO_GROUP_TITLE:
        ws.row_dimensions[ws.max_row].height = 32
        for column in (1, 2):
            ws.cell(ws.max_row, column).alignment = Alignment(wrap_text=True, vertical="center")

    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER

    amount_headers = {
        "amount_usd",
        "song_level_amount_usd",
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
        "Filas representadas",
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
            if ws.title == "resumen por tema" and cell.column == 2 and cell.value == DASHGO_GROUP_ARTIST:
                max_len = max(max_len, len("Intérpretes"))
            elif cell.value is not None:
                max_len = max(max_len, len(str(cell.value)))

        ws.column_dimensions[col_letter].width = min(max_len + 2, 50)


def add_period_filter(
    lf: pl.LazyFrame,
    columns: set[str],
    start_month: str | None,
    end_month: str | None,
    period_column: str,
) -> pl.LazyFrame:
    if period_column not in columns:
        return lf

    if start_month:
        lf = lf.filter(pl.col(period_column).cast(pl.Utf8) >= start_month)

    if end_month:
        lf = lf.filter(pl.col(period_column).cast(pl.Utf8) <= end_month)

    return lf


def add_source_account_filter(
    lf: pl.LazyFrame,
    columns: set[str],
    source: str | None,
    account: str | None,
) -> pl.LazyFrame:
    source_value = (source or "").strip().lower()
    account_value = (account or "").strip().lower()
    if source_value and "source" in columns:
        lf = lf.filter(
            pl.col("source").cast(pl.Utf8, strict=False).str.to_lowercase().str.strip_chars()
            == source_value
        )
    if account_value and "account" in columns:
        lf = lf.filter(
            pl.col("account").cast(pl.Utf8, strict=False).str.to_lowercase().str.strip_chars()
            == account_value
        )
    return lf


def build_filtered_raw_detail_lf(
    *,
    keywords: list[str],
    mode: str,
    start_month: str | None,
    end_month: str | None,
    period_basis: str,
    standardized_path: Path,
    exclude_isrcs: list[str] | None = None,
    source: str | None = None,
    account: str | None = None,
) -> tuple[pl.LazyFrame, set[str]]:
    columns = existing_columns(standardized_path)
    period_column = "statement_period" if period_basis == "statement_period" else "transaction_month"
    raw_filter = build_filter(columns, SEARCH_COLUMNS_STANDARDIZED, keywords, mode)
    excluded = normalize_isrcs(exclude_isrcs)
    detail = (
        add_report_code(
            normalize_report_usage(
                normalize_report_store(
                    normalize_report_units(
                        add_period_filter(
                            add_match_text(
                                add_source_account_filter(
                                    scan_income(standardized_path).filter(raw_filter).with_row_index('_report_detail_position'),
                                    columns,
                                    source,
                                    account,
                                ),
                                columns,
                                SEARCH_COLUMNS_STANDARDIZED,
                            ),
                            columns,
                            start_month,
                            end_month,
                            period_column,
                        ),
                        columns,
                    ),
                    columns,
                ),
                columns,
            ),
            columns,
        )
        .pipe(lambda frame: filter_reportable_generation(frame, columns))
        .pipe(lambda frame: apply_report_net_personalization(frame))
        .filter(exclude_isrc_expr(columns, excluded))
    )
    return detail, columns


def count_report_detail_rows(
    *,
    keywords: list[str],
    mode: str,
    start_month: str | None,
    end_month: str | None,
    period_basis: str,
    standardized_path: Path = STANDARDIZED_PATH,
    exclude_isrcs: list[str] | None = None,
    source: str | None = None,
    account: str | None = None,
) -> int:
    detail, _columns = build_filtered_raw_detail_lf(
        keywords=keywords,
        mode=mode,
        start_month=start_month,
        end_month=end_month,
        period_basis=period_basis,
        standardized_path=standardized_path,
        exclude_isrcs=exclude_isrcs,
        source=source,
        account=account,
    )
    result = detail.select(pl.len().alias("rows")).collect(engine="streaming")
    return int(result["rows"][0] or 0)


def _country_display_name(code: object) -> str:
    value = str(code or "Sin territorio").strip() or "Sin territorio"
    return COUNTRY_DISPLAY_NAMES.get(value.upper(), value)


def _aggregate_detail_row(
    detail_columns: list[str],
    *,
    keywords: list[str],
    country: str,
    territory: str,
    row_type: str,
    dsp: str,
    label: str,
    lines: int,
    amount_usd: float,
    units: float,
) -> dict[str, object]:
    row = {column: None for column in detail_columns}
    row.update(
        {
            "artist_statement_style": ", ".join(keywords),
            "track_statement_style": label,
            "report_territory": territory,
            "territory": territory,
            "dsp_normalized": dsp,
            "amount_usd": amount_usd,
            "units": units,
            "source": "varias",
            "account": "varias",
        }
    )
    return {
        "País consolidado": country,
        "Tipo de fila": row_type,
        **row,
        "Filas representadas": lines,
    }


def build_report_detail(
    raw_matches_lf: pl.LazyFrame,
    raw_columns: set[str],
    *,
    keywords: list[str],
    detail_mode: str,
    raw_limit: int,
    include_statement_metadata: bool = False,
) -> pd.DataFrame:
    if detail_mode not in DETAIL_MODES:
        raise ValueError(f"Modo de detalle no soportado: {detail_mode}.")

    detail_columns = public_detail_columns(
        raw_columns,
        include_statement_metadata=include_statement_metadata,
    )
    if detail_mode == DETAIL_MODE_LIMITED:
        if raw_limit <= 0:
            return pd.DataFrame()
        if '_report_detail_position' in raw_matches_lf.collect_schema().names():
            raw_matches_lf=raw_matches_lf.sort('_report_detail_position')
        return display_dataframe(
            raw_matches_lf.select(detail_columns).limit(raw_limit).collect(engine="streaming").to_pandas()
        )

    if detail_mode == DETAIL_MODE_FULL:
        row_count = int(
            raw_matches_lf.select(pl.len().alias("rows")).collect(engine="streaming")["rows"][0]
            or 0
        )
        if row_count > EXCEL_MAX_DATA_ROWS:
            raise ValueError(
                "No se puede generar el detalle completo. "
                f"El resultado contiene {row_count:,} filas y supera el máximo permitido "
                f"por Excel de {EXCEL_MAX_DATA_ROWS:,}. Reducí el período o aplicá más filtros."
            )
        return display_dataframe(
            raw_matches_lf.select(detail_columns).collect(engine="streaming").to_pandas()
        )

    ranked_matches_lf = raw_matches_lf.with_columns(
        normalize_report_territory_expr().alias("report_territory")
    )
    top_countries = (
        ranked_matches_lf.group_by("report_territory")
        .agg(pl.sum("amount_usd").fill_null(0).alias("amount_usd"))
        .sort("amount_usd", descending=True)
        .limit(TOP_COUNTRY_LIMIT)
        .collect(engine="streaming")
    )
    top_codes = top_countries.get_column("report_territory").to_list()
    output_frames: list[pd.DataFrame] = []
    raw_schema = set(ranked_matches_lf.collect_schema().names())
    primary_store_column = "store" if "store" in raw_schema else "dsp_normalized"
    primary_dsp = (
        pl.col(primary_store_column)
        .fill_null("")
        .cast(pl.Utf8)
        .str.to_lowercase()
        .str.contains("spotify|youtube")
    )

    sort_columns = [
        column
        for column in [
            "report_territory",
            primary_store_column,
            "statement_period",
            "transaction_month",
            "amount_usd",
        ]
        if column in raw_schema
    ]
    primary_detail = (
        ranked_matches_lf.filter(
            pl.col("report_territory").is_in(top_codes) & primary_dsp
        )
        .sort(sort_columns, descending=[False] * (len(sort_columns) - 1) + [True])
        .select(detail_columns)
        .collect(engine="streaming")
    )
    aggregate_groups = (
        ranked_matches_lf.with_columns(
            pl.when(
                pl.col("report_territory").is_in(top_codes) & ~primary_dsp
            )
            .then(pl.col("report_territory"))
            .when(~pl.col("report_territory").is_in(top_codes))
            .then(pl.lit("__REST_OF_WORLD__"))
            .otherwise(None)
            .alias("_aggregate_group")
        )
        .filter(pl.col("_aggregate_group").is_not_null())
        .group_by("_aggregate_group")
        .agg(
            pl.len().alias("lines"),
            pl.sum("amount_usd").alias("amount_usd"),
            pl.sum("units").alias("units"),
        )
        .collect(engine="streaming")
    )
    aggregate_by_group = {
        str(row["_aggregate_group"]): row for row in aggregate_groups.to_dicts()
    }

    for code in top_codes:
        country = _country_display_name(code)
        primary_frame = primary_detail.filter(
            pl.col("report_territory") == code
        ).to_pandas()
        primary_frame.insert(0, "País consolidado", country)
        primary_frame.insert(1, "Tipo de fila", "Detalle Spotify/YouTube")
        primary_frame["Filas representadas"] = 1
        output_frames.append(primary_frame)

        other = aggregate_by_group.get(
            str(code),
            {"lines": 0, "amount_usd": 0, "units": 0},
        )
        if int(other["lines"] or 0) > 0:
            output_frames.append(
                pd.DataFrame(
                    [
                        _aggregate_detail_row(
                            detail_columns,
                            keywords=keywords,
                            country=country,
                            territory=str(code),
                            row_type="Consolidado país",
                            dsp="Resto de plataformas",
                            label=f"{country} - resto de plataformas",
                            lines=int(other["lines"]),
                            amount_usd=float(other["amount_usd"] or 0),
                            units=float(other["units"] or 0),
                        )
                    ]
                )
            )

    rest = aggregate_by_group.get(
        "__REST_OF_WORLD__",
        {"lines": 0, "amount_usd": 0, "units": 0},
    )
    if int(rest["lines"] or 0) > 0:
        output_frames.append(
            pd.DataFrame(
                [
                    _aggregate_detail_row(
                        detail_columns,
                        keywords=keywords,
                        country="Resto del mundo",
                        territory="Resto del mundo",
                        row_type="Consolidado global",
                        dsp="Todas las plataformas",
                        label="Resto del mundo",
                        lines=int(rest["lines"]),
                        amount_usd=float(rest["amount_usd"] or 0),
                        units=float(rest["units"] or 0),
                    )
                ]
            )
        )

    if not output_frames:
        return pd.DataFrame()
    detail = pd.concat(output_frames, ignore_index=True)
    if len(detail) > EXCEL_MAX_DATA_ROWS:
        raise ValueError(
            "No se puede generar el detalle priorizado. "
            f"El resultado contiene {len(detail):,} filas y supera el máximo permitido "
            f"por Excel de {EXCEL_MAX_DATA_ROWS:,}. Reducí el período o aplicá más filtros."
        )
    return display_dataframe(detail)


def style_workbook(writer):
    for ws in writer.book.worksheets:
        prepare_sheet(ws)
        if ws.title != "resumen por tema":
            continue
        headers = {cell.value: cell.column - 1 for cell in ws[1]}
        if not {"Codigo", "Tipo codigo"}.issubset(headers):
            continue
        for row in ws.iter_rows(min_row=2):
            cell = row[headers["Codigo"]]
            url = youtube_video_url(cell.value, row[headers["Tipo codigo"]].value)
            if url:
                cell.hyperlink = url
                font = copy(cell.font)
                font.color = "0563C1"
                font.underline = "single"
                cell.font = font


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


def add_wml_reference_annex(tables: dict, matched_isrcs: set[str]) -> dict:
    from app.royalty_scope import is_wml, MARTS
    if is_wml():
        references_path = MARTS.get().get('wml_isrc_references.parquet')
        if references_path is None:
            raise RuntimeError('Faltan las referencias WML fijadas para este reporte.')
        # A separate annex avoids multiplying economic rows by participants.
        references = pl.read_parquet(references_path).filter(pl.col('isrc').is_in(sorted(matched_isrcs)))
        rows = references.to_dicts()
        status_labels = {'informed':'Informado','deduced':'Deducido','hypothesis':'Hipótesis'}
        tables['referencias WML'] = pd.DataFrame([{
            'ISRC':r['isrc'],'Tipo':r['reference_type'],'Participante / contrato':r['participant'],
            'Porcentaje sobre base 100%':r['percent'],'Evidencia':status_labels.get(r['evidence_status'],r['evidence_status']),
            'Alcance':r['reference_scope'],'Tipo de uso':r['product_type'],
            'Statements observados':', '.join(r['statement_periods']),'Archivos':', '.join(r['source_files']),
            'Notas':r['notes'],'Aplicación automática':'No',
        } for r in rows])
        tables['resumen general']['Base del informe'] = 'WML 91230 · Base contractual al 100%; referencias informativas sin aplicación automática'

    return tables


def build_report_tables(
    keywords: list[str],
    mode: str,
    raw_limit: int,
    start_month: str | None = None,
    end_month: str | None = None,
    period_basis: str = "transaction_month",
    song_path: Path = SONG_PATH,
    standardized_path: Path = STANDARDIZED_PATH,
    exclude_isrcs: list[str] | None = None,
    source: str | None = None,
    account: str | None = None,
    detail_mode: str = DETAIL_MODE_LIMITED,
    contract_snapshot: dict | None = None,
    contract_columns: str = "all",
    _dashgo_video_groups: pl.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    if _dashgo_video_groups is None:
        from app.royalty_scope import is_wml
        evidence_path = standardized_path if standardized_path.exists() else song_path
        _dashgo_video_groups = (
            compile_video_groups(pl.scan_parquet(evidence_path))
            if not is_wml() and evidence_path.exists() else pl.DataFrame()
        )
    if (standardized_path.exists() and standardized_path.stat().st_size>128*1024*1024
            and '_income_allocated' not in pl.scan_parquet(standardized_path).collect_schema().names()):
        from lib.product_income import current_index,use_product_income
        with use_product_income(current_index(standardized_path)),tempfile.TemporaryDirectory(prefix='royalty-selection-') as temporary:
            selected=prepare_keyword_source(standardized_path,Path(temporary)/'selected_income.parquet',keywords,mode)
            return build_report_tables(keywords,mode,raw_limit,start_month,end_month,period_basis,song_path,selected,
                exclude_isrcs,source,account,detail_mode,contract_snapshot,contract_columns,
                _dashgo_video_groups=_dashgo_video_groups)
    period_column = "statement_period" if period_basis == "statement_period" else "transaction_month"
    period_label = PERIOD_BASIS_LABELS.get(period_column, period_column)
    excluded_isrcs = normalize_isrcs(exclude_isrcs)

    song_cols = existing_columns(song_path)
    song_filter = build_filter(song_cols, SEARCH_COLUMNS_SONG, keywords, mode)
    standardized_cols = existing_columns(standardized_path)

    if period_column == "statement_period":
        raw_filter = build_filter(standardized_cols, SEARCH_COLUMNS_STANDARDIZED, keywords, mode)

        statement_base_lf = (
            add_report_code(
                normalize_report_usage(
                    normalize_report_store(
                        normalize_report_units(
                            add_period_filter(
                                add_source_account_filter(
                                    scan_income(standardized_path).filter(raw_filter),
                                    standardized_cols,
                                    source,
                                    account,
                                ),
                                standardized_cols,
                                start_month,
                                end_month,
                                period_column,
                            ),
                            standardized_cols,
                        ),
                        standardized_cols,
                    ),
                    standardized_cols,
                ),
                standardized_cols,
            )
            .pipe(lambda frame: filter_reportable_generation(frame, standardized_cols))
            .pipe(lambda frame: apply_report_net_personalization(frame))
            .filter(exclude_isrc_expr(standardized_cols, excluded_isrcs))
            .select([
                col for col in [
                    "source",
                    "account",
                    "statement_period",
                    "transaction_month",
                    "report_code",
                    "report_code_source",
                    "asset_isrc",
                    "video_id",
                    "video_id_source",
                    "channel_id",
                    "Track Title",
                    "report_territory",
                    "track_statement_style",
                    "asset_title_statement",
                    "artist_statement_style",
                    "asset_artist_statement",
                    "content_type",
                    "dsp_normalized",
                    "monetization_normalized",
                    "content_origin_normalized",
                    "classification_status",
                    "store_raw",
                    "usage_type",
                    "amount_usd",
                    "units",
                    "territory",
                    "source_sheet",
                    "revenue_basis",
                    "catalog_key",
                    "catalog_business_status",
                    "product_upc", "UPC Code", "UPC", "Video ID", "VideoId", "track_id",
                    "Label Track ID", "Track ID", "gpid", "source_asset_id", "catalog_number",
                    '_income_product_pending','_income_upc_pending',
                ]
                if col in standardized_cols or col in {"store", "store_raw", "usage_type", "usage_raw", "report_code", "report_code_source", "report_territory", "catalog_key", "catalog_business_status", "video_id", "video_id_source", "channel_id", "dsp_normalized", "monetization_normalized", "content_origin_normalized", "classification_status"}
            ])
            .with_columns([
                pl.lit(None).cast(pl.Utf8).alias("content_type")
                if "content_type" not in standardized_cols
                else pl.col("content_type"),
                pl.col(period_column).cast(pl.Utf8).alias("period_month"),
            ])
        )

        # All summaries and optional contract columns consume one frozen selection.
        # Do not repeat the wide keyword/catalog/policy scan for every worksheet.
        statement_base_lf = statement_base_lf.collect(engine='streaming').lazy()
        summary_base_lf = with_video_groups(statement_base_lf, _dashgo_video_groups)
        metrics_lf = statement_base_lf.select([
            pl.len().alias("song_level_rows"),
            pl.sum("amount_usd").alias("song_level_amount_usd"),
            pl.sum("units").alias("song_level_units"),
        ])

        monthly_summary_lf = (
            statement_base_lf
            .group_by(["period_month"])
            .agg([
                pl.sum("amount_usd").alias("amount_usd"),
                pl.sum("units").alias("units"),
                pl.len().alias("rows"),
            ])
            .sort("period_month")
        )

        store_summary_lf = build_normalized_store_summary(
            statement_base_lf,
            set(statement_base_lf.collect_schema().names()),
        ).rename({"source": "distributor"})

        territory_summary_lf = (
            statement_base_lf
            .with_columns(
                normalize_report_territory_expr().alias("report_territory")
            )
            .group_by(["report_territory"])
            .agg([
                pl.sum("amount_usd").alias("amount_usd"),
                pl.sum("units").alias("units"),
            ])
            .sort("report_territory")
        )

        track_summary_lf = build_track_summary_lf(summary_base_lf, include_identity=contract_snapshot is not None, include_dashgo_metadata=True)

        raw_matches_lf, raw_detail_columns = build_filtered_raw_detail_lf(
            keywords=keywords,
            mode=mode,
            start_month=start_month,
            end_month=end_month,
            period_basis=period_basis,
            standardized_path=standardized_path,
            exclude_isrcs=excluded_isrcs,
            source=source,
            account=account,
        )

        metrics = metrics_lf.collect()
        song_rows = int(metrics["song_level_rows"][0])
        song_amount_usd = float(metrics["song_level_amount_usd"][0] or 0)
        song_units = float(metrics["song_level_units"][0] or 0)

        if song_rows == 0:
            print("No hubo matches en standardized_raw_all_sources.")
            return {
                "resumen general": display_dataframe(pd.DataFrame([{
                    "keywords": ", ".join(keywords),
                    "mode": mode,
                    "period_basis": period_label,
                    "start_month": start_month or "",
                    "end_month": end_month or "",
                    "excluded_isrcs": ", ".join(excluded_isrcs),
                    "song_level_rows": 0,
                    "song_level_amount_usd": 0,
                    "song_level_units": 0,
                    "raw_sample_rows": 0,
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                }])),
                "sin resultados": display_dataframe(pd.DataFrame([{
                    "resultado": "Sin coincidencias para los parametros ingresados."
                }])),
            }

        monthly_summary = monthly_summary_lf.collect()
        store_summary = store_summary_lf.collect()
        territory_summary = territory_summary_lf.collect()
        track_summary = track_summary_lf.collect()
        raw_sample = build_report_detail(
            raw_matches_lf,
            raw_detail_columns,
            keywords=keywords,
            detail_mode=detail_mode,
            raw_limit=raw_limit,
            include_statement_metadata=True,
        )

        tables = {
            "resumen general": display_dataframe(pd.DataFrame([{
                "keywords": ", ".join(keywords),
                "mode": mode,
                "period_basis": period_label,
                "start_month": start_month or "",
                "end_month": end_month or "",
                "excluded_isrcs": ", ".join(excluded_isrcs),
                "song_level_rows": song_rows,
                "song_level_amount_usd": song_amount_usd,
                "song_level_units": song_units,
                "raw_sample_rows": len(raw_sample),
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            }])),
            "resumen mensual": display_dataframe(monthly_summary.to_pandas()),
            "resumen por store": display_dataframe(store_summary.to_pandas()),
            "resumen por territorio": display_dataframe(territory_summary.to_pandas()),
            "resumen por tema": display_dataframe(track_summary.drop("_report_identity", "_dashgo_only", strict=False).to_pandas()),
        }

        if contract_snapshot is not None:
            from app.royalty_reports.excel_contracts import enrich_tables
            enrich_tables(tables, track_summary, summary_base_lf, contract_snapshot, keywords, contract_columns)

        tables["resumen por tema"] = present_dashgo_summary(tables["resumen por tema"], track_summary)

        if not raw_sample.empty:
            tables["detalle"] = raw_sample

        from app.royalty_scope import is_wml
        matched=set(statement_base_lf.select('asset_isrc').unique().collect()['asset_isrc'].drop_nulls().to_list()) if is_wml() else set()
        return add_wml_reference_annex(tables,matched)
    else:
        song = (
            add_report_code(
                normalize_report_units(
                    add_period_filter(
                        add_match_text(
                            add_source_account_filter(
                                scan_income(song_path).filter(song_filter),
                                song_cols,
                                source,
                                account,
                            ),
                            song_cols,
                            SEARCH_COLUMNS_SONG,
                        ),
                        song_cols,
                        start_month,
                        end_month,
                        period_column,
                    ),
                    song_cols,
                ),
                song_cols,
            )
            .pipe(lambda frame: filter_reportable_generation(frame, song_cols))
            .pipe(lambda frame: apply_report_net_personalization(frame))
            .filter(exclude_isrc_expr(song_cols, excluded_isrcs))
            .with_columns(pl.col(period_column).cast(pl.Utf8).alias("period_month"))
            .collect()
        )

    if song.height == 0:
        print("No hubo matches en song_level_all_sources.")
        return {
            "resumen general": display_dataframe(pd.DataFrame([{
                "keywords": ", ".join(keywords),
                "mode": mode,
                "period_basis": period_label,
                "start_month": start_month or "",
                "end_month": end_month or "",
                "excluded_isrcs": ", ".join(excluded_isrcs),
                "song_level_rows": 0,
                "song_level_amount_usd": 0,
                "song_level_units": 0,
                "raw_sample_rows": 0,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            }])),
            "sin resultados": display_dataframe(pd.DataFrame([{
                "resultado": "Sin coincidencias para los parametros ingresados."
            }])),
        }

    monthly_summary = (
        song
        .group_by(["period_month"])
        .agg([
            pl.sum("amount_usd").alias("amount_usd"),
            pl.sum("units").alias("units"),
            pl.len().alias("rows"),
        ])
        .sort("period_month")
    )

    song = with_video_groups(song.lazy(), _dashgo_video_groups).collect()
    track_summary = build_track_summary_lf(song.lazy(), include_identity=contract_snapshot is not None, include_dashgo_metadata=True).collect()

    raw_sample = pd.DataFrame()
    store_summary = pl.DataFrame()
    territory_summary = pl.DataFrame()
    if standardized_path.exists():
        raw_cols = standardized_cols
        raw_filter = build_filter(raw_cols, SEARCH_COLUMNS_STANDARDIZED, keywords, mode)

        raw_matches_lf = (
            add_report_code(
                normalize_report_usage(
                    normalize_report_store(
                        normalize_report_units(
                            add_period_filter(
                                add_match_text(
                                    add_source_account_filter(
                                        scan_income(standardized_path).filter(raw_filter),
                                        raw_cols,
                                        source,
                                        account,
                                    ),
                                    raw_cols,
                                    SEARCH_COLUMNS_STANDARDIZED,
                                ),
                                raw_cols,
                                start_month,
                                end_month,
                                period_column,
                            ),
                            raw_cols,
                        ),
                        raw_cols,
                    ),
                    raw_cols,
                ),
                raw_cols,
            )
            .pipe(lambda frame: filter_reportable_generation(frame, raw_cols))
            .pipe(lambda frame: apply_report_net_personalization(frame))
            .filter(exclude_isrc_expr(raw_cols, excluded_isrcs))
        )

        store_summary = (
            build_normalized_store_summary(
                raw_matches_lf,
                set(raw_matches_lf.collect_schema().names()),
            )
            .rename({"source": "distributor"})
            .collect()
        )

        territory_summary = (
            raw_matches_lf
            .with_columns(
                normalize_report_territory_expr().alias("report_territory")
            )
            .group_by(["report_territory"])
            .agg([
                pl.sum("amount_usd").alias("amount_usd"),
                pl.sum("units").alias("units"),
            ])
            .sort("report_territory")
            .collect()
        )

        raw_sample = build_report_detail(
            raw_matches_lf,
            raw_cols,
            keywords=keywords,
            detail_mode=detail_mode,
            raw_limit=raw_limit,
        )

    tables = {
        "resumen general": display_dataframe(pd.DataFrame([{
            "keywords": ", ".join(keywords),
            "mode": mode,
            "period_basis": period_label,
            "start_month": start_month or "",
            "end_month": end_month or "",
            "excluded_isrcs": ", ".join(excluded_isrcs),
            "song_level_rows": song.height,
            "song_level_amount_usd": song["amount_usd"].sum(),
            "song_level_units": song["units"].sum(),
            "raw_sample_rows": len(raw_sample),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }])),
        "resumen mensual": display_dataframe(monthly_summary.to_pandas()),
        "resumen por store": display_dataframe(store_summary.to_pandas()),
        "resumen por territorio": display_dataframe(territory_summary.to_pandas()),
        "resumen por tema": display_dataframe(track_summary.drop("_report_identity", "_dashgo_only", strict=False).to_pandas()),
    }

    if contract_snapshot is not None:
        from app.royalty_reports.excel_contracts import enrich_tables
        if not standardized_path.exists():
            raise ValueError("Falta el detalle publicado para verificar las vigencias de los contratos.")
        enrich_tables(tables, track_summary, with_video_groups(raw_matches_lf, _dashgo_video_groups),
                      contract_snapshot, keywords, contract_columns)

    tables["resumen por tema"] = present_dashgo_summary(tables["resumen por tema"], track_summary)

    if not raw_sample.empty:
        tables["detalle"] = raw_sample

    return add_wml_reference_annex(tables,{
        value for column in ('asset_isrc','ISRC') if column in song.columns
        for value in song[column].drop_nulls().to_list()
    })


def build_report(
    keywords: list[str],
    mode: str,
    raw_limit: int,
    start_month: str | None = None,
    end_month: str | None = None,
    period_basis: str = "transaction_month",
    song_path: Path = SONG_PATH,
    standardized_path: Path = STANDARDIZED_PATH,
    output_dir: Path = REPORTS,
    exclude_isrcs: list[str] | None = None,
    detail_mode: str = DETAIL_MODE_LIMITED,
    source: str | None = None,
    account: str | None = None,
    contract_snapshot: dict | None = None,
    contract_columns: str = "all",
) -> Path:
    output_path = report_output_path(keywords, start_month, end_month, output_dir)
    tables = build_report_tables(
        keywords=keywords,
        mode=mode,
        raw_limit=raw_limit,
        detail_mode=detail_mode,
        start_month=start_month,
        end_month=end_month,
        period_basis=period_basis,
        song_path=song_path,
        standardized_path=standardized_path,
        exclude_isrcs=exclude_isrcs,
        source=source,
        account=account,
        **({"contract_snapshot": contract_snapshot, "contract_columns": contract_columns} if contract_snapshot is not None else {}),
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, dataframe in tables.items():
            dataframe.to_excel(writer, index=False, sheet_name=sheet_name)

        style_workbook(writer)
        if contract_snapshot is not None and "resumen por tema" in tables:
            ws = writer.book["resumen por tema"]
            for column, number_format in tables["resumen por tema"].attrs.get("contract_formats", {}).items():
                for row in ws.iter_rows(min_row=2, min_col=column, max_col=column):
                    row[0].number_format = number_format

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
        period_basis=args.period_basis,
        exclude_isrcs=args.exclude_isrc,
    )

    print("\nReporte generado:")
    print(output_path)


if __name__ == "__main__":
    main()
