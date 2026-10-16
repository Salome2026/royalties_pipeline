from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import polars as pl
from polars.testing import assert_frame_equal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.onerpm_catalog_artists import ARTIST_COLUMNS, enrich_onerpm_catalog, parse_credits, resolve, read_onerpm_metadata


def observation(raw="A(performer), B(featuring)", **patch):
    return {"parsed": parse_credits(raw), "raw": raw, "level": "track", "identity_status": "resolved",
            "sheet": "Masters", "account": "future_account", "statement": "2026-01", "file": "2026-01-01.xlsx",
            "file_hash": "f" * 64, "row": 2, "product_type": "Track", "upc": "123456789012", **patch}


class CatalogTests(unittest.TestCase):
    def test_noncertified_workbook_stops_before_partial_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "2026-01-report.xlsm").touch()
            with self.assertRaisesRegex(ValueError, "XLSX"):
                read_onerpm_metadata(root)

    def test_unknown_account_stops_before_reading_workbook(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "unconfigured_account"
            folder.mkdir()
            (folder / "2026-01-report.xlsx").touch()
            with self.assertRaisesRegex(ValueError, "cuenta no configurada"):
                read_onerpm_metadata(root, allowed_accounts={"gusty_dj"})

    def test_performer_featuring_not_writer(self):
        self.assertEqual(parse_credits("A(performer), B(featuring), C(writer)")["artists"], ["A", "B"])

    def test_unknown_role_does_not_delete_performer(self):
        self.assertEqual(parse_credits("New(performer), Other(new_role)")["artists"], ["New"])

    def test_bad_serialization_not_exposed_as_people(self):
        self.assertEqual(parse_credits("A(performer), bad fragment")["artists"], [])

    def test_chain_completes_not_intersects(self):
        result = resolve([observation("A(performer)"), observation()])
        self.assertEqual(result["artists"], ["A", "B"])

    def test_incomparable_never_fabricates_union(self):
        result = resolve([observation(), observation("A(performer), C(featuring)")])
        self.assertEqual(result["status"], "contradictory")

    def test_same_people_different_main_keeps_names(self):
        result = resolve([observation(), observation("B(performer), A(featuring)")])
        self.assertEqual(set(result["artists"]), {"A", "B"})
        self.assertEqual(result["principal_status"], "uncertain")

    def test_shares_order_not_main(self):
        result = resolve([observation(sheet="Shares In & Out")])
        self.assertEqual(result["principal_status"], "unknown")

    def test_order_independent(self):
        rows = [observation(), observation("A(performer)")]
        self.assertEqual(resolve(rows), resolve(list(reversed(rows))))

    def test_accent_only_normalization_not_dj_alias(self):
        self.assertEqual(parse_credits("Jos\u00e9(performer), Jose(featuring)")["artists"], ["Jos\u00e9"])
        self.assertEqual(resolve([observation("Matias(performer)"), observation("Matias DJ(performer)")])["status"], "contradictory")

    def test_enrichment_preserves_legacy_and_money_and_is_idempotent(self):
        catalog = pl.DataFrame({"catalog_key": ["ISRC:XXAAA2500001"], "asset_isrc": ["XXAAA2500001"],
            "artist_statement": ["A"], "track_title": ["Title"], "amount_usd": [12.3], "upcs": ["123456789012"],
            "artist_variants": ["A"], **{name: [None] for name in ARTIST_COLUMNS}},
            schema_overrides=ARTIST_COLUMNS)
        row = {"asset_isrc": "XXAAA2500001", "catalog_artists": ["A", "B"], "status": "resolved",
               "principal": "A", "principal_status": "order_only", "evidence": json.dumps([observation()])}
        with tempfile.TemporaryDirectory() as temporary:
            corrections = Path(temporary) / "corrections.json"
            corrections.write_text('{"corrections": []}', encoding="utf-8")
            native = pl.DataFrame([row], schema_overrides={"catalog_artists": pl.List(pl.String)})
            result = enrich_onerpm_catalog(catalog, native, corrections_path=corrections)
            self.assertEqual(result["catalog_artists"].to_list(), [["A", "B"]])
            assert_frame_equal(result.drop(list(ARTIST_COLUMNS)), catalog.drop(list(ARTIST_COLUMNS)))
            assert_frame_equal(result, enrich_onerpm_catalog(result, native, corrections_path=corrections))


if __name__ == "__main__":
    unittest.main()
