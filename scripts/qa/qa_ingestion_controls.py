"""Catalogue admission regression tests; synthetic inputs, no network or SQL."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import polars as pl
from lib.ingestion_controls import Batch, IngestionControlError, controlled_ingestion, select_inputs, validate_amounts, validate_no_failed_batches, checksum
from lib.catalog_ingestion_review import control_frame, reading_incidents, native_title_incidents
from app.source_ingestion_controls import classify_fingerprint, source_controls


class IngestionControlsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def file(self, source="fuga", *, month=6, prefix="", text=None):
        folder = self.root / source
        folder.mkdir(exist_ok=True)
        names = {"fuga": f"June2026StatementRun-royalty_product_and_asset.csv" if month == 6 else "July2026StatementRun-royalty_product_and_asset.csv",
            "onerpm": f"2026-{month:02d}-01-details.xlsx", "ada": f"99500_2026{month:02d}_2026{month:02d}_99500_DTL.xlsx",
            "dashgo": f"MAWZ Records-{month:02d}-26.csv", "orchard": f"mawz-revenue-{month}.csv",
            "soundon": f"SoundOn_royalty_monthly_statement_2026_{month:02d}_My Royalty.csv"}
        path = folder / (prefix + names[source])
        content = '"STATEMENT PERIOD","ACCOUNT NAME"\n"June 2026","mawzrecords"\n' if source == "orchard" else "same economic input\n"
        path.write_text(text if text is not None else content, encoding="utf-8")
        return path

    def test_replay_selection_shared_by_context(self):
        for source in ("fuga", "onerpm", "dashgo", "orchard", "soundon"):
            with self.subTest(source=source):
                first = self.file(source)
                duplicate = first.with_name(("2026-06-copy.xlsx" if source == "onerpm" else "Copy-" + first.name))
                shutil.copy2(first, duplicate)
                self.assertEqual(select_inputs([duplicate, first], source, "mawzrecords"), [first])
                self.assertEqual(first.read_bytes(), duplicate.read_bytes())

    def test_changed_content_same_scope_needs_explicit_decision(self):
        first = self.file()
        another = first.with_name("Copy-" + first.name)
        another.write_text("corrected amount\n", encoding="utf-8")
        with self.assertRaises(IngestionControlError) as error:
            select_inputs([first, another], "fuga")
        self.assertEqual(error.exception.code, "UNDECLARED_REPLACEMENT")

    def test_different_months_never_deduplicated_by_content(self):
        first, second = self.file(), self.file(month=7)
        self.assertEqual(checksum(first), checksum(second))
        self.assertEqual(len(select_inputs([first, second], "fuga")), 2)

    def test_accounts_never_merged(self):
        one = self.file("onerpm")
        second = self.root / "other" / one.name
        second.parent.mkdir()
        shutil.copy2(one, second)
        self.assertEqual(len(select_inputs([one, second], "onerpm")), 2)

    def test_regular_and_correction_remain_separate(self):
        regular = self.file()
        correction = regular.with_name("Correction-royalty_product_and_asset.csv")
        shutil.copy2(regular, correction)
        self.assertEqual(len(select_inputs([regular, correction], "fuga")), 2)

    def test_previously_admitted_filename_remains_representative(self):
        first = self.file()
        duplicate = first.with_name("Copy-" + first.name)
        shutil.copy2(first, duplicate)
        output = self.root / "marts/out.parquet"
        output.parent.mkdir()
        pl.DataFrame({"statement_file_name": [duplicate.name]}).write_parquet(output)
        batch = Batch("fuga", output)
        from lib.ingestion_controls import _CURRENT
        token = _CURRENT.set(batch)
        try:
            self.assertEqual(select_inputs([first, duplicate], "fuga"), [duplicate])
        finally:
            _CURRENT.reset(token)

    def test_identical_rows_inside_one_file_are_not_removed(self):
        path = self.file(text="amount\n10\n10\n")
        before = path.read_bytes()
        self.assertEqual(select_inputs([path], "fuga"), [path])
        self.assertEqual(path.read_bytes(), before)

    def test_unknown_file_format_has_a_cause(self):
        path = self.file("onerpm").with_name("2026-06.xlsx")
        path.write_bytes(b"unknown")
        with self.assertRaises(IngestionControlError) as error:
            select_inputs([path], "onerpm")
        self.assertEqual(error.exception.code, "UNKNOWN_LAYOUT")

    def test_invalid_finite_amounts_rejected_without_coercion(self):
        for value in (None, "BAD", "NaN", "inf", "-inf"):
            with self.subTest(value=value):
                frame = pl.DataFrame({"amount_usd": [value]}, schema={"amount_usd": pl.String})
                with self.assertRaises(IngestionControlError) as error:
                    validate_amounts(frame, source="fuga", path=Path("file.csv"), field="Net")
                self.assertEqual(error.exception.code, "INVALID_AMOUNT")

    def test_negatives_zero_and_empty_economic_sheets_remain_valid(self):
        for values in ([-10., 0., 3.5], []):
            frame = pl.DataFrame({"amount_usd": values}, schema={"amount_usd": pl.Float64})
            before = frame.clone()
            validate_amounts(frame, source="onerpm", path=Path("file.xlsx"), field="Net")
            self.assertTrue(frame.equals(before))

    def test_changed_name_and_content_is_pending_not_loaded(self):
        path = self.file("dashgo")
        records = [{"file_name": path.name, "file_hash": checksum(path), "period": "2026-06", "kind": "statement", "status": "selected"}]
        self.assertEqual(classify_fingerprint("dashgo", path, records)["status"], "loaded_to_mart")
        before = path.stat()
        path.write_text("changed economic input\n", encoding="utf-8")
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        result = classify_fingerprint("dashgo", path, records)
        self.assertEqual(result["change_type"], "replacement")
        self.assertEqual(result["status"], "pending_real")

    def test_renamed_replay_does_not_become_a_new_pending_file(self):
        path = self.file("dashgo")
        copy = path.with_name("Copy-" + path.name)
        shutil.copy2(path, copy)
        result = classify_fingerprint("dashgo", copy, [{"file_name": path.name, "file_hash": checksum(path), "period": "2026-06", "kind": "statement", "status": "selected"}])
        self.assertEqual(result["status"], "ignored_duplicate")

    def test_replacement_under_same_name_has_only_one_selected_input(self):
        path = self.file()
        path.write_text("new corrected content", encoding="utf-8")
        self.assertEqual(select_inputs([path], "fuga"), [path])

    def test_failed_batch_blocks_publish_until_successful_retry(self):
        output = self.root / "warehouse/marts/out.parquet"
        output.parent.mkdir(parents=True)
        batch = Batch("fuga", output)
        batch.failed(IngestionControlError("INVALID_AMOUNT", "No se publica el importe invalido"))
        with self.assertRaises(ValueError):
            validate_no_failed_batches(output.parent)
        batch.completed()
        validate_no_failed_batches(output.parent)

    def metadata(self, *, title="Tema", variants="Tema", manual=False, observations=None):
        return pl.DataFrame([{"catalog_key": "ISRC:USFUT2700001", "asset_isrc": "USFUT2700001", "track_title": title,
            "title_variants": variants, "amount_usd": 123.45, "catalog_manual_correction_id": "human" if manual else None,
            "catalog_artist_evidence": json.dumps(observations or [{"source": "onerpm", "account": "mawzrecords", "status": "resolved",
                "credits": [{"name": "Guest", "role": "unknown", "role_original": "featured_artist"}]}])}])

    def test_unknown_roles_are_visible_even_with_a_known_performer(self):
        frame = self.metadata()
        before = frame.clone()
        issues = reading_incidents(frame)
        self.assertEqual([row["code"] for row in issues], ["UNKNOWN_ROLE"])
        self.assertTrue(frame.equals(before))

    def test_incidents_are_grouped_not_one_task_per_observation(self):
        observations = [{"source": "onerpm", "account": "mawzrecords", "status": "ambiguous_serialization", "raw": "unknown grammar"}] * 100
        issues = reading_incidents(self.metadata(observations=observations))
        self.assertEqual(len(issues), 1)
        self.assertEqual(json.loads(issues[0]["details"])["identity_count"], 1)

    def test_cosmetic_titles_cover_and_artist_order_do_not_raise_incidents(self):
        row = self.metadata(variants="Tema | TEMA | Téma (Cover)", observations=[{"source": "fuga", "field": "Asset Artist", "status": "fuga_comma_and_featuring", "principal_status": "uncertain"}])
        self.assertEqual(reading_incidents(row), [])

    def test_disjoint_titles_are_reviewable_never_automatically_remapped(self):
        frame = pl.DataFrame({"source": ["fuga"] * 2, "account": ["indyana_records"] * 2, "asset_isrc": ["USFUT2700001"] * 2,
            "statement_file_name": ["old.csv", "new.csv"], "Asset Title": ["Me Pide Candy", "Tu Pones La Hora"]})
        before = frame.clone()
        self.assertEqual(native_title_incidents(frame.lazy())[0]["code"], "TITLE_CONTRADICTION")
        self.assertTrue(frame.equals(before))

    def test_derived_video_title_variants_are_not_native_track_conflicts(self):
        frame = self.metadata(variants="Tema | Otro titulo del video asociado", observations=[{"source": "fuga", "status": "resolved"}])
        self.assertEqual(reading_incidents(frame), [])

    def test_confirmed_title_exception_does_not_reappear(self):
        frame = self.metadata(variants="Me Pide Candy | Tu Pones La Hora", manual=True, observations=[{"source": "fuga", "status": "contradictory"}])
        self.assertEqual(reading_incidents(frame), [])

    def test_unknown_roles_do_not_disappear_under_manual_title_correction(self):
        self.assertEqual(reading_incidents(self.metadata(manual=True))[0]["code"], "UNKNOWN_ROLE")

    def test_album_context_and_complementary_membership_are_not_new_conflicts(self):
        entries = [{"source": "fuga", "field": "Product Artist", "status": "ambiguous_serialization"},
            {"source": "soundon", "participant_resolution_status": "cross_source_membership_difference"}]
        self.assertEqual(reading_incidents(self.metadata(observations=entries)), [])

    def test_control_artifact_is_separate_from_money_and_source_rows(self):
        marts = self.root / "warehouse/marts"
        marts.mkdir(parents=True)
        catalog = self.metadata()
        before = catalog.clone()
        frame = control_frame(marts, catalog, base_release_id="release-test")
        selected = source_controls(frame, "onerpm", "mawzrecords")
        self.assertEqual(selected["incidents"][0]["code"], "UNKNOWN_ROLE")
        self.assertTrue(catalog.equals(before))


if __name__ == "__main__":
    unittest.main()
