"""Common membership, protected decisions and adversarial future inputs."""
from copy import deepcopy
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import polars as pl
from polars.testing import assert_frame_equal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.lib.catalog_participant_resolution import (
    FIELD, RULE, resolve_row, resolve_catalog_participants, resolution_from_evidence, keys,
)
from scripts.lib.catalog_ingestion_review import reading_incidents
from scripts.lib.catalog_artist_evidence import records
from app.master_contracts import artist_suggestions, suggested_split
from app.master_contract_participants import propose_participants
from app import catalog_metadata_review

ISRC = "ARABC2600001"


def proof(source, names, *, isrc=ISRC):
    common = {"account": "indyana_records", "statement_period": "2026-07",
        "statement_file_name": "July2026.csv", "statement_file_hash": "a" * 64}
    if source == "fuga":
        raw = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        return {**common, "source": source, "field": "Asset Artist", "artists": names, "raw": raw,
            "used_for_catalog": True, "status": "fuga_comma_and_featuring", "Product Reference": "123", "Asset Reference": "456"}
    if source == "onerpm":
        from scripts.lib.onerpm_catalog_artists import parse_credits, RULE_VERSION
        raw = ", ".join(name + "(performer)" for name in names) + ", Not An Artist(writer)"
        parsed = parse_credits(raw)
        return {**common, "source": source, "field": "Artists", "raw": raw, "artists": parsed["artists"],
            "credits": parsed["credits"], "status": "resolved", "identity_status": "resolved", "native_resolution_status": "resolved",
            "level": "track", "sheet": "Shares In & Out", "product_type": "Track", "catalog_rule": RULE_VERSION,
            "source_rule": RULE_VERSION, "row": 2}
    if source == "ada":
        from scripts.lib.ada_catalog_artists import EVIDENCE_VERSION
        common["statement_file_name"] = "99500_202607_202607_99500_DTL.xlsx"
        raw = " & ".join(names)
        observation = {**common, "source": source, "asset_isrc": isrc, "native_entity_key": "ISRC:" + isrc,
            "native_source_sheet": "Distribution Statement", "source_row": 2, "Artist Name": raw,
            "artist_catalog_style": raw, "artists": names, "grammar_status": "resolved", "artist_credit_status": "as_reported"}
        return {"source": source, "field": "Artist Name", "adapter_version": EVIDENCE_VERSION,
            "identity_status": "resolved", "native_resolution_status": "resolved", "artists": names,
            "observations": [observation]}
    if source == "soundon":
        from scripts.lib.soundon_catalog_artists import EVIDENCE_VERSION, RULE_VERSION
        common.update(account="soundon", statement_file_name="SoundOn_royalty_monthly_statement_2026_07_My Royalty.csv")
        observation = {**common, "asset_isrc": isrc, "ISRC": isrc, "source_sheet": "my_royalty",
            "Reporting Period": "2026-07", "Track Artists": ",".join(names), "artists": names,
            "Track ID": "123", "UPC Code": "123456789012", "locator_kind": "standardized_soundon_subset_row", "standardized_rows": [1]}
        return {"source": source, "field": "Track Artists", "account": "soundon", "source_sheet": "my_royalty", "level": "track",
            "asset_isrc": isrc, "rule": RULE_VERSION, "adapter_version": EVIDENCE_VERSION, "identity_status": "resolved",
            "native_resolution_status": "as_reported", "participant_resolution_status": "cross_source_membership_difference",
            "native_artists": names, "principal_proposed": names[0], "principal_status": "order_only",
            "observation_count": 1, "observations": [observation]}
    if source == "orchard":
        from scripts.lib.orchard_catalog_artists import EVIDENCE_VERSION, RULE_VERSION
        observation = {**common, "asset_isrc": isrc, "ISRC": isrc, "TRACK ARTIST": "|".join(names),
                       "artists": names, "standardized_row": 1, "provenance_complete": True}
        return {"source": source, "field": "TRACK ARTIST", "asset_isrc": isrc, "level": "track",
            "rule": RULE_VERSION, "adapter_version": EVIDENCE_VERSION, "identity_status": "resolved",
            "native_resolution_status": "resolved", "native_artists": names, "observations": [observation]}
    if source == "dashgo":
        from scripts.lib.dashgo_catalog_artists import EVIDENCE_VERSION, RULE_VERSION
        assert len(names) == 1
        common.update(account="mawzrecords", statement_file_name="MAWZ Records-07-26.csv")
        observation = {**common, "asset_isrc": isrc, "ISRC": isrc, "Track Artist": names[0], "Artist Name": names[0],
            "artists": names, "locator_kind": "standardized_dashgo_subset_row", "standardized_rows": [1]}
        return {"source": source, "field": "Track Artist", "asset_isrc": isrc, "account": "mawzrecords", "level": "track",
            "source_sheet": "detail", "source_sheet_origin": "dashgo_detail_policy", "rule": RULE_VERSION,
            "adapter_version": EVIDENCE_VERSION, "identity_status": "resolved", "native_resolution_status": "as_reported",
            "native_artists": names, "observation_count": 1, "observations": [observation]}
    raise ValueError(source)


