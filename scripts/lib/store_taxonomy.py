from __future__ import annotations

import polars as pl


DIMENSION_COLUMNS = [
    "dsp_normalized",
    "monetization_normalized",
    "content_origin_normalized",
    "plan_normalized",
    "classification_status",
    "store_report_label",
]


def _text(columns: set[str], name: str) -> pl.Expr:
    if name not in columns:
        return pl.lit("")
    return pl.col(name).cast(pl.Utf8, strict=False).fill_null("").str.strip_chars()


def _joined(columns: set[str], names: list[str]) -> pl.Expr:
    values = [_text(columns, name) for name in names if name in columns]
    if not values:
        return pl.lit("")
    return pl.concat_str(values, separator=" | ").str.to_lowercase()


def _first_text(columns: set[str], names: list[str]) -> pl.Expr:
    values = []
    for name in names:
        if name not in columns:
            continue
        value = _text(columns, name)
        values.append(pl.when(value == "").then(None).otherwise(value))
    if not values:
        return pl.lit("")
    return pl.coalesce(values).fill_null("")


def _contains_any(value: pl.Expr, terms: list[str]) -> pl.Expr:
    result = pl.lit(False)
    for term in terms:
        result = result | value.str.contains(term, literal=True)
    return result


def add_store_dimensions(frame: pl.LazyFrame, columns: set[str] | None = None) -> pl.LazyFrame:
    """Add report dimensions without changing raw distributor fields or amounts."""
    columns = columns or set(frame.collect_schema().names())
    source = _text(columns, "source").str.to_lowercase()
    source_sheet = _text(columns, "source_sheet").str.to_lowercase()
    statement_type = _text(columns, "statement_type").str.to_lowercase()

    store_evidence = _joined(columns, [
        "dsp",
        "DSP",
        "store_name",
        "Store Name",
        "Sale Store Name",
        "Store",
        "STORE",
        "service_detail",
        "SERVICE DETAIL",
    ])
    store_primary = _first_text(columns, [
        "dsp",
        "DSP",
        "store_name",
        "Store Name",
        "Sale Store Name",
        "Store",
        "STORE",
        "service_detail",
        "SERVICE DETAIL",
    ])
    usage_evidence = _joined(columns, [
        "sale_user_type",
        "Sale User Type",
        "sales_sub_type",
        "Sales Sub Type",
        "use_type",
        "Use Type",
        "sale_type",
        "Sale Type",
        "Sales Type",
        "TRANSACTION TYPE",
        "TRANSACTION SUBTYPE",
        "Product Type",
        "product_type",
        "Royalty Type",
        "ROYALTY TYPE",
    ])
    channel_evidence = _joined(columns, [
        "Sale Store Name",
        "Store Name",
        "store_name",
        "Store",
        "STORE",
        "service_detail",
        "SERVICE DETAIL",
        "source_sheet",
    ])
    all_evidence = pl.concat_str(
        [store_evidence, usage_evidence, source_sheet], separator=" | "
    )

    is_youtube = _contains_any(store_evidence, ["youtube", "yt audio", "yt adj"])
    is_spotify = store_evidence.str.contains("spotify", literal=True)
    is_apple = _contains_any(store_evidence, ["apple music", "itunes"])
    is_amazon = store_evidence.str.contains("amazon", literal=True)
    is_meta = _contains_any(store_evidence, ["facebook", "instagram", "meta"])
    is_tiktok = _contains_any(store_evidence, ["tiktok", "tik tok", "douyin", "capcut"])

    dsp = (
        pl.when(is_youtube).then(pl.lit("YouTube"))
        .when(is_spotify).then(pl.lit("Spotify"))
        .when(is_apple).then(pl.lit("Apple Music"))
        .when(is_amazon).then(pl.lit("Amazon Music"))
        .when(is_meta).then(pl.lit("Meta"))
        .when(is_tiktok).then(pl.lit("TikTok"))
        .when(store_evidence.str.contains("soundcloud", literal=True)).then(pl.lit("SoundCloud"))
        .when(store_evidence.str.contains("deezer", literal=True)).then(pl.lit("Deezer"))
        .when(store_evidence.str.contains("tidal", literal=True)).then(pl.lit("TIDAL"))
        .when(store_evidence.str.contains("pandora", literal=True)).then(pl.lit("Pandora"))
        .when(store_evidence.str.contains("audiomack", literal=True)).then(pl.lit("Audiomack"))
        .when(store_evidence.str.contains("qobuz", literal=True)).then(pl.lit("Qobuz"))
        .when(store_evidence.str.contains("trebel", literal=True)).then(pl.lit("Trebel"))
        .when(store_evidence.str.contains("netease", literal=True)).then(pl.lit("NetEase"))
        .when(store_evidence.str.contains("jiosaavn", literal=True)).then(pl.lit("JioSaavn"))
        .when(store_evidence.str.contains("anghami", literal=True)).then(pl.lit("Anghami"))
        .when(store_evidence.str.contains("tencent", literal=True)).then(pl.lit("Tencent Music"))
        .when(store_evidence.str.contains("kkbox", literal=True)).then(pl.lit("KKBOX"))
        .when(store_evidence.str.contains("iheartradio", literal=True) | store_evidence.str.contains("iheart radio", literal=True)).then(pl.lit("iHeartRadio"))
        .when(store_evidence.str.contains("soundtrack your brand", literal=True) | store_evidence.str.contains("soundtrack your band", literal=True)).then(pl.lit("Soundtrack Your Brand"))
        .when(store_evidence.str.contains("snap", literal=True)).then(pl.lit("Snapchat"))
        .when(store_evidence.str.contains("resso", literal=True)).then(pl.lit("Resso"))
        .when(store_evidence.str.contains("imusic", literal=True)).then(pl.lit("iMusica"))
        .when(store_evidence.str.contains("fizy", literal=True)).then(pl.lit("Fizy"))
        .when(store_evidence.str.contains("awa", literal=True)).then(pl.lit("AWA"))
        .when(store_evidence.str.contains("line music", literal=True)).then(pl.lit("LINE Music"))
        .when(store_evidence.str.contains("melon", literal=True)).then(pl.lit("Melon"))
        .when(store_primary != "").then(store_primary)
        .otherwise(pl.lit("Unknown"))
        .alias("dsp_normalized")
    )

    dashgo_use_type = _text(columns, "Use Type").str.to_uppercase()
    dashgo_spotify = (source == "dashgo") & is_spotify
    dashgo_premium = dashgo_spotify & dashgo_use_type.is_in(["P", "FAM6", "DUO"])
    dashgo_ads = dashgo_spotify & (dashgo_use_type == "A")

    is_adjustment = _contains_any(all_evidence, [
        "adjust", "correction", "dispute", "conflict", "discovery mode",
        "fraudulent", "unqualified", "deduction", "breakage",
    ])
    is_trial = _contains_any(usage_evidence, ["trial", "promo", "offer", "winback", "2for1", "3for1"])
    is_ads = _contains_any(all_evidence, ["ad-supported", "ad supported", "advertising", "amazon ads", "youtube ad"])
    is_premium = _contains_any(all_evidence, [
        "premium", "subscription", "individual", "family", "fam6", "duo",
        "student", "bundle", "paid", "prime_paid",
    ])
    is_download = _contains_any(usage_evidence, ["download", "tethered"])
    is_license = _contains_any(usage_evidence, ["synch", "license"])

    monetization = (
        pl.when(is_adjustment).then(pl.lit("Adjustment"))
        .when(dashgo_ads | is_ads).then(pl.lit("Ads"))
        .when(is_trial).then(pl.lit("Trial / Promo"))
        .when(dashgo_premium | is_premium).then(pl.lit("Premium"))
        .when(is_download).then(pl.lit("Download"))
        .when(is_license).then(pl.lit("License / Sync"))
        .otherwise(pl.lit("Unknown"))
        .alias("monetization_normalized")
    )

    plan = (
        pl.when(dashgo_spotify & (dashgo_use_type == "P")).then(pl.lit("Individual"))
        .when(dashgo_spotify & (dashgo_use_type == "FAM6")).then(pl.lit("Family"))
        .when(dashgo_spotify & (dashgo_use_type == "DUO")).then(pl.lit("Duo"))
        .when(dashgo_spotify & (dashgo_use_type == "A")).then(pl.lit("Advertising"))
        .when(_contains_any(usage_evidence, ["family", "fam6"])).then(pl.lit("Family"))
        .when(usage_evidence.str.contains("duo", literal=True)).then(pl.lit("Duo"))
        .when(usage_evidence.str.contains("student", literal=True)).then(pl.lit("Student"))
        .when(usage_evidence.str.contains("individual", literal=True)).then(pl.lit("Individual"))
        .when(usage_evidence.str.contains("bundle", literal=True)).then(pl.lit("Bundle"))
        .otherwise(pl.lit("Unknown"))
        .alias("plan_normalized")
    )

    is_short = all_evidence.str.contains("short", literal=True)
    is_manual_claim = all_evidence.str.contains("manual claim", literal=True)
    is_ugc = _contains_any(all_evidence, ["ugc", "content id", "fingerprint"])
    is_art_track = _contains_any(all_evidence, ["art track", "youtube music", "yt audio tier", "audio tier"])
    is_channel = _contains_any(channel_evidence, ["channel income", "partnered channel"])
    is_audio_library = _contains_any(all_evidence, ["audio library", "al production", "al consumption", "music sticker", "music_notes", "music on feed"])
    is_video = _contains_any(usage_evidence, ["video stream", "video view"])
    is_audio = _contains_any(usage_evidence, ["audio stream", "streaming", "stream", "download"])
    onerpm_youtube_channel = (source == "onerpm") & source_sheet.str.contains("youtube channel", literal=True)

    origin = (
        pl.when(is_short).then(pl.lit("Shorts"))
        .when(is_manual_claim).then(pl.lit("Manual Claim"))
        .when(is_ugc).then(pl.lit("UGC / Content ID"))
        .when(is_channel | onerpm_youtube_channel).then(pl.lit("Video / Channel"))
        .when(is_art_track).then(pl.lit("Music / Art Track"))
        .when(is_youtube & is_video).then(pl.lit("Video (unspecified)"))
        .when(is_youtube & is_audio).then(pl.lit("Audio / Master"))
        .when(is_audio_library).then(pl.lit("Audio Library"))
        .when(is_meta | is_tiktok).then(pl.lit("UGC / Content ID"))
        .when(dsp != "Unknown").then(pl.lit("Audio / Master"))
        .otherwise(pl.lit("Unknown"))
        .alias("content_origin_normalized")
    )

    legacy = statement_type.str.contains("altafonte", literal=True)
    enriched = frame.with_columns([dsp, monetization, origin, plan])
    status = (
        pl.when(legacy | (pl.col("dsp_normalized") == "Unknown"))
        .then(pl.lit("unknown"))
        .when(
            (pl.col("monetization_normalized") == "Unknown")
            | (pl.col("content_origin_normalized") == "Unknown")
            | (pl.col("content_origin_normalized") == "Video (unspecified)")
        )
        .then(pl.lit("partial"))
        .otherwise(pl.lit("exact"))
        .alias("classification_status")
    )
    enriched = enriched.with_columns(status)
    report_label = (
        pl.concat_str(
            [
                pl.col("dsp_normalized"),
                pl.when(pl.col("monetization_normalized") == "Unknown").then(pl.lit(None)).otherwise(pl.col("monetization_normalized")),
                pl.when(pl.col("content_origin_normalized") == "Unknown").then(pl.lit(None)).otherwise(pl.col("content_origin_normalized")),
            ],
            separator=" - ",
            ignore_nulls=True,
        )
        .alias("store_report_label")
    )
    return enriched.with_columns(report_label)
