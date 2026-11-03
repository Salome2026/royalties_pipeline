"""Contract scope must restrict every report table, independently of artist text."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import polars as pl
from fastapi import HTTPException
from scripts.qa.qa_excel_contracts import canonical_functions, row, snapshot, report
from app.royalty_reports.contract_filter import freeze_filter, filter_income, require_filter, use_filter
from app.royalty_reports.contracts import ReportRequest
from app.master_contract_associations import association_key
from lib.distributor_policy_store import use_distributor_policy_snapshot

A, B = 'ARDL12600001', 'ARDL12600002'


def state():
    s = snapshot()
    s['contracts'][0]['split']['agreements'][0]['distribution_contract_number'] = 10010
    other = deepcopy(s['contracts'][0])
    other['isrc'] = B
    other['split']['agreements'][0]['distribution_contract_number'] = 10011
    s['contracts'].append(other)
    return s


def selection(numbers=(10010,)):
    return freeze_filter(list(numbers), [{'number': 10010}, {'number': 10011}], state())


class ContractFilterTests(unittest.TestCase):
    def test_numbers_only_multiple_deduplicated_and_legacy_unchanged(self):
        ns = canonical_functions()
        model, canonical = ns['RoyaltyReportJobRequest'], ns['canonical_royalty_report_params']
        params = canonical(model(distribution_contract_numbers=[10011,10010,10011]), {})
        self.assertEqual(params['distribution_contract_numbers'], [10010,10011])
        self.assertEqual(params['keywords'], [])
        self.assertNotIn('distribution_contract_numbers', canonical(model(keywords=['artist']), {}))
        for output, key in [('excel','royalty_keyword'), ('google_sheet','royalty_google_sheet'), ('executive_pdf','royalty_executive')]:
            request = ReportRequest.from_job({'id':1,'report_key':key,'output_format':output,'params':params}, keywords=[])
            self.assertEqual(request.distribution_contract_numbers, (10010,10011))
        ns['is_wml'] = lambda: True
        with self.assertRaises(HTTPException): canonical(model(distribution_contract_numbers=[10010]), {})

    def test_unknown_empty_and_stale_snapshot_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'No existen'): selection([99999])
        with self.assertRaisesRegex(ValueError, 'no tienen temas'): freeze_filter([10012], [{'number':10012}], state())
        for values, release in [([10011], 'release-a'), ([10010], 'release-b')]:
            with self.assertRaises(ValueError): require_filter(selection(), values, release)

    def test_associations_native_precedence_exclusion_ambiguity_and_no_duplication(self):
        s = selection()
        video = association_key('VIDEO','video-code1','fuga','indy')
        s['associations']['included'][video] = [A]
        frame = pl.DataFrame([
            row(asset_isrc=A, catalog_key='ISRC:'+A, video_id='video-code1'),
            row(asset_isrc=B, catalog_key='ISRC:'+B, video_id='video-code1'),
            row(asset_isrc=None, catalog_key='VIDEO:video-code1', video_id='video-code1'),
        ]).lazy()
        with use_filter(s):
            self.assertEqual(filter_income(frame).collect().height, 2)
        self.assertEqual(filter_income(frame).collect().height, 3)
        s['associations']['excluded'][video] = [A]
        with use_filter(s): self.assertEqual(filter_income(frame).collect().height, 1)
        s['associations']['excluded'] = {}
        s['associations']['included'][video] = [A,B]
        with use_filter(s): self.assertEqual(filter_income(frame).collect().height, 1)

    def test_every_table_and_detail_count_obey_contract_and_keyword_intersection(self):
        policy = {'schema_version':1,'policy_version':1,'entries':[{'source':'fuga','account':'indy',
            'sheet_rules':{'royalty_detail':{'catalog_view':True,'statement_view':True,'revenue_basis':'generation'}}}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw, song = root/'raw.parquet', root/'song.parquet'
            pl.DataFrame([row(track_statement_style='Selected', artist_statement_style='Same artist'),
                row(asset_isrc=B, track_statement_style='Outside', artist_statement_style='Same artist', amount_usd=900.)]).write_parquet(raw)
            song.write_bytes(raw.read_bytes())
            with patch.dict(os.environ, {'VPO_CATALOG_MASTER_PATH':str(root/'absent'), 'VPO_CATALOG_STATUS_PATH':str(root/'status')}), use_distributor_policy_snapshot(policy):
                for basis in ['transaction_month','statement_period']:
                    for numbers, amount, count in [([10010],100.,1), ([10010,10011],1000.,2)]:
                        with use_filter(selection(numbers)):
                            args = dict(keywords=[], mode='any', start_month=None,end_month=None,period_basis=basis, standardized_path=raw)
                            self.assertEqual(report.count_report_detail_rows(**args),count)
                            tables = report.build_report_tables(**args, song_path=song, raw_limit=5000, detail_mode='full')
                            detail = tables['detalle']
                            self.assertEqual(len(detail),count)
                            summary = tables['resumen por tema']
                            self.assertEqual(len(summary),count)
                            self.assertAlmostEqual(summary['Ingresos USD'].sum(),amount)
                        with use_filter(selection([10010])):
                            args['keywords']=['Outside']
                            self.assertEqual(report.count_report_detail_rows(**args),0)


if __name__ == '__main__': unittest.main()
