from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from lib.ada_catalog_artists import ARTIST_COLUMNS, EVIDENCE_VERSION, enrich_ada_catalog, evidence_entry, parse_credit
from app.master_contracts import artist_suggestions, suggested_split
from app.master_contract_participants import ada_principal, propose_participants
from lib.ada_statement_reader import control_disposition, known_controls


def catalog(names=None):
    row = {"catalog_key": "ISRC:USABC2600001", "asset_isrc": "USABC2600001", "track_title": "Song",
           "artist_statement": "Original credit", "amount_usd": 100.0, "units": 50.0, "catalog_aliases": ["VIDEO:example"],
           "catalog_artists": names, "catalog_artist_statement": None, "catalog_artist_rule": None, "catalog_artist_evidence": None}
    return pl.DataFrame([row], schema_overrides=ARTIST_COLUMNS)


def native(credits):
    return pl.DataFrame([{"source": "ada", "account": "indyana_records", "asset_isrc": "USABC2600001",
        "native_entity_key": "ISRC:USABC2600001", "Artist Name": credit, "Catalogue Title": "Song", "Project Title": "Album",
        "statement_period": "2026-10", "statement_file_hash": str(i), "statement_file_name": f"file{i}.xlsx",
        "source_row": i + 7, "native_source_sheet": "Distribution Statement"} for i, credit in enumerate(credits)])


