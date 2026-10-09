from __future__ import annotations

import copy
import unittest
from unittest.mock import MagicMock, patch

from scripts.qa.qa_master_contract_associations import ISRC, OTHER, choice, evidence
from app import vpo_corp_api as api
from app.master_contract_associations import append_missing_choices, candidates, unresolved_associations, validate_choices, validate_closure
from app.master_contract_income import consolidate_associated_income
from app.master_contract_metadata import infer_video_evidence

VIDEO = "uqY-3RS-V0Y"


def recording(isrc=ISRC, title="Movimento", performers="DJ Plaga and MC Tota", **extra):
    return {"asset_isrc": isrc, "track_title": title, "artist_statement": performers, **extra}


def video(**extra):
    values = {"source": "fuga", "account": "indyana_records", "isrcs": [],
              "titles": ["Movimento - DJ Plaga, MC Tota (Video Oficial)"], "artists": [], **extra}
    return evidence("VIDEO", VIDEO, **values)


class ContractMetadataTests(unittest.TestCase):
    def infer(self, catalog=None, rows=None):
        return infer_video_evidence(catalog or [recording()], rows or [video()])

    def items(self, rows=None, overrides=None, catalog=None, claims=None):
        return candidates(ISRC, self.infer(catalog, rows), {f"VIDEO:{VIDEO}": f"VIDEO:{VIDEO}"}, overrides or [], claims or {})

    def test_strong_video_included_without_catalog_or_evidence_mutation(self):
        catalog, rows = [recording()], [video()]
        before = copy.deepcopy((catalog, rows))
        inferred = self.infer(catalog, rows)
        item = self.items(rows, catalog=catalog)[0]
        self.assertEqual(inferred[0]["inferred_isrcs"], [ISRC])
        self.assertEqual(item["status"], "automatic")
        self.assertTrue(item["included"])
        self.assertEqual((catalog, rows), before)
        validate_closure([item], [])

    def test_normalization_order_accents_and_full_artist_credit(self):
        item = self.items([video(titles=["MC Tota & DJPlaga - MOVIM\u00c9NTO (Official Video)"])],
                          catalog=[recording(title="Movim\u00e9nto")])[0]
        self.assertTrue(item["automatic"])

    def test_partial_artist_variant_not_used_as_proof(self):
        rows = self.infer([recording(artist_variants="DJ Plaga")],
                          [video(titles=["DJ Plaga - Movimento (Video Oficial)"])])
        self.assertEqual(rows[0]["inference_status"], "incomplete")
        self.assertFalse(self.items(rows, catalog=[recording(artist_variants="DJ Plaga")])[0]["automatic"])

    def test_wrong_guest_never_proposed(self):
        rows = self.infer(rows=[video(titles=["DJ Plaga, Otra Persona - Movimento (Video Oficial)"])])
        self.assertNotIn("inferred_isrcs", rows[0])

    def test_channel_name_not_used_as_performer_credit(self):
        rows = self.infer([recording(performers="DJ Plaga")],
                          [video(source="onerpm", titles=["Movimento"], artists=["DJ Plaga"])])
        self.assertNotIn("inferred_isrcs", rows[0])

    def test_two_isrcs_same_credits_pending_not_merged(self):
        catalog = [recording(), recording(OTHER)]
        item = self.items(catalog=catalog)[0]
        self.assertFalse(item["automatic"])
        self.assertTrue(item["selectable"])
        self.assertEqual(item["status"], "pending")
        with self.assertRaisesRegex(ValueError, "cerrar"):
            validate_closure([item], [])
        validate_closure([item], [choice(item, False)])
        validate_closure([item], [choice(item)])

    def test_other_credit_variants_veto_false_uniqueness(self):
        catalog = [recording(performers="DJ Plaga and ROZE OFICIAL"),
                   recording(OTHER, performers="DJ Plaga and ROZE", artist_variants="DJ Plaga and ROZE OFICIAL")]
        rows = self.infer(catalog, [video(titles=["DJ Plaga, ROZE OFICIAL - Movimento"])])
        self.assertEqual(rows[0]["inferred_isrcs"], sorted([ISRC, OTHER]))
        self.assertEqual(rows[0]["inference_status"], "ambiguous")

    def test_raw_version_not_removed_or_ignored_by_cleaned_title(self):
        rows = self.infer(rows=[video(artists=["Movimento - DJ Plaga, MC Tota (Video Oficial) Set Session 1"])])
        self.assertEqual(rows[0]["inference_status"], "version")
        rows = self.infer(rows=[video(titles=["DJ Plaga, MC Tota - Movimento (Remix)"])])
        self.assertNotIn("inferred_isrcs", rows[0])

    def test_explicit_same_remix_version_can_be_automatic(self):
        item = self.items([video(titles=["DJ Plaga, MC Tota - Movimento (Remix) (Video Oficial)"])],
                          catalog=[recording(title="Movimento (Remix)")])[0]
        self.assertTrue(item["automatic"])

    def test_changed_source_title_cannot_silently_reassign(self):
        rows = self.infer(rows=[video(titles=["Movimento - DJ Plaga, MC Tota (Video Oficial)", "Otra Cancion - Otro Artista"])])
        self.assertEqual(rows[0]["inference_status"], "incomplete")

    def test_explicit_other_isrc_blocks_metadata_inference_but_allows_discard(self):
        item = self.items([video(isrcs=[OTHER])])[0]
        self.assertFalse(item["selectable"])
        self.assertFalse(item["included"])
        with self.assertRaises(ValueError):
            validate_closure([item], [])
        validate_closure([item], [choice(item, False)])

    def test_existing_exact_association_keeps_signature(self):
        row = video(isrcs=[ISRC])
        aliases = {f"VIDEO:{VIDEO}": f"ISRC:{ISRC}"}
        old = candidates(ISRC, [row], aliases, [], {})[0]
        new = candidates(ISRC, self.infer(rows=[row]), aliases, [choice(old)], {})[0]
        self.assertEqual(old["evidence_signature"], new["evidence_signature"])
        self.assertEqual(new["status"], "confirmed")

    def test_new_statement_keeps_identity_signature(self):
        old = self.items()[0]
        new = self.items([video(titles=["MOVIMENTO - MC Tota, DJ PLAGA (Official Video)"])])[0]
        self.assertEqual(old["evidence_signature"], new["evidence_signature"])

    def test_new_competing_isrc_suspends_old_confirmation(self):
        old = self.items()[0]
        new = self.items(overrides=[choice(old)], catalog=[recording(), recording(OTHER)])[0]
        self.assertEqual(new["status"], "pending")
        self.assertFalse(new["included"])
        with self.assertRaises(ValueError):
            validate_closure([new], [choice(old)])

    def test_manual_discard_survives_new_account_and_is_not_overwritten(self):
        old = self.items()[0]
        new = self.items([video(), video(source="onerpm", account="la_nueva_sangre")], [choice(old, False)])
        self.assertTrue(all(item["status"] == "excluded" and not item["included"] for item in new))
        validate_closure(new, [choice(old, False)])

    def test_other_contract_claim_protects_all_sources(self):
        old = self.items()[0]
        new = self.items([video(source="onerpm", account="la_nueva_sangre")], claims={old["key"]: OTHER})[0]
        self.assertFalse(new["selectable"])

    def test_orphaned_confirmation_blocks_close_but_discard_does_not(self):
        selected = choice(self.items()[0])
        with self.assertRaises(ValueError):
            validate_closure([], [selected])
        validate_closure([], [{**selected, "included": False}])

    def test_missing_included_code_is_visible_and_can_be_discarded(self):
        selected = choice(self.items()[0])
        rows = append_missing_choices([], [selected])
        self.assertFalse(rows[0]["selectable"])
        discarded = choice(rows[0], False)
        validate_choices([discarded], [selected], rows)
        validate_closure(rows, [discarded])

    def test_reusing_evidence_does_not_keep_obsolete_inference(self):
        inferred = self.infer()
        result = infer_video_evidence([recording(title="Otro Tema")], inferred)
        self.assertNotIn("inferred_isrcs", result[0])

    def test_shared_album_upc_not_inferred(self):
        rows = infer_video_evidence([recording()], [evidence(isrcs=[], titles=["Movimento"], artists=["DJ Plaga and MC Tota"])])
        self.assertNotIn("inferred_isrcs", rows[0])

    def test_automatic_income_counts_once_and_respects_statement_cutoff(self):
        row = {"source": "fuga", "account": "indyana_records", "asset_isrc": "", "video_id": VIDEO,
               "track_id": VIDEO, "product_upc": "", "statement_period": "2026-06", "amount_usd": 10}
        evidence_rows = self.infer()
        result = consolidate_associated_income([row, {**row, "statement_period": "2026-07", "amount_usd": 100}],
            evidence_rows, {f"VIDEO:{VIDEO}": f"VIDEO:{VIDEO}"}, {}, {}, "2026-06")
        self.assertEqual(result[ISRC]["amount_usd"], 10)
        self.assertEqual(sum(group["amount_usd"] for group in result[ISRC]["groups"]), 10)
        item = self.items()[0]
        self.assertEqual(consolidate_associated_income([row], evidence_rows,
            {f"VIDEO:{VIDEO}": f"VIDEO:{VIDEO}"}, {ISRC: [choice(item, False)]}, {}, "2026-06"), {})

    def test_close_without_choice_changes_rechecks_under_lock_and_does_not_save(self):
        conn = MagicMock()
        pending = self.items(catalog=[recording(), recording(OTHER)])
        request = api.MasterContractSaveRequest(split={}, expected_version=1, closed=True)
        with patch.object(api, "require_api_key"), patch.object(api, "operational_connect") as connect, \
             patch.object(api, "require_master_contract_user", return_value="editor"), \
             patch.object(api, "master_contract_catalog") as catalog, \
             patch.object(api, "read_split", return_value={"split": {}, "version": 1, "closed": False}), \
             patch.object(api, "is_postgres_connection", return_value=True), \
             patch.object(api, "db_sql", side_effect=lambda _, sql: sql), \
             patch.object(api, "read_contract_association_claims", return_value={}), \
             patch.object(api, "master_contract_associations", return_value=pending) as verify, \
             patch.object(api, "save_split") as save:
            connect.return_value.__enter__.return_value = conn
            catalog.return_value.filter.return_value.is_empty.return_value = False
            with self.assertRaises(api.HTTPException) as error:
                api.put_master_contract(ISRC, request, "key", "editor")
            self.assertEqual(error.exception.status_code, 400)
            self.assertIn("por validar", error.exception.detail)
            save.assert_not_called()
            verify.assert_called_once()
            self.assertIn("pg_advisory_xact_lock", conn.execute.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
