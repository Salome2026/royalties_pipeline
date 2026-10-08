from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

import polars as pl


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.load_bigquery_release import (
    CATALOG_FIELDS,
    DASHBOARD_FIELDS,
    DETAIL_FIELDS,
    DIGITAL_FIELDS,
    SONG_FIELDS,
    build_catalog,
    build_dashboard,
    build_detail,
    build_digital,
    build_song,
    detail_context_schema_sql,
)


def assert_columns(path: Path, expected: list[str]) -> pl.DataFrame:
    frame = pl.read_parquet(path)
    assert frame.columns == expected
    assert frame.get_column("release_id").unique().to_list() == ["release-test"]
    return frame


def main() -> None:
    schema_sql = detail_context_schema_sql("project", "dataset")
    assert schema_sql.count("ALTER TABLE") == 2
    assert schema_sql.count("ADD COLUMN IF NOT EXISTS") == 46
    assert "CREATE OR REPLACE VIEW `project.dataset.royalty_report_detail`" in schema_sql
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)

        detail_source = root / "detail_source.parquet"
        pl.DataFrame(
            {
                "statement_period": ["2026-08", "2026-08"],
                "transaction_month": ["2026-07", "bad"],
                "source": ["ada", "fuga"],
                "account": ["indyana_records", "indyana_records"],
                "artist_best_available": ["Artist A", "Artist B"],
                "asset_title_statement": ["Song A", "Song B"],
                "asset_isrc": ["ARA", "ARB"],
                "product_upc": ["0085365665804", None],
                "product_upc_source": ["Parent Product ID", None],
                "gross_royalty_usd": [15.0, None],
                "deductible_fees_usd": [2.5, None],
                "artist_catalog_style": ["Artist A & Guest", None],
                "artist_credit_status": ["confirmed_prefix", None],
                "product_upc_status": ["reported", None],
                "amount_usd": [12.5, -2.0],
                "units": [100.0, 5.0],
                "include_in_statement_view": [True, False],
            }
        ).write_parquet(detail_source)
        detail_target = root / "detail.parquet"
        build_detail(detail_source, detail_target, "release-test")
        detail = assert_columns(detail_target, DETAIL_FIELDS)
        assert detail.get_column("statement_month").to_list() == [date(2026, 8, 1), date(2026, 8, 1)]
        assert detail.get_column("transaction_month").to_list() == [date(2026, 7, 1), None]
        assert abs(detail.get_column("amount_usd").sum() - 10.5) < 0.000001
        assert detail["product_upc"].to_list() == ["0085365665804", None]
        assert detail["product_upc_source"].to_list() == ["Parent Product ID", None]
        assert detail["gpid"].null_count() == 2
        assert detail["gross_royalty_usd"].to_list() == [15.0, None]
        assert detail["deductible_fees_usd"].to_list() == [2.5, None]
        assert detail["artist_catalog_style"].to_list() == ["Artist A & Guest", None]
        assert detail["product_upc_status"].to_list() == ["reported", None]

        onerpm_source = root / "onerpm_source.parquet"
        onerpm_input = pl.DataFrame(
            {
                "source": ["onerpm"] * 5 + ["ada", "fuga"],
                "account": ["henry_remix", "gusty_dj", "la_nueva_sangre", "mawzrecords", "henry_remix", "mawz", "indyana_records"],
                "source_sheet": ["Masters", "Masters", "Youtube Channels", "Shares In & Out", "Masters", "royalty_detail", "standard_statement_csv"],
                "Quantity": [9499.0, 100.0, 5.0, -34.0, 200.0, 999.0, 888.0],
                "units": [None, None, None, None, 0.0, None, 12.0],
                "amount_usd": [45.863822, 10.0, 2.0, -1.25, 0.0, 9.0, 8.0],
                "revenue_basis": ["generation"] * 3 + ["transfer"] + ["generation"] * 3,
                "include_in_statement_view": [True, False, False, False, True, True, True],
                "include_in_cash_view": [True, False, False, True, True, True, True],
                "include_in_catalog_view": [True, True, True, False, True, True, True],
                "possible_internal_transfer": [False, False, False, True, False, False, False],
                "has_share_in_out": [False, True, True, True, False, False, False],
            }
        )
        onerpm_input.write_parquet(onerpm_source)
        onerpm_target = root / "onerpm_detail.parquet"
        build_detail(onerpm_source, onerpm_target, "release-test")
        onerpm_detail = assert_columns(onerpm_target, DETAIL_FIELDS)
        assert onerpm_detail["units"].to_list() == [9499.0, 100.0, 5.0, -34.0, 0.0, 0.0, 12.0]
        for field in ["source", "account", "source_sheet", "amount_usd", "revenue_basis", "include_in_statement_view", "include_in_cash_view", "include_in_catalog_view", "possible_internal_transfer"]:
            assert onerpm_detail[field].to_list() == onerpm_input[field].to_list(), field
        onerpm_input.head(4).drop("units").write_parquet(onerpm_source)
        build_detail(onerpm_source, onerpm_target, "release-test")
        assert pl.read_parquet(onerpm_target)["units"].to_list() == [9499.0, 100.0, 5.0, -34.0]

        dashboard_source = root / "dashboard_source.parquet"
        pl.DataFrame(
            {
                "statement_period": ["2026-08"],
                "transaction_month": ["2026-07"],
                "source": ["ada"],
                "account": ["indyana_records"],
                "artist": ["Artist A"],
                "title": ["Song A"],
                "amount_usd": [12.5],
                "units": [100.0],
                "raw_rows": [2],
            }
        ).write_parquet(dashboard_source)
        dashboard_target = root / "dashboard.parquet"
        build_dashboard(dashboard_source, dashboard_target, "release-test")
        assert_columns(dashboard_target, DASHBOARD_FIELDS)

        song_source = root / "song_source.parquet"
        pl.DataFrame(
            {
                "transaction_month": ["2026-07"],
                "source": ["ada"],
                "account": ["indyana_records"],
                "track_statement_style": ["Song A"],
                "artist_statement_style": ["Artist A"],
                "amount_usd": [12.5],
                "units": [100.0],
            }
        ).write_parquet(song_source)
        song_target = root / "song.parquet"
        build_song(song_source, song_target, "release-test")
        assert_columns(song_target, SONG_FIELDS)

        catalog_source = root / "catalog_source.parquet"
        pl.DataFrame(
            {
                "catalog_key": ["ISRC:ARA"],
                "asset_isrc": ["ARA"],
                "track_title": ["Song A"],
                "artist_statement": ["Artist A"],
                "first_transaction_month": ["2026-07"],
                "last_transaction_month": ["2026-07"],
                "external_release_date": ["2026-06-01"],
                "amount_usd": [12.5],
                "units": [100.0],
            }
        ).write_parquet(catalog_source)
        catalog_target = root / "catalog.parquet"
        build_catalog(catalog_source, catalog_target, "release-test")
        catalog = assert_columns(catalog_target, CATALOG_FIELDS)
        assert catalog.get_column("external_release_date").to_list() == [date(2026, 6, 1)]

        digital_source = root / "digital_source.parquet"
        pl.DataFrame(
            {
                "statement_period": ["2026-08"],
                "source": ["ada"],
                "account": ["indyana_records"],
                "artist": ["Artist A"],
                "title": ["Song A"],
                "search_text": ["artist a song a"],
                "total_usd": [12.5],
                "has_share_in_out": [False],
                "raw_rows": [2],
            }
        ).write_parquet(digital_source)
        digital_target = root / "digital.parquet"
        build_digital(digital_source, digital_target, "release-test")
        assert_columns(digital_target, DIGITAL_FIELDS)

    print("BigQuery release transforms OK")


if __name__ == "__main__":
    main()
