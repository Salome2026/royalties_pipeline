from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.master_contract_participants import names, onerpm_principal, propose_participants


def allocation():
    return {"principal": "Principal", "principal_percent": 20, "indyana_percent": None,
            "participants": [{"artist": "Invitado", "percent": 10, "rule": {"treatment": "direct"}}]}


def sample():
    return {**allocation(), "notes": "Original", "code_association_overrides": [], "agreements": [
        {"id": "principal", "master_pool_percent": 70, "effective_from": "2025-01-01", "allocation": allocation()}]}


def saved(split=None, version=1, closed=False):
    return {"split": split or sample(), "version": version, "closed": closed, "future_reports_selected": False}


def history(row, closed=None):
    return {"payload_json": json.dumps(row["split"], sort_keys=True), "version": row["version"],
            "is_closed": row["closed"] if closed is None else closed, "future_reports_selected": row["future_reports_selected"]}


class ParticipantTests(unittest.TestCase):
    def project(self, row, histories=None, artists=None):
        return propose_participants(row["split"], artists or ["Principal", "Invitado", "Recuperado"],
                                    saved=row, history=[history(row)] if histories is None else histories)

    def test_open_fills_every_allocation_without_changing_saved_values(self):
        row = saved()
        original = copy.deepcopy(row)
        projected, info = self.project(row)
        self.assertEqual(info["status"], "open_never_closed")
        for allocation in (projected, projected["agreements"][0]["allocation"]):
            self.assertEqual(names(allocation), ["Principal", "Invitado", "Recuperado"])
            self.assertEqual(allocation["principal_percent"], 20)
            self.assertEqual(allocation["participants"][0]["percent"], 10)
            self.assertIsNone(allocation["participants"][-1]["percent"])
        self.assertEqual(row, original)
        self.assertEqual(projected["notes"], "Original")
        self.assertEqual(projected["code_association_overrides"], [])

    def test_new_unsaved_historical_has_all_artists_even_without_principal(self):
        initial = {"principal": "", "participants": []}
        projected, info = propose_participants(initial, ["A", "B"], saved=None, history=[])
        self.assertEqual(names(projected), ["A", "B"])
        self.assertEqual(info["status"], "new_unsaved")

    def test_closed_untouched(self):
        row = saved(closed=True)
        self.assertIs(self.project(row)[0], row["split"])

    def test_reopened_untouched(self):
        row = saved(version=2)
        records = [history(saved(closed=True)), history(row)]
        self.assertIs(self.project(row, records)[0], row["split"])

    def test_incomplete_history_not_assumed_never_closed(self):
        row = saved(version=2)
        self.assertEqual(self.project(row)[1]["status"], "history_incomplete")

    def test_latest_history_must_match_payload(self):
        row = saved()
        wrong = saved({**sample(), "notes": "Other"})
        self.assertEqual(self.project(row, [history(wrong)])[1]["status"], "history_incomplete")

    def test_history_keeps_manual_deletion(self):
        first = saved()
        smaller = sample()
        smaller["participants"] = []
        smaller["agreements"][0]["allocation"]["participants"] = []
        second = saved(smaller, version=2)
        projected, _ = self.project(second, [history(first), history(second)])
        self.assertEqual(names(projected), ["Principal", "Recuperado"])

    def test_first_save_exclusion_survives(self):
        row = saved({**sample(), "catalog_participant_exclusions": ["Recuperado"]})
        projected, _ = self.project(row)
        self.assertNotIn("Recuperado", names(projected))
        self.assertIn("Recuperado", names(projected["agreements"][0]["allocation"]))

    def test_duplicates_only_case_space_accents(self):
        projected, _ = propose_participants({"principal": "Jos\u00e9", "participants": []},
            ["Jose", " Jos\u00e9 ", "Jose DJ"], saved=None, history=[])
        self.assertEqual(names(projected), ["Jos\u00e9", "Jose DJ"])

    def test_capacity_is_exposed_not_truncated(self):
        all_names = [f"Artist {number}" for number in range(14)]
        projected, info = propose_participants({"principal": "", "participants": []}, all_names, saved=None, history=[])
        self.assertEqual(names(projected), all_names)
        self.assertTrue(info["capacity_exceeded"])

    def test_idempotent_and_future_artists_added(self):
        first = saved()
        one, _ = self.project(first)
        second = saved(one, version=2)
        two, info = self.project(second, [history(first), history(second)])
        self.assertEqual(one, two)
        self.assertEqual(info["added"], {})
        third, _ = self.project(second, [history(first), history(second)], ["Principal", "Invitado", "Recuperado", "Futuro"])
        self.assertIn("Futuro", names(third))

    def test_request_schema_does_not_drop_exclusions(self):
        from app.vpo_corp_api import MasterContractSplit
        value = sample()
        value["catalog_participant_exclusions"] = ["Recuperado"]
        value["agreements"][0].update(commercialization="master", owners=[])
        value["agreements"][0]["allocation"]["catalog_participant_exclusions"] = ["Invitado 2"]
        encoded = MasterContractSplit.model_validate(value).model_dump()
        self.assertEqual(encoded["catalog_participant_exclusions"], ["Recuperado"])
        self.assertEqual(encoded["agreements"][0]["allocation"]["catalog_participant_exclusions"], ["Invitado 2"])

    def test_principal_is_source_order_only(self):
        evidence = {"source": "onerpm", "field": "Artists", "sheet": "Masters", "used_for_catalog": True,
                    "level": "track", "product_type": "Track", "status": "resolved", "identity_status": "resolved",
                    "native_resolution_status": "resolved", "principal_status": "order_only", "principal_proposed": "Principal"}
        self.assertFalse(onerpm_principal([evidence], ["Principal", "Invitado"], False))
        self.assertTrue(onerpm_principal([evidence], ["Principal", "Invitado"], True))
        self.assertTrue(onerpm_principal([{**evidence, "sheet": "Shares In & Out"}], ["Principal"], False))
        self.assertIsNone(onerpm_principal([], ["Principal"], False))


if __name__ == "__main__":
    unittest.main()
