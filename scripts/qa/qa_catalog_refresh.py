import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import polars as pl

from app.catalog_refresh import select_dashboard_release, snapshot_id, receive_change_event
from fastapi import HTTPException
from app import vpo_corp_api as api


class CatalogRefreshTests(unittest.TestCase):
    def test_durable_event_authentication_and_redelivery(self):
        environment = {"VPO_CATALOG_EVENT_AUDIENCE": "https://api/catalog/refresh-event",
                       "VPO_CATALOG_EVENT_SERVICE_ACCOUNT": "worker@example.test", "GCS_BUCKET": "bucket", "GCS_PREFIX": "marts"}
        payload = {"message": {"attributes": {"bucketId": "bucket", "eventType": "OBJECT_FINALIZE", "objectId": "marts/catalog_status.parquet"}}}
        with patch.dict("os.environ", environment), \
             patch("google.oauth2.id_token.verify_oauth2_token", return_value={"email": "worker@example.test", "email_verified": True}), \
             patch("app.catalog_refresh.launch_refresh", return_value="operations/test") as launch:
            with self.assertRaises(HTTPException) as caught:
                receive_change_event(payload, None)
            self.assertEqual(caught.exception.status_code, 401)
            launch.assert_not_called()
            self.assertTrue(receive_change_event(payload, "Bearer test")["queued"])
            launch.side_effect = RuntimeError("temporary outage")
            with self.assertRaises(HTTPException) as caught:
                receive_change_event(payload, "Bearer test")
            self.assertEqual(caught.exception.status_code, 503)

    def test_ready_requires_exact_catalog_generation_and_base_release(self):
        ready = {"base_release_id": "base", "catalog_generation": "123", "dashboard_release_id": "snapshot"}
        self.assertEqual(select_dashboard_release("base", {"catalog_generation": "123", "ready": ready}), ("snapshot", "ready"))
        self.assertEqual(select_dashboard_release("base", {"catalog_generation": "124", "ready": ready}), ("snapshot", "pending"))
        self.assertEqual(select_dashboard_release("new-base", {"catalog_generation": "123", "ready": ready}), ("new-base", "pending"))

    def test_snapshot_identity_covers_both_inputs(self):
        self.assertEqual(snapshot_id("base", "1"), snapshot_id("base", "1"))
        self.assertNotEqual(snapshot_id("base", "1"), snapshot_id("base", "2"))
        self.assertNotEqual(snapshot_id("base", "1"), snapshot_id("new-base", "1"))

    def test_full_source_restores_inactive_income_and_preserves_other_track(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.parquet"
            catalog = root / "catalog.parquet"
            status = root / "status.parquet"
            rows = [{"source": "test", "account": "test", "revenue_basis": "generation",
                     "statement_period": "2026-01", "transaction_month": "2025-12",
                     "amount_usd": amount, "units": 1, "asset_isrc": isrc,
                     "track_statement_style": title, "artist_statement_style": "Artist",
                     "dsp_normalized": "Spotify", "monetization_normalized": "streaming",
                     "content_origin_normalized": "official", "classification_status": "classified",
                     "store_report_label": "Spotify"}
                    for isrc, title, amount in [("ARAAA2600001", "Boxindanga", 25.25), ("ARAAA2600002", "Other", 10.50)]]
            pl.DataFrame(rows).write_parquet(source)
            pl.DataFrame({"catalog_key": ["ISRC:ARAAA2600001", "ISRC:ARAAA2600002"],
                          "asset_isrc": ["ARAAA2600001", "ARAAA2600002"]}).write_parquet(catalog)
            with patch.dict("os.environ", {"VPO_CATALOG_STATUS_PATH": str(status), "VPO_CATALOG_MASTER_PATH": str(catalog)}), \
                 patch("scripts.lib.catalog_report_filter.load_distributor_policy_document", return_value={"entries": [{"source": "test", "account": "test", "sheet_rules": {"": {"catalog_view": True, "statement_view": True, "revenue_basis": "generation"}}}]}), \
                 patch("lib.catalog_report_filter.load_distributor_policy_document", return_value={"entries": [{"source": "test", "account": "test", "sheet_rules": {"": {"catalog_view": True, "statement_view": True, "revenue_basis": "generation"}}}]}):
                for active, expected in [(False, 10.50), (True, 35.75), (False, 10.50)]:
                    pl.DataFrame({"catalog_key": ["ISRC:ARAAA2600001"], "active": [active],
                                  "include_in_reports": [active]}).write_parquet(status)
                    result = api.build_royalties_dashboard_summary_mart(source, refresh_cache=True,
                        output_path=root / "summary.parquet", partition_large_input=False)
                    self.assertAlmostEqual(pl.read_parquet(result)["amount_usd"].sum(), expected)
                    # The bounded-memory path must retain the same governance,
                    # money, quantities and classifications as the single scan.
                    multi = pl.concat([pl.DataFrame(rows), pl.DataFrame(rows).with_columns(
                        pl.lit('2026-02').alias('statement_period'),
                        (-pl.col('amount_usd')).alias('amount_usd'),
                        pl.lit(7, dtype=pl.Int64).alias('units'))])
                    multi.with_columns(pl.lit('unrelated payload').alias('unrelated_native_field')).write_parquet(source)
                    direct = api.build_royalties_dashboard_summary_mart(source, refresh_cache=True,
                        output_path=root / 'direct.parquet', partition_large_input=False)
                    partitioned = api.build_partitioned_royalties_dashboard_summary_mart(source, root / 'partitioned.parquet')
                    left, right = pl.read_parquet(direct), pl.read_parquet(partitioned)
                    self.assertEqual(left.columns, right.columns)
                    self.assertEqual(sorted(left.rows()), sorted(right.rows()))
                    pl.DataFrame(rows).write_parquet(source)


if __name__ == "__main__":
    unittest.main()
