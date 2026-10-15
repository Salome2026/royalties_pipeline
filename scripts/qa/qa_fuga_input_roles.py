from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch
import polars as pl
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build_song_level_fuga as song
from ingest_standardized_fuga import is_economic_statement,standardize_fuga_file

class FugaInputRoleTests(unittest.TestCase):
    def test_regular_and_correction_are_economic_but_extended_is_not(self):
        for filename in ["October2026_INDYANA-royalty_product_and_asset.csv", "YouTubeCorrection_INDYANA-ROYALTY_PRODUCT_AND_ASSET.CSV"]:
            self.assertTrue(is_economic_statement(Path(filename)))
        for filename in ["October2026_INDYANA-youtube_extended.csv", "unknown.csv"]:
            self.assertFalse(is_economic_statement(Path(filename)))

    def test_direct_standardization_of_extended_cannot_duplicate_income(self):
        with self.assertRaisesRegex(ValueError,"no es un statement economico adicional"):
            standardize_fuga_file(pl.DataFrame({"Reported Royalty":[1]}),Path("October2026_INDYANA-youtube_extended.csv"),"regular","2026-10","filename","")

    def test_product_revenue_keeps_release_identity_without_inventing_isrc(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"native.parquet";target=Path(directory)/"songs.parquet"
            pl.DataFrame({
                "source":["fuga"],"account":["indyana_records"],"statement_type":["regular"],
                "asset_isrc":[None],"video_id":[None],"asset_title_statement":[None],"asset_artist_statement":[None],
                "transaction_month":["2026-06"],"amount_usd":[0.439761],"net_amount_eur":[0.392],
                "asset_quantity_num":[None],"video_id_source":[None],"asset_product_type":["Product"],
                "product_upc":["8721416408410"],"product_title_statement":["Guarache"],
                "product_artist_statement":["Dj Plaga, John Eric and Santiago Berrio"],
            }).write_parquet(source)
            with patch.object(song,"INPUT_PATH",source),patch.object(song,"OUTPUT_PATH",target):song.main()
            result=pl.read_parquet(target).to_dicts()[0]
            self.assertEqual(result["amount_usd"],0.439761)
            self.assertIsNone(result["asset_isrc"])
            self.assertEqual(result["product_upc"],"8721416408410")
            self.assertEqual(result["track_statement_style"],"Guarache")
            self.assertEqual(result["content_type"],"product")

if __name__ == "__main__": unittest.main()
