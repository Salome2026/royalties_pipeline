import copy
import unittest

from app.master_contract_unidentified import unidentified_income
from app.master_contract_associations import association_key, candidates

A, B = "XXAAA2500001", "XXAAA2500002"
VIDEO = "abcdefghijk"
CATALOG = [{"asset_isrc": A, "track_title": "Tema A", "artist_statement": "Artista"},
           {"asset_isrc": B, "track_title": "Tema B", "artist_statement": "Otro"}]


def row(**patch):
    return {"source": "fuga", "account": "indy", "source_sheet": "standard_statement_csv",
        "asset_isrc": None, "video_id": VIDEO, "product_upc": None, "track_id": None,
        "catalog_number": None, "title": "Canción sin identificar", "artist": "José",
        "amount_usd": 10., "statement_period": "2026-10", "raw_rows": 2, **patch}


def evidence(**patch):
    return {"kind": "VIDEO", "code": VIDEO, "source": "fuga", "account": "indy",
        "isrcs": [], "titles": ["Video"], "artists": ["Artista"], "native_ada_product": False,
        "inferred_isrcs": [A], "inference_reason": "Propuesta", "inference_signature": "current",
        "inference_rule": "test", **patch}


def listing(rows=None, ev=None, choices=None, aliases=None, **filters):
    return unidentified_income(rows if rows is not None else [row()], ev if ev is not None else [evidence()],
        CATALOG, aliases or {}, choices or {}, **filters)


def choice(included=True, signature=None):
    item = candidates(A, [evidence()], {}, [], {})[0]
    return {"key": item["key"], "included": included,
            "evidence_signature": signature if signature is not None else item["evidence_signature"]}


