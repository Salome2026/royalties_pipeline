from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import polars as pl

try:
    from build_fuga_gusty_contract_report import (
        best_artist_expr,
        best_title_expr,
        build_listado,
        build_onerpm_map,
        classify_fuga,
        coalesce_number_expr,
        coalesce_text_expr,
        group_sum,
        gusty_filter,
        normalize_text,
        signature,
        style_workbook,
        text_col,
    )
except ModuleNotFoundError:
    from scripts.build_fuga_gusty_contract_report import (
        best_artist_expr,
        best_title_expr,
        build_listado,
        build_onerpm_map,
        classify_fuga,
        coalesce_number_expr,
        coalesce_text_expr,
        group_sum,
        gusty_filter,
        normalize_text,
        signature,
        style_workbook,
        text_col,
    )

try:
    from lib.catalog_report_filter import with_catalog_report_status
    from lib.distributor_policy_store import load_distributor_policy_document
    from lib.store_taxonomy import build_normalized_store_summary
except ModuleNotFoundError:
    from scripts.lib.catalog_report_filter import with_catalog_report_status
    from scripts.lib.distributor_policy_store import load_distributor_policy_document
    from scripts.lib.store_taxonomy import build_normalized_store_summary


BASE = Path(r"C:\royalties_pipeline")
MARTS = BASE / "warehouse" / "marts"
REGISTRY = BASE / "warehouse" / "registry"
REPORTS = BASE / "reports"
RAW_PATH = MARTS / "standardized_raw_all_sources.parquet"
CONTRACT_CUTOFFS_PATH = REGISTRY / "contract_cutoffs.json"
SUPER_JUNTE_TERMS = [
    "super junte",
    "superjunte",
    "junte rkt",
]


def load_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("entries", [])


def policy_table() -> pl.DataFrame:
    rows: list[dict] = []
    for policy in load_distributor_policy_document().get("entries", []):
        source = policy.get("source")
        account = policy.get("account")
        for source_sheet, rule in (policy.get("sheet_rules") or {}).items():
            if not isinstance(rule, dict):
                continue
            rows.append(
                {
                    "source": source,
                    "account": account,
                    "source_sheet": source_sheet,
                    "policy_statement_view": str(rule.get("statement_view")),
                    "policy_catalog_view": str(rule.get("catalog_view")),
                    "policy_cash_view": str(rule.get("cash_view")),
                    "policy_revenue_basis": str(rule.get("revenue_basis") or ""),
                    "include_generation_for_report": bool(
                        rule.get("revenue_basis") in {"generation", "correction", "legacy_generation"}
                    )
                    and rule.get("catalog_view") is True,
                }
            )
    return pl.DataFrame(rows)


def super_junte_filter(columns: set[str]) -> pl.Expr:
    expr = pl.lit(False)
    for col in [
        "artist_statement_style",
        "asset_artist_statement",
        "track_statement_style",
        "asset_title_statement",
        "Album Title",
        "album_title",
        "artists_raw",
        "Track Artists",
        "Product Artist",
        "Asset Artist",
        "Title",
        "Video Title",
        "Track Title",
        "Channel Name",
        "Product Title",
        "Asset Title",
        "TRACK ARTIST",
        "PRODUCT ARTIST",
        "TRACK",
        "PRODUCT",
    ]:
        if col in columns:
            text = text_col(col).str.to_lowercase()
            for term in SUPER_JUNTE_TERMS:
                expr = expr | text.str.contains(term, literal=True).fill_null(False)
    return expr


