"""Contract coverage of uncoded items never changes their physical identity."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts'), str(ROOT / 'scripts/qa')]
import polars as pl
from app.contract_text_reference import context, text_evidence, reference_code, enrich_text_proposals, with_reference_code
from app.master_contract_associations import association_key, candidates, unresolved_associations, validate_choices
from app.master_contract_income import income_association_index, associated_income_isrc
from app.master_contract_link import prepare_link, validate_row_destinations
from app.master_contract_unidentified import unidentified_income
from app.royalty_reports.contract_query import ranking_association_key, select_associated_rankings, association_query_parameter
from app.royalty_reports.contractual import analyze_contractual_income
from app.royalty_reports.artist_settlement import individual_statement
from app.royalty_reports.contract_filter import filter_income, use_filter
from qa_contractual_executive import fixture

ROOT_ISRC = 'ARDL12600001'
OTHER = 'ARDL12600002'
VIDEO = 'abcdefghijk'

def sale(**changes):
    return dict(source='dashgo', account='mawzrecords', source_sheet='', channel_id='channel',
        title='Artista - Canción (Official Video)', artist='Artista', asset_isrc=None,
        product_upc=None, video_id=None, track_id=None, statement_period='2026-07',
        amount_usd=10., raw_rows=1, **changes)

class TextReferenceTests(unittest.TestCase):
    def setUp(self):
        self.sale = sale()
        self.catalog = [{'asset_isrc': ROOT_ISRC, 'track_title': 'Canción', 'artist_statement': 'Artista'}]
        self.aliases = {'VIDEO:' + VIDEO: 'ISRC:' + ROOT_ISRC}
        self.native = {'kind': 'VIDEO', 'code': VIDEO, 'source': 'dashgo', 'account': 'mawzrecords',
            'isrcs': [ROOT_ISRC], 'titles': [self.sale['title']], 'artists': ['Artista'],
            'source_contexts': [json.dumps({'title': self.sale['title'], 'channel_id': 'channel'})]}
        self.evidence = self.enrich([self.native, *text_evidence([self.sale])])
        self.code = reference_code(self.sale)
        self.key = association_key('TEXT', self.code, 'dashgo', 'mawzrecords')

    def enrich(self, evidence):
        return enrich_text_proposals(evidence, self.catalog, self.aliases, {}, {})

    def prepare(self, root=ROOT_ISRC):
        ref = unidentified_income([self.sale], self.evidence, self.catalog, self.aliases, {})['unidentified_items'][0]
        return prepare_link(ref, root, self.evidence, self.aliases, {}, [], 'release', 1)['choices']

    def test_exact_native_context_proposes_but_never_assigns_or_requires_coverage(self):
        item = candidates(ROOT_ISRC, self.evidence[-1:], self.aliases, [], {})[0]
        self.assertEqual(item['proposed_isrcs'], [ROOT_ISRC])
        self.assertFalse(item['included'])
        self.assertEqual(unresolved_associations([item], []), [])
        self.assertIsNone(associated_income_isrc(self.sale, income_association_index(self.evidence, self.aliases, {}, {})))

    def test_manual_financial_destination_can_differ_from_asset_proposal(self):
        for root in (ROOT_ISRC, OTHER):
            choices = self.prepare(root)
            index = income_association_index(self.evidence, self.aliases, {root: choices}, {self.key: root})
            self.assertEqual(associated_income_isrc(self.sale, index), root)
            validate_row_destinations([self.sale], {'included': {}, 'excluded': {}}, index, [self.key], root)
            validate_choices(choices, [], candidates(root, self.evidence[-1:], self.aliases, choices, {}))
        self.assertIsNone(self.sale['asset_isrc'])
        self.assertIsNone(self.sale['video_id'])

    def test_proposals_respect_existing_native_destination_and_discard(self):
        native_key=association_key('VIDEO', VIDEO, 'dashgo', 'mawzrecords')
        selected=candidates(ROOT_ISRC,[self.native],self.aliases,[],{})[0]
        choices={ROOT_ISRC:[{'key':native_key,'included':True,'evidence_signature':selected['evidence_signature']}],
                 OTHER:[{'key':native_key,'included':False,'evidence_signature':'old'}]}
        proposed=enrich_text_proposals([self.native,*text_evidence([self.sale])],self.catalog,self.aliases,choices,{native_key:ROOT_ISRC})
        self.assertEqual(proposed[-1]['inferred_isrcs'],[ROOT_ISRC])

    def test_no_name_only_native_id_invention_and_strict_scope(self):
        self.assertEqual(reference_code({**self.sale, 'amount_usd': 999, 'statement_period': '2027-01', 'monetization': 'Ads'}), self.code)
        for name in ('source', 'account', 'channel_id', 'title', 'artist', 'source_sheet'):
            self.assertNotEqual(reference_code({**self.sale, name: self.sale[name] + ' x'}), self.code)
        for title in ('Artista - Cancion (Official Video)', 'Artista - canción (Official Video)', 'Artista - Canción (Live)'):
            altered = {**self.sale, 'title': title}
            self.assertEqual(self.enrich([self.native, *text_evidence([altered])])[-1]['inferred_isrcs'], [])
        for field in ('asset_isrc', 'product_upc', 'video_id', 'track_id', 'catalog_number'):
            self.assertIsNone(context({**self.sale, field: 'native'}))
        self.assertIsNone(context({**self.sale, 'product_type': 'album'}))

    def test_new_conflicting_anchor_invalidates_saved_decision_not_new_month_or_amount(self):
        choices = self.prepare()
        extra = {**self.native, 'code': 'zyxwvutsrqp'}
        changed = self.enrich([self.native, extra, *text_evidence([self.sale])])
        self.assertFalse(candidates(ROOT_ISRC, changed[-1:], self.aliases, choices, {})[0]['included'])
        future = self.enrich([self.native, *text_evidence([{**self.sale, 'amount_usd': 200, 'statement_period': '2027-01'}])])
        self.assertTrue(candidates(ROOT_ISRC, future[-1:], self.aliases, choices, {})[0]['included'])
        index = income_association_index(self.evidence, self.aliases, {ROOT_ISRC: [{**choices[0], 'included': False}]}, {})
        self.assertIsNone(associated_income_isrc(self.sale, index))
        with self.assertRaises(ValueError):
            prepare_link({'kind': 'TEXT', 'association_code': self.code, 'source_accounts': [{'source': 'dashgo', 'account': 'mawzrecords'}]},
                OTHER, self.evidence, self.aliases, {self.key: ROOT_ISRC}, [], 'release', 1)

    def test_polars_reference_and_contract_filter_preserve_cardinality(self):
        rows = [self.sale, {**self.sale, 'amount_usd': -2}, {**self.sale, 'channel_id': 'other'}]
        frame = pl.DataFrame(rows).lazy()
        hashed = with_reference_code(frame).collect()
        self.assertEqual(hashed['_contract_text_code'].to_list(), [self.code, self.code, reference_code(rows[2])])
        with use_filter({'isrcs': [ROOT_ISRC], 'associations': {'included': {self.key: [ROOT_ISRC]}, 'excluded': {}}}):
            result = filter_income(frame.with_columns(pl.lit('TEXT:original').alias('catalog_key'))).collect()
        self.assertEqual(result.height, 2)
        self.assertEqual(result['amount_usd'].sum(), 8)

    def test_pdf_frozen_text_owner_keeps_original_item_and_native_code(self):
        snapshot, _, _, _ = fixture()
        root = snapshot['catalog'][0]['isrc']
        snapshot.update(schema_version=3)
        row = {**self.sale, 'isrc': None, 'upc': None, 'statement_month': '2026-07',
            'gross_amount_usd': 10, 'units': 3, 'search_text': 'artista artista - canción (official video)   ',
            'normalized_search': 'artista artista - cancion (official video)'}
        key = json.dumps(['dashgo','mawzrecords','','2026-07','TEXT',self.sale['title'],'Artista','channel'], separators=(',',':'))
        snapshot['associations'] = {'ranking_owners': {key: {'isrc': root, 'amount_usd': 10, 'raw_rows': 1}}, 'search_codes': {}}
        from types import SimpleNamespace
        request = SimpleNamespace(keywords=[], source=None, account=None, start_month=None, end_month=None)
        self.assertEqual(ranking_association_key(row, snapshot), key)
        selected = select_associated_rankings([row], request, snapshot)
        self.assertIsNone(selected[0]['isrc'])
        self.assertEqual(selected[0]['_contract_isrc'], root)
        data = analyze_contractual_income(snapshot, selected)
        self.assertEqual(data['covered'], 10)
        self.assertEqual(data['total'], 10)
        self.assertEqual(data['catalog_count'], 1)
        self.assertEqual(sum(t['amount_usd'] for t in data['tracks'] if t['isrc'] == root), 0)
        params = association_query_parameter(snapshot, request).to_api_repr()['parameterValue']['arrayValues']
        self.assertEqual(len(params), 1)
        bad = select_associated_rankings([{**row, 'gross_amount_usd': 11}], request, snapshot)
        self.assertTrue(all('_contract_isrc' not in item for item in bad))

if __name__ == '__main__': unittest.main()
