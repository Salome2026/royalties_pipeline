"""Confirmed associations expand the exact ISRC term once, at movement grain."""

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
import polars as pl

from scripts.qa.qa_excel_contracts import ISRC, canonical_functions, report, row, snapshot
from app.contract_text_reference import reference_code
from app.master_contract_associations import association_key
from app.royalty_reports.bigquery_backend.archive_query import association_candidates
from app.royalty_reports.bigquery_backend.selection import write_selection
from app.royalty_reports.contracts import ReportRequest
from app.royalty_reports.keyword_associations import candidate_keys, report_index, use_keyword_associations
from lib.distributor_policy_store import use_distributor_policy_snapshot


OTHER = "ARDL12600002"


class KeywordAssociationTests(unittest.TestCase):
    def test_request_requires_contracts_and_a_full_isrc_and_keeps_old_parameters(self):
        functions = canonical_functions()
        model = functions["RoyaltyReportJobRequest"]
        canonical = functions["canonical_royalty_report_params"]
        fields = {"keywords": [ISRC.lower(), "Palabra adicional"], "include_contracts": True}
        self.assertNotIn("include_associated", canonical(model(**fields), {}))
        params = canonical(model(**fields, include_associated=True), {})
        self.assertTrue(params["include_associated"])
        job = {"id": 1, "report_key": "royalty_keyword", "output_format": "excel", "params": params}
        self.assertTrue(ReportRequest.from_job(job, keywords=params["keywords"]).include_associated)
        for invalid in ({**fields, "include_contracts": False}, {**fields, "keywords": [ISRC[:7]]},
                        {**fields, "output": "executive_pdf"}, {**fields, "output": "google_sheet"}):
            with self.assertRaises(HTTPException):
                canonical(model(**invalid, include_associated=True), {})
        functions["is_wml"] = lambda: True
        with self.assertRaises(HTTPException):
            canonical(model(**fields, include_associated=True), {})

    def test_expanded_summary_detail_count_and_split_keep_native_codes_and_vetoes(self):
        state = snapshot()
        index = state["associations"]
        video = "video-code1"
        state["catalog"].append({"catalog_key": "VIDEO:" + video, "asset_isrc": None,
                                 "artist_statement": "Proyecto, Artista - Tema video (Video Oficial)"})
        text = row(asset_isrc=None, track_statement_style="Approved TEXT title",
                   artist_statement_style="Proyecto and Artista", channel_id="Channel1", amount_usd=12.)
        code = reference_code({"source": "fuga", "account": "indy", "source_sheet": "royalty_detail",
                               "title": text["track_statement_style"], "artist": text["artist_statement_style"],
                               "channel_id": "Channel1"})
        index["included"][association_key("TEXT", code, "fuga", "indy")] = [ISRC]
        index["included"][association_key("TRACK", "one-unique-track", "fuga", "indy")] = [ISRC]
        index["included"][association_key("UPC", "123456789012", "fuga", "indy")] = [OTHER]
        index["excluded"][association_key("TRACK", "excluded-slot", "fuga", "indy")] = [ISRC]
        fixture = [
            row(track_statement_style="Tema direct", units=100.),
            row(asset_isrc=None, video_id=video, track_statement_style="Tema video", amount_usd=20., units=20.),
            row(asset_isrc=None, video_id=video, track_statement_style="Tema video", amount_usd=-3., units=-2.),
            text,
            row(asset_isrc=None, track_id="one-unique-track", track_statement_style="Tema track", amount_usd=5.),
            row(asset_isrc=None, video_id=video, product_upc="123456789012", amount_usd=800.),
            row(asset_isrc=None, video_id=video, track_id="excluded-slot", amount_usd=900.),
            row(asset_isrc=OTHER, video_id=video, amount_usd=1000.),
            row(asset_isrc=None, video_id="pending11", amount_usd=1100.),
            row(asset_isrc=None, video_id=video, account="other", amount_usd=1200.),
            {**text, "channel_id": "Channel2", "amount_usd": 1300.},
        ]
        policy = {"schema_version": 1, "policy_version": 1, "entries": [{
            "source": "fuga", "account": account,
            "sheet_rules": {"royalty_detail": {"catalog_view": True, "statement_view": True, "revenue_basis": "generation"}},
        } for account in ["indy", "other"]]}
        manifest = {"release_id": "release-a", "excel_contract_snapshot": state}
        self.assertIsNone(report_index(manifest, True, ["other"]))
        with self.assertRaises(ValueError):
            report_index({**manifest, "release_id": "stale"}, True, [ISRC])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.parquet"
            pl.DataFrame(fixture, infer_schema_length=None).write_parquet(raw)
            environment = {"VPO_CATALOG_MASTER_PATH": str(root / "absent"), "VPO_CATALOG_STATUS_PATH": str(root / "status")}
            with patch.dict(os.environ, environment), use_distributor_policy_snapshot(policy):
                for basis in ("statement_period", "transaction_month"):
                    with self.subTest(basis=basis):
                        args = dict(keywords=[ISRC], mode="any", start_month=None, end_month=None,
                                    source=None, account=None, period_basis=basis)
                        self.assertEqual(report.count_report_detail_rows(**args, standardized_path=raw), 1)
                        with use_keyword_associations(report_index(manifest, True, args["keywords"])):
                            self.assertEqual(report.count_report_detail_rows(**args, standardized_path=raw), 5)
                            self.assertEqual(report.count_report_detail_rows(
                                **{**args, "start_month": "2026-07"}, standardized_path=raw), 0)
                            self.assertEqual(report.count_report_detail_rows(
                                **{**args, "keywords": [ISRC, "Tema video"], "mode": "all"}, standardized_path=raw), 2)
                            self.assertEqual(report.count_report_detail_rows(
                                **{**args, "keywords": [ISRC, "Tema video"]}, standardized_path=raw), 5)
                            self.assertEqual(report.count_report_detail_rows(
                                **{**args, "source": "fuga", "account": "other"}, standardized_path=raw), 0)
                            prepared = report.prepare_keyword_source(raw, root / "prepared.parquet", [ISRC], "any", batch_size=2)
                            spool = write_selection(report, prepared, args, root / "spool")
                            self.assertEqual(spool.detail.count, 5)
                            output = report.build_report_tables(
                                **args, standardized_path=prepared, song_path=raw, raw_limit=0,
                                detail_mode="full", spooled_selection=spool, contract_snapshot=state,
                            )
                            summary = output["resumen por tema"]
                            self.assertEqual(summary["Ingresos USD"].sum(), 134.)
                            self.assertEqual(summary["Unidades"].sum(), 138.)
                            self.assertTrue({ISRC, video, "one-unique-track"}.issubset(set(summary["Codigo"])))
                            self.assertAlmostEqual(summary["Importe Artista"].sum(), 8.04)
                            self.assertNotIn("Importe Artista - Tema video (Video Oficial)", summary.columns)
                            self.assertEqual(output["resumen general"].iloc[0]["Filas raw"], 5)

    def test_archive_uses_code_scope_and_preserves_extension_and_text_candidates(self):
        state = snapshot()
        index = state["associations"]
        index["included"][association_key("TRACK", "legacy-track", "ada", "indy")] = [ISRC]
        index["included"][association_key("TEXT", "digest", "dashgo", "mawzrecords")] = [ISRC]
        keys = candidate_keys(index, [ISRC.lower()])
        aliases = {"source": "f001", "account": "f002", "video_id": "f003"}
        manifest = {"fields": [{"name": name} for name in [*aliases, "Track ID"]]}
        predicate, args = association_candidates(manifest, aliases, keys)
        self.assertIn("TRIM(CAST(`f003` AS STRING)) = k.code", predicate)
        self.assertIn("TRIM(CAST(`f002` AS STRING)) = k.account", predicate)
        self.assertIn("k.kind = 'TRACK'", predicate)
        self.assertIn("k.kind = 'TEXT'", predicate)
        values = args[0].to_api_repr()["parameterValue"]["arrayValues"]
        self.assertEqual(len(values), 3)


if __name__ == "__main__":
    unittest.main()
