"""The panel omits only duplicate income work; association validation stays current."""
from contextlib import ExitStack
import json
import unittest
from unittest.mock import MagicMock, patch

import polars as pl
from app import vpo_corp_api as api

ISRC = "ARDL12600006"


class FastAssociationReadTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.mocks = {}
        self.conn = MagicMock()
        self.saved = {"version": 7, "closed": True, "split": {"code_association_overrides": []}}
        self.items = [
            {"key": json.dumps(["UPC", "8721466047355", "fuga", "indyana_records"]),
             "code": "8721466047355", "automatic": True, "selectable": True,
             "evidence_signature": "native", "status": "automatic", "included": True},
            {"key": json.dumps(["VIDEO", "abcdefghijk", "fuga", "indyana_records"]),
             "code": "abcdefghijk", "automatic": False, "selectable": True,
             "requires_review": True, "evidence_signature": "current", "status": "pending", "included": False},
        ]
        returns = {
            "require_api_key": None, "require_master_contract_user": "reader",
            "read_split": self.saved, "read_contract_association_claims": {"claimed": "OTHER"},
            "read_contract_association_choices": {}, "master_contract_associations": self.items,
            "master_contract_associated_income": {ISRC: {"amount_usd": 10., "statement_income": [
                {"statement_month": "2026-06", "amount_usd": 10.}, {"statement_month": "2026-07", "amount_usd": 20.}]}},
            "master_contract_income_baseline": pl.DataFrame({"asset_isrc": [ISRC], "amount_usd": [100.]}),
            "master_contract_statement_income": [{"statement_month": "2026-05", "amount_usd": 100.},
                                                 {"statement_month": "2026-07", "amount_usd": 50.}],
        }
        for name, value in returns.items():
            self.mocks[name] = stack.enter_context(patch.object(api, name, return_value=value))
        connect = stack.enter_context(patch.object(api, "operational_connect"))
        connect.return_value.__enter__.return_value = self.conn
        stack.enter_context(patch.object(api, "CONTRACT_ANALYSIS_CUTOFF_MONTH", "2026-06"))
        stack.enter_context(patch.object(api, "is_wml", return_value=False))

    def get(self, **params):
        return api.get_master_contract_associations(ISRC, "key", "reader", **params)

    def test_default_response_keeps_income_for_existing_callers(self):
        result = self.get()
        self.assertEqual(result["income"]["amount_usd"], 110.)
        self.assertEqual(result["income"]["isrc_amount_usd"], 100.)
        self.assertEqual(result["income"]["associated_amount_usd"], 10.)
        self.assertEqual(result["income"]["statement_income"], [
            {"statement_month": "2026-05", "amount_usd": 100.},
            {"statement_month": "2026-06", "amount_usd": 10.}])
        self.assertEqual(result["pending_codes"], ["abcdefghijk"])

    def test_explicit_full_response_matches_default(self):
        self.assertEqual(self.get(include_income=True), self.get())

    def test_light_read_does_not_run_any_income_helpers(self):
        result = self.get(include_income=False)
        self.assertNotIn("income", result)
        for name in ("read_contract_association_choices", "master_contract_associated_income",
                     "master_contract_income_baseline", "master_contract_statement_income"):
            self.mocks[name].assert_not_called()

    def test_all_codes_signatures_decisions_and_pending_counts_are_identical(self):
        full = self.get()
        light = self.get(include_income=False)
        self.assertEqual(light, {k: v for k, v in full.items() if k != "income"})
        self.assertEqual(light["items"], self.items)
        self.assertEqual(light["version"], 7)
        self.assertFalse(light["reports_effective"])

    def test_light_read_still_checks_permissions_and_latest_claims(self):
        self.get(include_income=False)
        self.mocks["require_api_key"].assert_called_once_with("key")
        self.mocks["require_master_contract_user"].assert_called_once_with(self.conn, "reader", "access")
        self.mocks["read_split"].assert_called_once_with(self.conn, ISRC)
        self.mocks["read_contract_association_claims"].assert_called_once_with(self.conn)
        self.mocks["master_contract_associations"].assert_called_once_with(ISRC, [], {"claimed": "OTHER"})
        self.conn.execute.assert_not_called()

    def test_new_contract_version_and_manual_exclusion_are_not_cached(self):
        self.get(include_income=False)
        self.saved["version"] = 8
        decision = {"key": self.items[1]["key"], "included": False, "evidence_signature": "current"}
        self.saved["split"]["code_association_overrides"] = [decision]
        result = self.get(include_income=False)
        self.assertEqual(result["version"], 8)
        self.assertEqual(result["pending_codes"], [])
        self.mocks["master_contract_associations"].assert_called_with(ISRC, [decision], {"claimed": "OTHER"})

    def test_unsaved_contract_keeps_version_zero(self):
        self.mocks["read_split"].return_value = None
        self.assertEqual(self.get(include_income=False)["version"], 0)

    def test_access_denied_cannot_be_bypassed_by_light_mode(self):
        self.mocks["require_master_contract_user"].side_effect = api.HTTPException(403, "Denied")
        with self.assertRaises(api.HTTPException) as error:
            self.get(include_income=False)
        self.assertEqual(error.exception.status_code, 403)
        self.mocks["master_contract_associations"].assert_not_called()

    def test_evidence_errors_remain_blocking(self):
        self.mocks["master_contract_associations"].side_effect = api.HTTPException(503, "Cannot verify")
        with self.assertRaises(api.HTTPException) as error:
            self.get(include_income=False)
        self.assertEqual(error.exception.status_code, 503)
        self.mocks["master_contract_income_baseline"].assert_not_called()

    def test_invalid_isrc_still_fails_before_reading_data(self):
        with self.assertRaises(api.HTTPException) as error:
            api.get_master_contract_associations("invalid", "key", "reader", include_income=False)
        self.assertEqual(error.exception.status_code, 400)
        self.mocks["read_split"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
