from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import polars as pl
from polars.testing import assert_frame_equal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.catalog_identity_references import materialize_identity_references
from lib.onerpm_catalog_artists import (
    materialize_onerpm_identity_file, enrich_onerpm_catalog, parse_credits, ARTIST_COLUMNS,
)


def reference(code="XXAAA2500002", **patch):
    return {"isrc": code, "title": "New track", "source": "onerpm", "level": "track",
            "sheet": "Shares In & Out", "account": "future_account", "statement": "2026-01",
            "file_hash": "f" * 64, "file": "2026-01-01-details.xlsx", "row": 2,
            "upc": "123456789012", "raw": "A(performer), B(featuring), Writer(writer)",
            "parsed": parse_credits("A(performer), B(featuring), Writer(writer)"),
            "identity_status": "resolved", "product_type": "Track", **patch}


def catalog():
    return pl.DataFrame({"catalog_key": ["ISRC:XXAAA2500001", "VIDEO:abcdefghijk"],
        "asset_isrc": ["XXAAA2500001", None], "track_title": ["Human title", "Video title"],
        "artist_statement": ["Human artist", "A"], "amount_usd": [10., 25.],
        "primary_upc": [None, None],
        "observed_amount_usd": [10., 25.], "transfer_amount_usd": [0., 0.],
        "units": [1., 2.], "song_level_rows": [1, 2], "catalog_aliases": [[], []],
        "catalog_manual_correction_id": ["manual-1", None],
        **{name: [None, None] for name in ARTIST_COLUMNS}}, schema_overrides={
            **ARTIST_COLUMNS, "catalog_aliases": pl.List(pl.String), "primary_upc": pl.String})


