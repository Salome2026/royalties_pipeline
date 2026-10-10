from __future__ import annotations

from types import SimpleNamespace
import json
import unittest
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pyarrow.parquet as pq
import polars as pl

from app.royalty_reports import contract_identity as identity


def key(code: str, kind: str = "ID", sheet: str = "recording", month: str = "2026-07",
        source: str = "fuga", account: str = "indyana_records") -> str:
    return json.dumps([source, account, sheet, month, kind, code], separators=(",", ":"))


def sale(**changes) -> dict:
    return {"source": "fuga", "account": "indyana_records", "source_sheet": "recording",
            "statement_period": "2026-07", "asset_isrc": None, "video_id": None,
            "track_id": None, "UPC": None, **changes}


class ContractIdentityTests(unittest.TestCase):
    def setUp(self):
        identity.unsafe_ranking_slot_keys.cache_clear()

    def tearDown(self):
        identity.unsafe_ranking_slot_keys.cache_clear()

    def scan(self, rows: list[dict], *, generation: int = 7, split: int = 65536,
             schema: pa.Schema | None = None, statistics: bool = True,
             fail_on_columns: frozenset[str] = frozenset(), include_upc: bool | None = None):
        names = sorted({name for row in rows for name in row})
        filled = [{name: row.get(name) for name in names} for row in rows]
        table = pa.Table.from_pylist(filled, schema=schema)
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, row_group_size=split, write_statistics=statistics)
        actual = pq.ParquetFile(pa.BufferReader(sink.getvalue()))
        parquet = MagicMock()
        parquet.schema_arrow = actual.schema_arrow
        parquet.schema = actual.schema
        parquet.metadata = actual.metadata
        parquet.num_row_groups = actual.num_row_groups

        def read_group(index, *, columns, **kwargs):
            if fail_on_columns.intersection(columns):
                raise OSError("identity pages unavailable")
            return actual.read_row_group(index, columns=columns, **kwargs)

        parquet.read_row_group.side_effect = read_group
        parquet.iter_batches.side_effect = actual.iter_batches
        stream, blob, client = MagicMock(), MagicMock(), MagicMock()
        blob.open.return_value.__enter__.return_value = stream
        client.bucket.return_value.blob.return_value = blob
        with patch.object(identity.storage, "Client", return_value=client), \
             patch.object(identity.pq, "ParquetFile", return_value=parquet) as reader:
            options = {} if include_upc is None else {"include_upc": include_upc}
            result = identity.unsafe_ranking_slot_keys("private-bucket", "releases/raw.parquet", generation, **options)
        return result, parquet, blob, client, reader, stream

    def test_projected_pinned_stream_and_batch_settings(self):
        result, parquet, blob, client, reader, stream = self.scan([
            sale(ID="LegacyA", track_id="TrackB", amount_usd=50, units=1,
                 revenue_basis="transfer", include_in_catalog_view=False, title="private title")])
        self.assertEqual(result, frozenset({key("legacya")}))
        client.bucket.assert_called_once_with("private-bucket")
        client.bucket.return_value.blob.assert_called_once_with("releases/raw.parquet", generation=7)
        blob.open.assert_called_once_with("rb", chunk_size=64 * 1024)
        reader.assert_called_once_with(stream)
        reads = parquet.read_row_group.call_args_list
        self.assertTrue(reads)
        projected = {name for call in reads for name in call.kwargs["columns"]}
        self.assertTrue(projected.issubset(identity._IDENTITY_COLUMNS))
        self.assertTrue({"ID", "track_id", "source_sheet"}.issubset(projected))
        self.assertTrue({"amount_usd", "units", "revenue_basis", "include_in_catalog_view", "title"}.isdisjoint(projected))
        self.assertTrue({"ID", "track_id", "UPC", "statement_period"}
                        .isdisjoint(reads[0].kwargs["columns"]))
        self.assertTrue({"ID", "track_id"}.issubset(reads[-1].kwargs["columns"]))
        blob.open.return_value.__exit__.assert_called_once()

    def test_native_excluded_and_legacy_eligible_counterexample_vetoes_a(self):
        result, *_ = self.scan([
            sale(video_id="NativeA", amount_usd=50, include_in_catalog_view=False),
            sale(ID="NativeA", track_id="TrackB", amount_usd=50, include_in_catalog_view=True),
        ], split=1)
        self.assertEqual(result, frozenset({key("nativea")}))

    def test_legacy_space_id_vetoes_the_recovered_first_token(self):
        result, *_ = self.scan([
            sale(video_id="NativeA", amount_usd=50, include_in_catalog_view=False),
            sale(ID="NativeA legacy", track_id="TrackB", amount_usd=50, include_in_catalog_view=True),
        ])
        self.assertEqual(result, frozenset({key("nativea")}))

    def test_all_producer_legacy_video_aliases_and_exact_case(self):
        for name in ("YOUTUBE VIDEO ID", "YouTube Video ID", "YouTube Asset ID", "ID", "Parent ID"):
            with self.subTest(name=name):
                identity.unsafe_ranking_slot_keys.cache_clear()
                result, *_ = self.scan([sale(**{name: "MixedCase", "track_id": "mixedcase"})])
                self.assertEqual(result, frozenset({key("mixedcase")}))

    def test_precedence_trim_nulls_and_native_tracks_remain_safe(self):
        result, *_ = self.scan([
            sale(video_id=" Native ", **{"Video ID": "other", "ID": "legacy"}, track_id="different"),
            sale(video_id="  ", **{"Video ID": " Native ", "VideoId": "other"}),
            sale(track_id=" Track "),
            sale(ID=" Same ", **{"Label Track ID": "Same"}),
        ])
        self.assertEqual(result, frozenset())

    def test_ada_track_branch_uses_exact_source_and_precedence(self):
        result, *_ = self.scan([
            sale(source=" ada ", track_id="Ranking", source_asset_id="Native", catalog_number="Album"),
            sale(source="ada", track_id="Same", source_asset_id=" Same ", catalog_number="different"),
            sale(source="ada", track_id="Catalog", source_asset_id=" ", catalog_number="Catalog"),
            sale(source="ADA", track_id="Same", source_asset_id="different"),
        ])
        self.assertEqual(result, frozenset({key("ranking", source="ada")}))

    def test_upc_precedence_and_fact_only_track_guard(self):
        result, *_ = self.scan([
            sale(upc=" RankingUPC ", product_upc="FactUPC", UPC="Third"),
            sale(upc=" Same ", product_upc="Same", UPC="Other"),
            sale(**{"Product UPC": "Product", "Release UPC": "Release", "UPC Code": "Fact"}),
            sale(UPC="Shared", **{"Label Track ID": "Hidden"}),
            sale(UPC="Shared"),
            sale(upc=" ", product_upc="FactOnly"),
        ])
        self.assertEqual(result, frozenset({key("RankingUPC", "UPC"), key("Product", "UPC"), key("Shared", "UPC")}))

    def test_sheet_aliases_are_trimmed_and_scope_mismatches_vetoed(self):
        for alias in ("sheet_name", "Sheet", "SHEET"):
            with self.subTest(alias=alias):
                identity.unsafe_ranking_slot_keys.cache_clear()
                result, *_ = self.scan([sale(source_sheet=" ", track_id=" Same ", **{alias: " alias "})])
                self.assertEqual(result, frozenset({key("same", sheet="alias")}))
        identity.unsafe_ranking_slot_keys.cache_clear()
        result, *_ = self.scan([sale(source_sheet=" recording ", sheet_name="ignored", track_id="Same")])
        self.assertEqual(result, frozenset())

    def test_no_primary_isrc_blank_scopes_and_invalid_months(self):
        rows = [sale(ID="Legacy", source=" "), sale(ID="Legacy", account=None),
                sale(ID="Legacy", statement_period="invalid"), sale(ID="Legacy", statement_period=None)]
        rows.extend(sale(ID="Legacy", **{name: " Existing "}) for name in identity._PRODUCER_ISRC)
        rows.append(sale(source=" fuga ", account=" indyana_records ", source_sheet=" ",
                         statement_period=" 2026-07 ", asset_isrc=" ", ID=" Legacy "))
        rows.append(sale(ID="Pruned", **{"Track ISRC": "not-retained-by-producer"}))
        result, *_ = self.scan(rows)
        self.assertEqual(result, frozenset({key("legacy", sheet=""), key("pruned")}))

    def test_schema_shortcuts_do_not_skip_upc_only_mismatches(self):
        result, parquet, *_ = self.scan([{"source": "fuga", "account": "indyana_records",
                                          "statement_period": "2026-07", "upc": "Ranking", "product_upc": "Fact"}])
        self.assertEqual(result, frozenset({key("Ranking", "UPC", sheet="")}))
        self.assertTrue(parquet.read_row_group.called)
        identity.unsafe_ranking_slot_keys.cache_clear()
        result, parquet, *_ = self.scan([{"source": "fuga", "account": "indyana_records", "statement_period": "2026-07"}])
        self.assertEqual(result, frozenset())
        parquet.read_row_group.assert_not_called()

    def test_native_video_groups_do_not_read_legacy_or_upc_fields(self):
        result, parquet, *_ = self.scan([
            sale(video_id="Native", ID="Legacy", track_id="Other", upc="Ranking", product_upc="Fact"),
            sale(video_id=" ", **{"Video ID": " Alias ", "ID": "Legacy"}),
            sale(video_id=None, **{"VideoId": "Third", "ID": "Legacy"}),
        ])
        self.assertEqual(result, frozenset())
        for read in parquet.read_row_group.call_args_list:
            self.assertTrue({"ID", "track_id", "upc", "UPC", "product_upc"}
                            .isdisjoint(read.kwargs["columns"]))

    def test_native_video_does_not_hide_sheet_alias_drift(self):
        result, parquet, *_ = self.scan([
            sale(source_sheet=None, sheet_name="LegacySheet", video_id="Native", ID="ignored"),
        ])
        self.assertEqual(result, frozenset({key("native", sheet="LegacySheet")}))
        self.assertTrue(any("ID" in read.kwargs["columns"]
                            for read in parquet.read_row_group.call_args_list))

    def test_sparse_row_indices_stay_aligned_with_second_projection(self):
        result, parquet, *_ = self.scan([
            sale(video_id="Native0", ID="ignored0"),
            sale(ID="Legacy1", track_id="Fact1", source_sheet="Sheet1"),
            sale(asset_isrc="Primary", ID="ignored2"),
            sale(ID="Legacy3", track_id="Fact3", source_sheet="Sheet3", statement_period="2026-08"),
            sale(**{"Video ID": "Native4", "ID": "ignored4"}),
            sale(upc="UPC5", product_upc="Fact5", source_sheet="Sheet5"),
        ])
        self.assertEqual(result, frozenset({key("legacy1", sheet="Sheet1"),
                                           key("legacy3", sheet="Sheet3", month="2026-08"),
                                           key("UPC5", "UPC", sheet="Sheet5")}))
        reads = parquet.read_row_group.call_args_list
        self.assertGreaterEqual(len(reads), 2)
        self.assertEqual(reads[0].args[0], reads[-1].args[0])
        self.assertTrue(set(reads[0].kwargs["columns"]).isdisjoint(reads[-1].kwargs["columns"]))

    def test_primary_isrc_statistics_skip_group_without_reading_pages(self):
        result, parquet, *_ = self.scan([
            sale(asset_isrc="ARAAA2600001", ID="Legacy1"),
            sale(asset_isrc="USBBB2600002", ID="Legacy2"),
        ])
        self.assertEqual(result, frozenset())
        parquet.read_row_group.assert_not_called()

    def test_missing_statistics_and_blank_primary_isrc_do_not_skip_candidates(self):
        for statistics in (True, False):
            for blank in (None, "", " ", "\u2003"):
                with self.subTest(statistics=statistics, blank=repr(blank)):
                    identity.unsafe_ranking_slot_keys.cache_clear()
                    result, *_ = self.scan([
                        sale(asset_isrc="A", ID="ignored"),
                        sale(asset_isrc=blank, ID="Legacy", track_id="Different"),
                        sale(asset_isrc="\U0001f600", ID="ignored"),
                    ], statistics=statistics)
                    self.assertEqual(result, frozenset({key("legacy")}))

    def test_full_date_statement_month_is_normalized_to_seven_characters(self):
        result, *_ = self.scan([
            sale(ID="Date", statement_period=" 2026-07-31 "),
            sale(ID="Timestamp", statement_period="2026-08-15T12:34:56"),
            sale(ID="Invalid", statement_period="2026-13-01"),
        ])
        self.assertEqual(result, frozenset({key("date"), key("timestamp", month="2026-08")}))

    def test_candidate_analysis_batches_are_bounded(self):
        rows = [sale(ID="Repeated", track_id="Different")] * 65539
        with patch.object(identity, "_unsafe_slots", wraps=identity._unsafe_slots) as analyze:
            result, *_ = self.scan(rows, split=len(rows))
        self.assertEqual(result, frozenset({key("repeated")}))
        self.assertGreaterEqual(analyze.call_count, 2)
        self.assertTrue(all(call.args[0].height <= 65536 for call in analyze.call_args_list))

    def test_second_stage_failure_is_not_cached_as_safe(self):
        with self.assertRaisesRegex(OSError, "identity pages unavailable"):
            self.scan([sale(ID="Legacy", track_id="Different")], fail_on_columns=frozenset({"ID"}))
        self.assertEqual(identity.unsafe_ranking_slot_keys.cache_info().currsize, 0)

    def test_footer_leaf_indices_are_not_arrow_top_level_field_indices(self):
        schema = pa.schema([
            pa.field("a_nested", pa.struct([("first", pa.string()), ("second", pa.string())])),
            pa.field("asset_isrc", pa.string()),
            *[pa.field(name, pa.string()) for name in
              ("source", "account", "source_sheet", "statement_period", "video_id", "track_id", "ID")],
        ])
        result, *_ = self.scan([
            sale(ID="Legacy", track_id="Different",
                 a_nested={"first": "unused", "second": "ARAAA2600001"}),
        ], schema=schema)
        self.assertEqual(result, frozenset({key("legacy")}))

    def test_probe_indices_respect_trim_alias_precedence_and_sheet_scope(self):
        rows = [sale(asset_isrc=" Primary ", ID="ignored"),
                sale(video_id=" ", **{"Video ID": " Native ", "ID": "ignored"}),
                sale(video_id=" ", ID="Legacy"),
                sale(video_id="Native", source_sheet=" recording ", sheet_name="ignored"),
                sale(video_id="Native", source_sheet=" ", sheet_name="alias"),
                sale(asset_isrc=" ", video_id=None)]
        frame = pl.from_dicts(rows, infer_schema_length=None)
        self.assertEqual(identity._needs_guard_indices(frame), [2, 4, 5])

    def test_native_video_footer_can_skip_without_sheet_alias_columns(self):
        result, parquet, *_ = self.scan([
            sale(video_id="abcdefghijk", ID="ignored"),
            sale(video_id="lmnopqrstuv", ID="ignored"),
        ])
        self.assertEqual(result, frozenset())
        parquet.read_row_group.assert_not_called()

    def test_all_native_statistics_fail_closed_when_proof_is_missing(self):
        pattern = r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}"
        good = {"null_count": 0, "has_min_max": True, "min": "ARAAA2600001", "max": "USBBB2600002"}
        for changes in ({"null_count": 1}, {"null_count": None}, {"has_min_max": False},
                        {"min": ""}, {"min": " "}, {"min": b"ARAAA2600001"}):
            with self.subTest(changes=changes):
                group = MagicMock(num_columns=1)
                group.column.return_value.path_in_schema = "asset_isrc"
                group.column.return_value.statistics = SimpleNamespace(**{**good, **changes})
                self.assertFalse(identity._all_native(group, ["asset_isrc"], "asset_isrc", pattern))
        group.column.return_value.statistics = None
        self.assertFalse(identity._all_native(group, ["asset_isrc"], "asset_isrc", pattern))
        self.assertFalse(identity._all_native(group, ["other"], "asset_isrc", pattern))
        group.column.return_value.statistics = SimpleNamespace(**good)
        self.assertTrue(identity._all_native(group, ["asset_isrc"], "asset_isrc", pattern))

    def test_id_only_all_null_legacy_and_sheet_aliases_skip_native_group(self):
        rows = [sale(track_id="Same", upc="Ranking", product_upc="Fact", ID=None, sheet_name=None)]
        schema = pa.schema([(name, pa.string()) for name in sorted(rows[0])])
        result, parquet, *_ = self.scan(rows, schema=schema, include_upc=False)
        self.assertEqual(result, frozenset())
        parquet.read_row_group.assert_not_called()
        result, parquet, *_ = self.scan(rows, schema=schema, include_upc=True)
        self.assertEqual(result, frozenset())
        self.assertTrue(parquet.read_row_group.called)

    def test_id_only_does_not_skip_legacy_sheet_or_ada_override_candidates(self):
        for row, expected in [
            (sale(ID="Legacy", track_id="Different"), key("legacy")),
            (sale(source_sheet=None, sheet_name="Alias", track_id="Same"), key("same", sheet="Alias")),
            (sale(source="ada", track_id="Ranking", source_asset_id="Native"), key("ranking", source="ada")),
        ]:
            with self.subTest(row=row):
                identity.unsafe_ranking_slot_keys.cache_clear()
                result, parquet, *_ = self.scan([row], include_upc=False)
                self.assertEqual(result, frozenset({expected}))
                self.assertTrue(parquet.read_row_group.called)

    def test_id_only_source_stats_do_not_hide_trimmed_ada(self):
        for source in (" ada ", "ada ", "ada\t", "ada\u2003"):
            with self.subTest(source=repr(source)):
                identity.unsafe_ranking_slot_keys.cache_clear()
                result, *_ = self.scan([
                    sale(source=source, track_id="Ranking", source_asset_id="Native"),
                ], include_upc=False)
                self.assertEqual(result, frozenset({key("ranking", source="ada")}))

    def test_id_only_ascii_bounds_do_not_hide_interior_unicode_padded_ada(self):
        result, *_ = self.scan([
            sale(source="adaa", track_id="Same"),
            sale(source="ada\u2003", track_id="Ranking", source_asset_id="Native"),
            sale(source="fuga", track_id="Same"),
        ], include_upc=False)
        self.assertEqual(result, frozenset({key("ranking", source="ada")}))

    def test_id_only_requires_all_null_statistics_not_just_missing_minmax(self):
        columns = ["source", "ID", "sheet_name"]
        source = SimpleNamespace(has_min_max=True, min="fuga", max="orchard", null_count=0)
        empty = SimpleNamespace(null_count=3)
        group = MagicMock(num_rows=3, num_columns=len(columns))
        values = [source, empty, empty]
        group.column.side_effect = lambda index: SimpleNamespace(
            statistics=values[index], path_in_schema=columns[index])
        self.assertTrue(identity._native_id_layout(group, columns))
        for bad in (None, SimpleNamespace(null_count=None), SimpleNamespace(null_count=2),
                    SimpleNamespace(null_count=0, has_min_max=False)):
            for index in (1, 2):
                with self.subTest(index=index, statistics=bad):
                    values = [source, empty, empty]
                    values[index] = bad
                    self.assertFalse(identity._native_id_layout(group, columns))
        for bad in (None, SimpleNamespace(has_min_max=False),
                    SimpleNamespace(has_min_max=True, min="ada", max="fuga"),
                    SimpleNamespace(has_min_max=True, min=" ada ", max="fuga")):
            values = [bad, empty, empty]
            self.assertFalse(identity._native_id_layout(group, columns))

    def test_cache_separates_id_only_and_upc_modes(self):
        rows = [sale(upc="Ranking", product_upc="Fact")]
        first, _, _, client, *_ = self.scan(rows, include_upc=False)
        self.assertEqual(first, frozenset())
        self.assertEqual(client.bucket.call_count, 1)
        second, _, _, client, *_ = self.scan(rows, include_upc=True)
        self.assertEqual(second, frozenset({key("Ranking", "UPC")}))
        self.assertEqual(client.bucket.call_count, 1)
        again, _, _, client, *_ = self.scan(rows, include_upc=False)
        self.assertIs(first, again)
        client.bucket.assert_not_called()

    def test_cache_is_immutable_and_keyed_by_all_pinned_coordinates(self):
        parquet = MagicMock(schema_arrow=SimpleNamespace(names=["source", "account", "statement_period"]))
        with patch.object(identity.storage, "Client") as client, patch.object(identity.pq, "ParquetFile", return_value=parquet):
            first = identity.unsafe_ranking_slot_keys("bucket", "raw", 1)
            self.assertIs(first, identity.unsafe_ranking_slot_keys("bucket", "raw", 1))
            identity.unsafe_ranking_slot_keys("bucket", "raw", 2)
            identity.unsafe_ranking_slot_keys("other", "raw", 2)
            identity.unsafe_ranking_slot_keys("other", "different", 2)
            self.assertEqual(client.call_count, 4)
        self.assertEqual(identity.unsafe_ranking_slot_keys.cache_info().maxsize, 2)
        self.assertEqual(identity.unsafe_ranking_slot_keys.cache_info().currsize, 2)
        self.assertIsInstance(first, frozenset)

    def test_bad_pins_and_read_failures_never_return_a_safe_fallback(self):
        with patch.object(identity.storage, "Client") as client:
            for args in [("", "raw", 1), ("bucket", "", 1), ("bucket", "raw", 0)]:
                with self.assertRaises(ValueError):
                    identity.unsafe_ranking_slot_keys(*args)
            client.assert_not_called()
            client.return_value.bucket.return_value.blob.return_value.open.side_effect = OSError("unavailable")
            with self.assertRaisesRegex(OSError, "unavailable"):
                identity.unsafe_ranking_slot_keys("bucket", "raw", 1)
        self.assertEqual(identity.unsafe_ranking_slot_keys.cache_info().currsize, 0)


if __name__ == "__main__":
    unittest.main()
