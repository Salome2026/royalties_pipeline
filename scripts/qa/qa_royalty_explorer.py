"""Read-only explorer checks; no credentials, network or database required."""
from copy import deepcopy
import json
import unittest
from unittest.mock import MagicMock, patch

from google.api_core.exceptions import NotFound, InternalServerError, Forbidden
from google.cloud import bigquery

from app import royalty_explorer as ex
from app.royalty_reports import contract_identity as guard
from scripts.qa.qa_contractual_executive import fixture


def context():
    snapshot, _, _, saved = fixture()
    saved[0]["future_reports_selected"] = True
    snapshot["contracts"] = saved
    return {"snapshot": snapshot, "catalog": [{"asset_isrc": "ARDL12600001", "artist": "Proyecto and Artista"}],
            "names": {"indyana": "Indyana", "socio": "Socio", "artista": "Artista", "proyecto": "Proyecto"},
            "bindings": [], "table": "`project.dataset.rankings`", "release": "release-a", "revision": "v1"}


def income(amount=100, **changes):
    return {"identity_key": "ISRC:ARDL12600001", "isrc": "ARDL12600001", "title": "Tema",
            "statement_month": "2026-07", "transaction_month": "2026-05", "source": "fuga", "account": "indyana",
            "dsp": "YouTube", "territory": "AR", "monetization": "Content ID", "content_origin": "UGC",
            "contract_percent": 6, "contract_version": 1, "pending_reason": "", "amount_usd": amount,
            "units": 123, "rows": 2, **changes}


def project_context():
    ctx = context()
    ctx["snapshot"]["contracts"][0]["split"]["agreements"][0]["allocation"]["principal"] = "La Juntada de los Artistas"
    return ctx


