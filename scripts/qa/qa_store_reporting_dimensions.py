from __future__ import annotations

import sys
from pathlib import Path

import polars as pl


BASE = Path(__file__).resolve().parents[2]
SCRIPTS = BASE / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib.store_taxonomy import (  # noqa: E402
    NOT_REPORTED,
    add_store_dimensions,
    build_normalized_store_summary,
    ensure_store_dimensions,
)


CASES = [
    {
        "case": "ada_spotify_subscription",
        "source": "ada",
        "Digital Service Provider(DSP)": "Spotify",
        "Dist Chan Desc": "Subscription",
        "expected_dsp": "Spotify",
        "expected_monetization": "Premium",
        "expected_origin": "Audio / Master",
    },
    {
        "case": "ada_youtube_ad",
        "source": "ada",
        "Digital Service Provider(DSP)": "YouTube",
        "Dist Chan Desc": "Ad Supported",
        "expected_dsp": "YouTube",
        "expected_monetization": "Ads",
        "expected_origin": NOT_REPORTED,
    },
    {
        "case": "ada_youtube_music",
        "source": "ada",
        "Digital Service Provider(DSP)": "YouTube Music",
        "Dist Chan Desc": "Subscription",
        "expected_dsp": "YouTube",
        "expected_monetization": "Premium",
        "expected_origin": "Music / Art Track",
    },
    {
        "case": "ada_audit_recovery",
        "source": "ada",
        "Digital Service Provider(DSP)": "Spotify",
        "Dist Chan Desc": "Audit Recovery",
        "expected_dsp": "Spotify",
        "expected_monetization": "Adjustment",
        "expected_origin": "Audio / Master",
    },
    {
        "case": "dashgo_family",
        "source": "dashgo",
        "store_name": "Spotify",
        "Use Type": "FAM6",
        "expected_dsp": "Spotify",
        "expected_monetization": "Premium",
        "expected_origin": "Audio / Master",
    },
    {
        "case": "dashgo_pds",
        "source": "dashgo",
        "store_name": "Spotify",
        "Use Type": "PDS",
        "expected_dsp": "Spotify",
        "expected_monetization": NOT_REPORTED,
        "expected_origin": "Audio / Master",
    },
    {
        "case": "dashgo_youtube_ugc",
        "source": "dashgo",
        "store_name": "Youtube Premium",
        "Use Type": "UGC",
        "expected_dsp": "YouTube",
        "expected_monetization": "Premium",
        "expected_origin": "UGC / Content ID",
    },
    {
        "case": "fuga_youtube_channel_ads",
        "source": "fuga",
        "DSP": "Youtube Ad Supported",
        "Sale Store Name": "YouTube Channel Income",
        "Sale User Type": "Ad-supported",
        "expected_dsp": "YouTube",
        "expected_monetization": "Ads",
        "expected_origin": "Video / Channel",
    },
    {
        "case": "fuga_tiktok_partner",
        "source": "fuga",
        "DSP": "TikTok",
        "Sale Store Name": "TikTok Inc.",
        "Sale User Type": "Partner-provided",
        "expected_dsp": "TikTok",
        "expected_monetization": NOT_REPORTED,
        "expected_origin": "Audio Library / Partner Provided",
    },
    {
        "case": "fuga_tiktok_ugc",
        "source": "fuga",
        "DSP": "TikTok",
        "Sale Store Name": "TikTok Inc.",
        "Sale User Type": "User generated content",
        "expected_dsp": "TikTok",
        "expected_monetization": NOT_REPORTED,
        "expected_origin": "UGC / Content ID",
    },
    {
        "case": "onerpm_spotify_plain",
        "source": "onerpm",
        "Store": "Spotify",
        "source_sheet": "Masters",
        "expected_dsp": "Spotify",
        "expected_monetization": "Premium",
        "expected_origin": "Audio / Master",
    },
    {
        "case": "onerpm_youtube_plain_master",
        "source": "onerpm",
        "Store": "YouTube",
        "source_sheet": "Masters",
        "expected_dsp": "YouTube",
        "expected_monetization": "Ads",
        "expected_origin": NOT_REPORTED,
    },
    {
        "case": "onerpm_youtube_channel_premium",
        "source": "onerpm",
        "Store": "Youtube Premium",
        "source_sheet": "Youtube Channels",
        "expected_dsp": "YouTube",
        "expected_monetization": "Premium",
        "expected_origin": "Video / Channel",
    },
    {
        "case": "orchard_art_track_ads",
        "source": "orchard",
        "STORE_1": "YouTube Content ID",
        "TRANSACTION TYPE": "Ad Supported Audio Streams from Art Track Videos",
        "expected_dsp": "YouTube",
        "expected_monetization": "Ads",
        "expected_origin": "Music / Art Track",
    },
    {
        "case": "orchard_ugc_premium",
        "source": "orchard",
        "STORE_1": "YouTube Art Tracks & Music Videos",
        "TRANSACTION TYPE": "Subscription Audio Streams from UGC",
        "expected_dsp": "YouTube",
        "expected_monetization": "Premium",
        "expected_origin": "UGC / Content ID",
    },
    {
        "case": "altafonte_legacy",
        "source": "orchard",
        "statement_type": "altafonte_legacy",
        "expected_dsp": NOT_REPORTED,
        "expected_monetization": NOT_REPORTED,
        "expected_origin": NOT_REPORTED,
    },
    {
        "case": "soundon_spotify_ads",
        "source": "soundon",
        "Store Name": "Spotify",
        "Sales Sub Type": "AD_SUPPORTED",
        "expected_dsp": "Spotify",
        "expected_monetization": "Ads",
        "expected_origin": "Audio / Master",
    },
    {
        "case": "soundon_youtube_combined",
        "source": "soundon",
        "Store Name": "YouTube Music / Content ID",
        "Sales Sub Type": "INDIVIDUAL",
        "expected_dsp": "YouTube",
        "expected_monetization": "Premium",
        "expected_origin": NOT_REPORTED,
    },
    {
        "case": "soundon_tiktok_pgc",
        "source": "soundon",
        "Store Name": "TikTok",
        "Sales Sub Type": "PGC",
        "expected_dsp": "TikTok",
        "expected_monetization": NOT_REPORTED,
        "expected_origin": "Audio Library / Partner Provided",
    },
]


