import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import polars as pl
from polars.testing import assert_frame_equal
from lib.catalog_video_metadata import apply_catalog_video_metadata, load_decisions, video_search_expr, REGISTRY_PATH
from lib.catalog_report_filter import catalog_alias_lookup
from load_bigquery_release import build_catalog


class CatalogVideoMetadataTests(unittest.TestCase):
    def catalog(self):
        return pl.DataFrame([
            {"catalog_key":"ISRC:ARDL12500089","asset_isrc":"ARDL12500089","track_title":"Qué Ironía",
             "artist_statement":"Candu / Fak","amount_usd":100.,"observed_amount_usd":100.,"units":20.,"song_level_rows":2,
             "identity_amount_usd":90.,"identity_rows":10,"video_ids":"8CUvkg_Y4XM","isrcs":"ARDL12500089","title_variants":"Qué Ironía"},
            {"catalog_key":"VIDEO:8CUvkg_Y4XM","asset_isrc":None,"track_title":"Qué Ironía (Video Oficial)",
             "artist_statement":None,"amount_usd":0.,"observed_amount_usd":0.,"units":0.,"song_level_rows":0,
             "identity_amount_usd":10.,"identity_rows":3,"video_ids":"8CUvkg_Y4XM","isrcs":"","title_variants":"Qué Ironía (Video Oficial)"},
            {"catalog_key":"VIDEO:iNaADuQMAxE","asset_isrc":None,"track_title":"Fui Nada",
             "artist_statement":"G Sony","amount_usd":50.,"observed_amount_usd":50.,"units":5.,"song_level_rows":1,
             "identity_amount_usd":50.,"identity_rows":2,"video_ids":"iNaADuQMAxE","isrcs":"","title_variants":"Fui Nada"},
        ])

    def decisions(self):
        registry=load_decisions()
        return {**registry,"entries":[entry for entry in registry['entries'] if entry['video_isrc'] in ['ARS8H2500027','ARS8H2600025']],
                'aliases':[registry['aliases'][0]]}

    def test_alias_resolution_preserves_economic_values_and_all_identity_evidence(self):
        before=self.catalog()
        after=apply_catalog_video_metadata(before,decisions=self.decisions())
        self.assertEqual(after.height,2)
        for field in ['amount_usd','observed_amount_usd','units','song_level_rows','identity_amount_usd','identity_rows']:
            self.assertEqual(before[field].sum(),after[field].sum())
        row=after.filter(pl.col('asset_isrc')=='ARDL12500089').to_dicts()[0]
        self.assertEqual(row['asset_isrc'],'ARDL12500089')
        self.assertEqual(row['isrcs'],'ARDL12500089')
        self.assertEqual(row['video_isrcs'],['ARS8H2500027'])
        self.assertIn('Qué Ironía (Video Oficial)',row['title_variants'])
        self.assertEqual(row['catalog_aliases'],['VIDEO:8CUvkg_Y4XM'])
        self.assertEqual(row['artist_statement'],'Candu / Fak')

    def test_repeated_enrichment_is_idempotent(self):
        once=apply_catalog_video_metadata(self.catalog(),decisions=self.decisions())
        assert_frame_equal(once,apply_catalog_video_metadata(once,decisions=self.decisions()))

    def test_pending_audio_does_not_change_video_identity_or_financial_aliases(self):
        result=apply_catalog_video_metadata(self.catalog(),decisions=self.decisions())
        row=result.filter(pl.col('catalog_key')=='VIDEO:iNaADuQMAxE').to_dicts()[0]
        relation=json.loads(row['video_relationships_json'])[0]
        self.assertIsNone(row['asset_isrc'])
        self.assertEqual(relation['audio_relationship_status'],'pending_confirmation')
        self.assertIsNone(relation['confirmed_audio_isrc'])
        self.assertEqual(relation['proposed_audio_isrc'],'BK4DA2658122')
        lookup=catalog_alias_lookup(catalog=result)
        self.assertEqual(lookup.filter(pl.col('alias_catalog_key')=='VIDEO:8CUvkg_Y4XM')['catalog_key'][0],'ISRC:ARDL12500089')
        self.assertEqual(lookup.filter(pl.col('alias_catalog_key').is_in(['ISRC:ARS8H2500027','ISRC:ARS8H2600025','ISRC:BK4DA2658122'])).height,0)

    def test_nonzero_alias_is_rejected_without_changing_source(self):
        catalog=self.catalog().with_columns(pl.when(pl.col('catalog_key')=='VIDEO:8CUvkg_Y4XM').then(1.).otherwise(pl.col('amount_usd')).alias('amount_usd'))
        before=catalog.clone()
        with self.assertRaisesRegex(ValueError,'valores economicos propios'):
            apply_catalog_video_metadata(catalog,decisions=self.decisions())
        assert_frame_equal(catalog,before)

    def test_missing_target_or_changed_video_cannot_create_a_song(self):
        for field,value in [('catalog_key','ISRC:NOTPRESENT'),('video_ids',['wrongvideo1'])]:
            decisions=copy.deepcopy(self.decisions())
            decisions['entries'][0][field]=value
            with self.assertRaises(ValueError):apply_catalog_video_metadata(self.catalog(),decisions=decisions)

    def test_real_registry_contains_exactly_authorized_decisions(self):
        registry=load_decisions()
        statuses=[entry['audio_relationship_status'] for entry in registry['entries']]
        self.assertEqual(len(registry['entries']),28)
        self.assertEqual(statuses.count('confirmed'),8)
        self.assertEqual(statuses.count('pending_confirmation'),18)
        self.assertEqual(statuses.count('video_only'),2)
        self.assertEqual(len(registry['aliases']),2)
        medley=next(entry for entry in registry['entries'] if entry['video_isrc']=='ARS8H2500004')
        self.assertTrue(medley['is_composite_video'])

    def test_search_finds_video_isrc_but_never_promotes_pending_audio(self):
        frame=apply_catalog_video_metadata(self.catalog(),decisions=self.decisions())
        self.assertEqual(frame.filter(video_search_expr(set(frame.columns),'ars8h2600025'))['catalog_key'][0],'VIDEO:iNaADuQMAxE')
        self.assertEqual(frame.filter(video_search_expr(set(frame.columns),'bk4da2658122')).height,0)

    def test_bigquery_preparation_preserves_typed_identifiers_and_pending_status(self):
        catalog=apply_catalog_video_metadata(self.catalog(),decisions=self.decisions())
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'catalog.parquet'; target=Path(temp)/'bq.parquet'
            catalog.write_parquet(source)
            build_catalog(source,target,'existing-release')
            result=pl.read_parquet(target)
            self.assertEqual(result.schema['video_isrcs'],pl.List(pl.String))
            self.assertEqual(result['amount_usd'].sum(),150.)
            self.assertIn('pending_confirmation',''.join(result['video_relationships_json'].to_list()))

    def test_duplicate_registry_isrc_is_rejected(self):
        data=load_decisions()
        data['entries'].append(data['entries'][0])
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'decisions.json';path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'repetido'):load_decisions(path)


if __name__=='__main__':unittest.main()
