"""Cross-source regression tests: incremental readers cannot erase native proof."""
from copy import deepcopy
import json
import unittest

import polars as pl
from polars.testing import assert_frame_equal

from scripts.lib.catalog_artist_evidence import (
    assert_other_sources_preserved, enrich_checked, records, replace_source,
)
from scripts.lib.catalog_ingestion_review import reading_incidents
from scripts.lib.fuga_catalog_artists import enrich_fuga_catalog
from scripts.lib.soundon_catalog_artists import enrich_soundon_catalog
from app.master_contract_participants import soundon_suggestions


ISRC = "ARABC2600001"


def catalog(artists=None, evidence=None, **extra):
    return pl.DataFrame([{"catalog_key": "ISRC:" + ISRC, "asset_isrc": ISRC,
        "artist_statement": "Lead", "track_title": "Test track", "catalog_artists": artists or ["Lead"],
        "catalog_artist_statement": " / ".join(artists or ["Lead"]),
        "catalog_artist_rule": "SOUNDON-LECTURA-1", "catalog_artist_evidence": json.dumps(evidence or []),
        "amount_usd": -123.456789, "units": 100, "upcs": "001234", **extra}],
        schema_overrides={"catalog_artists": pl.List(pl.String)})


def fuga(artist="Lead", album="Lead"):
    return pl.DataFrame([{"source": "fuga", "account": "indyana_records", "asset_isrc": ISRC,
        "Asset Artist": artist, "Product Artist": album, "Product Reference": "123", "Asset Reference": "456",
        "Product UPC": "001234", "statement_period": "2026-07", "statement_file_name": "July2026.csv",
        "statement_file_hash": "b" * 64}]).lazy()


def soundon():
    return pl.DataFrame([{"source": "soundon", "account": "soundon", "source_sheet": "my_royalty",
        "asset_isrc": ISRC, "ISRC": ISRC, "Track Artists": "Lead,Guest", "Track ID": "987", "UPC Code": "001234",
        "Reporting Period": "2026-07", "statement_period": "2026-07", "statement_file_hash": "a" * 64,
        "statement_file_name": "SoundOn_royalty_monthly_statement_2026_07_My Royalty.csv"}]).lazy()


