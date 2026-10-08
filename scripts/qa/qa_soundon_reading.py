from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from ingest_standardized_soundon import read_soundon_csv, standardize_detail_file
import ingest_standardized_soundon as ingest
import build_song_level_soundon as song
from lib.soundon_identity import add_artist_reference
from scripts.load_bigquery_release import build_detail
from app.master_contracts import artist_suggestions


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "SoundOn_royalty_monthly_statement_2026_07_My Royalty.csv"
        rows = pl.DataFrame({
            "Reporting Period": ["2026-07"] * 2, "Sales Period": ["2026-05-01~2026-05-31", "2026-06-01~2026-06-30"],
            "Final Royalty": ["12.5", "7.5"], "Units of Sold": ["100", "50"], "Currency": ["USD"] * 2,
            "Track Artists": ["La Juntada de los Artistas,Candu Dominguez", "Candu Dominguez,La Juntada de los Artistas"],
            "Track Title": ["Tu Falta De Querer"] * 2, "ISRC": ["QT5M22692699"] * 2,
            "UPC Code": ["046081037160", "640472880757"], "Track ID": ["00123", "00124"],
            "Album Title": ["Single", "Album"], "Release Date": ["2026-01-22"] * 2,
            "Royalty Type": ["RECORDING", "PUBLISHING"], "Store Name": ["Spotify", "TikTok"],
            "Sales Region": ["AR"] * 2, "Sales Type": ["STREAMING"] * 2, "Sales Sub Type": ["INDIVIDUAL", "UGC"],
        })
        rows.write_csv(path)
        raw = read_soundon_csv(path)
        assert raw["UPC Code"][0] == "046081037160" and raw["Track ID"][0] == "00123"
        detail = add_artist_reference(standardize_detail_file(raw, path, "my_royalty"))
        assert detail["statement_period"].to_list() == ["2026-07"] * 2
        assert detail["transaction_month"].to_list() == ["2026-05", "2026-06"]
        assert detail["artist_statement_original"].equals(raw["Track Artists"])
        assert detail["artist_catalog_style"].n_unique() == 1
        assert detail["artist_statement_style"].equals(raw["Track Artists"])
        assert detail["amount_usd"].sum() == 20 and detail["units"].sum() == 150
        assert detail.filter(pl.col("royalty_type") == "PUBLISHING")["amount_usd"].sum() == 7.5
        source = root / "raw.parquet"
        detail.write_parquet(source)
        original_song_paths = song.INPUT_PATH, song.OUTPUT_PATH
        song.INPUT_PATH, song.OUTPUT_PATH = source, root / "song.parquet"
        try:
            song.main()
            song_rows = pl.read_parquet(song.OUTPUT_PATH)
            assert song_rows["artist_catalog_style"].unique().to_list() == ["La Juntada de los Artistas,Candu Dominguez"]
            assert song_rows["statement_period"].unique().to_list() == ["2026-07"]
            assert song_rows["transaction_month"].n_unique() == 2
        finally:
            song.INPUT_PATH, song.OUTPUT_PATH = original_song_paths
        suggestions = artist_suggestions("QT5M22692699", source, None)
        assert suggestions["artists"] == ["La Juntada de los Artistas", "Candu Dominguez"]
        assert not suggestions["principal_uncertain"]
        target = root / "bigquery.parquet"
        build_detail(source, target, "test")
        loaded = pl.read_parquet(target)
        assert loaded["artist_statement_original"].equals(detail["artist_statement_original"])
        assert loaded["sales_period"].equals(detail["sales_period"])
        assert loaded["royalty_type"].to_list() == ["RECORDING", "PUBLISHING"]
        assert loaded["amount_usd"].sum() == 20
        conflicting = add_artist_reference(detail.with_columns(pl.lit("Candu Dominguez,Other Guest").alias("Track Artists")))
        assert conflicting["soundon_artist_credit_status"].unique().to_list() == ["conflicting_participants"]
        assert conflicting["artist_catalog_style"].null_count() == 2
        unknown = add_artist_reference(detail.with_columns(pl.lit("ARABC2600001").alias("asset_isrc")))
        assert unknown["soundon_artist_credit_status"].unique().to_list() == ["principal_unresolved"]
        for column, value in [("Sales Period", "2026-05-01~2026-06-30"), ("Sales Period", "2026-02-30~2026-02-30"),
                              ("Reporting Period", "2026-06"), ("Final Royalty", "bad"), ("Currency", "EUR"), ("ISRC", "12345")]:
            try:
                standardize_detail_file(raw.with_columns(pl.lit(value).alias(column)), path, "my_royalty")
            except ValueError:
                pass
            else:
                raise AssertionError((column, value))
        previous = root / "existing.parquet"
        previous.write_bytes(b"prior-release")
        broken = root / "SoundOn_royalty_monthly_statement_2026_08_My Royalty.csv"
        raw.write_csv(broken)
        original_paths = ingest.INPUT_DIR, ingest.OUTPUT_PATH, ingest.TEMP_DIR
        ingest.INPUT_DIR, ingest.OUTPUT_PATH, ingest.TEMP_DIR = root, previous, root / "parts"
        try:
            try:
                ingest.main()
            except RuntimeError:
                assert previous.read_bytes() == b"prior-release"
            else:
                raise AssertionError("Failed input replaced the previous mart")
        finally:
            ingest.INPUT_DIR, ingest.OUTPUT_PATH, ingest.TEMP_DIR = original_paths
    print("SoundOn reading: dates, original credits, ISRC references, UPC zeros, publishing, BigQuery and failure guards OK")


if __name__ == "__main__":
    main()