class UnidentifiedTests(unittest.TestCase):
    def test_proposal_alone_keeps_money_visible(self):
        result = listing()
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["unidentified_items"][0]["candidates"][0]["isrc"], A)

    def test_no_candidate_is_still_visible(self):
        result = listing(ev=[])
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["unidentified_summary"]["without_candidates"], 1)

    def test_valid_inclusion_removes_only_assigned_income(self):
        self.assertEqual(listing(choices={A: [choice()]})["total"], 0)

    def test_exclusion_does_not_hide_income(self):
        result = listing(choices={A: [choice(False)]})
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["unidentified_items"][0]["candidates"][0]["statuses"], ["excluded"])

    def test_stale_inclusion_returns_to_list(self):
        self.assertEqual(listing(choices={A: [choice(signature="old")]})["total"], 1)

    def test_automatic_exact_mapping_removes_income(self):
        self.assertEqual(listing(aliases={"VIDEO:" + VIDEO: "ISRC:" + A})["total"], 0)

    def test_discard_a_but_valid_inclusion_b_is_identified(self):
        ev = evidence(inferred_isrcs=[A, B])
        key = association_key("VIDEO", VIDEO, "fuga", "indy")
        exclusion = {"key": key, "included": False, "evidence_signature": "unused"}
        item = candidates(B, [ev], {}, [], {})[0]
        inclusion = {"key": key, "included": True, "evidence_signature": item["evidence_signature"]}
        self.assertEqual(listing(ev=[ev], choices={A: [exclusion], B: [inclusion]})["total"], 0)

    def test_multiple_candidates_never_multiply_money(self):
        result = listing(ev=[evidence(inferred_isrcs=[A, B])])
        self.assertEqual(result["unidentified_summary"]["amount_usd"], 10.)
        self.assertEqual(len(result["unidentified_items"][0]["candidates"]), 2)

    def test_multiple_codes_never_multiply_money(self):
        self.assertEqual(listing(rows=[row(product_upc="123456789012", track_id="native")])["unidentified_summary"]["amount_usd"], 10.)

    def test_months_accounts_and_sources_group_same_video_once(self):
        rows = [row(), row(statement_period="2026-09", amount_usd=3), row(source="onerpm", account="gusty", amount_usd=2)]
        result = listing(rows=rows)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["unidentified_summary"]["amount_usd"], 15.)

    def test_new_unconfirmed_account_remains_after_partial_inclusion(self):
        result = listing(rows=[row(), row(source="onerpm", account="gusty", amount_usd=2)],
            ev=[evidence(), evidence(source="onerpm", account="gusty")], choices={A: [choice()]})
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["unidentified_items"][0]["amount_usd"], 2.)

    def test_track_ids_stay_scoped(self):
        rows = [row(video_id=None, track_id="123"), row(video_id=None, track_id="123", account="other")]
        self.assertEqual(listing(rows=rows, ev=[])["total"], 2)

    def test_source_filter_does_not_change_assignment(self):
        self.assertEqual(listing(choices={A: [choice()]}, source="fuga")["total"], 0)
        self.assertEqual(listing(source="onerpm")["total"], 0)

    def test_search_and_pagination_summary_is_global_to_filter(self):
        rows = [row(video_id="12345678901"), row(video_id="12345678902")]
        result = listing(rows=rows, ev=[], keyword="jose", limit=1, offset=1)
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["unidentified_items"]), 1)
        self.assertEqual(result["unidentified_summary"]["amount_usd"], 20.)
        self.assertEqual(listing(rows=rows, ev=[], limit=1, offset=99)["offset"], 1)

    def test_catalog_visibility_includes_reference_accounts_but_not_transfers(self):
        from unittest.mock import patch
        import polars as pl
        from app import vpo_corp_api as api
        from lib.distributor_policy_store import use_distributor_policy_snapshot
        policy = {"schema_version": 1, "policy_version": 1, "entries": [{
            "source": "fuga", "account": "indy", "sheet_rules": {
                "standard_statement_csv": {"catalog_view": True, "statement_view": False, "revenue_basis": "generation"},
                "transfers": {"catalog_view": False, "statement_view": False, "revenue_basis": "transfer"}}}]}
        class Cache:
            def status(self): return {"active_release_id": "test"}
        rows = [row(), row(source_sheet="transfers", amount_usd=100)]
        with use_distributor_policy_snapshot(policy), \
             patch.object(api, "ensure_marts", return_value={"catalog_master.parquet": "unused"}), \
             patch.object(api, "mart_release_cache", return_value=Cache()), \
             patch.object(api, "contract_metadata_catalog", side_effect=lambda rows: rows), \
             patch.object(api, "published_unassigned_income", return_value=(rows, [])), \
             patch.object(api.pl, "read_parquet", return_value=pl.DataFrame(CATALOG)), \
             patch.object(api, "catalog_alias_lookup", return_value=pl.DataFrame({"alias_catalog_key": [], "catalog_key": []})):
            result = api.master_contract_unidentified_income({})
            self.assertEqual(result["unidentified_summary"]["amount_usd"], 10.)

    def test_negative_adjustment_and_net_zero_movements_are_visible(self):
        self.assertEqual(listing(rows=[row(amount_usd=-5)])["unidentified_summary"]["amount_usd"], -5)
        self.assertEqual(listing(rows=[row(), row(amount_usd=-10)])["total"], 1)
        self.assertEqual(listing(rows=[row(amount_usd=0)])["total"], 0)

    def test_embedded_video_id_is_link_only_and_text_keeps_scope(self):
        result = listing(rows=[row(video_id=None, title="Auto generated asset - " + VIDEO)],
            aliases={"VIDEO:" + VIDEO: "ISRC:" + A})
        self.assertEqual(result["total"], 1)
        self.assertTrue(result["unidentified_items"][0]["video_url"].endswith(VIDEO))

    def test_existing_isrc_income_and_assigned_ugc_not_reintroduced(self):
        self.assertEqual(listing(rows=[row(asset_isrc=A)])["total"], 0)

    def test_read_only_inputs_are_untouched(self):
        rows, ev, choices = [row()], [evidence()], {A: [choice(False)]}
        before = copy.deepcopy((rows, ev, choices))
        listing(rows=rows, ev=ev, choices=choices)
        self.assertEqual((rows, ev, choices), before)

    def test_api_permission_and_wml_scope_guard(self):
        from unittest.mock import patch, MagicMock
        from fastapi import HTTPException
        from app import vpo_corp_api as api
        with patch.object(api, "require_api_key"), patch.object(api, "operational_connect") as conn, \
             patch.object(api, "read_split_statuses", return_value={}), \
             patch.object(api, "read_contract_association_choices", return_value={}), \
             patch.object(api, "read_association_review_states", return_value={}), \
             patch.object(api, "master_contract_unidentified_income", return_value={"total": 7}) as load, \
             patch.object(api, "require_master_contract_user") as permission, patch.object(api, "is_wml", return_value=False):
            result = api.list_master_contracts(status="unidentified", x_vpo_username="reader")
            self.assertEqual(result, {"total": 7})
            permission.assert_called_once_with(conn.return_value.__enter__.return_value, "reader", "access")
            with patch.object(api, "is_wml", return_value=True):
                with self.assertRaises(HTTPException):
                    api.list_master_contracts(status="unidentified")
            permission.side_effect = HTTPException(403, "Forbidden")
            with self.assertRaises(HTTPException):
                api.list_master_contracts(status="unidentified")
            self.assertEqual(load.call_count, 1)


if __name__ == "__main__":
    unittest.main()
