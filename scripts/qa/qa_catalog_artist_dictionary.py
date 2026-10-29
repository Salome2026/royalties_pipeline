"""Approved aliases must precede credit comparisons, not financial identity."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "scripts/qa")]

import polars as pl
from polars.testing import assert_frame_equal

from lib.catalog_artist_dictionary import canonical, comparison_key, unique
from lib import ada_catalog_artists, dashgo_catalog_artists, fuga_catalog_artists
from lib import onerpm_catalog_artists, orchard_catalog_artists, soundon_catalog_artists
from lib.catalog_artist_extensions import credit_identity_evidence
from lib.soundon_identity import artist_key as source_identity_key
from app.master_contracts import artist_key as contractual_key, artist_suggestions
from app.master_contract_participants import propose_participants
from qa_onerpm_catalog_artists import observation
import qa_dashgo_catalog_artists as dashgo_fixture
import qa_soundon_catalog_artists as soundon_fixture


class ArtistDictionaryTests(unittest.TestCase):
    def test_only_confirmed_equivalences(self):
        self.assertEqual(canonical("Matias Mareco DJ"), "Matias Mareco")
        self.assertEqual(canonical("DJ Alan Gomez"), "Alan Gomez")
        self.assertEqual(unique(["DJ Alan Gomez", "Alan Gomez", "Another DJ"]), ["Alan Gomez", "Another DJ"])
        for name in ("Matias DJ", "DJ New Artist", "El Mago y La Luna", "DJ Alan Gomez Remix"):
            self.assertEqual(canonical(name), name)

    def test_all_six_metadata_comparators_use_approved_dictionary(self):
        comparators = [fuga_catalog_artists.name_key, onerpm_catalog_artists.name_key,
            ada_catalog_artists.name_key, orchard_catalog_artists.name_key,
            soundon_catalog_artists.artist_key, dashgo_catalog_artists.artist_key]
        for key in comparators:
            with self.subTest(module=key.__module__):
                self.assertEqual(key("Matias Mareco DJ"), key("Matias Mareco"))
                self.assertEqual(key("DJ Alan Gomez"), key("Alan Gomez"))
                self.assertNotEqual(key("DJ Another"), key("Another"))

    def test_contractual_and_source_identity_keys_are_not_merged(self):
        for key in (contractual_key, source_identity_key):
            self.assertNotEqual(key("Matias Mareco DJ"), key("Matias Mareco"))
            self.assertNotEqual(key("DJ Alan Gomez"), key("Alan Gomez"))

    def test_fuga_other_accent_semantics_unchanged(self):
        self.assertNotEqual(fuga_catalog_artists.name_key("Jos\u00e9"), fuga_catalog_artists.name_key("Jose"))

    def test_future_onerpm_statement_alias_does_not_hide_participants(self):
        old = observation("Matias Mareco DJ(performer), Lucas Rmx(performer), DJ Bryanflow(performer), Matias Mareco(writer)", statement="2025-01")
        new = observation("Matias Mareco(performer), Lucas Rmx(performer), DJ Bryanflow(performer), Writer(writer)", statement="2027-01")
        before = deepcopy([old, new])
        result = onerpm_catalog_artists.resolve([old, new])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["artists"], ["Matias Mareco", "Lucas Rmx", "DJ Bryanflow"])
        self.assertEqual(result["principal"], "Matias Mareco")
        self.assertEqual([old, new], before)

    def test_new_names_still_work_without_dictionary_entry(self):
        result = onerpm_catalog_artists.resolve([observation("New Person 2030(performer), Another Person(featuring)")])
        self.assertEqual(result["artists"], ["New Person 2030", "Another Person"])

    def test_unknown_dj_variant_and_real_membership_conflict_remain_uncertain(self):
        for left, right in [("Matias", "Matias DJ"), ("DJ New", "New"), ("DJ Alan Gomez, B", "Alan Gomez, C")]:
            def encoded(value):
                return ", ".join(name.strip() + "(performer)" for name in value.split(","))
            result = onerpm_catalog_artists.resolve([observation(encoded(left)), observation(encoded(right))])
            self.assertEqual(result["status"], "contradictory")

    def test_legacy_contract_suggestions_compare_aliases_before_intersection(self):
        code = "ZZABC2700001"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "raw.parquet"
            literals = ["Matias Mareco DJ(performer), Lucas Rmx(performer), DJ Bryanflow(performer), Writer(writer)",
                        "Matias Mareco(performer), Lucas Rmx(performer), DJ Bryanflow(performer), Writer(writer)"]
            frame = pl.DataFrame({"source": ["onerpm"] * 2, "asset_isrc": [code] * 2,
                "artists_raw": literals, "transaction_month": ["2026-01", "2027-01"], "amount_usd": [10., -1.]})
            frame.write_parquet(path)
            original = path.read_bytes()
            proposed = artist_suggestions(code, path, "")
            self.assertEqual(proposed["artists"], ["Matias Mareco", "Lucas Rmx", "DJ Bryanflow"])
            self.assertFalse(proposed["principal_uncertain"])
            self.assertEqual({row["raw"] for row in proposed["evidence"]}, set(literals))
            self.assertEqual(path.read_bytes(), original)

    def test_resolved_onerpm_list_and_display_are_populated_without_money_change(self):
        fields = onerpm_catalog_artists.ARTIST_COLUMNS
        catalog = pl.DataFrame({"catalog_key": ["ISRC:ZZABC2700001"], "asset_isrc": ["ZZABC2700001"],
            "artist_statement": ["Matias Mareco, Lucas Rmx"], "amount_usd": [33.805825],
            "units": [28004.], **{name: [None] for name in fields}}, schema_overrides=fields)
        observations = [observation("Matias Mareco DJ(performer), Lucas Rmx(performer)"),
                        observation("Matias Mareco(performer), Lucas Rmx(performer)", statement="2027-01")]
        resolved = onerpm_catalog_artists.resolve(observations)
        native = pl.DataFrame([{**resolved, "asset_isrc": "ZZABC2700001", "catalog_artists": resolved["artists"],
            "evidence": json.dumps(observations)}], schema_overrides={"catalog_artists": pl.List(pl.String)})
        result = onerpm_catalog_artists.enrich_onerpm_catalog(catalog, native)
        self.assertEqual(result["catalog_artists"].to_list(), [["Matias Mareco", "Lucas Rmx"]])
        self.assertEqual(result["catalog_artist_statement"][0], "Matias Mareco / Lucas Rmx")
        assert_frame_equal(result.drop(list(fields)), catalog.drop(list(fields)))
        assert_frame_equal(result, onerpm_catalog_artists.enrich_onerpm_catalog(result, native))

    def test_soundon_aliases_keep_native_credit_literals_and_valid_provenance(self):
        out, _, _ = soundon_fixture.consume(["Matias Mareco DJ,B", "Matias Mareco,B"], ["Matias Mareco", "B"])
        row = out.row(0, named=True)
        proposed = artist_suggestions(soundon_fixture.ISRC, None, row["artist_statement"],
            row["catalog_artists"], row["catalog_artist_evidence"])
        self.assertEqual(set(proposed["artists"]), {"Matias Mareco", "B"})
        self.assertFalse(proposed["principal_uncertain"])
        evidence = json.loads(row["catalog_artist_evidence"])[0]
        self.assertEqual({r["Track Artists"] for r in evidence["observations"]}, {"Matias Mareco DJ,B", "Matias Mareco,B"})

    def test_dashgo_aliases_accept_approved_dictionary_but_not_forged_credit(self):
        out, _, _ = dashgo_fixture.consume(["DJ Alan Gomez", "Alan Gomez"], ["Alan Gomez"])
        row = out.row(0, named=True)
        proposed = artist_suggestions(dashgo_fixture.ISRC, None, row["artist_statement"], row["catalog_artists"], row["catalog_artist_evidence"])
        self.assertEqual(proposed["artists"], ["Alan Gomez"])
        self.assertFalse(proposed["principal_uncertain"])
        entry = credit_identity_evidence(json.loads(row["catalog_artist_evidence"]))[0]
        self.assertTrue(dashgo_catalog_artists.valid_dashgo_evidence(entry, dashgo_fixture.ISRC))
        entry["observations"][0]["artists"] = ["Different Person"]
        self.assertFalse(dashgo_catalog_artists.valid_dashgo_evidence(entry, dashgo_fixture.ISRC))

    def test_closed_contract_payload_is_not_rewritten_by_suggestions(self):
        saved = {"closed": True, "split": {"principal": "Matias Mareco DJ", "principal_percent": 30,
            "indyana_percent": 70, "participants": [], "code_association_overrides": [{"key": "original", "included": False}]}}
        before = deepcopy(saved)
        split, _ = propose_participants({}, ["Matias Mareco", "Lucas Rmx"], saved=saved, history=[])
        self.assertEqual(saved, before)
        self.assertEqual(split, before["split"])


if __name__ == "__main__":
    unittest.main()
