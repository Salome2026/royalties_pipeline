"""Financial parity, authorization, pagination and editable PDF field checks."""
from __future__ import annotations

import ast
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "scripts/qa")]

from fastapi import HTTPException
from pypdf import PdfReader, PdfWriter
from app.royalty_reports.artist_settlement import HEADER, IndividualPdf, individual_statement, title_markup
from app.royalty_reports.contracts import BuiltReport, ReportRequest
from app.royalty_reports.contractual import analyze_contractual_income, beneficiary_key
from app.royalty_reports.engine import ReportEngine
from qa_contractual_executive import fixture, income
from qa_excel_contracts import canonical_functions
from qa_royalty_report_engine import job_payload, runtime_for


def artist_fixture():
    snapshot, _, _, _ = fixture()
    snapshot["artists"] = ["Artista"]
    return snapshot


class SettlementTests(unittest.TestCase):
    def test_original_emoji_titles_use_embedded_glyphs_without_changing_native_text(self):
        title = 'Un nuevo tratamiento 🧍🏻 | Juli Savioli'
        markup = title_markup(title)
        self.assertIn('StatementEmoji', markup)
        self.assertIn('🧍', markup)
        self.assertEqual(title_markup('Canción & versión'), 'Canción &amp; versión')
    def test_individual_after_internal_contract(self):
        data = individual_statement(artist_fixture(), [income()])
        self.assertEqual(data["total"], 6)
        self.assertEqual(len(data["rows"]), 1)
        self.assertEqual((data["rows"][0]["net"], data["rows"][0]["effective_percent"], data["rows"][0]["contract_percent"]), (100, 6, 6))

    def test_multiple_tracks_negatives_and_rounding(self):
        snapshot = artist_fixture()
        snapshot["catalog"].append({**snapshot["catalog"][0], "isrc": "ARDL12600002", "title": "Otro"})
        saved = deepcopy(snapshot["contracts"][0]); saved["isrc"] = "ARDL12600002"
        snapshot["contracts"].append(saved)
        for values in [(100.01, 55.75), (100, -50), (-100, -40), (100, -100), (.01, .01)]:
            rows = [income(value, isrc=f"ARDL1260000{i+1}") for i, value in enumerate(values)]
            expected = next(r["amount"] for r in analyze_contractual_income(snapshot, rows)["recipients"] if r["artist"] == "Artista")
            result = individual_statement(snapshot, rows)
            self.assertEqual(result["total"], expected)
            self.assertAlmostEqual(sum(r["amount"] for r in result["rows"]), expected)
            self.assertEqual(sorted(r["net"] for r in result["rows"]), sorted(values))

    def test_contract_changes_and_full_period_net(self):
        snapshot = artist_fixture()
        agreement = snapshot["contracts"][0]["split"]["agreements"][0]
        agreement["effective_until"] = "2026-01-31"
        next_agreement = deepcopy(agreement)
        next_agreement.update(id="b", effective_from="2026-02-01", effective_until=None)
        next_agreement["allocation"]["participants"][0]["rule"]["retained_percent"] = 50
        snapshot["contracts"][0]["split"]["agreements"].append(next_agreement)
        result = individual_statement(snapshot, [income(month="2026-01"), income(month="2026-02")])
        row = result["rows"][0]
        self.assertEqual((row["net"], row["amount"], row["effective_percent"], row["contract_percent"]), (200, 16, 8, None))
        next_agreement["allocation"]["participants"][0]["artist"] = "Otro artista"
        result = individual_statement(snapshot, [income(month="2026-01"), income(month="2026-02")])
        row = result["rows"][0]
        self.assertEqual((row["net"], row["amount"], row["effective_percent"]), (200, 6, 3))

    def test_zero_net_preserves_contract_percentage(self):
        row = individual_statement(artist_fixture(), [income(100), income(-100)])["rows"][0]
        self.assertEqual((row["net"], row["amount"], row["effective_percent"], row["contract_percent"]), (0, 0, None, 6))

    def test_missing_contract_or_identity_remains_visible_without_invented_allocation(self):
        for rows in [[income(), income(3, isrc=None)], [income(month="2025-12")],
                     [income(), income(100, isrc=None), income(-100, month="2026-02", isrc=None)]]:
            result = individual_statement(artist_fixture(), rows)
            self.assertTrue(result['has_pending'])
            self.assertAlmostEqual(sum(row['net'] for row in result['rows']), sum(row['amount_usd'] for row in rows))
            pending = [row for row in result['rows'] if row.get('pending')]
            self.assertTrue(pending)
            self.assertTrue(all(row['amount'] is None and row['contract_percent'] is None and row['effective_percent'] is None for row in pending))
        snapshot = artist_fixture(); snapshot["contracts"][0]["is_closed"] = False
        result = individual_statement(snapshot, [income()])
        self.assertEqual(result['rows'][0]['net'], 100)
        self.assertIsNone(result['rows'][0]['amount'])
        self.assertIsNone(result['total'])
        snapshot["artists"].append("Otro")
        with self.assertRaisesRegex(ValueError, "exactamente un artista"):
            individual_statement(snapshot, [income()])

    def test_api_and_worker_validation(self):
        namespace = canonical_functions()
        model = namespace["RoyaltyReportJobRequest"]
        canonical = namespace["canonical_royalty_report_params"]
        params = canonical(model(output="executive_pdf", executive_mode="artist_settlement", contract_artists=["Artista"]), {"entries": []})
        self.assertEqual(params["executive_mode"], "artist_settlement")
        self.assertEqual(params["period_basis"], "statement_period")
        for artists in [[], ["Artista", "Otro"]]:
            with self.assertRaises(HTTPException):
                canonical(model(output="executive_pdf", executive_mode="artist_settlement", contract_artists=artists), {"entries": []})
        namespace["is_wml"] = lambda: True
        with self.assertRaises(HTTPException):
            canonical(model(output="executive_pdf", executive_mode="artist_settlement", contract_artists=["Artista"]), {"entries": []})
        job = job_payload("royalty_executive", "executive_pdf")
        job["params"].update(params)
        self.assertEqual(ReportRequest.from_job(job, keywords=[]).executive_mode, "artist_settlement")
        job["params"]["contract_artists"] = []
        with self.assertRaises(ValueError):
            ReportRequest.from_job(job, keywords=[])

    def test_authorization_before_reading_artifact(self):
        tree = ast.parse((ROOT / "app/vpo_corp_api.py").read_text(encoding="utf-8"))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "require_report_job_access"]
        from typing import Any, Literal
        guard = unittest.mock.Mock(side_effect=HTTPException(403, "Contratos no autorizados"))
        namespace = {"Any": Any, "Literal": Literal, "HTTPException": HTTPException,
            "operational_connect": lambda: nullcontext(None), "require_module_permission": lambda *args: {"is_admin": True},
            "require_contract_report_permission": guard}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "settlement-permissions", "exec"), namespace)
        with self.assertRaises(HTTPException):
            namespace["require_report_job_access"]("admin", {"params": {"executive_mode": "artist_settlement"}})
        guard.assert_called_once()

    def test_job_engine_uses_new_renderer_and_existing_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); stages, uploads = [], []
            runtime = runtime_for(folder, stages, uploads)
            def prohibited(*args):
                raise AssertionError("No ejecutar generadores anteriores ni resolver marts localmente")
            runtime = replace(runtime, resolve_marts=prohibited, configure_catalog_environment=prohibited)
            artifact = folder / "individual.pdf"; artifact.write_bytes(b"pdf-test")
            job = job_payload("royalty_executive", "executive_pdf")
            job["params"].update(executive_mode="artist_settlement", contract_artists=["Artista"])
            with patch("app.royalty_reports.artist_settlement.build_individual_pdf", return_value=BuiltReport(output_path=artifact, content_type="application/pdf")), patch("app.royalty_reports.contract_pdf.build_contractual_pdf", prohibited):
                result = ReportEngine(runtime).build(job)
            self.assertEqual(result.content_type, "application/pdf")
            self.assertEqual(stages, ["reading_data", "building", "uploading"])
            self.assertEqual(len(uploads), 1)

    def test_pdf_fields_are_canonical_empty_editable_and_printable(self):
        data = individual_statement(artist_fixture(), [income()])
        request = SimpleNamespace(start_month=None, end_month="2026-07", job_id=1)
        with tempfile.TemporaryDirectory() as directory:
            path = IndividualPdf(data, artist_fixture(), request).build(Path(directory))
            reader = PdfReader(path)
            fields = reader.get_fields()
            self.assertEqual(set(fields), {"nombre_cobro", "dni_cobro", "correo_cobro"})
            self.assertTrue(all(field["/V"] == "" for field in fields.values()))
            self.assertEqual(tuple(reader.pages[0].mediabox), (0, 0, 842, 595))
            for ref in reader.pages[0]["/Annots"]:
                widget = ref.get_object()
                self.assertTrue(widget["/AP"]["/N"].get_data())
                self.assertTrue(widget["/F"] & 4)
                self.assertEqual(widget["/V"], fields[widget["/T"]]["/V"])
            writer = PdfWriter(); writer.clone_document_from_reader(reader)
            expected = {"nombre_cobro": "Persona de prueba", "dni_cobro": "12345678", "correo_cobro": "prueba@example.com"}
            writer.update_page_form_field_values(writer.pages[0], expected, auto_regenerate=False)
            filled = Path(directory)/"filled.pdf"; writer.write(filled)
            reopened = PdfReader(filled)
            self.assertEqual({k:v["/V"] for k,v in reopened.get_fields().items()}, expected)
            self.assertEqual({a.get_object()["/T"]: a.get_object()["/V"] for a in reopened.pages[0]["/Annots"]}, expected)
            template = PdfReader(HEADER).pages[0].extract_text().lower()
            for private in ["melina", "meli gimenez", "43.057", "brisamelina", "$5,49", "$0,41"]:
                self.assertNotIn(private, template)

    def test_long_titles_and_multiple_pages(self):
        data = individual_statement(artist_fixture(), [income()])
        prototype = data["rows"][0]
        data["rows"] = [{**prototype, "isrc": str(i), "title": f"Tema {i}: " + "Una canción con un título largo "*4} for i in range(55)]
        data["total"] = 330
        request = SimpleNamespace(start_month="2026-01", end_month="2026-07", job_id=2)
        with tempfile.TemporaryDirectory() as directory:
            reader = PdfReader(IndividualPdf(data, artist_fixture(), request).build(Path(directory)))
            self.assertGreater(len(reader.pages), 1)
            for page in reader.pages:
                self.assertIn("INDYANA RECORDS LLC", page.extract_text())
            self.assertEqual(sum(len(page.get("/Annots", [])) for page in reader.pages), 3)
            self.assertEqual(sum(page.extract_text().count("Total del artista") for page in reader.pages), 1)
            self.assertIn("Tema 54:", " ".join(page.extract_text() for page in reader.pages))


if __name__ == "__main__":
    unittest.main(verbosity=2)