class AdaCatalogTests(unittest.TestCase):
    def test_only_artist_columns_can_change(self):
        before = catalog(["Principal"])
        after = enrich_ada_catalog(before, native(["Principal & Guest"]))
        self.assertTrue(before.drop(list(ARTIST_COLUMNS)).equals(after.drop(list(ARTIST_COLUMNS))))
        self.assertEqual(after["catalog_artists"][0].to_list(), ["Principal", "Guest"])

    def test_reconstruction_is_idempotent(self):
        first = enrich_ada_catalog(catalog(), native(["Principal & Guest"]))
        self.assertTrue(first.equals(enrich_ada_catalog(first, native(["Principal & Guest"]))))

    def test_evidence_is_stable_when_input_order_changes(self):
        observations = native(["Principal & Guest", "Principal"])
        self.assertTrue(enrich_ada_catalog(catalog(), observations).equals(enrich_ada_catalog(catalog(), observations.reverse())))

    def test_title_never_invents_an_artist(self):
        values = native(["Principal"]).with_columns(pl.lit("Guest collaboration").alias("Project Title"))
        self.assertEqual(enrich_ada_catalog(catalog(), values)["catalog_artists"][0].to_list(), ["Principal"])

    def test_incompatible_lists_preserve_prior(self):
        before = catalog(["Published"])
        after = enrich_ada_catalog(before, native(["Other & Guest"]))
        self.assertEqual(after["catalog_artists"][0].to_list(), ["Published"])
        record = json.loads(after["catalog_artist_evidence"][0])[-1]
        self.assertEqual(record["identity_status"], "contradictory")
        self.assertTrue(ada_principal([record], ["Published"]))

    def test_collective_reference_and_unknown_guest_reach_real_contract(self):
        after = enrich_ada_catalog(catalog(), native(["Earth, Wind & Fire & Unknown Guest"]), atomic_names=("Earth, Wind & Fire",))
        row = after.row(0, named=True)
        suggestions = artist_suggestions(row["asset_isrc"], None, row["artist_statement"], row["catalog_artists"], row["catalog_artist_evidence"])
        self.assertFalse(suggestions["principal_uncertain"])
        proposed = suggested_split(suggestions["artists"], {}, "2026-10-01")
        proposed, _ = propose_participants(proposed, suggestions["artists"], saved=None, history=[])
        self.assertEqual(proposed["principal"], "Earth, Wind & Fire")
        self.assertIsNone(proposed["participants"][0]["percent"])
        self.assertIsNone(proposed["indyana_percent"])

    def test_different_order_keeps_names_and_doubt(self):
        after = enrich_ada_catalog(catalog(), native(["First & Second", "Second & First"]))
        record = json.loads(after["catalog_artist_evidence"][0])[-1]
        self.assertEqual(set(record["artists"]), {"First", "Second"})
        self.assertTrue(ada_principal([record], record["artists"]))

    def test_no_other_source_adapter_override(self):
        self.assertIsNone(ada_principal([{"source": "onerpm", "adapter_version": EVIDENCE_VERSION}], ["Principal"]))
        self.assertIsNone(ada_principal([{"source": "ada", "adapter_version": "future-version"}], ["Principal"]))

    def test_unknown_grammar_does_not_fall_back_to_another_parser(self):
        after = enrich_ada_catalog(catalog(), native(["First and Second"]))
        row = after.row(0, named=True)
        suggestions = artist_suggestions(row["asset_isrc"], None, row["artist_statement"], row["catalog_artists"], row["catalog_artist_evidence"])
        self.assertEqual(suggestions["artists"], [])
        self.assertTrue(suggestions["principal_uncertain"])
        self.assertEqual(row["amount_usd"], 100.0)

    def test_native_product_stays_separate(self):
        before = catalog().with_columns(pl.lit("ADA:99500:CATALOG:ALBUM").alias("catalog_key"), pl.lit(None, dtype=pl.String).alias("asset_isrc"))
        self.assertTrue(before.equals(enrich_ada_catalog(before, native(["Principal & Guest"]))))

    def test_no_unapproved_control_tolerance(self):
        self.assertEqual(control_disposition({"earnings_control_status": "equal"}), "equal")
        row = {"earnings_control_status": "different", "source_rule_version": "ADA-LECTURA-1", "ada_account_id": "99205",
               "statement_period": "2025-12", "statement_file_hash": known_controls()["file_sha256"], "source_row": 995,
               "statement_file_name": "99205_202512_202512_99205_DTL.xlsx", "Receipts Value": "0.1",
               "Distribution Fees": "0.01", "Royalty Earnings": "0.09", "native_net": "0.09"}
        self.assertEqual(control_disposition(row), "review_required")

    def test_actual_ingestion_writes_separate_metadata_and_never_publishes_partial_package(self):
        import ingest_standardized_ada as ingest
        from lib.distributor_policy_store import use_distributor_policy_snapshot
        from scripts.qa.qa_ada_excel_replacement import fixture
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            sources = root / "input"
            output = root / "marts/standardized_raw_ada.parquet"
            parts = root / "parts"
            assert parts.resolve().is_relative_to(root)
            for folder, account in [("mawz", "99205"), ("Indyana Records", "99500")]:
                (sources / folder).mkdir(parents=True)
                fixture(sources / folder / f"{account}_202607_202607_{account}_DTL.xlsx", account=account)
            policy = {"schema_version": 1, "policy_version": 1, "entries": [
                {"source": "ada", "account": account, "sheet_rules": {"royalty_detail": {
                    "revenue_basis": "generation", "cash_view": True, "catalog_view": True, "statement_view": True}}}
                for account in ["mawz", "indyana_records"]]}
            with use_distributor_policy_snapshot(policy), patch.object(ingest, "INPUT_ROOT", sources), \
                    patch.object(ingest, "OUTPUT_PATH", output), patch.object(ingest, "TEMP_DIR", parts):
                ingest.main()
                files = [output, output.with_name("catalog_ada_artists.parquet"), output.with_name("ada_native_evidence.parquet")]
                previous = {path: path.read_bytes() for path in files}
                actual = pl.read_parquet(output)
                self.assertEqual(actual.height, 2)
                self.assertEqual(actual["amount_usd"].sum(), .378)
                self.assertNotIn("Royalty Earnings", actual.columns)
                self.assertEqual(pl.read_parquet(files[1]).height, 2)
                self.assertEqual(pl.read_parquet(files[2])["observation_id"].n_unique(), 2)
                fixture(sources / "Indyana Records/99500_202607_202607_99500_DTL.xlsx", {"Royalty Earnings": .188})
                self.assertTrue(parts.resolve().is_relative_to(root))
                with self.assertRaisesRegex(ValueError, "requiere revision"):
                    ingest.main()
                self.assertTrue(all(path.read_bytes() == value for path, value in previous.items()))


if __name__ == "__main__":
    unittest.main()
