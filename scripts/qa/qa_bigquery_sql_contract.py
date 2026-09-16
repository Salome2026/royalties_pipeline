from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.bootstrap_bigquery_analytics import rendered_schema
from scripts.load_bigquery_release import insert_sql


def main() -> None:
    schema = rendered_schema("project-test", "dataset_test", "US")
    assert "PARTITION BY statement_month" in schema
    assert "PARTITION BY transaction_month" in schema
    assert "CLUSTER BY release_id, source, account, asset_isrc" in schema
    assert "CREATE OR REPLACE VIEW `project-test.dataset_test.current_release`" in schema
    assert "royalty_report_detail" in schema

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
    assert "shadow load from immutable GCS release" in load_sql

    print("BigQuery SQL contract OK")


if __name__ == "__main__":
    main()
