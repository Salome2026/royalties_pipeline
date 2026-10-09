from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import polars as pl

# Initialize the existing test policy context before the API adds scripts/ to sys.path.
from scripts.lib.catalog_report_filter import apply_report_net_personalization  # noqa: F401
from app.master_contract_associations import candidates, identity_evidence, preserve_choices, validate_choices
from app import vpo_corp_api as api
from app import master_contracts

ISRC = "ARDL12600006"
OTHER = "BK4DA2659368"


def evidence(kind="UPC", code="8721466047355", **kwargs):
    return {"kind": kind, "code": code, "source": "soundon", "account": "soundon",
            "isrcs": [ISRC], "titles": ["Tema"], "artists": ["Artista"], "native_ada_product": False, **kwargs}


def choice(item, included=True):
    return {key: item[key] for key in ("key", "evidence_signature")} | {"included": included}


class ContractAssociationTests(unittest.TestCase):
    def items(self, rows=None, overrides=None, aliases=None, claims=None):
        return candidates(ISRC, rows or [evidence()],
                          aliases if aliases is not None else {"UPC:8721466047355": f"ISRC:{ISRC}"},
                          overrides or [], claims or {})

    def test_exact_unique_upc_automatic_without_mutating_evidence(self):
        row = evidence()
        item = self.items([row])[0]
        self.assertTrue(item["automatic"])
        self.assertTrue(item["included"])
        self.assertEqual(item["status"], "automatic")
        self.assertNotIn("included", row)

    def test_video_unique_and_platform_id_scoped(self):
        rows = [evidence("VIDEO", "abcdefghijk"), evidence("TRACK", "123"),
                evidence("TRACK", "123", account="other", isrcs=[OTHER])]
        items = self.items(rows, aliases={"VIDEO:abcdefghijk": f"ISRC:{ISRC}"})
        included = [item for item in items if item["included"]]
        self.assertEqual(len(included), 2)
        self.assertEqual([item["status"] for item in items if item["account"] == "other"], ["blocked"])

    def test_shared_upc_blocked_even_if_catalog_alias_points_to_target(self):
        rows = [evidence(), evidence(source="fuga", account="indyana_records", isrcs=[OTHER])]
        items = self.items(rows)
        self.assertTrue(all(not item["included"] and not item["selectable"] for item in items))
        self.assertTrue(all(item["isrcs"] == sorted([ISRC, OTHER]) for item in items))

    def test_catalog_without_unique_alias_requires_manual_confirmation(self):
        item = self.items(aliases={})[0]
        self.assertFalse(item["automatic"])
        self.assertEqual(item["status"], "pending")
        self.assertTrue(item["selectable"])
        selected = choice(item)
        validate_choices([selected], [], [item])
        confirmed = self.items(aliases={}, overrides=[selected])[0]
        self.assertEqual(confirmed["status"], "confirmed")

    def test_ada_native_product_never_allocated_to_track(self):
        item = self.items([evidence(source="ada", account="mawzrecords", isrcs=[], native_ada_product=True)])[0]
        self.assertEqual(item["status"], "blocked")
        self.assertIn("identidad e ingreso propios", item["reason"])
        with self.assertRaises(ValueError):
            validate_choices([choice(item)], [], [item])

    def test_separate_catalog_asset_not_merged(self):
        item = self.items(aliases={"UPC:8721466047355": "UPC:8721466047355"})[0]
        self.assertFalse(item["selectable"])

    def test_exclusion_persists_and_new_month_labels_do_not_invalidate_identity(self):
        item = self.items()[0]
        excluded = self.items([evidence(titles=["Other title"])], [choice(item, False)])[0]
        self.assertFalse(excluded["included"])
        self.assertEqual(excluded["status"], "excluded")
        self.assertEqual(item["evidence_signature"], excluded["evidence_signature"])

    def test_changed_evidence_suspends_old_confirmation(self):
        item = self.items(aliases={})[0]
        changed = self.items(aliases={}, overrides=[choice(item)], rows=[evidence(isrcs=[])])[0]
        self.assertFalse(changed["included"])
        self.assertEqual(changed["status"], "pending")
        with self.assertRaisesRegex(ValueError, "evidencia cambió"):
            validate_choices([choice(item)], [], [changed])

    def test_claimed_code_cannot_be_included_by_other_contract(self):
        item = self.items()[0]
        blocked = self.items(claims={item["key"]: OTHER})[0]
        self.assertFalse(blocked["selectable"])
        with self.assertRaisesRegex(ValueError, OTHER):
            validate_choices([choice(blocked)], [], [blocked])

    def test_forged_duplicate_choices_rejected(self):
        item = self.items()[0]
        with self.assertRaisesRegex(ValueError, "repetidos"):
            validate_choices([choice(item), choice(item)], [], [item])
        with self.assertRaisesRegex(ValueError, "no está disponible"):
            validate_choices([{**choice(item), "key": "fake"}], [], [item])

    def test_legacy_client_preserves_choices_and_explicit_empty_clears(self):
        choices = [choice(self.items()[0], False)]
        old = {"split": {"code_association_overrides": choices}}
        self.assertEqual(preserve_choices({"code_association_overrides": None}, old)["code_association_overrides"], choices)
        self.assertEqual(preserve_choices({"code_association_overrides": []}, old)["code_association_overrides"], [])
        self.assertNotIn("code_association_overrides", preserve_choices({"code_association_overrides": None}, None))

    def test_api_schema_roundtrip_keeps_choices(self):
        choices = [choice(self.items()[0], False)]
        request = api.MasterContractSaveRequest(split={"code_association_overrides": choices})
        self.assertEqual(request.split.model_dump()["code_association_overrides"], choices)

    def test_parameterized_query_inspects_all_statements_without_financial_changes(self):
        client = MagicMock()
        client.query.return_value.result.side_effect = [[{"release_id": "published"}], [evidence()]]
        rows = identity_evidence(ISRC, {"upcs": "8721466047355", "video_ids": "abcdefghijk"}, client=client)
        self.assertEqual(rows[0]["code"], "8721466047355")
        sql = client.query.call_args.args[0]
        self.assertNotIn(ISRC, sql)
        self.assertNotIn("amount_usd", sql)
        self.assertNotIn("statement_month", sql)
        self.assertIn("JOIN seeds", sql)
        config = client.query.call_args.kwargs["job_config"]
        self.assertEqual(config.maximum_bytes_billed, 5_000_000_000)
        self.assertEqual(config.query_parameters[0].value, "published")
        self.assertEqual(config.query_parameters[1].value, ISRC)
        self.assertIn("WHERE release_id = @release_id", sql)

    def test_get_associations_enforces_existing_permission_and_is_read_only(self):
        conn = MagicMock()
        with patch.object(api, "require_api_key"), patch.object(api, "operational_connect") as connect, \
             patch.object(api, "require_master_contract_user") as auth, patch.object(api, "read_split", return_value=None), \
             patch.object(api, "read_contract_association_claims", return_value={}), \
             patch.object(api, "read_contract_association_choices", return_value={}), \
             patch.object(api, "master_contract_associated_income", return_value={}), \
             patch.object(api, "master_contract_income_baseline", return_value=pl.DataFrame({"asset_isrc": [ISRC], "amount_usd": [100.0]})), \
             patch.object(api, "master_contract_statement_income", return_value=[]), \
             patch.object(api, "master_contract_associations", return_value=self.items()):
            connect.return_value.__enter__.return_value = conn
            result = api.get_master_contract_associations(ISRC, "key", "reader")
            auth.assert_called_once_with(conn, "reader", "access")
            conn.execute.assert_not_called()
            self.assertFalse(result["reports_effective"])

    def test_choice_saved_in_same_postgres_payload_and_history(self):
        conn = MagicMock()
        conn.execute.return_value.rowcount = 1
        choices = [choice(self.items()[0], False)]
        split = {"principal": "Artist", "code_association_overrides": choices}
        with patch.object(master_contracts, "is_postgres_connection", return_value=True), \
             patch.object(master_contracts, "ensure_sqlite_tables"), \
             patch.object(master_contracts, "db_sql", side_effect=lambda _, sql: sql):
            result = master_contracts.save_split(conn, ISRC, split, closed=False,
                                                future_reports_selected=False, expected_version=1, actor="tester")
        self.assertEqual(result["split"]["code_association_overrides"], choices)
        self.assertEqual(result["version"], 2)
        self.assertEqual(len(conn.execute.call_args_list), 2)
        update, history = conn.execute.call_args_list
        self.assertIn("master_contract_split_history", history.args[0])
        self.assertEqual(update.args[1][0], history.args[1][2])

    def test_new_metadata_has_no_sqlite_write_path(self):
        with patch.object(master_contracts, "is_postgres_connection", return_value=False):
            with self.assertRaisesRegex(ValueError, "exclusivamente Cloud SQL"):
                master_contracts.save_split(MagicMock(), ISRC, {"code_association_overrides": [choice(self.items()[0])]},
                                            closed=False, future_reports_selected=False, expected_version=0, actor="tester")

    def test_put_preserves_older_client_choices_without_identity_query(self):
        conn = MagicMock()
        saved = {"split": {"code_association_overrides": [choice(self.items()[0], False)]}, "version": 2, "closed": False, "future_reports_selected": False}
        request = api.MasterContractSaveRequest(split={"principal": "Artista"}, expected_version=2)
        with patch.object(api, "require_api_key"), patch.object(api, "operational_connect") as connect, \
             patch.object(api, "require_master_contract_user", return_value="editor"), \
             patch.object(api, "master_contract_catalog") as catalog, patch.object(api, "read_split", return_value=saved), \
             patch.object(api, "save_split", return_value={}) as save, patch.object(api, "master_contract_associations") as verify:
            connect.return_value.__enter__.return_value = conn
            catalog.return_value.filter.return_value.is_empty.return_value = False
            api.put_master_contract(ISRC, request, "key", "editor")
            self.assertEqual(save.call_args.args[2]["code_association_overrides"], saved["split"]["code_association_overrides"])
            verify.assert_not_called()

    def test_put_rechecks_new_choices_under_global_lock_and_approval(self):
        conn = MagicMock()
        item = self.items()[0]
        request = api.MasterContractSaveRequest(split={"code_association_overrides": [choice(item)]}, expected_version=1, closed=True)
        with patch.object(api, "require_api_key"), patch.object(api, "operational_connect") as connect, \
             patch.object(api, "require_master_contract_user", return_value="editor") as auth, \
             patch.object(api, "master_contract_catalog") as catalog, \
             patch.object(api, "read_split", return_value={"split": {}, "version": 1, "closed": True}), \
             patch.object(api, "is_postgres_connection", return_value=True), patch.object(api, "db_sql", side_effect=lambda _, sql: sql), \
             patch.object(api, "read_contract_association_claims", return_value={}), \
             patch.object(api, "master_contract_associations", return_value=[item]) as verify, patch.object(api, "save_split", return_value={}):
            connect.return_value.__enter__.return_value = conn
            catalog.return_value.filter.return_value.is_empty.return_value = False
            api.put_master_contract(ISRC, request, "key", "editor")
            self.assertEqual(auth.call_args_list[1].args[2], "approve")
            self.assertIn("pg_advisory_xact_lock", conn.execute.call_args.args[0])
            verify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
