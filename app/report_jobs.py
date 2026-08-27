from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime
from typing import Any

from app.operational_db import is_postgres_connection, operational_connect


_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def _db_retry(operation, attempts: int = 3):
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with operational_connect() as conn:
                ensure_report_runs_schema(conn)
                return operation(conn)
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("No se pudo acceder a la base de trabajos de reportes.")


def report_job_request_hash(output_format: str, params: dict[str, Any]) -> str:
    payload = json.dumps(
        {"output_format": output_format, "params": params},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def ensure_report_runs_schema(conn: Any) -> None:
    global _SCHEMA_READY
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        if not is_postgres_connection(conn):
            raise RuntimeError("Los trabajos de reportes requieren la base operativa Postgres.")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS report_runs (
                id bigserial PRIMARY KEY,
                report_key text,
                requested_by text,
                params_json jsonb NOT NULL DEFAULT '{}'::jsonb,
                output_uri text,
                output_format text NOT NULL DEFAULT 'excel',
                request_hash text,
                progress_stage text NOT NULL DEFAULT 'queued',
                result_filename text,
                result_content_type text,
                result_url text,
                task_name text,
                attempt_count integer NOT NULL DEFAULT 0,
                status text NOT NULL DEFAULT 'queued',
                error_message text,
                created_at timestamptz NOT NULL DEFAULT now(),
                started_at timestamptz,
                finished_at timestamptz,
                updated_at timestamptz NOT NULL DEFAULT now(),
                expires_at timestamptz NOT NULL DEFAULT (now() + interval '30 days')
            )
            """
        )
        for definition in (
            "output_format text NOT NULL DEFAULT 'excel'",
            "request_hash text",
            "progress_stage text NOT NULL DEFAULT 'queued'",
            "result_filename text",
            "result_content_type text",
            "result_url text",
            "task_name text",
            "attempt_count integer NOT NULL DEFAULT 0",
            "started_at timestamptz",
            "updated_at timestamptz NOT NULL DEFAULT now()",
            "expires_at timestamptz NOT NULL DEFAULT (now() + interval '30 days')",
        ):
            conn.execute(f"ALTER TABLE report_runs ADD COLUMN IF NOT EXISTS {definition}")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_report_runs_requester_time "
            "ON report_runs(requested_by, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_report_runs_active_hash "
            "ON report_runs(requested_by, request_hash, status) "
            "WHERE status IN ('queued', 'running')"
        )
        _SCHEMA_READY = True


def report_job_item(row: Any) -> dict[str, Any]:
    params = _json_value(row.get("params_json"))
    return {
        "id": int(row["id"]),
        "report_key": row.get("report_key") or "royalty_report",
        "output_format": row.get("output_format") or "excel",
        "requested_by": row.get("requested_by") or "",
        "params": params,
        "status": row.get("status") or "queued",
        "progress_stage": row.get("progress_stage") or "queued",
        "result_filename": row.get("result_filename"),
        "result_content_type": row.get("result_content_type"),
        "result_url": row.get("result_url"),
        "error_message": row.get("error_message"),
        "attempt_count": int(row.get("attempt_count") or 0),
        "created_at": str(row.get("created_at")) if row.get("created_at") else None,
        "started_at": str(row.get("started_at")) if row.get("started_at") else None,
        "finished_at": str(row.get("finished_at")) if row.get("finished_at") else None,
        "updated_at": str(row.get("updated_at")) if row.get("updated_at") else None,
        "expires_at": str(row.get("expires_at")) if row.get("expires_at") else None,
        "download_ready": bool(row.get("status") == "completed" and row.get("output_uri")),
    }


def create_or_reuse_report_job(
    *,
    requested_by: str,
    report_key: str,
    output_format: str,
    params: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    from psycopg.types.json import Jsonb

    request_hash = report_job_request_hash(output_format, params)
    with operational_connect() as conn:
        ensure_report_runs_schema(conn)
        existing = conn.execute(
            """
            SELECT *
            FROM report_runs
            WHERE lower(requested_by) = lower(%s)
              AND request_hash = %s
              AND status IN ('queued', 'running')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (requested_by, request_hash),
        ).fetchone()
        if existing is not None:
            return report_job_item(existing), False
        row = conn.execute(
            """
            INSERT INTO report_runs (
                report_key, requested_by, params_json, output_format,
                request_hash, progress_stage, status, created_at, updated_at, expires_at
            )
            VALUES (%s, %s, %s, %s, %s, 'queued', 'queued', now(), now(), now() + interval '30 days')
            RETURNING *
            """,
            (report_key, requested_by, Jsonb(params), output_format, request_hash),
        ).fetchone()
        return report_job_item(row), True


