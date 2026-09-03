from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from app.operational_db import operational_connect


def _db_retry(operation, attempts: int = 3):
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with operational_connect() as conn:
                return operation(conn)
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("No se pudo acceder a la base de trabajos de reportes.")


def report_job_request_hash(
    report_key: str,
    output_format: str,
    params: dict[str, Any],
    input_manifest: dict[str, Any],
    policy_snapshot: dict[str, Any],
) -> str:
    payload = json.dumps(
        {
            "report_key": report_key,
            "output_format": output_format,
            "params": params,
            "input_manifest": input_manifest,
            "policy_snapshot": policy_snapshot,
        },
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


def report_job_item(row: Any, *, include_execution_context: bool = False) -> dict[str, Any]:
    params = _json_value(row.get("params_json"))
    item = {
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
        "policy_version": row.get("policy_version"),
        "engine_version": row.get("engine_version"),
        "execution_name": row.get("execution_name"),
        "result_size_bytes": row.get("result_size_bytes"),
        "result_sha256": row.get("result_sha256"),
        "error_log_ref": row.get("error_log_ref"),
        "created_at": str(row.get("created_at")) if row.get("created_at") else None,
        "started_at": str(row.get("started_at")) if row.get("started_at") else None,
        "finished_at": str(row.get("finished_at")) if row.get("finished_at") else None,
        "updated_at": str(row.get("updated_at")) if row.get("updated_at") else None,
        "expires_at": str(row.get("expires_at")) if row.get("expires_at") else None,
        "lease_expires_at": str(row.get("lease_expires_at")) if row.get("lease_expires_at") else None,
        "download_ready": bool(row.get("status") == "completed" and row.get("output_uri")),
    }
    if include_execution_context:
        item["input_manifest"] = _json_value(row.get("input_manifest_json"))
        item["policy_snapshot"] = _json_value(row.get("policy_snapshot_json"))
    return item


def create_or_reuse_report_job(
    *,
    requested_by: str,
    report_key: str,
    output_format: str,
    params: dict[str, Any],
    input_manifest: dict[str, Any],
    policy_snapshot: dict[str, Any],
    policy_version: int,
) -> tuple[dict[str, Any], bool]:
    from psycopg.types.json import Jsonb

    request_hash = report_job_request_hash(
        report_key,
        output_format,
        params,
        input_manifest,
        policy_snapshot,
    )
    with operational_connect() as conn:
        row = conn.execute(
            """
            INSERT INTO report_runs (
                report_key, requested_by, params_json, output_format,
                request_hash, input_manifest_json, policy_snapshot_json,
                policy_version, progress_stage, status, created_at, updated_at, expires_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                'queued', 'queued', now(), now(), now() + interval '30 days'
            )
            ON CONFLICT (lower(requested_by), request_hash)
                WHERE status IN ('queued', 'running') AND request_hash IS NOT NULL
                DO NOTHING
            RETURNING *
            """,
            (
                report_key,
                requested_by,
                Jsonb(params),
                output_format,
                request_hash,
                Jsonb(input_manifest),
                Jsonb(policy_snapshot),
                policy_version,
            ),
        ).fetchone()
        if row is not None:
            return report_job_item(row), True
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
        if existing is None:
            raise RuntimeError("No se pudo recuperar el trabajo de reporte activo.")
        return report_job_item(existing), False


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


def set_report_job_execution(
    job_id: int,
    execution_name: str,
    *,
    engine_version: str | None = None,
) -> None:
    def update(conn):
        conn.execute(
            """
            UPDATE report_runs
            SET execution_name = %s,
                engine_version = COALESCE(%s, engine_version),
                updated_at = now()
            WHERE id = %s
            """,
            (execution_name, engine_version, job_id),
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
        return (
            report_job_item(row, include_execution_context=True)
            if row is not None
            else None
        )
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
    result_size_bytes: int | None = None,
    result_sha256: str | None = None,
) -> None:
    def update(conn):
        conn.execute(
            """
            UPDATE report_runs
            SET status = 'completed', progress_stage = 'completed', output_uri = %s,
                result_filename = %s, result_content_type = %s, result_url = %s,
                result_size_bytes = %s, result_sha256 = %s,
                error_message = NULL, finished_at = now(), updated_at = now()
            WHERE id = %s
            """,
            (
                output_uri,
                filename,
                content_type,
                result_url,
                result_size_bytes,
                result_sha256,
                job_id,
            ),
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
