from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest
import json
import os
from unittest.mock import patch

import polars as pl

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'scripts/qa'))
from lib.product_income import RULE, allocate_income, compile_index, use_product_income,align_catalog_income,allocation_cache_matches,validate_index


def index(tracks=3):
    return {'schema_version':1,'scope':'regular','rule':RULE,'products':{'UPC:08718521191726':{
        'status':'validated','tracks':[{'position':i,'isrc':f'BK4DA263280{5+i}',
            'title':f'Tema {i}','artist':f'Artista {i}'} for i in range(1,tracks+1)]}}}


def sale(**extra):
    return {'source':'ada','account':'indyana_records','source_sheet':'royalty_detail','revenue_basis':'generation',
        'product_upc':'8718521191726','asset_isrc':None,'catalog_number':'ALBUM-1',
        'track_statement_style':'La Juntada album','release_statement_style':'La Juntada album',
        'artist_statement_style':'La Juntada','amount_usd':1.89,'units':1.,'statement_period':'2026-08',
        'transaction_month':'2026-05',**extra}


class AllocationTests(unittest.TestCase):
    def test_conserves_money_units_and_negative_adjustments(self):
        frame=pl.DataFrame([sale(),sale(amount_usd=-.09,units=-1.)])
        out=allocate_income(frame.lazy(),index()).collect()
        self.assertEqual(out.height,6)
        self.assertAlmostEqual(out['amount_usd'].sum(),1.8)
        self.assertAlmostEqual(out['units'].sum(),0)
        self.assertEqual(set(out['statement_period']),{'2026-08'})
        self.assertEqual(set(out['catalog_number']),{'ALBUM-1'})
        self.assertEqual(set(out['asset_isrc']),{'BK4DA2632806','BK4DA2632807','BK4DA2632808'})

    def test_identified_tracks_video_transfers_and_source_shares_are_never_resplit(self):
        rows=[sale(asset_isrc='BK4DA2632806'),sale(video_id='abcdefghijk'),
              sale(revenue_basis='transfer'),sale(**{'Share Total Tracks':'7'})]
        out=allocate_income(pl.DataFrame(rows).lazy(),index()).collect()
        self.assertEqual(out.height,4)
        self.assertAlmostEqual(out['amount_usd'].sum(),7.56)

    def test_unknown_product_is_preserved_and_application_is_idempotent(self):
        rows=pl.DataFrame([sale(),sale(product_upc='123456789012')])
        first=allocate_income(rows.lazy(),index())
        a=first.collect();b=allocate_income(first,index()).collect()
        self.assertTrue(a.equals(b))
        self.assertEqual(a.height,4)
        self.assertEqual(a.filter(pl.col('asset_isrc').is_null()).height,1)

    def test_multiple_positions_of_same_recording_use_positions_not_distinct_isrcs(self):
        doc=index();doc['products']['UPC:08718521191726']['tracks'][1]['isrc']='BK4DA2632806'
        out=allocate_income(pl.DataFrame([sale()]).lazy(),doc).collect()
        amounts=out.group_by('asset_isrc').agg(pl.col('amount_usd').sum())
        self.assertAlmostEqual(amounts.filter(pl.col('asset_isrc')=='BK4DA2632806')['amount_usd'][0],1.26)

    def test_keyword_keeps_original_album_matches_and_target_isrc(self):
        from build_keyword_royalty_report import build_filter,SEARCH_COLUMNS_STANDARDIZED
        out=allocate_income(pl.DataFrame([sale()]).lazy(),index())
        cols=set(out.collect_schema().names())
        self.assertEqual(out.filter(build_filter(cols,SEARCH_COLUMNS_STANDARDIZED,['La Juntada'],'all')).collect().height,3)
        self.assertEqual(out.filter(build_filter(cols,SEARCH_COLUMNS_STANDARDIZED,['BK4DA2632807'],'any')).collect().height,1)
        self.assertEqual(out.filter(build_filter(cols,SEARCH_COLUMNS_STANDARDIZED,['La Juntada','Tema 2'],'all')).collect().height,1)

    def test_no_contract_state_is_required(self):
        row=sale()
        self.assertNotIn('is_closed',row)
        self.assertEqual(allocate_income(pl.DataFrame([row]).lazy(),index()).collect().height,3)

    def test_partial_and_conflicting_composition_stays_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'raw.parquet';pl.DataFrame([sale()]).write_parquet(path)
            albums={'a':{'id':'a','external_ids':{'upc':'8718521191726'},'total_tracks':3,
                'tracks':{'total':3,'next':None,'items':[{'id':'one'},{'id':'two'}]}}}
            doc=compile_index(path,albums=albums,tracks={})
            self.assertEqual(doc['products']['UPC:08718521191726']['status'],'pending')

    def test_old_frozen_release_does_not_use_new_local_evidence(self):
        with use_product_income(None):
            frame=pl.DataFrame([sale()]).lazy()
            self.assertTrue(allocate_income(frame).collect().equals(frame.collect()))

    def test_thin_published_rows_use_exact_native_product_scope(self):
        doc=index();doc['products']['UPC:08718521191726']['native_product_scopes']=['ada||indyana_records||ALBUM-1||La Juntada album']
        row=sale();row['title']=row.pop('track_statement_style');row.pop('release_statement_style')
        out=allocate_income(pl.DataFrame([row]).lazy(),doc).collect()
        self.assertEqual(out.height,3)
        from app.master_contract_unidentified import unidentified_income
        from app.master_contract_income import consolidate_associated_income
        with use_product_income(doc):
            result=unidentified_income([row],[],[],{},{})
            self.assertEqual(result['total'],0)
            self.assertEqual(consolidate_associated_income([row],[],{},{},{},'2026-09'),{})
            row['product_upc']='123456789012'
            self.assertEqual(unidentified_income([row],[],[],{},{})['total'],1)

    def test_multi_track_upc_without_native_product_evidence_remains_visible(self):
        row=sale(track_statement_style='Unidentified track',release_statement_style=None)
        out=allocate_income(pl.DataFrame([row]).lazy(),index()).collect()
        self.assertEqual(out.height,1)
        self.assertIsNone(out['asset_isrc'][0])

    def test_source_scope_and_corrupted_evidence_fail_closed(self):
        doc=index();doc['scope']='wml'
        with self.assertRaises(ValueError):allocate_income(pl.DataFrame([sale()]).lazy(),doc)
        doc=index();doc['evidence_hash']='incorrect'
        with self.assertRaises(ValueError):validate_index(doc)

    def test_complete_conflicting_and_new_upcs_are_compiled_from_evidence(self):
        def album(code):return {'id':code,'total_tracks':1,'external_ids':{'upc':'8718521191726'},
            'tracks':{'items':[{'id':code,'external_ids':{'isrc':code},'name':code,'artists':[]}],'total':1,'next':None}}
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'raw.parquet';pl.DataFrame([sale()]).write_parquet(source)
            albums={'a':album('BK4DA2632806')}
            self.assertEqual(compile_index(source,albums=albums,tracks={})['products']['UPC:08718521191726']['status'],'validated')
            albums['b']=album('BK4DA2632807')
            self.assertEqual(compile_index(source,albums=albums,tracks={})['products']['UPC:08718521191726']['reason'],'contradictory_composition')
            pl.DataFrame([sale(product_upc='123456789012')]).write_parquet(source)
            self.assertEqual(compile_index(source,albums=albums,tracks={})['products']['UPC:00123456789012']['status'],'pending')

    def test_new_ingest_reuses_frozen_proof_but_new_contradictions_stay_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'raw.parquet';pl.DataFrame([sale()]).write_parquet(source)
            prior=index();prior['products']['UPC:08718521191726']['evidence']=[{'album_id':'verified','track_count':3}]
            doc=compile_index(source,albums={},tracks={},prior_index=prior)
            self.assertEqual(doc['products']['UPC:08718521191726']['status'],'validated')
            pl.DataFrame([sale(),sale(asset_isrc='XXAAA2600001')]).write_parquet(source)
            doc=compile_index(source,albums={},tracks={},prior_index=prior)
            self.assertEqual(doc['products']['UPC:08718521191726']['reason'],'contradictory_composition')

    def test_catalog_preserves_native_records_and_only_transfers_money(self):
        from lib.distributor_policy_store import use_distributor_policy_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'raw.parquet';pl.DataFrame([sale()]).write_parquet(source)
            cat=pl.DataFrame([{'catalog_key':'ADA:99500:CATALOG:ALBUM-1','asset_isrc':None,'amount_usd':1.89,'units':1.},
                {'catalog_key':'ISRC:XXAAA2600001','asset_isrc':'XXAAA2600001','amount_usd':10.,'units':7.}])
            policy={'schema_version':1,'policy_version':1,'entries':[{'source':'ada','account':'indyana_records',
                'sheet_rules':{'royalty_detail':{'catalog_view':True,'revenue_basis':'generation'}}}]}
            with use_distributor_policy_snapshot(policy):
                out=align_catalog_income(cat,source,index())
                self.assertTrue(out.equals(align_catalog_income(out,source,index())))
            self.assertTrue(set(cat['catalog_key']).issubset(set(out['catalog_key'])))
            self.assertAlmostEqual(out['amount_usd'].sum(),11.89)
            self.assertAlmostEqual(out['units'].sum(),8.)
            self.assertAlmostEqual(out.filter(pl.col('catalog_key')=='ADA:99500:CATALOG:ALBUM-1')['amount_usd'][0],0.)
            self.assertAlmostEqual(out.filter(pl.col('asset_isrc')=='XXAAA2600001')['amount_usd'][0],10.)

    def test_cache_changes_with_evidence_and_with_removal_of_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            stamp=Path(tmp)/'stamp.json'
            self.assertTrue(allocation_cache_matches(stamp,None))
            self.assertFalse(allocation_cache_matches(stamp,{'evidence_hash':'a'}))
            stamp.write_text(json.dumps({'evidence_hash':'a'}))
            self.assertTrue(allocation_cache_matches(stamp,{'evidence_hash':'a'}))
            self.assertFalse(allocation_cache_matches(stamp,None))
            self.assertFalse(allocation_cache_matches(stamp,{'evidence_hash':'b'}))

    def test_excel_bases_formats_and_sheets_with_and_without_contracts(self):
        import openpyxl
        from qa_excel_contracts import snapshot,row
        import build_keyword_royalty_report as report
        from lib.distributor_policy_store import use_distributor_policy_snapshot
        doc=index()
        for pos,t in enumerate(doc['products']['UPC:08718521191726']['tracks'],1):t['isrc']=f'ARDL1260000{pos}'
        policy={'schema_version':1,'policy_version':1,'entries':[{'source':'fuga','account':'indy',
            'sheet_rules':{'royalty_detail':{'catalog_view':True,'statement_view':True,'revenue_basis':'generation'}}}]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'raw.parquet'
            pl.DataFrame([row(asset_isrc=None,product_upc='8718521191726',track_statement_style='La Juntada',
                artist_statement_style='La Juntada',asset_product_type='Product',amount_usd=9.,units=1.,
                dsp_normalized='Spotify',monetization_normalized='Premium',content_origin_normalized='Audio / Master',
                classification_status='classified')]).write_parquet(source)
            with patch.dict(os.environ,{'VPO_CATALOG_MASTER_PATH':str(root/'missing.parquet'),'VPO_CATALOG_STATUS_PATH':str(root/'missing-status.parquet')}),use_distributor_policy_snapshot(policy),use_product_income(doc):
                for basis in ['statement_period','transaction_month']:
                    args=dict(keywords=['La Juntada'],mode='any',raw_limit=10,period_basis=basis,song_path=source,standardized_path=source)
                    a=report.build_report(**args,output_dir=root/(basis+'-plain'))
                    b=report.build_report(**args,output_dir=root/(basis+'-contract'),contract_snapshot=snapshot())
                    wa=openpyxl.load_workbook(a);wb=openpyxl.load_workbook(b)
                    self.assertEqual(wa.sheetnames,wb.sheetnames)
                    self.assertEqual(wa['resumen por tema'].max_row,4)
                    for sheet in wa:
                        other=wb[sheet.title];self.assertEqual(sheet.max_row,other.max_row)
                        if sheet.title=='resumen general':continue
                        rows=list(sheet.values);other_rows=[r[:sheet.max_column] for r in other.values]
                        self.assertEqual(sorted(rows[1:],key=str),sorted(other_rows[1:],key=str))
                        for arow in sheet:
                            for cell in arow:self.assertEqual(cell.number_format,other[cell.coordinate].number_format)
                    wa.close();wb.close()

    def test_dashboard_and_digital_income_share_the_assignment(self):
        from app import vpo_corp_api as api
        from qa_excel_contracts import row
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'raw.parquet'
            record=row(asset_isrc=None,product_upc='8718521191726',track_statement_style='La Juntada',
                asset_product_type='Product',amount_usd=9.,units=1.,dsp_normalized='Spotify',
                monetization_normalized='Download',content_origin_normalized='Audio / Master',classification_status='classified')
            record['store_report_label']='Spotify'
            pl.DataFrame([record]).write_parquet(source)
            policy={'entries':[{'source':'fuga','account':'indy','sheet_rules':{'royalty_detail':{
                'catalog_view':True,'statement_view':True,'revenue_basis':'generation'}}}]}
            with use_product_income(index()),patch.dict(os.environ,{'VPO_CATALOG_MASTER_PATH':str(root/'missing.parquet'),
                'VPO_CATALOG_STATUS_PATH':str(root/'missing-status.parquet')}), \
                patch('lib.catalog_report_filter.load_distributor_policy_document',return_value=policy), \
                patch('scripts.lib.catalog_report_filter.load_distributor_policy_document',return_value=policy), \
                patch.object(api,'DIGITAL_INCOME_SUMMARY_PATH',root/'digital.parquet'):
                path=api.build_royalties_dashboard_summary_mart(source,refresh_cache=True,output_path=root/'dashboard.parquet',partition_large_input=False)
                dashboard=pl.read_parquet(path)
                self.assertEqual(dashboard['isrc'].n_unique(),3)
                self.assertAlmostEqual(dashboard['amount_usd'].sum(),9.)
                self.assertAlmostEqual(dashboard['units'].sum(),1.)
                self.assertTrue(all('la juntada' in text for text in dashboard['search_text']))
                digital=pl.read_parquet(api.build_digital_income_summary_mart(source,True))
                self.assertAlmostEqual(digital['total_usd'].sum(),9.)
                self.assertEqual(digital['title'].n_unique(),3)

    def test_optional_evidence_is_pinned_and_old_release_never_uses_canonical_map(self):
        from qa_mart_release_cache import FakeBucket,FakeClient,FILES,write_release_files,validate_test_parquet
        from scripts.lib.mart_release import publish_mart_release
        from scripts.lib.mart_release_cache import MartReleaseCache
        from lib.product_income import FILE
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bucket=FakeBucket();client=FakeClient(bucket)
            evidence=root/FILE;evidence.write_text(json.dumps(index()))
            publish_mart_release(bucket,'marts',write_release_files(root,'r1'),release_id='r1')
            bucket.put('marts/'+FILE,evidence.read_bytes())
            def validate(path):
                if path.name==FILE:validate_index(json.loads(path.read_text()))
                else:validate_test_parquet(path)
            cache=MartReleaseCache(cache_dir=root/'cache',bucket_name='bucket',prefix='marts',required_files=FILES,
                optional_release_files=[FILE],client_factory=lambda:client,validator=validate,check_interval_seconds=0)
            self.assertNotIn(FILE,cache.ensure(['a.parquet']))
            publish_mart_release(bucket,'marts',write_release_files(root,'r2')+[(FILE,evidence)],release_id='r2')
            result=cache.ensure(['a.parquet'])
            self.assertIn(FILE,result);self.assertIn('r2',str(result[FILE]))
            bucket.put('marts/'+FILE,b'corrupt canonical')
            self.assertEqual(json.loads(cache.ensure(['a.parquet'])[FILE].read_text()),index())
            publish_mart_release(bucket,'marts',write_release_files(root,'r3',corrupt_a=True)+[(FILE,evidence)],release_id='r3')
            fallback=cache.ensure(['a.parquet'])
            self.assertEqual(fallback[FILE],result[FILE]);self.assertEqual(cache.status()['active_release_id'],'r2')


if __name__=='__main__':unittest.main()