def get_report_job(job_id: int) -> dict[str, Any] | None:
    def read(conn):
        conn.execute(
            """
            UPDATE report_runs
            SET status = 'failed', progress_stage = 'failed',
                error_message = 'La ejecucion se interrumpio antes de completar el reporte.',
                finished_at = now(), updated_at = now()
            WHERE id = %s
              AND status = 'running'
              AND updated_at < now() - interval '35 minutes'
            """,
            (job_id,),
        )
        row = conn.execute("SELECT * FROM report_runs WHERE id = %s", (job_id,)).fetchone()
        return report_job_item(row) if row is not None else None
    return _db_retry(read)


def get_report_job_artifact(job_id: int) -> dict[str, Any] | None:
    def read(conn):
        row = conn.execute(
            """
            SELECT output_uri, result_filename, result_content_type, status, expires_at
            FROM report_runs
            WHERE id = %s
            """,
            (job_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    return _db_retry(read)


def list_report_jobs(requested_by: str | None, limit: int = 10) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 10), 50))
    with operational_connect() as conn:
        ensure_report_runs_schema(conn)
        if requested_by:
            rows = conn.execute(
                """
                SELECT * FROM report_runs
                WHERE lower(requested_by) = lower(%s)
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (requested_by, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM report_runs ORDER BY created_at DESC LIMIT %s",
                (safe_limit,),
            ).fetchall()
        return [report_job_item(row) for row in rows]


def set_report_job_task(job_id: int, task_name: str) -> None:
    def update(conn):
        conn.execute(
            "UPDATE report_runs SET task_name = %s, updated_at = now() WHERE id = %s",
            (task_name, job_id),
        )
    _db_retry(update)


def claim_report_job(job_id: int) -> dict[str, Any] | None:
    def claim(conn):
        row = conn.execute(
            """
            UPDATE report_runs
            SET status = 'running', progress_stage = 'preparing',
                started_at = COALESCE(started_at, now()), updated_at = now(),
                attempt_count = attempt_count + 1, error_message = NULL
            WHERE id = %s AND status = 'queued'
            RETURNING *
            """,
            (job_id,),
        ).fetchone()
        return report_job_item(row) if row is not None else None
    return _db_retry(claim)


def set_report_job_stage(job_id: int, stage: str) -> None:
    def update(conn):
        conn.execute(
            "UPDATE report_runs SET progress_stage = %s, updated_at = now() WHERE id = %s AND status = 'running'",
            (stage, job_id),
        )
    _db_retry(update)


def complete_report_job(
    job_id: int,
    *,
    output_uri: str | None,
    filename: str | None,
    content_type: str | None,
    result_url: str | None = None,
) -> None:
    def update(conn):
        conn.execute(
            """
            UPDATE report_runs
            SET status = 'completed', progress_stage = 'completed', output_uri = %s,
                result_filename = %s, result_content_type = %s, result_url = %s,
                error_message = NULL, finished_at = now(), updated_at = now()
            WHERE id = %s
            """,
            (output_uri, filename, content_type, result_url, job_id),
        )
    _db_retry(update, attempts=5)


def fail_report_job(job_id: int, error_message: str) -> None:
    clean_message = (error_message or "Error desconocido")[:2000]
    def update(conn):
        conn.execute(
            """
            UPDATE report_runs
            SET status = 'failed', progress_stage = 'failed', error_message = %s,
                finished_at = now(), updated_at = now()
            WHERE id = %s
            """,
            (clean_message, job_id),
        )
    _db_retry(update, attempts=5)


def cloud_tasks_enabled() -> bool:
    return bool(
        os.environ.get("VPO_REPORT_TASKS_PROJECT", "").strip()
        and os.environ.get("VPO_REPORT_TASKS_LOCATION", "").strip()
        and os.environ.get("VPO_REPORT_TASKS_QUEUE", "").strip()
    )


def enqueue_report_job(job_id: int, worker_url: str) -> str:
    from google.api_core.exceptions import AlreadyExists
    from google.cloud import tasks_v2
    from google.protobuf import duration_pb2

    project = os.environ.get("VPO_REPORT_TASKS_PROJECT", "").strip()
    location = os.environ.get("VPO_REPORT_TASKS_LOCATION", "").strip()
    queue = os.environ.get("VPO_REPORT_TASKS_QUEUE", "").strip()
    worker_token = os.environ.get("VPO_REPORT_WORKER_TOKEN", "").strip()
    if not project or not location or not queue or not worker_token:
        raise RuntimeError("La cola de reportes cloud no esta configurada completamente.")

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(project, location, queue)
    task_name = client.task_path(project, location, queue, f"royalty-report-{job_id}")
    task = {
        "name": task_name,
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": worker_url,
            "headers": {
                "Content-Type": "application/json",
                "X-VPO-Worker-Token": worker_token,
            },
            "body": b"{}",
        },
        "dispatch_deadline": duration_pb2.Duration(seconds=1800),
    }
    try:
        response = client.create_task(parent=parent, task=task)
        return response.name
    except AlreadyExists:
        return task_name


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
