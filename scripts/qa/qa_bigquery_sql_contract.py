from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.bootstrap_bigquery_analytics import rendered_schema
from scripts.load_bigquery_release import insert_sql
from scripts.reconcile_bigquery_release import aggregate_bigquery_sql
from app.bigquery_dashboard import royalty_detail_count_bigquery


class FakeQuery:
    def result(self) -> list[dict[str, int]]:
        return [{"row_count": 123}]


class FakeClient:
    def __init__(self) -> None:
        self.sql = ""
        self.parameters: dict[str, Any] = {}

    def query(self, sql: str, *, job_config: Any, location: str) -> FakeQuery:
        self.sql = sql
        self.parameters = {
            parameter.name: getattr(parameter, "value", None)
            if hasattr(parameter, "value")
            else parameter.values
            for parameter in job_config.query_parameters
        }
        assert location == "US"
        return FakeQuery()


def main() -> None:
    schema = rendered_schema("project-test", "dataset_test", "US")
    assert "PARTITION BY statement_month" in schema
    assert "PARTITION BY transaction_month" in schema
    assert "CLUSTER BY release_id, source, account, asset_isrc" in schema
    assert "CREATE OR REPLACE VIEW `project-test.dataset_test.current_release`" in schema
    assert "royalty_report_detail" in schema
    assert "analytics_reconciliation_runs" in schema
    assert "analytics_reconciliation_results" in schema

    stages = {key: f"stage_{key}" for key in ["detail", "dashboard", "song", "catalog", "digital"]}
    load_sql = insert_sql(
        project="project-test",
        dataset="dataset_test",
        release_id="release-test",
        manifest_generation="123",
        published_at="2026-09-16T00:00:00+00:00",
        manifest_uri="gs://bucket/marts/release_manifest.json",
        source_files=6,
        stages=stages,
    )
    assert load_sql.startswith("BEGIN TRANSACTION;")
    assert load_sql.endswith("COMMIT TRANSACTION;")
    assert "DELETE FROM `project-test.dataset_test.royalty_statement_fact`" in load_sql
    assert "INSERT INTO `project-test.dataset_test.analytics_releases`" in load_sql
    assert "'loaded'" in load_sql
    assert "shadow load pending BQ-003 reconciliation" in load_sql

    reconciliation_sql = aggregate_bigquery_sql(
        project="project-test",
        dataset="dataset_test",
        release_id="release-test",
        period_column="statement_month",
        period_basis="statement",
    )
    assert "COUNT(DISTINCT NULLIF(asset_isrc, '')) AS isrcs" in reconciliation_sql
    assert "HAVING COUNT(DISTINCT asset_isrc) > 1" in reconciliation_sql
    assert "GROUP BY source, account, period_month, title" in reconciliation_sql
    transaction_sql = aggregate_bigquery_sql(
        project="project-test",
        dataset="dataset_test",
        release_id="release-test",
        period_column="transaction_month",
        period_basis="transaction",
    )
    assert "`project-test.dataset_test.royalty_transaction_fact`" in transaction_sql

    fake_client = FakeClient()
    detail_count = royalty_detail_count_bigquery(
        keywords=["Mamiyosoyelth", "Perreo TH"],
        mode="any",
        start_month="2025-01",
        end_month="2026-08",
        period_basis="transaction_month",
        project="project-test",
        dataset="dataset_test",
        client=fake_client,
    )
    assert detail_count == 123
    assert "SUM(raw_rows)" in fake_client.sql
    assert "transaction_month" in fake_client.sql
    assert fake_client.parameters["search_terms"] == ["mamiyosoyelth", "perreo th"]
    assert fake_client.parameters["mode"] == "any"

    print("BigQuery SQL contract OK")


if __name__ == "__main__":
    main()
