from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


BASE = Path(__file__).resolve().parents[2]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from app.royalty_reports.contracts import (  # noqa: E402
    BuiltReport,
    ReportRequest,
    StoredArtifact,
)
from app.royalty_reports.engine import ReportEngine, ReportRuntime  # noqa: E402


def job_payload(report_key: str = "royalty_keyword", output_format: str = "excel") -> dict:
    return {
        "id": 42,
        "report_key": report_key,
        "output_format": output_format,
        "params": {
            "keywords": ["Un Boton"],
            "start_month": "2026-04",
            "end_month": "2026-06",
            "period_basis": "statement_period",
            "mode": "any",
            "raw_limit": 5000,
            "source": "FUGA",
            "account": "MAWZ",
        },
        "input_manifest": {"schema_version": 1},
        "policy_snapshot": {
            "schema_version": 1,
            "policy_version": 1,
            "entries": [{"source": "fuga", "account": "mawz"}],
        },
    }


def runtime_for(temp_dir: Path, stages: list[str], uploads: list[tuple]) -> ReportRuntime:
    marts = {
        "song.parquet": temp_dir / "song.parquet",
        "standardized.parquet": temp_dir / "standardized.parquet",
        "catalog.parquet": temp_dir / "catalog.parquet",
    }
    for path in marts.values():
        path.touch()

    def upload(job_id: int, output_path: Path, content_type: str) -> StoredArtifact:
        assert output_path.exists()
        uploads.append((job_id, output_path.name, content_type))
        return StoredArtifact(
            uri=f"gs://reports/{job_id}/{output_path.name}",
            size_bytes=output_path.stat().st_size,
            sha256="a" * 64,
        )

    return ReportRuntime(
        song_filename="song.parquet",
        standardized_filename="standardized.parquet",
        catalog_master_filename="catalog.parquet",
        output_dir=temp_dir,
        resolve_marts=lambda manifest, filenames: {name: marts[name] for name in filenames},
        configure_catalog_environment=lambda resolved: None,
        normalize_keywords=lambda values: [str(value).strip().lower() for value in values],
        create_google_sheet=lambda tables, keywords, start, end: "https://sheets.example/report",
        upload_artifact=upload,
        report_stage=lambda job_id, stage: stages.append(stage),
    )


def check_binary_report() -> None:
    stages: list[str] = []
    uploads: list[tuple] = []
    with tempfile.TemporaryDirectory() as raw_dir:
        temp_dir = Path(raw_dir)
        runtime = runtime_for(temp_dir, stages, uploads)
        artifact = temp_dir / "report.xlsx"
        artifact.write_bytes(b"report-test")

        def fake_builder(request, inputs, *, create_google_sheet):
            assert isinstance(request, ReportRequest)
            assert request.keywords == ("un boton",)
            assert request.source == "fuga"
            assert request.account == "mawz"
            assert inputs.output_dir == temp_dir
            return BuiltReport(
                output_path=artifact,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        with patch("app.royalty_reports.engine.build_registered_report", fake_builder):
            result = ReportEngine(runtime).build(job_payload())

        assert result.output_uri == "gs://reports/42/report.xlsx"
        assert result.filename == "report.xlsx"
        assert result.result_url is None
        assert result.result_size_bytes == len(b"report-test")
        assert result.result_sha256 == "a" * 64
        assert uploads == [
            (42, "report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        ]
        assert stages == ["reading_data", "building", "uploading"]
        assert not artifact.exists(), "El temporal debe eliminarse despues de publicar."


def check_google_sheet_report() -> None:
    stages: list[str] = []
    uploads: list[tuple] = []
    with tempfile.TemporaryDirectory() as raw_dir:
        runtime = runtime_for(Path(raw_dir), stages, uploads)

        def fake_builder(request, inputs, *, create_google_sheet):
            assert request.report_key == "royalty_google_sheet"
            return BuiltReport(result_url="https://sheets.example/report")

        with patch("app.royalty_reports.engine.build_registered_report", fake_builder):
            result = ReportEngine(runtime).build(
                job_payload("royalty_google_sheet", "google_sheet")
            )

        assert result.result_url == "https://sheets.example/report"
        assert result.output_uri is None
        assert uploads == []
        assert stages == ["reading_data", "building"]


def check_registry_guards() -> None:
    try:
        ReportRequest.from_job(job_payload("royalty_keyword", "executive_pdf"), keywords=["x"])
    except ValueError as exc:
        assert "no corresponde" in str(exc)
    else:
        raise AssertionError("Un report_key no puede ejecutar otro formato.")

    try:
        ReportRequest.from_job(job_payload("desconocido", "excel"), keywords=["x"])
    except ValueError as exc:
        assert "no soportado" in str(exc)
    else:
        raise AssertionError("Un builder no registrado debe rechazarse.")


def main() -> None:
    check_binary_report()
    check_google_sheet_report()
    check_registry_guards()
    print("OK: motor de reportes modular, registrado y con publicacion unica.")


if __name__ == "__main__":
    main()
