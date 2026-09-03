from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


ReportOutputFormat = Literal["excel", "executive_pdf", "google_sheet"]

REPORT_FORMAT_BY_KEY: dict[str, ReportOutputFormat] = {
    "royalty_keyword": "excel",
    "royalty_executive": "executive_pdf",
    "royalty_google_sheet": "google_sheet",
}


@dataclass(frozen=True)
class ReportRequest:
    job_id: int
    report_key: str
    output_format: ReportOutputFormat
    keywords: tuple[str, ...]
    start_month: str | None
    end_month: str | None
    period_basis: str
    mode: str
    raw_limit: int
    source: str | None
    account: str | None

    @classmethod
    def from_job(cls, job: dict[str, Any], *, keywords: list[str]) -> "ReportRequest":
        params = dict(job.get("params") or {})
        report_key = str(job.get("report_key") or "").strip()
        output_format = str(job.get("output_format") or "").strip()
        expected_format = REPORT_FORMAT_BY_KEY.get(report_key)
        if expected_format is None:
            raise ValueError(f"Tipo de reporte no soportado: {report_key or 'sin tipo'}.")
        if output_format != expected_format:
            raise ValueError(
                f"El formato {output_format or 'vacio'} no corresponde al reporte {report_key}."
            )

        start_month = params.get("start_month") or None
        end_month = params.get("end_month") or None
        if start_month and end_month and start_month > end_month:
            raise ValueError("El periodo desde no puede ser mayor que hasta.")
        if output_format in {"excel", "google_sheet"} and not keywords:
            raise ValueError("El reporte requiere al menos una palabra clave.")

        return cls(
            job_id=int(job["id"]),
            report_key=report_key,
            output_format=expected_format,
            keywords=tuple(keywords),
            start_month=start_month,
            end_month=end_month,
            period_basis=str(params.get("period_basis") or "transaction_month"),
            mode=str(params.get("mode") or "any"),
            raw_limit=max(0, min(int(params.get("raw_limit") or 0), 50000)),
            source=(str(params.get("source") or "").strip().lower() or None),
            account=(str(params.get("account") or "").strip().lower() or None),
        )


@dataclass(frozen=True)
class ReportInputs:
    song_path: Path
    standardized_path: Path
    catalog_master_path: Path
    output_dir: Path


@dataclass(frozen=True)
class BuiltReport:
    output_path: Path | None = None
    content_type: str | None = None
    result_url: str | None = None


@dataclass(frozen=True)
class StoredArtifact:
    uri: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ReportBuildResult:
    output_uri: str | None
    filename: str | None
    content_type: str | None
    result_url: str | None
    result_size_bytes: int | None = None
    result_sha256: str | None = None
