from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import polars as pl

from app.master_contracts import artist_suggestions, read_split, save_split, validate_split


class MasterContractsPilotTests(unittest.TestCase):
    def test_source_specific_artist_suggestions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.parquet"
            pl.DataFrame([
                {
                    "asset_isrc": "ARDL12600041", "source": "fuga",
                    "Asset Artist": "La Juntada De Los Artistas, Aneley and Onda Sabanera",
                    "Product Artist": "La Juntada De Los Artistas and Aneley",
                    "artists_raw": None,
                },
                {
                    "asset_isrc": "QZW9L2346202", "source": "onerpm",
                    "Asset Artist": None, "Product Artist": None,
                    "artists_raw": "GUSTY DJ(performer), SALASTKBRON(featuring), Someone(writer)",
                },
            ]).write_parquet(path)
            fuga = artist_suggestions("ARDL12600041", path, None)
            onerpm = artist_suggestions("QZW9L2346202", path, None)
            self.assertEqual(fuga["artists"], ["La Juntada de los Artistas", "Aneley", "Onda Sabanera"])
            self.assertEqual(onerpm["artists"], ["Gusty DJ", "SALASTKBRON"])

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
