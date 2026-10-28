from __future__ import annotations
import copy
import io
import json
import sqlite3
import unittest
from unittest.mock import MagicMock, patch
import polars as pl
from lib.catalog_identity_corrections import correct_recording_identity, correct_extended_identity, corrected_legacy_is_not_video_alias, correct_release_metadata
from app.catalog_participant_review import build_review_plan, project_review, apply_review_plan, preserve_review, publish_with_participant_review, REVIEW
from app.master_contracts import ensure_sqlite_tables, read_split, save_split, validate_split
from app.master_contract_participants import allocations, propose_participants
from app.royalty_reports.contractual import analyze_contractual_income
from app.royalty_reports.contract_snapshot import freeze_contract_snapshot
from scripts.qa.qa_contractual_executive import fixture, income

OLD, NEW, TEST = "ARDL12400078", "ARDL12600160", "ARDL12600999"


def sale(code=OLD, **overrides):
    return {"source": "fuga", "account": "indyana_records", "asset_isrc": code,
        "asset_reference": "1001863737555", "asset_artist_statement": "Dormun", "asset_title_statement": "El Farsante",
        "Asset ISRC": code, "amount_usd": 100.25, "units": 20., **overrides}


def catalog(artists, isrc=TEST):
    return pl.DataFrame([{"catalog_key": "ISRC:" + isrc, "asset_isrc": isrc,
        "catalog_artists": artists, "artist_statement": " / ".join(artists)}])


def event(before=None, after=None):
    return build_review_plan(catalog(before or ["Lead"]), catalog(after or ["Lead", "Guest"]))["changes"][0]


def split():
    return {"principal": "Lead", "indyana_percent": 70, "principal_percent": 30,
        "participants": [], "apply_guest_contracts": False, "agreements": [],
        "master_type": "indyana_master", "has_contract": True, "agreement_confirmed": True,
        "effective_from": "2024-01-01", "notes": "Original"}


def saved(value=None):
    return {"split": value or split(), "closed": True, "future_reports_selected": True, "version": 1}