class IdentityTests(unittest.TestCase):
    def test_reference_only_preserves_all_existing_cells_and_money(self):
        before = catalog()
        after = materialize_identity_references(before, [reference()])
        assert_frame_equal(after.head(before.height).select(before.columns), before)
        new = after.tail(1).row(0, named=True)
        for field in ["amount_usd", "observed_amount_usd", "transfer_amount_usd", "units", "song_level_rows"]:
            self.assertEqual(new[field], 0)
        self.assertTrue(new["catalog_identity_reference_only"])
        self.assertEqual(after["amount_usd"].sum(), 35.)
        self.assertEqual(new["catalog_aliases"], [])
        self.assertIsNone(new["primary_upc"])
        self.assertEqual(new["catalog_identity_upcs"], ["123456789012"])
        self.assertEqual(json.loads(new["catalog_identity_evidence"])[0]["row"], 2)

    def test_same_title_different_isrc_remains_two_recordings(self):
        result = materialize_identity_references(catalog(), [reference(), reference("XXAAA2500003")])
        self.assertEqual(result.height, 4)
        self.assertEqual(result.tail(2)["asset_isrc"].n_unique(), 2)

    def test_repeated_months_sources_and_rebuild_do_not_duplicate(self):
        refs = [reference(), reference(statement="2026-02"), reference(), reference(source="future_provider")]
        first = materialize_identity_references(catalog(), refs)
        self.assertEqual(first.height, 3)
        self.assertEqual(len(json.loads(first.tail(1)["catalog_identity_evidence"][0])), 3)
        assert_frame_equal(first, materialize_identity_references(first, refs))

    def test_existing_manual_fiche_not_overwritten_by_native_metadata(self):
        before = catalog()
        assert_frame_equal(before, materialize_identity_references(before, [reference("XXAAA2500001")]))

    def test_ambiguous_artist_or_upc_does_not_hide_explicit_isrc(self):
        result = materialize_identity_references(catalog(), [reference(upc="invalid", identity_status="incomplete", parsed={"status": "ambiguous"})])
        self.assertEqual(result.height, 3)
        self.assertIsNone(result.tail(1)["primary_upc"][0])
        self.assertIsNone(result.tail(1)["artist_statement"][0])

    def test_no_album_or_fuzzy_identity_is_accepted(self):
        for patch in [{"level": "album"}, {"isrc": "abcdefghijk"}, {"file_hash": None}]:
            with self.assertRaises(ValueError):
                materialize_identity_references(catalog(), [reference(**patch)])

    def test_provider_file_materializes_shares_and_role_aware_enrichment(self):
        obs = reference()
        native = pl.DataFrame([{"asset_isrc": obs["isrc"], "evidence": json.dumps([obs]),
            "catalog_artists": ["A", "B"], "status": "resolved", "principal": None,
            "principal_status": "unknown"}], schema_overrides={"catalog_artists": pl.List(pl.String)})
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "native.parquet"
            native.write_parquet(path)
            corrections = Path(temporary) / "corrections.json"
            corrections.write_text('{"corrections": []}', encoding="utf8")
            result = materialize_onerpm_identity_file(catalog(), path)
            result = enrich_onerpm_catalog(result, native, corrections_path=corrections)
            self.assertEqual(result.tail(1)["catalog_artists"][0].to_list(), ["A", "B"])
            self.assertEqual(result.tail(1)["artist_statement"][0], "A, B")
            self.assertNotIn("Writer", result.tail(1)["catalog_artists"][0].to_list())

    def test_future_catalog_rebuild_consumes_references_before_release_and_manual_metadata(self):
        import build_catalog_master as builder
        from lib.distributor_policy_store import use_distributor_policy_snapshot
        # Run the real catalog builder on a future generation plus Shares-only
        # recording. External enrichment is isolated; no operational writes.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pl.DataFrame({"source": ["onerpm"], "account": ["future_account"],
                "source_sheet": ["Masters"], "revenue_basis": ["generation"],
                "asset_isrc": ["XXAAA2500001"], "track_statement_style": ["Known"],
                "artist_statement_style": ["A"], "transaction_month": ["2026-01"],
                "amount_usd": [35.], "units": [3.]}).write_parquet(root / "songs.parquet")
            obs = reference()
            pl.DataFrame([{"asset_isrc": obs["isrc"], "evidence": json.dumps([obs]),
                "catalog_artists": ["A", "B"], "status": "resolved", "principal": None,
                "principal_status": "unknown"}], schema_overrides={"catalog_artists": pl.List(pl.String)}).write_parquet(root / builder.METADATA_FILE)
            policy = {"schema_version": 1, "policy_version": 1, "entries": [{
                "source": "onerpm", "account": "future_account", "sheet_rules": {
                    "Masters": {"catalog_view": True, "revenue_basis": "generation"}}}]}
            stages = []
            def manual(frame):
                self.assertIn(obs["isrc"], frame["asset_isrc"].to_list())
                stages.append("manual")
                return frame.with_columns(pl.when(pl.col("asset_isrc") == obs["isrc"])
                    .then(pl.lit("Manual title")).otherwise(pl.col("track_title")).alias("track_title"))
            from contextlib import ExitStack
            with ExitStack() as stack:
                stack.enter_context(use_distributor_policy_snapshot(policy))
                for name, value in {"MARTS_DIR": root, "SONG_LEVEL_PATH": root / "songs.parquet",
                    "build_identity_alias_lookup": lambda: pl.DataFrame(),
                    "build_identity_lookup": lambda: pl.DataFrame(),
                    "build_release_lookup": lambda: pl.DataFrame(),
                    "apply_catalog_manual_metadata": manual,
                    **{name: (lambda frame, *args: frame) for name in [
                        "enrich_fuga_catalog_file", "apply_automatic_extended", "enrich_ada_catalog_file",
                        "enrich_orchard_catalog_file", "enrich_soundon_catalog_file", "enrich_dashgo_catalog_file"]}}.items():
                    stack.enter_context(patch.object(builder, name, value))
                result = builder.build_catalog_master()
            self.assertEqual(stages, ["manual"])
            self.assertEqual(result.height, 2)
            self.assertEqual(result["amount_usd"].sum(), 35.)
            added = result.filter(pl.col("asset_isrc") == obs["isrc"])
            self.assertEqual(added["track_title"][0], "Manual title")
            self.assertEqual(added["catalog_artists"][0].to_list(), ["A", "B"])


if __name__ == "__main__":
    unittest.main()
