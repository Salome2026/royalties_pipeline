"""No artist-specific identity inference in report presentation."""
import unittest
from pathlib import Path
import os
import tempfile
from unittest.mock import patch

import polars as pl

from scripts.build_keyword_royalty_report import (
    DASHGO_GROUP_ARTIST,
    build_track_summary_lf,
    display_dataframe,
    present_dashgo_summary,
)
from scripts.lib.dashgo_video_identity import compile_video_groups, with_video_groups, SUMMARY_VIDEO, SUMMARY_TITLE


def video_row(**changes):
    return {
        "source": "dashgo", "account": "account-a", "source_sheet": "detail",
        "revenue_basis": "generation", "statement_period": "2026-06",
        "transaction_month": "2026-04", "period_month": "2026-04",
        "track_statement_style": "Artista - Canción (Official Video)",
        "artist_statement_style": "Artista", "channel_id": "UC" + "a" * 22,
        "video_id": None, "asset_isrc": None, "product_upc": None, "track_id": None,
        "amount_usd": 100.0, "units": 10.0, "dsp_normalized": "YouTube",
        "monetization_normalized": "Ads", "content_origin_normalized": "No informado",
        "territory": "AR", "store_name": "Youtube AD", "content_type": None,
        **changes,
    }


def premium_row(**changes):
    return video_row(**{
        "video_id": "video-code1", "amount_usd": 10.0, "units": 2.0,
        "monetization_normalized": "Premium", "store_name": "Youtube Premium",
        "content_origin_normalized": "Audio Library / Partner Provided", **changes,
    })


def grouped_frame(rows, evidence=None):
    frame = pl.DataFrame(rows).lazy()
    groups = compile_video_groups(pl.DataFrame(evidence or rows).lazy())
    return with_video_groups(frame, groups)


