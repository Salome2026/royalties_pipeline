from __future__ import annotations

import sys
from pathlib import Path


BASE = Path(__file__).resolve().parents[2]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from app.operational_db import operational_connect  # noqa: E402


EXPECTED_COLUMNS = {
    "input_manifest_json",
    "policy_snapshot_json",
    "policy_version",
    "engine_version",
    "execution_name",
    "result_size_bytes",
    "result_sha256",
    "error_log_ref",
    "lease_expires_at",
}

EXPECTED_CONSTRAINTS = {
    "report_runs_output_chk",
    "report_runs_status_chk",
    "report_runs_stage_chk",
    "report_runs_report_key_chk",
    "report_runs_requested_by_chk",
    "report_runs_params_json_chk",
    "report_runs_input_manifest_chk",
    "report_runs_policy_snapshot_chk",
    "report_runs_policy_version_chk",
    "report_runs_attempt_count_chk",
    "report_runs_result_size_chk",
    "report_runs_result_sha256_chk",
    "report_runs_request_hash_chk",
    "report_runs_running_started_chk",
    "report_runs_terminal_finished_chk",
    "report_runs_completed_result_chk",
    "report_runs_active_context_chk",
}


def main() -> None:
    report_jobs_source = (BASE / "app" / "report_jobs.py").read_text(encoding="utf-8")
    forbidden_runtime_ddl = ("CREATE TABLE", "ALTER TABLE", "CREATE INDEX")
    found = [token for token in forbidden_runtime_ddl if token in report_jobs_source.upper()]
    if found:
        raise AssertionError(f"DDL encontrado en runtime: {', '.join(found)}")

    with operational_connect() as conn:
        columns = {
            row["column_name"]: row
            for row in conn.execute(
                """
                SELECT column_name, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'report_runs'
                """
            ).fetchall()
        }
        constraints = {
            row["conname"]
            for row in conn.execute(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'public.report_runs'::regclass
                """
            ).fetchall()
        }
        indexes = {
            row["indexname"]: row["indexdef"]
            for row in conn.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = 'report_runs'
                """
            ).fetchall()
        }
        migration = conn.execute(
            """
            SELECT version
            FROM schema_migrations
            WHERE version = '011_report_runs_definitive_contract'
            """
        ).fetchone()
        cutover_migration = conn.execute(
            """
            SELECT version
            FROM schema_migrations
            WHERE version = '012_cloud_run_report_job_cutover'
            """
        ).fetchone()
        invalid_rows = conn.execute(
            """
            SELECT count(*) AS total
            FROM report_runs
            WHERE report_key IS NULL
               OR requested_by IS NULL
               OR status NOT IN ('queued', 'running', 'completed', 'failed')
               OR progress_stage NOT IN (
                   'queued', 'preparing', 'reading_data', 'building', 'uploading',
                   'completed', 'failed'
               )
            """
        ).fetchone()

    missing_columns = sorted(EXPECTED_COLUMNS - columns.keys())
    if missing_columns:
        raise AssertionError(f"Faltan columnas: {', '.join(missing_columns)}")
    missing_constraints = sorted(EXPECTED_CONSTRAINTS - constraints)
    if missing_constraints:
        raise AssertionError(f"Faltan constraints: {', '.join(missing_constraints)}")
    if columns["report_key"]["is_nullable"] != "NO":
        raise AssertionError("report_key debe ser NOT NULL.")
    if columns["requested_by"]["is_nullable"] != "NO":
        raise AssertionError("requested_by debe ser NOT NULL.")
    if "UNIQUE INDEX" not in indexes.get("idx_report_runs_active_hash", ""):
        raise AssertionError("El indice activo de idempotencia debe ser unico.")
    if "idx_report_runs_status_updated" not in indexes:
        raise AssertionError("Falta el indice operativo por estado y actividad.")
    if migration is None:
        raise AssertionError("La migracion 011 no figura aplicada.")
    if cutover_migration is None:
        raise AssertionError("La migracion 012 no figura aplicada.")
    if "task_name" in columns:
        raise AssertionError("task_name pertenece al transporte retirado de Cloud Tasks.")
    if int(invalid_rows["total"] or 0) != 0:
        raise AssertionError("Existen trabajos incompatibles con el contrato definitivo.")

    print(
        "OK: report_runs es propiedad de migraciones y cumple el contrato definitivo."
    )


if __name__ == "__main__":
    main()
