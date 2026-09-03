from __future__ import annotations

from app.report_jobs import (
    claim_report_job,
    complete_report_job,
    fail_report_job,
    get_report_job,
)
from app.royalty_reports.engine import ReportEngine, ReportRuntime


def execute_report_job(job_id: int, runtime: ReportRuntime) -> dict | None:
    job = claim_report_job(job_id)
    if job is None:
        return get_report_job(job_id)
    try:
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
