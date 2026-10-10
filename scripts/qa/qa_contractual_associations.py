from __future__ import annotations

import copy
import json
from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import polars as pl

from app.master_contract_associations import association_key
from app.royalty_reports.contract_query import (
    association_query_parameter, query_contract_income, select_associated_rankings, ranking_association_key,
)
from app.royalty_reports.contract_snapshot import freeze_contract_associations
from app.royalty_reports.contractual import analyze_contractual_income
from scripts.qa.qa_contractual_executive import fixture, income

ISRC, OTHER, VIDEO = "ARDL12600001", "ARDL12600002", "abcdefghijk"
KEY = association_key("VIDEO", VIDEO, "fuga", "indyana_records")
SCOPE = json.dumps([VIDEO, "fuga", "indyana_records"], separators=(",", ":"))
OWNER = json.dumps(["fuga", "indyana_records", "recording", "2026-07", "ID", VIDEO], separators=(",", ":"))


def snapshot():
    state = fixture()[0]
    state.update(schema_version=2, associations={"release_id": "release-a", "ranking_layout": "artist-title-isrc-upc-id-v1",
                 "included": {KEY: [ISRC]}, "excluded": {}, "search_codes": {SCOPE: ["VIDEO", VIDEO]},
                 "ranking_owners": {OWNER: {"isrc": ISRC, "amount_usd": 50., "raw_rows": 1}}})
    return state


def row(**changes):
    sale = {"isrc": None, "upc": None, "title": "Tema (Video Oficial)", "artist": "Canal", "source": "fuga",
            "account": "indyana_records", "source_sheet": "recording", "statement_month": "2026-07",
            "amount_usd": 45., "gross_amount_usd": 50., "units": 2., "raw_rows": 1, **changes}
    text = " ".join(str(sale.get(key) or "") for key in ("artist", "title", "isrc", "upc")) + " " + VIDEO + " spotify extra credits"
    sale.setdefault("search_text", text.lower())
    sale.setdefault("normalized_search", sale["search_text"])
    return sale


def request(**changes):
    return SimpleNamespace(**{"keywords": [], "source": None, "account": None, "start_month": None, "end_month": None, **changes})


