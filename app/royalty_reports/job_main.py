from __future__ import annotations

import os
import sys

from app.report_jobs import set_report_job_execution
from app.royalty_reports.cloud_runtime import build_cloud_report_runtime
from app.royalty_reports.execution import execute_report_job


def report_run_id() -> int:
    raw_value = os.environ.get("VPO_REPORT_RUN_ID", "").strip()
    if not raw_value:
        raise RuntimeError("VPO_REPORT_RUN_ID es obligatorio.")
    value = int(raw_value)
    if value <= 0:
        raise RuntimeError("VPO_REPORT_RUN_ID debe ser positivo.")
    return value


def main() -> None:
    job_id = report_run_id()
    execution_name = os.environ.get("CLOUD_RUN_EXECUTION", "").strip()
    if execution_name:
        set_report_job_execution(
            job_id,
            execution_name,
            engine_version=os.environ.get("VPO_ENGINE_VERSION", "").strip() or None,
        )
    item = execute_report_job(job_id, build_cloud_report_runtime())
    if item is None:
        raise RuntimeError(f"No existe report_run {job_id}.")
    status = str(item.get("status") or "")
    if status != "completed":
        detail = str(item.get("error_message") or "El reporte no finalizo correctamente.")
        raise RuntimeError(f"report_run {job_id} termino en {status}: {detail}")
    print(f"report_run {job_id} completado.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        raise
