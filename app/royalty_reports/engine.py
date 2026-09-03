from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.royalty_reports.builders import GoogleSheetBuilder, build_registered_report
from app.royalty_reports.contracts import (
    ReportBuildResult,
    ReportInputs,
    ReportRequest,
    StoredArtifact,
)


MartResolver = Callable[[dict, list[str]], dict[str, Path]]
StageReporter = Callable[[int, str], None]
ArtifactUploader = Callable[[int, Path, str], StoredArtifact]
CatalogEnvironmentConfigurator = Callable[[dict[str, Path]], None]
KeywordNormalizer = Callable[[list[str]], list[str]]


@dataclass(frozen=True)
class ReportRuntime:
    song_filename: str
    standardized_filename: str
    catalog_master_filename: str
    output_dir: Path
    resolve_marts: MartResolver
    configure_catalog_environment: CatalogEnvironmentConfigurator
    normalize_keywords: KeywordNormalizer
    create_google_sheet: GoogleSheetBuilder
    upload_artifact: ArtifactUploader
    report_stage: StageReporter


class ReportEngine:
    def __init__(self, runtime: ReportRuntime) -> None:
        self.runtime = runtime

    def build(self, job: dict) -> ReportBuildResult:
        params = dict(job.get("params") or {})
        normalized_keywords = self.runtime.normalize_keywords(params.get("keywords") or [])
        request = ReportRequest.from_job(job, keywords=normalized_keywords)

        self.runtime.report_stage(request.job_id, "reading_data")
        marts = self.runtime.resolve_marts(
            dict(job.get("input_manifest") or {}),
            [
                self.runtime.song_filename,
                self.runtime.standardized_filename,
                self.runtime.catalog_master_filename,
            ],
        )
        self.runtime.configure_catalog_environment(marts)
        inputs = ReportInputs(
            song_path=marts[self.runtime.song_filename],
            standardized_path=marts[self.runtime.standardized_filename],
            catalog_master_path=marts[self.runtime.catalog_master_filename],
            output_dir=self.runtime.output_dir,
        )

        policy_snapshot = dict(job.get("policy_snapshot") or {})
        if not policy_snapshot:
            raise RuntimeError("El trabajo no tiene un snapshot de policies.")
        from lib.distributor_policy_store import use_distributor_policy_snapshot

        self.runtime.report_stage(request.job_id, "building")
        with use_distributor_policy_snapshot(policy_snapshot):
            built = build_registered_report(
                request,
                inputs,
                create_google_sheet=self.runtime.create_google_sheet,
            )
        if built.result_url:
            return ReportBuildResult(None, None, None, built.result_url)
        if built.output_path is None or not built.content_type:
            raise RuntimeError("El builder no genero un artefacto valido.")

        self.runtime.report_stage(request.job_id, "uploading")
        stored = self.runtime.upload_artifact(
            request.job_id,
            built.output_path,
            built.content_type,
        )
        filename = built.output_path.name
        try:
            built.output_path.unlink(missing_ok=True)
        except OSError:
            pass
        return ReportBuildResult(
            stored.uri,
            filename,
            built.content_type,
            None,
            stored.size_bytes,
            stored.sha256,
        )
