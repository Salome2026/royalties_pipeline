"""Regression witnesses for source identity, quantities and compact report grouping."""
import sys
import tempfile
import unittest
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.lib.video_context import preserve_video_context
from scripts.lib.bigquery_source_integrity import validate_detail_source
from scripts.load_bigquery_release import build_detail, build_detail_batches, build_song
from scripts.build_keyword_royalty_report import report_identity_expr, build_track_summary_lf


class VideoContextTests(unittest.TestCase):
    def test_native_ids_survive_isrc_and_do_not_use_unrelated_track_ids(self):
        raw = pl.DataFrame({
            'source': ['fuga', 'orchard', 'dashgo', 'onerpm', 'soundon', 'ada'],
            'source_sheet': ['', '', '', 'Youtube Channels', '', ''],
            'asset_isrc': ['ARDL12500066'] * 6,
            'DSP Container ID': ['m6mrKKUuosk', None, None, None, None, None],
            'YOUTUBE VIDEO ID': [None, 'nsNXd-HljTE', None, None, None, None],
            'VideoId': [None, None, 'PTIN0kcBank', None, None, None],
            'Video ID': [None, None, None, 'kulHLYoWF6I', None, None],
            'Track ID': [None, None, None, None, '12345678901', None],
            'catalog_number': [None, None, None, None, None, 'ABCDEFGHIJK'],
        })
        got = preserve_video_context(raw)
        self.assertEqual(got['video_id'].to_list(),
                         ['m6mrKKUuosk', 'nsNXd-HljTE', 'PTIN0kcBank', 'kulHLYoWF6I', None, None])
        self.assertEqual(got['asset_isrc'].to_list(), raw['asset_isrc'].to_list())

    def test_quantities_respect_native_product_negative_and_explicit_zero(self):
        raw = pl.DataFrame({'source': ['fuga', 'fuga', 'onerpm', 'onerpm'],
            'asset_product_type': ['Asset', 'Product', None, None],
            'Asset Quantity': [-12., 999., None, None],
            'Product Quantity': [999., 17., None, None],
            'units': [0., 0., 0., None], 'Quantity': [None, None, 777., 34.]})
        self.assertEqual(preserve_video_context(raw)['units'].to_list(), [-12., 17., 0., 34.])

    def test_report_exception_is_channel_only_and_consolidates_across_isrc_change(self):
        raw = pl.DataFrame({'video_id': ['m6mrKKUuosk'] * 4,
            'asset_isrc': [None, 'ARDL12500066', 'ARDL12500066', 'ARDL12500066'],
            'catalog_key': ['VIDEO:m6mrKKUuosk', 'ISRC:ARDL12500066', 'ISRC:ARDL12500066', 'ISRC:ARDL12500066'],
            'content_origin_normalized': ['Video / Channel', 'Video / Channel', 'Music / Art Track', 'UGC']})
        keys = raw.select(report_identity_expr(set(raw.columns)).alias('key'))['key'].to_list()
        self.assertEqual(keys, ['VIDEO:m6mrKKUuosk', 'VIDEO:m6mrKKUuosk', 'ISRC:ARDL12500066', 'ISRC:ARDL12500066'])

    def test_independent_source_check_rejects_lost_id_or_zero_quantities(self):
        with tempfile.TemporaryDirectory() as d:
            source, target = Path(d)/'source.parquet', Path(d)/'detail.parquet'
            pl.DataFrame({'source': ['fuga', 'orchard'], 'account': ['a', 'b'],
                'statement_period': ['2026-03'] * 2, 'transaction_month': ['2026-01'] * 2,
                'asset_isrc': ['ARDL12500066'] * 2, 'amount_usd': [11., -2.],
                'Asset Quantity': [123., None], 'QUANTITY': [None, 17.],
                'DSP Container ID': ['m6mrKKUuosk', None],
                'YOUTUBE VIDEO ID': [None, 'nsNXd-HljTE']}).write_parquet(source)
            build_detail(source, target, 'test')
            good = pl.read_parquet(target)
            self.assertEqual(good['units'].to_list(), [123., 17.])
            batched = Path(d)/'batched.parquet'
            build_detail_batches(source, batched, 'test', batch_size=1)
            from polars.testing import assert_frame_equal
            assert_frame_equal(good, pl.read_parquet(batched))
            for corruption in [pl.lit(0.).alias('units'), pl.lit(None, dtype=pl.String).alias('video_id')]:
                good.with_columns(corruption).write_parquet(target)
                with self.assertRaisesRegex(ValueError, 'fuente'):
                    validate_detail_source(source, target)

    def test_channel_summary_preserves_confirmed_contract_participants(self):
        from scripts.qa.qa_excel_contracts import evaluate, row, snapshot
        state = snapshot()
        rows = [row(asset_isrc=None, video_id='video-code1', content_origin_normalized='Video / Channel'),
                row(video_id='video-code1', content_origin_normalized='Video / Channel')]
        names, values, summary = evaluate(rows, state)
        self.assertEqual(summary.height, 1)
        self.assertEqual(summary['_report_identity'][0], 'VIDEO:video-code1')
        self.assertAlmostEqual(sum(cell[1] for cell in values[0].values() if cell), 200.)


if __name__ == '__main__':
    unittest.main()
