from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from app.report_jobs import (
    claim_report_job,
    complete_report_job,
    fail_report_job,
    get_report_job,
    heartbeat_report_job,
)
from app.royalty_reports.engine import ReportEngine, ReportRuntime


REPORT_HEARTBEAT_INTERVAL_SECONDS = 60.0


@contextmanager
def report_job_heartbeat(job_id: int, interval_seconds: float | None = None) -> Iterator[None]:
    stop = threading.Event()
    interval = REPORT_HEARTBEAT_INTERVAL_SECONDS if interval_seconds is None else interval_seconds

    def heartbeat_loop() -> None:
        while not stop.wait(interval):
            try:
                if not heartbeat_report_job(job_id):
                    return
            except Exception:
                logging.exception("No se pudo actualizar la actividad del reporte %s", job_id)

    thread = threading.Thread(target=heartbeat_loop, name=f"report-heartbeat-{job_id}", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=15)
        if thread.is_alive():
            logging.warning("El heartbeat del reporte %s no se detuvo a tiempo", job_id)


def execute_report_job(job_id: int, runtime: ReportRuntime) -> dict | None:
    job = claim_report_job(job_id)
    if job is None:
        return get_report_job(job_id)
    try:
        with report_job_heartbeat(job_id):
            result = ReportEngine(runtime).build(job)
        complete_report_job(
            job_id,
            output_uri=result.output_uri,
            filename=result.filename,
            content_type=result.content_type,
            result_url=result.result_url,
            result_size_bytes=result.result_size_bytes,
            result_sha256=result.result_sha256,
        )
    except Exception as exc:
        fail_report_job(job_id, str(exc))
    return get_report_job(job_id)
