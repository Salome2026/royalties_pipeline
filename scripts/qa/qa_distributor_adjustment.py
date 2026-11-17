from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

import polars as pl

from app.bigquery_dashboard import dashboard_sql, personalization_factor_sql
from scripts.lib.catalog_report_filter import apply_report_net_personalization
from scripts.lib.distributor_adjustment import adjustment_schedule


POLICY = {"report_personalization": {"enabled": True}, "entries": [
    {"source": "fuga", "account": "indyana_records", "report_net_adjustment_pct": 10,
     "report_adjustment_schedule": [{"from_statement": "2026-11", "percent": 18},
                                    {"from_statement": "2027-01", "percent": 0}]},
    {"source": "ada", "account": "indyana_records", "report_net_adjustment_pct": 20},
]}


class DistributorAdjustmentTest(unittest.TestCase):
    def test_adjusts_by_statement_not_consumption_or_account_alone(self):
        frame = pl.DataFrame({
            "source": ["fuga"] * 6 + ["ada"],
            "account": ["indyana_records"] * 4 + ["other"] + ["indyana_records"] * 2,
            "statement_period": ["2026-10", "2026-11", "2026-12", "2027-01", "2026-11", None, "2026-11"],
            "transaction_month": ["2026-09"] * 7,
            "amount_usd": [100.0, 100.0, -100.0, 100.0, 100.0, 100.0, 100.0],
            "units": list(range(7)),
        })
        with patch("scripts.lib.catalog_report_filter.load_distributor_policy_document", return_value=POLICY):
            adjusted = apply_report_net_personalization(frame.lazy()).collect()
            self.assertEqual(adjusted["amount_usd"].to_list(), [90, 82, -82, 100, 100, 90, 80])
            self.assertEqual(adjusted["units"].to_list(), frame["units"].to_list())
            self.assertEqual(apply_report_net_personalization(frame.rename({"statement_period": "statement_month"})
                             .with_columns(pl.col("statement_month").str.to_date("%Y-%m")).lazy())
                             .collect()["amount_usd"].to_list(), adjusted["amount_usd"].to_list())
            with self.assertRaisesRegex(ValueError, "mes de statement"):
                apply_report_net_personalization(frame.drop("statement_period").lazy())

    def test_sql_checks_latest_statement_first_even_when_grouping_by_consumption(self):
        factor = personalization_factor_sql(POLICY, row_alias="n")
        self.assertIn("n.source = 'fuga' AND n.account = 'indyana_records'", factor)
        self.assertLess(factor.index("2027-01-01"), factor.index("2026-11-01"))
        self.assertIn("WHEN n.statement_month >= DATE '2026-11-01' THEN 0.820000000000", factor)
        sql = dashboard_sql(project="test", dataset="test", period_basis="transaction_month", policy_document=POLICY)
        self.assertIn("transaction_month AS period_month", sql)
        self.assertIn("statement_month >= DATE '2026-11-01'", sql)
        off = deepcopy(POLICY)
        off["report_personalization"]["enabled"] = False
        self.assertEqual(personalization_factor_sql(off), "1.0")

    def test_rejects_invalid_dates_rates_and_duplicate_boundaries(self):
        def rule(month="2026-11", percent=18):
            return {"from_statement": month, "percent": percent}
        for changes in ([rule("2026-00")], [rule("0000-11")], [rule(percent=101)],
                        [rule(percent=float("nan"))], [rule(), rule(percent=19)]):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                adjustment_schedule(changes)


if __name__ == "__main__":
    unittest.main()
