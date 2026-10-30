"""Billing fallback must retain identifiers, dates and cross-period evidence."""
from datetime import date
import unittest

from google.api_core.exceptions import InternalServerError, Forbidden
from google.cloud import bigquery

from app.master_contract_income import _statement_rows, _merge_statement_evidence, STATEMENT_WINDOW


class Job:
    def __init__(self, rows=None, error=None):
        self.rows, self.error = rows or [], error

    def result(self, timeout):
        if self.error:
            raise self.error
        return self.rows


class Client:
    def __init__(self, callback):
        self.callback, self.calls = callback, []

    def query(self, sql, *, job_config, location):
        assert job_config.maximum_bytes_billed == 5_000_000_000
        assert location == 'US'
        params = {param.name: param.value for param in job_config.query_parameters}
        self.calls.append((sql, params))
        return self.callback(sql, params)


def config():
    return bigquery.QueryJobConfig(maximum_bytes_billed=5_000_000_000,
        query_parameters=[bigquery.ScalarQueryParameter('release_id', 'STRING', 'current')])


def limit():
    return Job(error=InternalServerError('Query exceeded limit for bytes billed: 5000000000.'))


class ContractIncomeBudgetTests(unittest.TestCase):
    def test_small_query_remains_one_query(self):
        client = Client(lambda sql, params: Job([{'amount_usd': 123}]))
        self.assertEqual(_statement_rows(client, config(), 'SELECT 1 ' + STATEMENT_WINDOW), [{'amount_usd': 123}])
        self.assertEqual(len(client.calls), 1)

    def test_non_budget_failures_are_not_hidden_or_retried(self):
        client = Client(lambda sql, params: Job(error=Forbidden('permission denied')))
        with self.assertRaises(Forbidden):
            _statement_rows(client, config(), 'SELECT 1 ' + STATEMENT_WINDOW)
        self.assertEqual(len(client.calls), 1)

    def test_years_are_disjoint_and_preserve_the_release_filter(self):
        def callback(sql, params):
            self.assertEqual(params['release_id'], 'current')
            if 'DATE_TRUNC' in sql:
                return Job([{'month': date(2025, 12, 1)}, {'month': date(2026, 1, 1)}])
            if 'window_start' not in params:
                return limit()
            self.assertIn('AND statement_month >= @window_start AND statement_month < @window_end', sql)
            return Job([{'period': params['window_start'].year}])
        client = Client(callback)
        self.assertEqual(_statement_rows(client, config(), 'SELECT 1 WHERE release_id=@release_id ' + STATEMENT_WINDOW),
                         [{'period': 2025}, {'period': 2026}])
        windows = [params for _, params in client.calls if 'window_start' in params]
        self.assertEqual(windows[0]['window_end'], windows[1]['window_start'])

    def test_oversized_year_splits_only_into_present_months_and_preserves_null_dates(self):
        def callback(sql, params):
            if 'DATE_TRUNC' in sql:
                return Job([{'month': date(2026, 1, 1)}, {'month': date(2026, 12, 1)}])
            if 'IS NULL' in sql:
                return Job([{'period': None}])
            if 'window_start' not in params or (params['window_end'] - params['window_start']).days > 32:
                return limit()
            return Job([{'period': params['window_start'].month}])
        client = Client(callback)
        self.assertEqual(_statement_rows(client, config(), 'SELECT 1 WHERE TRUE ' + STATEMENT_WINDOW,
                                        alias='c', include_undated=True),
                         [{'period': 1}, {'period': 12}, {'period': None}])
        self.assertTrue(any(params.get('window_end') == date(2027, 1, 1) for _, params in client.calls))
        self.assertEqual(client.calls[-1][0], 'SELECT 1 WHERE TRUE AND c.statement_month IS NULL')

    def test_evidence_is_merged_across_periods_and_retains_ada_product_scope(self):
        base = {'kind': 'VIDEO', 'code': 'abcdefghijk', 'source': 'fuga', 'account': 'indyana',
                'isrcs': None, 'titles': ['Old'], 'artists': ['Lead'], 'native_ada_product': False}
        rows = [base, {**base, 'isrcs': ['ARABC2600001'], 'titles': ['New'], 'artists': ['Guest'], 'native_ada_product': True},
                {**base, 'account': 'other', 'isrcs': ['ARABC2600002']}]
        result = _merge_statement_evidence(rows)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['isrcs'], ['ARABC2600001'])
        self.assertEqual(result[0]['titles'], ['New', 'Old'])
        self.assertEqual(result[0]['artists'], ['Guest', 'Lead'])
        self.assertTrue(result[0]['native_ada_product'])

    def test_global_seeds_are_not_narrowed_to_the_output_window(self):
        import inspect
        from app.master_contract_income import published_unassigned_income
        source = inspect.getsource(published_unassigned_income)
        evidence = source.split('WITH facts AS (', 1)[1]
        self.assertNotIn('{STATEMENT_WINDOW}', evidence.split('FROM codes c JOIN seeds', 1)[0])
        self.assertIn('WHERE TRUE {STATEMENT_WINDOW}', evidence)


if __name__ == '__main__':
    unittest.main()
