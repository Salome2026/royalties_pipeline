import csv
from pathlib import Path
import sys
import tempfile
import unittest
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.native_csv import read_native_csv
from lib.native_identity_integrity import compare_original_frame, fingerprint, validate_original_witnesses


class NativeIdentityIntegrityTests(unittest.TestCase):
    def test_real_fuga_reader_and_standardizer_keep_late_native_video(self):
        from unittest.mock import patch
        import ingest_standardized_fuga as fuga
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "June2026StatementRun-royalty_product_and_asset.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(["Sale Start date", "Reported Royalty", "Product Reference", "Asset Reference", "Product UPC"])
                writer.writerows([["2026-04-01", "1.25", str(i+100000), str(i+200000), "046081037160"] for i in range(10001)])
                writer.writerow(["2026-04-01", "-0.25", "YT-V-D7fw7V7xM_o", "YT-A-A495111758494142", "046081037160"])
            with patch.object(fuga, "get_monthly_fx", return_value=1.1):
                result = fuga.standardize_fuga_file(fuga.read_fuga_csv(path), path,
                                                   "regular", "2026-06", "filename", "fixture")
            self.assertEqual(result[-1, "video_id"], "D7fw7V7xM_o")
            self.assertEqual(result[-1, "product_upc"], "046081037160")
            self.assertEqual(result[-1, "amount_usd"], -0.275)
            self.assertEqual(result.height, 10002)

    def test_excel_native_text_keeps_zero_prefix_and_mixed_id_types(self):
        from openpyxl import Workbook
        from lib.onerpm_catalog_artists import read_native_workbook
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "statement.xlsx"
            book = Workbook()
            sheet = book.active
            sheet.title = "Masters"
            sheet.append(["ID", "UPC", "Net"])
            sheet.append(["10001", "000123", 1.25])
            sheet.append(["YT-V-D7fw7V7xM_o", "000456", -2])
            book.save(path)
            frame = read_native_workbook(path, "Masters")
            self.assertEqual(frame[0, "UPC"], "000123")
            self.assertEqual(frame[1, "ID"], "YT-V-D7fw7V7xM_o")
            self.assertEqual(frame[0, "Net"], "1.25")

    def test_saved_original_witness_rejects_a_later_degraded_projection(self):
        with tempfile.TemporaryDirectory() as folder:
            raw = pl.DataFrame({"Product Reference": ["YT-V-D7fw7V7xM_o"]})
            proof = {**fingerprint(raw, ["Product Reference"]), "status": "verified_against_original",
                     "source": "fuga", "file_hash": "a" * 64, "file_name": "statement.csv"}
            written = raw.with_columns(pl.lit("fuga").alias("source"), pl.lit("a" * 64).alias("statement_file_hash"),
                                       pl.lit("statement.csv").alias("statement_file_name"))
            path = Path(folder) / "published.parquet"
            written.write_parquet(path)
            document = {"rule": "native-original-identity-1", "files": [proof]}
            self.assertEqual(validate_original_witnesses(path, document)["verified_files_or_sheets"], 1)
            written.with_columns(pl.lit(None, dtype=pl.String).alias("Product Reference")).write_parquet(path)
            with self.assertRaises(ValueError):
                validate_original_witnesses(path, document)
    def test_numeric_prefix_does_not_erase_late_identifiers_or_leading_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "statement.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(["Product Reference", "Asset Reference", "Reported Royalty"])
                writer.writerows([[str(n + 100000), str(n + 200000), "1.25"] for n in range(10001)])
                writer.writerow(["YT-V-D7fw7V7xM_o", "YT-A-A495111758494142", "-0.001"])
                writer.writerow(["000123", "YT-A-OTHER", "0"])
            frame = read_native_csv(path)
            self.assertEqual(frame[-2, "Product Reference"], "YT-V-D7fw7V7xM_o")
            self.assertEqual(frame[-1, "Product Reference"], "000123")
            self.assertEqual(frame[-2, "Reported Royalty"], "-0.001")
            lost = pl.read_csv(path, infer_schema_length=10000, ignore_errors=True)
            with self.assertRaises(ValueError):
                compare_original_frame(frame, lost, "fuga")

    def test_reordering_preserves_duplicate_rows_but_dropping_one_fails(self):
        raw = pl.DataFrame({"Asset ISRC": ["QZW9L2430233"] * 3, "Product Reference": ["YT-V-D7fw7V7xM_o"] * 3})
        self.assertEqual(compare_original_frame(raw, raw.reverse(), "fuga")["rows"], 3)
        with self.assertRaises(ValueError):
            compare_original_frame(raw, raw.head(2), "fuga")

    def test_same_counts_do_not_hide_swapped_identifier_correspondence(self):
        raw = pl.DataFrame({"ISRC": ["QZW9L2430233", "QZTVM2212749"], "VideoId": ["D7fw7V7xM_o", "ARNCwvS41aw"]})
        wrong = raw.with_columns(pl.col("VideoId").reverse())
        with self.assertRaises(ValueError):
            compare_original_frame(raw, wrong, "dashgo")

    def test_all_csv_sources_reject_missing_original_identifier_columns(self):
        for source, field in [("fuga", "Asset Reference"), ("dashgo", "VideoId"),
                              ("orchard", "YOUTUBE VIDEO ID"), ("soundon", "Track ID")]:
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    compare_original_frame(pl.DataFrame({field: ["0012"]}), pl.DataFrame({"other": ["0012"]}), source)

    def test_invalid_csv_is_not_silently_admitted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.csv"
            path.write_text('ISRC,VideoId\n"unclosed,123', encoding="utf-8")
            with self.assertRaises(pl.exceptions.ComputeError):
                read_native_csv(path)

    def test_admission_blocks_lost_reference_before_replacing_output(self):
        from lib.ingestion_controls import Batch, IngestionControlError
        from lib.ingestion_controls import checksum
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "statement.csv"
            source.write_text("Product Reference,Sale ID\nYT-V-D7fw7V7xM_o,1001\n", encoding="utf-8")
            digest = checksum(source)
            output = root / "warehouse/marts/standardized_raw_fuga.parquet"
            output.parent.mkdir(parents=True)
            original = pl.DataFrame({"Product Reference": ["YT-V-D7fw7V7xM_o"], "Sale ID": ["1001"],
                                     "source": ["fuga"], "account": ["indyana_records"],
                                     "statement_file_hash": [digest], "statement_file_name": [source.name]})
            original.write_parquet(output)
            candidate = output.with_name("candidate.parquet")
            original.with_columns(pl.lit(None, dtype=pl.String).alias("Product Reference")).write_parquet(candidate)
            batch = Batch("fuga", output)
            batch.inputs = {source: digest}
            batch.records = [{"status": "selected", "source": "fuga", "account": "indyana_records", "period": "2026-01",
                              "kind": "regular", "file_name": source.name, "file_hash": digest}]
            with self.assertRaises(IngestionControlError) as error:
                batch.stage(candidate)
            self.assertEqual(error.exception.code, "NATIVE_IDENTITY_LOSS")
            self.assertTrue(pl.read_parquet(output).equals(original))

    def test_nonfinancial_share_identity_cannot_disappear(self):
        from lib.native_identity_integrity import validate_onerpm_metadata_references
        import json
        frames = {"Shares In & Out": pl.DataFrame({"ID": ["QZTVM2212749"], "Product Type": ["Track"]})}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "metadata.parquet"
            pl.DataFrame({"asset_isrc": ["QZTVM2212749"], "evidence": [json.dumps([
                {"file_hash": "a" * 64, "sheet": "Shares In & Out"}])]}).write_parquet(path)
            validate_onerpm_metadata_references(frames, path, "a" * 64)
            with self.assertRaises(ValueError):
                validate_onerpm_metadata_references(frames, path, "b" * 64)


if __name__ == "__main__":
    unittest.main()