def prepare_all_gusty_rows(path: Path, start_month: str | None, end_month: str | None) -> pl.DataFrame:
    columns = set(pl.scan_parquet(path).collect_schema().names())
    amount_eur = next((col for col in ["amount_eur", "net_amount_eur", "Reported Royalty"] if col in columns), None)
    units_candidates = [
        "units",
        "asset_quantity_num",
        "product_quantity_num",
        "Asset Quantity",
        "Product Quantity",
        "QUANTITY",
        "Quantity",
        "Units",
        "Units of Sold",
    ]
    dedicated_gusty_account = (text_col("source") == "onerpm") & (text_col("account") == "gusty_dj")
    lf = (
        pl.scan_parquet(path)
        .filter(gusty_filter(columns) | dedicated_gusty_account | super_junte_filter(columns))
        .with_columns(
            [
                best_title_expr(columns),
                best_artist_expr(columns),
                pl.col("amount_usd").cast(pl.Float64, strict=False).fill_null(0.0).alias("amount_usd"),
                (pl.col(amount_eur).cast(pl.Float64, strict=False).fill_null(0.0) if amount_eur else pl.lit(0.0)).alias("ingresos_eur"),
                coalesce_text_expr(columns, ["asset_isrc", "ISRC", "Asset ISRC", "isrc"], "asset_isrc"),
                coalesce_text_expr(columns, ["product_upc", "UPC", "Product UPC", "DISPLAY UPC", "UPC Code"], "product_upc"),
                coalesce_text_expr(columns, ["video_id", "Video ID", "VideoId", "YOUTUBE VIDEO ID", "YouTube Video ID", "ID", "Parent ID"], "video_id_best"),
                coalesce_number_expr(columns, units_candidates, "units"),
                text_col("source").alias("source"),
                text_col("account").alias("account"),
                text_col("statement_period").alias("statement_period"),
                text_col("transaction_month").alias("transaction_month"),
                (text_col("content_type", "catalog") if "content_type" in columns else pl.lit("catalog")).alias("tipo_contenido"),
                (text_col("dsp_normalized") if "dsp_normalized" in columns else pl.lit(None, dtype=pl.Utf8)).alias("dsp_normalized"),
                (text_col("monetization_normalized") if "monetization_normalized" in columns else pl.lit(None, dtype=pl.Utf8)).alias("monetization_normalized"),
                (text_col("content_origin_normalized") if "content_origin_normalized" in columns else pl.lit(None, dtype=pl.Utf8)).alias("content_origin_normalized"),
                (text_col("plan_normalized") if "plan_normalized" in columns else pl.lit(None, dtype=pl.Utf8)).alias("plan_normalized"),
                (text_col("classification_status") if "classification_status" in columns else pl.lit(None, dtype=pl.Utf8)).alias("classification_status"),
                (text_col("store_report_label") if "store_report_label" in columns else pl.lit(None, dtype=pl.Utf8)).alias("store_report_label"),
                (text_col("dsp") if "dsp" in columns else pl.lit(None, dtype=pl.Utf8)).alias("dsp_original"),
                (text_col("store_name") if "store_name" in columns else pl.lit(None, dtype=pl.Utf8)).alias("store_name"),
                (text_col("sale_type") if "sale_type" in columns else pl.lit(None, dtype=pl.Utf8)).alias("sale_type"),
                (text_col("sale_user_type") if "sale_user_type" in columns else pl.lit(None, dtype=pl.Utf8)).alias("sale_user_type"),
                (text_col("territory") if "territory" in columns else pl.lit(None, dtype=pl.Utf8)).alias("territory"),
                (text_col("statement_type") if "statement_type" in columns else pl.lit(None, dtype=pl.Utf8)).alias("statement_type"),
                (text_col("statement_file_name") if "statement_file_name" in columns else pl.lit(None, dtype=pl.Utf8)).alias("statement_file_name"),
                (text_col("source_sheet") if "source_sheet" in columns else pl.lit(None, dtype=pl.Utf8)).alias("source_sheet"),
                (text_col("revenue_basis") if "revenue_basis" in columns else pl.lit(None, dtype=pl.Utf8)).alias("revenue_basis"),
                (pl.col("possible_internal_transfer").cast(pl.Boolean, strict=False) if "possible_internal_transfer" in columns else pl.lit(False)).alias("possible_internal_transfer"),
                (text_col("asset_title_statement") if "asset_title_statement" in columns else pl.lit(None, dtype=pl.Utf8)).alias("asset_title_statement"),
                (text_col("artist_statement_style") if "artist_statement_style" in columns else pl.lit(None, dtype=pl.Utf8)).alias("artist_statement_style"),
                (text_col("asset_artist_statement") if "asset_artist_statement" in columns else pl.lit(None, dtype=pl.Utf8)).alias("asset_artist_statement"),
            ]
        )
        .with_columns(
            [
                pl.col("tema").map_elements(normalize_text, return_dtype=pl.Utf8).alias("_title_key"),
                pl.col("tema").map_elements(signature, return_dtype=pl.Utf8).alias("_signature_key"),
                pl.col("source_sheet").fill_null("").alias("_source_sheet_key"),
            ]
        )
    )
    if start_month:
        lf = lf.filter(pl.col("statement_period") >= start_month)
    if end_month:
        lf = lf.filter(pl.col("statement_period") <= end_month)
    return lf.collect()


