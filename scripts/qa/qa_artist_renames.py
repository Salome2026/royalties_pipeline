"""Confirmed renames change presentation and search, preserving native evidence."""
import unittest
import pandas as pd
import polars as pl
from polars.testing import assert_frame_equal
from scripts.lib.catalog_artist_dictionary import canonical, display_credit, display_credit_expr, search_terms
from scripts.build_keyword_royalty_report import display_dataframe, filter_report_keyword_values, build_filter
from app.royalty_scope import use_scope


class ArtistRenameTests(unittest.TestCase):
    def test_current_name_for_solo_and_collaborations_without_partial_matches(self):
        cases = {'ACIT x': 'Acita', 'acita': 'Acita', 'ACIT x featuring Gusty dj': 'Acita featuring Gusty dj',
            'ACIT x and good Brusi': 'Acita and good Brusi', 'ACIT x, Gordo Larvo and Teø': 'Acita, Gordo Larvo and Teø',
            'Guest / ACIT x': 'Guest / Acita', 'ACIT x and ACIT x': 'Acita and Acita',
            'ACIT xyz': 'ACIT xyz', 'ACIT x Remix': 'ACIT x Remix', 'Another Acita Band': 'Another Acita Band', None: None}
        frame = pl.DataFrame({'artist': list(cases)})
        self.assertEqual(frame.select(display_credit_expr(pl.col('artist'))).to_series().to_list(), list(cases.values()))
        for before, after in cases.items():
            self.assertEqual(display_credit(before), after)
            self.assertEqual(display_credit(after), after)
        self.assertEqual(canonical('ACIT x'), 'Acita')

    def test_report_search_both_names_retains_historical_money_and_rows(self):
        frame = pl.DataFrame({'artist_statement_style': ['ACIT x', 'Acita', 'Someone else'],
            'asset_isrc': ['ARDL12500074'] * 3, 'amount_usd': [10., -2., 99.], 'units': [20., 4., 99.]})
        original = frame.clone()
        for name in ('ACIT x', 'Acita'):
            selected = filter_report_keyword_values(frame, [name], 'any')
            self.assertEqual(selected.height, 2)
            self.assertEqual(selected['amount_usd'].sum(), 8.)
            expr = build_filter(set(frame.columns), ['artist_statement_style'], [name], 'any')
            assert_frame_equal(frame.filter(expr), selected)
        assert_frame_equal(frame, original)

    def test_export_changes_only_the_artist_presentation(self):
        source = pd.DataFrame({'artist_statement_style': ['ACIT x and good Brusi'], 'amount_usd': [5.25], 'asset_isrc': ['ARDL12500042']})
        original = source.copy(deep=True)
        result = display_dataframe(source)
        self.assertEqual(result.iloc[0]['Artista'], 'Acita and good Brusi')
        self.assertEqual(result.iloc[0]['Ingresos USD'], 5.25)
        pd.testing.assert_frame_equal(source, original)

    def test_regular_rename_does_not_change_wml(self):
        with use_scope('wml'):
            self.assertEqual(search_terms('Acita'), ['Acita'])
            self.assertEqual(pl.DataFrame({'artist':['ACIT x']}).select(display_credit_expr(pl.col('artist'))).item(), 'ACIT x')
            self.assertEqual(display_dataframe(pd.DataFrame({'artist_statement_style':['ACIT x']})).iloc[0]['Artista'], 'ACIT x')

    def test_contract_report_catalog_uses_current_name_and_keeps_native_variants(self):
        from app.royalty_reports.contract_snapshot import contract_catalog_rows
        frame = pl.DataFrame({'asset_isrc':['ARDL12500074'],'track_title':['Fancy'],
            'artist_statement':['ACIT x'],'artist_variants':['ACIT x | Acita'],'amount_usd':[10.]})
        result = contract_catalog_rows(frame)[0]
        self.assertEqual(result['artists_informed'], 'Acita')
        self.assertEqual(result['artist_variants'], 'ACIT x | Acita')
        self.assertEqual(frame['artist_statement'][0], 'ACIT x')

    def test_future_digital_rebuild_keeps_both_names_searchable(self):
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        from app import vpo_corp_api as api
        from scripts.lib.text_search import contains_search_expr
        with tempfile.TemporaryDirectory() as temporary:
            source, target = Path(temporary)/'source.parquet', Path(temporary)/'summary.parquet'
            pl.DataFrame({'source':['soundon'],'account':['soundon'],'statement_period':['2025-12'],
                'artist_statement_style':['ACIT x'],'track_statement_style':['Fancy'],'amount_usd':[4.]}).write_parquet(source)
            with patch.object(api,'DIGITAL_INCOME_SUMMARY_PATH',target), \
                 patch('scripts.lib.product_income.current_index',return_value=None), \
                 patch('scripts.lib.product_income.allocate_income',side_effect=lambda frame,**kw:frame):
                api.build_digital_income_summary_mart(source,True)
            frame=pl.read_parquet(target)
            self.assertEqual(frame['artist'][0], 'Acita')
            for name in ('ACIT x','Acita'):
                self.assertEqual(frame.filter(contains_search_expr(pl.col('search_text'),name))['total_usd'].sum(), 4.)


if __name__ == '__main__':unittest.main()
