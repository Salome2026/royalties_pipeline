from __future__ import annotations

import copy
import unittest
from unittest.mock import MagicMock, patch
import polars as pl

from scripts.qa.qa_master_contract_associations import ISRC, OTHER, choice, evidence
from app.master_contract_associations import candidates
from app.master_contract_income import combined_income, consolidate_associated_income, published_unassigned_income, read_choices
from app import vpo_corp_api as api


def sale(**changes):
    return {"source": "soundon", "account": "soundon", "asset_isrc": "",
            "statement_period": "2026-07", "transaction_month": "2026-08",
            "product_upc": "8721466047355", "video_id": "", "track_id": "",
            "amount_usd": 25.0, **changes}


class ContractIncomeTests(unittest.TestCase):
    def calculate(self, rows=None, items=None, aliases=None, choices=None, claims=None):
        return consolidate_associated_income(rows or [sale()], items or [evidence()],
            aliases if aliases is not None else {"UPC:8721466047355": f"ISRC:{ISRC}"},
            choices or {}, claims or {}, "2026-07")

    def test_primary_rows_never_added_a_second_time(self):
        self.assertEqual(self.calculate([sale(asset_isrc=ISRC), sale(asset_isrc=OTHER)]), {})

    def test_one_sale_with_multiple_identifiers_counts_once_and_breaks_down_once(self):
        result = self.calculate([sale(video_id="abcdefghijk")],
            [evidence(), evidence("VIDEO", "abcdefghijk")],
            {"UPC:8721466047355": f"ISRC:{ISRC}", "VIDEO:abcdefghijk": f"ISRC:{ISRC}"})[ISRC]
        self.assertEqual(result["amount_usd"], 25)
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(len(result["groups"][0]["codes"]), 2)
        self.assertEqual(result["groups"][0]["amount_usd"], 25)

    def test_july_statement_not_consumption_and_future_kept_for_default_date_only(self):
        result = self.calculate([sale(), sale(statement_period="2026-08", transaction_month="2026-01", amount_usd=100)])[ISRC]
        self.assertEqual(result["amount_usd"], 25)
        self.assertEqual(sum(item["amount_usd"] for item in result["groups"]), 25)
        self.assertEqual(len(result["statement_income"]), 2)

    def test_negative_adjustments_and_monthly_conservation(self):
        result = self.calculate([sale(), sale(amount_usd=-5)])[ISRC]
        combined = combined_income(100, result, [{"statement_month": "2026-07", "amount_usd": 100}])
        self.assertEqual(combined["amount_usd"], 120)
        self.assertEqual(combined["associated_amount_usd"], 20)
        self.assertEqual(sum(row["amount_usd"] for row in combined["statement_income"]), 120)
        self.assertEqual(sum(row["amount_usd"] for row in combined["associated_income_groups"]), 20)

    def test_shared_upc_not_absorbed(self):
        self.assertEqual(self.calculate(items=[evidence(isrcs=[ISRC, OTHER])]), {})

    def test_manual_pending_not_summed_and_confirmed_exact_signature_summed(self):
        item = candidates(ISRC, [evidence()], {}, [], {})[0]
        self.assertEqual(self.calculate(aliases={}), {})
        result = self.calculate(aliases={}, choices={ISRC: [choice(item)]}, claims={item["key"]: ISRC})
        self.assertEqual(result[ISRC]["amount_usd"], 25)
        self.assertEqual(self.calculate(items=[evidence(isrcs=[])], aliases={},
            choices={ISRC: [choice(item)]}, claims={item["key"]: ISRC}), {})

    def test_exclusion_vetoes_even_another_included_identifier(self):
        items = [evidence(), evidence("VIDEO", "abcdefghijk")]
        aliases = {"UPC:8721466047355": f"ISRC:{ISRC}", "VIDEO:abcdefghijk": f"ISRC:{ISRC}"}
        selected = candidates(ISRC, items, aliases, [], {})
        excluded = next(item for item in selected if item["kind"] == "VIDEO")
        self.assertEqual(self.calculate([sale(video_id="abcdefghijk")], items, aliases,
            {ISRC: [choice(excluded, False)]}), {})

    def test_native_ada_product_not_absorbed_through_a_second_identifier(self):
        self.assertEqual(self.calculate([sale(source="ada", catalog_number="ALBUM")],
            [evidence(source="ada", native_ada_product=True)]), {})

    def test_conflicting_identifiers_not_allocated_to_two_contracts(self):
        aliases = {"UPC:8721466047355": f"ISRC:{ISRC}", "VIDEO:abcdefghijk": f"ISRC:{OTHER}"}
        self.assertEqual(self.calculate([sale(video_id="abcdefghijk")],
            [evidence(), evidence("VIDEO", "abcdefghijk", isrcs=[OTHER])], aliases), {})

    def test_account_namespace_and_no_name_matching(self):
        self.assertEqual(self.calculate([sale(account="other")]), {})
        self.assertEqual(self.calculate([sale(product_upc="", title=ISRC)]), {})

    def test_inputs_not_mutated(self):
        rows, items = [sale()], [evidence()]
        before = copy.deepcopy((rows, items))
        self.calculate(rows, items)
        self.assertEqual((rows, items), before)

    def test_cache_pinned_to_release_and_money_grouped_without_identifier_expansion(self):
        published_unassigned_income.cache_clear()
        client = MagicMock()
        client.query.return_value.result.side_effect = [[{"release_id": "release-a"}], [sale()], [evidence()], [{"release_id": "release-b"}], [], []]
        with patch("app.master_contract_income.dashboard_client", return_value=client):
            published_unassigned_income("release-a")
            published_unassigned_income("release-a")
            self.assertEqual(client.query.call_count, 3)
            published_unassigned_income("release-b")
            self.assertEqual(client.query.call_count, 6)
        first = client.query.call_args_list[1]
        self.assertNotIn("UNNEST", first.args[0])
        self.assertIn("COALESCE(asset_isrc, '') = ''", first.args[0])
        self.assertEqual(first.kwargs["job_config"].query_parameters[0].value, "release-a")
        published_unassigned_income.cache_clear()

    def test_catalog_combined_sort_and_base_preserved(self):
        catalog = pl.DataFrame([{"asset_isrc": ISRC, "track_title": "One", "amount_usd": 999},
                                {"asset_isrc": OTHER, "track_title": "Two", "amount_usd": 998}])
        base = pl.DataFrame([{"asset_isrc": ISRC, "amount_usd": 100., "first_statement_month": "2026-01", "last_statement_month": "2026-07"},
                             {"asset_isrc": OTHER, "amount_usd": 90., "first_statement_month": "2026-01", "last_statement_month": "2026-07"}])
        with patch.object(api, "ensure_marts", return_value={api.CATALOG_MASTER_FILE: "catalog"}), \
             patch.object(api.pl, "read_parquet", return_value=catalog), \
             patch.object(api, "master_contract_income_baseline", return_value=base):
            result = api.master_contract_catalog({OTHER: {"amount_usd": 25, "statement_income": [{"statement_month": "2025-12", "amount_usd": 25}]}})
        self.assertEqual(result["asset_isrc"].to_list(), [OTHER, ISRC])
        self.assertEqual(result["amount_usd"].to_list(), [115., 100.])
        self.assertEqual(result["isrc_amount_usd"].to_list(), [90., 100.])
        self.assertEqual(result["_contract_first_statement_month"].to_list(), ["2025-12", "2026-01"])

    def test_validation_baseline_uses_june_statement_cutoff(self):
        with patch.object(api, "VPO_ROYALTIES_DASHBOARD_BACKEND", "bigquery"), \
             patch.object(api, "load_distributor_policy_document", return_value={}), \
             patch.object(api, "royalty_isrc_income_bigquery", return_value=[]) as query:
            api.master_contract_income_baseline()
        self.assertEqual(query.call_args.kwargs["end_month"], "2026-06")

    def test_june_cutoff_includes_primary_and_associated_income_in_detail_and_panel(self):
        extra = consolidate_associated_income(
            [sale(statement_period="2026-06", transaction_month="2026-08"),
             sale(statement_period="2026-07", transaction_month="2026-01", amount_usd=100)],
            [evidence()], {"UPC:8721466047355": f"ISRC:{ISRC}"}, {}, {}, api.CONTRACT_ANALYSIS_CUTOFF_MONTH)
        self.assertEqual(extra[ISRC]["amount_usd"], 25)
        self.assertEqual(sum(item["amount_usd"] for item in extra[ISRC]["groups"]), 25)
        baseline = pl.DataFrame([{"asset_isrc": ISRC, "amount_usd": 100.}])
        catalog = baseline.with_columns(pl.lit(100.).alias("isrc_amount_usd"),
                                       pl.lit(125.).alias("amount_usd"))
        with patch.object(api, "require_api_key"), patch.object(api, "operational_connect"), \
             patch.object(api, "require_master_contract_user"), \
             patch.object(api, "read_split", return_value=None), \
             patch.object(api, "read_contract_association_choices", return_value={}), \
             patch.object(api, "read_contract_association_claims", return_value={}), \
             patch.object(api, "master_contract_associations", return_value=[]), \
             patch.object(api, "master_contract_associated_income", return_value=extra), \
             patch.object(api, "master_contract_income_baseline", return_value=baseline), \
             patch.object(api, "master_contract_catalog", return_value=catalog), \
             patch.object(api, "active_artist_contracts", return_value={}), \
             patch.object(api, "ensure_marts", return_value={api.STANDARDIZED_FILE: None}), \
             patch.object(api, "artist_suggestions", return_value={"artists": ["Aneley"]}), \
             patch.object(api, "master_contract_statement_income", return_value=[
                 {"statement_month": "2026-06", "amount_usd": 100.},
                 {"statement_month": "2026-07", "amount_usd": 200.}]):
            detail = api.get_master_contract(ISRC, x_vpo_username="tester")
            panel = api.get_master_contract_associations(ISRC, x_vpo_username="tester")["income"]
        for result in (detail, panel):
            self.assertEqual(result["amount_usd"], 125)
            self.assertEqual(result["statement_income"], [{"statement_month": "2026-06", "amount_usd": 125.}])
        self.assertEqual(detail["first_statement_date"], "2026-06-01")
        self.assertFalse(detail["reports_effective"])

    def test_release_mismatch_and_sqlite_rejected_without_reading_economics(self):
        published_unassigned_income.cache_clear()
        client = MagicMock()
        client.query.return_value.result.return_value = [{"release_id": "other-release"}]
        with patch("app.master_contract_income.dashboard_client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "misma versión"):
                published_unassigned_income("catalog-release")
        self.assertEqual(client.query.call_count, 1)
        with patch("app.master_contract_income.is_postgres_connection", return_value=False):
            with self.assertRaisesRegex(ValueError, "exclusivamente Cloud SQL"):
                read_choices(MagicMock())
        published_unassigned_income.cache_clear()

    def test_existing_generation_filters_discount_and_live_policy_changes(self):
        rows = [sale(statement_period="2026-06", source_sheet="recording", revenue_basis="generation"),
                sale(source_sheet="recording", revenue_basis="generation", amount_usd=100),
                sale(source_sheet="share", revenue_basis="transfer", amount_usd=1000)]
        aliases = pl.DataFrame({"alias_catalog_key": ["UPC:8721466047355"], "catalog_key": [f"ISRC:{ISRC}"]})
        policy = {"policy_version": 1, "report_personalization": {"enabled": True}, "entries": [{
            "source": "soundon", "account": "soundon", "report_net_adjustment_pct": 10,
            "sheet_rules": {"recording": {"catalog_view": True, "statement_view": True, "revenue_basis": "generation"},
                            "share": {"catalog_view": False, "statement_view": False, "revenue_basis": "transfer"}},
        }]}
        module = api.filter_reportable_generation.__module__
        with patch.object(api, "ensure_marts", return_value={api.CATALOG_MASTER_FILE: "catalog"}), \
             patch.object(api, "load_catalog_status"), patch.object(api, "configure_catalog_report_env"), \
             patch.object(api, "mart_release_cache") as cache, \
             patch.object(api, "published_unassigned_income", return_value=(rows, [evidence()])), \
             patch.object(api, "catalog_alias_lookup", return_value=aliases), \
             patch(f"{module}.catalog_alias_lookup", return_value=pl.DataFrame()), \
             patch(f"{module}.catalog_status_for_reports", return_value=pl.DataFrame()), \
             patch(f"{module}.load_distributor_policy_document", return_value=policy):
            cache.return_value.status.return_value = {"active_release_id": "published"}
            result = api.master_contract_associated_income({})
            self.assertEqual(result[ISRC]["amount_usd"], 22.5)
            policy["entries"][0]["report_net_adjustment_pct"] = 20
            self.assertEqual(api.master_contract_associated_income({})[ISRC]["amount_usd"], 20)


if __name__ == "__main__":
    unittest.main()
