from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import polars as pl

from app.master_contracts import (
    active_artist_contracts,
    artist_suggestions,
    contract_analysis_catalog,
    contract_statement_baseline,
    list_artist_contracts,
    read_split,
    save_artist_contract,
    save_split,
    suggested_split,
    validate_split,
)
from app.bigquery_dashboard import royalty_isrc_income_bigquery
from scripts.lib.catalog_report_filter import apply_report_net_personalization
from scripts.lib.distributor_policy_store import use_distributor_policy_snapshot
from app import vpo_corp_api


class MasterContractsPilotTests(unittest.TestCase):
    def test_contract_income_queries_current_dashboard_with_policy_and_july_cutoff(self) -> None:
        class Client:
            def query(self, sql, *, job_config, location):
                self.sql = sql
                self.config = job_config
                self.location = location
                return self

            def result(self):
                return [{"asset_isrc": "ARDL12600006", "amount_usd": 11646.10,
                         "first_statement_month": "2026-01", "last_statement_month": "2026-07"}]

        client = Client()
        rows = royalty_isrc_income_bigquery(
            policy_document={"report_personalization": {"enabled": True}, "entries": [
                {"source": "fuga", "account": "indyana_records", "report_net_adjustment_pct": 10},
            ]},
            end_month="2026-07", project="project", dataset="dataset", location="US",
            maximum_bytes_billed=5000000000, client=client,
        )
        self.assertEqual(rows[0]["amount_usd"], 11646.10)
        self.assertIn("project.dataset.royalty_dashboard_current", client.sql)
        self.assertIn("source = 'fuga' AND account = 'indyana_records'", client.sql)
        self.assertEqual(str(client.config.query_parameters[0].value), "2026-07-01")

    def test_contract_list_uses_statement_month_columns(self) -> None:
        catalog = pl.DataFrame({
            "asset_isrc": ["ARDL12600006"],
            "track_title": ["Tema"],
            "artist_statement": ["Artista"],
            "artist_variants": ["Artista"],
            "amount_usd": [11646.10],
            "_contract_first_statement_month": ["2026-01"],
            "_contract_last_statement_month": ["2026-07"],
            "sources": ["fuga"],
        })
        with sqlite3.connect(":memory:") as conn, \
                patch.object(vpo_corp_api, "require_api_key"), \
                patch.object(vpo_corp_api, "operational_connect", return_value=conn), \
                patch.object(vpo_corp_api, "require_master_contract_user"), \
                patch.object(vpo_corp_api, "read_split_statuses", return_value={}), \
                patch.object(vpo_corp_api, "master_contract_catalog", return_value=catalog):
            result = vpo_corp_api.list_master_contracts(x_vpo_username="tester")
        self.assertEqual(result["items"][0]["amount_usd"], 11646.10)
        self.assertEqual(result["items"][0]["first_month"], "2026-01")
        self.assertEqual(result["items"][0]["last_month"], "2026-07")

    def test_contract_income_matches_dashboard_statement_cutoff_and_net_policy(self) -> None:
        current = pl.DataFrame({
            "asset_isrc": ["ARDL12600041", "BK4DA2634549", "ARDL12600999"],
            "amount_usd": [500.0, 7000.0, 25.0],
            "last_transaction_month": ["2026-09", "2026-08", "2026-09"],
        })
        summary = pl.DataFrame([
            {"isrc": "ARDL12600041", "source": "fuga", "account": "indyana_records",
             "transaction_month": "2026-05", "statement_period": "2026-07", "amount_usd": 100.0},
            {"isrc": "ARDL12600041", "source": "fuga", "account": "indyana_records",
             "transaction_month": "2026-06", "statement_period": "2026-08", "amount_usd": 50.0},
            {"isrc": "BK4DA2634549", "source": "ada", "account": "indyana_records",
             "transaction_month": "2026-07", "statement_period": "2026-07", "amount_usd": 200.0},
            {"isrc": "", "source": "fuga", "account": "indyana_records",
             "transaction_month": "2026-07", "statement_period": "2026-07", "amount_usd": 999.0},
        ])
        baseline = contract_statement_baseline(summary.lazy(), "2026-07")
        policy = {
            "schema_version": 1, "policy_version": 1,
            "report_personalization": {"enabled": True},
            "entries": [
                {"source": "fuga", "account": "indyana_records", "report_net_adjustment_pct": 10},
                {"source": "ada", "account": "indyana_records", "report_net_adjustment_pct": 0},
            ],
        }
        with use_distributor_policy_snapshot(policy):
            adjusted = apply_report_net_personalization(baseline.lazy(), set(baseline.columns))
            by_isrc = adjusted.group_by("asset_isrc").agg([
                pl.sum("amount_usd").alias("amount_usd"),
                pl.min("first_statement_month").alias("first_statement_month"),
                pl.max("last_statement_month").alias("last_statement_month"),
            ]).collect()
        result = contract_analysis_catalog(current, by_isrc)
        self.assertEqual(result.get_column("asset_isrc").to_list(),
                         ["BK4DA2634549", "ARDL12600041", "ARDL12600999"])
        self.assertEqual(result.get_column("amount_usd").to_list(), [200.0, 90.0, 0.0])
        self.assertEqual(result.get_column("_contract_last_statement_month").to_list(),
                         ["2026-07", "2026-07", None])
        self.assertEqual(current.get_column("amount_usd").to_list(), [500.0, 7000.0, 25.0])
        self.assertEqual(contract_statement_baseline(summary.with_columns(
            pl.when(pl.col("isrc") == "ARDL12600041").then(pl.lit("2026-08"))
            .otherwise(pl.col("transaction_month")).alias("transaction_month")
        ).lazy(), "2026-07").height, 2)

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
            self.assertEqual(suggested_split(fuga["artists"], first_sale_date=fuga["first_sale_date"])["agreements"][0]["effective_from"], "2026-02-27")

    def test_distributor_field_rules_do_not_promote_release_artists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.parquet"
            pl.DataFrame([
                {"asset_isrc": "BK4DA2634549", "source": "ada",
                 "Artist Name": "LA JUNTADA DE LOS ARTISTAS & S",
                 "artist_catalog_style": "LA JUNTADA DE LOS ARTISTAS & SOFI B",
                 "artist_credit_status": "confirmed_prefix",
                 "artist_credit_evidence_file": "99500_202607_202607_99500_DTL.xlsx",
                 "Project Title": "SOFI B / Enganchado En Vivo en LA JUNTADA DE LOS ARTISTAS"},
                {"asset_isrc": "BK4DA2634548", "source": "ada",
                 "Artist Name": "LA JUNTADA DE LOS ARTISTAS & S",
                 "Project Title": "Solamente Tú"},
                {"asset_isrc": "ARDL12600007", "source": "fuga",
                 "Asset Artist": "La Juntada De Los Artistas and G Sony",
                 "Product Artist": "La Juntada De Los Artistas, Candu Dominguez and G Sony"},
                {"asset_isrc": "QM4TX2613905", "source": "orchard",
                 "TRACK ARTIST": "TOTI|Benja Garcia|Falcone", "PRODUCT ARTIST": "TOTI"},
                {"asset_isrc": "ARDL12500056", "source": "soundon",
                 "Track Artists": "Aneley,Maxi Espindola,Valen"},
                {"asset_isrc": "ARDL12300007", "source": "dashgo",
                 "Track Artist": "Juli Jones", "Artist Name": "Juli Jones"},
                {"asset_isrc": "QZW9L2346202", "source": "onerpm",
                 "artists_raw": "GUSTY DJ(performer), SALASTKBRON(featuring), Someone(writer)"},
            ]).write_parquet(path)
            self.assertEqual(artist_suggestions("BK4DA2634549", path, None)["artists"],
                             ["La Juntada de los Artistas", "SOFI B"])
            ambiguous = artist_suggestions("BK4DA2634548", path, None)
            self.assertEqual(ambiguous["artists"], ["La Juntada de los Artistas"])
            self.assertTrue(ambiguous["warnings"])
            self.assertEqual(artist_suggestions("ARDL12600007", path, None)["artists"],
                             ["La Juntada de los Artistas", "G Sony"])
            self.assertEqual(artist_suggestions("QM4TX2613905", path, None)["artists"],
                             ["TOTI", "Benja Garcia", "Falcone"])
            self.assertEqual(artist_suggestions("ARDL12500056", path, None)["artists"],
                             ["Aneley", "Maxi Espindola", "Valen"])
            self.assertEqual(artist_suggestions("ARDL12300007", path, None)["artists"], ["Juli Jones"])
            self.assertEqual(artist_suggestions("QZW9L2346202", path, None)["artists"],
                             ["Gusty DJ", "SALASTKBRON"])

    def test_conflicting_track_credits_require_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.parquet"
            pl.DataFrame([
                {"asset_isrc": "ARDL12600007", "source": "fuga",
                 "Asset Artist": "La Juntada De Los Artistas and G Sony"},
                {"asset_isrc": "ARDL12600007", "source": "soundon",
                 "Track Artists": "La Juntada de los Artistas,Candu Dominguez"},
            ]).write_parquet(path)
            result = artist_suggestions("ARDL12600007", path, None)
            self.assertEqual(result["artists"], ["La Juntada de los Artistas"])
            self.assertTrue(any("discrepan" in warning for warning in result["warnings"]))

    def test_changed_artist_order_never_picks_an_unconfirmed_principal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.parquet"
            pl.DataFrame([
                {"asset_isrc": "QT5M22664077", "source": "soundon",
                 "Track Artists": "La Juntada de los Artistas,Candu Dominguez"},
                {"asset_isrc": "QT5M22664077", "source": "soundon",
                 "Track Artists": "Candu Dominguez,La Juntada de los Artistas"},
            ]).write_parquet(path)
            result = artist_suggestions("QT5M22664077", path, None)
            self.assertEqual(set(result["artists"]), {"La Juntada de los Artistas", "Candu Dominguez"})
            self.assertTrue(result["principal_uncertain"])
            self.assertTrue(any("principal" in warning for warning in result["warnings"]))

    def test_multiple_commercial_contracts_validate_ownership_and_periods(self) -> None:
        split = {
            "principal": "Aneley", "agreement_confirmed": True,
            "indyana_percent": 50, "principal_percent": 50, "participants": [],
            "agreements": [
                {"id": "principal", "label": "Contrato principal", "commercialization": "master",
                 "owners": [{"name": "Indyana", "percent": 60}, {"name": "Mawz", "percent": 40}],
                 "effective_from": "2026-02-27", "effective_until": "2026-06-30"},
                {"id": "second", "label": "Contrato 2", "commercialization": "distribution",
                 "owners": [], "effective_from": "2026-07", "effective_until": None},
            ],
        }
        validate_split(split, True, False)
        with self.assertRaisesRegex(ValueError, "100%"):
            validate_split({**split, "agreements": [
                {**split["agreements"][0], "owners": [{"name": "Indyana", "percent": 60}]},
                split["agreements"][1],
            ]}, True, False)
        with self.assertRaisesRegex(ValueError, "anterior"):
            validate_split({**split, "agreements": [
                {**split["agreements"][0], "effective_until": "2026-01"},
                split["agreements"][1],
            ]}, True, False)
        with self.assertRaisesRegex(ValueError, "no lleva titulares"):
            validate_split({**split, "agreements": [
                split["agreements"][0],
                {**split["agreements"][1], "owners": [{"name": "Mawz", "percent": 100}]},
            ]}, True, False)
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            saved = save_split(conn, "ARDL12600041", split, closed=True,
                               future_reports_selected=False, expected_version=0, actor="ruben")
            self.assertEqual(saved["version"], 1)
            self.assertEqual(read_split(conn, "ARDL12600041")["split"]["agreements"], split["agreements"])

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
