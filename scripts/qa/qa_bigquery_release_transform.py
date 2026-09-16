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
)


def assert_columns(path: Path, expected: list[str]) -> pl.DataFrame:
    frame = pl.read_parquet(path)
    assert frame.columns == expected
    assert frame.get_column("release_id").unique().to_list() == ["release-test"]
    return frame


def main() -> None:
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
