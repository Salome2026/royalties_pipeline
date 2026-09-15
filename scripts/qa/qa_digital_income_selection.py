"""Focused regression check for the shared digital-income view filter."""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import polars as pl
from fastapi import HTTPException

from app import vpo_corp_api as api


def main() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        standardized = base / api.STANDARDIZED_FILE
        standardized.touch()
        summary = base / api.DIGITAL_INCOME_SUMMARY_FILE
        rows = [
            {"source": "ADA", "account": "Indyana", "statement_period": "2026-06", "artist": "Flor", "title": "Uno", "total_usd": 100.0, "total_eur": 0.0, "has_share_in_out": False, "raw_rows": 1, "search_text": "flor uno"},
            {"source": "ADA", "account": "Mawz", "statement_period": "2026-06", "artist": "Flor", "title": "Dos", "total_usd": 200.0, "total_eur": 0.0, "has_share_in_out": False, "raw_rows": 1, "search_text": "flor dos"},
            {"source": "FUGA", "account": "Indyana", "statement_period": "2026-06", "artist": "Flor", "title": "Tres", "total_usd": 300.0, "total_eur": 0.0, "has_share_in_out": False, "raw_rows": 1, "search_text": "flor tres"},
        ]
        pl.DataFrame(rows).write_parquet(summary)

        with patch.object(api, "booking_connect", return_value=conn), \
             patch.object(api, "operational_connect", return_value=conn), \
             patch.object(api, "require_api_key"), \
             patch.object(api, "require_module_permission"), \
             patch.object(api, "is_postgres_connection", return_value=True), \
             patch.object(api, "db_sql", side_effect=lambda _conn, sql: sql), \
             patch.object(api, "VPO_LOCAL_MARTS_DIR", base), \
             patch.object(api, "ensure_marts", return_value={api.STANDARDIZED_FILE: standardized}), \
             patch.object(api, "build_digital_income_summary_mart", return_value=summary):
            api.ensure_digital_income_view_selection_table(conn)
            first = api.digital_income(x_vpo_username="ruben")
            assert first["totals"]["total_usd"] == 600.0
            assert first["view_selection"]["sources"] is None

            changed = api.update_digital_income_view_selection(
                api.DigitalIncomeViewSelectionRequest(
                    sources=None,
                    source_accounts=None,
                    excluded_source_accounts=[{"source": "ADA", "account": "Mawz"}],
                    version=0,
                ),
                x_vpo_username="ruben",
            )
            assert changed["version"] == 1
            second = api.digital_income(x_vpo_username="jefe")
            assert second["totals"]["total_usd"] == 400.0
            assert len(second["options"]["source_accounts"]) == 3
            assert second["view_selection"]["version"] == 1

            rows.append({"source": "ADA", "account": "Nueva", "statement_period": "2026-06", "artist": "Flor", "title": "Cuatro", "total_usd": 50.0, "total_eur": 0.0, "has_share_in_out": False, "raw_rows": 1, "search_text": "flor cuatro"})
            pl.DataFrame(rows).write_parquet(summary)
            with_new_account = api.digital_income(x_vpo_username="jefe")
            assert with_new_account["totals"]["total_usd"] == 450.0
            assert len(with_new_account["options"]["source_accounts"]) == 4

            one_source = api.update_digital_income_view_selection(
                api.DigitalIncomeViewSelectionRequest(
                    sources=["ADA"],
                    source_accounts=None,
                    excluded_source_accounts=changed["excluded_source_accounts"],
                    version=1,
                ),
                x_vpo_username="jefe",
            )
            assert one_source["version"] == 2
            assert api.digital_income(x_vpo_username="ruben")["totals"]["total_usd"] == 150.0

            try:
                api.update_digital_income_view_selection(
                    api.DigitalIncomeViewSelectionRequest(sources=["ADA"], version=0),
                    x_vpo_username="jefe",
                )
            except HTTPException as error:
                assert error.status_code == 409
            else:
                raise AssertionError("A stale selection overwrote a newer one")

            empty = api.update_digital_income_view_selection(
                api.DigitalIncomeViewSelectionRequest(sources=[], source_accounts=None, version=2),
                x_vpo_username="jefe",
            )
            assert empty["version"] == 3
            assert api.digital_income(x_vpo_username="ruben")["totals"]["total_usd"] == 0.0

    print("Digital income shared selection: OK")


if __name__ == "__main__":
    main()
