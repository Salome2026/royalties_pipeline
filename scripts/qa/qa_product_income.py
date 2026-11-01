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

    def test_bounded_history_scan_preserves_native_rows_and_batch_boundary_assignments(self):
        from lib.product_income import _scan_income_bounded
        rows=[sale(asset_isrc='BK4DA2632806',amount_usd=10.),sale(amount_usd=-.09),
              sale(product_upc='123456789012',amount_usd=7.),sale(video_id='abcdefghijk'),sale(),
              sale(asset_isrc='BK4DA2632807',amount_usd=3.)]
        rows=[{**row,'opaque_distributor_field':f'native {n}'} for n,row in enumerate(rows)]
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'history.parquet';original=pl.DataFrame(rows);original.write_parquet(source)
            expected=allocate_income(original.lazy(),index()).collect()
            actual=_scan_income_bounded(source,index(),batch_size=2).collect()
            self.assertEqual(actual.columns,expected.columns)
            self.assertEqual(actual.to_dicts(),expected.to_dicts())
            self.assertAlmostEqual(actual['amount_usd'].sum(),original['amount_usd'].sum())
            self.assertAlmostEqual(actual['units'].sum(),original['units'].sum())

    def test_report_selection_preserves_order_amounts_and_destination_keyword_matches(self):
        from build_keyword_royalty_report import prepare_keyword_source,build_filter,SEARCH_COLUMNS_STANDARDIZED
        rows=[sale(asset_isrc='BK4DA2632806',amount_usd=10.),sale(amount_usd=-.09),
              sale(product_upc='123456789012',amount_usd=7.),sale(video_id='abcdefghijk'),sale()]
        rows=[{**row,'Product Quantity':'3','streams':3} for row in rows]
        with tempfile.TemporaryDirectory() as tmp,use_product_income(index()):
            source=Path(tmp)/'source.parquet';original=pl.DataFrame(rows);original.write_parquet(source)
            full=allocate_income(original.lazy()).collect()
            for n,(keywords,mode) in enumerate([(['La Juntada'],'any'),(['La Juntada','Tema 2'],'all'),(['absent'],'any')]):
                path=prepare_keyword_source(source,Path(tmp)/f'selected{n}.parquet',keywords,mode,batch_size=2)
                actual=pl.read_parquet(path)
                expected=full.filter(build_filter(set(full.columns),SEARCH_COLUMNS_STANDARDIZED,keywords,mode))
                self.assertEqual(actual.select(full.columns).to_dicts(),expected.to_dicts())
                self.assertAlmostEqual(actual['amount_usd'].sum(),expected['amount_usd'].sum())

    def test_report_selection_without_evidence_preserves_frozen_native_album(self):
        from build_keyword_royalty_report import prepare_keyword_source
        with tempfile.TemporaryDirectory() as tmp,use_product_income(None):
            source=Path(tmp)/'source.parquet';pl.DataFrame([sale()]).write_parquet(source)
            selected=prepare_keyword_source(source,Path(tmp)/'selected.parquet',['La Juntada'],'any',batch_size=1)
            actual=pl.read_parquet(selected)
            self.assertEqual(actual.height,1)
            self.assertIsNone(actual['asset_isrc'][0])
            self.assertAlmostEqual(actual['amount_usd'][0],1.89)
            self.assertNotIn('_income_origin_search',actual.columns)

    def test_distinct_value_search_preserves_accents_nulls_compaction_and_ada_scope(self):
        from build_keyword_royalty_report import filter_report_keyword_values,build_filter,SEARCH_COLUMNS_STANDARDIZED
        frame=pl.DataFrame([{'source':source,'track_statement_style':title,'artist_statement_style':artist,
            'catalog_number':'CÓDIGO_1','_income_origin_search':origin} for source,title,artist,origin in [
                ('ada','Tema-Feliz','Candú',None),('fuga','Otro tema','G Sony','La Juntada'),
                ('ada',None,None,None),('fuga','Tema-Feliz','Candú',None)]])
        for keywords in [['candu'],['tema feliz'],['CODIGO1'],['la juntada','g sony'],[''],[],['absent']]:
            for mode in ['all','any']:
                expected=frame.filter(build_filter(set(frame.columns),SEARCH_COLUMNS_STANDARDIZED,keywords,mode))
                self.assertTrue(filter_report_keyword_values(frame,keywords,mode).equals(expected),(keywords,mode))

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

    def test_request_pins_its_catalog_and_evidence_and_restores_outer_scope(self):
        from lib.product_income import FILE,use_product_income_marts,current_index
        from lib.catalog_report_filter import current_catalog_master_path
        from app.royalty_scope import use_scope,MARTS,RELEASE
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);evidence=root/FILE;evidence.write_text(json.dumps(index()))
            outer={'catalog_master.parquet':root/'outer.parquet'}
            with use_scope('regular',marts=outer,release_id='r1'):
                own={'catalog_master.parquet':root/'own.parquet',FILE:evidence}
                with use_product_income_marts(own):
                    self.assertEqual(current_catalog_master_path(),own['catalog_master.parquet'])
                    self.assertEqual(current_index(),index())
                    self.assertEqual(RELEASE.get(),'r1')
                with use_product_income_marts({'catalog_master.parquet':root/'old.parquet'}):
                    self.assertIsNone(current_index())
                self.assertEqual(MARTS.get(),outer)

    def test_summary_build_uses_source_catalog_even_if_another_request_changed_environment(self):
        from lib.product_income import FILE,use_product_income_source,current_index
        from lib.catalog_report_filter import current_catalog_master_path
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'standardized_raw_all_sources.parquet'
            pl.DataFrame([sale()]).write_parquet(source)
            catalog=root/'catalog_master.parquet';catalog.touch()
            (root/FILE).write_text(json.dumps(index()))
            with patch.dict(os.environ,{'VPO_CATALOG_MASTER_PATH':str(root/'other-release.parquet')}):
                with use_product_income_source(source):
                    self.assertEqual(current_catalog_master_path(),catalog)
                    self.assertEqual(current_index(),index())

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

    def test_pending_album_cannot_bypass_rule_through_old_unique_upc_alias(self):
        from app.master_contract_unidentified import unidentified_income
        from app.master_contract_income import consolidate_associated_income
        from app.royalty_reports.excel_contracts import reference_fragments,participant_columns
        from app.master_contract_associations import association_key
        from qa_excel_contracts import snapshot
        import build_keyword_royalty_report as report
        doc=index();doc['products']['UPC:08718521191726'].update(status='pending',tracks=[])
        row=sale(source='fuga',account='indy',product_type='Product')
        code='ARDL12600001'
        ev=[{'kind':'UPC','code':row['product_upc'],'source':'fuga','account':'indy','isrcs':[code],'titles':[],'artists':[]}]
        aliases={'UPC:'+row['product_upc']:'ISRC:'+code}
        with use_product_income(doc):
            result=unidentified_income([row],ev,[{'asset_isrc':code}],aliases,{})
            self.assertEqual(result['total'],1)
            self.assertEqual(consolidate_associated_income([row],ev,aliases,{},{},'2026-12'),{})
            frame=allocate_income(pl.DataFrame([row]).lazy())
            frame=report.add_report_code(frame,set(frame.collect_schema().names())).with_columns(pl.col('transaction_month').alias('period_month'))
            summary=report.build_track_summary_lf(frame,include_identity=True).collect()
            state=snapshot();state['associations']['included'][association_key('UPC',row['product_upc'],'fuga','indy')]=[code]
            _,values=participant_columns(summary,reference_fragments(frame),state,['La Juntada'],'all')
            self.assertTrue(all(value is None for value in values[0].values()))

    def test_product_without_upc_remains_pending_and_explicit_track_is_not_an_album(self):
        row=sale(source='fuga',account='indy',asset_product_type='Product',product_upc=None,catalog_number=None)
        out=allocate_income(pl.DataFrame([row]).lazy(),index()).collect()
        self.assertTrue(out['_income_product_pending'][0])
        self.assertIsNone(out['asset_isrc'][0])
        doc=index();doc['products']['UPC:08718521191726']['native_product_scopes']=['fuga||indy||ALBUM-1||La Juntada album']
        row=sale(source='fuga',account='indy',product_type='Track')
        out=allocate_income(pl.DataFrame([row]).lazy(),doc).collect()
        self.assertEqual(out.height,1);self.assertIsNone(out['asset_isrc'][0])

    def test_fact_retains_product_type_so_equal_titles_do_not_mix_album_and_track(self):
        from scripts.load_bigquery_release import build_detail
        from lib.product_income import allocate_income_rows
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'raw.parquet';target=root/'fact.parquet'
            rows=[sale(source='fuga',account='indy',asset_product_type=kind,release_statement_style='La Juntada album',amount_usd=amount)
                for kind,amount in [('Product',1.89),('Asset',2.)]]
            rows.append(sale(source='fuga',account='indy',asset_product_type='Product',product_type='Video',amount_usd=4.))
            pl.DataFrame(rows).write_parquet(source)
            build_detail(source,target,'release-test')
            fact=pl.read_parquet(target)
            self.assertEqual(set(fact['product_type']),{'Product','Asset','Video'})
            self.assertAlmostEqual(fact['amount_usd'].sum(),7.89)
            with use_product_income(index()):out=allocate_income_rows(fact.to_dicts())
            self.assertEqual(len(out),5)
            self.assertAlmostEqual(sum(r['amount_usd'] for r in out if not r['asset_isrc']),6.)

    def test_catalog_keeps_native_product_identity_even_with_one_observed_isrc(self):
        import build_catalog_master as catalog
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'raw.parquet'
            pl.DataFrame([sale(source='fuga',account='indy',asset_product_type='Product'),
                sale(source='fuga',account='indy',asset_product_type='Asset',asset_isrc='BK4DA2632806')]).write_parquet(source)
            with patch.object(catalog,'MARTS_DIR',root),patch.object(catalog,'STANDARDIZED_PATHS',[source]),use_product_income(index()):
                frame=catalog.identity_with_canonical_key().collect()
                product=frame.filter(pl.col('identity_native_product'))
                self.assertEqual(product.height,1)
                self.assertIsNone(product['effective_isrc'][0])
                self.assertTrue(product['catalog_key'][0].startswith('TEXT:'))

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

    def test_missing_ada_upc_uses_unique_native_product_binding_and_rejects_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'raw.parquet'
            rows=[sale(),sale(product_upc=None)]
            pl.DataFrame(rows).write_parquet(source)
            albums={'verified':{'id':'verified','total_tracks':3,'external_ids':{'upc':'8718521191726'},
                'tracks':{'total':3,'next':None,'items':[{'id':str(i),'name':f'Tema {i}','artists':[],
                    'external_ids':{'isrc':f'BK4DA263280{i}'}} for i in [6,7,8]]}}}
            doc=compile_index(source,albums=albums,tracks={})
            native='ADA:indyana_records:ALBUM-1'
            self.assertEqual(doc['products'][native]['status'],'validated')
            self.assertEqual(doc['products'][native]['resolved_upc'],'08718521191726')
            out=allocate_income(pl.DataFrame(rows).lazy(),doc).collect()
            self.assertEqual(out.height,6)
            self.assertEqual(out.filter(pl.col('product_upc').is_null()).height,3)
            self.assertAlmostEqual(out['amount_usd'].sum(),3.78)
            rows.append(sale(product_upc='123456789012'))
            pl.DataFrame(rows).write_parquet(source)
            changed=compile_index(source,albums=albums,tracks={},prior_index=doc)
            self.assertEqual(changed['products'][native]['status'],'pending')

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
            old=cache.ensure(['a.parquet'])
            self.assertNotIn(FILE,old)
            self.assertEqual(cache.release_id_for(old['a.parquet']),'r1')
            publish_mart_release(bucket,'marts',write_release_files(root,'r2')+[(FILE,evidence)],release_id='r2')
            result=cache.ensure(['a.parquet'])
            self.assertEqual(cache.release_id_for(old['a.parquet']),'r1')
            self.assertEqual(cache.release_id_for(result['a.parquet']),'r2')
            self.assertIn(FILE,result);self.assertIn('r2',str(result[FILE]))
            bucket.put('marts/'+FILE,b'corrupt canonical')
            self.assertEqual(json.loads(cache.ensure(['a.parquet'])[FILE].read_text()),index())
            publish_mart_release(bucket,'marts',write_release_files(root,'r3',corrupt_a=True)+[(FILE,evidence)],release_id='r3')
            fallback=cache.ensure(['a.parquet'])
            self.assertEqual(fallback[FILE],result[FILE]);self.assertEqual(cache.status()['active_release_id'],'r2')


if __name__=='__main__':unittest.main()
