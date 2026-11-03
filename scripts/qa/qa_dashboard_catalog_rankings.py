"""Complete dashboard rankings preserve monetary totals and access boundaries."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import polars as pl
from fastapi.testclient import TestClient

from app import bigquery_dashboard as bq
from app import vpo_corp_api as api


POLICY = {"report_personalization": {"enabled": False}, "policy_version": 1, "updated_at": None}


class DashboardCatalogRankingsTests(unittest.TestCase):
    def test_parquet_complete_rankings_preserve_totals_filters_and_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.parquet"
            pl.DataFrame([{
                "statement_period": "2026-09", "transaction_month": "2026-08",
                "source": "test", "account": "A" if i % 2 else "B",
                "title": f"Tema {i:03}", "artist": f"Artista {i:03}",
                "search_text": f"tema {i:03} artista {i:03}",
                "amount_usd": float(i), "units": float(i * 10), "raw_rows": 1,
                "dsp": "YouTube", "monetization_normalized": "Streaming",
                "content_origin_normalized": "Official", "territory": f"Territory {i:03}",
                "sale_type": "Streaming", "label": f"Label {i:03}",
            } for i in range(1, 66)]).write_parquet(summary)
            with patch.object(api, "VPO_ROYALTIES_DASHBOARD_BACKEND", "parquet"), \
                 patch.object(api, "VPO_LOCAL_MARTS_DIR", None), \
                 patch.object(api, "VPO_API_KEY", "scroll-qa"), \
                 patch.object(api, "ensure_marts", return_value={api.ROYALTIES_DASHBOARD_SUMMARY_FILE: summary}), \
                 patch("app.catalog_refresh.fallback_summary", return_value=(summary, "ready")), \
                 patch.object(api, "apply_report_net_personalization", side_effect=lambda frame, *a, **kw: frame), \
                 patch.object(api, "load_distributor_policy_document", return_value=POLICY):
                client = TestClient(api.app)

                def request(**params):
                    response = client.get("/royalties-dashboard", params=params,
                                          headers={"X-VPO-API-Key": "scroll-qa"})
                    self.assertEqual(response.status_code, 200, response.text)
                    return response.json()

                default = request()
                full = request(full_catalog_rankings="true")
                for category in ("title", "artist"):
                    self.assertEqual(len(default["rankings"][category]), 10)
                    self.assertEqual(len(full["rankings"][category]), 65)
                    self.assertEqual(full["rankings"][category][:10], default["rankings"][category])
                self.assertEqual(full["rankings"]["title"][-1]["name"], "Tema 001")
                self.assertEqual(full["totals"], default["totals"])
                first = request(paged_rankings="true")
                self.assertEqual(first["totals"], full["totals"])
                self.assertEqual(first["matrix"], full["matrix"])
                self.assertEqual(first["ranking_next"], {"artist": 50, "title": 50})
                for category in ("artist", "title"):
                    following = request(rank_category=category, rank_offset=50,
                                        rank_snapshot_token=first["ranking_snapshot"])
                    self.assertEqual(first["rankings"][category] + following["rows"], full["rankings"][category])
                    self.assertIsNone(following["next_offset"])
                small = request(paged_rankings="true", account="A")
                self.assertEqual(len(small["rankings"]["title"]), 33)
                self.assertIsNone(small["ranking_next"]["title"])
                stale = client.get("/royalties-dashboard", params={
                    "rank_category": "title", "rank_offset": 50, "rank_snapshot_token": "old",
                }, headers={"X-VPO-API-Key": "scroll-qa"})
                self.assertEqual(stale.status_code, 409)
                self.assertEqual(full["youtube"], default["youtube"])
                for category in ("territory", "label", "dsp"):
                    self.assertEqual(full["rankings"][category], default["rankings"][category])
                self.assertEqual(len(request(full_catalog_rankings="true", account="A")["rankings"]["title"]), 33)
                self.assertEqual(len(request(full_catalog_rankings="true", keyword="065")["rankings"]["title"]), 1)
                self.assertEqual(request(full_catalog_rankings="true", start_month="2030-01")["rankings"]["title"], [])
                transaction = request(full_catalog_rankings="true", period_basis="transaction_month")
                self.assertEqual(transaction["period_months"], ["2026-08"])
                self.assertEqual(len(transaction["rankings"]["title"]), 65)
                with patch.object(api, "operational_connect"), \
                     patch.object(api, "require_module_permission", return_value={"scope": {"Artista 065"}}):
                    response = client.get("/royalties-dashboard", params={"full_catalog_rankings": "true"},
                                          headers={"X-VPO-API-Key": "scroll-qa", "X-VPO-Username": "qa"})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual([r["name"] for r in response.json()["rankings"]["artist"]], ["Artista 065"])

    def test_bigquery_limits_only_general_artist_and_title_rankings(self):
        for full in (False, True):
            with self.subTest(full=full):
                client = MagicMock()
                client.query.return_value.result.side_effect = [[{"release_id": "qa-ready"}], []]
                bq.royalties_dashboard_bigquery(policy_document=POLICY, full_catalog_rankings=full,
                                               artist_scope={"Artista"}, client=client)
                call = client.query.call_args
                params = {p.name: p.to_api_repr() for p in call.kwargs["job_config"].query_parameters}
                self.assertEqual(params["full_catalog_rankings"]["parameterValue"]["value"], str(full).lower())
                self.assertEqual(params["ranking_limit"]["parameterValue"]["value"], "10")
                self.assertIn("(@full_catalog_rankings AND category IN ('artist', 'title'))", call.args[0])
                self.assertEqual(call.args[0].count("<= @ranking_limit"), 2)
                self.assertEqual(params["artist_scope_tokens"]["parameterValue"]["arrayValues"], [{"value": "artista"}])

    def test_bigquery_route_forwards_opt_in(self):
        with patch.object(api, "VPO_ROYALTIES_DASHBOARD_BACKEND", "bigquery"), \
             patch.object(api, "VPO_API_KEY", "scroll-qa"), \
             patch.object(api, "query_royalties_dashboard_from_bigquery", return_value={}) as query:
            response = TestClient(api.app).get("/royalties-dashboard", params={"full_catalog_rankings": "true"},
                                               headers={"X-VPO-API-Key": "scroll-qa"})
            self.assertEqual(response.status_code, 200)
            self.assertIs(query.call_args.kwargs["full_catalog_rankings"], True)


if __name__ == "__main__":
    unittest.main()