def validate_reduced_preclassified_frame() -> None:
    frame = pl.DataFrame([
        {
            "source": "fuga",
            "amount_usd": 10.0,
            "units": 100,
            "dsp_normalized": "YouTube",
            "monetization_normalized": "Ads",
            "content_origin_normalized": "Video / Channel",
            "classification_status": "exact",
            "plan_normalized": "Individual",
        },
        {
            "source": "onerpm",
            "amount_usd": 20.0,
            "units": 200,
            "dsp_normalized": "Spotify",
            "monetization_normalized": "Premium",
            "content_origin_normalized": "Audio / Master",
            "classification_status": None,
            "plan_normalized": "Family",
        },
    ])
    normalized = ensure_store_dimensions(frame.lazy(), set(frame.columns)).collect()

    if "plan_normalized" in normalized.columns:
        raise AssertionError("Una proyeccion reducida debe eliminar Plan sin reclasificar")
    actual = normalized.select([
        "dsp_normalized",
        "monetization_normalized",
        "content_origin_normalized",
        "classification_status",
        "store_report_label",
    ]).rows()
    expected = [
        ("YouTube", "Ads", "Video / Channel", "exact", "YouTube"),
        ("Spotify", "Premium", "Audio / Master", "exact", "Spotify"),
    ]
    if actual != expected:
        raise AssertionError(f"La proyeccion reducida reinterpretó dimensiones: {actual}")

    summary = build_normalized_store_summary(
        frame.lazy(),
        set(frame.columns),
        include_rows=True,
    ).collect()
    summary_keys = set(summary.select([
        "source",
        "dsp_normalized",
        "monetization_normalized",
        "content_origin_normalized",
    ]).rows())
    expected_keys = {
        ("fuga", "YouTube", "Ads", "Video / Channel"),
        ("onerpm", "Spotify", "Premium", "Audio / Master"),
    }
    if summary_keys != expected_keys:
        raise AssertionError(f"El resumen reinterpretó dimensiones resueltas: {summary_keys}")
    if abs(float(summary["amount_usd"].sum()) - 30.0) > 1e-9:
        raise AssertionError("El resumen reducido cambio el total de ingresos")


def main() -> None:
    validate_reduced_preclassified_frame()

    rows = []
    for index, case in enumerate(CASES, start=1):
        row = dict(case)
        row["amount_usd"] = float(index)
        row["units"] = index
        rows.append(row)

    frame = pl.from_dicts(rows, infer_schema_length=None)
    classified = add_store_dimensions(frame.lazy(), set(frame.columns)).collect()
    if "plan_normalized" in classified.columns:
        raise AssertionError("La taxonomia nueva no debe producir plan_normalized")

    for row in classified.iter_rows(named=True):
        expected = (
            row["expected_dsp"],
            row["expected_monetization"],
            row["expected_origin"],
        )
        actual = (
            row["dsp_normalized"],
            row["monetization_normalized"],
            row["content_origin_normalized"],
        )
        if actual != expected:
            raise AssertionError(f"{row['case']}: {actual} != {expected}")

    summary = build_normalized_store_summary(
        classified.lazy(),
        set(classified.columns),
        include_rows=True,
    ).collect()
    if "plan_normalized" in summary.columns:
        raise AssertionError("El resumen no debe agrupar ni presentar Plan")
    if abs(float(summary["amount_usd"].sum()) - float(classified["amount_usd"].sum())) > 1e-9:
        raise AssertionError("El resumen cambio el total de ingresos")
    if abs(float(summary["units"].sum()) - float(classified["units"].sum())) > 1e-9:
        raise AssertionError("El resumen cambio el total de unidades")

    print(
        f"OK: {len(CASES)} casos rectores, proyeccion reducida "
        "y reconciliacion sin Plan."
    )


if __name__ == "__main__":
    main()