class DashgoVideoIdentityTests(unittest.TestCase):
    def test_same_video_across_monetization_has_one_summary_and_unchanged_detail(self):
        rows = [video_row(), premium_row()]
        original = pl.DataFrame(rows)
        resolved = grouped_frame(rows).collect()
        self.assertTrue(resolved.select(original.columns).equals(original))
        self.assertEqual(resolved[SUMMARY_VIDEO].to_list(), ["video-code1", "video-code1"])
        summary = build_track_summary_lf(resolved.lazy(), include_identity=True).collect()
        self.assertEqual(summary.height, 1)
        self.assertEqual(summary["_report_identity"][0], "VIDEO:video-code1")
        self.assertEqual(summary["amount_usd"][0], 110.0)
        self.assertEqual(summary["units"][0], 12.0)
        self.assertEqual(resolved["monetization_normalized"].to_list(), ["Ads", "Premium"])
        self.assertEqual(resolved["content_origin_normalized"].to_list(),
                         ["No informado", "Audio Library / Partner Provided"])

    def test_rule_uses_new_artists_without_a_name_or_title_allowlist(self):
        rows = [video_row(track_statement_style="Nuevo grupo - Otra canción (Live)") ,
                premium_row(track_statement_style="Nuevo grupo - Otra canción (Live)")]
        self.assertEqual(compile_video_groups(pl.DataFrame(rows).lazy()).height, 1)

    def test_second_native_video_anywhere_in_history_vetoes_grouping(self):
        rows = [video_row(), premium_row(), premium_row(video_id="video-code2",
                asset_isrc="ARABC2600002", statement_period="2024-01")]
        self.assertTrue(compile_video_groups(pl.DataFrame(rows).lazy()).is_empty())
        rows.append(premium_row(video_id="video-code3", dsp_normalized="No informado", store_name="Unknown"))
        self.assertTrue(compile_video_groups(pl.DataFrame(rows).lazy()).is_empty())

    def test_missing_channel_account_or_different_source_does_not_match(self):
        for change in [{"channel_id": None}, {"channel_id": "UC" + "b" * 22},
                       {"account": "other"}, {"source": "fuga"}]:
            with self.subTest(change=change):
                rows = [video_row(), premium_row(**change)]
                self.assertTrue(compile_video_groups(pl.DataFrame(rows).lazy()).is_empty())

    def test_versions_accents_and_auto_generated_tokens_are_not_erased(self):
        for title in ["Artista - Canción (Official Video) - MAKING OFF",
                      "Artista - Canción (Live)", "Artista - Cancion (Official Video)"]:
            rows = [video_row(), premium_row(track_statement_style=title)]
            self.assertTrue(compile_video_groups(pl.DataFrame(rows).lazy()).is_empty())
        for title in ["Auto generated asset", "Auto generated asset - video-code1", "Artista - (Official Video)"]:
            rows = [video_row(track_statement_style=title), premium_row(track_statement_style=title)]
            self.assertTrue(compile_video_groups(pl.DataFrame(rows).lazy()).is_empty())

    def test_product_and_two_recordings_keep_their_native_identity(self):
        original = [video_row(), premium_row(),
                    video_row(asset_isrc="ARABC2600001"), video_row(asset_isrc="ARABC2600002"),
                    video_row(product_upc="123456789012"), video_row(track_id="native-asset-42")]
        resolved = grouped_frame(original).collect()
        self.assertEqual(resolved[SUMMARY_VIDEO].to_list(), ["video-code1", "video-code1", None, None, None, None])
        summary = build_track_summary_lf(resolved.lazy(), include_identity=True).collect()
        self.assertTrue({"ISRC:ARABC2600001", "ISRC:ARABC2600002"} <= set(summary["_report_identity"]))
        self.assertTrue(resolved.select(pl.DataFrame(original).columns).equals(pl.DataFrame(original)))

    def test_period_selection_uses_full_history_not_only_selected_premium_rows(self):
        evidence = [video_row(statement_period="2026-01"), premium_row(statement_period="2026-06")]
        selected = grouped_frame([evidence[0]], evidence=evidence).collect()
        self.assertEqual(selected[SUMMARY_VIDEO][0], "video-code1")
        self.assertIsNone(selected["video_id"][0])

    def test_zero_ads_units_are_part_of_the_same_identified_video(self):
        rows = [video_row(amount_usd=0.0, units=924.0), premium_row()]
        result = build_track_summary_lf(grouped_frame(rows), include_identity=True).collect()
        self.assertEqual(result.height, 1)
        self.assertEqual(result['amount_usd'][0], 10.0)
        self.assertEqual(result['units'][0], 926.0)

    def test_raw_title_takes_precedence_over_a_conflicting_display_title(self):
        rows = [video_row(**{'Track Title': 'Another recording'}), premium_row()]
        self.assertTrue(compile_video_groups(pl.DataFrame(rows).lazy()).is_empty())

    def test_invalid_native_video_is_not_repaired_by_title(self):
        rows = [video_row(video_id="invalid-id"), premium_row()]
        self.assertTrue(compile_video_groups(pl.DataFrame(rows).lazy()).is_empty())

    def test_unmatched_references_do_not_get_a_verified_title(self):
        rows = [video_row(), premium_row(), video_row(track_statement_style='Unrelated reference')]
        resolved = grouped_frame(rows).collect()
        self.assertIsNone(resolved[SUMMARY_VIDEO][-1])
        self.assertIsNone(resolved[SUMMARY_TITLE][-1])

    def test_verified_full_title_is_preferred_over_a_generic_native_caption(self):
        rows = [video_row(), premium_row(), premium_row(
            track_statement_style='Auto generated asset', amount_usd=200.0,
            catalog_key='VIDEO:video-code1')]
        summary = build_track_summary_lf(grouped_frame(rows), include_identity=True).collect()
        self.assertEqual(summary.height, 1)
        self.assertEqual(summary['track_statement_style'][0], video_row()['track_statement_style'])
        self.assertEqual(summary['amount_usd'][0], 310.0)

    def test_summary_identity_does_not_extend_contract_coverage(self):
        from app.royalty_reports.excel_contracts import reference_fragments, participant_columns
        from app.master_contract_associations import association_key
        from scripts.qa.qa_excel_contracts import snapshot, ISRC
        rows = [video_row(), premium_row()]
        original = pl.DataFrame(rows).lazy()
        resolved = grouped_frame(rows)
        state = snapshot()
        state["associations"]["included"] = {
            association_key("VIDEO", "video-code1", "dashgo", "account-a"): [ISRC]}
        before = build_track_summary_lf(original, include_identity=True).collect()
        after = build_track_summary_lf(resolved, include_identity=True).collect()
        names, first = participant_columns(before, reference_fragments(original), state, [], "all")
        names_after, second = participant_columns(after, reference_fragments(resolved), state, [], "all")
        self.assertEqual(set(names), set(names_after))
        for name in names:
            expected = sum(row[name][1] for row in first if row[name] is not None)
            actual = sum(row[name][1] for row in second if row[name] is not None)
            self.assertAlmostEqual(expected, actual)
        self.assertAlmostEqual(second[0]["Artista"][1], 0.6)
        self.assertAlmostEqual(second[0]["Artista"][0], 0.6 / 110.0)

    def test_public_builder_changes_only_track_summary_for_both_time_axes(self):
        from scripts import build_keyword_royalty_report as report
        policy = {"schema_version": 1, "policy_version": 1, "entries": [{
            "source": "dashgo", "account": "account-a", "sheet_rules": {
                "detail": {"catalog_view": True, "statement_view": True, "revenue_basis": "generation"}}}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw, song = root / "raw.parquet", root / "song.parquet"
            pl.DataFrame([video_row(), premium_row()]).write_parquet(raw)
            song.write_bytes(raw.read_bytes())
            env = {"VPO_CATALOG_MASTER_PATH": str(root / "absent"), "VPO_CATALOG_STATUS_PATH": str(root / "status")}
            with patch.dict(os.environ, env), patch.dict(
                report.filter_reportable_generation.__globals__,
                {"load_distributor_policy_document": lambda: policy},
            ):
                for basis in ["statement_period", "transaction_month"]:
                    args = dict(keywords=["Artista"], mode="any", raw_limit=100, song_path=song,
                                standardized_path=raw, period_basis=basis, detail_mode="full")
                    before = report.build_report_tables(**args, _dashgo_video_groups=pl.DataFrame())
                    after = report.build_report_tables(**args)
                    self.assertEqual(len(before["resumen por tema"]), 2)
                    self.assertEqual(len(after["resumen por tema"]), 1)
                    for name in before:
                        if name in {"resumen por tema", "resumen general"}:
                            continue
                        left, right = before[name], after[name]
                        if name == "detalle":
                            # Existing catalog joins do not promise source-row order.
                            left = left.sort_values(["Monetizacion", "Ingresos USD"]).reset_index(drop=True)
                            right = right.sort_values(["Monetizacion", "Ingresos USD"]).reset_index(drop=True)
                        self.assertTrue(left.equals(right), (basis, name))
                    self.assertEqual(len(after["detalle"]), 2)
                    from scripts.qa.qa_excel_contracts import snapshot, ISRC
                    from app.master_contract_associations import association_key
                    state = snapshot()
                    state["associations"]["included"] = {
                        association_key("VIDEO", "video-code1", "dashgo", "account-a"): [ISRC]}
                    before_contracts = report.build_report_tables(**args, contract_snapshot=state,
                                                                 _dashgo_video_groups=pl.DataFrame())
                    after_contracts = report.build_report_tables(**args, contract_snapshot=state)
                    for name in before_contracts["resumen por tema"].columns:
                        if name.startswith("Importe "):
                            self.assertAlmostEqual(before_contracts["resumen por tema"][name].sum(),
                                                   after_contracts["resumen por tema"][name].sum(), msg=(basis, name))
                    self.assertAlmostEqual(after_contracts["resumen por tema"]["Importe Artista"].sum(), 0.6)


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