class CatalogArtistEvidenceTests(unittest.TestCase):
    def test_fuga_refresh_retains_every_other_source_record_and_rule(self):
        proof = [{"source": source, "field": "Native track credit", "raw": "Lead,Guest",
                  "used_for_catalog": True, "artists": ["Lead", "Guest"], "opaque": {"literal": "unchanged"}}
                 for source in ("onerpm", "ada", "orchard", "soundon", "dashgo")]
        before = catalog(["Lead", "Guest"], proof)
        before = before.with_columns(pl.lit("FUGA-ARTISTS-1 | SOUNDON-LECTURA-1").alias("catalog_artist_rule"))
        result = enrich_fuga_catalog(before, fuga())
        remaining = [entry for entry in records(result["catalog_artist_evidence"][0]) if entry.get("source") != "fuga"]
        self.assertEqual(remaining, proof)
        self.assertIn("SOUNDON-LECTURA-1", result["catalog_artist_rule"][0])
        self.assertNotIn("FUGA-ARTISTS-1", result["catalog_artist_rule"][0])
        assert_frame_equal(before.drop("catalog_artist_rule", "catalog_artist_evidence"),
                           result.drop("catalog_artist_rule", "catalog_artist_evidence"))

    def test_fuga_does_not_clear_fiches_absent_from_its_input(self):
        before = catalog(evidence=[{"source": "ada", "artists": ["Lead"]}]).with_columns(
            pl.lit("ARXYZ2600002").alias("asset_isrc"))
        assert_frame_equal(before, enrich_fuga_catalog(before, fuga()))

    def test_album_only_name_is_not_removed_if_another_source_uses_it_as_track_artist(self):
        before = catalog(["Lead", "Guest"], [{"source": "onerpm", "field": "Artists",
            "artists": ["Lead", "Guest"], "used_for_catalog": True}])
        self.assertEqual(enrich_fuga_catalog(before, fuga(album="Lead and Guest"))["catalog_artists"][0].to_list(), ["Lead", "Guest"])

    def test_album_context_without_native_track_proof_does_not_add_a_participant(self):
        result = enrich_fuga_catalog(catalog(), fuga(album="Lead and Album Guest"))
        self.assertEqual(result["catalog_artists"][0].to_list(), ["Lead"])

    def test_replay_does_not_duplicate_source_evidence(self):
        before = enrich_soundon_catalog(catalog(), soundon())
        once = enrich_fuga_catalog(before, fuga())
        twice = enrich_fuga_catalog(once, fuga())
        assert_frame_equal(once, twice)

    def test_later_fuga_keeps_soundon_alternative_and_contract_suggestion(self):
        before = enrich_soundon_catalog(catalog(), soundon())
        after = enrich_fuga_catalog(before, fuga())
        row = after.row(0, named=True)
        evidence = records(row["catalog_artist_evidence"])
        suggestion = soundon_suggestions({"artists": ["Lead"], "evidence": [], "warnings": []},
            evidence, row["catalog_artists"], None, isrc=ISRC)
        self.assertEqual(suggestion["artists"], ["Lead", "Guest"])
        self.assertEqual(suggestion["participant_resolution_status"], "cross_source_membership_difference")
        self.assertEqual(reading_incidents(after)[0]["code"], "PARTICIPANTS_DIFFERENCE")
        self.assertEqual(after["amount_usd"][0], before["amount_usd"][0])
        self.assertEqual(after["catalog_artists"][0].to_list(), ["Lead"])

    def test_soundon_then_fuga_has_same_native_evidence_as_fuga_then_soundon(self):
        a = enrich_fuga_catalog(enrich_soundon_catalog(catalog(), soundon()), fuga())
        b = enrich_soundon_catalog(enrich_fuga_catalog(catalog(), fuga()), soundon())
        signature = lambda frame: {json.dumps(entry, sort_keys=True) for entry in records(frame["catalog_artist_evidence"][0])}
        self.assertEqual(signature(a), signature(b))

    def test_guard_rejects_lost_or_rewritten_proof_from_any_other_source(self):
        for source in ("fuga", "onerpm", "ada", "orchard", "soundon", "dashgo"):
            before = catalog(evidence=[{"source": source, "raw": "literal"}])
            with self.subTest(source=source):
                for replacement in ([], [{"source": source, "raw": "changed"}]):
                    with self.assertRaisesRegex(ValueError, "evidence was lost or changed"):
                        assert_other_sources_preserved(before, catalog(evidence=replacement), "another-reader")

    def test_guard_allows_own_source_refresh_but_not_identity_loss(self):
        before = catalog(evidence=[{"source": "fuga", "raw": "old"}])
        assert_other_sources_preserved(before, catalog(evidence=[{"source": "fuga", "raw": "new"}]), "fuga")
        with self.assertRaisesRegex(ValueError, "identity disappeared"):
            assert_other_sources_preserved(before, before.with_columns(pl.lit("OTHER").alias("catalog_key")), "fuga")

    def test_checked_step_rejects_a_reader_that_clears_another_source(self):
        before = catalog(evidence=[{"source": "soundon", "raw": "Lead,Guest"}])
        with self.assertRaises(ValueError):
            enrich_checked(before, "fuga", lambda frame: frame.with_columns(pl.lit("[]").alias("catalog_artist_evidence")))

    def test_source_writer_cannot_claim_another_source(self):
        with self.assertRaises(ValueError):
            replace_source("[]", "fuga", [{"source": "soundon"}])

    def test_invalid_evidence_is_rejected_not_silently_dropped(self):
        for value in ("{}", "[null]", "[1]", "not-json"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                records(value)

    def test_unknown_proof_and_duplicate_observations_are_preserved(self):
        proof = [{"field": "legacy credit", "raw": "unknown source"}] * 2
        after = records(replace_source(json.dumps(proof), "fuga", [{"source": "fuga"}]))
        self.assertEqual(after[:2], proof)

    def test_new_native_name_requires_review_but_order_and_partial_source_do_not(self):
        for source in ("soundon", "orchard", "dashgo"):
            entry = {"source": source, "account": "test", "identity_status": "resolved",
                     "native_resolution_status": "as_reported", "field": "Track Artists", "native_artists": ["Lead", "Guest"]}
            with self.subTest(source=source):
                self.assertEqual(reading_incidents(catalog(evidence=[entry]))[0]["code"], "PARTICIPANTS_DIFFERENCE")
                self.assertEqual(reading_incidents(catalog(["Guest", "Lead"], [entry])), [])
                entry["native_artists"] = ["Lead"]
                self.assertEqual(reading_incidents(catalog(["Lead", "Guest"], [entry])), [])

    def test_approved_dictionary_alias_does_not_make_a_missing_participant(self):
        proof = {"source": "onerpm", "field": "Artists", "identity_status": "resolved",
                 "native_resolution_status": "resolved", "artists": ["Matias Mareco DJ"]}
        self.assertEqual(reading_incidents(catalog(["Matias Mareco"], [proof])), [])

    def test_confirmed_manual_metadata_does_not_reopen_an_old_difference(self):
        entry = {"source": "soundon", "identity_status": "resolved", "native_resolution_status": "as_reported",
                 "native_artists": ["Lead", "Guest"]}
        before = catalog(evidence=[entry], catalog_manual_correction_id="CONFIRMED")
        self.assertEqual(reading_incidents(before), [])


if __name__ == "__main__":
    unittest.main()
