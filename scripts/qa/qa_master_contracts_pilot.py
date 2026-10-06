from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import polars as pl

from app.master_contracts import (
    active_artist_contracts,
    artist_suggestions,
    list_artist_contracts,
    read_split,
    save_artist_contract,
    save_split,
    suggested_split,
    validate_split,
)


class MasterContractsPilotTests(unittest.TestCase):
    def test_artist_contract_suggestions_are_reusable_and_do_not_change_saved_splits(self) -> None:
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            aneley = save_artist_contract(conn, {
                "artist_name": "Aneley", "indyana_percent": 50, "has_contract": True,
                "effective_from": "2025-11", "is_project": False, "is_active": True, "notes": "",
            }, expected_version=0, actor="ruben")
            self.assertEqual(aneley["version"], 1)
            self.assertEqual(len(list_artist_contracts(conn)), 1)
            with self.assertRaisesRegex(ValueError, "cambió"):
                save_artist_contract(conn, {**aneley, "indyana_percent": 60}, expected_version=0, actor="alejandrop")
            juntada = save_artist_contract(conn, {
                "artist_name": "La Juntada de los Artistas", "indyana_percent": 70,
                "has_contract": True, "effective_from": None, "is_project": True,
                "is_active": True, "notes": "Proyecto",
            }, expected_version=0, actor="ruben")
            contracts = active_artist_contracts(conn)
            solo = suggested_split(["Aneley"], contracts)
            self.assertEqual((solo["indyana_percent"], solo["principal_percent"]), (50, 50))
            self.assertFalse(solo["agreement_confirmed"])
            group = suggested_split(["La Juntada de los Artistas", "Aneley"], contracts)
            self.assertEqual(group["indyana_percent"], 70)
            self.assertIsNone(group["principal_percent"])
            self.assertTrue(group["apply_guest_contracts"])
            self.assertEqual(group["participants"][0]["internal_contract_indyana_percent"], 50)
            self.assertIsNone(suggested_split(["Candu Dominguez"])["indyana_percent"])
            saved = save_split(conn, "ARDL12600041", group, closed=False,
                               future_reports_selected=False, expected_version=0, actor="ruben")
            self.assertEqual(saved["split"]["indyana_percent"], 70)
            save_artist_contract(conn, {**juntada, "indyana_percent": 65}, expected_version=1, actor="alejandrop")
            self.assertEqual(read_split(conn, "ARDL12600041")["split"]["indyana_percent"], 70)
            self.assertEqual(suggested_split(["La Juntada de los Artistas"], active_artist_contracts(conn))["indyana_percent"], 65)
            save_artist_contract(conn, {**aneley, "is_active": False}, expected_version=1, actor="ruben")
            self.assertIsNone(suggested_split(["Aneley"], active_artist_contracts(conn))["indyana_percent"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM master_artist_contract_history").fetchone()[0], 4)

    def test_source_specific_artist_suggestions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.parquet"
            pl.DataFrame([
                {
                    "asset_isrc": "ARDL12600041", "source": "fuga",
                    "Asset Artist": "La Juntada De Los Artistas, Aneley and Onda Sabanera",
                    "Product Artist": "La Juntada De Los Artistas and Aneley",
                    "artists_raw": None, "transaction_month": "2026-02",
                    "sale_start_date": "2026-02-27", "transaction_date": None,
                },
                {
                    "asset_isrc": "QZW9L2346202", "source": "onerpm",
                    "Asset Artist": None, "Product Artist": None,
                    "artists_raw": "GUSTY DJ(performer), SALASTKBRON(featuring), Someone(writer)",
                    "transaction_month": "2026-03", "sale_start_date": None, "transaction_date": None,
                },
            ]).write_parquet(path)
            fuga = artist_suggestions("ARDL12600041", path, None)
            onerpm = artist_suggestions("QZW9L2346202", path, None)
            self.assertEqual(fuga["artists"], ["La Juntada de los Artistas", "Aneley", "Onda Sabanera"])
            self.assertEqual(onerpm["artists"], ["Gusty DJ", "SALASTKBRON"])
            self.assertEqual((fuga["first_sale_date"], fuga["first_sale_precision"]), ("2026-02-27", "day"))
            self.assertEqual((onerpm["first_sale_date"], onerpm["first_sale_precision"]), ("2026-03", "month"))
            self.assertEqual(suggested_split(fuga["artists"], first_sale_date=fuga["first_sale_date"])["effective_from"], "2026-02-27")

    def test_close_requires_confirmed_complete_split(self) -> None:
        split = {
            "master_type": "indyana_master",
            "has_contract": False,
            "agreement_confirmed": True,
            "effective_from": "2026-01",
            "principal": "La Juntada de los Artistas",
            "indyana_percent": 70,
            "principal_percent": 10,
            "apply_guest_contracts": True,
            "participants": [
                {"artist": "Aneley", "percent": 10, "internal_contract_indyana_percent": 50},
                {"artist": "Onda Sabanera", "percent": 10, "internal_contract_indyana_percent": None},
            ],
            "notes": "Acuerdo validado sin documento adjunto.",
        }
        validate_split(split, True, True)
        with self.assertRaisesRegex(ValueError, "100%"):
            validate_split({**split, "principal_percent": 9}, True, False)
        with self.assertRaisesRegex(ValueError, "único"):
            validate_split({**split, "participants": [{"artist": "La Juntada de los Artistas", "percent": 20}]}, False, False)
        with self.assertRaisesRegex(ValueError, "Solo un ISRC cerrado"):
            validate_split(split, False, True)
        with self.assertRaisesRegex(ValueError, "otro artista"):
            validate_split({**split, "master_type": "indyana_and_other", "other_master_artist": None}, True, False)
        validate_split({**split, "master_type": "mawz_and_other", "other_master_artist": "Aneley", "effective_from": "2026-02-27"}, True, False)

    def test_versions_and_optimistic_lock(self) -> None:
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            split = {
                "master_type": "distribution", "has_contract": False,
                "agreement_confirmed": True, "effective_from": None,
                "principal": "Aneley", "indyana_percent": 50,
                "principal_percent": 30, "apply_guest_contracts": False,
                "participants": [
                    {"artist": "Maxi Espindola", "percent": 10, "internal_contract_indyana_percent": None},
                    {"artist": "Valen", "percent": 10, "internal_contract_indyana_percent": None},
                ],
                "notes": "",
            }
            first = save_split(
                conn, "ARDL12500056", split, closed=True,
                future_reports_selected=False, expected_version=0, actor="ruben",
            )
            self.assertEqual(first["version"], 1)
            self.assertTrue(read_split(conn, "ARDL12500056")["closed"])
            second = save_split(
                conn, "ARDL12500056", {**split, "notes": "Revisado"}, closed=True,
                future_reports_selected=True, expected_version=1, actor="ruben",
            )
            self.assertEqual(second["version"], 2)
            self.assertTrue(read_split(conn, "ARDL12500056")["future_reports_selected"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM master_contract_split_history").fetchone()[0], 2)
            with self.assertRaisesRegex(ValueError, "cambió"):
                save_split(
                    conn, "ARDL12500056", split, closed=True,
                    future_reports_selected=False, expected_version=1, actor="ruben",
                )


if __name__ == "__main__":
    unittest.main()
