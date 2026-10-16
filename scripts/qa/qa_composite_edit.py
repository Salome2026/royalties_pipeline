"""Regression checks; optional Cloud SQL cases always roll back their transaction."""
import copy
import os
import sys
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from fastapi.encoders import jsonable_encoder

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import vpo_corp_api as api
from app.operational_db import operational_sqlite_compatible_connect, close_operational_db_pool


class CompositeChildTests(unittest.TestCase):
    def test_hidden_details_and_cash_are_preserved_without_double_payment(self):
        current = dict(
            artist='G Sony', show_date='2026-10-10', venue='San Clemente',
            status='realizado', currency='ARS', cachet_amount=8210000,
            contracted_cachet_amount=8210000, venue_collected_amount=8210000,
            artist_percent=50, producer_percent=25, artist_paid_amount=1500000,
            producer_received_amount=90000, seller='Seller', notes='Child notes',
            receipt_refs=['receipt'], expenses_amount=1231500,
            show_expenses=[dict(concept='Gaston', category='comision_externa', amount=1231500)],
            external_shares=[dict(name='Fede', role='tercero', percent=25)],
            cash_movements=[dict(recipient='artist', concept='Advance', amount=1000000, payment_method='efectivo')],
            direct_commissions=[dict(concept='Own fee', amount=10)],
            pre_split_adjustments=[dict(concept='Own recovery', amount=20)],
            artist_adjustments=[dict(concept='Own expense', amount=30)],
        )
        line = api.BookingCompositeEventLineRequest(description='G Sony', artist='G Sony', amount=8210000)
        parent = api.BookingCompositeEventRequest(event_date='2026-10-10', venue='San Clemente')
        request = api.composite_child_request(current, line, parent)
        self.assertEqual(request.artist_paid_amount, 500000)
        self.assertEqual(request.producer_received_amount, 90000)
        for field in ['seller','notes','receipt_refs']:
            self.assertEqual(getattr(request, field), current[field])
        for field in ['show_expenses','external_shares','cash_movements','direct_commissions','pre_split_adjustments','artist_adjustments']:
            self.assertEqual(len(getattr(request, field)), 1)
        payload = api.prepare_booking_show_payload(request, validate_artist=False)
        self.assertEqual(payload['artist_paid_amount'], 1500000)

    def test_omitted_expenses_preserve_but_explicit_empty_clears(self):
        current = dict(artist='Candu', show_date='2026-10-10', venue='San Clemente', status='realizado',
                       cachet_amount=100, contracted_cachet_amount=100, venue_collected_amount=100,
                       expenses_amount=10, show_expenses=[dict(concept='Cost',amount=10)])
        parent = api.BookingCompositeEventRequest(event_date='2026-10-10',venue='San Clemente')
        for fields,expected in [({},10),({'show_expenses':[]},0)]:
            line=api.BookingCompositeEventLineRequest(description='Candu',artist='Candu',amount=100,**fields)
            result=api.prepare_booking_show_payload(api.composite_child_request(current,line,parent),validate_artist=False)
            self.assertEqual(result['expenses_amount'],expected)

    def test_timestamp_json_and_database_formats_match(self):
        stored=datetime(2026,10,16,16,30,tzinfo=timezone.utc)
        self.assertTrue(api.booking_version_matches(stored, stored.isoformat()))
        self.assertTrue(api.booking_version_matches(stored, str(stored)))
        self.assertFalse(api.booking_version_matches(stored, '2026-10-16T16:31:00+00:00'))


@unittest.skipUnless(os.environ.get('VPO_QA_POSTGRES_ROLLBACK')=='1', 'requires explicit PostgreSQL rollback verification')
class PostgresCompositeEditTests(unittest.TestCase):
    def test_repeated_edits_and_conflicts(self):
        with operational_sqlite_compatible_connect() as conn:
            conn.execute("SET LOCAL lock_timeout = '5s'")
            conn.execute("SET LOCAL statement_timeout = '30s'")
            @contextmanager
            def same_connection():
                yield conn
            try:
                with patch.object(api, 'booking_connect', same_connection), patch.object(api,'require_api_key'):
                    for event_id in [23,24]:
                        item=api.fetch_booking_composite_event_item(conn,event_id)
                        identities=[(l['id'],l['booking_show_id']) for l in item['lines']]
                        bases=[l['amount'] for l in item['lines']]
                        expenses=[l['show_expenses'] for l in item['lines']]
                        stale=None
                        for iteration in range(3):
                            values=jsonable_encoder(item)
                            values['expected_updated_at']=item['updated_at'].isoformat()
                            request=api.BookingCompositeEventRequest(**values)
                            result=api.update_booking_composite_event(event_id,request)['item']
                            self.assertEqual([(l['id'],l['booking_show_id']) for l in result['lines']],identities)
                            self.assertEqual([l['amount'] for l in result['lines']],bases)
                            self.assertEqual([[e['amount'] for e in l['show_expenses']] for l in result['lines']],[[e['amount'] for e in group] for group in expenses])
                            if stale is None:
                                stale=request
                            item=result
                        with self.assertRaises(api.HTTPException) as failure:
                            api.update_booking_composite_event(event_id,stale)
                        self.assertEqual(failure.exception.status_code,409)
                        for mutation in ['unknown_id','duplicate_id','remove_linked','changed_child']:
                            values=jsonable_encoder(item)
                            values['lines']=copy.deepcopy(values['lines'])
                            values['expected_updated_at']=str(item['updated_at'])
                            if mutation=='unknown_id': values['lines'][0]['id']=999999999
                            if mutation=='duplicate_id': values['lines'][1]['id']=values['lines'][0]['id']
                            if mutation=='remove_linked': values['lines']=values['lines'][1:]
                            if mutation=='changed_child': values['lines'][0]['child_updated_at']='2000-01-01T00:00:00+00:00'
                            with self.assertRaises(api.HTTPException) as failure:
                                api.update_booking_composite_event(event_id,api.BookingCompositeEventRequest(**values))
                            self.assertEqual(failure.exception.status_code,409,mutation)
            finally:
                conn._conn.rollback()
        close_operational_db_pool()


if __name__=='__main__':
    unittest.main()
