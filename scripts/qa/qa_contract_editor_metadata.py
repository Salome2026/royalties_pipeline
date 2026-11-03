"""Contracts may read metadata without running any income calculation."""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import polars as pl
from fastapi import HTTPException
from app import vpo_corp_api as api
from app.master_contract_editor_metadata import metadata_catalog, statement_dates

ISRC='ARDL12600097'
class ContractEditorMetadataTests(unittest.TestCase):
    def test_dates_read_all_platforms_without_amount_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'dates.parquet'
            pl.DataFrame({'isrc':[ISRC,ISRC,ISRC,'OTHER'],'statement_period':['2026-09','2026-02','2026-10','2026-01']}).write_parquet(path)
            dates=statement_dates(str(path),path.stat().st_mtime_ns)
            cat=pl.DataFrame({'asset_isrc':[ISRC,'CLEM42100943'],'track_title':['Ticket','External'],'amount_usd':[987.,0.], 'catalog_artists':[['A'],['B']]})
            result=metadata_catalog(cat,dates)
            self.assertEqual(result.filter(pl.col('asset_isrc')==ISRC)['_contract_first_statement_month'][0],'2026-02')
            self.assertEqual(result.filter(pl.col('asset_isrc')==ISRC)['_contract_last_statement_month'][0],'2026-10')
            self.assertEqual(result.height,2)
            self.assertEqual(cat['amount_usd'].to_list(),[987.,0.])
            self.assertEqual(result['amount_usd'].sum(),0)
            self.assertEqual(result['catalog_artists'].to_list(),[['A'],['B']])

    def fixtures(self, stack):
        catalog=pl.DataFrame({'asset_isrc':[ISRC],'track_title':['Ticket'],'artist_statement':['Artist'],'artist_variants':['Artist'],'catalog_artists':[['Artist']], 'catalog_artist_evidence':['[]'], 'amount_usd':[0.], 'isrc_amount_usd':[0.], 'associated_amount_usd':[0.], '_contract_first_statement_month':['2026-07'],'_contract_last_statement_month':['2026-10'], 'sources':['fuga'],'accounts':['indyana_records']})
        saved={'split':{'principal':'Artist','participants':[],'agreements':[]},'closed':True,'future_reports_selected':True,'version':6,'updated_by':'owner','updated_at':'now'}
        values={'require_api_key':None,'require_master_contract_user':'reader','read_split':saved,'active_artist_contracts':{},'read_contract_association_choices':{},'read_association_review_states':{},'master_contract_catalog':catalog,'is_wml':False}
        mocks={name:stack.enter_context(patch.object(api,name,return_value=value)) for name,value in values.items()}
        stack.enter_context(patch.object(api,'operational_connect')).return_value.__enter__.return_value=MagicMock()
        stack.enter_context(patch('app.master_contract_participants.propose_participants',return_value=(saved['split'],None)))
        for name in ['master_contract_income_baseline','master_contract_associated_income','master_contract_statement_income','ensure_marts']:
            mocks[name]=stack.enter_context(patch.object(api,name,side_effect=AssertionError('Unexpected financial/raw read: '+name)))
        return mocks,saved

    def test_get_metadata_keeps_contract_and_dates_without_financial_or_raw_reads(self):
        with ExitStack() as stack:
            mocks,saved=self.fixtures(stack)
            result=api.get_master_contract(ISRC,'key','reader',include_income=False)
            self.assertEqual(result['split'],saved['split'])
            self.assertTrue(result['closed']);self.assertTrue(result['future_reports_selected'])
            self.assertFalse(result['income_included'])
            self.assertEqual(result['first_statement_date'],'2026-07-01')
            self.assertEqual(result['statement_income'],[])
            mocks['master_contract_catalog'].assert_called_once_with({},include_income=False)
            mocks['require_master_contract_user'].assert_called_once_with(unittest.mock.ANY,'reader','access')

    def test_get_metadata_never_bypasses_contract_permission(self):
        with ExitStack() as stack:
            mocks,_=self.fixtures(stack)
            mocks['require_master_contract_user'].side_effect=HTTPException(403,'Access denied')
            with self.assertRaises(HTTPException) as error:api.get_master_contract(ISRC,'key','dashboard-only',include_income=False)
            self.assertEqual(error.exception.status_code,403)
            mocks['master_contract_catalog'].assert_not_called()

    def test_list_metadata_still_filters_and_reports_contract_states(self):
        with ExitStack() as stack:
            mocks,_=self.fixtures(stack)
            stack.enter_context(patch.object(api,'read_split_statuses',return_value={ISRC:{'closed':True,'future_reports_selected':True,'version':6}}))
            stack.enter_context(patch.object(api,'master_contract_source_accounts',return_value=pl.DataFrame({'asset_isrc':[ISRC],'source':['fuga'],'account':['indyana_records']})))
            result=api.list_master_contracts(keyword='Ticket',status='closed',source='fuga',account='indyana_records',x_vpo_api_key='key',x_vpo_username='reader',include_income=False)
            self.assertEqual(result['total'],1)
            self.assertTrue(result['items'][0]['closed'])
            self.assertFalse(result['income_included'])
            mocks['master_contract_associated_income'].assert_not_called()

if __name__=='__main__':unittest.main()
