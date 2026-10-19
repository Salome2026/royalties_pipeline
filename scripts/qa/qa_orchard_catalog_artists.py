from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from lib.orchard_catalog_artists import ARTIST_COLUMNS, EVIDENCE_VERSION, enrich_orchard_catalog, parse_credit
from app.master_contract_participants import orchard_principal, propose_participants
from app.master_contracts import artist_suggestions

ISRC = "ZZXYZ2800001"


def catalog(names=None, **overrides):
    return pl.DataFrame([{ "catalog_key": "ISRC:" + ISRC, "asset_isrc": ISRC, "track_title": "Song",
        "artist_statement": "Existing display", "amount_usd": 7.123456, "units": 21.0,
        "catalog_aliases": ["VIDEO:existing"], "catalog_artists": names, "catalog_artist_statement": "Prior" if names else None,
        "catalog_artist_evidence": None, "catalog_artist_rule": None, **overrides}], schema_overrides=ARTIST_COLUMNS)


def raw(credits=("Principal|Guest",), **overrides):
    return pl.DataFrame([{ "source": "orchard", "statement_type": "orchard_statement", "account": "mawzrecords",
        "asset_isrc": ISRC, "ISRC": ISRC, "TRACK": "Song", "TRACK ARTIST": credit, "PRODUCT ARTIST": "Product Label",
        "statement_period": "2028-01", "statement_file_hash": f"{i:064x}", "statement_file_name": f"statement{i}.csv",
        "amount_usd": 7.123456, "units": 21.0, **overrides} for i, credit in enumerate(credits)]).lazy()


def entry(credits=("Principal|Guest",)):
    result = enrich_orchard_catalog(catalog(), raw(credits))
    return json.loads(result["catalog_artist_evidence"][0])[-1]


