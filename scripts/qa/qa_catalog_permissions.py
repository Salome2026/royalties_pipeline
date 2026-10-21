"""Catalog writes must use module permissions, regardless of global editor role."""

import sqlite3
import unittest
from contextlib import nullcontext
from unittest.mock import patch

import polars as pl
from fastapi import HTTPException

from app import vpo_corp_api as api


class CatalogPermissionTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        self.conn.executescript("""
            CREATE TABLE employees (id INTEGER PRIMARY KEY);
            CREATE TABLE app_users (
                username TEXT, global_role TEXT, active INTEGER, employee_id INTEGER
            );
            CREATE TABLE module_permissions (
                employee_id INTEGER, module_key TEXT, can_access INTEGER,
                can_create INTEGER, can_view_history INTEGER, can_edit INTEGER,
                can_approve INTEGER, scope_json TEXT
            );
            INSERT INTO employees VALUES (1);
            INSERT INTO app_users VALUES ('alejandro', 'viewer', 1, 1);
            INSERT INTO module_permissions VALUES (1, 'catalog', 1, 1, 1, 1, 1, '[]');
        """)
        self.request = api.CatalogStatusRequest(
            catalog_key="test-boxindanga", active=True,
            include_in_reports=True, business_status="vpo_catalog",
        )

    def update(self, username):
        with patch.object(api, "require_api_key"), \
             patch.object(api, "operational_connect", return_value=nullcontext(self.conn)), \
             patch.object(api, "db_sql", side_effect=lambda conn, sql: sql), \
             patch.object(api, "db_bool", side_effect=bool), \
             patch.object(api, "load_catalog_status", return_value=pl.DataFrame()) as load, \
             patch.object(api, "save_catalog_status") as save:
            try:
                result = api.update_catalog_status(
                    self.request, x_vpo_api_key="test", x_vpo_username=username,
                )
            except HTTPException:
                load.assert_not_called()
                save.assert_not_called()
                raise
            save.assert_called_once()
            row = save.call_args.args[0].to_dicts()[0]
            self.assertTrue(row["active"])
            self.assertTrue(row["include_in_reports"])
            return result

    def test_module_editor_with_global_viewer_can_activate(self):
        self.assertTrue(self.update("alejandro")["ok"])

    def test_global_editor_without_module_edit_cannot_activate(self):
        self.conn.execute("UPDATE app_users SET global_role = 'editor'")
        self.conn.execute("UPDATE module_permissions SET can_edit = 0")
        with self.assertRaises(HTTPException) as caught:
            self.update("alejandro")
        self.assertEqual(caught.exception.status_code, 403)

    def test_global_admin_can_activate_without_module_row(self):
        self.conn.execute("UPDATE app_users SET global_role = 'admin'")
        self.conn.execute("DELETE FROM module_permissions")
        self.assertTrue(self.update("alejandro")["ok"])

    def test_inactive_user_cannot_activate(self):
        self.conn.execute("UPDATE app_users SET active = 0")
        with self.assertRaises(HTTPException) as caught:
            self.update("alejandro")
        self.assertEqual(caught.exception.status_code, 403)

    def test_missing_identity_is_rejected_before_permission_fallback(self):
        with self.assertRaises(HTTPException) as caught:
            self.update(None)
        self.assertEqual(caught.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
