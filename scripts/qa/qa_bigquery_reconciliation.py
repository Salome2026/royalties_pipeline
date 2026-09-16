from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

import polars as pl


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.reconcile_bigquery_release import aggregate_local, reconcile_rows


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        detail_path = Path(temporary) / "detail.parquet"
        pl.DataFrame(
            {
                "statement_month": [date(2026, 7, 1)] * 3,
                "transaction_month": [date(2026, 6, 1)] * 3,
                "source": ["fuga"] * 3,
                "account": ["mawz"] * 3,
                "title": ["Same Song", "Same Song", "No Code"],
                "asset_isrc": ["ARAAA2600001", "ARAAA2600002", None],
                "amount_usd": [10.0, 15.0, 2.5],
                "units": [100.0, 200.0, 1.0],
            }
        ).write_parquet(detail_path)

        local = aggregate_local(detail_path, "statement_month", "statement")
        assert len(local) == 1
        assert local[0]["isrcs"] == 2
        assert local[0]["missing_isrc_rows"] == 1
        assert local[0]["multi_isrc_title_groups"] == 1

        matching = reconcile_rows(
            local_rows=local,
            bigquery_rows=[dict(local[0])],
            release_id="release-test",
            run_id="run-test",
            amount_tolerance=0.01,
            units_tolerance=0.0001,
        )
        assert matching[0]["status"] == "match"
        assert matching[0]["parquet_isrcs"] == 2
        assert matching[0]["parquet_multi_isrc_title_groups"] == 1

        changed = dict(local[0])
        changed["isrcs"] = 1
        mismatch = reconcile_rows(
            local_rows=local,
            bigquery_rows=[changed],
            release_id="release-test",
            run_id="run-test",
            amount_tolerance=0.01,
            units_tolerance=0.0001,
        )
        assert mismatch[0]["status"] == "mismatch"
        assert "isrcs" in mismatch[0]["mismatch_reasons"]

    print("BigQuery reconciliation OK")


if __name__ == "__main__":
    main()
