from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import MagicMock, patch

from scripts.qa.qa_master_contract_metadata import recording, video
from scripts.qa.qa_master_contract_associations import ISRC, OTHER, choice
from app.master_contract_metadata import infer_video_evidence, with_external_titles
from app.master_contract_associations import candidates, validate_closure
from app.master_contract_review import evidence_by_contract, pending_details, review_state, save_review
from app import vpo_corp_api as api


class ContractReviewTests(unittest.TestCase):
    def items(self, rows=None, catalog=None, choices=None):
        rows = rows or [video(titles=["Movimento Remix - DJ Plaga, MC Tota (Official Video)"])]
        enriched = infer_video_evidence(catalog or [recording()], rows)
        return candidates(ISRC, enriched, {"VIDEO:" + rows[0]["code"]: "VIDEO:" + rows[0]["code"]}, choices or [], {})

    def test_version_mismatch_is_visible_selectable_and_never_included(self):
        item = self.items()[0]
        self.assertEqual(item["status"], "pending")
        self.assertTrue(item["selectable"])
        self.assertFalse(item["automatic"])
        self.assertFalse(item["included"])
        self.assertEqual(item["proposed_isrcs"], [ISRC])
        with self.assertRaises(ValueError):
            validate_closure([item], [])
        validate_closure([item], [choice(item)])
        validate_closure([item], [choice(item, False)])

    def test_original_with_different_credits_is_not_a_candidate(self):
        row = {**video(titles=["MOVIMENTO - MC Tota - DJ Machu-K (DM RECORDS)"]), "code": "PTIN0kcBank"}
        result = infer_video_evidence([recording()], [row])[0]
        self.assertNotIn("inferred_isrcs", result)

    def test_original_and_remix_contracts_with_same_credits_both_need_review(self):
        rows = infer_video_evidence([recording(), recording(OTHER, title="Movimento Remix")], [video()])
        self.assertEqual(rows[0]["inference_status"], "ambiguous")
        self.assertEqual(rows[0]["inferred_isrcs"], sorted([ISRC, OTHER]))

    def test_external_title_requires_exact_isrc_and_does_not_rewrite_catalog(self):
        catalog = [recording(title="Nombre antiguo")]
        before = copy.deepcopy(catalog)
        metadata = [{"lookup_isrc": ISRC, "metadata_status": "found", "raw_json": json.dumps({
            "selected": {"name": "Movimento Remix", "external_ids": {"isrc": ISRC}}})}]
        enriched = with_external_titles(catalog, metadata)
        item = self.items(catalog=enriched)[0]
        self.assertEqual(item["status"], "pending")
        self.assertEqual(catalog, before)
        metadata[0]["lookup_isrc"] = OTHER
        self.assertFalse(with_external_titles(catalog, metadata)[0]["contract_external_titles"])

    def test_amount_and_month_changes_do_not_change_review_or_confirmation(self):
        old = self.items()[0]
        later = self.items([video(titles=["Movimento Remix - DJ Plaga, MC Tota (Official Video)"],
                                 statement_period="2026-07", amount_usd=1000)])[0]
        self.assertEqual(pending_details([old], []), pending_details([later], []))
        confirmed = self.items(choices=[choice(old)])[0]
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(pending_details([confirmed], [choice(old)]), [])

    def test_discard_survives_new_source_and_new_statement(self):
        old = self.items()[0]
        later = self.items([video(source="onerpm", account="another", titles=[
            "Movimento Remix - DJ Plaga, MC Tota (Official Video)"])], choices=[choice(old, False)])[0]
        self.assertEqual(later["status"], "excluded")
        self.assertEqual(pending_details([later], [choice(old, False)]), [])

    def test_new_code_reopens_review_without_mutating_agreement_or_old_decisions(self):
        old = self.items()[0]
        decisions = [choice(old)]
        before = copy.deepcopy(decisions)
        old_video = video(titles=["Movimento Remix - DJ Plaga, MC Tota (Official Video)"])
        new_video = {**old_video, "code": "newVideo123"}
        inferred = infer_video_evidence([recording()], [old_video, new_video])
        grouped = evidence_by_contract(inferred, {}, {ISRC: decisions}, {})
        aliases = {"VIDEO:" + row["code"]: "VIDEO:" + row["code"] for row in inferred}
        items = candidates(ISRC, grouped[ISRC], aliases, decisions, {})
        state = review_state(pending_details(items, decisions))
        self.assertTrue(state["association_review_pending"])
        self.assertEqual(state["association_pending_codes"], ["newVideo123"])
        self.assertEqual(decisions, before)

    def test_identical_review_has_no_second_history_event(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        items = self.items()
        save_review(conn, ISRC, 6, "release-a", items, [], "statement-review")
        calls = conn.execute.call_args_list
        upsert = next(call for call in calls if "INSERT INTO master_contract_association_reviews\n" in call.args[0])
        fingerprint = upsert.args[1][-1]
        conn.reset_mock()
        conn.execute.return_value.fetchone.return_value = {"review_fingerprint": fingerprint}
        save_review(conn, ISRC, 6, "release-b", items, [], "statement-review")
        self.assertFalse(any("INSERT INTO master_contract_association_review_history" in c.args[0] for c in conn.execute.call_args_list))
        self.assertFalse(any("UPDATE master_contract_splits" in c.args[0] for c in conn.execute.call_args_list))

    def test_saving_partial_decisions_keeps_approved_split_but_completing_is_blocked(self):
        conn = MagicMock()
        item = self.items()[0]
        for complete in (False, True):
            request = api.MasterContractSaveRequest(split={}, expected_version=6, closed=True,
                                                    complete_association_review=complete)
            with patch.object(api, "require_api_key"), patch.object(api, "operational_connect") as connect, \
                 patch.object(api, "require_master_contract_user", return_value="editor"), \
                 patch.object(api, "master_contract_catalog") as catalog, \
                 patch.object(api, "read_split", return_value={"split": {}, "closed": True, "version": 6}), \
                 patch.object(api, "is_postgres_connection", return_value=True), \
                 patch.object(api, "db_sql", side_effect=lambda _, sql: sql), \
                 patch.object(api, "read_contract_association_claims", return_value={}), \
                 patch.object(api, "master_contract_associations", return_value=[item]), \
                 patch("app.master_contract_review.ensure_schema"), \
                 patch.object(api, "save_association_review", return_value={"association_review_pending": True}), \
                 patch.object(api, "save_split", return_value={"version": 7}) as save:
                connect.return_value.__enter__.return_value = conn
                catalog.return_value.filter.return_value.is_empty.return_value = False
                if complete:
                    with self.assertRaises(api.HTTPException):
                        api.put_master_contract(ISRC, request, "key", "editor")
                    save.assert_not_called()
                else:
                    result = api.put_master_contract(ISRC, request, "key", "editor")
                    self.assertTrue(result["association_review_pending"])
                    self.assertTrue(save.call_args.kwargs["closed"])

    def test_ready_dashboard_still_runs_release_review(self):
        from app.catalog_refresh import run_refresh
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {"locked": True}
        bq = MagicMock()
        bq.query.return_value.result.return_value = [{"release_id": "release-a"}]
        with patch("app.operational_db.operational_connect") as connect, \
             patch("app.catalog_refresh.storage.Client"), patch("google.cloud.bigquery.Client", return_value=bq), \
             patch("app.catalog_refresh.dashboard_state", return_value={"catalog_generation": "1"}), \
             patch("app.catalog_refresh.catalog_generation", return_value="1"), \
             patch("app.catalog_refresh.read_json", return_value={"release_id": "release-a"}), \
             patch("app.catalog_refresh.select_dashboard_release", return_value=("ready", "ready")), \
             patch("app.royalty_reports.manifests.build_gcs_input_manifest", return_value={"release_id": "release-a"}), \
             patch("app.master_contract_review.review_published_release") as review, \
             patch.dict("os.environ", {"GCS_BUCKET": "bucket"}):
            connect.return_value.__enter__.return_value = conn
            run_refresh()
            review.assert_called_once()

    def test_list_review_filter_keeps_closed_economic_state_and_income(self):
        import polars as pl
        catalog = pl.DataFrame({"asset_isrc": [ISRC, OTHER], "track_title": ["Uno", "Dos"],
            "artist_statement": ["Artist", "Artist"], "artist_variants": ["Artist", "Artist"],
            "amount_usd": [12.5, 23.0], "isrc_amount_usd": [12.5, 23.0], "associated_amount_usd": [0., 0.],
            "_contract_first_statement_month": ["2026-01", "2026-01"],
            "_contract_last_statement_month": ["2026-06", "2026-06"], "sources": ["fuga", "fuga"]})
        memberships = pl.DataFrame({"asset_isrc": [ISRC, OTHER], "source": ["fuga", "fuga"],
                                    "account": ["account", "account"]})
        with patch.object(api, "require_api_key"), patch.object(api, "operational_connect"), \
             patch.object(api, "require_master_contract_user"), \
             patch.object(api, "read_split_statuses", return_value={ISRC: {"closed": True}, OTHER: {"closed": True}}), \
             patch.object(api, "read_contract_association_choices", return_value={}), \
             patch.object(api, "read_association_review_states", return_value={ISRC: {
                 "association_review_pending": True, "association_pending_count": 1}}), \
             patch.object(api, "master_contract_associated_income", return_value={}), \
             patch.object(api, "master_contract_catalog", return_value=catalog), \
             patch.object(api, "master_contract_source_accounts", return_value=memberships):
            result = api.list_master_contracts(status="review", x_vpo_username="editor")
            self.assertEqual(result["total"], 1)
            self.assertTrue(result["items"][0]["closed"])
            self.assertEqual(result["items"][0]["amount_usd"], 12.5)
            self.assertEqual(result["summary"], {"open": 0, "closed": 2, "review": 1})


if __name__ == "__main__":
    unittest.main()
