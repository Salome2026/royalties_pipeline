"""Exercise the real commission summary with controlled show and rule inputs."""
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import vpo_corp_api as api


def rule(employee, percent, order, base='commissionable', cobra_igual=False):
    return dict(artist='Gusty DJ', employee_id=employee, employee_name=f'Employee {employee}',
                percentage=percent, priority_order=order, calculation_base=base,
                include_booking_fee_paid_shows=cobra_igual, active=True,
                active_from_month=None, active_to_month=None)


def calculate(rules, income=100, excluded=False):
    shows=[dict(artist='Gusty DJ', month='2026-10', indyana_total=income,
                booking_commission_exempt=excluded, commission_notes='')]
    class Cursor:
        def __init__(self, rows): self.rows=rows
        def fetchall(self): return self.rows
    class Connection:
        def execute(self, sql, params=()):
            return Cursor(rules if 'JOIN employees' in sql else shows)
    @contextmanager
    def connect(): yield Connection()
    with patch.object(api,'booking_connect',connect), patch.object(api,'ensure_booking_commission_rules_table'), patch.object(api,'apply_artist_scope_sql',return_value=''):
        return api.booking_summary_for_module('booking_commissions',None)


class CommissionCalculationBaseTests(unittest.TestCase):
    def test_saldo_uses_remaining_eighty(self):
        result=calculate([rule(1,20,1),rule(2,10,2)])
        detail=result['items'][0]['commission_details']
        self.assertEqual([d['base_amount'] for d in detail],[100,80])
        self.assertEqual([d['commission_amount'] for d in detail],[20,8])
        self.assertEqual(result['totals']['indyana_net_total'],72)

    def test_original_uses_full_hundred_even_in_second_order(self):
        result=calculate([rule(1,20,1),rule(2,10,2,'total')])
        detail=result['items'][0]['commission_details']
        self.assertEqual([d['base_amount'] for d in detail],[100,100])
        self.assertEqual([d['commission_amount'] for d in detail],[20,10])
        self.assertEqual(result['totals']['indyana_net_total'],70)
        self.assertEqual(result['items'][0]['months']['2026-10']['commission_total'],30)

    def test_original_commission_also_reduces_following_saldo(self):
        result=calculate([rule(3,10,3),rule(2,10,2,'total'),rule(1,20,1)])
        detail=result['items'][0]['commission_details']
        self.assertEqual([d['base_amount'] for d in detail],[100,100,70])
        self.assertEqual([d['commission_amount'] for d in detail],[20,10,7])
        self.assertEqual(result['totals']['indyana_net_total'],63)

    def test_cobra_igual_is_independent_of_calculation_base(self):
        for base in ['commissionable','total']:
            with self.subTest(base=base):
                blocked=calculate([rule(1,20,1),rule(2,10,2,base)],excluded=True)
                self.assertEqual(blocked['totals']['commission_total'],0)
                allowed=calculate([rule(1,20,1),rule(2,10,2,base,True)],excluded=True)
                detail=allowed['items'][0]['commission_details']
                self.assertEqual(len(detail),1)
                self.assertEqual(detail[0]['base_amount'],100)
                self.assertEqual(detail[0]['commission_amount'],10)

    def test_zero_and_negative_income_do_not_generate_commissions(self):
        for income in [0,-100]:
            result=calculate([rule(1,20,1),rule(2,10,2,'total')],income=income)
            self.assertEqual(result['totals']['commission_total'],0)


if __name__=='__main__': unittest.main()
