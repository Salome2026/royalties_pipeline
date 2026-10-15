from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import polars as pl
from lib.fuga_extended import audit_directory, inventory_item, evidence_dir, load_reports, AUDIT_FILE, METADATA_FILE
import ingest_standardized_fuga as ingest


class ExtendedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root / "input_raw" / "fuga"
        self.raw.mkdir(parents=True)
        self.regular = self.raw / "October2026_INDYANA-royalty_product_and_asset.csv"
        self.extended = self.raw / "October2026_INDYANA-youtube_extended.csv"
        self.native = {"Sale ID": ["1"], "Reported Royalty": ["1.12345678901234567890"],
            "Converted Gross Income": ["2"], "Asset Quantity": ["10"], "Currency": ["EUR"],
            "Territory": ["AR"], "DSP": ["Youtube Music"], "Contract deal term": ["50"],
            "Sale Type": ["UGC"], "Sale Start date": ["2026-08-01"], "Sale End date": ["2026-08-31"],
            "Asset ISRC": ["ARAUDIO00001"]}
        self.extra = {"Sale ID": ["1"], "Reported Royalty": ["1.12345678901234567890"],
            "Converted Gross Income": ["2"], "Quantity": ["10"], "Currency": ["EUR"],
            "Territory": ["AR"], "Service": ["Youtube Music"], "Contract deal term": ["50"],
            "YouTube Claim Type": ["UGC"], "Sale Start date": ["2026-08-01"], "Sale End date": ["2026-08-31"],
            "YouTube Asset ISRC": ["ARVIDEO00001"], "YouTube Video Title": ["Video"],
            "YouTube Channel Display Name": ["Canal"]}
        self.write()

    def write(self):
        pl.DataFrame(self.native).write_csv(self.regular)
        pl.DataFrame(self.extra).write_csv(self.extended)

    def test_first_load_preserves_evidence_and_second_load_is_idempotent(self):
        self.assertEqual(inventory_item(self.root, self.extended)["status"], "pending_real")
        first = audit_directory(self.root)
        self.assertEqual(first[0]["status"], "validated")
        self.assertEqual(first[0]["isrc_review_rows"], 1)
        self.assertEqual(inventory_item(self.root, self.extended)["status"], "ignored_audit_detail")
        evidence = evidence_dir(self.root, self.extended) / "metadata.parquet"
        before = evidence.stat().st_mtime_ns
        self.assertEqual(audit_directory(self.root), first)
        self.assertEqual(evidence.stat().st_mtime_ns, before)
        result = pl.read_parquet(self.root / "warehouse" / "marts" / METADATA_FILE)
        self.assertEqual(result.height, 1)
        self.assertEqual(result["economic_role"][0], "supplementary_metadata_only")
        self.assertEqual(result["YouTube Asset ISRC"][0], "ARVIDEO00001")
        self.assertEqual(result["source_row"][0], 2)

    def test_changed_money_invalidates_cache_and_blocks(self):
        audit_directory(self.root)
        self.extra["Reported Royalty"] = ["1.12345678901234567891"]
        self.write()
        self.assertEqual(inventory_item(self.root, self.extended)["status"], "pending_real")
        with self.assertRaisesRegex(ValueError, "Reported Royalty"):
            audit_directory(self.root)
        self.assertEqual(load_reports(self.root / "warehouse/marts" / AUDIT_FILE)[0]["status"], "blocked")

    def test_changed_principal_also_invalidates_cache(self):
        audit_directory(self.root)
        self.native["Currency"] = ["USD"]
        self.write()
        with self.assertRaisesRegex(ValueError, "Currency"):
            audit_directory(self.root)

    def test_missing_principal_stops_standard_ingestion_before_economic_writes(self):
        self.regular.unlink()
        sentinel = self.root / "economic.parquet"
        sentinel.write_bytes(b"unchanged")
        with patch.object(ingest, "BASE_DIR", self.root), patch.object(ingest, "INPUT_DIR", self.raw), \
                patch.object(ingest, "OUTPUT_PATH", sentinel), patch.object(ingest, "TEMP_DIR", self.root / "parts"):
            with self.assertRaisesRegex(ValueError, "Falta el statement completo"):
                ingest.main()
        self.assertEqual(sentinel.read_bytes(), b"unchanged")

    def test_duplicate_missing_and_uncovered_sale_ids_block(self):
        for kind in ["duplicate", "unmatched", "uncovered", "blank"]:
            with self.subTest(kind=kind):
                extra, native = pl.DataFrame(self.extra), pl.DataFrame(self.native)
                if kind == "duplicate": extra = pl.concat([extra, extra])
                if kind == "unmatched": extra = extra.with_columns(pl.lit("2").alias("Sale ID"))
                if kind == "uncovered": native = pl.concat([native, native.with_columns(pl.lit("2").alias("Sale ID"))])
                if kind == "blank": extra = extra.with_columns(pl.lit("").alias("Sale ID"))
                extra.write_csv(self.extended)
                native.write_csv(self.regular)
                with self.assertRaises(ValueError): audit_directory(self.root)

    def test_regular_only_and_youtube_shorts_do_not_require_extended_coverage(self):
        shorts = pl.DataFrame(self.native).with_columns(pl.lit("shorts").alias("Sale ID"), pl.lit("YouTube Shorts").alias("DSP"))
        pl.concat([pl.DataFrame(self.native), shorts]).write_csv(self.regular)
        self.assertEqual(audit_directory(self.root)[0]["status"], "validated")
        self.extended.unlink()
        self.assertEqual(audit_directory(self.root), [])
        self.assertEqual(pl.read_parquet(self.root / "warehouse/marts" / METADATA_FILE).height, 0)

    def test_new_month_and_account_are_paired_without_hardcoded_names(self):
        second = self.raw / "November2026_OTHER-YOUTUBE_EXTENDED.CSV"
        self.extended.rename(second)
        self.regular.rename(self.raw / "November2026_OTHER-ROYALTY_PRODUCT_AND_ASSET.CSV")
        self.assertEqual(audit_directory(self.root)[0]["file_name"], second.name)

    def test_missing_metadata_requires_reprocessing(self):
        audit_directory(self.root)
        (evidence_dir(self.root, self.extended) / "metadata.parquet").unlink()
        self.assertEqual(inventory_item(self.root, self.extended)["status"], "pending_real")
        self.assertEqual(audit_directory(self.root)[0]["status"], "validated")

    def test_standard_load_uses_only_principal_income_on_repeated_runs(self):
        output = self.root / "economic.parquet"
        with patch.object(ingest, "BASE_DIR", self.root), patch.object(ingest, "INPUT_DIR", self.raw), \
                patch.object(ingest, "OUTPUT_PATH", output), patch.object(ingest, "TEMP_DIR", self.root / "parts"), \
                patch.object(ingest, "get_monthly_fx", return_value=1.0):
            ingest.main()
            first = pl.read_parquet(output)
            ingest.main()
            second = pl.read_parquet(output)
        self.assertEqual(first.height, 1)
        self.assertEqual(second.height, 1)
        self.assertEqual(first["amount_usd"].sum(), second["amount_usd"].sum())
        self.assertEqual(second["statement_file_name"].to_list(), [self.regular.name])

    def test_monitor_and_publication_gate_use_current_audit_not_filename_only(self):
        import app.vpo_corp_api as api
        with patch.object(api, "BASE", self.root):
            before = api.build_raw_inventory("fuga", "input_raw/fuga", {self.regular.name})
            self.assertEqual(before["summary"]["pending_real"], 1)
            audit_directory(self.root)
            after = api.build_raw_inventory("fuga", "input_raw/fuga", {self.regular.name})
            self.assertNotIn("pending_real", after["summary"])
            self.assertEqual(api.source_monitor_fuga_audits()["items"][0]["status"], "validated")
            self.native["Reported Royalty"] = ["3"]
            self.write()
            self.assertEqual(api.source_monitor_fuga_audits()["items"][0]["status"], "pending")
            self.assertEqual(api.build_raw_inventory("fuga", "input_raw/fuga", {self.regular.name})["summary"]["pending_real"], 1)

    def test_corrupted_evidence_is_not_considered_audited(self):
        audit_directory(self.root)
        (evidence_dir(self.root, self.extended) / "metadata.parquet").write_bytes(b"corrupted")
        self.assertEqual(inventory_item(self.root, self.extended)["status"], "pending_real")
        self.assertEqual(audit_directory(self.root)[0]["status"], "validated")

    def test_process_button_runs_late_supplement_with_real_pipeline_script(self):
        import app.vpo_corp_api as api
        before = {"source": "fuga", "account": "indyana_records", "display_name": "FUGA",
            "unprocessed_raw_files": [self.extended.name], "last_statement_period": "2026-10"}
        after = {**before, "unprocessed_raw_files": []}
        sentinel = self.root / "warehouse/marts" / "standardized_raw_all_sources.parquet"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_bytes(b"economic data unchanged")
        calls = []
        def run_script(name):
            calls.append(name)
            run = subprocess.run([sys.executable, str(api.SCRIPTS / name), "--root", str(self.root)],
                capture_output=True, text=True)
            return {"script": name, "returncode": run.returncode, "tail": (run.stdout + run.stderr).splitlines()[-40:]}
        with patch.object(api, "BASE", self.root), patch.object(api, "require_api_key"), \
                patch.object(api, "get_source_monitor_item", side_effect=[before, after]), \
                patch.object(api, "run_pipeline_script", side_effect=run_script), \
                patch.object(api, "statement_summary_for_files", return_value=[]):
            result = api.process_source_monitor("fuga_indyana_records", "test")
        self.assertTrue(result["ok"])
        self.assertEqual(calls, ["audit_fuga_youtube_extended.py"])
        self.assertEqual(sentinel.read_bytes(), b"economic data unchanged")
        self.assertEqual(inventory_item(self.root, self.extended)["status"], "ignored_audit_detail")


if __name__ == "__main__":
    unittest.main()