def row(artists=None, evidence=None, **extra):
    artists = ["Lead"] if artists is None else artists
    return {"catalog_key": "ISRC:" + ISRC, "asset_isrc": ISRC, "catalog_artists": artists,
        "catalog_artist_statement": " / ".join(artists), "catalog_artist_evidence": json.dumps(evidence or []),
        "catalog_artist_rule": "old-rule", "artist_statement": "Lead", "track_title": "Title",
        "amount_usd": -12.3456, "units": 20, "upcs": "00123456789012", **extra}


class CommonParticipantTests(unittest.TestCase):
    def resolve(self, original):
        return resolve_row(original, manual_keys=set())

    def test_complete_reported_list_supersedes_only_a_compatible_partial_list(self):
        a, result = self.resolve(row(evidence=[proof("fuga", ["Lead"]), proof("soundon", ["Lead", "Guest"])]))
        self.assertEqual(a["catalog_artists"], ["Lead", "Guest"])
        self.assertEqual(result["status"], "completed_from_native_track")
        self.assertEqual(result["added"], ["Guest"])
        self.assertFalse(result["contractual_rights_inferred"])

    def test_all_six_sources_have_certified_projection_and_no_new_grammar(self):
        for source in ("fuga", "onerpm", "ada", "orchard", "soundon", "dashgo"):
            names = ["Lead"] if source == "dashgo" else ["Lead", "Guest"]
            with self.subTest(source=source):
                a, result = self.resolve(row(evidence=[proof(source, names)]))
                self.assertEqual(a["catalog_artists"], names)
                self.assertFalse(result["issues"])

    def test_no_union_of_incomparable_partial_lists_without_a_complete_witness(self):
        a, result = self.resolve(row(evidence=[proof("fuga", ["Lead", "B"]), proof("soundon", ["Lead", "C"])]))
        self.assertEqual(a["catalog_artists"], ["Lead"])
        self.assertEqual(result["status"], "conflicting_participants")

    def test_largest_report_does_not_erase_an_existing_catalogue_artist(self):
        a, result = self.resolve(row(["Lead", "Kept"], [proof("soundon", ["Lead", "B", "C"])]))
        self.assertEqual(a["catalog_artists"], ["Lead", "Kept"])
        self.assertEqual(result["status"], "conflicting_participants")

    def test_one_witness_must_cover_all_compatible_lists(self):
        native = [proof("fuga", ["Lead", "B"]), proof("ada", ["Lead", "C"]), proof("soundon", ["Lead", "B", "C"])]
        a, result = self.resolve(row(evidence=native))
        self.assertEqual(a["catalog_artists"], ["Lead", "B", "C"])
        self.assertEqual(result["status"], "completed_from_native_track")

    def test_source_order_does_not_change_resolution_or_give_votes_to_repeated_months(self):
        entries = [proof("fuga", ["Lead"]), proof("soundon", ["Lead", "Guest"]), proof("ada", ["Lead"])]
        results = [self.resolve(row(evidence=list(order)))[1] for order in itertools.permutations(entries)]
        self.assertTrue(all(item == results[0] for item in results))
        a, _ = self.resolve(row(evidence=[*entries, *[entries[0]] * 20]))
        self.assertEqual(a["catalog_artists"], ["Lead", "Guest"])

    def test_replay_is_exact_and_new_statements_invalidate_the_cached_proof(self):
        a, result = self.resolve(row(evidence=[proof("soundon", ["Lead", "Guest"])]))
        self.assertEqual(a, self.resolve(a)[0])
        native = records(a["catalog_artist_evidence"])
        native.append(proof("fuga", ["Lead", "Guest", "Next Arrival"]))
        changed = {**a, "catalog_artist_evidence": json.dumps(native)}
        b, updated = self.resolve(changed)
        self.assertEqual(b["catalog_artists"], ["Lead", "Guest", "Next Arrival"])
        self.assertNotEqual(result["native_digest"], updated["native_digest"])

    def test_album_and_channel_context_never_adds_members(self):
        album = {**proof("fuga", ["Lead", "Album Guest"]), "field": "Product Artist"}
        a, result = self.resolve(row(evidence=[proof("fuga", ["Lead"]), album]))
        self.assertEqual(a["catalog_artists"], ["Lead"])
        self.assertEqual(result["status"], "consistent")

    def test_bad_identity_version_or_tampered_parsed_names_cannot_complete(self):
        for field, value in (("asset_isrc", "ARABC2600002"), ("adapter_version", "unknown"), ("native_artists", ["Lead", "Invented"])):
            entry = {**proof("soundon", ["Lead", "Guest"]), field: value}
            with self.subTest(field=field):
                a, result = self.resolve(row(evidence=[entry]))
                self.assertEqual(a["catalog_artists"], ["Lead"])
                self.assertEqual(result["status"], "review_required")

    def test_native_conflict_is_not_overruled_by_another_source(self):
        entry = {**proof("soundon", ["Lead", "Guest"]), "native_resolution_status": "conflicting_participants"}
        a, result = self.resolve(row(evidence=[proof("ada", ["Lead", "Guest"]), entry]))
        self.assertEqual(a["catalog_artists"], ["Lead"])
        self.assertEqual(result["status"], "review_required")

    def test_approved_aliases_are_equivalences_not_new_people(self):
        a, result = self.resolve(row(["Matias Mareco"], [proof("soundon", ["Matias Mareco DJ"])]))
        self.assertEqual(a["catalog_artists"], ["Matias Mareco"])
        self.assertFalse(result["added"])

    def test_scoped_fuga_name_reference_does_not_become_a_global_alias(self):
        original = row(["Federikita"], [proof("fuga", ["Kita"])], asset_isrc="ARDL12400060", catalog_key="ISRC:ARDL12400060")
        a, result = self.resolve(original)
        self.assertEqual(result["status"], "consistent")
        other, result = self.resolve(row(["Federikita"], [proof("fuga", ["Kita"])]))
        self.assertEqual(result["status"], "conflicting_participants")

    def test_artist_corrections_and_explicit_exclusions_take_precedence(self):
        original = row(evidence=[proof("soundon", ["Lead", "Guest"])], artist_exclusions=["Guest"])
        a, result = self.resolve(original)
        self.assertEqual(result["status"], "manual_protected")
        self.assertEqual(a["catalog_artists"], ["Lead"])

    def test_writers_are_not_artists_and_shares_metadata_does_not_create_money(self):
        original = row(evidence=[proof("onerpm", ["Lead", "Guest"])])
        a, result = self.resolve(original)
        self.assertEqual(a["catalog_artists"], ["Lead", "Guest"])
        self.assertNotIn("Not An Artist", a["catalog_artists"])
        self.assertEqual(a["amount_usd"], original["amount_usd"])

    def test_dashgo_group_names_remain_atomic(self):
        a, result = self.resolve(row(["Band and Friends"], [proof("dashgo", ["Band and Friends"])]))
        self.assertEqual(a["catalog_artists"], ["Band and Friends"])
        self.assertFalse(result["issues"])

    def test_length_30_is_not_by_itself_a_new_manual_review(self):
        entry = proof("ada", ["A" * 30])
        entry["observations"][0]["artist_credit_status"] = "possible_truncation"
        a, result = self.resolve(row(["A" * 30], [entry]))
        self.assertEqual(result["status"], "consistent")
        a, result = self.resolve(row(evidence=[entry]))
        self.assertNotEqual(result["status"], "completed_from_native_track")

    def test_fuga_video_reference_is_not_a_music_track_witness(self):
        entry = {**proof("fuga", ["Lead", "Channel"]), "Asset Reference": "YT-A-123"}
        a, result = self.resolve(row(evidence=[entry]))
        self.assertEqual(a["catalog_artists"], ["Lead"])
        self.assertEqual(result["status"], "review_required")

    def test_video_upc_legacy_and_other_workspaces_are_untouched(self):
        for extra in ({"catalog_key": "UPC:123", "asset_isrc": None}, {"catalog_key": "VIDEO:abcdefghijk", "asset_isrc": None}, {"scope": "wml91230"}):
            original = row(evidence=[proof("soundon", ["Lead", "Guest"])], **extra)
            self.assertEqual(self.resolve(original), (original, None))

    def test_confidence_in_principal_and_order_do_not_change(self):
        original = row(["Zulu", "Lead"], [proof("fuga", ["Zulu", "Lead"]), proof("soundon", ["Lead", "Zulu", "Guest"])])
        a, _ = self.resolve(original)
        self.assertEqual(a["catalog_artists"], ["Zulu", "Lead", "Guest"])
        old = artist_suggestions(ISRC, None, None, original["catalog_artists"], original["catalog_artist_evidence"])
        new = artist_suggestions(ISRC, None, None, a["catalog_artists"], a["catalog_artist_evidence"])
        self.assertEqual(old["principal_uncertain"], new["principal_uncertain"])

    def test_contracts_use_the_exact_master_list_and_remove_only_obsolete_membership_warning(self):
        a, _ = self.resolve(row(evidence=[proof("fuga", ["Lead"]), proof("soundon", ["Lead", "Guest"])]))
        suggestion = artist_suggestions(ISRC, None, "Lead", a["catalog_artists"], a["catalog_artist_evidence"])
        self.assertEqual(suggestion["artists"], a["catalog_artists"])
        self.assertEqual(suggestion["participant_resolution_rule"], RULE)
        self.assertFalse(any('difieren en participantes' in text for text in suggestion["warnings"]))
        self.assertFalse(reading_incidents(pl.DataFrame([a])))

    def test_corrupt_derived_record_is_not_reinterpreted_by_contracts(self):
        a, _ = self.resolve(row(evidence=[proof("soundon", ["Lead", "Guest"])]))
        for change in ("artists", "native"):
            entries = records(a["catalog_artist_evidence"])
            if change == 'artists':
                entries[-1]["artists"].append('Bogus')
            else:
                entries[0]["native_artists"].append('Bogus')
            with self.assertRaises(ValueError):
                artist_suggestions(ISRC, None, None, a["catalog_artists"], json.dumps(entries))

    def test_approved_runtime_override_is_authoritative_after_common_resolution(self):
        a, _ = self.resolve(row(evidence=[proof("soundon", ["Lead", "Guest"])]))
        review = {a['catalog_key']: {'overrides_json': {'artists': ['Lead']}}}
        with patch.object(catalog_metadata_review, 'read_state', return_value=({}, review)):
            frame = catalog_metadata_review.apply_approved(pl.DataFrame([a]))
        actual = frame.row(0, named=True)
        proposal = artist_suggestions(ISRC, None, None, actual['catalog_artists'], actual['catalog_artist_evidence'])
        self.assertEqual(proposal['artists'], ['Lead'])
        self.assertEqual(proposal['participant_resolution_status'], 'manual_protected')

    def test_existing_saved_contracts_and_percentages_are_not_changed(self):
        from scripts.qa.qa_master_contract_participants import saved, history
        a, _ = self.resolve(row(evidence=[proof("soundon", ["Lead", "Guest"])]))
        for closed in (False, True):
            record = saved(closed=closed)
            baseline = deepcopy(record)
            projected, _ = propose_participants(suggested_split(a['catalog_artists']), a['catalog_artists'], saved=record, history=[history(record)])
            self.assertEqual(record, baseline)
            if closed:
                self.assertEqual(projected, baseline['split'])

    def test_all_other_columns_and_native_records_are_preserved(self):
        original = row(evidence=[proof("soundon", ["Lead", "Guest"])], statement_month="2026-07", transaction_month="2026-05")
        frame = pl.DataFrame([original])
        after = resolve_catalog_participants(frame)
        fields = ['catalog_artists', 'catalog_artist_statement', 'catalog_artist_rule', 'catalog_artist_evidence']
        assert_frame_equal(frame.drop(fields), after.drop(fields))
        self.assertEqual(records(original['catalog_artist_evidence']), records(after['catalog_artist_evidence'][0])[:-1])

    def test_new_unknown_artists_need_no_preloaded_dictionary_or_inferred_principal(self):
        a, result = self.resolve(row([], [proof('soundon', ['Unknown Main 900', 'Unknown Guest 901'])]))
        self.assertEqual(keys(a['catalog_artists']), keys(['Unknown Main 900', 'Unknown Guest 901']))
        actual = artist_suggestions(ISRC, None, None, a['catalog_artists'], a['catalog_artist_evidence'])
        self.assertTrue(actual['principal_uncertain'])
        self.assertEqual(actual['artists'], a['catalog_artists'])

    def test_same_upc_or_title_never_merges_two_isrcs(self):
        other = 'ARABC2600002'
        left = row(evidence=[proof('soundon', ['Lead', 'Guest'])])
        right = row(evidence=[proof('soundon', ['Lead', 'Different'], isrc=other)], asset_isrc=other, catalog_key='ISRC:' + other)
        result = resolve_catalog_participants(pl.DataFrame([left, right]))
        self.assertEqual(result.height, 2)
        self.assertEqual(result['catalog_artists'][0].to_list(), ['Lead', 'Guest'])
        self.assertEqual(result['catalog_artists'][1].to_list(), ['Lead', 'Different'])

    def test_existing_explicit_ada_feat_rule_is_reused_only_with_native_credit_proof(self):
        from scripts.lib.catalog_artist_extensions import RULE as FEAT_RULE
        native = proof('ada', ['Lead'])
        item = native['observations'][0]
        item['Catalogue Title'] = 'Song (feat. Guest)'
        title = {'source': 'ada', 'field': 'Catalogue Title', 'rule': FEAT_RULE, 'isrc': ISRC,
            'file': item['statement_file_name'], 'file_hash': item['statement_file_hash'], 'row': item['source_row'],
            'account': item['account'], 'sheet': 'Distribution Statement', 'artist_raw': 'Lead',
            'title_raw': 'Song (feat. Guest)', 'candidate_names': ['Guest']}
        a, result = self.resolve(row(evidence=[native, title]))
        self.assertEqual(a['catalog_artists'], ['Lead', 'Guest'])
        without_native, result = self.resolve(row(evidence=[title]))
        self.assertEqual(without_native['catalog_artists'], ['Lead'])
        corrupt = {**title, 'candidate_names': ['Invented']}
        a, result = self.resolve(row(evidence=[native, corrupt]))
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(a['catalog_artists'], ['Lead'])
        wrong_native = deepcopy(native)
        wrong_native['observations'][0]['Catalogue Title'] = 'Different track title'
        a, result = self.resolve(row(evidence=[wrong_native, title]))
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(a['catalog_artists'], ['Lead'])

    def test_certified_dashgo_isrc_normalization_is_preserved(self):
        entry = proof('dashgo', ['Lead'])
        entry['observations'][0].update(ISRC='AR-ABC-26-00001', asset_isrc='AR-ABC-26-00001')
        a, result = self.resolve(row(evidence=[entry]))
        self.assertEqual(result['status'], 'consistent')

    def test_raw_fallback_cannot_replace_common_membership_and_dates_remain_intact(self):
        a, _ = self.resolve(row(evidence=[proof('soundon', ['Lead', 'Guest'])]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'exists.parquet'
            path.touch()
            raw = {'artists': ['Incorrect'], 'evidence': [{'source': 'legacy'}], 'warnings': [],
                'principal_uncertain': True, 'first_sale_date': '2024-11-01', 'first_sale_precision': 'day'}
            with patch('app.master_contracts._artist_suggestions', return_value=raw):
                actual = artist_suggestions(ISRC, path, None, a['catalog_artists'], a['catalog_artist_evidence'])
        self.assertEqual(actual['artists'], a['catalog_artists'])
        self.assertEqual(actual['first_sale_date'], '2024-11-01')
        self.assertEqual(actual['first_sale_precision'], 'day')

    def test_combinatorial_subset_cases_never_invent_an_unreported_union(self):
        groups = [['Lead', *(name for bit, name in enumerate(['B', 'C', 'D']) if mask & (1 << bit))] for mask in range(8)]
        for left, right in itertools.product(groups, repeat=2):
            original = row(evidence=[proof('fuga', left), proof('soundon', right)])
            result, info = self.resolve(original)
            union = keys([*left, *right])
            if keys(left) == union or keys(right) == union:
                self.assertEqual(keys(result['catalog_artists']), union)
            else:
                self.assertEqual(result['catalog_artists'], ['Lead'])


if __name__ == '__main__':
    unittest.main()
