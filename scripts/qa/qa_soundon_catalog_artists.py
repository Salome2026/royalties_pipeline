from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

import polars as pl

sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]
from lib.soundon_catalog_artists import ARTIST_COLUMNS, EVIDENCE_VERSION, collect_soundon_artists, enrich_soundon_catalog
from app.master_contract_participants import soundon_suggestions, propose_participants


ISRC = "ARABC2600001"


def frame(credits=None, **overrides):
    rows = []
    for index, credit in enumerate(credits or ["A,B"]):
        rows.append({"source": "soundon", "account": "soundon", "source_sheet": "my_royalty",
            "asset_isrc": ISRC, "ISRC": ISRC, "Track Artists": credit, "Track ID": str(index), "UPC Code": "001234",
            "Reporting Period": "2026-07", "statement_period": "2026-07", "statement_file_hash": "a" * 64,
            "statement_file_name": "SoundOn_royalty_monthly_statement_2026_07_My Royalty.csv", **overrides})
    return pl.DataFrame(rows).lazy()


def catalog(prior=None, **overrides):
    return pl.DataFrame([{"catalog_key": "ISRC:" + ISRC, "asset_isrc": ISRC, "artist_statement": "Existing economic credit",
        "catalog_artists": prior, "catalog_artist_statement": " / ".join(prior) if prior else None,
        "catalog_artist_evidence": None, "catalog_artist_rule": None, "amount_usd": 123.45, **overrides}],
        schema_overrides=ARTIST_COLUMNS)


def consume(credits=None, prior=None, raw=None, **kwargs):
    result = enrich_soundon_catalog(catalog(prior, **kwargs), frame(credits))
    row = result.row(0, named=True)
    evidence = json.loads(row["catalog_artist_evidence"])
    suggestions = soundon_suggestions({"artists": row["catalog_artists"], "evidence": [], "warnings": [], "principal_uncertain": True},
        evidence, row["catalog_artists"], raw, isrc=ISRC)
    return result, evidence, suggestions


