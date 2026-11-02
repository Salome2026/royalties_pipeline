from __future__ import annotations

import copy
import json
import unittest
import subprocess
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.qa.qa_master_contract_metadata import recording, video
from scripts.qa.qa_master_contract_associations import ISRC, OTHER, choice
from app.master_contract_metadata import infer_video_evidence, with_external_titles
from app.master_contract_associations import candidates, validate_closure, review_identity_evidence, append_missing_choices
from app.master_contract_review import evidence_by_contract, pending_details, review_state, save_review, reconcile_reviews, review_revision, enrich_review_evidence
from app import vpo_corp_api as api


class ContractReviewTests(unittest.TestCase):
    def test_native_identified_recording_does_not_create_a_new_metadata_proposal(self):
        native = video(isrcs=[OTHER], has_unassigned_rows=False)
        result = enrich_review_evidence([recording()], [native])
        self.assertNotIn("inferred_isrcs", result[0])
        discovered = enrich_review_evidence([recording()], [{**native, "has_unassigned_rows": True}])
        self.assertEqual(discovered[0]["inferred_isrcs"], [ISRC])

    def test_editor_catalog_seeds_are_also_reviewed_without_a_catalog_alias(self):
        row = video(isrcs=[], inferred_isrcs=[])
        grouped = evidence_by_contract([row], {}, {ISRC: []}, {},
            catalog=[{"asset_isrc": ISRC, "video_ids": row["code"]}])
        self.assertEqual(grouped[ISRC], [row])

    def test_browser_and_server_agree_on_reference_and_financial_pending_states(self):
        native = video(isrcs=[ISRC, OTHER], only_ugc_rows=True, has_identified_rows=True, has_unassigned_rows=False)
        old = candidates(ISRC, [video(isrcs=[ISRC])], {}, [], {})[0]
        cases = []
        for rows in [[native], [{**native, "has_unassigned_rows": True}],
                     [{**native, "only_ugc_rows": False}], []]:
            for decisions in [[choice(old)], [choice(old, False)], []]:
                items = append_missing_choices(candidates(ISRC, rows, {}, decisions, {}), decisions)
                cases.append({"items": items, "choices": decisions,
                              "expected": review_state(pending_details(items, decisions))["association_pending_codes"]})
        script = """const fs=require('fs'),ts=require('./web/node_modules/typescript');
const source=fs.readFileSync('./web/app/features/master-contracts/associationLogic.ts','utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const m={exports:{}};new Function('exports','module',compiled)(m.exports,m);
const rows=JSON.parse(fs.readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(rows.map(r=>({codes:m.exports.pendingAssociationCodes(r.items,r.choices),sections:m.exports.groupedAssociations(r.items,r.choices).map(g=>g.section)}))));"""
        completed = subprocess.run([shutil.which("node"), "-e", script], input=json.dumps(cases),
            capture_output=True, text=True, check=True, cwd=Path(__file__).resolve().parents[2])
        results = json.loads(completed.stdout)
        for case, result in zip(cases, results): self.assertEqual(result["codes"], case["expected"])
        self.assertEqual(results[0]["sections"], ["ugc"])

    def test_batch_includes_identified_and_saved_codes_and_keeps_native_context(self):
        row = video(isrcs=[ISRC], content_origins=["UGC / Content ID"], only_ugc_rows=True,
                    has_identified_rows=True, has_unassigned_rows=False)
        client = MagicMock(); client.query.return_value.result.return_value = [row]
        key = json.dumps(["VIDEO", row["code"], row["source"], row["account"]], separators=(",", ":"))
        choices = {ISRC: [{"key": key, "included": True, "evidence_signature": "previous"}]}
        result = review_identity_evidence("release", [dict(asset_isrc=ISRC, upcs="123", video_ids=row["code"])], choices, client=client)
        self.assertEqual(result, [row])
        sql = client.query.call_args.args[0]
        config = client.query.call_args.kwargs["job_config"]
        params = {p.name: p for p in config.query_parameters}
        self.assertIn("asset_isrc IN UNNEST(@review_isrcs)", sql)
        self.assertIn("UNNEST(@saved_codes)", sql)
        self.assertIn("has_unassigned_rows", sql)
        self.assertEqual(params["review_isrcs"].values, [ISRC])
        self.assertEqual(params["saved_codes"].values, [key])
        self.assertTrue(params["include_unassigned"].value)
        grouped = evidence_by_contract(result, {}, choices, {})
        items = candidates(ISRC, grouped[ISRC], {}, choices[ISRC], {})
        self.assertEqual(pending_details(append_missing_choices(items, choices[ISRC]), choices[ISRC]), [])
        self.assertEqual(choices[ISRC][0]["evidence_signature"], "previous")

    def test_identified_shared_ugc_does_not_reopen_saved_review_or_assign_money(self):
        row = video(isrcs=[ISRC, OTHER], only_ugc_rows=True, has_identified_rows=True, has_unassigned_rows=False)
        old = candidates(ISRC, [video(isrcs=[ISRC])], {}, [], {})[0]
        decisions = [choice(old)]; before = copy.deepcopy(decisions)
        items = candidates(ISRC, [row], {}, decisions, {})
        self.assertEqual(pending_details(items, decisions), [])
        self.assertFalse(items[0]["included"])
        self.assertEqual(items[0]["status"], "blocked")
        self.assertEqual(items[0]["isrcs"], sorted([ISRC, OTHER]))
        self.assertEqual(decisions, before)

    def test_unassigned_or_non_ugc_in_any_account_restores_financial_review(self):
        identified = video(isrcs=[ISRC, OTHER], only_ugc_rows=True, has_identified_rows=True, has_unassigned_rows=False)
        old = candidates(ISRC, [video(isrcs=[ISRC])], {}, [], {})[0]
        for change in [{"has_unassigned_rows": True}, {"only_ugc_rows": False}]:
            rows = [identified, {**identified, "source": "orchard", "account": "other", **change}]
            items = candidates(ISRC, rows, {}, [choice(old)], {})
            self.assertTrue(all(i["reference_group"] == "associated" for i in items))
            self.assertTrue(pending_details(items, [choice(old)]))

    def test_genuinely_missing_saved_code_still_requires_review(self):
        old = self.items()[0]
        choices = [choice(old)]
        self.assertTrue(pending_details(append_missing_choices([], choices), choices))

    def test_human_decision_race_aborts_before_review_writes(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [{"isrc": ISRC, "payload_json": {"code_association_overrides": []}, "version": 2}]
        with patch("app.master_contract_review.ensure_schema"), self.assertRaises(RuntimeError):
            reconcile_reviews(conn, "release", [], {}, expected_choices={ISRC: [{"key": "new"}]})
        self.assertFalse(any("INSERT" in c.args[0] or "UPDATE" in c.args[0] for c in conn.execute.call_args_list))

    def test_same_release_rechecks_new_catalog_or_external_metadata_generation(self):
        manifest = {"bucket": "b", "objects": {"catalog_master.parquet": {"object": "catalog", "generation": 1}}}
        first = review_revision(manifest, {"object": "metadata", "generation": 5})
        changed = copy.deepcopy(manifest); changed["objects"]["catalog_master.parquet"]["generation"] = 2
        self.assertNotEqual(first, review_revision(changed, {"object": "metadata", "generation": 5}))
        self.assertNotEqual(first, review_revision(manifest, {"object": "metadata", "generation": 6}))
        self.assertEqual(first, review_revision(manifest, {"object": "metadata", "generation": "5", "size_bytes": 123}))
        changed = copy.deepcopy(manifest)
        changed['objects']['product_income_allocations.json'] = {'object':'products','generation':3}
        self.assertNotEqual(first, review_revision(changed, {"object":"metadata","generation":5}))

    def test_background_review_uses_validated_product_like_live_editor(self):
        import polars as pl
        from app.master_contract_review import review_aliases
        from scripts.lib.product_income import use_product_income
        upc='790092134546'
        catalog=pl.DataFrame({'catalog_key':['ISRC:'+ISRC,'TEXT:funky rocho|credits'], 'upcs':[upc,upc]})
        index={'schema_version':1,'scope':'regular','rule':'product-income-equal-tracks-v1',
            'products':{'UPC:'+upc.zfill(14):{'status':'validated','tracks':[{'isrc':ISRC,'position':1}]}}}
        self.assertNotIn('UPC:'+upc,review_aliases(catalog,None))
        aliases=review_aliases(catalog,index)
        self.assertEqual(aliases['UPC:'+upc],'ISRC:'+ISRC)
        row={'kind':'UPC','code':upc,'source':'fuga','account':'indyana_records','isrcs':[ISRC]}
        self.assertTrue(candidates(ISRC,[row],aliases,[],{})[0]['automatic'])
        self.assertEqual(pending_details(candidates(ISRC,[row],aliases,[],{}),[]),[])
        with use_product_income(index):
            self.assertNotIn('UPC:'+upc,review_aliases(catalog,None))

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
             patch("app.catalog_participant_review.review_published_participants") as participant_review, \
             patch("app.royalty_reports.contract_identity.publish_ranking_guard"), \
             patch.dict("os.environ", {"GCS_BUCKET": "bucket"}):
            connect.return_value.__enter__.return_value = conn
            run_refresh()
            review.assert_called_once()
            participant_review.assert_called_once()

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
