import unittest
from contextlib import contextmanager
from unittest.mock import patch,Mock
import polars as pl
from fastapi import HTTPException
from app import catalog_metadata_review as m

class MetadataTests(unittest.TestCase):
 def row(self):return {'catalog_key':'ISRC:ARDL12600005','asset_isrc':'ARDL12600005','track_title':'Tema','catalog_artists':['Lead'],'amount_usd':123.45,'catalog_duration_seconds':100}
 def obs(self):return {'payload_json':{'status':'found','exact_isrc':True,'artists':['Lead','Guest'],'track_title':'Tema nuevo'},'version':3}
 def test_album_artists_never_become_track_artists(self):
  p=m.observation_from_cache({'raw_json':{'selected':{'name':'Song','external_ids':{'isrc':'ARDL12600005'},'artists':[{'name':'Track'}],'album':{'artists':[{'name':'Album Guest'}]}}}},'ARDL12600005')
  self.assertEqual(p['artists'],['Track']);self.assertEqual(p['album_artists'],['Album Guest']);self.assertTrue(p['exact_isrc'])
 def test_found_is_not_human_approval(self):
  c=m.comparison(self.row(),self.obs());self.assertEqual(c['status'],'pending');self.assertFalse(c['reviewed_by'])
 def test_manual_registry_and_scoped_references_protected(self):
  row={'catalog_key':'ISRC:ARDL12400086','asset_isrc':'ARDL12400086'}
  self.assertEqual(set(m.protection(row)),{'track_title','artists','duration_seconds'})
  self.assertIn('artists',m.protection({'catalog_key':'ISRC:ARDL12400060','asset_isrc':'ARDL12400060'}))
 def test_approved_overlay_keeps_money_identity_and_manual_fields(self):
  row=self.row();review={'overrides_json':{'track_title':'Approved','artists':['New']}}
  with patch.object(m,'read_state',return_value=({}, {row['catalog_key']:review})):
   result=m.apply_approved(pl.DataFrame([row])).to_dicts()[0]
  self.assertEqual(result['amount_usd'],123.45);self.assertEqual(result['asset_isrc'],row['asset_isrc']);self.assertEqual(result['catalog_artists'],['New'])
 def test_new_observation_keeps_old_approval_but_requires_new_review(self):
  c=m.comparison(self.row(),self.obs(),{'overrides_json':{'track_title':'Earlier approval'},'decisions_json':{'artists':'keep'},'observation_version':2,'version':1})
  self.assertEqual(c['ours']['track_title'],'Earlier approval');self.assertEqual(c['decisions'],{});self.assertEqual(c['status'],'pending')
 def test_concurrency_and_protected_fields_checked_in_transaction(self):
  obs=self.obs();review={'version':1,'observation_version':3,'decisions_json':{},'overrides_json':{}}
  @contextmanager
  def connect():
   c=Mock();c.execute.side_effect=[Mock(),Mock(fetchone=lambda:obs),Mock(fetchone=lambda:review)];yield c
  with patch.object(m,'operational_connect',connect):
   with self.assertRaises(HTTPException) as e:m.decide(self.row(),{'field':'artists','decision':'accept','observation_version':2,'review_version':1},'editor')
   self.assertEqual(e.exception.status_code,409)
  with patch.object(m,'operational_connect',connect),patch.object(m,'protection',return_value={'artists':{}}):
   with self.assertRaises(HTTPException) as e:m.decide(self.row(),{'field':'artists','decision':'accept','observation_version':3,'review_version':1},'editor')
   self.assertEqual(e.exception.status_code,409)
 def test_unknown_isrc_cannot_refresh(self):
  with self.assertRaises(HTTPException) as e:m.refresh('TITLE:similar','editor')
  self.assertEqual(e.exception.status_code,400)

if __name__=='__main__':unittest.main()
