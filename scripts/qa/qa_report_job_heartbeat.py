from __future__ import annotations

import sys
import threading
from pathlib import Path
from unittest.mock import patch


BASE = Path(__file__).resolve().parents[2]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from app import report_jobs  # noqa: E402
from app.royalty_reports import execution  # noqa: E402


def check_status_read_has_no_side_effect() -> None:
    queries: list[str] = []

    class Cursor:
        def fetchone(self):
            return {"id": 42, "status": "running", "updated_at": "old timestamp"}

    class Connection:
        def execute(self, query, params):
            assert params == (42,)
            queries.append(query)
            return Cursor()

    with patch.object(report_jobs, "_db_retry", side_effect=lambda operation: operation(Connection())):
        item = report_jobs.get_report_job(42)

    assert item is not None and item["status"] == "running"
    assert len(queries) == 1 and queries[0].strip().startswith("SELECT")


def check_heartbeat_updates_only_running_job() -> None:
    queries: list[str] = []

    class Cursor:
        rowcount = 1

    class Connection:
        def execute(self, query, params):
            assert params == (42,)
            queries.append(query)
            return Cursor()

    with patch.object(
        report_jobs,
        "_db_retry",
        side_effect=lambda operation, attempts: operation(Connection()),
    ):
        assert report_jobs.heartbeat_report_job(42)

    assert len(queries) == 1
    assert "status = 'running'" in queries[0]
    assert "updated_at = now()" in queries[0]


def check_long_report_stays_active_and_stops_on_completion() -> None:
    activity = threading.Event()
    calls: list[tuple] = []

    class FakeEngine:
        def __init__(self, runtime):
            pass

        def build(self, job):
            assert job == {"id": 42}
            assert activity.wait(2), "El trabajo largo no recibio heartbeat."
            result = type("Result", (), {})()
            result.output_uri = "gs://bucket/report.xlsx"
            result.filename = "report.xlsx"
            result.content_type = "application/octet-stream"
            result.result_url = None
            result.result_size_bytes = 10
            result.result_sha256 = "a" * 64
            return result

    def heartbeat(job_id):
        calls.append(("heartbeat", job_id))
        activity.set()
        return True

    def complete(job_id, **kwargs):
        assert activity.is_set()
        calls.append(("complete", job_id))

    with patch.object(execution, "claim_report_job", return_value={"id": 42}), \
         patch.object(execution, "get_report_job", return_value={"id": 42, "status": "completed"}), \
         patch.object(execution, "heartbeat_report_job", side_effect=heartbeat), \
         patch.object(execution, "complete_report_job", side_effect=complete), \
         patch.object(execution, "fail_report_job") as failed, \
         patch.object(execution, "ReportEngine", FakeEngine), \
         patch.object(execution, "REPORT_HEARTBEAT_INTERVAL_SECONDS", 0.01):
        item = execution.execute_report_job(42, None)

    assert item == {"id": 42, "status": "completed"}
    assert calls[0] == ("heartbeat", 42)
    assert calls[-1] == ("complete", 42)
    failed.assert_not_called()


def check_heartbeat_stops_on_builder_failure() -> None:
    class FakeEngine:
        def __init__(self, runtime):
            pass

        def build(self, job):
            raise RuntimeError("builder fallo")

    with patch.object(execution, "claim_report_job", return_value={"id": 42}), \
         patch.object(execution, "get_report_job", return_value={"id": 42, "status": "failed"}), \
         patch.object(execution, "heartbeat_report_job") as heartbeat, \
         patch.object(execution, "complete_report_job") as complete, \
         patch.object(execution, "fail_report_job") as fail, \
         patch.object(execution, "ReportEngine", FakeEngine), \
         patch.object(execution, "REPORT_HEARTBEAT_INTERVAL_SECONDS", 0.01):
        item = execution.execute_report_job(42, None)

    assert item == {"id": 42, "status": "failed"}
    heartbeat.assert_not_called()
    complete.assert_not_called()
    fail.assert_called_once_with(42, "builder fallo")


def check_transient_heartbeat_error_does_not_fail_report() -> None:
    activity = threading.Event()

    class FakeEngine:
        def __init__(self, runtime):
            pass

        def build(self, job):
            assert activity.wait(2)
            result = type("Result", (), {})()
            result.output_uri = "gs://bucket/report.xlsx"
            result.filename = "report.xlsx"
            result.content_type = "application/octet-stream"
            result.result_url = None
            result.result_size_bytes = 10
            result.result_sha256 = "a" * 64
            return result

    attempts = 0

    def heartbeat(job_id):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("conexion temporalmente caida")
        activity.set()
        return True

    with patch.object(execution, "claim_report_job", return_value={"id": 42}), \
         patch.object(execution, "get_report_job", return_value={"id": 42, "status": "completed"}), \
         patch.object(execution, "heartbeat_report_job", side_effect=heartbeat), \
         patch.object(execution, "complete_report_job") as complete, \
         patch.object(execution, "fail_report_job") as fail, \
         patch.object(execution, "ReportEngine", FakeEngine), \
         patch.object(execution, "REPORT_HEARTBEAT_INTERVAL_SECONDS", 0.01), \
         patch.object(execution.logging, "exception") as logged:
        execution.execute_report_job(42, None)

    assert attempts >= 2
    logged.assert_called_once()
    complete.assert_called_once()
    fail.assert_not_called()


def main() -> None:
    check_status_read_has_no_side_effect()
    check_heartbeat_updates_only_running_job()
    check_long_report_stays_active_and_stops_on_completion()
    check_heartbeat_stops_on_builder_failure()
    check_transient_heartbeat_error_does_not_fail_report()
    print("OK: consulta sin mutaciones y heartbeat durante la ejecucion de reportes.")


if __name__ == "__main__":
    main()
