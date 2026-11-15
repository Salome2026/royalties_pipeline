"""Build one admitted FUGA statement with the normal mart and Excel generators."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys


CASES = {"fuga-statement-upc": "655857944443", "fuga-statement-isrc": "ES71G1921229"}
CLOUD_CASES = {"fuga-cloud-upc": "789556228853", "fuga-cloud-isrc": "ARL2P2500320"}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def build(code, target, statement, context, *, reference, cloud_arrival=False, report_terms=()):
    target = target.resolve()
    copy = Path(__file__).resolve().parents[2]
    runtime = copy / "tmp/fuga_ingest_preview"
    if cloud_arrival:
        runtime = Path("/tmp/royalty-cloud-preview/fuga-arrival") if os.name != "nt" else copy / "tmp/report_cloud_preview/fuga-arrival"
    if target.parent.resolve() != runtime.resolve() or (
        target.name not in {"candidate", "current_system"} and not (
            reference and target.name == f"reference_{statement.name.removesuffix('.csv')}"
        )
    ):
        raise ValueError("El destino debe ser un directorio aislado de la prueba.")
    if code not in {copy, copy / "tmp/statement_ingest_preview/system_current_code"}:
        raise ValueError("Código o destino fuera del entorno de la prueba.")
    sys.path[:0] = [str(code), str(code / "scripts")]
    os.environ["VPO_PROJECT_ROOT"] = str(target)
    os.environ["VPO_CATALOG_STATUS_SYNC_GCS"] = "0"
    os.environ.setdefault("POLARS_MAX_THREADS", "2")
    os.chdir(code)
    import polars as pl
    from app import vpo_corp_api as api
    from app.royalty_reports.builders import build_keyword_excel, normalize_keywords
    from app.royalty_reports.contracts import ReportInputs, ReportRequest
    from app.royalty_scope import use_scope
    from scripts import build_catalog_master, build_consolidated_marts, build_product_income_allocations
    from scripts import build_song_level_fuga, build_statement_summary_mart, ingest_standardized_fuga
    from lib import fx
    from lib.distributor_policy_store import use_distributor_policy_snapshot
    from lib.ingestion_controls import validate_no_failed_batches
    from lib.statement_period import from_fuga_filename
    from scripts.lib.product_income import use_product_income

    marts = target / "warehouse/marts"
    inputs = target / "input_raw/fuga"
    registry = target / "warehouse/registry"
    for path in (marts, inputs, registry):
        path.mkdir(parents=True, exist_ok=True)
    incoming = inputs / statement.name
    if not incoming.exists():
        shutil.copyfile(statement, incoming)
    assert sha(incoming) == sha(statement)
    assert all(sha(context / name) == checksum for name, checksum in read(context / "binding.json").items())
    for name in ("exchange_rates.parquet", "catalog_release_lookup_cache.parquet", "fuga_video_catalog_decisions.json"):
        shutil.copyfile(context / name, registry / name)
    for name in ("catalog_status.parquet", "catalog_release_metadata.parquet"):
        shutil.copyfile(context / name, marts / name)
    for name in ("catalog_onerpm_artists.parquet", "catalog_ada_artists.parquet", "standardized_raw_orchard.parquet",
                 "standardized_raw_soundon.parquet", "standardized_raw_dashgo.parquet"):
        shutil.copyfile(context / name, marts / name)
    frozen = read(context / "policy_snapshot.json")
    fx.FX_PATH = registry / "exchange_rates.parquet"
    fx.fetch_monthly_avg_rate = lambda *args: (_ for _ in ()).throw(ValueError("Falta el FX congelado de la prueba."))
    ingest_standardized_fuga.BASE_DIR = target
    ingest_standardized_fuga.INPUT_DIR = inputs
    ingest_standardized_fuga.TEMP_DIR = target / "staging/fuga"
    ingest_standardized_fuga.OUTPUT_PATH = marts / "standardized_raw_fuga.parquet"
    build_song_level_fuga.INPUT_PATH = ingest_standardized_fuga.OUTPUT_PATH
    build_song_level_fuga.OUTPUT_PATH = marts / "song_level_fuga.parquet"
    raw = marts / "standardized_raw_all_sources.parquet"
    song = marts / "song_level_all_sources.parquet"
    catalog = marts / "catalog_master.parquet"
    allocation = marts / "product_income_allocations.json"
    build_statement_summary_mart.STANDARDIZED_PATH = raw
    build_statement_summary_mart.OUTPUT_PATH = marts / "statement_summary_all_sources.parquet"
    build_catalog_master.BASE = target
    build_catalog_master.MARTS_DIR = marts
    build_catalog_master.REGISTRY_DIR = registry
    build_catalog_master.SONG_LEVEL_PATH = song
    build_catalog_master.RELEASE_METADATA_PATH = marts / "catalog_release_metadata.parquet"
    build_catalog_master.STANDARDIZED_PATHS = [ingest_standardized_fuga.OUTPUT_PATH,
                                               context / "catalog_fuga_video_identity_context.parquet"]
    build_catalog_master.OUTPUT_PATH = catalog
    resolve_video = build_catalog_master.apply_automatic_extended
    confirmed = pl.read_parquet(context / "reviewed_video_context.parquet")
    video_ids = dict(confirmed.iter_rows())

    def resolve_with_reviewed_context(frame, root):
        # The December batch can lack video observations already reviewed in the historical catalog.
        def merge_video_ids(row):
            previous = video_ids.get(row["catalog_key"]) or ""
            native = row["video_ids"] or ""
            return " | ".join(sorted(set((native + " | " + previous).split(" | ")) - {""})) or None

        with_history = frame.with_columns(
            pl.struct("catalog_key", "video_ids").map_elements(merge_video_ids, return_dtype=pl.String).alias("video_ids")
        )
        return resolve_video(with_history, root)

    build_catalog_master.apply_automatic_extended = resolve_with_reviewed_context
    api.BASE = target
    api.DIGITAL_INCOME_SUMMARY_PATH = marts / "digital_income_statement_summary.parquet"

    with use_distributor_policy_snapshot(frozen), use_scope("regular", marts={
        "catalog_master.parquet": catalog, "catalog_status.parquet": marts / "catalog_status.parquet",
    }):
        ingest_standardized_fuga.main()
        build_song_level_fuga.main()
        build_consolidated_marts.consolidate([ingest_standardized_fuga.OUTPUT_PATH], raw, add_reporting_dimensions=True)
        build_consolidated_marts.consolidate([build_song_level_fuga.OUTPUT_PATH], song)
        build_statement_summary_mart.main()
        index = build_product_income_allocations.build(
            raw, context / "catalog_master.parquet", allocation, online=False,
            lookup_cache=registry / "catalog_release_lookup_cache.parquet",
            prior_index=read(context / "product_income_allocations.json"),
        )
        build_catalog_master.main()
        api.build_digital_income_summary_mart(raw, refresh_cache=True)
        api.build_royalties_dashboard_summary_mart(raw, refresh_cache=True,
                                                  output_path=marts / "royalties_dashboard_summary.parquet")
        validate_no_failed_batches(marts)
        closed = api.validate_analytics_package_for_publish()
        assert closed["ok"]
        receipts = {}
        if reference:
            out = target / "reports"
            out.mkdir(exist_ok=True)
            with use_product_income(index):
                month = from_fuga_filename(statement.name).period
                cases = dict(report_terms) if report_terms else (CLOUD_CASES if cloud_arrival else CASES)
                for case, keyword in cases.items():
                    params = {"keywords": [keyword], "mode": "any", "period_basis": "statement_period",
                              "start_month": month, "end_month": month, "raw_limit": 0,
                              "detail_mode": "full", "source": "fuga", "account": "indyana_records"}
                    job = {"id": 0, "report_key": "royalty_keyword", "output_format": "excel", "params": params}
                    request = ReportRequest.from_job(job, keywords=normalize_keywords(params["keywords"]))
                    built = build_keyword_excel(request, ReportInputs(song, raw, catalog, out))
                    receipts[case] = {"params": params, "xlsx": str(built.output_path), "sha256": sha(built.output_path)}
    measured = pl.scan_parquet(raw).select(pl.len().alias("rows"), pl.col("amount_usd").sum(),
                                           pl.col("net_amount_eur").sum()).collect().row(0, named=True)
    data = {"input_sha256": sha(incoming), "marts": str(marts), "metrics": measured,
            "package_validation": closed, "index_sha256": sha(allocation), "reports": receipts}
    (target / "native_receipt.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("Paquete FUGA cerrado", measured, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--statement", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--reference", action="store_true")
    parser.add_argument("--cloud-arrival", action="store_true")
    parser.add_argument("--report-term", nargs=2, action="append", default=[])
    args = parser.parse_args()
    build(args.code.resolve(), args.target.resolve(), args.statement.resolve(), args.context.resolve(),
          reference=args.reference, cloud_arrival=args.cloud_arrival, report_terms=args.report_term)
