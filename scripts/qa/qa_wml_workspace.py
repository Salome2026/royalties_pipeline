"""Financial and isolation regression checks for the optional WML workspace."""
from __future__ import annotations
import asyncio
import csv
import json
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.royalty_scope import use_scope,is_wml,MARTS,RELEASE,WML_FILES,wml_policy
from app.wml_workspace import expected_semester,monitor_item,local_release
from scripts.ingest_wml_workspace import standardize,discover,sha256,ingest

def sample(path: Path,rows: list[dict]):
    defaults={'Account':'91230','Start Period':'2026-01','End Period':'2026-06','Royalty Payable':'2.5',
        'Royalty Base':'1','Sale Units':'10','Royalty Rate':'25','Revenue Rate':'','Receipts':'','Share Tracks':'1',
        'Share Total Tracks':'1','Product Title':'FLEXIN','Artist Name':'Lit Killah','ISRC':'USWL12000001',
        'Product Type':'Track','Repdate Month ID':'2026-05','Recdate Month ID':'2026-06','Catalog Number':'123','GPID':'123456789012',
        'Country':'AR','Digital Service Provider(DSP)':'Spotify','Dist Chan Desc':'Streaming'}
    with path.open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=list(defaults),delimiter='\t');writer.writeheader()
        writer.writerows({**defaults,**r} for r in rows)

