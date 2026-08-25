from __future__ import annotations

import polars as pl


NOT_REPORTED = "No informado"

DIMENSION_COLUMNS = [
    "dsp_normalized",
    "monetization_normalized",
    "content_origin_normalized",
    "classification_status",
    "store_report_label",
]

STORE_SUMMARY_GROUP_COLUMNS = [
    "dsp_normalized",
    "monetization_normalized",
    "content_origin_normalized",
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
    """Apply the single business taxonomy without changing raw fields or amounts."""
    columns = columns or set(frame.collect_schema().names())
    stale_dimensions = set(DIMENSION_COLUMNS) | {"plan_normalized"}
    existing_stale = sorted(stale_dimensions & columns)
    if existing_stale:
        frame = frame.drop(existing_stale)
        columns = columns - set(existing_stale)

    source = _text(columns, "source").str.to_lowercase()
    source_sheet = _text(columns, "source_sheet").str.to_lowercase()
    statement_type = _text(columns, "statement_type").str.to_lowercase()

    ada_store = _first_text(columns, ["Digital Service Provider(DSP)", "dsp", "DSP"])
    dashgo_store = _first_text(columns, ["store_name", "Store"])
    fuga_store = _first_text(columns, ["dsp_1", "dsp", "DSP", "Sale Store Name"])
    onerpm_store = _first_text(columns, ["Store", "store_name"])
    orchard_store = _first_text(columns, ["STORE_1", "STORE", "service_detail", "SERVICE DETAIL"])
    soundon_store = _first_text(columns, ["Store Name", "store_name"])
    generic_store = _first_text(columns, [
        "dsp", "dsp_1", "DSP", "store_name", "Store Name", "Sale Store Name",
        "Store", "STORE_1", "STORE", "service_detail", "SERVICE DETAIL",
        "Digital Service Provider(DSP)",
    ])
    store_primary = (
        pl.when(source == "ada").then(ada_store)
        .when(source == "dashgo").then(dashgo_store)
        .when(source == "fuga").then(fuga_store)
        .when(source == "onerpm").then(onerpm_store)
        .when(source == "orchard").then(orchard_store)
        .when(source == "soundon").then(soundon_store)
        .otherwise(generic_store)
    )
    store_lower = store_primary.str.to_lowercase()

    is_youtube = _contains_any(store_lower, ["youtube", "yt audio", "yt adj"])
    is_spotify = store_lower.str.contains("spotify", literal=True)
    is_apple = _contains_any(store_lower, ["apple music", "itunes"])
    is_amazon = store_lower.str.contains("amazon", literal=True)
    is_meta = _contains_any(store_lower, ["facebook", "instagram", "meta"])
    is_tiktok = _contains_any(store_lower, ["tiktok", "tik tok", "douyin", "capcut"])
    is_social = is_meta | is_tiktok | store_lower.str.contains("snap", literal=True)

    dsp = (
        pl.when(is_youtube).then(pl.lit("YouTube"))
        .when(is_spotify).then(pl.lit("Spotify"))
        .when(is_apple).then(pl.lit("Apple Music"))
        .when(is_amazon).then(pl.lit("Amazon Music"))
        .when(is_meta).then(pl.lit("Meta"))
        .when(is_tiktok).then(pl.lit("TikTok"))
        .when(store_lower.str.contains("soundcloud", literal=True)).then(pl.lit("SoundCloud"))
        .when(store_lower.str.contains("deezer", literal=True)).then(pl.lit("Deezer"))
        .when(store_lower.str.contains("tidal", literal=True)).then(pl.lit("TIDAL"))
        .when(store_lower.str.contains("pandora", literal=True)).then(pl.lit("Pandora"))
        .when(store_lower.str.contains("audiomack", literal=True)).then(pl.lit("Audiomack"))
        .when(store_lower.str.contains("qobuz", literal=True)).then(pl.lit("Qobuz"))
        .when(store_lower.str.contains("trebel", literal=True)).then(pl.lit("Trebel"))
        .when(store_lower.str.contains("netease", literal=True)).then(pl.lit("NetEase"))
        .when(store_lower.str.contains("jiosaavn", literal=True)).then(pl.lit("JioSaavn"))
        .when(store_lower.str.contains("anghami", literal=True)).then(pl.lit("Anghami"))
        .when(store_lower.str.contains("tencent", literal=True)).then(pl.lit("Tencent Music"))
        .when(store_lower.str.contains("kkbox", literal=True)).then(pl.lit("KKBOX"))
        .when(_contains_any(store_lower, ["iheartradio", "iheart radio"])).then(pl.lit("iHeartRadio"))
        .when(_contains_any(store_lower, ["soundtrack your brand", "soundtrack your band"])).then(pl.lit("Soundtrack Your Brand"))
        .when(store_lower.str.contains("snap", literal=True)).then(pl.lit("Snapchat"))
        .when(store_lower.str.contains("resso", literal=True)).then(pl.lit("Resso"))
        .when(store_lower.str.contains("imusic", literal=True)).then(pl.lit("iMusica"))
        .when(store_lower.str.contains("fizy", literal=True)).then(pl.lit("Fizy"))
        .when(store_lower.str.contains("awa", literal=True)).then(pl.lit("AWA"))
        .when(store_lower.str.contains("line music", literal=True)).then(pl.lit("LINE Music"))
        .when(store_lower.str.contains("melon", literal=True)).then(pl.lit("Melon"))
        .when(store_primary != "").then(store_primary)
        .otherwise(pl.lit(NOT_REPORTED))
        .alias("dsp_normalized")
    )

    ada_channel = _text(columns, "Dist Chan Desc").str.to_lowercase()
    dashgo_use = _text(columns, "Use Type").str.to_uppercase()
    fuga_user = _first_text(columns, ["sale_user_type", "Sale User Type"]).str.to_lowercase()
    onerpm_store_lower = onerpm_store.str.to_lowercase()
    orchard_type = _joined(columns, ["TRANSACTION TYPE", "TRANSACTION SUBTYPE", "ROYALTY TYPE"])
    soundon_subtype = _first_text(columns, ["sales_sub_type", "Sales Sub Type"]).str.to_uppercase()

    all_usage = _joined(columns, [
        "Dist Chan Desc", "Price Desc", "sale_user_type", "Sale User Type",
        "sales_sub_type", "Sales Sub Type", "use_type", "Use Type",
        "sale_type", "Sale Type", "Sales Type", "TRANSACTION TYPE",
        "TRANSACTION SUBTYPE", "Product Type", "product_type", "Royalty Type",
        "ROYALTY TYPE", "Store", "Store Name", "Sale Store Name", "STORE_1",
        "SERVICE DETAIL", "service_detail",
    ])
    common_adjustment = _contains_any(all_usage, [
        "adjust", "correction", "dispute", "conflict", "discovery mode",
        "fraudulent", "unqualified", "deduction", "breakage", "audit recovery",
        "payment top - up", "payment top-up",
    ])
    common_trial = _contains_any(all_usage, ["trial", "promo", "offer", "winback", "2for1", "3for1"])
    common_ads = _contains_any(all_usage, ["ad-supported", "ad supported", "ad_supported", "advertising", "ad channel", "youtube ad"])
    common_premium = _contains_any(all_usage, ["premium", "subscription", "individual", "family", "fam6", "duo", "student", "bundle", "prime_paid"])
    common_download = _contains_any(all_usage, ["download", "tethered"])
    common_license = _contains_any(all_usage, ["synch", "sync", "license"])

    dashgo_spotify = (source == "dashgo") & is_spotify
    dashgo_premium = dashgo_spotify & dashgo_use.is_in(["P", "FAM6", "DUO"])
    dashgo_ads = dashgo_spotify & (dashgo_use == "A")
    dashgo_youtube_premium = (source == "dashgo") & dashgo_store.str.to_lowercase().str.contains("youtube premium", literal=True)
    dashgo_youtube_ads = (source == "dashgo") & dashgo_store.str.to_lowercase().str.contains("youtube ad", literal=True)
    onerpm_premium = (source == "onerpm") & (
        (onerpm_store_lower == "spotify")
        | onerpm_store_lower.str.contains("youtube premium", literal=True)
    )
    onerpm_ads = (source == "onerpm") & (
        onerpm_store_lower.str.contains("spotify ad supported", literal=True)
        | (onerpm_store_lower == "youtube")
    )
    onerpm_adjustment = (source == "onerpm") & onerpm_store_lower.str.contains("spotify discovery mode", literal=True)
    soundon_premium = (source == "soundon") & soundon_subtype.is_in(["INDIVIDUAL", "FAMILY", "DUO", "STUDENT", "BUNDLE"])
    soundon_ads = (source == "soundon") & (soundon_subtype == "AD_SUPPORTED")
    soundon_trial = (source == "soundon") & (soundon_subtype == "TRIAL")

    monetization = (
        pl.when(common_adjustment | onerpm_adjustment).then(pl.lit("Adjustment"))
        .when(common_ads | dashgo_ads | dashgo_youtube_ads | onerpm_ads | soundon_ads).then(pl.lit("Ads"))
        .when(common_trial | soundon_trial).then(pl.lit("Trial / Promo"))
        .when(common_premium | dashgo_premium | dashgo_youtube_premium | onerpm_premium | soundon_premium).then(pl.lit("Premium"))
        .when(common_download).then(pl.lit("Download"))
        .when(common_license).then(pl.lit("License / Sync"))
        .otherwise(pl.lit(NOT_REPORTED))
        .alias("monetization_normalized")
    )

    dashgo_partner = (source == "dashgo") & dashgo_use.str.to_lowercase().str.contains("partner-provided", literal=True)
    dashgo_ugc = (source == "dashgo") & dashgo_use.str.to_lowercase().str.contains("ugc", literal=True)
    fuga_store_detail = _first_text(columns, ["Sale Store Name", "store_name"]).str.to_lowercase()
    fuga_partner = (source == "fuga") & fuga_user.str.contains("partner-provided", literal=True)
    fuga_ugc = (source == "fuga") & fuga_user.str.contains("user generated", literal=True)
    soundon_ugc = (source == "soundon") & (soundon_subtype == "UGC")
    soundon_partner = (source == "soundon") & soundon_subtype.is_in(["PGC", "PARTNER_PROVIDED", "PARTNER-PROVIDED"])

    is_short = _contains_any(all_usage, ["short", "short-form"])
    is_manual_claim = all_usage.str.contains("manual claim", literal=True)
    is_audio_library = _contains_any(all_usage, [
        "audio library", "al production", "al consumption", "music sticker",
        "music_notes", "music on feed",
    ])
    is_content_id = _contains_any(all_usage, ["ugc", "content id", "fingerprint", "user generated"])
    is_channel = _contains_any(all_usage, ["channel income", "partnered channel"])
    onerpm_channel = (source == "onerpm") & source_sheet.str.contains("youtube channel", literal=True)
    onerpm_short = (source == "onerpm") & onerpm_store_lower.str.contains("short", literal=True)
    onerpm_audio_tier = (source == "onerpm") & onerpm_store_lower.str.contains("audio tier", literal=True)
    orchard_art_track = (source == "orchard") & orchard_type.str.contains("art track", literal=True)
    orchard_channel = (source == "orchard") & orchard_type.str.contains("partnered channel", literal=True)
    orchard_ugc = (source == "orchard") & orchard_type.str.contains("ugc", literal=True)
    orchard_short = (source == "orchard") & orchard_type.str.contains("short-form", literal=True)
    ada_youtube_music = (source == "ada") & ada_store.str.to_lowercase().str.contains("youtube music", literal=True)
    dashgo_audio_tier = (source == "dashgo") & dashgo_store.str.to_lowercase().str.contains("audio tier", literal=True)

    explicit_ugc = dashgo_ugc | orchard_ugc | fuga_ugc | soundon_ugc | (
        is_content_id & ~((source == "soundon") & is_youtube) & ~orchard_art_track
    )
    explicit_partner = dashgo_partner | fuga_partner | soundon_partner | is_audio_library

    origin = (
        pl.when(statement_type.str.contains("altafonte", literal=True)).then(pl.lit(NOT_REPORTED))
        .when(is_short | onerpm_short | orchard_short).then(pl.lit("Shorts"))
        .when(is_manual_claim).then(pl.lit("Manual Claim"))
        .when(is_channel | onerpm_channel | orchard_channel).then(pl.lit("Video / Channel"))
        .when(orchard_art_track | ada_youtube_music | dashgo_audio_tier | onerpm_audio_tier).then(pl.lit("Music / Art Track"))
        .when(explicit_ugc).then(pl.lit("UGC / Content ID"))
        .when(explicit_partner).then(pl.lit("Audio Library / Partner Provided"))
        .when((source == "fuga") & fuga_store_detail.str.contains("art track", literal=True)).then(pl.lit("Music / Art Track"))
        .when((source == "fuga") & (fuga_store_detail == "youtube music")).then(pl.lit("Music / Art Track"))
        .when(is_youtube).then(pl.lit(NOT_REPORTED))
        .when(is_social).then(pl.lit(NOT_REPORTED))
        .when(store_primary != "").then(pl.lit("Audio / Master"))
        .otherwise(pl.lit(NOT_REPORTED))
        .alias("content_origin_normalized")
    )

    enriched = frame.with_columns([dsp, monetization, origin])
    legacy = statement_type.str.contains("altafonte", literal=True)
    status = (
        pl.when(legacy | (pl.col("dsp_normalized") == NOT_REPORTED))
        .then(pl.lit("unknown"))
        .when(
            (pl.col("monetization_normalized") == NOT_REPORTED)
            | (pl.col("content_origin_normalized") == NOT_REPORTED)
        )
        .then(pl.lit("partial"))
        .otherwise(pl.lit("exact"))
        .alias("classification_status")
    )
    return enriched.with_columns([
        status,
        pl.col("dsp_normalized").alias("store_report_label"),
    ])


def ensure_store_dimensions(
    frame: pl.LazyFrame,
    columns: set[str] | None = None,
) -> pl.LazyFrame:
    """Return canonical dimensions and replace any obsolete Plan-era taxonomy."""
    columns = columns or set(frame.collect_schema().names())
    if set(DIMENSION_COLUMNS).issubset(columns) and "plan_normalized" not in columns:
        return frame
    return add_store_dimensions(frame, columns)


def build_normalized_store_summary(
    frame: pl.LazyFrame,
    columns: set[str] | None = None,
    *,
    amount_column: str = "amount_usd",
    units_column: str = "units",
    include_source: bool = True,
    include_rows: bool = False,
    extra_group_columns: list[str] | None = None,
) -> pl.LazyFrame:
    """Aggregate reportable rows by distributor, DSP, monetization and origin."""
    columns = columns or set(frame.collect_schema().names())
    if amount_column not in columns:
        raise ValueError(f"Falta la columna de importe requerida: {amount_column}")

    normalized = ensure_store_dimensions(frame, columns)
    normalized_columns = set(normalized.collect_schema().names())
    group_columns = [
        *(["source"] if include_source and "source" in normalized_columns else []),
        *[
            column
            for column in (extra_group_columns or [])
            if column in normalized_columns and column != "source"
        ],
        *STORE_SUMMARY_GROUP_COLUMNS,
    ]
    normalized = normalized.with_columns([
        pl.when(
            pl.col(column).is_null()
            | (pl.col(column).cast(pl.Utf8, strict=False).str.strip_chars() == "")
        )
        .then(pl.lit(NOT_REPORTED))
        .otherwise(pl.col(column).cast(pl.Utf8, strict=False).str.strip_chars())
        .alias(column)
        for column in STORE_SUMMARY_GROUP_COLUMNS
    ])

    aggregations = [pl.sum(amount_column).alias("amount_usd")]
    if units_column in normalized_columns:
        aggregations.append(
            pl.col(units_column)
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
            .sum()
            .alias("units")
        )
    if include_rows:
        aggregations.append(pl.len().alias("rows"))

    return normalized.group_by(group_columns).agg(aggregations).sort(group_columns)
