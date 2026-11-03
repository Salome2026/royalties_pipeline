"""Reusable templates preserve the existing distribution calculations and snapshots."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from app import distribution_contracts as store
from app import vpo_corp_api as api
from app.master_contracts import save_split, read_split, validate_split
from app.royalty_reports.contractual import allocation_rows, analyze_contractual_income
from app.royalty_scope import use_scope


class PersistenceFixture:
    """Exercise repository SQL in memory; Postgres row locking is not emulated."""
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        schema = Path("database/migrations/018_distribution_contracts.sql").read_text().split("INSERT INTO schema_migrations")[0]
        self.conn.executescript(schema + "COMMIT;")

    def execute(self, sql, params=()):
        return self.conn.execute(sql.replace(" FOR UPDATE", ""), params)


class DistributionContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = PersistenceFixture()
        self.addCleanup(self.fixture.conn.close)
        self.scope = patch.object(store, "is_postgres_connection", return_value=True)
        self.sql = patch.object(store, "db_sql", side_effect=lambda conn, sql: sql)
        self.scope.start(); self.sql.start()
        self.addCleanup(self.scope.stop); self.addCleanup(self.sql.stop)
        self.terms = {"label": "Sello", "sublabel": "", "master_pool_percent": 30,
                      "company_name": "Indyana", "distribution_recipients": None}

    def save(self, terms=None, **kwargs):
        return store.save_distribution_contract(self.fixture, terms or self.terms,
            number=kwargs.get("number"), expected_version=kwargs.get("version", 0), actor="tester")

    def test_incremental_unique_numbers_and_normalized_label_sublabel(self):
        first = self.save()
        self.assertEqual(first["number"], 10010)
        with self.assertRaisesRegex(ValueError, "10010"):
            self.save({**self.terms, "label": " SÉLLO  "})
        second = self.save({**self.terms, "sublabel": "Pop"})
        third = self.save({**self.terms, "label": "Otro sello"})
        self.assertEqual([second["number"], third["number"]], [10011, 10012])
        with self.assertRaises(ValueError): self.save({**self.terms, "sublabel": " POP "})
        self.assertEqual(len(store.list_distribution_contracts(self.fixture)), 3)

    def test_number_is_immutable_and_updates_are_versioned(self):
        first = self.save()
        second = self.save({**self.terms, "master_pool_percent": 25}, number=first["number"], version=1)
        self.assertEqual((second["number"], second["version"]), (10010, 2))
        with self.assertRaisesRegex(ValueError, "cambió"):
            self.save(number=10010, version=1)
        history = self.fixture.execute("SELECT payload_json FROM master_distribution_contract_history ORDER BY version").fetchall()
        self.assertEqual([json.loads(row["payload_json"])["master_pool_percent"] for row in history], [30, 25])
        self.assertEqual(self.save({**self.terms, "label": "Otro"})["number"], 10011)

    def test_duplicate_edit_and_invalid_number_are_rejected(self):
        self.save()
        second = self.save({**self.terms, "sublabel": "Pop"})
        with self.assertRaisesRegex(ValueError, "subsello diferente"):
            self.save(number=second["number"], version=1)
        with self.assertRaisesRegex(ValueError, "cambió"):
            self.save({**self.terms, "label": "Otro"}, number=20000, version=0)

    def test_template_validation_uses_absolute_recipient_shares(self):
        rows = [{"name": "Indyana", "percent": 20}, {"name": "Socio", "percent": 10}]
        saved = self.save({**self.terms, "distribution_recipients": rows})
        self.assertEqual(saved["distribution_recipients"], rows)
        for invalid in [None, -1, 101, float("nan"), float("inf")]:
            with self.subTest(pool=invalid), self.assertRaises(ValueError):
                store.validate_terms({**self.terms, "master_pool_percent": invalid})
        for invalid_rows in [[{"name": "Indyana", "percent": 20}, {"name": "Socio", "percent": 9}],
                             [{"name": "Indyana", "percent": 20}, {"name": "INDYANA", "percent": 10}],
                             [{"name": "", "percent": 30}], [{"name": "X", "percent": None}, {"name": "Y", "percent": 10}]]:
            with self.subTest(rows=invalid_rows), self.assertRaises(ValueError):
                store.validate_terms({**self.terms, "distribution_recipients": invalid_rows})
        self.assertEqual(store.validate_terms({**self.terms, "distribution_recipients": [{"name": "Mawz", "percent": None}]})["company_name"], "Mawz")

    def test_references_validate_historical_versions_and_scope(self):
        first = self.save()
        self.save({**self.terms, "master_pool_percent": 25}, number=first["number"], version=1)
        reference = {"commercialization": "distribution", "distribution_contract_number": 10010, "distribution_contract_version": 1}
        store.validate_distribution_references(self.fixture, {"agreements": [reference]})
        for patch_values in [{"distribution_contract_version": 99}, {"commercialization": "master"}, {"distribution_contract_number": None}]:
            with self.assertRaises(ValueError):
                store.validate_distribution_references(self.fixture, {"agreements": [{**reference, **patch_values}]})
        with use_scope("wml"), self.assertRaises(ValueError): store.list_distribution_contracts(self.fixture)

    def test_api_keeps_template_reference_and_enforces_permissions(self):
        model = api.MasterDistributionContractSaveRequest(**self.terms)
        with patch.object(api, "require_api_key"), patch.object(api, "operational_connect") as connect, \
                patch.object(api, "require_master_contract_user", return_value="tester") as permission:
            connect.return_value.__enter__.return_value = self.fixture
            saved = api.put_master_contract_distribution(model, x_vpo_username="tester")
            permission.assert_called_with(self.fixture, "tester", "edit")
            result = api.get_master_contract_distribution(x_vpo_username="tester")
            permission.assert_called_with(self.fixture, "tester", "access")
        self.assertEqual(result["items"][0]["number"], saved["number"])
        parsed = api.MasterAgreement(id="principal", commercialization="distribution",
            distribution_contract_number=10010, distribution_contract_version=1).model_dump()
        self.assertEqual(parsed["distribution_contract_version"], 1)

    def test_reports_use_closed_contract_with_no_report_opt_in(self):
        agreement = {"id": "principal", "commercialization": "distribution", "allocation_model": "pools",
            "master_pool_percent": 30, "company_name": "Indyana", "owners": [], "effective_from": "2026-01-01",
            "distribution_recipients": [{"name": "Indyana", "percent": 20}, {"name": "Socio", "percent": 10}],
            "allocation": {"principal": "Artista", "principal_percent": 70, "participants": []}}
        split = {"agreement_confirmed": True, "agreements": [agreement]}
        snapshot = {"as_of": "2026-11-03", "artists": ["Artista"], "catalog": [{"isrc": "ARDL12600041", "title": "Tema"}],
                    "contracts": [{"isrc": "ARDL12600041", "split": split, "is_closed": True, "version": 1, "future_reports_selected": False}]}
        income = [{"isrc": "ARDL12600041", "amount_usd": 100, "statement_month": "2026-03", "source": "fuga"}]
        result = analyze_contractual_income(snapshot, income)
        self.assertEqual(result["covered"], 100)
        self.assertEqual(result["pending"], 0)
        self.assertEqual({row["artist"]: row["amount"] for row in result["recipients"]}, {"Indyana": 20, "Socio": 10, "Artista": 70})
        marked = deepcopy(snapshot); marked["contracts"][0]["future_reports_selected"] = True
        self.assertEqual(analyze_contractual_income(marked, income), result)
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            legacy_split = {"master_type": "distribution", "has_contract": False, "principal": "Artista", "participants": []}
            saved = save_split(conn, "ARDL12600041", legacy_split, closed=False,
                future_reports_selected=True, expected_version=0, actor="tester")
            self.assertFalse(saved["future_reports_selected"])
            self.assertIsNotNone(read_split(conn, "ARDL12600041"))


if __name__ == "__main__": unittest.main()
