import json
import sys
import tempfile
import unittest
from pathlib import Path

import polars as pl
from polars.testing import assert_frame_equal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.catalog_manual_metadata import CORRECTIONS_PATH, apply_catalog_manual_metadata


class CatalogManualMetadataTests(unittest.TestCase):
    def catalog(self):
        return pl.DataFrame({
            "catalog_key": ["ISRC:ARDL12400086", "ISRC:ARDL12400080", "ISRC:OTHER"],
            "asset_isrc": ["ARDL12400086", "ARDL12400080", "OTHER"],
            "track_title": ["ME PIDE CANDY", "ME PIDE CANDY RKT", "ME PIDE CANDY"],
            "artist_statement": ["FACUU DJ", "FACUU DJ", "Unrelated artist"],
            "track_title_normalized": ["me pide candy", "me pide candy rkt", "me pide candy"],
            "artist_statement_normalized": ["facuu dj", "facuu dj", "unrelated artist"],
            "title_variants": ["ME PIDE CANDY | TU PONES LA HORA", "ME PIDE CANDY RKT", "ME PIDE CANDY"],
            "amount_usd": [80.929092, 0.261616, -1.5],
            "units": [230867.0, 0.0, 10.0],
            "upcs": ["8721253044475", "8721093910459", "OTHER"],
        })

    def test_exact_isrc_display_correction_preserves_economy_and_evidence(self):
        before = self.catalog()
        after = apply_catalog_manual_metadata(before)
        corrected = after.row(0, named=True)
        self.assertEqual("TU PONES LA HORA", corrected["track_title"])
        self.assertEqual("FACUU DJ and LAALODJ", corrected["artist_statement"])
        self.assertEqual(135, corrected["catalog_duration_seconds"])
        self.assertEqual("tu pones la hora", corrected["track_title_normalized"])
        self.assertEqual("FUGA-META-ARDL12400086-20261013", corrected["catalog_manual_correction_id"])
        protected = ["catalog_key", "asset_isrc", "title_variants", "amount_usd", "units", "upcs"]
        assert_frame_equal(before.select(protected), after.select(protected))
        assert_frame_equal(before.slice(1), after.select(before.columns).slice(1))
        self.assertIsNone(after.row(1, named=True)["catalog_manual_correction_id"])

    def test_reapply_is_idempotent(self):
        once = apply_catalog_manual_metadata(self.catalog())
        assert_frame_equal(once, apply_catalog_manual_metadata(once))

    def test_no_target_does_not_change_schema_or_values(self):
        catalog = self.catalog().slice(1)
        assert_frame_equal(catalog, apply_catalog_manual_metadata(catalog))

    def test_duplicate_corrections_fail(self):
        document = json.loads(CORRECTIONS_PATH.read_text(encoding="utf-8"))
        document["corrections"] *= 2
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "corrections.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                apply_catalog_manual_metadata(self.catalog(), corrections_path=path)


if __name__ == "__main__":
    unittest.main()
