from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import google.auth
from google.auth.transport.requests import AuthorizedSession

from app.report_jobs import fail_interrupted_report_job, get_report_job


IDLE_BEFORE_CHECK = timedelta(minutes=5)
TERMINAL_GRACE = timedelta(minutes=2)


@dataclass(frozen=True)
class ExecutionOutcome:
    succeeded: bool
    completed_at: datetime | None
    message: str = ""


@dataclass(frozen=True)
class CloudRunReportExecutionReader:
    project: str
    location: str
    job_name: str
    credentials_provider: Callable = google.auth.default
    session_factory: Callable = AuthorizedSession

    @classmethod
    def from_environment(cls) -> CloudRunReportExecutionReader:
        project = os.environ.get("VPO_REPORT_JOB_PROJECT", "").strip()
        location = os.environ.get("VPO_REPORT_JOB_LOCATION", "").strip()
        job_name = os.environ.get("VPO_REPORT_JOB_NAME", "").strip()
        if not project or not location or not job_name:
            raise RuntimeError("El Cloud Run Job de reportes no esta configurado.")
        return cls(project, location, job_name)

    def inspect(self, execution_name: str) -> ExecutionOutcome | None:
        credentials, _ = self.credentials_provider(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        session = self.session_factory(credentials)
        operation_prefix = f"projects/{self.project}/locations/{self.location}/operations/"
        if execution_name.startswith(operation_prefix):
            if not re.fullmatch(r"[a-zA-Z0-9-]+", execution_name[len(operation_prefix):]):
                raise ValueError("Nombre de operacion de reporte invalido.")
            operation = self._get(session, execution_name)
            if not operation.get("done"):
                return None
            error = operation.get("error") or {}
            if error:
                return ExecutionOutcome(False, None, str(error.get("message") or ""))
            execution_name = str((operation.get("response") or {}).get("name") or "")

        execution_prefix = (
            f"projects/{self.project}/locations/{self.location}/jobs/"
            f"{self.job_name}/executions/"
        )
        if execution_name.startswith(execution_prefix):
            short_name = execution_name[len(execution_prefix):]
        else:
            short_name = execution_name
        if not re.fullmatch(re.escape(self.job_name) + r"-[a-z0-9]+", short_name):
            raise ValueError("Nombre de ejecucion de reporte invalido.")

        execution = self._get(session, execution_prefix + short_name)
        completed_at = _parse_time(execution.get("completionTime"))
        if completed_at is None:
            return None
        completed = next(
            (item for item in execution.get("conditions") or [] if item.get("type") == "Completed"),
            {},
        )
        state = completed.get("state")
        if int(execution.get("failedCount") or 0) or int(execution.get("cancelledCount") or 0) or state == "CONDITION_FAILED":
            return ExecutionOutcome(False, completed_at, str(completed.get("message") or ""))
        if state == "CONDITION_SUCCEEDED" and int(execution.get("succeededCount") or 0) >= int(execution.get("taskCount") or 1):
            return ExecutionOutcome(True, completed_at)
        return None

    @staticmethod
    def _get(session: Any, resource: str) -> dict[str, Any]:
        response = session.get(f"https://run.googleapis.com/v2/{resource}", timeout=5)
        response.raise_for_status()
        return response.json()


def _parse_time(raw: Any) -> datetime | None:
    if not raw:
        return None
    parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def reconcile_report_job_if_stale(
    job: dict[str, Any],
    *,
    reader: CloudRunReportExecutionReader | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    status = str(job.get("status") or "")
    execution_name = str(job.get("execution_name") or "")
    updated_at = str(job.get("updated_at") or "")
    current_time = now or datetime.now(timezone.utc)
    last_activity = _parse_time(updated_at)
    if status not in {"queued", "running"} or not execution_name or last_activity is None:
        return job
    if current_time - last_activity < IDLE_BEFORE_CHECK:
        return job

    try:
        outcome = (reader or CloudRunReportExecutionReader.from_environment()).inspect(execution_name)
    except Exception:
        logging.exception("No se pudo verificar la ejecucion de Cloud Run del reporte %s", job["id"])
        return job
    if outcome is None:
        return job
    if outcome.completed_at is not None and current_time - outcome.completed_at < TERMINAL_GRACE:
        return job

    if outcome.succeeded:
        message = "Cloud Run termino el reporte, pero no quedo un resultado registrado."
    else:
        detail = outcome.message.strip()[:500]
        if "memory limit" in detail.lower():
            message = "El informe supero la memoria disponible durante la generacion."
        else:
            message = "Cloud Run termino la ejecucion sin completar el reporte."
            if detail:
                message += f" Motivo: {detail}"
    fail_interrupted_report_job(
        int(job["id"]),
        expected_status=status,
        expected_execution_name=execution_name,
        expected_updated_at=updated_at,
        error_message=message,
    )
    return get_report_job(int(job["id"])) or job
