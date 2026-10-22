from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

import polars as pl

sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]
from lib.dashgo_catalog_artists import ARTIST_COLUMNS, EVIDENCE_VERSION, NATIVE_FIELDS, collect_dashgo_artists, enrich_dashgo_catalog, valid_dashgo_evidence
from app.master_contract_participants import dashgo_suggestions, propose_participants

ISRC = "ARABC2600001"


def frame(credits=None, **overrides):
    rows = []
    for credit in (["A"] if credits is None else credits):
        row = {name: None for name in NATIVE_FIELDS}
        row.update({"source": "dashgo", "account": "mawzrecords", "asset_isrc": ISRC,
            "ISRC": ISRC, "Track Artist": credit, "Artist Name": credit,
            "Track Title": "A whole title (Cover Live)", "Payable": 1., "Units": 1., "Composers": "Writer",
            "Product Type": "S", "statement_period": "2026-07", "statement_file_hash": "a" * 64,
            "statement_file_name": "MAWZ Records-07-26.csv", **overrides})
        rows.append(row)
    return pl.DataFrame(rows, infer_schema_length=None).lazy()


def catalog(prior=None, **overrides):
    return pl.DataFrame([{"catalog_key": "ISRC:" + ISRC, "asset_isrc": ISRC, "amount_usd": 123.45,
        "artist_statement": "Existing report credit", "catalog_artists": prior,
        "catalog_artist_statement": " / ".join(prior) if prior else None,
        "catalog_artist_evidence": None, "catalog_artist_rule": None, **overrides}], schema_overrides=ARTIST_COLUMNS)


def consume(credits=None, prior=None, raw=None, source=None, **overrides):
    output = enrich_dashgo_catalog(catalog(prior, **overrides), source if source is not None else frame(credits))
    row = output.row(0, named=True)
    evidence = json.loads(row["catalog_artist_evidence"] or "[]")
    result = dashgo_suggestions({"artists": row["catalog_artists"] or [], "warnings": [], "evidence": [], "principal_uncertain": True}, evidence, row["catalog_artists"] or [], raw, isrc=ISRC)
    return output, evidence, result