def build_mawz_share_in_analysis(raw_path: Path, start_month: str | None, end_month: str | None) -> pd.DataFrame:
    columns = set(pl.scan_parquet(raw_path).collect_schema().names())
    if not {"source", "account", "source_sheet", "amount_usd"}.issubset(columns):
        return pd.DataFrame()
    amount_eur = next((col for col in ["amount_eur", "net_amount_eur", "Reported Royalty"] if col in columns), None)
    lf = (
        pl.scan_parquet(raw_path)
        .filter(
            (text_col("source") == "onerpm")
            & (text_col("account") == "mawzrecords")
            & (text_col("source_sheet") == "Shares In & Out")
        )
    )
    if "Share Type" in columns:
        lf = lf.filter(text_col("Share Type").str.to_lowercase() == "in")
    if start_month:
        lf = lf.filter(pl.col("statement_period") >= start_month)
    if end_month:
        lf = lf.filter(pl.col("statement_period") <= end_month)

    select_exprs = [
        text_col("statement_period").alias("statement_period"),
        text_col("transaction_month").alias("transaction_month"),
        text_col("source").alias("source"),
        text_col("account").alias("account"),
        text_col("source_sheet").alias("source_sheet"),
        (text_col("Share Type") if "Share Type" in columns else pl.lit("In")).alias("share_type"),
        (pl.col("% Share In/Out").cast(pl.Float64, strict=False) if "% Share In/Out" in columns else pl.lit(None, dtype=pl.Float64)).alias("share_pct"),
        (text_col("Payer Name") if "Payer Name" in columns else pl.lit(None, dtype=pl.Utf8)).alias("payer_name"),
        (text_col("Receiver Name") if "Receiver Name" in columns else pl.lit(None, dtype=pl.Utf8)).alias("receiver_name"),
        coalesce_text_expr(columns, ["Title", "Video Title", "Track Title", "Asset Title", "asset_title_statement", "track_statement_style"], "tema"),
        coalesce_text_expr(columns, ["artist_statement_style", "asset_artist_statement", "Track Artists", "Artist Name", "Channel Name"], "artist_best"),
        coalesce_text_expr(columns, ["ID", "asset_isrc", "ISRC", "Asset ISRC", "isrc"], "id"),
        coalesce_text_expr(columns, ["Parent ID", "product_upc", "UPC", "Product UPC"], "parent_id"),
        coalesce_text_expr(columns, ["Video ID", "video_id", "VideoId", "YOUTUBE VIDEO ID"], "video_id_best"),
        text_col("revenue_basis").alias("revenue_basis"),
        pl.col("amount_usd").cast(pl.Float64, strict=False).fill_null(0.0).alias("amount_usd"),
        (pl.col(amount_eur).cast(pl.Float64, strict=False).fill_null(0.0) if amount_eur else pl.lit(0.0)).alias("ingresos_eur"),
        coalesce_number_expr(columns, ["units", "Units", "Units of Sold", "Quantity", "QUANTITY"], "units"),
    ]
    df = lf.select(select_exprs).collect()
    if df.height == 0:
        return pd.DataFrame(columns=[expr.meta.output_name() for expr in select_exprs] + ["filas_raw"])
    group_cols = [col for col in df.columns if col not in {"amount_usd", "ingresos_eur", "units"}]
    return (
        df.group_by(group_cols)
        .agg(
            [
                pl.sum("amount_usd").alias("ingresos_usd"),
                pl.sum("ingresos_eur").alias("ingresos_eur"),
                pl.sum("units").alias("unidades"),
                pl.len().alias("filas_raw"),
            ]
        )
        .sort(["statement_period", "transaction_month", "ingresos_usd"], descending=[False, False, True])
        .to_pandas()
    )


def apply_policy_flags(rows: pl.DataFrame) -> pl.DataFrame:
    policies = policy_table()
    if policies.is_empty():
        return rows.with_columns(
            [
                pl.lit(True).alias("include_generation_for_report"),
                pl.lit("sin policy").alias("policy_revenue_basis"),
                pl.lit("").alias("policy_statement_view"),
            ]
        )
    joined = rows.join(
        policies,
        left_on=["source", "account", "_source_sheet_key"],
        right_on=["source", "account", "source_sheet"],
        how="left",
    )
    return joined.with_columns(
        [
            pl.col("include_generation_for_report").fill_null(
                ~pl.col("revenue_basis").fill_null("").is_in(["transfer", "summary"])
            ),
            pl.col("policy_revenue_basis").fill_null(pl.col("revenue_basis").fill_null("generation")),
            pl.col("policy_statement_view").fill_null("sin regla exacta"),
        ]
    )


