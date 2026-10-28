"""Compatibility of the approved identity correction with current production consumers."""
import io
import json
import unittest
from contextlib import nullcontext
from unittest.mock import MagicMock, patch
from app.master_contract_metadata import with_external_titles
from app.catalog_participant_review import review_published_participants


class CurrentProductionIdentityTests(unittest.TestCase):
    def test_standalone_worker_imports_without_api_path_bootstrap(self):
        import subprocess
        import sys
        from pathlib import Path
        root = str(Path(__file__).resolve().parents[2])
        code = ("import sys;sys.path.insert(0," + repr(root) + ");"
            "import app.catalog_participant_review;"
            "from app.master_contract_metadata import with_external_titles;"
            "assert with_external_titles([],[])==[];"
            "from app.master_contracts import artist_suggestions;"
            "assert artist_suggestions('XXAAA2500001',None,'Lead')['artists']==['Lead']")
        result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def metadata(self, artist="Dormun", title="El Farsante", upc="8721093907237"):
        return {"lookup_isrc": "ARDL12400078", "lookup_upc": upc, "lookup_artist": artist,
            "lookup_title": title, "metadata_status": "found", "raw_json": json.dumps({"selected": {
                "name": title, "external_ids": {"isrc": "ARDL12400078"}}})}

    def test_corrected_external_title_stays_with_dormun_not_lit_killah(self):
        rows = with_external_titles([{"asset_isrc": "ARDL12400078"}, {"asset_isrc": "ARDL12600160"}], [self.metadata()])
        self.assertEqual(rows[0]["contract_external_titles"], [])
        self.assertEqual(rows[1]["contract_external_titles"], ["El Farsante"])

    def test_lit_killah_external_title_unchanged(self):
        rows = with_external_titles([{"asset_isrc": "ARDL12400078"}],
            [self.metadata("LIT killah & Nicki Nicole", "Somos 3", "5034644050102")])
        self.assertEqual(rows[0]["contract_external_titles"], ["Somos 3"])

    def test_empty_metadata_is_unchanged(self):
        self.assertEqual(with_external_titles([{"asset_isrc": "ARDL12400078"}], []),
            [{"asset_isrc": "ARDL12400078", "contract_external_titles": []}])

    def test_native_external_isrc_still_must_match(self):
        value = self.metadata()
        value["raw_json"] = json.dumps({"selected": {"name": "Wrong", "external_ids": {"isrc": "OTHER"}}})
        self.assertEqual(with_external_titles([{"asset_isrc": "ARDL12600160"}], [value])[0]["contract_external_titles"], [])

    def test_durable_worker_replays_pinned_participant_plan(self):
        client, blob, plan_blob = MagicMock(), MagicMock(), MagicMock()
        client.bucket.return_value.blob.side_effect = [blob, plan_blob]
        blob.generation = 7
        blob.download_as_bytes.return_value = json.dumps({"release_id": "release-a", "files": {
            "catalog_participant_changes.json": {"object_name": "immutable/plan.json", "generation": "9"}}}).encode()
        plan = {"version": 1, "changes": []}
        plan_blob.download_as_bytes.return_value = json.dumps(plan).encode()
        conn = MagicMock()
        with patch("app.operational_db.operational_connect", return_value=nullcontext(conn)), patch(
                "app.catalog_participant_review.is_postgres_connection", return_value=True), patch(
                "app.catalog_participant_review.apply_review_plan", return_value={"reopened": 0}) as apply:
            self.assertEqual(review_published_participants(client, {"bucket": "private", "prefix": "marts", "release_id": "release-a"}), {"reopened": 0})
            apply.assert_called_once_with(conn, plan)
            blob.download_as_bytes.assert_called_once_with(if_generation_match=7)
            plan_blob.download_as_bytes.assert_called_once_with(if_generation_match=9)

    def test_durable_worker_does_not_replay_different_release(self):
        client = MagicMock()
        client.bucket.return_value.blob.return_value.download_as_bytes.return_value = b'{"release_id":"new"}'
        with self.assertRaises(ValueError), patch("app.catalog_participant_review.apply_review_plan") as apply:
            review_published_participants(client, {"bucket": "private", "release_id": "old"})
        apply.assert_not_called()


if __name__ == "__main__":
    unittest.main()
