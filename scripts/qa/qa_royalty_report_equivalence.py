from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path


BASE = Path(__file__).resolve().parents[2]
SCRIPTS = BASE / "scripts"
for path in (BASE, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.royalty_reports.contracts import ReportRequest  # noqa: E402
from app.royalty_reports.contracts import StoredArtifact  # noqa: E402
from app.royalty_reports.engine import ReportEngine, ReportRuntime  # noqa: E402
from build_keyword_royalty_report import build_report, normalize_keywords  # noqa: E402
from qa_royalty_report_witness import read_job, workbook_signature  # noqa: E402
from lib.distributor_policy_store import load_distributor_policy_document  # noqa: E402


SONG_FILE = "song_level_all_sources.parquet"
STANDARDIZED_FILE = "standardized_raw_all_sources.parquet"
CATALOG_MASTER_FILE = "catalog_master.parquet"


def signatures_equivalent(
    expected: dict,
    actual: dict,
    *,
    width_tolerance: float,
) -> bool:
    expected_sheets = expected.get("sheets", [])
    actual_sheets = actual.get("sheets", [])
    if len(expected_sheets) != len(actual_sheets):
        return False
    for expected_sheet, actual_sheet in zip(
        expected_sheets, actual_sheets, strict=True
    ):
        for key in (
            "title",
            "state",
            "max_row",
            "max_column",
            "freeze_panes",
            "auto_filter",
            "merged",
            "cells",
        ):
            if expected_sheet[key] != actual_sheet[key]:
                return False
        expected_widths = expected_sheet["widths"]
        actual_widths = actual_sheet["widths"]
        if expected_widths.keys() != actual_widths.keys():
            return False
        if any(
            abs(expected_widths[key] - actual_widths[key]) > width_tolerance
            for key in expected_widths
        ):
            return False
    return True


def first_signature_difference(
    expected: dict,
    actual: dict,
    *,
    width_tolerance: float,
) -> str:
    expected_sheets = expected.get("sheets", [])
    actual_sheets = actual.get("sheets", [])
    if len(expected_sheets) != len(actual_sheets):
        return f"cantidad de hojas: {len(expected_sheets)} != {len(actual_sheets)}"
    for sheet_index, (expected_sheet, actual_sheet) in enumerate(
        zip(expected_sheets, actual_sheets, strict=True)
    ):
        for key in (
            "title",
            "state",
            "max_row",
            "max_column",
            "freeze_panes",
            "auto_filter",
            "merged",
        ):
            if expected_sheet[key] != actual_sheet[key]:
                return (
                    f"hoja {sheet_index + 1} ({expected_sheet['title']}), {key}: "
                    f"{expected_sheet[key]!r} != {actual_sheet[key]!r}"
                )
        expected_widths = expected_sheet["widths"]
        actual_widths = actual_sheet["widths"]
        if expected_widths.keys() != actual_widths.keys():
            return (
                f"hoja {sheet_index + 1} ({expected_sheet['title']}), columnas con ancho: "
                f"{expected_widths.keys()!r} != {actual_widths.keys()!r}"
            )
        for key in expected_widths:
            if abs(expected_widths[key] - actual_widths[key]) > width_tolerance:
                return (
                    f"hoja {sheet_index + 1} ({expected_sheet['title']}), ancho {key}: "
                    f"{expected_widths[key]!r} != {actual_widths[key]!r}"
                )
        for row_index, (expected_row, actual_row) in enumerate(
            zip(expected_sheet["cells"], actual_sheet["cells"], strict=True),
            start=1,
        ):
            for column_index, (expected_cell, actual_cell) in enumerate(
                zip(expected_row, actual_row, strict=True),
                start=1,
            ):
                if expected_cell != actual_cell:
                    return (
                        f"hoja {expected_sheet['title']}, fila {row_index}, "
                        f"columna {column_index}: {expected_cell!r} != {actual_cell!r}"
                    )
    return "las firmas difieren sin una diferencia localizada"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", type=int, required=True)
    args = parser.parse_args()

    mart_dir = Path(os.environ.get("VPO_LOCAL_MARTS_DIR") or BASE / "warehouse" / "marts")
    catalog_status = BASE / "warehouse" / "registry" / "catalog_status.parquet"
    job = read_job(args.job_id)
    job["policy_snapshot"] = load_distributor_policy_document()
    request = ReportRequest.from_job(
        job,
        keywords=normalize_keywords((job.get("params") or {}).get("keywords") or []),
    )
    if request.report_key != "royalty_keyword" or request.output_format != "excel":
        raise RuntimeError("Este QA compara reportes de regalias Excel.")

    marts = {
        name: mart_dir / name
        for name in (SONG_FILE, STANDARDIZED_FILE, CATALOG_MASTER_FILE)
    }
    missing = [str(path) for path in marts.values() if not path.exists()]
    if missing:
        raise RuntimeError(f"Faltan marts para QA: {', '.join(missing)}")

    os.environ["VPO_CATALOG_MASTER_PATH"] = str(marts[CATALOG_MASTER_FILE])
    os.environ["VPO_CATALOG_STATUS_PATH"] = str(catalog_status)

    with tempfile.TemporaryDirectory(prefix="vpo-report-equivalence-") as raw_dir:
        root = Path(raw_dir)
        expected_dir = root / "previous"
        actual_dir = root / "modular"
        expected_dir.mkdir()
        actual_dir.mkdir()

        expected_path = Path(
            build_report(
                keywords=list(request.keywords),
                mode=request.mode,
                raw_limit=request.raw_limit,
                start_month=request.start_month,
                end_month=request.end_month,
                period_basis=request.period_basis,
                song_path=marts[SONG_FILE],
                standardized_path=marts[STANDARDIZED_FILE],
                output_dir=expected_dir,
            )
        )
        expected_signature = workbook_signature(
            expected_path,
            ignore_generated_at=True,
            float_decimals=10,
        )
        comparison: dict[str, bool] = {}

        def resolve_marts(manifest: dict, filenames: list[str]) -> dict[str, Path]:
            return {name: marts[name] for name in filenames}

        def configure_catalog(resolved: dict[str, Path]) -> None:
            os.environ["VPO_CATALOG_MASTER_PATH"] = str(resolved[CATALOG_MASTER_FILE])
            os.environ["VPO_CATALOG_STATUS_PATH"] = str(catalog_status)

        def compare_artifact(
            job_id: int,
            generated: Path,
            content_type: str,
        ) -> StoredArtifact:
            actual_signature = workbook_signature(
                generated,
                ignore_generated_at=True,
                float_decimals=10,
            )
            comparison["equal"] = signatures_equivalent(
                expected_signature,
                actual_signature,
                width_tolerance=1.0,
            )
            if not comparison["equal"]:
                print(
                    "Primera diferencia: "
                    + first_signature_difference(
                        expected_signature,
                        actual_signature,
                        width_tolerance=1.0,
                    ),
                    flush=True,
                )
                raise AssertionError(
                    f"El motor modular no coincide con el camino anterior para job {job_id}."
                )
            return StoredArtifact(
                uri=f"qa://report/{job_id}/{generated.name}",
                size_bytes=generated.stat().st_size,
                sha256="0" * 64,
            )

        runtime = ReportRuntime(
            song_filename=SONG_FILE,
            standardized_filename=STANDARDIZED_FILE,
            catalog_master_filename=CATALOG_MASTER_FILE,
            output_dir=actual_dir,
            resolve_marts=resolve_marts,
            configure_catalog_environment=configure_catalog,
            normalize_keywords=normalize_keywords,
            create_google_sheet=lambda *values: (_ for _ in ()).throw(
                RuntimeError("Este QA valida artefactos Excel.")
            ),
            upload_artifact=compare_artifact,
            report_stage=lambda job_id, stage: print(
                f"job={job_id} stage={stage}", flush=True
            ),
        )
        result = ReportEngine(runtime).build(job)
        if not comparison.get("equal"):
            raise AssertionError("No se comparo el artefacto generado.")
        print(
            f"OK: job {args.job_id}; motor anterior y modular coinciden "
            "en datos, estructura y estilos."
        )
        print(f"Resultado QA: {result.output_uri}")


if __name__ == "__main__":
    main()