def contract_cutoff_month() -> str:
    cutoffs = load_entries(CONTRACT_CUTOFFS_PATH)
    gusty = next((entry for entry in cutoffs if entry.get("cutoff_id") == "onerpm_gusty_dj_contract_start"), {})
    return str(gusty.get("contract_start_month") or gusty.get("contract_start_date") or "2023-04")[:7]


def contract_cutoff_summary() -> str:
    cutoffs = load_entries(CONTRACT_CUTOFFS_PATH)
    gusty = next((entry for entry in cutoffs if entry.get("cutoff_id") == "onerpm_gusty_dj_contract_start"), {})
    return (
        f"{gusty.get('contract_start_date') or gusty.get('contract_start_month') or 'sin corte'} "
        f"({gusty.get('cutoff_basis') or 'sin base'}; evidencia: {', '.join(gusty.get('evidence_terms') or [])})"
    )


def build_full_gusty_content_map(path: Path) -> pd.DataFrame:
    columns = set(pl.scan_parquet(path).collect_schema().names())
    cutoff = contract_cutoff_month()
    df = (
        pl.scan_parquet(path)
        .filter((text_col("source") == "onerpm") & (text_col("account") == "gusty_dj"))
        .with_columns(
            [
                best_title_expr(columns),
                best_artist_expr(columns),
                coalesce_text_expr(columns, ["asset_isrc", "ISRC", "Asset ISRC", "isrc"], "asset_isrc"),
                pl.col("amount_usd").cast(pl.Float64, strict=False).fill_null(0.0).alias("amount_usd"),
                coalesce_number_expr(columns, ["units", "Units", "Units of Sold", "Quantity", "QUANTITY"], "units"),
            ]
        )
        .filter(pl.col("tema").is_not_null())
        .with_columns(
            [
                pl.col("tema").map_elements(normalize_text, return_dtype=pl.Utf8).alias("_title_key"),
                pl.col("tema").map_elements(signature, return_dtype=pl.Utf8).alias("_signature_key"),
            ]
        )
        .select(["asset_isrc", "tema", "artist_best", "transaction_month", "amount_usd", "units", "_title_key", "_signature_key"])
        .collect()
    )
    rows: list[dict] = []
    for method, key_col in [("isrc", "asset_isrc"), ("title", "_title_key"), ("signature", "_signature_key")]:
        tmp = df.filter(pl.col(key_col).is_not_null() & (pl.col(key_col) != ""))
        if tmp.height == 0:
            continue
        grouped = (
            tmp.group_by(key_col)
            .agg(
                [
                    pl.min("transaction_month").alias("onerpm_first_month"),
                    pl.col("tema").drop_nulls().mode().first().alias("onerpm_title"),
                    pl.col("artist_best").drop_nulls().mode().first().alias("onerpm_artist"),
                    pl.sum("amount_usd").alias("onerpm_total_usd"),
                    pl.sum("units").alias("onerpm_units"),
                    pl.len().alias("onerpm_rows"),
                ]
            )
            .rename({key_col: "match_key"})
            .to_pandas()
        )
        grouped["match_method"] = method
        rows.extend(grouped.to_dict("records"))
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["match_method", "match_key", "onerpm_first_month", "onerpm_title", "onerpm_artist", "contract_segment"])
    out["contract_segment"] = out["onerpm_first_month"].apply(
        lambda value: "CONTRATO NUEVO" if str(value or "")[:7] >= cutoff else "CONTRATO VIEJO"
    )
    return out.sort_values(["match_method", "onerpm_total_usd"], ascending=[True, False])


def classify_by_unique_content(rows: pl.DataFrame, raw_path: Path) -> pl.DataFrame:
    if rows.height == 0:
        return rows.with_columns(
            [
                pl.lit("CONTRATO NUEVO - SIN MATCH ONErpm").alias("contract_segment"),
                pl.lit("sin_match_asumido_nuevo").alias("match_method"),
                pl.lit(None, dtype=pl.Utf8).alias("onerpm_first_month"),
                pl.lit(None, dtype=pl.Utf8).alias("onerpm_title"),
            ]
        )
    onerpm_map = build_full_gusty_content_map(raw_path)
    key_cols = ["asset_isrc", "_title_key", "_signature_key"]
    prepared = rows.with_columns([pl.col(col).fill_null("").alias(col) for col in key_cols])
    unique_content = prepared.select(key_cols).unique()
    classified_content = classify_fuga(unique_content, onerpm_map).select(
        key_cols + ["contract_segment", "match_method", "onerpm_first_month", "onerpm_title"]
    )
    return prepared.join(classified_content, on=key_cols, how="left").with_columns(
        [
            pl.col("contract_segment").fill_null("CONTRATO NUEVO - SIN MATCH ONErpm"),
            pl.col("match_method").fill_null("sin_match_asumido_nuevo"),
        ]
    )


