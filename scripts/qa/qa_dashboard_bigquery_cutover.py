from __future__ import annotations

import sys
from pathlib import Path

from fastapi import Response


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import vpo_corp_api as api
from app.bigquery_dashboard import dashboard_sql, query_rows, royalties_dashboard_bigquery


class EmptyQueryJob:
    def __init__(self, rows=None) -> None:
        self.rows = rows or []

    def result(self) -> list:
        return self.rows


class RecordingBigQueryClient:
    def __init__(self) -> None:
        self.job_config = None
        self.sql = None
        self.calls = []
        self.release_rows = [{"release_id": "ready-release-test"}]

    def query(self, sql: str, *, job_config, location: str):
        assert location == "US"
        self.sql = sql
        self.job_config = job_config
        self.calls.append((sql, job_config))
        if "SELECT release_id FROM" in sql:
            return EmptyQueryJob(self.release_rows)
        return EmptyQueryJob()


def assert_bigquery_cost_guard() -> None:
    client = RecordingBigQueryClient()
    rows = query_rows(
        sql="SELECT 1",
        release_id="ready-release-test",
        project="test-project",
        location="US",
        source=None,
        account=None,
        start_month=None,
        end_month=None,
        search_tokens=[],
        artist_scope_tokens=["candu"],
        use_all_months=False,
        month_limit=6,
        ranking_limit=10,
        maximum_bytes_billed=5_000_000_000,
        client=client,
    )
    assert rows == []
    assert client.job_config is not None
    assert client.job_config.maximum_bytes_billed == 5_000_000_000
    parameters = {parameter.name: parameter for parameter in client.job_config.query_parameters}
    assert parameters["artist_scope_tokens"].values == ["candu"]
    assert parameters["release_id"].value == "ready-release-test"


def assert_unrestricted_artist_scope_handles_null_array() -> None:
    sql = dashboard_sql(
        project="test-project",
        dataset="test_dataset",
        period_basis="statement_period",
        policy_document={"report_personalization": {"enabled": False}, "entries": []},
    )
    assert sql.count("COALESCE(ARRAY_LENGTH(@artist_scope_tokens), 0) = 0") == 2
    assert sql.count("release_id = @release_id") == 2
    assert "royalty_dashboard_rankings`" in sql


def assert_ready_snapshot_selection() -> None:
    client = RecordingBigQueryClient()
    result = royalties_dashboard_bigquery(
        policy_document={"report_personalization": {"enabled": False}, "entries": []},
        client=client,
    )
    assert result["totals"]["rows"] == 0
    assert len(client.calls) == 2
    assert "current_release`" in client.calls[0][0]
    assert all(config.maximum_bytes_billed == 5_000_000_000 for _, config in client.calls)
    params = {parameter.name: parameter for parameter in client.job_config.query_parameters}
    assert params["release_id"].value == "ready-release-test"
    consumption_sql = dashboard_sql(
        project="test-project", dataset="test_dataset", period_basis="transaction_month",
        policy_document={"report_personalization": {"enabled": False}, "entries": []},
    )
    assert consumption_sql.count("release_id = @release_id") == 2
    client.release_rows = []
    try:
        royalties_dashboard_bigquery(policy_document={}, client=client)
    except RuntimeError as error:
        assert "conciliada" in str(error)
    else:
        raise AssertionError("An unverified release must not be queried")


def assert_dashboard_switch() -> None:
    original_backend = api.VPO_ROYALTIES_DASHBOARD_BACKEND
    original_key = api.VPO_API_KEY
    original_query = api.query_royalties_dashboard_from_bigquery
    expected = {"backend": "bigquery", "ok": True}
    try:
        api.VPO_ROYALTIES_DASHBOARD_BACKEND = "bigquery"
        api.VPO_API_KEY = "test-key"
        api.query_royalties_dashboard_from_bigquery = lambda **_kwargs: expected
        response = Response()
        actual = api.royalties_dashboard(response=response, x_vpo_api_key="test-key")
        assert actual == expected
        assert response.headers["X-VPO-Dashboard-Backend"] == "bigquery"
    finally:
        api.VPO_ROYALTIES_DASHBOARD_BACKEND = original_backend
        api.VPO_API_KEY = original_key
        api.query_royalties_dashboard_from_bigquery = original_query


def main() -> None:
    assert_bigquery_cost_guard()
    assert_unrestricted_artist_scope_handles_null_array()
    assert_ready_snapshot_selection()
    assert_dashboard_switch()
    print("Dashboard BigQuery cutover contract OK")


if __name__ == "__main__":
    main()