class ExplorerTests(unittest.TestCase):
    def test_project_distribution_excludes_other_projects_of_the_same_participant(self):
        ctx = project_context()
        foreign = deepcopy(ctx["snapshot"]["contracts"][0])
        foreign["isrc"] = "ARDL12600002"
        foreign["split"]["agreements"][0]["allocation"]["principal"] = "Otro proyecto"
        ctx["snapshot"]["contracts"].append(foreign)
        ctx["snapshot"]["catalog"].append({"isrc": foreign["isrc"], "title": "Tema ajeno", "artists_informed": "Artista"})
        self.assertEqual(ex.juntada_roots(ctx), {"ARDL12600001"})
        original = deepcopy(ctx)
        with patch.object(ex, "get_context", return_value=ctx), patch.object(ex, "_job", return_value=[]) as query:
            result = ex.distribution([], {}, {"Artista"}, keyword="Artista")
            params = query.call_args.args[1]
            self.assertEqual(next(p for p in params if p.name == "roots").values, ["ARDL12600001"])
            self.assertFalse(next(p.value for p in params if p.name == "all_tracks"))
            self.assertEqual(result["amount_usd"], 0)
        self.assertEqual(ctx, original)
        with patch.object(ex, "get_context", return_value=ctx), patch.object(ex, "_job", return_value=[]) as query:
            ex.distribution([], {}, None)
            params = query.call_args.args[1]
            self.assertFalse(next(p.value for p in params if p.name == "all_tracks"))
            self.assertEqual(next(p for p in params if p.name == "roots").values, ["ARDL12600001"])
        # The participant's ordinary scope still contains both tracks.
        self.assertEqual(len(ex.compiled_rules(ctx, "Artista")[0]), 2)

    def test_project_track_shows_all_shares_but_other_projects_keep_private_projection(self):
        for ctx, full in [(project_context(), True), (context(), False)]:
            with patch.object(ex, "get_context", return_value=ctx), patch.object(ex, "_job", return_value=[income()]):
                track = ex.detail([], {}, {"Artista"}, track_key="ISRC:ARDL12600001")["tracks"][0]
            self.assertEqual(track["distribution_visible"], full)
            self.assertEqual("shares" in track["segments"][0], full)
            self.assertNotIn("records", track)
            if full:
                self.assertAlmostEqual(sum(s["amount_usd"] for s in track["segments"][0]["shares"]), track["base_amount_usd"])

    def test_distribution_groups_saved_partners_and_artists_and_conserves_cents(self):
        ctx = context()
        agreement = ctx["snapshot"]["contracts"][0]["split"]["agreements"][0]
        agreement["owners"] = [{"name": name, "percent": None} for name in ["Indyana", "Hernan", "Claudio"]]
        _, _, rules = ex.compiled_rules(ctx, "Artista")
        for amount in [100, -100, 0.01, 100.005]:
            rows = [{"isrc": "ARDL12600001", "statement_month": "2026-07", "pending_reason": "", "amount_usd": amount},
                    {"isrc": None, "statement_month": "2026-07", "pending_reason": "Contrato abierto", "amount_usd": 7.13}]
            result = ex.format_distribution(rows, rules)
            groups = {r["name"]: r for r in result["groups"]}
            self.assertEqual(set(groups), {"Indyana", "Hernan", "Claudio", "Artistas"})
            self.assertEqual(groups["Artistas"]["members"][0]["name"], "Artista")
            self.assertAlmostEqual(sum(r["amount_usd"] for r in groups.values()), result["distributed_amount_usd"])
            self.assertAlmostEqual(result["distributed_amount_usd"] + result["pending_amount_usd"], result["amount_usd"])
            self.assertEqual(sum(r["amount_usd"] for r in result["pending"]), result["pending_amount_usd"])
        self.assertEqual(ex.format_distribution([], {})["amount_usd"], 0)

    def test_distribution_cannot_override_artist_scope_and_keeps_track_detail_private(self):
        with patch.object(ex, "get_context", return_value=context()), patch.object(ex, "_job") as query:
            with self.assertRaises(PermissionError):
                ex.distribution([], {}, {"Artista"}, beneficiary="Socio")
            query.assert_not_called()
        row = {"isrc": "ARDL12600001", "statement_month": "2026-07", "pending_reason": "", "amount_usd": 100}
        with patch.object(ex, "get_context", return_value=project_context()), patch.object(ex, "_job", return_value=[row]) as query:
            result = ex.distribution([], {}, {"Artista"}, source="fuga", period_mode="last_6_months", drill={"dsp": "YouTube"})
            sql, params = query.call_args.args
            self.assertIn("WHERE t.root IS NOT NULL", sql)
            self.assertIn("n.statement_month BETWEEN r.start AND r.end", sql)
            self.assertEqual(next(p.value for p in params if p.name == "drill_dsp"), "YouTube")
            self.assertEqual(next(p.value for p in params if p.name == "source"), "fuga")
            self.assertEqual({r["name"]: r["amount_usd"] for r in result["groups"]}, {"Indyana": 54, "Socio": 40, "Artistas": 6})
        with patch.object(ex, "get_context", return_value=context()), patch.object(ex, "_job", return_value=[income(100)]):
            private = ex.detail([], {}, {"Artista"}, track_key="ISRC:ARDL12600001")
            self.assertNotIn("shares", private["tracks"][0]["segments"][0])

    def test_distribution_budget_fallback_materializes_only_selected_income(self):
        discovery = [{"section": "scan_scope", "payload": json.dumps({"months": ["2026-07-01"], "statements": ["2026-07-01"], "undated": False})}]
        row = {"isrc": "ARDL12600001", "statement_month": "2026-07", "pending_reason": "", "amount_usd": 100}
        with patch.object(ex, "get_context", return_value=project_context()), patch.object(ex, "_job", side_effect=[InternalServerError("Query exceeded limit for bytes billed"), discovery, [row]]) as query:
            self.assertEqual(ex.distribution([], {}, {"Artista"})["distributed_amount_usd"], 100)
            sql, params = query.call_args.args
            self.assertIn("statement_month BETWEEN DATE '2026-07-01' AND DATE '2026-07-01'", sql)
            self.assertIn("SUM(base_amount_usd)", sql)
            self.assertIn("FROM explorer_filtered", sql)

    def test_budget_fallback_preserves_options_and_caches_the_complete_result(self):
        base, params, _ = ex.base_query(context(), {}, "Artista", measure="contractual", restricted=True,
            period_basis="transaction_month", source=None, account=None, keyword="Tema",
            start_month=None, end_month=None, drill={"track_title": "Tema"})
        discovery = [{"section": "option_bounds", "payload": '{"first_month":"2021-07","last_month":"2026-10"}'},
                     {"section": "scan_scope", "payload": json.dumps({"months": ["2025-12-01", "2026-01-01"],
                         "statements": ["2025-12-01", "2026-01-01", "2026-10-01"], "undated": True})}]
        result = [{"section": "totals", "payload": '{"amount_usd":-0.01}'}]
        ex._dashboard_rows.cache_clear()
        try:
            with patch.object(ex, "_job", side_effect=[InternalServerError("Query exceeded limit for bytes billed: 5000000000."), discovery, result]) as query:
                args = (base, json.dumps([p.to_api_repr() for p in params], sort_keys=True), "last_6_months", 10)
                expected = result + discovery[:1]
                self.assertEqual(ex._dashboard_rows(*args), expected)
                self.assertEqual(ex._dashboard_rows(*args), expected)
                self.assertEqual(query.call_count, 3)
                sql, bounded_params = query.call_args.args
                # Late statements and undated consumption remain in scope;
                # disjoint statement years are aggregated together only once.
                for window in ["BETWEEN DATE '2025-12-01' AND DATE '2025-12-01'",
                               "BETWEEN DATE '2026-01-01' AND DATE '2026-10-01'", "statement_month IS NULL"]:
                    self.assertIn(window, sql)
                self.assertEqual(sql.count(context()["table"]), 3)
                self.assertIn("SUM(amount_usd)", sql)
                self.assertEqual(next(p.value for p in bounded_params if p.name == "beneficiary_search"), "artista")
                months = next(p for p in bounded_params if p.name == "selected_months")
                self.assertEqual([v.isoformat() for v in months.values], ["2025-12-01", "2026-01-01"])
                self.assertIn("title=@drill_track_title", sql)
        finally:
            ex._dashboard_rows.cache_clear()

    def test_budget_fallback_does_not_retry_permission_errors(self):
        ex._dashboard_rows.cache_clear()
        with patch.object(ex, "_job", side_effect=Forbidden("permission denied")) as query:
            with self.assertRaises(Forbidden): ex._dashboard_rows("base", "[]", "all", 10)
            self.assertEqual(query.call_count, 1)

    def test_budget_fallback_handles_an_empty_search_without_reading_history(self):
        sql = ex._bounded_dashboard_sql("WITH filtered AS (SELECT * FROM `p.d.t` WHERE release_id=@release)",
            {"months": None, "statements": None, "undated": False}, 10)
        self.assertIn("WHERE release_id=@release AND (FALSE)", sql)
        self.assertIn("period_month IN UNNEST(@selected_months)", sql)

    def test_saved_eligible_nested_rules_and_zero_participant(self):
        ctx = context()
        for beneficiary, expected in [("Indyana", 54), ("Socio", 40), ("Artista", 6), ("Proyecto", 0)]:
            tracks, rules, full = ex.compiled_rules(ctx, beneficiary)
            self.assertEqual(len(tracks), 1)
            self.assertEqual(rules[0]["percent"], expected)
            self.assertAlmostEqual(sum(s["percent"] for s in full[tracks[0]["root"]][0]["shares"]), 100)

    def test_open_and_invalid_never_allocate(self):
        for field in ["is_closed", "invalid"]:
            ctx = context()
            if field == "invalid":
                ctx["snapshot"]["contracts"][0]["split"]["agreements"][0]["master_pool_percent"] = 99
            else:
                ctx["snapshot"]["contracts"][0][field] = False
            tracks, rules, full = ex.compiled_rules(ctx, "Artista")
            self.assertTrue(tracks[0]["reason"])
            self.assertEqual((rules, full), ([], {}))

    def test_overlap_is_pending(self):
        ctx = context()
        split = ctx["snapshot"]["contracts"][0]["split"]
        duplicate = deepcopy(split["agreements"][0]); duplicate["id"] = "overlap"
        split["agreements"].append(duplicate)
        self.assertEqual(ex.compiled_rules(ctx, "Artista")[1], [])

    def test_scope_is_canonical_and_cannot_be_overridden(self):
        names = context()["names"]
        self.assertEqual(ex.authorize_beneficiary(None, names, {"ARTISTA"}), "Artista")
        for value, scope in [("Indyana", {"Artista"}), (None, set()), (None, {"Artista", "Socio"})]:
            with self.assertRaises(PermissionError): ex.authorize_beneficiary(value, names, scope)
        with patch.object(ex, "get_context", return_value=context()), patch.object(ex, "_job") as query:
            with self.assertRaises(PermissionError): ex.detail([], {}, {"Artista"}, beneficiary="Socio", track_key="foreign")
            query.assert_not_called()

    def test_historical_candu_portal_label_does_not_use_substring_matching(self):
        names = {"candu dominguez": "Candu Domínguez", "candu otra": "Candu Otra", "indyana": "Indyana"}
        self.assertEqual(ex.authorize_beneficiary(None, names, {"Candu"}), "Candu Domínguez")
        for foreign in ["Candu Otra", "Indyana"]:
            with self.assertRaises(PermissionError): ex.authorize_beneficiary(foreign, names, {"Candu"})
        with patch.object(ex, "catalog_data", return_value=([], [])), patch.object(ex, "current_manifest", return_value="pinned"), patch.object(ex, "participant_names", return_value=names):
            self.assertEqual(ex.read_options([], {"Candu"})["beneficiaries"], ["Candu Domínguez"])

    def test_search_context_comes_from_contract_recipients_not_compound_credits(self):
        ctx = context()
        names = {**ctx["names"], "proyecto / artista": "Proyecto / Artista", "lost in you": "Lost In You"}
        with patch.object(ex, "catalog_data", return_value=([], [])), patch.object(ex, "current_manifest", return_value="pinned"), patch.object(ex, "participant_names", return_value=names):
            for keyword, expected in [("ARTISTA", "Artista"), ("Lost In You", None), ("Proyecto / Artista", None), ("Proyecto", None), ("", None)]:
                self.assertEqual(ex.read_options(ctx["snapshot"]["contracts"], None, keyword=keyword)["participant"], expected)
            self.assertIsNone(ex.read_options(ctx["snapshot"]["contracts"], {"Socio"}, keyword="Artista")["participant"])
            self.assertEqual(ex.read_options(ctx["snapshot"]["contracts"], {"Artista"}, keyword="")["participant"], "Artista")

    def test_internal_participant_changes_money_without_changing_the_search_universe(self):
        ctx = context()
        ctx["snapshot"]["catalog"].append({"isrc": "ARDL12600002", "title": "Lost In You", "artists_informed": "Otro"})
        args = dict(restricted=False, period_basis="statement_period", source=None, account=None,
                    keyword="Lost In You", start_month="2026-01", end_month="2026-09", drill={"track": "ISRC:ARDL12600002"})
        income_sql, income_params, _ = ex.base_query(ctx, {}, None, measure="income", **args)
        own_sql, own_params, _ = ex.base_query(ctx, {}, "Artista", measure="contractual", **args)
        left = {p.name: p.to_api_repr() for p in income_params}; right = {p.name: p.to_api_repr() for p in own_params}
        for key in ["tracks", "roots", "bindings", "keywords", "source", "account", "start", "end", "drill_track", "all_tracks"]:
            self.assertEqual(left[key], right[key], key)
        self.assertTrue(next(p for p in own_params if p.name == "all_tracks").value)
        self.assertIn("WHERE TRUE", own_sql)
        self.assertIn("n.title AS title", own_sql)
        self.assertNotIn("identity_key=@drill_track", own_sql)
        tail = ex._period_sql("last_6_months")
        self.assertLess(tail.index("LIMIT 6"), tail.index("identity_key=@drill_track"))
        _, private_params, _ = ex.base_query(ctx, {}, "Artista", measure="contractual", **{**args, "restricted": True})
        self.assertFalse(next(p for p in private_params if p.name == "all_tracks").value)

    def test_detail_money_conservation_private_projection_and_adjustments(self):
        for amount in [100, -100, 0, .01, 100.005]:
            with patch.object(ex, "get_context", return_value=context()), patch.object(ex, "_job", return_value=[income(amount)]):
                admin = ex.detail([], {}, None, track_key="ISRC:ARDL12600001", period_mode="all")
                artist = ex.detail([], {}, {"Artista"}, track_key="ISRC:ARDL12600001", period_mode="all")
            track = admin["tracks"][0]; segment = track["segments"][0]
            self.assertAlmostEqual(sum(s["amount_usd"] for s in segment["shares"]), track["base_amount_usd"])
            private = artist["tracks"][0]
            self.assertNotIn("records", private)
            self.assertNotIn("shares", private["segments"][0])
            self.assertEqual(private["segments"][0]["label"], "Participación vigente")
            own = next(s for s in segment["shares"] if s["name"] == "Artista")
            self.assertEqual(private["segments"][0]["own_share"], {"percent": 6, "amount_usd": own["amount_usd"]})
            serialized = json.dumps(artist)
            self.assertNotIn('Socio', serialized); self.assertNotIn('Titular del master', serialized)

    def test_pending_is_never_presented_as_a_zero_allocation(self):
        with patch.object(ex, "get_context", return_value=context()), patch.object(ex, "_job", return_value=[income(19, pending_reason="Contrato abierto")]):
            result = ex.detail([], {}, {"Artista"}, track_key="ISRC:ARDL12600001")
        self.assertEqual(result["tracks"][0]["segments"], [])
        self.assertEqual(result["tracks"][0]["pending"], [{"reason": "Contrato abierto", "amount_usd": 19}])

    def test_future_report_checkbox_does_not_block_closed_contract_exploration(self):
        ctx = context()
        ctx["snapshot"]["contracts"][0]["future_reports_selected"] = False
        before = deepcopy(ctx)
        self.assertEqual(ex.compiled_rules(ctx, "Artista")[1][0]["percent"], 6)
        with patch.object(ex, "get_context", return_value=ctx), patch.object(ex, "_job", return_value=[income(100)]):
            result = ex.detail([], {}, None, track_key="ISRC:ARDL12600001")
        self.assertEqual(sum(s["amount_usd"] for s in result["tracks"][0]["segments"][0]["shares"]), 100)
        self.assertEqual(result["tracks"][0]["pending"], [])
        self.assertEqual(ctx, before)

    def test_selected_title_and_isrc_are_intersected_and_survive_participant_drill(self):
        ctx = context()
        args = dict(measure="contractual", restricted=False, period_basis="statement_period", source=None,
                    account=None, keyword="MC Tota", start_month="2021-07", end_month="2026-06",
                    drill={"track": "ISRC:ARDL12600001", "track_title": "Movimento"})
        base, params, _ = ex.base_query(ctx, {}, "Artista", track_key="ISRC:ARDL12600001", track_title="Movimento", **args)
        values = {p.name: p.value for p in params if isinstance(p, bigquery.ScalarQueryParameter)}
        self.assertEqual(values["track_key"], values["drill_track"])
        self.assertEqual(values["track_title"], values["drill_track_title"])
        self.assertEqual(values["track_title"], "Movimento")
        tail = ex._period_sql("last_6_months")
        for condition in ["identity_key=@track_key", "title=@track_title", "identity_key=@drill_track", "title=@drill_track_title"]:
            self.assertIn(condition, tail)
            self.assertLess(tail.index("LIMIT 6"), tail.index(condition))
        self.assertNotIn("title=@drill_track_title", base)
        with patch.object(ex, "get_context", return_value=ctx), patch.object(ex, "_job", return_value=[income(100, title="Movimento")]) as query:
            detail = ex.detail([], {}, None, beneficiary="Artista", track_key="ISRC:ARDL12600001", track_title="Movimento", end_month="2026-06", period_mode="closed_range")
        self.assertEqual(detail["tracks"][0]["row_title"], "Movimento")
        self.assertEqual(detail["tracks"][0]["base_amount_usd"], 100)
        self.assertEqual(next(p.value for p in query.call_args.args[1] if p.name == "track_title"), "Movimento")

    def test_query_contract_uses_statement_not_consumption_and_keeps_units(self):
        args = dict(measure="contractual", restricted=True, period_basis="transaction_month", source=None,
                    account=None, keyword="", start_month=None, end_month=None, drill={})
        base, params, _ = ex.base_query(context(), {}, "Artista", **args)
        self.assertIn("n.statement_month BETWEEN r.start AND r.end", base)
        self.assertIn("transaction_month AS period_month", base)
        self.assertNotIn("units *", base)
        self.assertIn("n.isrc IN UNNEST(@roots)", base)
        tail = ex._period_sql("last_6_months")
        self.assertLess(tail.index("LIMIT 6"), tail.index("identity_key=@track_key"))
        # Typed empty arrays must survive the cache round-trip as well.
        for param in params:
            self.assertEqual(ex._parameter_from_api(param.to_api_repr()).to_api_repr(), param.to_api_repr())
        for bad in [{"injected; DROP TABLE": "x"}, {"dsp": []}, {"month": "2026-77"}]:
            with self.assertRaises(ValueError): ex.base_query(context(), {}, "Artista", **{**args, "drill": bad})

    def test_registry_changes_cache_key_and_selected_root_scope(self):
        ctx = context()
        args = dict(measure="contractual", restricted=True, period_basis="statement_period", source=None,
                    account=None, keyword="", start_month=None, end_month=None, drill={})
        _, before, _ = ex.base_query(ctx, {}, "Artista", **args)
        ctx["snapshot"]["contracts"][0]["is_closed"] = False
        _, after, _ = ex.base_query(ctx, {}, "Artista", **args)
        self.assertNotEqual([p.to_api_repr() for p in before], [p.to_api_repr() for p in after])
        self.assertEqual(ex.compiled_rules(ctx, "Foreign")[0], [])

    def test_guard_is_pinned_validated_and_immutable(self):
        manifest = {"bucket": "b", "prefix": "marts", "objects": {"standardized_raw_all_sources.parquet": {"object": "raw", "generation": 1}}}
        path, identity = guard.guard_object(manifest)
        other = deepcopy(manifest); other["objects"]["standardized_raw_all_sources.parquet"]["generation"] = 2
        self.assertNotEqual(path, guard.guard_object(other)[0])
        client = MagicMock(); blob = client.bucket.return_value.blob.return_value
        blob.download_as_bytes.side_effect = NotFound("not ready")
        self.assertIsNone(guard.cached_ranking_guard(manifest, client))
        blob.download_as_bytes.side_effect = None
        for document in [{"identity": identity, "complete": False, "keys": []}, {"identity": identity, "complete": True, "keys": ['["bad"]']}]:
            blob.download_as_bytes.return_value = json.dumps(document)
            with self.assertRaises(RuntimeError): guard.cached_ranking_guard(manifest, client)
        blob.download_as_bytes.side_effect = NotFound("not ready")
        with patch.object(guard, "unsafe_ranking_slot_keys", return_value=frozenset()):
            guard.publish_ranking_guard(manifest, client)
        self.assertEqual(blob.upload_from_string.call_args.kwargs["if_generation_match"], 0)


if __name__ == "__main__": unittest.main()