def build_gusty_all_companies_contract_report(
    start_month: str | None = None,
    end_month: str | None = "2026-03",
    output_dir: Path = REPORTS,
    raw_path: Path = RAW_PATH,
) -> Path:
    all_rows = prepare_all_gusty_rows(raw_path, start_month, end_month)
    all_rows = apply_policy_flags(all_rows)

    generation_candidates = all_rows.filter(pl.col("include_generation_for_report") == True)
    if generation_candidates.height:
        generation_with_catalog = with_catalog_report_status(generation_candidates.lazy(), set(generation_candidates.columns)).collect()
        generation = generation_with_catalog.filter(pl.col("include_in_reports") == True)
        catalog_excluded = generation_with_catalog.filter(pl.col("include_in_reports") != True)
    else:
        generation = generation_candidates
        catalog_excluded = generation_candidates

    excluded_by_policy = all_rows.filter(pl.col("include_generation_for_report") != True)
    df = classify_by_unique_content(generation, raw_path)
    mawz_share_in = build_mawz_share_in_analysis(raw_path, start_month, end_month)

    title = "Gusty todas las companias - contratos viejo/nuevo"
    criterio = (
        "ONErpm/gusty_dj entra completo como cuenta dedicada. "
        "El resto de fuentes entra cuando artista/titulo contiene Gusty o Super Junte, "
        "porque Super Junte pertenece al universo Gusty aunque algunas filas no traigan su nombre. "
        f"Corte statement_period {start_month or 'inicio'} a {end_month or 'ultimo'}. "
        "Clasificacion viejo/nuevo segun mapa ONErpm Gusty y corte contractual. "
        "ONErpm MAWZ Shares In & Out queda fuera del total principal por policy; "
        "se agrega como hoja separada de analisis."
    )

    overview = pd.DataFrame(
        [
            {"indicador": "Reporte", "valor": title},
            {"indicador": "Criterio", "valor": criterio},
            {"indicador": "Corte contractual Gusty", "valor": contract_cutoff_summary()},
            {"indicador": "Corte statement", "valor": f"{start_month or 'inicio'} a {end_month or 'ultimo'}"},
            {"indicador": "Ingresos USD incluidos", "valor": float(df["amount_usd"].sum()) if df.height else 0.0},
            {"indicador": "Ingresos EUR FUGA incluidos", "valor": float(df["ingresos_eur"].sum()) if df.height else 0.0},
            {"indicador": "Unidades incluidas", "valor": float(df["units"].sum()) if df.height else 0.0},
            {"indicador": "Filas incluidas", "valor": df.height},
            {"indicador": "Temas aprox incluidos", "valor": df.select("tema").unique().height if df.height else 0},
            {"indicador": "Excluido por policy USD", "valor": float(excluded_by_policy["amount_usd"].sum()) if excluded_by_policy.height else 0.0},
            {"indicador": "Excluido por catalogo USD", "valor": float(catalog_excluded["amount_usd"].sum()) if catalog_excluded.height else 0.0},
            {"indicador": "MAWZ Shares In USD analisis", "valor": float(mawz_share_in["ingresos_usd"].sum()) if not mawz_share_in.empty and "ingresos_usd" in mawz_share_in.columns else 0.0},
            {"indicador": "MAWZ Shares In filas agrupadas", "valor": int(len(mawz_share_in)) if not mawz_share_in.empty else 0},
            {"indicador": "Desde transaction incluido", "valor": df["transaction_month"].min() if df.height else ""},
            {"indicador": "Hasta transaction incluido", "valor": df["transaction_month"].max() if df.height else ""},
        ]
    )

    detalle_group_cols = [
        "contract_segment",
        "match_method",
        "source",
        "account",
        "source_sheet",
        "statement_period",
        "transaction_month",
        "asset_isrc",
        "product_upc",
        "video_id_best",
        "tema",
        "artist_best",
        "asset_title_statement",
        "artist_statement_style",
        "asset_artist_statement",
        "tipo_contenido",
        "dsp_normalized",
        "monetization_normalized",
        "content_origin_normalized",
        "plan_normalized",
        "classification_status",
        "store_report_label",
        "dsp_original",
        "store_name",
        "territory",
        "sale_type",
        "sale_user_type",
    ]
    detalle_group_cols = [col for col in detalle_group_cols if col in df.columns]
    if df.height:
        detalle = (
            df.group_by(detalle_group_cols)
            .agg(
                [
                    pl.sum("amount_usd").alias("ingresos_usd"),
                    pl.sum("ingresos_eur").alias("ingresos_eur"),
                    pl.sum("units").alias("unidades"),
                    pl.len().alias("filas_raw"),
                ]
            )
            .sort(["source", "account", "contract_segment", "statement_period", "ingresos_usd"], descending=[False, False, False, False, True])
            .to_pandas()
        )
    else:
        detalle = pd.DataFrame(columns=detalle_group_cols + ["ingresos_usd", "ingresos_eur", "unidades", "filas_raw"])

    source_summary = group_sum(df, ["source", "account", "source_sheet", "contract_segment", "match_method"])
    contract_summary = group_sum(df, ["contract_segment", "match_method"])

    excluded_cols = [
        "source",
        "account",
        "source_sheet",
        "revenue_basis",
        "policy_revenue_basis",
        "statement_period",
        "transaction_month",
        "asset_isrc",
        "product_upc",
        "video_id_best",
        "tema",
        "artist_best",
        "amount_usd",
        "units",
    ]
    excluded_cols = [col for col in excluded_cols if col in excluded_by_policy.columns]
    if excluded_by_policy.height:
        excluded_policy_pd = (
            excluded_by_policy
            .group_by([col for col in excluded_cols if col not in {"amount_usd", "units"}])
            .agg([
                pl.sum("amount_usd").alias("amount_usd"),
                pl.sum("units").alias("units"),
                pl.len().alias("filas_raw"),
            ])
            .sort(["source", "account", "source_sheet", "statement_period"])
            .to_pandas()
        )
    else:
        excluded_policy_pd = pd.DataFrame(columns=excluded_cols + ["filas_raw"])

    catalog_cols = [
        "source",
        "account",
        "source_sheet",
        "statement_period",
        "transaction_month",
        "catalog_key",
        "catalog_business_status",
        "catalog_status_notes",
        "asset_isrc",
        "product_upc",
        "video_id_best",
        "tema",
        "artist_best",
        "amount_usd",
        "units",
    ]
    catalog_cols = [col for col in catalog_cols if col in catalog_excluded.columns]
    if catalog_excluded.height:
        catalog_excluded_pd = (
            catalog_excluded
            .group_by([col for col in catalog_cols if col not in {"amount_usd", "units"}])
            .agg([
                pl.sum("amount_usd").alias("amount_usd"),
                pl.sum("units").alias("units"),
                pl.len().alias("filas_raw"),
            ])
            .sort(["source", "account", "statement_period"])
            .to_pandas()
        )
    else:
        catalog_excluded_pd = pd.DataFrame(columns=catalog_cols + ["filas_raw"])

    store_summary = (
        build_normalized_store_summary(
            df.lazy(),
            set(df.columns),
            include_rows=True,
            extra_group_columns=["account", "contract_segment"],
        )
        .collect()
        .to_pandas()
        if df.height
        else pd.DataFrame()
    )

    tables = {
        "Resumen": overview,
        "Contrato Summary": contract_summary,
        "Fuente Summary": source_summary,
        "Listado": build_listado(df),
        "Mensual": group_sum(df, ["contract_segment", "source", "account", "statement_period", "transaction_month"]),
        "Store Summary": store_summary,
        "Territory Summary": group_sum(df, ["contract_segment", "source", "account", "territory"]),
        "Content Type": group_sum(df, ["contract_segment", "source", "account", "tipo_contenido"]),
        "Statement Summary": group_sum(df, ["contract_segment", "source", "account", "statement_period", "statement_type", "statement_file_name"]),
        "Detalle": detalle,
        "MAWZ Shares In": mawz_share_in,
        "Auditoria policy excluida": excluded_policy_pd,
        "Auditoria catalogo excluido": catalog_excluded_pd,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = output_dir / f"gusty_todas_companias_contratos_{start_month or 'inicio'}_a_{end_month or 'ultimo'}_{timestamp}.xlsx"
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, table in tables.items():
            table.to_excel(writer, sheet_name=sheet_name[:31], index=False)
        style_workbook(writer.book)
    return output


if __name__ == "__main__":
    print(build_gusty_all_companies_contract_report())
