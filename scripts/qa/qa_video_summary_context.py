"""Retain video evidence across statement/consumption aggregates and BQ projections."""
import ast
import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import polars as pl
from polars.testing import assert_frame_equal

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from lib.distributor_policy_store import use_distributor_policy_snapshot
from scripts.load_bigquery_release import build_song, build_dashboard, build_detail
from scripts.build_keyword_royalty_report import build_track_summary_lf


def raw_rows():
    return pl.DataFrame({
        "source": ["fuga"] * 4, "account": ["test"] * 4,
        "statement_period": ["2026-02", "2026-03", "2026-03", "2026-03"],
        "transaction_month": ["2026-01"] * 4, "statement_type": ["regular"] * 4,
        "asset_product_type": ["Asset"] * 4, "asset_isrc": ["ARDL12500066"] * 4,
        "product_upc": [None] * 4, "product_title_statement": [None] * 4,
        "product_artist_statement": [None] * 4,
        "asset_title_statement": ["Tema"] * 4, "asset_artist_statement": ["Artista"] * 4,
        "track_statement_style": ["Tema"] * 4, "artist_statement_style": ["Artista"] * 4,
        "amount_usd": [10., -3., 1., 8.], "net_amount_eur": [10., -3., 1., 8.],
        "asset_quantity_num": [100., -20., 4., 10.], "units": [100., -20., 4., 10.],
        "video_id": ["m6mrKKUuosk", "m6mrKKUuosk", "nsNXd-HljTE", None],
        "video_id_source": ["DSP Container ID"] * 3 + [None],
        "channel_id": ["UCnyowdvLv8WNs7RVasOWPDA"] * 3 + [None],
        "dsp_normalized": ["YouTube"] * 3 + ["Spotify"],
        "monetization_normalized": ["Ads", "Adjustment", "Ads", "Premium"],
        "content_origin_normalized": ["Video / Channel"] * 3 + ["Audio / Master"],
        "classification_status": ["exact"] * 4,
        "store_report_label": ["YouTube"] * 3 + ["Spotify"],
        "source_sheet": ["standard_statement_csv"] * 4, "revenue_basis": ["generation"] * 4,
    })


class VideoSummaryContextTests(unittest.TestCase):
    def test_source_builder_retains_both_months_and_distinct_videos_with_same_isrc(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / "raw.parquet"; song = root / "song.parquet"
            raw_rows().write_parquet(source)
            module = importlib.import_module("scripts.build_song_level_fuga")
            with patch.object(module, "INPUT_PATH", source), patch.object(module, "OUTPUT_PATH", song):
                module.main()
            frame = pl.read_parquet(song)
            self.assertEqual(frame.height, 4)
            build_song(song, root / "bq.parquet", "test")
            bq = pl.read_parquet(root / "bq.parquet")
            self.assertEqual(bq["statement_month"].n_unique(), 2)
            self.assertEqual(bq["transaction_month"].n_unique(), 1)
            self.assertEqual(set(bq["content_origin"]), {"Video / Channel", "Audio / Master"})
            self.assertEqual(bq["amount_usd"].sum(), 16.)
            self.assertEqual(bq["units"].sum(), 94.)
            summary = build_track_summary_lf(frame.with_columns(pl.col("statement_period").alias("period_month")).lazy()).collect()
            self.assertEqual(summary.height, 3)
            video = summary.filter(pl.col("report_code") == "m6mrKKUuosk").row(0, named=True)
            self.assertEqual((video["amount_usd"], video["units"]), (7., 80.))
            self.assertEqual((video["first_month"], video["last_month"]), ("2026-02", "2026-03"))

    def test_dashboard_preserves_old_values_and_retains_native_video_context(self):
        from app import vpo_corp_api as api
        policy = {"schema_version": 1, "policy_version": 1,
                  "entries": [{"source": "fuga", "account": "test", "sheet_rules": {
                      "standard_statement_csv": {"catalog_view": True, "statement_view": True,
                                                 "cash_view": True, "revenue_basis": "generation"}}}],
                  "report_personalization": {"enabled": False}}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / "raw.parquet"; target = root / "dashboard.parquet"
            raw_rows().write_parquet(source)
            env = {"VPO_CATALOG_MASTER_PATH": str(root / "absent.parquet"),
                   "VPO_CATALOG_STATUS_PATH": str(root / "absent-status.parquet")}
            # Run the published builder as an independent witness for every old column.
            before_source = subprocess.run(["git", "show", "HEAD:app/vpo_corp_api.py"], cwd=ROOT,
                                          check=True, capture_output=True, encoding="utf-8").stdout
            nodes = [n for n in ast.parse(before_source).body if isinstance(n, ast.FunctionDef)
                     and n.name in {"royalties_dashboard_input_columns", "build_royalties_dashboard_summary_mart"}]
            previous = dict(vars(api))
            exec(compile(ast.Module(body=nodes, type_ignores=[]), "published_dashboard.py", "exec"), previous)
            with patch.dict(os.environ, env), use_distributor_policy_snapshot(policy):
                previous["build_royalties_dashboard_summary_mart"](source, True, output_path=root / "before.parquet", partition_large_input=False)
                api.build_royalties_dashboard_summary_mart(source, True, output_path=target, partition_large_input=False)
                api.build_partitioned_royalties_dashboard_summary_mart(source, root / "partitioned.parquet")
            frame = pl.read_parquet(target); before = pl.read_parquet(root / "before.parquet")
            old_columns = before.columns
            assert_frame_equal(before.sort(old_columns), frame.select(old_columns).sort(old_columns))
            partitioned = pl.read_parquet(root / "partitioned.parquet")
            assert_frame_equal(frame.sort(frame.columns), partitioned.sort(frame.columns))
            self.assertEqual(frame.filter(pl.col("video_id").is_not_null()).height, 3)
            self.assertTrue(frame.filter(pl.col("video_id").is_not_null())["video_id_source"].is_not_null().all())
            build_dashboard(target, root / "bq-dashboard.parquet", "test")
            loaded = pl.read_parquet(root / "bq-dashboard.parquet")
            self.assertEqual(loaded["video_id"].to_list(), frame["video_id"].to_list())
            self.assertEqual(loaded["channel_id"].to_list(), frame["channel_id"].to_list())
            self.assertEqual(loaded["amount_usd"].sum(), 16.)

    def test_original_store_context_is_not_lost_for_onerpm(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pl.DataFrame({"source": ["onerpm"], "source_sheet": ["Masters"],
                          "Store": ["Youtube Premium"], "amount_usd": [2.], "units": [3.]}).write_parquet(root / "raw.parquet")
            build_detail(root / "raw.parquet", root / "fact.parquet", "test")
            row = pl.read_parquet(root / "fact.parquet").row(0, named=True)
            self.assertEqual(row["store_name"], "Youtube Premium")
            self.assertIsNone(row["video_id"])


if __name__ == "__main__":
    unittest.main()
