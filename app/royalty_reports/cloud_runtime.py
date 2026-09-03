from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from google.cloud import storage

from app.report_jobs import set_report_job_stage
from app.royalty_reports.artifacts import GcsReportArtifactStore
from app.royalty_reports.builders import normalize_keywords
from app.royalty_reports.engine import ReportRuntime
from app.royalty_reports.google_sheets import create_google_sheet
from app.royalty_reports.manifests import require_manifest_object


SONG_FILE = "song_level_all_sources.parquet"
STANDARDIZED_FILE = "standardized_raw_all_sources.parquet"
CATALOG_MASTER_FILE = "catalog_master.parquet"
CATALOG_STATUS_FILE = "catalog_status.parquet"


@dataclass(frozen=True)
class GcsReportInputStore:
    bucket_name: str
    marts_prefix: str
    cache_dir: Path
    client_factory: Callable[[], storage.Client]

    def object_name(self, filename: str) -> str:
        prefix = self.marts_prefix.strip("/")
        return f"{prefix}/{filename}" if prefix else filename

    def resolve(self, manifest: dict, filenames: list[str]) -> dict[str, Path]:
        manifest_bucket = str(manifest.get("bucket") or "").strip()
        if not self.bucket_name or manifest_bucket != self.bucket_name:
            raise RuntimeError("El bucket del manifiesto no coincide con el Job.")
        requested = list(dict.fromkeys([*filenames, CATALOG_STATUS_FILE]))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        client = self.client_factory()
        bucket = client.bucket(self.bucket_name)
        paths: dict[str, Path] = {}
        for filename in requested:
            local_path = self.cache_dir / filename
            paths[filename] = local_path
            item = require_manifest_object(manifest, filename)
            object_name = str(item["object"])
            generation = int(item["generation"])
            blob = bucket.blob(object_name, generation=generation)
            blob.download_to_filename(str(local_path))
            expected_size = int(item.get("size_bytes") or 0)
            if expected_size and local_path.stat().st_size != expected_size:
                raise RuntimeError(f"La descarga de {filename} no coincide con el manifiesto.")
        return paths

    @staticmethod
    def configure_catalog_environment(marts: dict[str, Path]) -> None:
        os.environ["VPO_CATALOG_MASTER_PATH"] = str(marts[CATALOG_MASTER_FILE])
        os.environ["VPO_CATALOG_STATUS_PATH"] = str(marts[CATALOG_STATUS_FILE])


def build_cloud_report_runtime() -> ReportRuntime:
    bucket_name = os.environ.get("GCS_BUCKET", "").strip()
    marts_prefix = os.environ.get("GCS_PREFIX", "marts").strip("/")
    cache_dir = Path(os.environ.get("VPO_REPORT_MARTS_DIR", "/tmp/vpo-report/marts"))
    output_dir = Path(os.environ.get("VPO_REPORT_OUTPUT_DIR", "/tmp/vpo-report/output"))
    results_prefix = os.environ.get("VPO_REPORT_RESULTS_PREFIX", "reports/jobs")
    input_store = GcsReportInputStore(
        bucket_name=bucket_name,
        marts_prefix=marts_prefix,
        cache_dir=cache_dir,
        client_factory=storage.Client,
    )
    artifact_store = GcsReportArtifactStore(
        bucket_name=bucket_name,
        results_prefix=results_prefix,
        client_factory=storage.Client,
    )
    return ReportRuntime(
        song_filename=SONG_FILE,
        standardized_filename=STANDARDIZED_FILE,
        catalog_master_filename=CATALOG_MASTER_FILE,
        output_dir=output_dir,
        resolve_marts=input_store.resolve,
        configure_catalog_environment=input_store.configure_catalog_environment,
        normalize_keywords=normalize_keywords,
        create_google_sheet=create_google_sheet,
        upload_artifact=artifact_store.upload,
        report_stage=set_report_job_stage,
    )