class ContractualAssociationTests(unittest.TestCase):
    def test_association_without_channel_artist_and_once_only_conservation(self):
        state = snapshot()
        rows = select_associated_rankings([row()], request(), state)
        result = analyze_contractual_income(state, [income(), *rows])
        self.assertEqual((result["total"], result["covered"], result["pending"]), (145, 145, 0))
        self.assertEqual(sum(r["amount"] for r in result["recipients"]), 145)

    def test_empty_index_preserves_search_units_negative_and_pending(self):
        state = snapshot()
        state["associations"]["ranking_owners"] = {}
        rows = [row(artist="Proyecto", amount_usd=-5, gross_amount_usd=-5, units=2.5),
                row(artist="Otro", normalized_search="alternate proyecto credits", amount_usd=10, gross_amount_usd=10)]
        for keywords in [[], ["alternate"], ["spotify"], ["inexistente"]]:
            req = request(keywords=keywords)
            got = select_associated_rankings(rows, req, state)
            expected = [r for r in rows if "proyecto" in r["normalized_search"] and (
                not keywords or any(k in r["normalized_search"] for k in keywords))]
            self.assertEqual(got, expected)
        result = analyze_contractual_income(state, select_associated_rankings(rows, request(), state))
        self.assertEqual((result["total"], result["pending"], result["units"]), (5, 5, 4.5))

    def test_prefix_empty_slot_mismatch_unknown_and_collision_never_guess_from_title(self):
        state = snapshot()
        self.assertEqual(ranking_association_key(row(title=f"{VIDEO} Tema"), state), OWNER)
        empty = row(search_text="canal tema (video oficial)    spotify abcdefghijk")
        self.assertIsNone(ranking_association_key(empty, state))
        changed = row(search_text="not the serialized layout abcdefghijk")
        self.assertIsNone(ranking_association_key(changed, state))
        state["associations"]["search_codes"][SCOPE] = None
        self.assertIsNone(ranking_association_key(row(), state))
        state["associations"]["search_codes"] = {}
        self.assertIsNone(ranking_association_key(row(), state))

    def test_canonical_filter_scope_and_mismatch_stays_pending_without_blocking_report(self):
        state = snapshot()
        for keyword in [ISRC.lower(), "tema", "spotify"]:
            self.assertEqual(len(select_associated_rankings([row()], request(keywords=[keyword]), state)), 1)
        self.assertEqual(select_associated_rankings([row()], request(keywords=["otro"]), state), [])
        self.assertEqual(select_associated_rankings([row(gross_amount_usd=51)], request(), state), [])
        self.assertEqual(select_associated_rankings([row(raw_rows=2)], request(), state), [])
        for changes in [{"gross_amount_usd": 51}, {"raw_rows": 2}]:
            rows = select_associated_rankings([row(artist="Proyecto", **changes)], request(), state)
            self.assertEqual(analyze_contractual_income(state, rows)["pending"], 45)

    def test_month_validity_discard_and_namespace_do_not_reallocate(self):
        state = snapshot()
        state["contracts"][0]["split"]["agreements"][0]["effective_until"] = "2026-06-30"
        rows = select_associated_rankings([row()], request(), state)
        self.assertEqual(analyze_contractual_income(state, rows)["pending"], 45)
        state["associations"]["ranking_owners"] = {}
        self.assertIsNone(select_associated_rankings([row(artist="Proyecto")], request(), state)[0]["isrc"])
        self.assertIsNone(select_associated_rankings([row(artist="Proyecto", account="other")], request(), snapshot())[0]["isrc"])

    def test_full_bundle_veto_conflict_native_product_and_unsafe_tokens(self):
        state, _, _, saved = fixture()
        frame = pl.DataFrame([{"asset_isrc": ISRC, "catalog_key": f"ISRC:{ISRC}", "track_title": "Tema",
                               "artist_statement": "Proyecto and Artista", "video_ids": VIDEO},
                              {"asset_isrc": OTHER, "catalog_key": f"ISRC:{OTHER}", "track_title": "Otro",
                               "artist_statement": "Otro", "video_ids": "abcdefghijz"}])
        evidence = [{"kind": "VIDEO", "code": VIDEO, "source": "fuga", "account": "indyana_records",
                     "isrcs": [ISRC], "titles": ["Tema"], "artists": ["Proyecto and Artista"]},
                    {"kind": "TRACK", "code": "TRACK", "source": "fuga", "account": "indyana_records",
                     "isrcs": [OTHER], "titles": ["Otro"], "artists": ["Otro"]}]
        sale = {"asset_isrc": None, "source": "fuga", "account": "indyana_records", "source_sheet": "recording",
                "statement_period": "2026-07", "video_id": VIDEO, "track_id": None, "product_upc": None,
                "amount_usd": 50, "raw_rows": 1}
        original = copy.deepcopy(state)
        def freeze(rows, items=evidence, unsafe=frozenset()):
            manifest = {"schema_version": 1, "release_id": "release-a", "bucket": "bucket", "objects": {
                "standardized_raw_all_sources.parquet": {"object": "release/raw.parquet", "generation": 1}}}
            with patch("app.master_contract_income.published_unassigned_income", return_value=(rows, items)), \
                 patch("app.royalty_reports.contract_identity.unsafe_ranking_slot_keys", return_value=unsafe):
                return freeze_contract_associations(state, frame, saved, "release-a", input_manifest=manifest)
        frozen = freeze([sale])
        self.assertEqual(frozen["associations"]["ranking_owners"][OWNER]["isrc"], ISRC)
        self.assertEqual(freeze([sale], unsafe=frozenset({OWNER}))["associations"]["ranking_owners"], {})
        self.assertEqual(freeze([{**sale, "source": None}])["associations"]["ranking_owners"], {})
        self.assertEqual(freeze([{**sale, "track_id": "TRACK"}])["associations"]["ranking_owners"], {})
        self.assertEqual(freeze([{**sale, "source": "ada", "catalog_number": "ALBUM"}])["associations"]["ranking_owners"], {})
        saved[0]["split"]["code_association_overrides"] = [{"key": KEY, "included": False}]
        self.assertEqual(freeze([sale])["associations"]["ranking_owners"], {})
        saved[0]["split"].pop("code_association_overrides")
        unsafe = {**evidence[0], "kind": "TRACK", "code": VIDEO + " extra"}
        self.assertIsNone(freeze([sale], [*evidence, unsafe])["associations"]["search_codes"][SCOPE])
        self.assertEqual(state, original)

    def test_binding_payload_is_limited_to_requested_scope(self):
        state = snapshot()
        self.assertEqual(len(association_query_parameter(state, request()).to_api_repr()["parameterValue"]["arrayValues"]), 1)
        for changes in [{"source": "onerpm"}, {"account": "other"}, {"end_month": "2026-06"}, {"start_month": "2026-08"}]:
            self.assertEqual(association_query_parameter(state, request(**changes)).to_api_repr()["parameterValue"]["arrayValues"], [])

    def test_query_keeps_ranking_measures_and_binds_source_account_sheet_month(self):
        client, state = MagicMock(), snapshot()
        client.query.return_value.result.return_value = [row()]
        req = request(start_month="2026-07", end_month="2026-08", source="fuga", account="indyana_records")
        with patch("app.royalty_reports.contract_query.bigquery.Client", return_value=client):
            result = query_contract_income(req, {"release_id": "release-a", "contract_snapshot": state}, {})
        self.assertEqual(result[0]["isrc"], ISRC)
        self.assertEqual(client.query.call_count, 1)
        sql = client.query.call_args.args[0]
        self.assertIn("royalty_dashboard_rankings", sql)
        self.assertNotIn("royalty_statement_fact", sql)
        self.assertIn("code.source = ranking.source", sql)
        self.assertIn("code.account = ranking.account", sql)
        self.assertIn("code.sheet = COALESCE(ranking.source_sheet, '')", sql)
        self.assertIn("code.month = FORMAT_DATE", sql)
        self.assertIn("SUM(COALESCE(units, 0))", sql)
        config = client.query.call_args.kwargs["job_config"]
        params = {p.name: p.value for p in config.query_parameters if hasattr(p, "value")}
        self.assertEqual((params["start_month"], params["end_month"]), (date(2026, 7, 1), date(2026, 8, 1)))
        self.assertEqual(config.maximum_bytes_billed, 5_000_000_000)
        state["schema_version"] = 1
        client.reset_mock()
        client.query.return_value.result.return_value = [income(), income(5, isrc=None)]
        with patch("app.royalty_reports.contract_query.bigquery.Client", return_value=client):
            result = query_contract_income(req, {"release_id": "release-a", "contract_snapshot": state}, {})
        self.assertEqual(analyze_contractual_income(state, result)["pending"], 5)
        self.assertNotIn("serialized_code", client.query.call_args.args[0])

    def test_missing_mismatched_snapshot_and_layout_are_rejected(self):
        for field, value in [("ranking_owners", None), ("release_id", "other"), ("ranking_layout", "unknown")]:
            state = snapshot()
            state["associations"][field] = value
            with self.assertRaisesRegex(ValueError, "validacion de asociados"):
                query_contract_income(request(), {"release_id": "release-a", "contract_snapshot": state}, {})


if __name__ == "__main__":
    unittest.main()
