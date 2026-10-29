import copy
import json
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from app.master_contract_models import closed_models


class ContractModelTests(unittest.TestCase):
    def test_only_closed_published_records_preserve_saved_terms_without_income(self):
        catalog = [{"asset_isrc": "ARABC2600001", "track_title": "Referencia", "artist_statement": "Proyecto / Invitado",
                    "catalog_artists": ["Proyecto", "Invitado"], "catalog_artist_evidence": "[]"}]
        split = {"agreements": [{"allocation": {"principal": "Proyecto", "participants": [{"artist": "Invitado", "percent": 20}]}}],
                 "code_association_overrides": [{"included": True, "key": "individual"}]}
        saved = [{"isrc": "ARABC2600001", "payload_json": json.dumps(split), "is_closed": True, "version": 7},
                 {"isrc": "ARABC2600002", "payload_json": "{}", "is_closed": True, "version": 1},
                 {"isrc": "ARABC2600001", "payload_json": "{}", "is_closed": False, "version": 8}]
        before = copy.deepcopy((catalog, saved))
        items = closed_models(catalog, saved)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["version"], 7)
        self.assertEqual(items[0]["split"], split)
        self.assertEqual(items[0]["artist_suggestions"]["artists"], ["Proyecto", "Invitado"])
        self.assertNotIn("amount_usd", items[0])
        self.assertEqual((catalog, saved), before)

    def test_endpoint_reads_closed_models_with_access_check_and_no_income_work(self):
        from app import vpo_corp_api as api
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []

        @contextmanager
        def connection():
            yield conn

        with patch.object(api, "require_api_key") as key, patch.object(api, "require_master_contract_user") as access, \
             patch.object(api, "operational_connect", connection), patch.object(api, "is_postgres_connection", return_value=True), \
             patch.object(api, "is_wml", return_value=False), patch.object(api, "db_sql", side_effect=lambda c, q: q), \
             patch.object(api, "master_contract_catalog") as catalog, \
             patch.object(api, "master_contract_associations") as associations, \
             patch.object(api, "master_contract_associated_income") as income:
            catalog.return_value.to_dicts.return_value = []
            self.assertEqual(api.list_master_contract_models("key", "editor")["items"], [])
            key.assert_called_once_with("key")
            access.assert_called_once_with(conn, "editor", "access")
            query, params = conn.execute.call_args.args
            self.assertTrue(query.startswith("SELECT "))
            self.assertIn("WHERE is_closed = ?", query)
            self.assertEqual(params, (1,))
            self.assertIs(type(params[0]), int)
            associations.assert_not_called()
            income.assert_not_called()


if __name__ == "__main__":
    unittest.main()
