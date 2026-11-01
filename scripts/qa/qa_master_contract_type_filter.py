"""Contract types must filter the full list, together with its existing filters."""
from __future__ import annotations

import json
import sqlite3
import unittest
from contextlib import nullcontext
from unittest.mock import patch

import polars as pl
from fastapi import HTTPException

from app import vpo_corp_api as api
from app.master_contracts import contract_commercializations, ensure_sqlite_tables, read_split_statuses
from app.royalty_scope import use_scope


class ContractTypeFilterTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        self.codes = [f"ARDL1260000{i}" for i in range(1, 8)]
        catalog = pl.DataFrame({
            "asset_isrc": self.codes,
            "track_title": ["Tema máster", "Tema distribución", "Tema con dos vigencias", "Otro máster",
                            "Distribución Mawz", "Contrato por definir", "Sin contrato guardado"],
            "artist_statement": ["Aneley"] * 7, "artist_variants": ["Aneley"] * 7,
            "amount_usd": [700., 600., 500., 400., 300., 200., 100.],
            "isrc_amount_usd": [650., 600., 500., 400., 300., 200., 100.],
            "associated_amount_usd": [50., 0., 0., 0., 0., 0., 0.],
            "_contract_first_statement_month": ["2026-01"] * 7,
            "_contract_last_statement_month": ["2026-06"] * 7, "sources": ["fuga"] * 7,
        })
        memberships = pl.DataFrame({"asset_isrc": self.codes, "source": ["fuga"] * 7,
                                    "account": ["indy"] * 3 + ["mawz"] * 4})
        splits = [
            {"master_type": "indyana_master"},
            {"master_type": "distribution"},
            {"master_type": "pending", "agreements": [
                {"commercialization": "master"}, {"commercialization": "distribution"}]},
            {"master_type": "mawz_and_other"},
            {"master_type": "distribution_mawz"},
            {},
        ]
        ensure_sqlite_tables(self.conn)
        for code, split in zip(self.codes, splits):
            self.conn.execute("""INSERT INTO master_contract_splits
                (isrc, payload_json, is_closed, future_reports_selected, version, updated_by, updated_at)
                VALUES (?, ?, 0, 0, 1, 'test', '2026-10-30')""", (code, json.dumps(split)))
        # Mark fixture records as closed without constructing unrelated allocation terms.
        self.conn.execute("UPDATE master_contract_splits SET is_closed = 1 WHERE isrc IN (?, ?)",
                          (self.codes[0], self.codes[2]))
        patches = {
            "require_api_key": None,
            "require_master_contract_user": None,
            "operational_connect": nullcontext(self.conn),
            "read_contract_association_choices": {},
            "read_association_review_states": {self.codes[0]: {"association_review_pending": True}},
            "master_contract_associated_income": {},
            "master_contract_catalog": catalog,
            "master_contract_source_accounts": memberships,
        }
        for name, value in patches.items():
            patcher = patch.object(api, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def listing(self, **filters):
        return api.list_master_contracts(x_vpo_username="test", **filters)

    def test_modern_agreements_override_legacy_and_keep_both_types(self):
        self.assertEqual(contract_commercializations({"master_type": "distribution", "agreements": [
            {"commercialization": "master"}, {"commercialization": "master"}]}), ["master"])
        self.assertEqual(contract_commercializations({"agreements": [
            {"commercialization": "distribution"}, {"commercialization": "master"}]}), ["master", "distribution"])
        for kind in ("indyana_master", "mawz_master", "indyana_and_other", "mawz_and_other"):
            self.assertEqual(contract_commercializations({"master_type": kind}), ["master"])
        self.assertEqual(contract_commercializations({"agreements": [{"commercialization": "pending"}]}), ["pending"])

    def test_type_filter_before_pagination_preserves_income_and_summary(self):
        result = self.listing(commercialization="master", limit=1, offset=1)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["summary"], {"open": 1, "closed": 2, "review": 1})
        self.assertEqual([r["isrc"] for r in result["items"]], [self.codes[2]])
        first = self.listing(commercialization="master", limit=1)["items"][0]
        self.assertEqual((first["amount_usd"], first["isrc_amount_usd"], first["associated_amount_usd"]), (700, 650, 50))
        self.assertEqual(first["commercialization_types"], ["master"])

    def test_status_search_and_distributor_combine_with_contract_type(self):
        scenarios = [
            ({"commercialization": "master", "status": "closed"}, self.codes[:1] + self.codes[2:3]),
            ({"commercialization": "master", "status": "open"}, self.codes[3:4]),
            ({"commercialization": "distribution"}, self.codes[1:3] + self.codes[4:5]),
            ({"commercialization": "master", "status": "review"}, self.codes[:1]),
            ({"commercialization": "master", "keyword": "otro", "source": "fuga", "account": "mawz"}, self.codes[3:4]),
            ({"commercialization": "distribution", "status": "closed", "account": "mawz"}, []),
        ]
        for filters, expected in scenarios:
            with self.subTest(filters=filters):
                result = self.listing(**filters)
                self.assertEqual([r["isrc"] for r in result["items"]], expected)
                self.assertEqual(len(result["source_accounts"]), 2)

    def test_pending_includes_legacy_and_unsaved_records(self):
        result = self.listing(commercialization="pending")
        self.assertEqual([r["isrc"] for r in result["items"]], self.codes[5:])
        self.assertTrue(all(r["commercialization_types"] == ["pending"] for r in result["items"]))
        self.assertEqual(self.listing()["total"], 7)

    def test_wml_uses_only_its_saved_types(self):
        with use_scope("wml"), patch("app.royalty_workspace_store.records", return_value={self.codes[0]: {
            "payload": {"split": {"master_type": "distribution_mawz"}, "closed": False},
            "version": 1, "updated_at": "2026-10-30"}}):
            self.assertEqual(read_split_statuses(self.conn)[self.codes[0]]["commercialization_types"], ["distribution"])
            self.assertEqual(self.listing(commercialization="master")["total"], 0)
            self.assertEqual(self.listing(commercialization="distribution")["total"], 1)
        self.assertEqual(self.listing(commercialization="master")["total"], 3)

    def test_unidentified_rejects_contract_type_instead_of_ignoring_it(self):
        with self.assertRaises(HTTPException) as caught:
            self.listing(status="unidentified", commercialization="master")
        self.assertEqual(caught.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