class WmlFinancialTests(unittest.TestCase):
    def test_line_bases_preserve_rates_receipts_proration_and_reversals(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'Statement_91230_1_91230_20260630.txt'
            sample(p,[{}, {'Royalty Rate':'48','Royalty Payable':'4.8'},
                {'Royalty Rate':'50','Royalty Payable':'1.25','Share Total Tracks':'4'},
                {'Royalty Base':'','Royalty Rate':'','Revenue Rate':'50','Receipts':'20','Royalty Payable':'10'},
                {'Royalty Base':'-1','Royalty Payable':'-2.5'}])
            frame,summary=standardize(p,sha256(p))
            self.assertEqual(frame['amount_usd'].to_list(),[10,10,2.5,20,-10])
            self.assertAlmostEqual(summary['warner_royalty_usd'],16.05)
            self.assertEqual(summary['amount_usd'],32.5)
            self.assertEqual(frame['include_in_cash_view'].unique().to_list(),[False])
            self.assertEqual(frame['account'].unique().to_list(),['91230'])
            self.assertEqual(frame['statement_semester'].unique().to_list(),['2026-H1'])
            self.assertEqual(frame['statement_row_number'].to_list(),[2,3,4,5,6])
            from app.wml_job import prepare_detail_batches
            raw=Path(d)/'raw.parquet';target=Path(d)/'detail.parquet';frame.write_parquet(raw)
            prepare_detail_batches(raw,target,'wml-'+'a'*24,batch_size=2)
            normalized=pl.read_parquet(target)
            self.assertEqual(normalized['amount_usd'].to_list(),[10,10,2.5,20,-10])
            self.assertEqual(normalized['statement_row_number'].to_list(),[2,3,4,5,6])

    def test_invalid_financial_input_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'Statement_91230_1_91230_20260630.txt'
            for bad in [{'Account':'91231'},{'Royalty Payable':'3'},{'Start Period':'2026-03'},
                        {'Royalty Rate':'0'},{'Royalty Base':''},{'Receipts':'10'},{'Share Total Tracks':'0'}]:
                sample(p,[bad])
                with self.subTest(bad=bad),self.assertRaises((ValueError,pl.exceptions.PolarsError)):
                    standardize(p,sha256(p))

    def test_same_semester_duplicates_and_corrections(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'Statement_91230_1_91230_20260630.txt';sample(p,[{}])
            other=root/'Statement_91230_2_91230_20260630.txt';other.write_bytes(p.read_bytes())
            sample(root/'Statement_91231_1_91231_20260630.txt',[{'Account':'91231'}])
            files,ignored=discover(root)
            self.assertEqual(len(files),1);self.assertEqual(len(ignored),2)
            sample(other,[{'Product Title':'Corrected'}])
            with self.assertRaisesRegex(ValueError,'Dos versiones'):discover(root)

    def test_repeated_ingest_keeps_immutable_files_and_advisory_references(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inputs=root/'inputs';inputs.mkdir();sample(inputs/'Statement_91230_1_91230_20260630.txt',[{}])
            first=ingest(inputs,root/'output');folder=root/'output/releases'/first['release_id']
            before={n:(folder/n).stat().st_mtime_ns for n in WML_FILES}
            second=ingest(inputs,root/'output')
            self.assertTrue(second['reused']);self.assertEqual(first['release_id'],second['release_id'])
            self.assertEqual(before,{n:(folder/n).stat().st_mtime_ns for n in WML_FILES})
            refs=pl.read_parquet(folder/'wml_isrc_references.parquet')
            self.assertFalse(refs['applies_automatically'].any())
            self.assertEqual(set(refs['evidence_status']),{'informed','deduced'})
            with use_scope('wml',marts={n:folder/n for n in WML_FILES}):
                from app.wml_job import prepare_bigquery
                prepared=prepare_bigquery(folder,root/'bq',first['release_id'])
                detail=pl.read_parquet(prepared['detail'])
                self.assertEqual(detail['amount_usd'].sum(),10)
                self.assertEqual(detail['wml_reported_royalty_usd'].sum(),2.5)
                self.assertEqual(detail['gpid'].to_list(),['123456789012'])
                from scripts.build_keyword_royalty_report import build_report_tables
                tables=build_report_tables(keywords=['FLEXIN'],mode='any',song_path=folder/'song_level_all_sources.parquet',
                    standardized_path=folder/'standardized_raw_all_sources.parquet',raw_limit=0)
                self.assertIn('referencias WML',tables)
                self.assertFalse(tables['referencias WML'].empty)
                self.assertAlmostEqual(float(tables['resumen general']['Ingresos USD'].iloc[0]),10)
                statement=build_report_tables(keywords=['FLEXIN'],mode='any',period_basis='statement_period',
                    song_path=folder/'song_level_all_sources.parquet',standardized_path=folder/'standardized_raw_all_sources.parquet',raw_limit=0)
                self.assertFalse(statement['referencias WML'].empty)
                self.assertAlmostEqual(float(statement['resumen general']['Ingresos USD'].iloc[0]),10)

    def test_real_release_financial_totals_and_rates(self):
        release=local_release()
        if not release:self.skipTest('Sin datos WML locales')
        manifest,folder=release
        self.assertEqual(manifest['rows'],3865402)
        self.assertEqual(len(manifest['semesters']),10)
        self.assertAlmostEqual(manifest['amount_usd'],3846332.7695696163,places=6)
        self.assertAlmostEqual(manifest['warner_royalty_usd'],977028.66356013,places=6)
        detail=pl.scan_parquet(folder/'standardized_raw_all_sources.parquet')
        result=detail.select(pl.col('account').n_unique().alias('accounts'),pl.col('account').first().alias('account'),
            (pl.col('amount_usd')*pl.col('wml_royalty_rate_pct')/100-pl.col('wml_reported_royalty_usd')).abs().max().alias('error'),
            pl.col('movement_id').n_unique().alias('movements')).collect().row(0,named=True)
        self.assertEqual(result['account'],'91230');self.assertEqual(result['accounts'],1)
        self.assertLessEqual(result['error'],1e-6);self.assertEqual(result['movements'],manifest['rows'])
        refs=pl.read_parquet(folder/'wml_isrc_references.parquet')
        self.assertFalse(refs['applies_automatically'].any())
        self.assertEqual(set(refs['evidence_status']),{'informed','deduced','hypothesis'})
        self.assertIn(8.333,refs['percent'].to_list())
        for r in refs.filter(pl.col('evidence_status')!='informed').to_dicts():
            self.assertEqual(r['reference_scope'],'song_family_pending_asset_confirmation')

class WmlIsolationTests(unittest.TestCase):
    def test_bigquery_dataset_and_release_are_isolated_from_catalog_refresh(self):
        from app import vpo_corp_api as api
        from app import bigquery_dashboard as bq
        from contextlib import nullcontext
        release='wml-'+'a'*24
        with use_scope('wml',release_id=release),patch('app.catalog_refresh.enabled',return_value=True),\
             patch('app.catalog_refresh.dashboard_state',side_effect=AssertionError('No leer catálogo habitual')),\
             patch.object(api,'query_royalties_dashboard_bigquery',return_value={}) as dashboard:
            api.query_royalties_dashboard_from_bigquery(source=None,account=None,keyword=None,artist_keyword=None,
                start_month=None,end_month=None,period_basis='statement_period',period_mode='all',limit=10)
            self.assertEqual(dashboard.call_args.kwargs['dataset'],'royalties_wml')
            self.assertIsNone(dashboard.call_args.kwargs['catalog_state'])
            with patch.object(api,'require_api_key'),patch.object(api,'require_module_permission'),\
                 patch.object(api,'operational_connect',return_value=nullcontext(None)),\
                 patch.object(api,'query_royalty_detail_count_bigquery',return_value=1) as count:
                api.royalty_report_detail_count(api.RoyaltyReportJobRequest(keywords=['FLEXIN']),x_vpo_username='tester')
                self.assertEqual(count.call_args.kwargs['dataset'],'royalties_wml')
            fake=SimpleNamespace(query=lambda *a,**kw:SimpleNamespace(result=lambda:iter([{'release_id':release}])))
            with patch.object(bq,'query_rows',return_value=[]) as rows:
                bq.royalties_dashboard_bigquery(policy_document=wml_policy(),project='test-project',dataset='royalties_wml',
                    client=fake,catalog_state={'ready':{'release_id':'ordinary-catalog-release'}})
                self.assertEqual(rows.call_args.kwargs['release_id'],release)
                self.assertNotIn('royalty_catalog_dashboard',rows.call_args.kwargs['sql'])
            self.assertIn(release,bq.scoped_rankings_table('test-project','royalties_wml'))

    def test_concurrent_scopes_never_leak(self):
        def read(scope):
            with use_scope(scope,marts={'sample':Path(scope)},release_id='wml-'+'a'*24):
                return (is_wml(),str(MARTS.get()['sample']),RELEASE.get())
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(read,['regular','wml']*30))
        for index,item in enumerate(results):self.assertEqual(item[0],bool(index%2));self.assertEqual(item[1],['regular','wml'][index%2])
        self.assertFalse(is_wml());self.assertEqual(MARTS.get(),{});self.assertIsNone(RELEASE.get())

    def test_semiannual_due_dates_and_gaps(self):
        self.assertEqual(expected_semester(date(2026,9,29),3),'2025-12')
        self.assertEqual(expected_semester(date(2026,9,30),3),'2026-06')
        self.assertEqual(expected_semester(date(2026,12,31),0),'2026-12')
        state={'enabled':False,'installed':True,'version':1,'config':{'delivery_lag_months':3}}
        self.assertEqual(monitor_item(state,today=date(2026,10,24))['status'],'inactive')
        state['enabled']=True
        summary={'semesters':[{'statement_period':p,'rows':1} for p in ['2025-06','2026-06']]}
        item=monitor_item(state,summary,today=date(2026,10,24))
        self.assertEqual(item['missing_semesters'],['2025-12']);self.assertTrue(item['alert'])
        state['config'].update(published_release_id='wml-'+'a'*24,semesters=[{'statement_period':'2026-06','rows':2}],rows=2)
        published=monitor_item(state,{'semesters':[{'statement_period':'2025-12','rows':1}]},today=date(2026,10,24))
        self.assertEqual(published['last_statement_period'],'2026-06');self.assertFalse(published['alert'])

    def test_regular_local_marts_do_not_choose_wml_data(self):
        from app.wml_workspace import resolve_marts
        expected={'catalog_master.parquet':Path('published/catalog_master.parquet')}
        with use_scope('wml',release_id='wml-'+'a'*24),patch.dict(os.environ,{'VPO_WML_LOCAL_ROOT':''}),\
             patch('app.wml_workspace.release_cache') as cache,patch('app.wml_workspace.local_release') as local:
            cache.return_value.ensure.return_value=expected
            actual=resolve_marts(list(expected),bucket='test',client_factory=lambda:None,cache_dir=Path('cache'),local_mode=True)
            self.assertEqual(actual,expected);local.assert_not_called()

    def test_api_gate_and_missing_data_never_fall_back(self):
        from app.wml_api import install
        from contextlib import nullcontext
        fake=SimpleNamespace(app=FastAPI(),BASE=ROOT,operational_connect=lambda:nullcontext(None),
            require_module_permission=lambda *a:{'allowed':True,'scope':None},user_module_permission=lambda *a:{'allowed':True},
            require_api_key=lambda key:None)
        calls=[]
        def marts(*args,**kwargs):calls.append(is_wml());return {}
        fake.ensure_marts=marts
        @fake.app.get('/catalog')
        def catalog():return {'scope':'wml' if is_wml() else 'regular'}
        install(fake);client=TestClient(fake.app)
        state={'enabled':False,'installed':True,'version':1,'config':{'published_release_id':'wml-'+'a'*24}}
        headers={'X-VPO-Royalty-Scope':'wml','X-VPO-Username':'tester'}
        with patch('app.wml_api.settings',return_value=state),patch('app.royalty_workspace_store.records',return_value={}):
            self.assertEqual(client.get('/catalog',headers=headers).status_code,409)
            self.assertEqual(client.get('/catalog').json()['scope'],'regular');self.assertEqual(calls,[])
            state['enabled']=True
            self.assertEqual(client.get('/catalog',headers=headers).json()['scope'],'wml');self.assertEqual(calls,[True])
            self.assertEqual(client.get('/catalog').json()['scope'],'regular')
            fake.ensure_marts=lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('Datos WML ausentes'))
            self.assertEqual(client.get('/catalog',headers=headers).status_code,503)
            self.assertEqual(client.get('/catalog').json()['scope'],'regular')
            self.assertEqual(client.get('/health',headers=headers).status_code,400)
            self.assertEqual(client.get('/catalog',headers={'X-VPO-Royalty-Scope':'other'}).status_code,400)

    def test_processing_same_release_does_not_launch_or_write(self):
        from app.wml_cloud import launch_processing
        from scripts.ingest_wml_workspace import input_fingerprint
        files=[{'file':'Statement_91230_1_91230_20260630.txt','sha256':'a'*64}]
        fingerprint=input_fingerprint(files,[]);state={'installed':True,'config':{'published_release_id':'wml-'+fingerprint[:24]}}
        document={'fingerprint':fingerprint};fake=SimpleNamespace(bucket=lambda name:SimpleNamespace(
            blob=lambda name:SimpleNamespace(download_as_text=lambda:'{}')))
        with patch.dict(os.environ,{'VPO_WML_JOB_NAME':'wml-test','VPO_WML_JOB_PROJECT':'project-test','VPO_WML_JOB_LOCATION':'us-central1'}),\
             patch('app.wml_cloud.settings',return_value=state),patch('app.wml_cloud.stage_inputs',return_value={}),\
             patch('app.wml_cloud.input_manifest',return_value=document),patch('app.wml_cloud.merge_config') as save,\
             patch('google.auth.transport.requests.AuthorizedSession') as cloud:
            result=launch_processing(client_factory=lambda:fake,bucket_name='test',actor='test')
            self.assertTrue(result['reused']);save.assert_not_called();cloud.assert_not_called()

if __name__=='__main__':unittest.main()