class OrchardTests(unittest.TestCase):
    def test_only_artist_columns_change(self):
        original = catalog()
        result = enrich_orchard_catalog(original, raw())
        self.assertTrue(result.drop(ARTIST_COLUMNS).equals(original.drop(ARTIST_COLUMNS)))

    def test_delimiter_is_only_pipe(self):
        self.assertEqual(parse_credit("North, South and West & Friends feat. X|Guest"), ["North, South and West & Friends feat. X", "Guest"])

    def test_product_label_is_not_participant(self):
        value = entry()
        self.assertEqual(value["artists"], ["Principal", "Guest"])
        self.assertEqual(value["observations"][0]["PRODUCT ARTIST"], "Product Label")

    def test_records_literal_in_track_credit_is_retained(self):
        self.assertEqual(entry(("Artist|Caserio Records",))["artists"], ["Artist", "Caserio Records"])

    def test_single_artist_proposal(self):
        value = entry(("Principal",))
        self.assertEqual(value["principal_status"], "single_artist")
        self.assertFalse(orchard_principal([value], ["Principal"], False, isrc=ISRC))

    def test_stable_multiple_proposal(self):
        value = entry()
        self.assertEqual(value["principal_status"], "order_only")
        self.assertFalse(orchard_principal([value], ["Principal", "Guest"], False, isrc=ISRC))

    def test_order_changes_are_real_doubt_not_missing_members(self):
        value = entry(("Principal|Guest", "Guest|Principal"))
        self.assertEqual(set(value["artists"]), {"Principal", "Guest"})
        self.assertTrue(orchard_principal([value], value["artists"], False, isrc=ISRC))

    def test_subset_superset_is_not_automatic_union(self):
        value = entry(("Principal", "Principal|Guest"))
        self.assertEqual(value["native_resolution_status"], "contradictory")
        self.assertEqual(value["artists"], [])

    def test_previous_other_source_names_are_preserved(self):
        original = catalog(["Principal", "Guest", "Release Guest"])
        result = enrich_orchard_catalog(original, raw())
        self.assertEqual(result["catalog_artists"][0].to_list(), ["Principal", "Guest", "Release Guest"])
        self.assertEqual(result["catalog_artist_statement"][0], "Prior")

    def test_incompatible_previous_names_not_overwritten(self):
        result = enrich_orchard_catalog(catalog(["Manual Guest"]), raw())
        value = json.loads(result["catalog_artist_evidence"][0])[-1]
        self.assertEqual(result["catalog_artists"][0].to_list(), ["Manual Guest"])
        self.assertFalse(value["used_for_catalog"])
        self.assertTrue(orchard_principal([value], ["Manual Guest"], False, isrc=ISRC))

    def test_manual_correction_preserved(self):
        original = catalog(["Manual"], catalog_manual_correction_confirmed_by="Ruben")
        result = enrich_orchard_catalog(original, raw())
        self.assertEqual(result["catalog_artists"][0].to_list(), ["Manual"])
        self.assertTrue(result.drop(ARTIST_COLUMNS).equals(original.drop(ARTIST_COLUMNS)))

    def test_title_only_correction_does_not_suppress_track_artists(self):
        original = catalog(catalog_manual_correction_confirmed_by="Ruben", track_title="Confirmed Title")
        result = enrich_orchard_catalog(original, raw())
        self.assertEqual(result["catalog_artists"][0].to_list(), ["Principal", "Guest"])
        self.assertEqual(result["track_title"][0], "Confirmed Title")

    def test_isrc_normalization_does_not_rewrite_economic_identity(self):
        original = raw(asset_isrc=" zz-xyz-28-00001 ", ISRC="zzxyz2800001").collect()
        frozen = original.clone()
        result = enrich_orchard_catalog(catalog(), original.lazy())
        self.assertEqual(result["catalog_artists"][0].to_list(), ["Principal", "Guest"])
        self.assertTrue(original.equals(frozen))

    def test_identity_mismatch_cannot_confirm(self):
        result = enrich_orchard_catalog(catalog(), raw(ISRC="ZZXYZ2800002"))
        value = json.loads(result["catalog_artist_evidence"][0])[-1]
        self.assertEqual(value["identity_status"], "contradictory")
        self.assertTrue(orchard_principal([value], ["Principal"], False, isrc=ISRC))

    def test_altafonte_legacy_is_not_orchard_modern(self):
        original = catalog()
        self.assertTrue(enrich_orchard_catalog(original, raw(statement_type="altafonte_legacy")).equals(original))

    def test_no_orchard_delegates(self):
        self.assertIsNone(orchard_principal([{"source": "fuga", "artists": ["A"]}], ["A"], False, isrc=ISRC))

    def test_wrong_identity_rule_field_or_level_is_not_confirmed(self):
        for changes in ({"asset_isrc": "ZZXYZ2800002"}, {"rule": "future"}, {"level": "product"}, {"field": "PRODUCT ARTIST"}):
            with self.subTest(changes=changes):
                self.assertTrue(orchard_principal([{**entry(), **changes}], ["Principal", "Guest"], False, isrc=ISRC))

    def test_raw_uncertainty_survives(self):
        self.assertTrue(orchard_principal([entry()], ["Principal", "Guest"], True, isrc=ISRC))

    def test_ada_real_uncertainty_survives(self):
        from lib.ada_catalog_artists import EVIDENCE_VERSION as ADA_VERSION
        other = {"source": "ada", "adapter_version": ADA_VERSION, "native_resolution_status": "contradictory"}
        self.assertTrue(orchard_principal([entry(), other], ["Principal", "Guest"], False, isrc=ISRC))

    def test_onerpm_real_uncertainty_survives(self):
        other = {"source": "onerpm", "field": "Artists", "sheet": "Masters", "used_for_catalog": False}
        self.assertTrue(orchard_principal([entry(), other], ["Principal", "Guest"], False, isrc=ISRC))

    def test_fuga_principal_conflict_survives(self):
        other = {"source": "fuga", "field": "Asset Artist", "artists": ["Guest", "Principal"]}
        self.assertTrue(orchard_principal([entry(), other], ["Principal", "Guest"], False, isrc=ISRC))

    def test_duplicate_certificates_not_silently_chosen(self):
        self.assertTrue(orchard_principal([entry(), entry()], ["Principal", "Guest"], False, isrc=ISRC))

    def test_merge_idempotent(self):
        first = enrich_orchard_catalog(catalog(), raw())
        self.assertTrue(first.equals(enrich_orchard_catalog(first, raw())))

    def test_more_than_ten_guests_and_new_names(self):
        artists = [f"Future Artist {i}" for i in range(15)]
        value = entry(("|".join(artists),))
        proposed, info = propose_participants({"principal": "", "participants": []}, value["artists"], saved=None, history=[])
        self.assertEqual(len(proposed["participants"]), 15)
        self.assertTrue(info["capacity_exceeded"])
        self.assertTrue(all(row["percent"] is None for row in proposed["participants"]))

    def test_new_statement_no_dictionary_needed(self):
        value = entry(("Unknown 2028 Artist|Another Unknown",))
        self.assertFalse(orchard_principal([value], value["artists"], False, isrc=ISRC))

    def test_incomplete_provenance_not_certified(self):
        result = enrich_orchard_catalog(catalog(), raw(statement_file_hash=""))
        value = json.loads(result["catalog_artist_evidence"][0])[-1]
        self.assertEqual(value["native_resolution_status"], "incomplete")
        self.assertTrue(orchard_principal([value], ["Principal"], False, isrc=ISRC))

    def test_malformed_observations_not_certified(self):
        for observations in ("bad", [42], [{"asset_isrc": ISRC}], [{"asset_isrc": ISRC, "identity_status": "resolved", "provenance_complete": True, "artists": 42}]):
            with self.subTest(observations=observations):
                self.assertTrue(orchard_principal([{**entry(), "observations": observations}], ["Principal", "Guest"], False, isrc=ISRC))

    def test_blank_track_artist_does_not_promote_label(self):
        self.assertEqual(entry(("",))["artists"], [])

    def test_normalization_is_not_fuzzy_aliasing(self):
        self.assertEqual(parse_credit(" Jose |Jos\u00e9|Jose DJ"), ["Jose", "Jose DJ"])

    def test_real_suggestions_use_metadata_and_no_split(self):
        result = enrich_orchard_catalog(catalog(), raw())
        row = result.row(0, named=True)
        suggestions = artist_suggestions(ISRC, None, row["artist_statement"], row["catalog_artists"], row["catalog_artist_evidence"])
        self.assertFalse(suggestions["principal_uncertain"])
        self.assertEqual(suggestions["artists"], ["Principal", "Guest"])

    def test_financial_unknown_zero_and_negative_inputs_untouched(self):
        for units in (None, 0.0, -2.0):
            original = catalog(units=units)
            result = enrich_orchard_catalog(original, raw(units=units))
            self.assertEqual(result["units"][0], units)
            self.assertEqual(result["amount_usd"][0], 7.123456)


if __name__ == "__main__":
    unittest.main()