class IdentityTests(unittest.TestCase):
    def test_old_new_one_recording_and_lit_killah_separate(self):
        raw = pl.DataFrame([sale(), sale(NEW, amount_usd=75), sale(source="ada", account="mawz",
            asset_reference=None, asset_artist_statement="LIT killah & Nicki Nicole", asset_title_statement="Somos 3", amount_usd=200)])
        result = correct_recording_identity(raw)
        self.assertEqual(result["asset_isrc"].to_list(), [NEW, NEW, OLD])
        self.assertEqual(result["amount_usd"].to_list(), raw["amount_usd"].to_list())
        self.assertEqual(result["Asset ISRC"].to_list(), [OLD, NEW, OLD])
        totals = {r["asset_isrc"]: r["amount_usd"] for r in result.group_by("asset_isrc").agg(pl.col("amount_usd").sum()).to_dicts()}
        self.assertEqual(totals, {NEW: 175.25, OLD: 200})

    def test_negative_and_repeated_sales_are_not_deduplicated(self):
        raw = pl.DataFrame([sale(), sale(), sale(NEW, amount_usd=-25)])
        result = correct_recording_identity(raw)
        self.assertEqual(result.height, 3)
        self.assertEqual(result["amount_usd"].sum(), 175.5)
        self.assertEqual(result["asset_isrc"].n_unique(), 1)

    def test_repeat_and_reported_evidence(self):
        raw = pl.DataFrame([sale()])
        once = correct_recording_identity(raw)
        self.assertTrue(correct_recording_identity(once).equals(once))
        self.assertEqual(once["reported_asset_isrc"][0], OLD)
        self.assertEqual(raw["asset_isrc"][0], OLD)

    def test_future_new_isrc_allows_redistribution_reference_but_rejects_other_artist(self):
        row = sale(NEW, asset_reference="NEW-DISTRIBUTION-REFERENCE")
        self.assertEqual(correct_recording_identity(pl.DataFrame([row]))["asset_isrc"][0], NEW)
        with self.assertRaises(ValueError):
            correct_recording_identity(pl.DataFrame([{**row, "asset_artist_statement": "Lit Killah", "asset_title_statement": "Somos 3"}]))

    def test_aggregated_rows_use_exact_artist_and_title(self):
        raw = pl.DataFrame([{"source": "fuga", "account": "indyana_records", "isrc": OLD, "artist": "Dormun", "title": "El Farsante"}])
        self.assertEqual(correct_recording_identity(raw, code_column="isrc")["isrc"][0], NEW)

    def test_wrong_reference_artist_and_source_do_not_guess(self):
        cases = [sale(asset_reference="999"), sale(asset_artist_statement="Lit Killah"), sale(asset_reference=None, asset_title_statement="Otro"),
            sale(source="other", asset_reference=None)]
        for row in cases:
            with self.subTest(row=row):
                with self.assertRaises(ValueError):
                    correct_recording_identity(pl.DataFrame([row]))

    def test_known_reference_allows_same_artist_title_variant(self):
        self.assertEqual(correct_recording_identity(pl.DataFrame([sale(asset_title_statement="EL FARSANTE (Original)")]))["asset_isrc"][0], NEW)

    def test_wml_is_untouched(self):
        raw = pl.DataFrame([sale(scope="wml91230")])
        self.assertTrue(correct_recording_identity(raw).equals(raw))

    def test_extended_does_not_turn_shared_old_isrc_into_global_video_alias(self):
        raw = pl.DataFrame([{"principal_asset_isrc": OLD, "YouTube Asset ISRC": OLD, "YouTube Video ID": "vBW2vx8zlVg"}])
        result = correct_extended_identity(raw)
        self.assertEqual(result["principal_asset_isrc"][0], NEW)
        self.assertEqual(result["YouTube Asset ISRC"][0], OLD)
        self.assertTrue(corrected_legacy_is_not_video_alias(OLD, result.to_dicts()))
        self.assertFalse(corrected_legacy_is_not_video_alias("ARDL12600001", result.to_dicts()))

    def test_extended_other_video_not_reassigned(self):
        raw = pl.DataFrame([{"principal_asset_isrc": OLD, "YouTube Video ID": "OtherVideo1"}])
        self.assertEqual(correct_extended_identity(raw)["principal_asset_isrc"][0], OLD)

    def test_external_metadata_uses_recording_upc_not_catalog_global_source(self):
        raw = pl.DataFrame([{"source": "catalog", "account": "global", "lookup_isrc": OLD,
            "lookup_upc": "8721093907237", "lookup_artist": "Dormun", "lookup_title": "El Farsante"}])
        self.assertEqual(correct_release_metadata(raw)["lookup_isrc"][0], NEW)
        with self.assertRaises(ValueError):
            correct_release_metadata(raw.with_columns(pl.lit("5034644050102").alias("lookup_upc")))


