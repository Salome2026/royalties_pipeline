from __future__ import annotations

import os
import sys
from dataclasses import replace

from app.operational_db import close_operational_db_pool
from app.report_jobs import set_report_job_execution
from app.royalty_reports.cloud_runtime import build_cloud_report_runtime
from app.royalty_reports.execution import CloudReportAttempt, execute_report_job


def report_run_id() -> int:
    raw_value = os.environ.get("VPO_REPORT_RUN_ID", "").strip()
    if not raw_value:
        raise RuntimeError("VPO_REPORT_RUN_ID es obligatorio.")
    value = int(raw_value)
    if value <= 0:
        raise RuntimeError("VPO_REPORT_RUN_ID debe ser positivo.")
    return value


def main(*, pinned_builder=None, max_cloud_retries: int | None = None) -> None:
    if pinned_builder is None:
        from app.royalty_reports.bigquery_backend import deployment

        if deployment.configured():
            pinned_builder = deployment.build_pinned
            if max_cloud_retries is None and "VPO_REPORT_JOB_MAX_RETRIES" in os.environ:
                max_cloud_retries = int(os.environ["VPO_REPORT_JOB_MAX_RETRIES"])
    job_id = report_run_id()
    execution_name = os.environ.get("CLOUD_RUN_EXECUTION", "").strip()
    cloud_attempt = None
    if max_cloud_retries is not None:
        attempt_index = int(os.environ["CLOUD_RUN_TASK_ATTEMPT"])
        if not execution_name or not 0 <= attempt_index <= max_cloud_retries:
            raise RuntimeError("Falta el contexto de reintento del Cloud Run Job.")
        cloud_attempt = CloudReportAttempt(execution_name, attempt_index, max_cloud_retries)
    elif execution_name:
        set_report_job_execution(
            job_id,
            execution_name,
            engine_version=os.environ.get("VPO_ENGINE_VERSION", "").strip() or None,
        )
    runtime = build_cloud_report_runtime()
    if pinned_builder is not None:
        runtime = replace(runtime, build_pinned=pinned_builder)
    item = execute_report_job(job_id, runtime, cloud_attempt=cloud_attempt)
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
    finally:
        close_operational_db_pool()