class SoundOnCatalogTests(unittest.TestCase):
    def test_new_credit_and_unknown_artists(self):
        result, _, proposed = consume(["Never Seen,New Group"])
        self.assertEqual(result["catalog_artists"][0].to_list(), ["Never Seen", "New Group"])
        self.assertEqual(proposed["artists"], ["Never Seen", "New Group"])
        self.assertFalse(proposed["principal_uncertain"])

    def test_group_names_intact(self):
        for name in ("ACIT x", "Los Nocheros", "El Mago y La Luna", "Band and Friends", "Earth & Fire"):
            _, _, proposed = consume([name + ",Other"])
            self.assertEqual(proposed["artists"], [name, "Other"])

    def test_name_equivalence_does_not_erase_literal(self):
        _, proof, proposed = consume(["Jos\u00e9,B", "JOSE,B"])
        self.assertFalse(proposed["principal_uncertain"])
        self.assertEqual({row["Track Artists"] for row in proof[0]["observations"]}, {"Jos\u00e9,B", "JOSE,B"})

    def test_native_order_conflict(self):
        _, _, proposed = consume(["A,B", "B,A"])
        self.assertTrue(proposed["principal_uncertain"])
        self.assertEqual(set(proposed["artists"]), {"A", "B"})

    def test_cross_source_subset_is_not_intersected(self):
        result, _, proposed = consume(["A,B"], ["A"])
        self.assertEqual(result["catalog_artists"][0].to_list(), ["A"])
        self.assertEqual(proposed["artists"], ["A", "B"])
        self.assertEqual(proposed["participant_resolution_status"], "cross_source_membership_difference")
        self.assertFalse(proposed["principal_uncertain"])

    def test_cross_source_superset_is_still_recorded(self):
        _, _, proposed = consume(["A"], ["A", "B"])
        self.assertEqual(proposed["artists"], ["A", "B"])
        self.assertEqual(proposed["participant_resolution_status"], "cross_source_membership_difference")

    def test_incompatible_sets_keep_alternatives(self):
        _, _, proposed = consume(["A,B"], ["A", "C"])
        self.assertEqual(set(proposed["artists"]), {"A", "B", "C"})
        self.assertEqual(proposed["participant_resolution_status"], "conflicting_participants")
        self.assertEqual({tuple(v["artists"]) for v in proposed["participant_alternatives"]}, {("A", "B"), ("A", "C")})

    def test_conflicting_native_sets_keep_reported_members(self):
        _, _, proposed = consume(["A,B", "A,C"])
        self.assertEqual(set(proposed["artists"]), {"A", "B", "C"})
        self.assertTrue(proposed["principal_uncertain"])

    def test_reference_approved_order(self):
        for code in ("QT5M22664077", "QT5M22692699"):
            native = frame(["Candu Dominguez,La Juntada de los Artistas", "La Juntada de los Artistas,Candu Dominguez"], ISRC=code, asset_isrc=code)
            old = catalog().with_columns(pl.lit(code).alias("asset_isrc"), pl.lit("ISRC:" + code).alias("catalog_key"))
            enriched = enrich_soundon_catalog(old, native).row(0, named=True)
            result = soundon_suggestions({"artists": [], "warnings": [], "evidence": []}, json.loads(enriched["catalog_artist_evidence"]), enriched["catalog_artists"], None, isrc=code)
            self.assertEqual(result["artists"], ["La Juntada de los Artistas", "Candu Dominguez"])
            self.assertFalse(result["principal_uncertain"])

    def test_reference_mismatch_keeps_new_name(self):
        code = "QT5M22664077"
        observed = collect_soundon_artists(frame(["La Juntada de los Artistas,Candu Dominguez,New Guest"], ISRC=code, asset_isrc=code))[code]
        self.assertEqual(observed["native_resolution_status"], "reference_mismatch")
        self.assertIn("New Guest", observed["artists_reported"])

    def test_identity_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            collect_soundon_artists(frame(ISRC="ARABC2600002"))

    def test_invalid_isrc_not_repaired(self):
        with self.assertRaises(ValueError):
            collect_soundon_artists(frame(ISRC="AR-ABC-26-00001", asset_isrc="AR-ABC-26-00001"))

    def test_account_and_nonempty_shares_guarded(self):
        for change in ({"account": "unknown"}, {"source_sheet": "share_in"}, {"source_sheet": "share_out"}):
            with self.assertRaises(ValueError):
                collect_soundon_artists(frame(**change))

    def test_incomplete_provenance_rejected(self):
        for change in ({"statement_file_hash": "bad"}, {"statement_file_name": ""}, {"statement_period": "2026-08"}, {"Reporting Period": "2026-08"}):
            with self.assertRaises(ValueError):
                collect_soundon_artists(frame(**change))

    def test_other_sources_untouched(self):
        old = catalog(["A"])
        self.assertTrue(old.equals(enrich_soundon_catalog(old, frame(source="ada"))))

    def test_prior_evidence_preserved(self):
        prior = [{"source": "fuga", "field": "Asset Artist", "artists": ["A"]}]
        _, proof, proposed = consume(["A,B"], ["A"], catalog_artist_evidence=json.dumps(prior))
        self.assertEqual(proof[0], prior[0])
        self.assertFalse(proposed["principal_uncertain"])

    def test_wrong_fuga_principal_not_suppressed(self):
        prior = [{"source": "fuga", "field": "Asset Artist", "artists": ["B", "A"]}]
        _, _, proposed = consume(["A,B"], ["A", "B"], catalog_artist_evidence=json.dumps(prior))
        self.assertTrue(proposed["principal_uncertain"])

    def test_raw_uncertainty_not_suppressed(self):
        self.assertTrue(consume(raw={"principal_uncertain": True})[2]["principal_uncertain"])

    def test_broken_evidence_does_not_supply_names(self):
        _, proof, _ = consume()
        original = {"artists": ["A"], "principal_uncertain": True, "warnings": []}
        for mutation in ("hash", "identity", "artists"):
            changed = copy.deepcopy(proof)
            if mutation == "hash":
                changed[0]["observations"][0]["statement_file_hash"] = "bad"
            elif mutation == "identity":
                changed[0]["asset_isrc"] = "ARABC2600002"
            else:
                changed[0]["native_artists"].append("Not evidenced")
            result = soundon_suggestions(original, changed, ["A"], None, isrc=ISRC)
            self.assertEqual(result["artists"], ["A"])
            self.assertTrue(result["principal_uncertain"])

    def test_source_absence_delegates(self):
        self.assertIsNone(soundon_suggestions({}, [], ["A"], None, isrc=ISRC))

    def test_bad_json_shape_not_adopted(self):
        with self.assertRaises(ValueError):
            consume(catalog_artist_evidence='{"source":"experimental"}')

    def test_repeat_merge_idempotent(self):
        result, _, _ = consume()
        self.assertTrue(result.equals(enrich_soundon_catalog(result, frame())))

    def test_financial_columns_untouched(self):
        old = catalog()
        candidate = enrich_soundon_catalog(old, frame())
        columns = [c for c in old.columns if c not in ARTIST_COLUMNS]
        self.assertTrue(old.select(columns).equals(candidate.select(columns)))

    def test_manual_decision_preserved(self):
        result, proof, _ = consume(["A,B"], ["Human Decision"], catalog_manual_correction_confirmed_by="Ruben")
        self.assertEqual(result["catalog_artists"][0].to_list(), ["Human Decision"])
        self.assertTrue(proof[0]["manual_protected"])

    def test_no_participant_limit_in_evidence(self):
        all_names = [f"Artist {number}" for number in range(14)]
        _, _, proposed = consume([",".join(all_names)])
        split, info = propose_participants({"principal": all_names[0], "participants": []}, proposed["artists"], saved=None, history=[])
        self.assertEqual(len(split["participants"]), 13)
        self.assertTrue(info["capacity_exceeded"])
        self.assertTrue(all(row["percent"] is None for row in split["participants"]))

    def test_missing_fields_rejected(self):
        with self.assertRaises(ValueError):
            collect_soundon_artists(frame().drop("Track Artists"))

    def test_same_track_id_does_not_merge_two_isrc(self):
        a, b = frame(**{"Track ID": "shared"}).collect(), frame(ISRC="ARABC2600002", asset_isrc="ARABC2600002", **{"Track ID": "shared"}).collect()
        collected = collect_soundon_artists(pl.concat([a, b]).lazy())
        self.assertEqual(len(collected), 2)
        for entry in collected.values():
            self.assertEqual(entry["identity_relationship_status"], "conflicting_track_id")
            self.assertEqual(entry["identity_relationship_conflicts"], [{"track_id": "shared", "isrcs": [ISRC, "ARABC2600002"]}])

    def test_other_source_warnings_not_suppressed(self):
        for proof in ({"source": "ada", "adapter_version": "ADA-CAT003-adapter-1"},
                      {"source": "onerpm", "field": "Artists"},
                      {"source": "orchard", "adapter_version": "ORCHARD-CAT003-adapter-1"}):
            _, _, proposed = consume(catalog_artist_evidence=json.dumps([proof]))
            self.assertTrue(proposed["principal_uncertain"], proof)

    def test_reported_string_is_not_a_source_of_invented_names(self):
        _, proof, _ = consume()
        proof[0]["artists_reported"].append("Not evidenced")
        result = soundon_suggestions({"artists": ["A", "B"], "warnings": [], "evidence": []}, proof, ["A", "B"], None, isrc=ISRC)
        self.assertNotIn("Not evidenced", result["artists"])

    def test_month_mismatch_evidence_is_not_trusted(self):
        _, proof, _ = consume()
        proof[0]["observations"][0]["Reporting Period"] = "2026-08"
        result = soundon_suggestions({"artists": ["A"], "warnings": []}, proof, ["A"], None, isrc=ISRC)
        self.assertEqual(result["artists"], ["A"])
        self.assertTrue(result["principal_uncertain"])

    def test_label_or_payee_never_becomes_an_artist(self):
        data = frame().with_columns(pl.lit("Not Artist").alias("Payee"), pl.lit("Another Person").alias("Album Title"))
        entry = collect_soundon_artists(data)[ISRC]
        self.assertEqual(entry["artists_reported"], ["A", "B"])

    def test_record_locator_is_not_csv_line(self):
        _, proof, _ = consume(["A,B", "A,B"])
        self.assertEqual(proof[0]["observation_count"], 2)
        self.assertEqual(proof[0]["observations"][0]["locator_kind"], "standardized_soundon_subset_row")
        self.assertTrue(all("csv_line" not in row for row in proof[0]["observations"]))


if __name__ == "__main__":
    unittest.main()