class ReviewTests(unittest.TestCase):
    def test_closed_reopens_with_blank_guest_and_preserved_values(self):
        original = saved()
        before = copy.deepcopy(original)
        proposed = project_review(original, event())
        self.assertFalse(proposed["agreement_confirmed"])
        self.assertEqual(proposed["indyana_percent"], 70)
        self.assertEqual(proposed["principal_percent"], 30)
        self.assertEqual(proposed["participants"][0]["artist"], "Guest")
        self.assertIsNone(proposed["participants"][0]["percent"])
        self.assertEqual(original, before)

    def test_alias_accent_or_reordering_does_not_reopen(self):
        for left, right in [(["Matias Mareco DJ"], ["Matias Mareco"]), (["DJ Alan Gomez"], ["Alan Gomez"]),
            (["Jos\u00e9"], ["Jose"]), (["A", "B"], ["B", "A"])]:
            self.assertEqual(build_review_plan(catalog(left), catalog(right))["changes"], [])

    def test_intentional_exclusion_is_respected(self):
        original = saved({**split(), "catalog_participant_exclusions": ["Guest"]})
        self.assertIsNone(project_review(original, event()))

    def test_history_removal_is_respected(self):
        earlier = {**split(), "participants": [{"artist": "Guest", "percent": 0}]}
        self.assertIsNone(project_review(saved(), event(), history=[{"payload_json": json.dumps(earlier)}]))

    def test_all_period_allocations_filled_without_reassigning_existing_shares(self):
        value = split()
        value["agreements"] = [{"id": "a", "effective_from": "2024-01-01", "effective_until": "2024-12-31", "allocation": copy.deepcopy(split())},
            {"id": "b", "effective_from": "2025-01-01", "effective_until": None, "allocation": copy.deepcopy(split())}]
        proposed = project_review(saved(value), event())
        for _, allocation in allocations(proposed):
            self.assertEqual(allocation["principal_percent"], 30)
            self.assertEqual(allocation["participants"][0]["artist"], "Guest")
            self.assertIsNone(allocation["participants"][0]["percent"])
        self.assertEqual(proposed["agreements"][0]["effective_until"], "2024-12-31")

    def test_blank_cannot_close_but_zero_can(self):
        proposed = project_review(saved(), event())
        proposed["agreement_confirmed"] = True
        with self.assertRaises(ValueError):
            validate_split(proposed, True, False)
        proposed["participants"][0]["percent"] = 0
        validate_split(proposed, True, False)

    def test_removal_can_close_and_is_not_reinserted(self):
        proposed = project_review(saved(), event())
        proposed["participants"] = []
        proposed["catalog_participant_exclusions"] = ["Guest"]
        proposed["agreement_confirmed"] = True
        validate_split(proposed, True, False)
        previous = {"split": proposed}
        reviewed = preserve_review(proposed, previous, closed=True, actor="human")
        self.assertEqual(reviewed[REVIEW]["status"], "reviewed")
        self.assertIsNone(project_review(saved(reviewed), event()))

    def test_replay_does_not_add_history_or_duplicate_guests(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_sqlite_tables(conn)
        save_split(conn, TEST, split(), closed=True, future_reports_selected=True, expected_version=0, actor="human")
        first = apply_review_plan(conn, {"version": 1, "changes": [event()]})
        self.assertEqual(first["reopened"], 1)
        row = read_split(conn, TEST)
        self.assertFalse(row["closed"])
        self.assertFalse(row["future_reports_selected"])
        self.assertEqual(row["version"], 2)
        self.assertEqual(len(row["split"]["participants"]), 1)
        self.assertEqual(apply_review_plan(conn, {"version": 1, "changes": [event()]})["reopened"], 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM master_contract_split_history").fetchone()[0], 2)
        conn.close()

    def test_open_contract_stops_current_report_and_reclose_restores_it(self):
        snapshot, agreement, value, stored = fixture()
        self.assertEqual(analyze_contractual_income(snapshot, [income()])["covered"], 100)
        change = event(["Proyecto", "Artista"], ["Proyecto", "Artista", "Nuevo"])
        pending = project_review(saved(value), change)
        catalog_rows = [{"isrc": stored[0]["isrc"], "title": "Tema", "artists_informed": "Proyecto / Artista / Nuevo"}]
        reopened = [{"isrc": stored[0]["isrc"], "is_closed": False, "version": 2, "split": pending}]
        result = analyze_contractual_income(freeze_contract_snapshot(["Proyecto"], catalog_rows, reopened), [income()])
        self.assertEqual((result["total"], result["covered"], result["pending"]), (100, 0, 100))
        for _, allocation in allocations(pending):
            allocation["participants"][-1]["percent"] = 0
        pending["agreement_confirmed"] = True
        validate_split(pending, True, False)
        reopened[0]["is_closed"] = True
        result = analyze_contractual_income(freeze_contract_snapshot(["Proyecto"], catalog_rows, reopened), [income()])
        self.assertEqual(result["covered"], 100)

    def test_reopened_proposal_survives_previously_closed_history(self):
        pending = project_review(saved(), event())
        current = {"split": pending, "closed": False, "version": 2, "future_reports_selected": False}
        result, info = propose_participants(pending, ["Lead", "Guest"], saved=current, history=[{"is_closed": True}])
        self.assertEqual(info["status"], "catalog_reopened")
        self.assertIsNone(result["participants"][0]["percent"])

    def test_review_receipt_is_server_preserved_when_request_model_drops_it(self):
        previous = {"split": project_review(saved(), event())}
        submitted = split()
        result = preserve_review(submitted, previous, closed=True, actor="human")
        self.assertEqual(result[REVIEW]["status"], "reviewed")
        self.assertEqual(result[REVIEW]["fingerprint"], previous["split"][REVIEW]["fingerprint"])
        self.assertNotIn(REVIEW, submitted)

    def test_pending_publication_event_carried_over_and_stale_event_not_replayed(self):
        old, new = catalog(["Lead"]), catalog(["Lead", "Guest"])
        plan = build_review_plan(old, new)
        self.assertEqual(build_review_plan(new, new, plan), plan)
        self.assertEqual(build_review_plan(new, catalog(["Lead", "Other"]), plan)["changes"][0]["after"], ["Lead", "Other"])

    def test_more_than_ten_guests_reopens_without_hiding_anyone(self):
        all_names = ["Lead", *["Guest " + str(i) for i in range(12)]]
        pending = project_review(saved(), event(["Lead"], all_names))
        self.assertTrue(pending[REVIEW]["capacity_exceeded"])
        validate_split(pending, False, False)
        projected, info = propose_participants(pending, all_names,
            saved={"split": pending, "closed": False}, history=[{"is_closed": True}])
        self.assertEqual(len(projected["participants"]), 12)
        self.assertTrue(info["capacity_exceeded"])

    def test_failed_post_publication_review_is_recovered_without_another_catalog_change(self):
        objects = {}
        def parquet_bytes(frame):
            stream = io.BytesIO()
            frame.write_parquet(stream)
            return stream.getvalue()
        objects["old.parquet"] = parquet_bytes(catalog(["Lead"]))
        objects["marts/release_manifest.json"] = json.dumps({"files": {
            "catalog_master.parquet": {"object_name": "old.parquet", "generation": "1"}}}).encode()
        class Blob:
            def __init__(self, name):
                self.name = name
            def download_as_text(self, **kwargs):
                return objects[self.name].decode()
            def download_to_filename(self, path, **kwargs):
                from pathlib import Path
                Path(path).write_bytes(objects[self.name])
        class Bucket:
            def blob(self, name, **kwargs):
                return Blob(name)
        def publish(bucket, prefix, uploads):
            from pathlib import Path
            entries = {}
            for name, path in uploads:
                objects["new/" + name] = Path(path).read_bytes()
                entries[name] = {"object_name": "new/" + name, "generation": "1"}
            objects["marts/release_manifest.json"] = json.dumps({"files": entries}).encode()
            return {"release_id": "fake"}
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new.parquet"
            catalog(["Lead", "Guest"]).write_parquet(path)
            factory = MagicMock()
            with patch("app.catalog_participant_review.is_postgres_connection", return_value=True), patch(
                "app.catalog_participant_review.apply_review_plan", side_effect=[RuntimeError("Simulated review retry"), {"reopened": 1}]) as apply:
                with self.assertRaises(RuntimeError):
                    publish_with_participant_review(Bucket(), "marts", [("catalog_master.parquet", path)],
                        publisher=publish, connection_factory=factory)
                result = publish_with_participant_review(Bucket(), "marts", [("catalog_master.parquet", path)],
                    publisher=publish, connection_factory=factory)
                self.assertEqual(result["contract_participant_review"]["reopened"], 1)
                self.assertEqual(apply.call_args_list[0].args[1], apply.call_args_list[1].args[1])


if __name__ == "__main__":
    unittest.main()
