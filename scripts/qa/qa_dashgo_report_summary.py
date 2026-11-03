"""Regression coverage for the verified DashGo association and display thresholds."""
import unittest

import polars as pl

from scripts.build_keyword_royalty_report import (
    DASHGO_GROUP_ARTIST,
    JULI_VIDEO,
    build_track_summary_lf,
    display_dataframe,
    present_dashgo_summary,
)


class DashgoSummaryTests(unittest.TestCase):
    def test_grouping_preserves_income_units_and_participant_amounts(self):
        title = "Juli Savioli -  Te Prestaría Mis Ojos (Official Video)"
        base = {
            "source": "dashgo", "account": "mawzrecords", "period_month": "2026-04",
            "transaction_month": "2026-04", "track_statement_style": title,
            "channel_id": "UCnyowdvLv8WNs7RVasOWPDA", "content_type": "ugc",
        }
        rows = [
            dict(base, amount_usd=1.94205440, units=5905),
            dict(base, amount_usd=0.20692846, units=21, video_id=JULI_VIDEO,
                 report_code=JULI_VIDEO, report_code_source="Video ID"),
            dict(base, amount_usd=0.04, units=12, track_statement_style="Pequeño"),
            dict(base, amount_usd=0, units=100, track_statement_style="Revisar"),
            dict(base, amount_usd=0.10, units=1, track_statement_style="Límite"),
            dict(base, amount_usd=-0.04, units=1, track_statement_style="Ajuste"),
            dict(base, amount_usd=0.04, units=12, track_statement_style="Otra fuente", source="fuga"),
            dict(base, amount_usd=5, units=150, asset_isrc="USANG2402075",
                 video_id=JULI_VIDEO, report_code="USANG2402075", report_code_source="ISRC"),
        ]
        summary = build_track_summary_lf(
            pl.DataFrame(rows).lazy(), include_dashgo_metadata=True,
        ).collect()
        table = display_dataframe(summary.drop("_dashgo_only", "_dashgo_video_role").to_pandas())
        table["Participante"] = 0.5
        table["Importe Participante"] = table["Ingresos USD"] * 0.5
        table.attrs["contract_formats"] = {11: "0.00%", 12: "$#,##0.00"}
        result = present_dashgo_summary(table, summary)
        video = result[result["Codigo"].eq(JULI_VIDEO)]
        self.assertEqual(len(video), 1)
        self.assertAlmostEqual(video.iloc[0]["Ingresos USD"], 2.14898286)
        self.assertEqual(video.iloc[0]["Unidades"], 5926)
        self.assertIn("Partner-provided", video.iloc[0]["Tipo de contenido"])
        self.assertEqual(result.iloc[-1]["Artista"], DASHGO_GROUP_ARTIST)
        self.assertAlmostEqual(result.iloc[-1]["Ingresos USD"], 0.04)
        self.assertTrue({"Revisar", "Límite", "Ajuste", "Otra fuente"}.issubset(result["Tema"]))
        self.assertIn("USANG2402075", result["Codigo"].tolist())
        for column in ("Ingresos USD", "Unidades", "Importe Participante"):
            self.assertAlmostEqual(result[column].sum(), table[column].sum())