class DashGoCatalogTests(unittest.TestCase):
    def test_new_name_automatic_without_dictionary(self):
        out, _, result = consume(["New Artist 2029"])
        self.assertEqual(out["catalog_artists"][0].to_list(), ["New Artist 2029"])
        self.assertEqual(result["artists"], ["New Artist 2029"])
        self.assertFalse(result["principal_uncertain"])

    def test_group_and_connector_literals(self):
        for credit in ("Maxi y La Champions Liga", "Earth & Fire", "Band and Friends", "Grupo A, Grupo B", "ACIT x"):
            self.assertEqual(consume([credit])[2]["artists"], [credit])

    def test_metadata_reads_three_preserved_layouts(self):
        for extras in ({}, {"Noise Content (Y/N)": "N"}, {"Noise Content (Y/N)": "N", "Spatial Availability Indicator (Y/N)": "N"}):
            result = collect_dashgo_artists(frame(**extras))
            self.assertEqual(result[ISRC]["native_artists"], ["A"])

    def test_credit_variants_preserve_literals(self):
        _, evidence, result = consume(["Jose", "JOSE"])
        self.assertEqual({r["Track Artist"] for r in evidence[0]["observations"]}, {"Jose", "JOSE"})
        self.assertEqual(len(result["artists"]), 1)
        self.assertFalse(result["principal_uncertain"])

    def test_native_membership_conflict_not_intersected(self):
        _, _, result = consume(["A", "B"])
        self.assertEqual(set(result["artists"]), {"A", "B"})
        self.assertTrue(result["principal_uncertain"])
        self.assertEqual(result["participant_resolution_status"], "conflicting_participants")

    def test_existing_contract_name_presentation_preserved(self):
        _, evidence, result = consume(["Gusty dj"])
        self.assertEqual(result["artists"], ["Gusty DJ"])
        self.assertEqual(evidence[0]["observations"][0]["Track Artist"], "Gusty dj")

    def test_explicit_prior_name_presentation_not_replaced(self):
        _, _, result = consume(["Gusty dj"], ["Gusty dj"])
        self.assertEqual(result["artists"], ["Gusty dj"])

    def test_matching_existing_catalog_display_kept(self):
        output = enrich_dashgo_catalog(catalog(artist_statement="Gusty DJ"), frame(["Gusty dj"]))
        self.assertEqual(output["catalog_artist_statement"][0], "Gusty DJ")
        self.assertEqual(output["catalog_artists"][0].to_list(), ["Gusty dj"])

    def test_existing_display_not_rewritten_by_new_metadata(self):
        output = enrich_dashgo_catalog(catalog(artist_statement="GustyDj"), frame(["Gusty dj"]))
        self.assertEqual(output["catalog_artist_statement"][0], "GustyDj")
        self.assertEqual(output["catalog_artists"][0].to_list(), ["Gusty dj"])

    def test_artist_name_disagreement_is_context(self):
        _, proof, result = consume(source=frame(**{"Artist Name": "B"}))
        self.assertEqual(result["artists"], ["A"])
        self.assertTrue(result["principal_uncertain"])
        self.assertEqual(result["participant_resolution_status"], "conflicting_context")
        self.assertEqual(proof[0]["observations"][0]["Artist Name"], "B")

    def test_missing_track_credit_not_replaced_by_context(self):
        _, _, result = consume([""], source=frame([""], **{"Artist Name": "Context Person"}))
        self.assertEqual(result["artists"], [])
        self.assertTrue(result["principal_uncertain"])

    def test_product_without_isrc_not_a_track_credit(self):
        source = frame(asset_isrc=None, ISRC=None, UPC="001234567890", **{"Track Artist": None, "Artist Name": "Album Person", "Product Type": "A"})
        self.assertEqual(collect_dashgo_artists(source), {})

    def test_video_without_isrc_not_a_track_credit(self):
        source = frame(asset_isrc=None, ISRC=None, VideoId="abcdefghijk", **{"Track Artist": None, "Artist Name": "Video Person"})
        self.assertEqual(collect_dashgo_artists(source), {})

    def test_composers_labels_channels_are_context_only(self):
        _, proof, result = consume(source=frame(Composers="Writer One,Writer Two", **{"Label Name": "Label Person", "ChannelId": "UCcontext"}))
        self.assertEqual(result["artists"], ["A"])
        self.assertEqual(proof[0]["context_original"]["Composers"], ["Writer One,Writer Two"])

    def test_native_isrc_separators_follow_existing_policy(self):
        result = collect_dashgo_artists(frame(ISRC="AR-ABC-26-00001", asset_isrc="AR-ABC-26-00001"))
        self.assertIn(ISRC, result)
        self.assertEqual(result[ISRC]["observations"][0]["ISRC"], "AR-ABC-26-00001")

    def test_identity_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            collect_dashgo_artists(frame(ISRC="ARABC2600002"))

    def test_invalid_nonempty_identity_not_silently_discarded(self):
        with self.assertRaises(ValueError):
            collect_dashgo_artists(frame(ISRC="bad", asset_isrc="bad"))

    def test_provenance_and_account_guards(self):
        for changes in ({"account": "new"}, {"statement_period": "2026-08"}, {"statement_file_name": "other.csv"}, {"statement_file_hash": "bad"}, {"source_sheet": "shares"}):
            with self.assertRaises(ValueError):
                collect_dashgo_artists(frame(**changes))

    def test_missing_native_column_guard(self):
        with self.assertRaises(ValueError):
            collect_dashgo_artists(frame().drop("Track Artist"))

    def test_non_economic_controls_not_artists(self):
        blank = {k: None for k in NATIVE_FIELDS}
        base = {**blank, "source": "dashgo", "account": "mawzrecords", "asset_isrc": None,
            "statement_period": "2026-07", "statement_file_name": "MAWZ Records-07-26.csv", "statement_file_hash": "a" * 64}
        control = {**base, "ISRC": "Total Payable:", "asset_isrc": "Total Payable:", "Label Track ID": "1.00"}
        self.assertEqual(collect_dashgo_artists(pl.DataFrame([base, control]).lazy()), {})

    def test_unclassified_null_payable_guard(self):
        with self.assertRaises(ValueError):
            collect_dashgo_artists(frame(Payable=None))

    def test_zero_and_negative_payable_still_carry_metadata(self):
        for value in (0., -1.):
            self.assertEqual(collect_dashgo_artists(frame(Payable=value))[ISRC]["native_artists"], ["A"])

    def test_repeated_observations_preserved(self):
        entry = collect_dashgo_artists(frame(["A", "A"]))[ISRC]
        self.assertEqual(entry["observation_count"], 2)
        self.assertEqual(entry["observations"][0]["standardized_rows"], [1, 2])

    def test_locators_are_not_physical_csv_rows(self):
        entry = collect_dashgo_artists(frame())[ISRC]
        self.assertEqual(entry["observations"][0]["locator_kind"], "standardized_dashgo_subset_row")
        self.assertIsNone(entry["native_source_sheet"])

    def test_existing_list_not_replaced(self):
        _, _, result = consume(["A"], ["A", "B"])
        self.assertEqual(result["artists"], ["A", "B"])
        self.assertEqual(result["participant_resolution_status"], "cross_source_membership_difference")

    def test_conflicting_sources_offer_names_not_a_confirmed_union(self):
        out, _, result = consume(["A"], ["C"])
        self.assertEqual(out["catalog_artists"][0].to_list(), ["C"])
        self.assertEqual(result["artists"], ["C", "A"])
        self.assertTrue(result["principal_uncertain"])
        self.assertEqual(result["participant_resolution_status"], "conflicting_participants")

    def test_prior_evidence_and_manual_list_preserved(self):
        before = [{"source": "manual", "artists": ["Human"]}]
        out, proof, result = consume(["A"], ["Human"], catalog_artist_evidence=json.dumps(before), catalog_manual_correction_confirmed_by="Ruben")
        self.assertEqual(proof[0], before[0])
        self.assertEqual(out["catalog_artists"][0].to_list(), ["Human"])
        self.assertTrue(result["principal_uncertain"])

    def test_raw_uncertainty_not_erased(self):
        self.assertTrue(consume(raw={"principal_uncertain": True})[2]["principal_uncertain"])

    def test_fuga_principal_conflict_not_erased(self):
        proof = [{"source": "fuga", "field": "Asset Artist", "artists": ["B", "A"]}]
        self.assertTrue(consume(catalog_artist_evidence=json.dumps(proof))[2]["principal_uncertain"])

    def test_other_source_unresolved_status_not_erased(self):
        proof = [{"source": "other", "principal_status": "unresolved"}]
        self.assertTrue(consume(catalog_artist_evidence=json.dumps(proof))[2]["principal_uncertain"])

    def test_absent_source_delegates(self):
        self.assertIsNone(dashgo_suggestions({}, [], ["A"], None, isrc=ISRC))

    def test_other_sources_unchanged(self):
        old = catalog(["Existing"])
        self.assertTrue(old.equals(enrich_dashgo_catalog(old, frame(source="soundon"))))

    def test_idempotent_metadata_merge(self):
        out, _, _ = consume()
        self.assertTrue(out.equals(enrich_dashgo_catalog(out, frame())))

    def test_all_nonartist_columns_exact(self):
        old = catalog()
        out = enrich_dashgo_catalog(old, frame())
        protected = [c for c in old.columns if c not in ARTIST_COLUMNS]
        self.assertTrue(old.select(protected).equals(out.select(protected)))

    def test_bad_json_shape_not_adopted(self):
        with self.assertRaises(ValueError):
            consume(catalog_artist_evidence='{"source":"experimental"}')

    def test_duplicate_keys_guard(self):
        with self.assertRaises(ValueError):
            enrich_dashgo_catalog(pl.concat([catalog(), catalog()]), frame())

    def test_corrupt_evidence_cannot_supply_names(self):
        _, proof, _ = consume()
        for mutation in ("hash", "native", "positions", "isrc", "count"):
            damaged = copy.deepcopy(proof)
            if mutation == "hash": damaged[0]["observations"][0]["statement_file_hash"] = "bad"
            if mutation == "native": damaged[0]["native_artists"].append("Invented")
            if mutation == "positions": damaged[0]["observations"][0]["standardized_rows"] = [True]
            if mutation == "isrc": damaged[0]["asset_isrc"] = "ARABC2600002"
            if mutation == "count": damaged[0]["observation_count"] = 99
            result = dashgo_suggestions({"artists": ["A"], "warnings": [], "evidence": []}, damaged, ["A"], None, isrc=ISRC)
            self.assertEqual(result["artists"], ["A"])
            self.assertTrue(result["principal_uncertain"])

    def test_unverified_reported_names_not_used(self):
        _, proof, _ = consume()
        proof[0]["artists_reported"].append("Invented")
        result = dashgo_suggestions({"artists": ["A"], "warnings": [], "evidence": []}, proof, ["A"], None, isrc=ISRC)
        self.assertEqual(result["artists"], ["A"])

    def test_forged_resolved_status_cannot_hide_native_conflict(self):
        _, proof, _ = consume(["A", "B"])
        proof[0].update(native_resolution_status="as_reported", principal_status="single_artist", principal_proposed="A")
        result = dashgo_suggestions({"artists": ["A"], "warnings": [], "evidence": []}, proof, ["A"], None, isrc=ISRC)
        self.assertTrue(result["principal_uncertain"])

    def test_no_participant_limit_in_evidence(self):
        _, _, result = consume([f"Name {i}" for i in range(15)])
        self.assertEqual(len(result["artists"]), 15)
        self.assertTrue(result["principal_uncertain"])

    def test_saved_closed_contract_preserved(self):
        saved = {"closed": True, "split": {"principal": "A", "principal_percent": 30}, "version": 1}
        prior = copy.deepcopy(saved)
        proposed, info = propose_participants({}, ["B"], saved=saved, history=[])
        self.assertEqual(saved, prior)
        self.assertEqual(proposed, prior["split"])
        self.assertEqual(info["status"], "closed_or_previously_closed")

    def test_proposals_do_not_assign_percentages(self):
        initial = {"principal": "A", "participants": []}
        proposed, _ = propose_participants(initial, ["A", "B"], saved=None, history=[])
        self.assertIsNone(proposed["participants"][0]["percent"])
        self.assertEqual(initial["participants"], [])

    def test_consumption_and_fx_are_not_reinterpreted_by_metadata(self):
        source = frame(**{"Transaction Date": "2001-01-26", "Exchange Rate": "4.0e-05"})
        before = source.collect()
        entry = collect_dashgo_artists(source)[ISRC]
        self.assertEqual(entry["native_artists"], ["A"])
        self.assertTrue(before.equals(source.collect()))


if __name__ == "__main__":
    unittest.main()
