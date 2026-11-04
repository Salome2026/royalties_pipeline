"""No artist-specific identity inference in report presentation."""
import unittest

import polars as pl

from scripts.build_keyword_royalty_report import (
    DASHGO_GROUP_ARTIST,
    build_track_summary_lf,
    display_dataframe,
    present_dashgo_summary,
)


class DashgoSummaryTests(unittest.TestCase):
    def table(self, rows):
        summary = build_track_summary_lf(
            pl.DataFrame(rows).lazy(), include_dashgo_metadata=True,
        ).collect()
        table = display_dataframe(summary.drop("_dashgo_only").to_pandas())
        return table, summary

    def test_previously_special_cased_video_does_not_absorb_unidentified_ads(self):
        # Real witnesses for the removed exception, including its original scope.
        video = "hSW8SzhOfHQ"
        base = {
            "source": "dashgo", "account": "mawzrecords", "period_month": "2026-04",
            "transaction_month": "2026-04",
            "track_statement_style": "Juli Savioli -  Te Prestaría Mis Ojos (Official Video)",
            "channel_id": "UCnyowdvLv8WNs7RVasOWPDA", "dsp_normalized": "YouTube",
            "content_type": None,
        }
        rows = [
            dict(base, amount_usd=1.94205440, units=5905,
                 monetization_normalized="Ads", content_origin_normalized="No informado"),
            dict(base, amount_usd=0.20692846, units=21, video_id=video,
                 report_code=video, report_code_source="Video ID",
                 monetization_normalized="Premium",
                 content_origin_normalized="Audio Library / Partner Provided"),
        ]
        table, summary = self.table(rows)
        has_code = table["Codigo"].eq(video)
        table["Participante"] = [0.3 if value else None for value in has_code]
        table["Importe Participante"] = [0.062078538 if value else None for value in has_code]
        table.attrs["contract_formats"] = {11: "0.00%", 12: "$#,##0.00"}

        result = present_dashgo_summary(table, summary)

        self.assertEqual(len(result), 2)
        unidentified = result[result["Codigo"].isna()]
        identified = result[result["Codigo"].eq(video)]
        self.assertEqual(len(unidentified), 1)
        self.assertEqual(len(identified), 1)
        self.assertAlmostEqual(unidentified.iloc[0]["Ingresos USD"], 1.94205440)
        self.assertAlmostEqual(identified.iloc[0]["Ingresos USD"], 0.20692846)
        self.assertEqual(unidentified.iloc[0]["Unidades"], 5905)
        self.assertEqual(identified.iloc[0]["Unidades"], 21)
        self.assertTrue(unidentified["Importe Participante"].isna().all())
        self.assertAlmostEqual(identified.iloc[0]["Importe Participante"], 0.062078538)
        self.assertTrue(result["Tipo de contenido"].equals(table["Tipo de contenido"]))
        for column in ("Ingresos USD", "Unidades", "Importe Participante"):
            self.assertAlmostEqual(result[column].sum(), table[column].sum())

    def test_same_title_different_native_recordings_remain_separate(self):
        base = {"source": "dashgo", "account": "mawzrecords", "period_month": "2026-04",
                "track_statement_style": "Same title", "artist_statement_style": "Same artist",
                "amount_usd": 1.0, "units": 10}
        table, summary = self.table([
            dict(base, asset_isrc="ARABC2600001"),
            dict(base, asset_isrc="ARABC2600002"),
            dict(base, asset_isrc=None),
        ])
        result = present_dashgo_summary(table, summary)
        self.assertEqual(len(result), 3)
        self.assertEqual(set(result["Codigo"].dropna()), {"ARABC2600001", "ARABC2600002"})
        self.assertEqual(result["Codigo"].isna().sum(), 1)

    def test_existing_small_income_presentation_preserves_measures(self):
        base = {"source": "dashgo", "account": "mawzrecords", "period_month": "2026-04"}
        rows = [
            dict(base, amount_usd=0.04, units=12, track_statement_style="Pequeño"),
            dict(base, amount_usd=0, units=100, track_statement_style="Revisar"),
            dict(base, amount_usd=0.10, units=1, track_statement_style="Límite"),
            dict(base, amount_usd=-0.04, units=1, track_statement_style="Ajuste"),
            dict(base, amount_usd=0.04, units=12, track_statement_style="Otra fuente", source="fuga"),
        ]
        table, summary = self.table(rows)
        table["Participante"] = 0.5
        table["Importe Participante"] = table["Ingresos USD"] * 0.5
        table.attrs["contract_formats"] = {11: "0.00%", 12: "$#,##0.00"}
        result = present_dashgo_summary(table, summary)
        self.assertEqual(result.iloc[-1]["Artista"], DASHGO_GROUP_ARTIST)
        self.assertAlmostEqual(result.iloc[-1]["Ingresos USD"], 0.04)
        self.assertTrue({"Revisar", "Límite", "Ajuste", "Otra fuente"}.issubset(result["Tema"]))
        for column in ("Ingresos USD", "Unidades", "Importe Participante"):
            self.assertAlmostEqual(result[column].sum(), table[column].sum())


if __name__ == "__main__":
    unittest.main()
