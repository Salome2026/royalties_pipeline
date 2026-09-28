from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


BASE = Path(__file__).resolve().parents[2]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from app import report_jobs  # noqa: E402
from app.royalty_reports import reconciliation  # noqa: E402


NOW = datetime(2026, 9, 28, 14, 30, tzinfo=timezone.utc)
EXECUTION = "vpo-royalty-report-job-4nhgr"
OPERATION = "projects/project/locations/us-central1/operations/1234-abcd"


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, url, timeout):
        assert timeout == 5
        self.calls.append(url)
        return FakeResponse(self.payloads[url.rsplit("/", 1)[-1]])


def reader_for(payloads):
    session = FakeSession(payloads)
    reader = reconciliation.CloudRunReportExecutionReader(
        "project",
        "us-central1",
        "vpo-royalty-report-job",
        credentials_provider=lambda **kwargs: (object(), None),
        session_factory=lambda credentials: session,
    )
    return reader, session


def check_cloud_run_states() -> None:
    reader, session = reader_for({"1234-abcd": {"done": False}})
    assert reader.inspect(OPERATION) is None
    assert len(session.calls) == 1

    reader, _ = reader_for({"1234-abcd": {"done": True, "error": {"message": "launch failed"}}})
    result = reader.inspect(OPERATION)
    assert result is not None and not result.succeeded and result.message == "launch failed"

    reader, session = reader_for({
        "1234-abcd": {
            "done": True,
            "response": {
                "name": "projects/project/locations/us-central1/jobs/"
                "vpo-royalty-report-job/executions/" + EXECUTION
            },
        },
        EXECUTION: {
            "completionTime": NOW.isoformat(),
            "taskCount": 1,
            "succeededCount": 1,
            "conditions": [{"type": "Completed", "state": "CONDITION_SUCCEEDED"}],
        },
    })
    result = reader.inspect(OPERATION)
    assert result is not None and result.succeeded and result.completed_at == NOW
    assert len(session.calls) == 2

    reader, _ = reader_for({EXECUTION: {"runningCount": 1}})
    assert reader.inspect(EXECUTION) is None

    reader, _ = reader_for({EXECUTION: {
        "completionTime": NOW.isoformat(),
        "failedCount": 1,
        "conditions": [{"type": "Completed", "state": "CONDITION_FAILED", "message": "memory limit"}],
    }})
    result = reader.inspect(EXECUTION)
    assert result is not None and not result.succeeded and result.message == "memory limit"

    try:
        reader.inspect("projects/other/locations/us-central1/operations/xyz")
    except ValueError:
        pass
    else:
        raise AssertionError("No debe consultarse un recurso de otro proyecto.")


def job_at(minutes_idle: int) -> dict:
    return {
        "id": 42,
        "status": "running",
        "execution_name": EXECUTION,
        "updated_at": (NOW - timedelta(minutes=minutes_idle)).isoformat(),
    }


class OutcomeReader:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def inspect(self, name):
        self.calls.append(name)
        return self.outcome


def check_reconciliation_guards() -> None:
    failed = reconciliation.ExecutionOutcome(False, NOW - timedelta(minutes=3), "memory limit")
    reader = OutcomeReader(failed)
    with patch.object(reconciliation, "fail_interrupted_report_job") as mark:
        assert reconciliation.reconcile_report_job_if_stale(job_at(4), reader=reader, now=NOW) == job_at(4)
        mark.assert_not_called()
    assert not reader.calls

    reader = OutcomeReader(None)
    with patch.object(reconciliation, "fail_interrupted_report_job") as mark:
        assert reconciliation.reconcile_report_job_if_stale(job_at(10), reader=reader, now=NOW) == job_at(10)
        mark.assert_not_called()

    reader = OutcomeReader(reconciliation.ExecutionOutcome(False, NOW - timedelta(minutes=1), "memory limit"))
    with patch.object(reconciliation, "fail_interrupted_report_job") as mark:
        assert reconciliation.reconcile_report_job_if_stale(job_at(10), reader=reader, now=NOW) == job_at(10)
        mark.assert_not_called()

    reader = OutcomeReader(failed)
    latest = {"id": 42, "status": "completed"}
    with patch.object(reconciliation, "fail_interrupted_report_job", return_value=False) as mark, \
         patch.object(reconciliation, "get_report_job", return_value=latest):
        assert reconciliation.reconcile_report_job_if_stale(job_at(10), reader=reader, now=NOW) == latest
    assert mark.call_args.kwargs["expected_updated_at"] == job_at(10)["updated_at"]
    assert "memoria disponible" in mark.call_args.kwargs["error_message"]

    reader = OutcomeReader(reconciliation.ExecutionOutcome(True, NOW - timedelta(minutes=3)))
    with patch.object(reconciliation, "fail_interrupted_report_job", return_value=True) as mark, \
         patch.object(reconciliation, "get_report_job", return_value={"id": 42, "status": "failed"}):
        reconciliation.reconcile_report_job_if_stale(job_at(10), reader=reader, now=NOW)
    assert "no quedo un resultado registrado" in mark.call_args.kwargs["error_message"]


def check_compare_and_swap_sql() -> None:
    queries = []

    class Cursor:
        rowcount = 0

    class Connection:
        def execute(self, query, params):
            queries.append((query, params))
            return Cursor()

    with patch.object(report_jobs, "_db_retry", side_effect=lambda operation: operation(Connection())):
        changed = report_jobs.fail_interrupted_report_job(
            42,
            expected_status="running",
            expected_execution_name=EXECUTION,
            expected_updated_at=job_at(10)["updated_at"],
            error_message="Cloud Run termino.",
        )
    assert not changed
    assert "updated_at = %s" in queries[0][0]
    assert "execution_name = %s" in queries[0][0]
    assert "output_uri IS NULL" in queries[0][0]
    assert queries[0][1][-1] == job_at(10)["updated_at"]


def main() -> None:
    check_cloud_run_states()
    check_reconciliation_guards()
    check_compare_and_swap_sql()
    print("OK: conciliacion de reportes por estado terminal de Cloud Run y guardas de concurrencia.")


if __name__ == "__main__":
    main()
