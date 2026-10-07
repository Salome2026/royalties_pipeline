from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app import vpo_corp_api as api
from lib.ada_identity import add_ada_artist_evidence
from lib.store_taxonomy import add_store_dimensions
from scripts.load_bigquery_release import build_detail, build_song
from lib.distributor_policy_store import use_distributor_policy_snapshot


def main() -> None:
    full = "LIT KILLAH, POLIMA WESTCOAST & LUCHO SSJ"
    short = full[:30]
    assert len(short) == 30
    frame = pl.DataFrame({
        "asset_isrc": ["ARDL12500080"] * 2,
        "Artist Name": [short, full],
        "artist_statement_style": [short, full],
        "statement_file_name": ["old.xlsx", "new.xlsx"],
        "source": ["ada"] * 2, "account": ["mawz"] * 2,
        "source_sheet": ["Distribution Statement"] * 2, "revenue_basis": ["generation"] * 2,
        "statement_period": ["2026-07"] * 2, "transaction_month": ["2026-06"] * 2,
        "track_statement_style": ["Song"] * 2, "asset_title_statement": ["Song"] * 2,
        "store_name": ["Spotify"] * 2, "territory": ["AR"] * 2,
        "amount_usd": [10.5, 2.5], "units": [100, 20],
        "include_in_statement_view": [True] * 2,
    })
    resolved = add_ada_artist_evidence(frame)
    assert resolved["artist_statement_original"].to_list() == [short, full]
    assert resolved["artist_statement_style"].to_list() == [full, full]
    assert resolved.select(frame.columns).drop("artist_statement_style").equals(frame.drop("artist_statement_style"))
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "raw.parquet"
        add_store_dimensions(resolved.lazy()).sink_parquet(source)
        dashboard = root / "dashboard.parquet"
        with use_distributor_policy_snapshot({
            "schema_version": 1, "policy_version": 1,
            "entries": [{"source": "ada", "account": "mawz", "sheet_rules": {
                "Distribution Statement": {"revenue_basis": "generation", "statement_view": True,
                                           "catalog_view": True, "cash_view": True}}}],
        }):
            api.build_royalties_dashboard_summary_mart(source, True, output_path=dashboard)
        data = pl.read_parquet(dashboard)
        assert data["artist"].unique().to_list() == [full]
        assert data["amount_usd"].sum() == 13 and data["units"].sum() == 120
        assert data["raw_rows"].sum() == 2
        previous = api.DIGITAL_INCOME_SUMMARY_PATH
        try:
            api.DIGITAL_INCOME_SUMMARY_PATH = root / "digital.parquet"
            api.build_digital_income_summary_mart(source, True)
            digital = pl.read_parquet(api.DIGITAL_INCOME_SUMMARY_PATH)
            assert digital["artist"].unique().to_list() == [full]
            assert digital["total_usd"].sum() == 13 and digital["raw_rows"].sum() == 2
        finally:
            api.DIGITAL_INCOME_SUMMARY_PATH = previous
        detail_path, song_path = root / "detail.parquet", root / "song.parquet"
        build_detail(source, detail_path, "test")
        build_song(source, song_path, "test")
        detail, song = pl.read_parquet(detail_path), pl.read_parquet(song_path)
        assert detail["artist"].to_list() == [full, full]
        assert detail["artist_statement_original"].to_list() == [short, full]
        assert song["artist"].to_list() == [full, full]
        assert detail["amount_usd"].sum() == song["amount_usd"].sum() == 13
    print("PASSED: ADA full credits in dashboard, digital income and BigQuery; originals and economics preserved")


if __name__ == "__main__":
    main()
