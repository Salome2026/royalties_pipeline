"""Reconcile distributor/account filters across report summaries and detail."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import openpyxl
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.royalty_reports.builders import build_google_sheet, build_keyword_excel
from app.royalty_reports.contracts import ReportInputs, ReportRequest
from build_keyword_royalty_report import count_report_detail_rows
from lib.distributor_policy_store import use_distributor_policy_snapshot


class ReportSourceFilterTests(unittest.TestCase):
    def test_api_preserves_source_and_account_for_every_output(self):
        from app import vpo_corp_api as api
        from app.royalty_scope import use_scope
        from fastapi import HTTPException
        policy={'entries':[{'source':'fuga','account':'mawz'}]}
        for output in ('excel','google_sheet','executive_pdf'):
            with self.subTest(output=output),use_scope('regular'):
                params=api.canonical_royalty_report_params(api.RoyaltyReportJobRequest(
                    output=output,keywords=['tema'],source='FUGA',account='MAWZ'),policy)
                self.assertEqual((params['source'],params['account']),('fuga','mawz'))
                for source,account in [(None,'mawz'),('other',None),('fuga','other')]:
                    with self.assertRaises(HTTPException) as invalid:
                        api.canonical_royalty_report_params(api.RoyaltyReportJobRequest(
                            output=output,keywords=['tema'],source=source,account=account),policy)
                    self.assertEqual(invalid.exception.status_code,400)

    def test_distributor_and_account_filter_the_actual_outputs_and_count(self):
        rows = []
        for source, account, amount in [('fuga', 'mawz', 100.0), ('fuga', 'mawz', -10.0),
                                        ('fuga', 'indyana', 40.0), ('dashgo', 'mawz', 300.0)]:
            rows.append({
                'source': source, 'account': account, 'amount_usd': amount, 'units': 1.0,
                'statement_period': '2026-06', 'transaction_month': '2026-05',
                'artist_statement_style': 'Artista de prueba', 'track_statement_style': 'Tema compartido',
                'asset_isrc': 'USAAA2600001', 'territory': 'AR', 'store': 'spotify',
                'store_name': 'Spotify', 'usage_type': 'streaming', 'currency_original': 'USD',
                'statement_file_name': source + '.csv', 'source_sheet': 'royalty_detail', 'revenue_basis': 'generation',
            })
        policy = {'schema_version': 1, 'policy_version': 1,
                  'report_personalization': {'enabled': True},
                  'entries': [{'source': source, 'account': account, 'report_net_adjustment_pct': adjustment,
                               'sheet_rules': {'royalty_detail': {'catalog_view': True, 'statement_view': True,
                                                                 'cash_view': False, 'revenue_basis': 'generation'}}}
                              for source, account, adjustment in [('fuga', 'mawz', 10), ('fuga', 'indyana', 0), ('dashgo', 'mawz', 0)]]}
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            song = root / 'song.parquet'; detail = root / 'detail.parquet'
            pl.DataFrame(rows).write_parquet(song); pl.DataFrame(rows).write_parquet(detail)
            inputs = ReportInputs(song, detail, root / 'catalog.parquet', root / 'reports')
            with patch.dict(os.environ, {'VPO_CATALOG_MASTER_PATH': str(root / 'catalog.parquet'),
                                         'VPO_CATALOG_STATUS_PATH': str(root / 'status.parquet')}), \
                 use_distributor_policy_snapshot(policy):
                for basis in ('transaction_month', 'statement_period'):
                    for source, account, expected, count in [(None, None, 421.0, 4), ('fuga', None, 121.0, 3),
                                                              ('fuga', 'mawz', 81.0, 2), ('dashgo', 'mawz', 300.0, 1)]:
                        with self.subTest(basis=basis, source=source, account=account):
                            params = {'keywords': ['artista'], 'mode': 'any', 'raw_limit': 5000,
                                      'period_basis': basis, 'source': source, 'account': account}
                            request = ReportRequest.from_job({'id': 1, 'report_key': 'royalty_keyword',
                                'output_format': 'excel', 'params': params}, keywords=['artista'])
                            result = build_keyword_excel(request, inputs)
                            workbook = openpyxl.load_workbook(result.output_path, data_only=True)
                            try:
                                summary = list(workbook['resumen general'].values)
                                self.assertAlmostEqual(summary[1][summary[0].index('Ingresos USD')], expected)
                                detail_rows = list(workbook['detalle'].values)
                                self.assertEqual(len(detail_rows) - 1, count)
                                self.assertAlmostEqual(sum(row[detail_rows[0].index('Ingresos USD')] for row in detail_rows[1:]), expected)
                            finally:
                                workbook.close()
                            captured = []
                            sheet_request = ReportRequest.from_job({'id': 2, 'report_key': 'royalty_google_sheet',
                                'output_format': 'google_sheet', 'params': params}, keywords=['artista'])
                            build_google_sheet(sheet_request, inputs,
                                lambda tables, *_: captured.append(tables) or 'https://sheets.example/test')
                            tables = captured[0]
                            self.assertAlmostEqual(tables['resumen general']['Ingresos USD'].iloc[0], expected)
                            self.assertEqual(len(tables['detalle']), count)
                            self.assertAlmostEqual(tables['detalle']['Ingresos USD'].sum(), expected)
                            self.assertEqual(count_report_detail_rows(keywords=['artista'], mode='any',
                                start_month=None, end_month=None, period_basis=basis,
                                standardized_path=detail, source=source, account=account), count)


if __name__ == '__main__':
    unittest.main()
