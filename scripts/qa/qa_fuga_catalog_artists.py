from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import polars as pl
from polars.testing import assert_frame_equal

from app.master_contracts import artist_suggestions, suggested_split
from app.master_contract_metadata import infer_video_evidence
from scripts.lib.catalog_report_filter import catalog_alias_lookup
from scripts.lib.fuga_catalog_artists import (
    ARTIST_COLUMNS, RULE_VERSION, catalog_artist_display, enrich_fuga_catalog, parse_credit,
)
from scripts.load_bigquery_release import build_catalog, bq_load, catalog_artist_schema_sql, CATALOG_FIELDS


class FugaCatalogArtistTests(unittest.TestCase):
    def raw(self, **changes):
        return {
            "source": "fuga", "account": "indyana_records", "asset_isrc": "ARDL12600005",
            "Asset Artist": "La Juntada De Los Artistas and Candu Dominguez",
            "Product Artist": "La Juntada De Los Artistas, Candu Dominguez and G Sony",
            "Product Reference": "55818", "Asset Reference": "10759751", "Product UPC": "8721000000000",
            "statement_period": "2026-01", "statement_file_name": "January2026.csv",
            "statement_file_hash": "abc", **changes,
        }

    def catalog(self):
        return pl.DataFrame({
            "catalog_key": ["ISRC:ARDL12600005", "ISRC:ARDL12600006", "VIDEO:abcdefghijk"],
            "asset_isrc": ["ARDL12600005", "ARDL12600006", None],
            "track_title": ["La Nave del Olvido", "Other song", "Video"],
            "artist_statement": ["La Juntada De Los Artistas and Candu Dominguez", "Other artist", "Channel"],
            "artist_variants": ["La Juntada De Los Artistas, Candu Dominguez and G Sony", "Other artist", "Channel"],
            "title_variants": ["La Nave del Olvido", "Other song", "Video"],
            "amount_usd": [123.456789, -2.0, 19.0], "units": [100, 0, 7],
            "upcs": ["8721000000000", "8721000000001", None],
            "video_ids": [None, None, "abcdefghijk"],
            "track_ids": ["10759751", "1", "abcdefghijk"],
            "sources": ["fuga", "ada", "fuga"],
        })

    def enrich(self, rows=None, catalog=None):
        return enrich_fuga_catalog(self.catalog() if catalog is None else catalog,
                                   pl.DataFrame(rows or [self.raw()]).lazy())

    def test_union_preserves_every_existing_column_and_other_sources(self):
        before = self.catalog()
        after = self.enrich(catalog=before)
        assert_frame_equal(before, after.select(before.columns))
        self.assertEqual(after["catalog_artists"][0].to_list(), ["La Juntada De Los Artistas", "Candu Dominguez", "G Sony"])
        self.assertIsNone(after["catalog_artists"][1])
        self.assertIsNone(after["catalog_artists"][2])
        self.assertEqual(after["catalog_artist_rule"][0], RULE_VERSION)

    def test_track_only_and_release_only_credits_and_blank_values(self):
        for track, release, expected in [("Lead", "", ["Lead"]), ("", "New Guest", ["New Guest"]), ("", "", [])]:
            result = self.enrich([self.raw(**{"Asset Artist": track, "Product Artist": release})],
                                self.catalog().with_columns(pl.lit("").alias("artist_statement")))
            self.assertEqual(result["catalog_artists"][0].to_list(), expected)

    def test_future_artist_and_later_partial_statement_do_not_require_a_name_dictionary(self):
        rows = [self.raw(**{"Product Artist": "La Juntada De Los Artistas, Candu Dominguez and Previously Unknown Guest"}),
                self.raw(**{"statement_period": "2026-02", "statement_file_name": "February2026.csv",
                            "Product Artist": "La Juntada De Los Artistas"})]
        self.assertIn("Previously Unknown Guest", self.enrich(rows)["catalog_artists"][0].to_list())

    def test_multiple_upcs_do_not_multiply_catalog_or_sales(self):
        rows = [self.raw(), self.raw(**{"Product UPC": "8721000000002", "Product Reference": "55819",
                                        "Product Artist": "La Juntada De Los Artistas and Another Guest"})]
        result = self.enrich(rows)
        self.assertEqual(result.height, self.catalog().height)
        self.assertEqual(result["amount_usd"].to_list(), self.catalog()["amount_usd"].to_list())
        self.assertIn("Another Guest", result["catalog_artists"][0].to_list())

    def test_spaces_and_case_deduplicate_but_dj_and_accents_are_not_aliases(self):
        catalog = self.catalog().with_columns(pl.lit("").alias("artist_statement"))
        rows = [self.raw(**{"Asset Artist": "Guest", "Product Artist": " guest "}),
                self.raw(**{"Asset Artist": "DJ Guest", "Product Artist": "Gu\u00e9st"})]
        artists = self.enrich(rows, catalog)["catalog_artists"][0].to_list()
        self.assertEqual(len(artists), 3)
        self.assertEqual(set(artists), {"Guest", "DJ Guest", "Gu\u00e9st"})

    def test_original_literals_origins_files_hashes_and_upcs_remain_in_evidence(self):
        evidence = json.loads(self.enrich()["catalog_artist_evidence"][0])
        guest = next(item for item in evidence if "G Sony" in item["artists"])
        self.assertEqual(guest["field"], "Product Artist")
        self.assertEqual(guest["statement_file_hash"], "abc")
        self.assertEqual(guest["Product UPC"], "8721000000000")
        self.assertEqual(guest["raw"], self.raw()["Product Artist"])

    def test_video_channel_and_other_distributor_cannot_become_release_artists(self):
        for changes in [{"Product Reference": "YT-V-abcdefghijk"}, {"Asset Reference": "YT-A-123"}, {"source": "ada"}]:
            result = self.enrich([self.raw(**changes)])
            self.assertIsNone(result["catalog_artists"][0])

    def test_same_title_with_distinct_isrc_does_not_spread_participants(self):
        result = self.enrich(catalog=self.catalog().with_columns(pl.lit("Same title").alias("track_title")))
        self.assertIsNone(result["catalog_artists"][1])

    def test_idempotent_and_row_order_independent(self):
        rows = [self.raw(), self.raw(**{"statement_period": "2026-02", "Product Artist": "Late Guest"})]
        first = self.enrich(rows)
        assert_frame_equal(first, self.enrich(list(reversed(rows))))
        assert_frame_equal(first, self.enrich(rows, first))

    def test_display_is_separate_from_identity_aliases_and_video_inference(self):
        before, after = self.catalog(), self.enrich()
        assert_frame_equal(catalog_alias_lookup(catalog=before).sort("alias_catalog_key"),
                           catalog_alias_lookup(catalog=after).sort("alias_catalog_key"))
        self.assertEqual(infer_video_evidence(before.to_dicts(), []), infer_video_evidence(after.to_dicts(), []))
        displayed = catalog_artist_display(after)
        self.assertIn("G Sony", displayed["artist_statement"][0])
        assert_frame_equal(before.select("catalog_key", "amount_usd"), displayed.select("catalog_key", "amount_usd"))

    def test_approved_manual_metadata_has_priority_without_erasing_raw_evidence(self):
        catalog = self.catalog().with_columns(pl.Series("catalog_manual_correction_id", ["APPROVED", None, None]))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "corrections.json"
            path.write_text(json.dumps({"corrections": [{"catalog_key": "ISRC:ARDL12600005", "id": "APPROVED",
                "confirmed_by": "Test", "artist_statement": catalog["artist_statement"][0]}]}), encoding="utf-8")
            result = enrich_fuga_catalog(catalog, pl.DataFrame([self.raw()]).lazy(), corrections_path=path)
        self.assertNotIn("G Sony", result["catalog_artists"][0].to_list())
        self.assertIn("G Sony", result["catalog_artist_evidence"][0])

    def test_title_only_correction_does_not_disable_artist_union(self):
        catalog = self.catalog().with_columns(pl.Series("catalog_manual_correction_id", ["TITLE-ONLY", None, None]))
        self.assertIn("G Sony", self.enrich(catalog=catalog)["catalog_artists"][0].to_list())

    def test_quoted_group_does_not_create_ghost_names_from_existing_display(self):
        catalog = self.catalog().with_columns(pl.lit('"New and Future" and Lead').alias("artist_statement"))
        rows = [self.raw(**{"Asset Artist": '"New and Future" and Lead', "Product Artist": "Lead"})]
        self.assertEqual(self.enrich(rows, catalog)["catalog_artists"][0].to_list(), ['"New and Future"', "Lead"])

    def test_existing_catalog_comma_and_ampersand_are_not_new_combined_artists(self):
        catalog = self.catalog().with_columns(pl.lit("Lead, Guest & Another").alias("artist_statement"))
        rows = [self.raw(**{"Asset Artist": "Lead, Guest and Another", "Product Artist": "Lead"})]
        self.assertEqual(self.enrich(rows, catalog)["catalog_artists"][0].to_list(), ["Lead", "Guest", "Another"])

    def test_human_confirmed_artist_reference_is_isrc_scoped(self):
        catalog = self.catalog().with_columns(pl.lit("ARDL12400060").alias("asset_isrc"), pl.lit("Kita").alias("artist_statement"))
        rows = [self.raw(**{"asset_isrc": "ARDL12400060", "Asset Artist": "Kita", "Product Artist": "Federikita"})]
        self.assertEqual(self.enrich(rows, catalog)["catalog_artists"][0].to_list(), ["Federikita"])
        other = self.catalog().with_columns(pl.lit("Kita").alias("artist_statement"))
        self.assertEqual(self.enrich([self.raw(**{"Asset Artist": "Kita", "Product Artist": "Kita"})], other)["catalog_artists"][0].to_list(), ["Kita"])

    def test_release_only_artist_remains_available_without_becoming_principal(self):
        evidence = json.dumps([{"field": "Product Artist", "artists": ["Release Guest"]}])
        result = artist_suggestions("ARDL12600005", None, "Release Guest", ["Release Guest"], evidence)
        self.assertTrue(result["principal_uncertain"])
        draft = suggested_split(result["artists"], principal_uncertain=result["principal_uncertain"])
        self.assertEqual(draft["principal"], "")
        self.assertEqual(draft["participants"][0]["artist"], "Release Guest")
        self.assertIsNone(draft["participants"][0]["percent"])

    def test_artist_correction_does_not_assign_a_different_track_principal(self):
        evidence = json.dumps([{"field": "Asset Artist", "artists": ["Track Lead"]}])
        result = artist_suggestions("ARDL12600005", None, "Release Guest", ["Release Guest"], evidence)
        self.assertTrue(result["principal_uncertain"])
        draft = suggested_split(result["artists"], principal_uncertain=result["principal_uncertain"])
        self.assertEqual(draft["principal"], "")

    def test_union_does_not_hide_native_track_discrepancy_warnings(self):
        warning = "Las fuentes de pista discrepan; sugerimos solo los nombres comunes. Revisar antes de cerrar."
        raw_result = {"artists": ["Lead"], "evidence": [], "warnings": [warning], "principal_uncertain": True}
        with tempfile.TemporaryDirectory() as folder:
            raw = Path(folder) / "raw.parquet"; raw.touch()
            with patch("app.master_contracts._artist_suggestions", return_value=raw_result):
                result = artist_suggestions("ARDL12600005", raw, "Lead / Guest", ["Lead", "Guest"])
        self.assertIn(warning, result["warnings"])
        self.assertTrue(result["principal_uncertain"])

    def test_fuga_credit_grammar_preserves_quoted_groups_and_unknown_serialization(self):
        self.assertEqual(parse_credit('Lead, Second and Guest')[0], ["Lead", "Second", "Guest"])
        self.assertEqual(parse_credit('Lead featuring New Artist')[0], ["Lead", "New Artist"])
        self.assertEqual(parse_credit('"New and Future" and Lead')[0], ['"New and Future"', "Lead"])
        self.assertEqual(parse_credit("El Mago y La Luna")[0], ["El Mago y La Luna"])
        self.assertEqual(parse_credit("Uncertain, Name")[1], "ambiguous_serialization")
        self.assertEqual(parse_credit("Name | Guest")[1], "ambiguous_serialization")
        self.assertEqual(parse_credit('"Unbalanced')[1], "ambiguous_serialization")

    def test_contract_suggestions_use_master_list_and_do_not_write_a_saved_contract(self):
        current = {"artists": ["Lead"], "evidence": [{"field": "Asset Artist"}],
                   "warnings": [], "principal_uncertain": False, "first_sale_date": "2026-01-01", "first_sale_precision": "day"}
        with tempfile.TemporaryDirectory() as folder:
            raw_path = Path(folder) / "raw.parquet"
            raw_path.touch()
            with patch("app.master_contracts._artist_suggestions", return_value=current):
                result = artist_suggestions("ARDL12600005", raw_path, "Lead / New Guest", ["Lead", "New Guest"])
        self.assertEqual(result["artists"], ["Lead", "New Guest"])
        self.assertEqual(current["artists"], ["Lead"])
        self.assertEqual(result["first_sale_date"], "2026-01-01")

    def test_bigquery_preserves_master_list_and_unchanged_economic_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "catalog.parquet", Path(folder) / "bq.parquet"
            original = self.enrich()
            original.write_parquet(source)
            build_catalog(source, target, "test-release")
            result = pl.read_parquet(target)
        self.assertEqual(result["catalog_artists"][0].to_list(), original["catalog_artists"][0].to_list())
        self.assertEqual(result["artist_statement"].to_list(), original["artist_statement"].to_list())
        self.assertEqual(result["amount_usd"].to_list(), original["amount_usd"].to_list())
        self.assertTrue(set(ARTIST_COLUMNS) <= set(CATALOG_FIELDS))
        self.assertIn("catalog_artists ARRAY<STRING>", catalog_artist_schema_sql("project", "dataset"))

    def test_bigquery_load_maps_parquet_lists_to_arrays_not_nested_structs(self):
        with patch("scripts.load_bigquery_release.run") as run:
            bq_load(bq="bq", project="project", dataset="dataset", location="US", table="stage", uri="gs://bucket/catalog.parquet")
        self.assertIn("--parquet_enable_list_inference=true", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
