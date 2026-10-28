"""Manual reference links preserve amounts, native identity and contract percentages."""
from copy import deepcopy
from contextlib import ExitStack
import unittest
from unittest.mock import MagicMock, patch

from app import vpo_corp_api as api
from app.master_contract_associations import association_key, candidates, validate_choices
from app.master_contract_income import income_association_index, associated_income_isrc, consolidate_associated_income
from app.master_contract_link import prepare_link, validate_row_destinations

ISRC, OTHER, CODE = "ARDL12600006", "ARDL12600005", "abcdefghijk"
REAL_PREPARE = api.prepare_unidentified_link


class ManualLinkTests(unittest.TestCase):
    def setUp(self):
        self.row = {"kind": "VIDEO", "code": CODE, "source": "fuga", "account": "indyana_records",
            "isrcs": [], "titles": ["Nombre diferente"], "artists": ["Autor"], "native_ada_product": False}
        self.reference = {"id": "a" * 64, "kind": "VIDEO", "code": CODE, "amount_usd": 30.,
            "source_accounts": [{"source": "fuga", "account": "indyana_records"}]}
        self.aliases = {"VIDEO:" + CODE: "VIDEO:" + CODE}
        self.key = association_key("VIDEO", CODE, "fuga", "indyana_records")

    def prepare(self, evidence=None, choices=None, claims=None, aliases=None):
        return prepare_link(self.reference, ISRC, evidence or [self.row], self.aliases if aliases is None else aliases,
                            claims or {}, choices or [], "release-1", 7)

    def test_explicit_confirmation_without_title_inference(self):
        self.assertFalse(candidates(ISRC, [self.row], self.aliases, [], {})[0]["selectable"])
        choice = self.prepare()["choices"][0]
        item = candidates(ISRC, [self.row], self.aliases, [choice], {})[0]
        self.assertEqual(item["status"], "confirmed")
        self.assertTrue(item["manual"])

    def test_income_counted_once_with_secondary_identifier(self):
        choices = self.prepare()["choices"]
        rows = [{"source": "fuga", "account": "indyana_records", "video_id": CODE, "product_upc": "111",
                 "asset_isrc": None, "statement_period": "2026-06", "amount_usd": 10.},
                {"source": "fuga", "account": "indyana_records", "video_id": CODE,
                 "asset_isrc": None, "statement_period": "2026-07", "amount_usd": 20.}]
        result = consolidate_associated_income(rows, [self.row], self.aliases, {ISRC: choices}, {self.key: ISRC}, "2026-06")
        self.assertEqual(result[ISRC]["amount_usd"], 10.)
        self.assertEqual(sum(r["amount_usd"] for r in result[ISRC]["statement_income"]), 30.)

    def test_conflicting_native_isrc_blocks(self):
        for roots in ([OTHER], [OTHER, ISRC]):
            with self.subTest(roots=roots), self.assertRaises(ValueError):
                self.prepare([{**self.row, "isrcs": roots}])

    def test_shared_code_other_account_blocks(self):
        with self.assertRaises(ValueError):
            self.prepare([self.row, {**self.row, "account": "other", "isrcs": [OTHER]}])

    def test_native_alias_of_other_recording_blocks(self):
        with self.assertRaises(ValueError):
            self.prepare(aliases={"VIDEO:" + CODE: "ISRC:" + OTHER})

    def test_existing_claim_in_another_account_blocks(self):
        with self.assertRaises(ValueError):
            self.prepare(claims={association_key("VIDEO", CODE, "onerpm", "henry"): OTHER})

    def test_native_ada_product_remains_protected(self):
        with self.assertRaises(ValueError):
            self.prepare([{**self.row, "native_ada_product": True}])

    def test_product_and_text_are_not_assigned_by_name(self):
        for kind in ("PRODUCT", "TEXT"):
            self.reference["kind"] = kind
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.prepare()

    def test_missing_evidence_blocks(self):
        with self.assertRaises(ValueError): self.prepare([{**self.row, "code": "different"}])

    def test_old_included_accounts_and_unrelated_choices_are_preserved(self):
        old = {"key": association_key("VIDEO", CODE, "onerpm", "henry"), "included": True, "manual": True, "evidence_signature": "old"}
        other = {"key": association_key("TRACK", "123", "fuga", "indyana_records"), "included": False, "evidence_signature": "old"}
        self.assertEqual(self.prepare(choices=[old, other])["choices"][:2], [old, other])

    def test_exclusion_is_replaced_only_after_explicit_confirmation(self):
        old = {"key": self.key, "included": False, "evidence_signature": "old"}
        result = self.prepare(choices=[old])
        self.assertEqual(len(result["choices"]), 1)
        self.assertTrue(result["choices"][0]["included"])

    def test_manual_evidence_survives_metadata_proposal_changes(self):
        choice = self.prepare()["choices"][0]
        altered = {**self.row, "inferred_isrcs": [ISRC], "inference_signature": "new-title",
                   "inference_rule": "metadata", "inference_reason": "metadata"}
        self.assertEqual(candidates(ISRC, [altered], self.aliases, [choice], {})[0]["status"], "confirmed")

    def test_new_native_conflict_invalidates_existing_manual_link(self):
        choice = self.prepare()["choices"][0]
        item = candidates(ISRC, [{**self.row, "isrcs": [OTHER]}], self.aliases, [choice], {})[0]
        self.assertFalse(item["included"])
        self.assertFalse(item["selectable"])

    def test_future_rows_same_code_use_same_decision(self):
        choice = self.prepare()["choices"][0]
        index = income_association_index([self.row], self.aliases, {ISRC: [choice]}, {self.key: ISRC})
        self.assertEqual(associated_income_isrc({"source": "fuga", "account": "indyana_records", "video_id": CODE}, index), ISRC)
        self.assertIsNone(associated_income_isrc({"source": "fuga", "account": "indyana_records", "video_id": CODE, "asset_isrc": OTHER}, index))

    def test_discarded_manual_link_still_blocks_assignment_via_a_secondary_code(self):
        choice = self.prepare()["choices"][0]
        choice["included"] = False
        upc = {**self.row, "kind": "UPC", "code": "111", "isrcs": [ISRC]}
        aliases = {**self.aliases, "UPC:111": "ISRC:" + ISRC}
        index = income_association_index([self.row, upc], aliases, {ISRC: [choice]}, {})
        self.assertIsNone(associated_income_isrc({"source": "fuga", "account": "indyana_records", "video_id": CODE, "product_upc": "111"}, index))

    def test_manual_marker_cannot_be_injected_through_regular_save(self):
        base = {**self.row, "isrcs": [ISRC]}
        item = candidates(ISRC, [base], {"VIDEO:" + CODE: "ISRC:" + ISRC}, [], {})[0]
        with self.assertRaises(ValueError):
            validate_choices([{ "key": self.key, "included": True, "manual": True,
                               "evidence_signature": item["evidence_signature"]}], [], [item])

    def test_regular_decisions_keep_their_original_shape(self):
        result = api.MasterCodeAssociationChoice(key=self.key, included=False, evidence_signature="a" * 64).model_dump(exclude_defaults=True)
        self.assertEqual(set(result), {"key", "included", "evidence_signature"})

    def test_secondary_identifier_cannot_redirect_existing_income(self):
        row = {"source": "fuga", "account": "indyana_records", "video_id": CODE, "product_upc": "111"}
        upc = association_key("UPC", "111", "fuga", "indyana_records")
        old = {"included": {upc: [OTHER]}, "excluded": {}}
        new = {"included": {upc: [OTHER], self.key: [ISRC]}, "excluded": {}}
        with self.assertRaises(ValueError): validate_row_destinations([row], old, new, [self.key], ISRC)

    def test_one_row_with_multiple_identifiers_still_has_one_destination(self):
        row = {"source": "fuga", "account": "indyana_records", "video_id": CODE, "product_upc": "111"}
        index = {"included": {self.key: [ISRC]}, "excluded": {}}
        validate_row_destinations([row], {"included": {}, "excluded": {}}, index, [self.key], ISRC)

    def test_missing_economic_rows_cannot_be_associated(self):
        with self.assertRaises(ValueError): validate_row_destinations([], {}, {}, [self.key], ISRC)


class LinkEndpointTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack(); self.addCleanup(stack.close)
        self.conn = MagicMock()
        self.previous = {"closed": True, "version": 7, "future_reports_selected": True,
            "split": {"principal": "Aneley", "principal_percent": 30, "indyana_percent": 70, "notes": "Manual",
                      "agreements": [], "code_association_overrides": []}}
        self.prepared = {"target": {"version": 7}, "release_id": "release-1", "reference_signature": "a" * 64,
            "choices": [{"key": "code", "included": True, "manual": True, "evidence_signature": "b" * 64}]}
        self.request = api.MasterUnidentifiedLinkRequest(isrc=ISRC, expected_version=7, release_id="release-1", reference_signature="a" * 64)
        self.mocks = {}
        for name, value in {"require_api_key": None, "require_master_contract_user": "editor", "is_wml": False,
                            "is_postgres_connection": True, "prepare_unidentified_link": (self.prepared, self.previous),
                            "save_split": {"version": 8}}.items():
            self.mocks[name] = stack.enter_context(patch.object(api, name, return_value=value))
        connect = stack.enter_context(patch.object(api, "operational_connect"))
        connect.return_value.__enter__.return_value = self.conn

    def run_post(self): return api.post_unidentified_link("a" * 64, self.request, "key", "editor")

    def test_closed_contract_reopens_preserving_percentages_and_history_path(self):
        original = deepcopy(self.previous)
        self.assertEqual(self.run_post()["version"], 8)
        args, options = self.mocks["save_split"].call_args
        self.assertFalse(options["closed"])
        self.assertFalse(options["future_reports_selected"])
        self.assertEqual({k: v for k, v in args[2].items() if k != "code_association_overrides"},
                         {k: v for k, v in original["split"].items() if k != "code_association_overrides"})
        self.assertEqual(self.previous, original)
        self.assertEqual([call.args[2] for call in self.mocks["require_master_contract_user"].call_args_list], ["edit", "approve"])

    def test_stale_version_release_or_signature_cannot_save(self):
        for field, value in (("expected_version", 6), ("release_id", "old"), ("reference_signature", "c" * 64)):
            old = getattr(self.request, field); setattr(self.request, field, value)
            with self.subTest(field=field), self.assertRaises(api.HTTPException) as error: self.run_post()
            self.assertEqual(error.exception.status_code, 409)
            setattr(self.request, field, old)
        self.mocks["save_split"].assert_not_called()

    def test_repeated_association_does_not_create_another_save(self):
        self.mocks["prepare_unidentified_link"].side_effect = api.HTTPException(409, "Ya fue asociada")
        with self.assertRaises(api.HTTPException): self.run_post()
        self.mocks["save_split"].assert_not_called()

    def test_edit_or_approval_denied_cannot_write(self):
        for action in ("edit", "approve"):
            def permit(conn, user, requested):
                if requested == action: raise api.HTTPException(403, "Denied")
                return "editor"
            self.mocks["require_master_contract_user"].side_effect = permit
            with self.subTest(action=action), self.assertRaises(api.HTTPException): self.run_post()
        self.mocks["save_split"].assert_not_called()

    def test_wml_is_not_changed(self):
        self.mocks["is_wml"].return_value = True
        with self.assertRaises(api.HTTPException): self.run_post()
        self.mocks["save_split"].assert_not_called()

    def test_serialization_lock_is_taken_before_preparing_destination(self):
        self.run_post()
        self.assertIn("pg_advisory_xact_lock", self.conn.execute.call_args.args[0])

    def test_unsaved_template_is_loaded_before_taking_the_write_connection(self):
        self.request.expected_version = 0
        self.prepared["target"]["version"] = 0
        self.mocks["prepare_unidentified_link"].return_value = (self.prepared, None)
        with patch.object(api, "get_master_contract", return_value={"split": {"principal_percent": None}}) as detail:
            self.run_post()
            detail.assert_called_once_with(ISRC, "key", "editor")
        self.assertIsNone(self.mocks["save_split"].call_args.args[2]["principal_percent"])

    def test_reference_policy_is_read_with_the_existing_connection(self):
        from lib import distributor_policy_store as store
        document = {"schema_version": 1, "policy_version": 1, "entries": [{"source": "fuga"}]}
        def reading(*args, **kwargs):
            self.assertEqual(store.load_distributor_policy_document(), document)
            raise RuntimeError("checked snapshot before any additional work")
        with patch.object(store, "load_document_in_transaction", return_value=document) as load:
            with patch.object(api, "master_contract_unidentified_income", side_effect=reading):
                with patch.object(api, "read_contract_association_choices", return_value={}):
                    with self.assertRaisesRegex(RuntimeError, "checked snapshot"):
                        REAL_PREPARE(self.conn, "a" * 64, ISRC)
        load.assert_called_once_with(self.conn)


if __name__ == "__main__": unittest.main()
