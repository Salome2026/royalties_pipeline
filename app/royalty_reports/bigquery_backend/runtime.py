"""Use pinned BigQuery inputs in the ordinary royalty report worker."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Lock, Thread
import os

import pandas as pd
import polars as pl

from app.report_jobs import set_report_job_stage
from app.royalty_reports.builders import royalty_report_scope_label
from app.royalty_reports.contract_filter import freeze_filter, require_filter, use_filter
from app.royalty_reports.contracts import ReportBuildResult
from app.royalty_reports.engine import ReportRuntime
from app.royalty_reports.execution import execute_report_job
from app.royalty_reports.google_sheets import (
    GOOGLE_SHEETS_CELL_CAPACITY,
    complete_sheet_grid,
    create_google_sheet,
)
from app.royalty_scope import use_scope, wml_policy
from lib.distributor_policy_store import use_distributor_policy_snapshot
from scripts import build_keyword_royalty_report as report
from scripts.build_executive_royalty_pdf import build_executive_royalty_pdf
from scripts.lib.product_income import use_product_income
from .delivery import DetailRows, artifact, build_files
from .publication import PublicationError, digest, file_sha, read_json, write_json, LABELS
from .reader import read_dashgo_groups, read_source
from .selection import SpooledSelection, write_selection


SOURCE_KEYS = ("keywords", "mode", "period_basis", "start_month", "end_month", "source", "account")


class BigQueryReportBackend:
    def __init__(self, publications, *, publish_interval: float = 10, export_bucket: str | None = None,
                 queued_jobs: tuple[int, ...] = (), shared_state=None, dispatch_job=None,
                 watch_inbox: bool = True, reconcile_job=None, live_contracts: bool = False) -> None:
        self.publications = publications
        self.root = publications.root
        self.root.mkdir(parents=True, exist_ok=True)
        self.interval = publish_interval
        self.export_bucket = export_bucket
        self.queued_jobs = queued_jobs
        self.shared_state = shared_state
        self.dispatch_job = dispatch_job
        self.watch_inbox = watch_inbox
        self.reconcile_job = reconcile_job
        self.live_contracts = live_contracts
        self.publisher = None
        self.stop_event = Event()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="royalty-report")
        self.lock = Lock()
        self.cache_locks: dict[str, Lock] = {}
        self.runtime = ReportRuntime(
            song_filename="song_level_all_sources.parquet",
            standardized_filename="standardized_raw_all_sources.parquet",
            catalog_master_filename="catalog_master.parquet",
            output_dir=self.root / "artifacts",
            resolve_marts=self._unexpected_legacy,
            configure_catalog_environment=self._unexpected_legacy,
            normalize_keywords=report.normalize_keywords,
            create_google_sheet=create_google_sheet,
            upload_artifact=self._unexpected_legacy,
            report_stage=set_report_job_stage,
            build_pinned=self.build,
        )

    @staticmethod
    def _unexpected_legacy(*args):
        raise RuntimeError("El entorno de pruebas requiere una publicación de BigQuery fijada.")

    def start(self) -> None:
        from .publication import watch_publications

        if self.watch_inbox:
            self.publications.initialize()
            self.publisher = Thread(
                target=watch_publications,
                args=(self.publications, self.stop_event, self.interval),
                name="royalty-publication",
                daemon=True,
            )
            self.publisher.start()
        for job_id in self.queued_jobs:
            self.launch(job_id)

    def stop(self) -> None:
        self.stop_event.set()
        if self.publisher is not None:
            self.publisher.join(timeout=5)
        self.pool.shutdown(wait=False, cancel_futures=True)

    def launch(self, job_id: int) -> str:
        if self.dispatch_job is None:
            self.pool.submit(execute_report_job, job_id, self.runtime)
        else:
            operation = self.dispatch_job(job_id)
            if operation:
                return operation
        return self.execution_name(job_id)

    def execution_name(self, job_id: int) -> str:
        prefix = "report-ops" if self.shared_state is not None else "report-preview"
        return f"{prefix}/{job_id}"

    def capture(self, scope: str):
        pin = self.publications.pin(scope)
        release = self.publications.checked(pin)
        paths = self.publications.paths(release)
        policy = wml_policy() if scope == "wml" else read_json(paths["policy/policy_snapshot.json"])
        if policy["policy_version"] != release["context"]["policy_version"]:
            raise PublicationError("La política no pertenece a la publicación.")
        return pin, release, paths, policy

    @staticmethod
    def marts(paths):
        return {role.removeprefix("marts/"): path for role, path in paths.items() if role.startswith("marts/")}

    @staticmethod
    def _replay(paths):
        return read_json(paths["contracts/app_test_context.json"])

    def contract_options(self, scope):
        _, _, paths, _ = self.capture(scope)
        if self.live_contracts:
            from .contract_capture import artist_options
            return artist_options(paths)
        return sorted({artist for context in self._replay(paths)["payouts"] for artist in context["contract_snapshot"]["artists"]})

    def distribution_options(self, scope):
        if self.live_contracts:
            from .contract_capture import distribution_options
            return distribution_options()
        _, _, paths, _ = self.capture(scope)
        return self._replay(paths)["templates"]

    def job_manifest(self, captured, params) -> dict:
        pin, release, paths, policy = captured
        manifest = {"release_id": release["source_release_id"], "royalty_scope": release["scope"], "report_publication": pin}
        if self.live_contracts:
            if release["scope"] == "wml":
                from app.royalty_workspace_store import records

                manifest["catalog_status_snapshot"] = [row["payload"] for row in records("catalog_status").values()]
                return manifest
            from .contract_capture import capture_contracts
            with self.context(release, paths, manifest, policy):
                return capture_contracts(manifest, params, release, paths)
        numbers = params.get("distribution_contract_numbers")
        enriched = params.get("include_contracts")
        payout = params.get("executive_mode") in {"contractual", "artist_settlement"}
        if numbers or enriched:
            snapshot = read_json(paths["contracts/excel_snapshot.json"])
            if snapshot["release_id"] != manifest["release_id"]:
                raise PublicationError("Los contratos no pertenecen a la publicación.")
            if enriched:
                manifest["excel_contract_snapshot"] = snapshot
            if numbers:
                replay = self._replay(paths)
                frozen = next((item for item in replay["number_filters"] if item["numbers"] == numbers), None)
                frozen = frozen or freeze_filter(numbers, replay["templates"], snapshot)
                manifest["distribution_contract_filter"] = require_filter(frozen, numbers, manifest["release_id"])
        if payout:
            from app.master_contracts import artist_key

            selected = {artist_key(artist) for artist in params["contract_artists"]}
            contexts = self._replay(paths)["payouts"]
            frozen = next(
                (item for item in contexts if {artist_key(name) for name in item["contract_snapshot"]["artists"]} == selected),
                None,
            )
            if frozen is None:
                raise ValueError("No hay un contexto contractual de prueba para esta selección de artistas.")
            if frozen["release_id"] != manifest["release_id"]:
                raise PublicationError("El contexto contractual no pertenece a la publicación.")
            manifest["catalog_dashboard"] = deepcopy(frozen["catalog_dashboard"])
            snapshot = deepcopy(frozen["contract_snapshot"])
            snapshot["template_version"] = "artist-settlement-v1" if params["executive_mode"] == "artist_settlement" else "contractual-v1"
            if numbers:
                roots = set(manifest["distribution_contract_filter"]["isrcs"])
                snapshot["catalog"] = [row for row in snapshot["catalog"] if row["isrc"] in roots]
                snapshot["contracts"] = [row for row in snapshot["contracts"] if row["isrc"] in roots]
            manifest["contract_snapshot"] = snapshot
        return manifest

    def source_options(self, scope):
        from google.cloud import bigquery

        _, release, _, policy = self.capture(scope)
        table = self.publications.component_table(release, "song")
        fields = {field["name"]: field["column"] for field in release["components"]["song"]["manifest"]["fields"]}
        quote = chr(96)
        source, account = (quote + fields[name] + quote for name in ("source", "account"))
        sql = f"SELECT DISTINCT {source} source, {account} account FROM {quote}{table}{quote} WHERE {source} IS NOT NULL AND {account} IS NOT NULL ORDER BY source, account"
        rows = self.publications.client.query(sql, job_config=bigquery.QueryJobConfig(labels=LABELS)).result()
        display = {(entry["source"], entry["account"]): entry.get("display_name") for entry in policy["entries"]}
        accounts = [
            {"source": row.source, "account": row.account,
             "display_name": display.get((row.source, row.account)) or f"{row.source.upper()} / {row.account.replace('_', ' ').title()}"}
            for row in rows if row.source and row.account
        ]
        return {"sources": sorted({item["source"] for item in accounts}), "source_accounts": accounts,
                "excel_contracts_supported": scope == "regular", "artist_settlement_supported": scope == "regular"}

    @contextmanager
    def context(self, release, paths, manifest, policy):
        marts = self.marts(paths)
        scope = release["scope"]
        status = manifest.get("catalog_status_snapshot")
        if scope == "wml" and status is None:
            status = pl.read_parquet(marts["catalog_status.parquet"]).to_dicts()
        allocation = read_json(marts["product_income_allocations.json"])
        with use_scope(scope, marts=marts, release_id=release["source_release_id"], catalog_status=status), \
                use_filter(manifest.get("distribution_contract_filter")), use_product_income(allocation), \
                use_distributor_policy_snapshot(policy):
            yield

    def selection(self, release, params, *, complete, manifest, paths, policy, count_only=False):
        release_key = digest(release)
        key = digest({"release": release_key, "params": params, "filter": manifest.get("distribution_contract_filter")})
        folder = self.root / "selections" / key
        with self.lock:
            lock = self.cache_locks.setdefault(key, Lock())
        with lock:
            raw = read_source(self.publications, release, "raw", params, report, folder, export_bucket=self.export_bucket)
            prepared = folder / "prepared.parquet"
            marker = folder / "prepared.json"
            with self.context(release, paths, manifest, policy):
                if marker.exists():
                    if read_json(marker)["sha256"] != file_sha(prepared):
                        raise PublicationError("Cambió la selección preparada.")
                else:
                    report.prepare_keyword_source(raw, prepared, params["keywords"], params["mode"], batch_size=16384)
                    write_json(marker, {"sha256": file_sha(prepared)})
                spool = None
                if complete:
                    spool_receipt = folder / "spool.json"
                    if spool_receipt.exists():
                        saved = read_json(spool_receipt)
                        summary, detail = folder / "summary.parquet", folder / "detail.parquet"
                        if file_sha(summary) != saved["summary_sha"] or file_sha(detail) != saved["detail_sha"]:
                            raise PublicationError("Cambió el detalle guardado.")
                        spool = SpooledSelection(summary, DetailRows.from_parquet(detail, saved["headers"], saved["rows"]))
                    else:
                        spool = write_selection(report, prepared, params, folder)
                        if spool is not None:
                            write_json(spool_receipt, {"rows": spool.detail.count, "headers": spool.detail.columns,
                                "summary_sha": file_sha(spool.summary), "detail_sha": file_sha(spool.detail.source)})
        groups = pl.DataFrame()
        if release["scope"] == "regular" and not count_only and params["source"] in (None, "dashgo"):
            with self.lock:
                group_lock = self.cache_locks.setdefault(release_key, Lock())
            with group_lock:
                groups = read_dashgo_groups(self.publications, release, self.root / "video_groups" / release_key)
        return prepared, groups, spool

    def detail_count(self, captured, params):
        _, release, paths, policy = captured
        manifest = self.job_manifest(captured, params)
        selection = {key: params.get(key) for key in SOURCE_KEYS}
        _, _, spool = self.selection(release, selection, complete=True, manifest=manifest, paths=paths, policy=policy, count_only=True)
        return spool.detail.count if spool else 0

    def build(self, request, job):
        manifest = job["input_manifest"]
        pin = manifest["report_publication"]
        release = self.publications.checked(pin)
        policy = job["policy_snapshot"]
        if release["scope"] != request.royalty_scope or manifest["release_id"] != release["source_release_id"] or policy["policy_version"] != release["context"]["policy_version"]:
            raise PublicationError("El pedido no coincide con el ámbito, los datos o la política publicados.")
        paths = self.publications.paths(release)
        output_root = self.root / "artifacts"
        output_root.mkdir(exist_ok=True)
        final = output_root / str(request.job_id)
        if self.shared_state is not None:
            completed = self.shared_state.result(request.job_id)
            if completed is not None:
                return completed
        elif final.exists():
            return self._completed(request.job_id, final)
        set_report_job_stage(request.job_id, "reading_data")
        params = {key: getattr(request, key) for key in SOURCE_KEYS}
        params["keywords"] = list(params["keywords"])
        country_detail = request.output_format == "excel" and request.detail_mode == "top_countries"
        complete = request.output_format in {"excel", "google_sheet"} and not country_detail
        summary_inputs = {}
        if request.executive_mode == "income":
            prepared, groups, spool = self.selection(release, params, complete=complete,
                manifest=manifest, paths=paths, policy=policy)
            if request.period_basis == "transaction_month":
                summary_inputs["song_path"] = read_source(
                    self.publications, release, "song", params, report, prepared.parent,
                    export_bucket=self.export_bucket,
                )
        set_report_job_stage(request.job_id, "building")
        with TemporaryDirectory(dir=output_root) as temp_name:
            output = Path(temp_name)
            with self.context(release, paths, manifest, policy):
                if request.executive_mode != "income":
                    built = self._contractual_pdf(request, job, release, output)
                    files = [artifact(built.output_path, built.content_type)]
                else:
                    detail_mode = "top_countries" if country_detail else "full" if complete else "limited"
                    tables = report.build_report_tables(**params, raw_limit=0, detail_mode=detail_mode,
                        standardized_path=prepared, _dashgo_video_groups=groups, spooled_selection=spool,
                        contract_snapshot=manifest.get("excel_contract_snapshot"), contract_columns=request.contract_columns,
                        **summary_inputs)
                    if request.output_format == "google_sheet":
                        self.publications.checked(pin)
                        set_report_job_stage(request.job_id, "uploading")
                        return self._sheet(tables, params)
                    if request.output_format == "executive_pdf":
                        pdf = build_executive_royalty_pdf(tables=tables, output_dir=output,
                            scope_label=royalty_report_scope_label(params["source"], params["account"]),
                            keywords=params["keywords"], period_basis=params["period_basis"],
                            start_month=params["start_month"], end_month=params["end_month"])
                        files = [artifact(pdf, "application/pdf")]
                    else:
                        detail = tables.pop("detalle", None)
                        if detail is not None and not isinstance(detail, DetailRows):
                            detail = DetailRows.from_frame(detail)
                        files = build_files(report, tables, params, output, detail=detail)["files"]
            self.publications.checked(pin)
            set_report_job_stage(request.job_id, "uploading")
            if self.shared_state is not None:
                return self.shared_state.result(request.job_id, files)
            write_json(output / "download.json", [{k: v for k, v in item.items() if k != "path"} for item in files])
            os.replace(output, final)
        return self._completed(request.job_id, final)

    def _contractual_pdf(self, request, job, release, output):
        from app.royalty_reports.artist_settlement import build_individual_pdf
        from app.royalty_reports.contract_pdf import build_contractual_pdf

        eligible = release["components"]["eligible"]["manifest"]
        if job["input_manifest"]["catalog_dashboard"]["release_id"] != eligible["release_id"]:
            raise PublicationError("La base elegible no coincide con el pedido.")
        archive = (self.publications.client, self.publications.component_table(release, "eligible"))
        builder = build_individual_pdf if request.executive_mode == "artist_settlement" else build_contractual_pdf
        return builder(request, job, output, archive=archive)

    def _sheet(self, tables, params):
        grid = complete_sheet_grid(tables)
        cells = sum(sheet["rowCount"] * sheet["columnCount"] for sheet in grid.values())
        if cells > GOOGLE_SHEETS_CELL_CAPACITY:
            raise ValueError(f"El informe completo necesita {cells:,} celdas. Elegí Excel para conservar el detalle completo.")
        detail = tables.get("detalle")
        if isinstance(detail, DetailRows):
            frame = pd.read_parquet(detail.source)
            frame.columns = detail.columns
            tables["detalle"] = frame
        url = create_google_sheet(tables, params["keywords"], params["start_month"], params["end_month"])
        return ReportBuildResult(None, None, None, url)

    @staticmethod
    def _completed(job_id, folder):
        files = read_json(folder / "download.json")
        first = files[0]
        return ReportBuildResult(f"report-preview://{job_id}", first["name"], first["content_type"], None, first["bytes"], first["sha256"])

    def public_job(self, job):
        if job and self.reconcile_job is not None:
            job = self.reconcile_job(job)
        if job and job["download_ready"]:
            if self.shared_state is not None and job["engine_version"] == "bigquery":
                files = self.shared_state.files(job["id"])
                job = {**job, "download_ready": bool(files)}
            else:
                manifest = self.root / "artifacts" / str(job["id"]) / "download.json"
                files = read_json(manifest) if manifest.is_file() else []
            if files:
                job = {**job, "download_files": [
                    {"part": "primary" if index == 0 else "detail", "name": file["name"]}
                    for index, file in enumerate(files)
                ]}
        return job

    def download(self, job_id: int, part: str):
        folder = self.root / "artifacts" / str(job_id)
        files = read_json(folder / "download.json")
        index = 0 if part == "primary" else 1
        if index >= len(files):
            raise FileNotFoundError("El reporte no tiene ese archivo.")
        entry = files[index]
        path = folder / entry["name"]
        if not path.resolve().is_relative_to(folder.resolve()) or path.stat().st_size != entry["bytes"]:
            raise FileNotFoundError("El archivo del reporte ya no está disponible.")
        return path, entry
