from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
import requests


BASE = Path(r"C:\royalties_pipeline")
MARTS_DIR = BASE / "warehouse" / "marts"
REGISTRY_DIR = BASE / "warehouse" / "registry"
REPORTS_DIR = BASE / "reports" / "qa"
ENV_PATH = BASE / ".env"

STANDARDIZED_ONERPM_PATH = MARTS_DIR / "standardized_raw_onerpm.parquet"
OUTPUT_PATH = MARTS_DIR / "catalog_release_metadata.parquet"
CACHE_PATH = REGISTRY_DIR / "catalog_release_lookup_cache.parquet"
REVIEW_PATH = REPORTS_DIR / "catalog_release_metadata_review.csv"

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
SPOTIFY_ALBUMS_URL = "https://api.spotify.com/v1/albums"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def load_env_file(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def clean_text_expr(expr: pl.Expr) -> pl.Expr:
    return expr.cast(pl.Utf8, strict=False).str.strip_chars()


def coalesce_text(schema: set[str], columns: list[str]) -> pl.Expr:
    exprs = [clean_text_expr(pl.col(col)) for col in columns if col in schema]
    if not exprs:
        return pl.lit(None).cast(pl.Utf8)
    return pl.coalesce(exprs)


def amount_expr(schema: set[str]) -> pl.Expr:
    for col in ["amount_usd", "net_amount_usd", "net_amount"]:
        if col in schema:
            return pl.col(col).cast(pl.Float64, strict=False)
    return pl.lit(0.0)


def normalize_release_date(value: str | None, precision: str | None) -> str | None:
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    if precision == "year" and len(value) == 4:
        return f"{value}-01-01"
    if precision == "month" and len(value) == 7:
        return f"{value}-01"
    return value[:10]


def first_artist_name(track: dict[str, Any]) -> str | None:
    artists = track.get("artists") or []
    if not artists:
        return None
    return artists[0].get("name")


def normalize_match_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def primary_lookup_artist(value: str | None) -> str:
    if not value:
        return ""
    return normalize_match_text(str(value).split(",")[0])


def spotify_not_found(lookup_key: str, raw_json: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "lookup_provider": "spotify",
        "lookup_key": lookup_key,
        "metadata_status": "not_found",
        "metadata_confidence": "none",
        "metadata_match_method": None,
        "release_date": None,
        "release_date_precision": None,
        "release_year_month": None,
        "match_title": None,
        "match_artist": None,
        "match_url": None,
        "external_label": None,
        "spotify_album_id": None,
        "match_count": 0,
        "raw_json": json.dumps(raw_json or {}, ensure_ascii=False),
        "looked_up_at": datetime.now().isoformat(timespec="seconds"),
    }


def spotify_album_detail(album: dict[str, Any], token: str) -> dict[str, Any]:
    album_id = album.get("id")
    if not album_id:
        return album
    data = http_json(
        f"{SPOTIFY_ALBUMS_URL}/{album_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    return data or album


def spotify_album_details_batch(album_ids: list[str], token: str) -> list[dict[str, Any]]:
    if not album_ids:
        return []
    query = urllib.parse.urlencode({"ids": ",".join(album_ids[:20])})
    data = http_json(
        f"{SPOTIFY_ALBUMS_URL}?{query}",
        headers={"Authorization": f"Bearer {token}"},
    )
    return [album for album in (data.get("albums") or []) if album]


def spotify_album_label(album: dict[str, Any]) -> str | None:
    label = album.get("label")
    if label:
        return str(label)
    copyrights = album.get("copyrights") or []
    for wanted_type in ["P", "C"]:
        for item in copyrights:
            if item.get("type") == wanted_type and item.get("text"):
                return str(item["text"])
    return None


def spotify_found_from_track(
    lookup_key: str,
    track: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    confidence: str,
    match_method: str,
    token: str | None = None,
) -> dict[str, Any]:
    album = track.get("album") or {}
    album_detail = spotify_album_detail(album, token) if token else album
    release_date = normalize_release_date(album.get("release_date"), album.get("release_date_precision"))
    if not release_date:
        release_date = normalize_release_date(album_detail.get("release_date"), album_detail.get("release_date_precision"))
    release_year_month = release_date[:7] if release_date else None
    return {
        "lookup_provider": "spotify",
        "lookup_key": lookup_key,
        "metadata_status": "found",
        "metadata_confidence": confidence,
        "metadata_match_method": match_method,
        "release_date": release_date,
        "release_date_precision": album.get("release_date_precision"),
        "release_year_month": release_year_month,
        "match_title": track.get("name"),
        "match_artist": first_artist_name(track),
        "match_url": (track.get("external_urls") or {}).get("spotify"),
        "external_label": spotify_album_label(album_detail),
        "spotify_album_id": album_detail.get("id") or album.get("id"),
        "match_count": len(items),
        "raw_json": json.dumps({"selected": track, "selected_album": album_detail, "items": items}, ensure_ascii=False),
        "looked_up_at": datetime.now().isoformat(timespec="seconds"),
    }


def spotify_found_from_album(
    lookup_key: str,
    album: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    confidence: str,
    match_method: str,
    token: str | None = None,
) -> dict[str, Any]:
    album_detail = spotify_album_detail(album, token) if token else album
    release_date = normalize_release_date(album.get("release_date"), album.get("release_date_precision"))
    if not release_date:
        release_date = normalize_release_date(album_detail.get("release_date"), album_detail.get("release_date_precision"))
    release_year_month = release_date[:7] if release_date else None
    artists = album_detail.get("artists") or album.get("artists") or []
    match_artist = artists[0].get("name") if artists else None
    return {
        "lookup_provider": "spotify",
        "lookup_key": lookup_key,
        "metadata_status": "found",
        "metadata_confidence": confidence,
        "metadata_match_method": match_method,
        "release_date": release_date,
        "release_date_precision": album.get("release_date_precision"),
        "release_year_month": release_year_month,
        "match_title": album_detail.get("name") or album.get("name"),
        "match_artist": match_artist,
        "match_url": (album_detail.get("external_urls") or album.get("external_urls") or {}).get("spotify"),
        "external_label": spotify_album_label(album_detail),
        "spotify_album_id": album_detail.get("id") or album.get("id"),
        "match_count": len(items),
        "raw_json": json.dumps({"selected": album_detail, "items": items}, ensure_ascii=False),
        "looked_up_at": datetime.now().isoformat(timespec="seconds"),
    }


def load_cache() -> dict[tuple[str, str], dict[str, Any]]:
    if not CACHE_PATH.exists():
        return {}
    df = pl.read_parquet(CACHE_PATH)
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in df.to_dicts():
        key = (str(row.get("lookup_provider") or ""), str(row.get("lookup_key") or ""))
        result[key] = row
    return result


def write_cache(cache: dict[tuple[str, str], dict[str, Any]]) -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    if not cache:
        return
    rows = list(cache.values())
    keys: set[str] = set()
    for row in rows:
        keys.update(row.keys())
    normalized_rows = [{key: row.get(key) for key in keys} for row in rows]
    pl.DataFrame(normalized_rows, infer_schema_length=None).write_parquet(CACHE_PATH)


def http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    retries: int = 1,
) -> dict[str, Any]:
    headers = headers or {}
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            timeout_seconds = int(os.getenv("VPO_METADATA_HTTP_TIMEOUT", "12"))
            response = requests.request(
                method,
                url,
                headers=headers,
                data=data,
                timeout=timeout_seconds,
            )
            if response.status_code == 429:
                response.raise_for_status()
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            last_error = exc
            status_code = exc.response.status_code if exc.response is not None else 0
            if 500 <= status_code < 600 and attempt + 1 < retries:
                time.sleep(2 ** attempt)
                continue
            raise
        except requests.RequestException as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError("HTTP request failed without error detail")


def get_spotify_token() -> str | None:
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    raw = f"{client_id}:{client_secret}".encode("utf-8")
    auth = base64.b64encode(raw).decode("ascii")
    payload = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
    data = http_json(
        SPOTIFY_TOKEN_URL,
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=payload,
    )
    return data.get("access_token")


def spotify_lookup_isrc(isrc: str, token: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"q": f"isrc:{isrc}", "type": "track", "limit": "10"})
    data = http_json(
        f"{SPOTIFY_SEARCH_URL}?{query}",
        headers={"Authorization": f"Bearer {token}"},
    )
    items = ((data.get("tracks") or {}).get("items") or [])
    exact_matches = [
        track for track in items
        if ((track.get("external_ids") or {}).get("isrc") or "").upper() == isrc.upper()
    ]
    candidates = exact_matches or items
    if not candidates:
        return spotify_not_found(f"isrc:{isrc.upper()}", data)

    def release_key(track: dict[str, Any]) -> str:
        album = track.get("album") or {}
        return normalize_release_date(album.get("release_date"), album.get("release_date_precision")) or "9999-12-31"

    track = sorted(candidates, key=release_key)[0]
    return spotify_found_from_track(
        f"isrc:{isrc.upper()}",
        track,
        items,
        confidence="high" if exact_matches else "medium",
        match_method="isrc_exact" if exact_matches else "isrc_search_candidate",
        token=token,
    )


def spotify_lookup_upc(upc: str, token: str, lookup_key: str | None = None) -> dict[str, Any]:
    lookup_key = lookup_key or f"upc:{upc}"
    query = urllib.parse.urlencode({"q": f"upc:{upc}", "type": "album", "limit": "5"})
    data = http_json(
        f"{SPOTIFY_SEARCH_URL}?{query}",
        headers={"Authorization": f"Bearer {token}"},
    )
    items = ((data.get("albums") or {}).get("items") or [])
    if len(items) != 1:
        return spotify_not_found(lookup_key, data)
    return spotify_found_from_album(
        lookup_key,
        items[0],
        items,
        confidence="high",
        match_method="upc_unique_album",
        token=token,
    )


def spotify_lookup_text_strict(
    title: str | None,
    artist: str | None,
    token: str,
    lookup_key: str,
) -> dict[str, Any]:
    normalized_title = normalize_match_text(title)
    normalized_primary_artist = primary_lookup_artist(artist)
    if not normalized_title or not normalized_primary_artist:
        return spotify_not_found(lookup_key, {"reason": "missing_title_or_primary_artist"})

    query_text = f'track:"{title}" artist:"{str(artist).split(",")[0]}"'
    query = urllib.parse.urlencode({"q": query_text, "type": "track", "limit": "10"})
    data = http_json(
        f"{SPOTIFY_SEARCH_URL}?{query}",
        headers={"Authorization": f"Bearer {token}"},
    )
    items = ((data.get("tracks") or {}).get("items") or [])
    strong_matches = []
    for track in items:
        track_title = normalize_match_text(track.get("name"))
        track_artists = normalize_match_text(", ".join(a.get("name", "") for a in track.get("artists") or []))
        if track_title == normalized_title and normalized_primary_artist in track_artists:
            strong_matches.append(track)
    if not strong_matches:
        return spotify_not_found(lookup_key, data)

    def release_key(track: dict[str, Any]) -> str:
        album = track.get("album") or {}
        return normalize_release_date(album.get("release_date"), album.get("release_date_precision")) or "9999-12-31"

    track = sorted(strong_matches, key=release_key)[0]
    return spotify_found_from_track(
        lookup_key,
        track,
        items,
        confidence="high",
        match_method="title_primary_artist_exact",
        token=token,
    )


def spotify_lookup_candidate(row: dict[str, Any], token: str) -> dict[str, Any] | None:
    allow_text_fallback = bool(row.get("allow_text_fallback", True))
    lookup_key = row.get("preferred_lookup_key")
    lookup_isrc = row.get("lookup_isrc")
    lookup_upc = row.get("lookup_upc")
    lookup_title = row.get("lookup_title")
    lookup_artist = row.get("lookup_artist")

    if lookup_key and str(lookup_key).startswith("isrc:"):
        result = spotify_lookup_isrc(str(lookup_isrc or "").upper(), token)
        if result.get("metadata_status") == "found":
            return result
        if lookup_upc:
            fallback = spotify_lookup_upc(str(lookup_upc), token, lookup_key=str(lookup_key))
            if fallback.get("metadata_status") == "found":
                return fallback
        if allow_text_fallback and lookup_title and lookup_artist:
            fallback = spotify_lookup_text_strict(lookup_title, lookup_artist, token, lookup_key=str(lookup_key))
            if fallback.get("metadata_status") == "found":
                return fallback
        return result

    if lookup_key and str(lookup_key).startswith("upc:"):
        return spotify_lookup_upc(str(lookup_upc or "").strip(), token, lookup_key=str(lookup_key))

    if allow_text_fallback and lookup_title and lookup_artist:
        text_key = f"text:{normalize_match_text(lookup_title)}|{primary_lookup_artist(lookup_artist)}"
        return spotify_lookup_text_strict(lookup_title, lookup_artist, token, lookup_key=text_key)

    return None


def youtube_lookup_batch(video_ids: list[str], api_key: str) -> list[dict[str, Any]]:
    if not video_ids:
        return []
    query = urllib.parse.urlencode({
        "part": "snippet",
        "id": ",".join(video_ids),
        "key": api_key,
    })
    data = http_json(f"{YOUTUBE_VIDEOS_URL}?{query}")
    by_id = {item.get("id"): item for item in data.get("items") or []}
    rows = []
    for video_id in video_ids:
        item = by_id.get(video_id)
        if not item:
            rows.append({
                "lookup_provider": "youtube",
                "lookup_key": f"video:{video_id}",
                "metadata_status": "not_found",
                "metadata_confidence": "none",
                "release_date": None,
                "release_date_precision": None,
                "release_year_month": None,
                "match_title": None,
                "match_artist": None,
                "match_url": f"https://www.youtube.com/watch?v={video_id}",
                "external_label": None,
                "spotify_album_id": None,
                "match_count": 0,
                "raw_json": json.dumps(data, ensure_ascii=False),
                "looked_up_at": datetime.now().isoformat(timespec="seconds"),
            })
            continue
        snippet = item.get("snippet") or {}
        published_at = snippet.get("publishedAt")
        release_date = published_at[:10] if published_at else None
        rows.append({
            "lookup_provider": "youtube",
            "lookup_key": f"video:{video_id}",
            "metadata_status": "found",
            "metadata_confidence": "medium",
            "release_date": release_date,
            "release_date_precision": "day" if release_date else None,
            "release_year_month": release_date[:7] if release_date else None,
            "match_title": snippet.get("title"),
            "match_artist": snippet.get("channelTitle"),
            "match_url": f"https://www.youtube.com/watch?v={video_id}",
            "external_label": snippet.get("channelTitle"),
            "spotify_album_id": None,
            "match_count": 1,
            "raw_json": json.dumps(item, ensure_ascii=False),
            "looked_up_at": datetime.now().isoformat(timespec="seconds"),
        })
    return rows


def build_candidates(source: str, account: str) -> pl.DataFrame:
    if source != "onerpm":
        raise ValueError("Por ahora este metadata builder soporta source=onerpm.")
    if not STANDARDIZED_ONERPM_PATH.exists():
        raise FileNotFoundError(f"No existe {STANDARDIZED_ONERPM_PATH}")

    lf = pl.scan_parquet(STANDARDIZED_ONERPM_PATH)
    schema = set(lf.collect_schema().names())
    base = (
        lf.filter((pl.col("source") == source) & (pl.col("account") == account))
        .with_columns([
            coalesce_text(schema, ["ISRC", "asset_isrc"]).alias("lookup_isrc"),
            coalesce_text(schema, ["UPC"]).alias("lookup_upc"),
            coalesce_text(schema, ["Track Title", "track_statement_style", "Title", "Video Title"]).alias("lookup_title"),
            coalesce_text(schema, ["artist_statement_style", "Artists", "Channel Name"]).alias("lookup_artist"),
            coalesce_text(schema, ["Video ID", "ID", "Parent ID"]).alias("lookup_video_id"),
            amount_expr(schema).alias("amount_usd_f64"),
        ])
    )

    masters = (
        base.filter(pl.col("source_sheet") == "Masters")
        .group_by(["source_sheet", "lookup_isrc", "lookup_upc", "lookup_title", "lookup_artist"])
        .agg([
            pl.sum("amount_usd_f64").round(6).alias("amount_usd"),
            pl.min("transaction_month").alias("first_transaction_month"),
            pl.min("statement_period").alias("first_statement_period"),
            pl.len().alias("row_count"),
        ])
        .with_columns([
            pl.lit("spotify").alias("preferred_provider"),
            pl.when(pl.col("lookup_isrc").is_not_null() & (pl.col("lookup_isrc") != ""))
            .then(pl.concat_str([pl.lit("isrc:"), pl.col("lookup_isrc").str.to_uppercase()]))
            .when(pl.col("lookup_upc").is_not_null() & (pl.col("lookup_upc") != ""))
            .then(pl.concat_str([pl.lit("upc:"), pl.col("lookup_upc")]))
            .otherwise(pl.lit(None).cast(pl.Utf8))
            .alias("preferred_lookup_key"),
            pl.lit(None).cast(pl.Utf8).alias("lookup_video_id"),
        ])
    )

    youtube = (
        base.filter(pl.col("source_sheet") == "Youtube Channels")
        .group_by(["source_sheet", "lookup_video_id", "lookup_title", "lookup_artist"])
        .agg([
            pl.sum("amount_usd_f64").round(6).alias("amount_usd"),
            pl.min("transaction_month").alias("first_transaction_month"),
            pl.min("statement_period").alias("first_statement_period"),
            pl.len().alias("row_count"),
        ])
        .with_columns([
            pl.lit(None).cast(pl.Utf8).alias("lookup_isrc"),
            pl.lit(None).cast(pl.Utf8).alias("lookup_upc"),
            pl.lit("youtube").alias("preferred_provider"),
            pl.when(pl.col("lookup_video_id").is_not_null() & (pl.col("lookup_video_id") != ""))
            .then(pl.concat_str([pl.lit("video:"), pl.col("lookup_video_id")]))
            .otherwise(pl.lit(None).cast(pl.Utf8))
            .alias("preferred_lookup_key"),
        ])
    )

    return (
        pl.concat([masters, youtube], how="diagonal_relaxed")
        .with_columns([
            pl.lit(source).alias("source"),
            pl.lit(account).alias("account"),
        ])
        .select([
            "source",
            "account",
            "source_sheet",
            "lookup_isrc",
            "lookup_upc",
            "lookup_video_id",
            "lookup_title",
            "lookup_artist",
            "preferred_provider",
            "preferred_lookup_key",
            "amount_usd",
            "first_transaction_month",
            "first_statement_period",
            "row_count",
        ])
        .sort("amount_usd", descending=True)
        .collect()
    )


def enrich_candidates(candidates: pl.DataFrame, contract_cutoff: str, *, cache_only: bool = False) -> pl.DataFrame:
    cache = load_cache()
    spotify_token = None if cache_only else get_spotify_token()
    youtube_key = None if cache_only else os.getenv("YOUTUBE_API_KEY")
    new_cache_rows = 0

    if not cache_only:
        for row in candidates.to_dicts():
            provider = row.get("preferred_provider")
            lookup_key = row.get("preferred_lookup_key")
            if not provider or not lookup_key:
                continue
            cache_key = (provider, lookup_key)
            cached = cache.get(cache_key)
            if cached and cached.get("metadata_status") == "found":
                continue
            if provider == "spotify":
                if not spotify_token:
                    continue
                result = spotify_lookup_candidate(row, spotify_token)
                if result:
                    cache[cache_key] = result
                    new_cache_rows += 1
                time.sleep(0.05)

        if youtube_key:
            missing_video_ids = [
                str(row["preferred_lookup_key"]).replace("video:", "", 1)
                for row in candidates.to_dicts()
                if row.get("preferred_provider") == "youtube"
                and row.get("preferred_lookup_key")
                and ("youtube", row["preferred_lookup_key"]) not in cache
            ]
            for idx in range(0, len(missing_video_ids), 50):
                for item in youtube_lookup_batch(missing_video_ids[idx: idx + 50], youtube_key):
                    cache[(item["lookup_provider"], item["lookup_key"])] = item
                    new_cache_rows += 1
                time.sleep(0.05)

    write_cache(cache)

    cache_columns = {
        "lookup_provider": pl.Utf8,
        "lookup_key": pl.Utf8,
        "metadata_status": pl.Utf8,
        "metadata_confidence": pl.Utf8,
        "release_date": pl.Utf8,
        "release_date_precision": pl.Utf8,
        "release_year_month": pl.Utf8,
        "match_title": pl.Utf8,
        "match_artist": pl.Utf8,
        "match_url": pl.Utf8,
        "external_label": pl.Utf8,
        "spotify_album_id": pl.Utf8,
        "match_count": pl.Int64,
        "raw_json": pl.Utf8,
        "looked_up_at": pl.Utf8,
    }
    cache_rows = list(cache.values())
    cache_df = (
        pl.DataFrame(cache_rows)
        if cache_rows
        else pl.DataFrame({name: pl.Series([], dtype=dtype) for name, dtype in cache_columns.items()})
    )
    enriched = (
        candidates
        .join(
            cache_df,
            left_on=["preferred_provider", "preferred_lookup_key"],
            right_on=["lookup_provider", "lookup_key"],
            how="left",
        )
        .with_columns([
            pl.when(pl.col("metadata_status").is_null())
            .then(pl.lit("pending_credentials_or_manual_review"))
            .otherwise(pl.col("metadata_status"))
            .alias("metadata_status"),
            pl.when(pl.col("release_date").is_not_null() & (pl.col("release_date") >= contract_cutoff))
            .then(pl.lit(True))
            .when(pl.col("release_date").is_not_null())
            .then(pl.lit(False))
            .otherwise(pl.lit(None).cast(pl.Boolean))
            .alias("include_after_release_cutoff"),
            pl.lit(contract_cutoff).alias("contract_cutoff_date"),
            pl.lit(new_cache_rows).alias("_new_cache_rows_this_run"),
        ])
    )
    return enriched


def main() -> None:
    load_env_file()

    parser = argparse.ArgumentParser(description="Build catalog release metadata candidates/cache.")
    parser.add_argument("--source", default="onerpm")
    parser.add_argument("--account", default="la_nueva_sangre")
    parser.add_argument("--contract-cutoff", default="2023-06-15")
    parser.add_argument("--cache-only", action="store_true", help="Sin llamadas externas; solo sincroniza metadata ya cacheada.")
    args = parser.parse_args()

    MARTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    candidates = build_candidates(args.source, args.account)
    enriched = enrich_candidates(candidates, args.contract_cutoff, cache_only=args.cache_only)

    if OUTPUT_PATH.exists():
        existing = pl.read_parquet(OUTPUT_PATH)
        existing = existing.filter(
            ~((pl.col("source") == args.source) & (pl.col("account") == args.account))
        )
        final = pl.concat([existing, enriched], how="diagonal_relaxed")
    else:
        final = enriched

    final.write_parquet(OUTPUT_PATH)
    enriched.drop("raw_json", strict=False).write_csv(REVIEW_PATH)

    print("Catalog release metadata")
    print(f"Cuenta: {args.source}/{args.account}")
    print(f"Candidatos: {candidates.height}")
    print(f"Con release_date: {enriched.filter(pl.col('release_date').is_not_null()).height}")
    print(f"Pendientes: {enriched.filter(pl.col('release_date').is_null()).height}")
    print(f"Output mart: {OUTPUT_PATH}")
    print(f"Review CSV: {REVIEW_PATH}")
    print(f"Cache: {CACHE_PATH}")
    if not os.getenv("SPOTIFY_CLIENT_ID") or not os.getenv("SPOTIFY_CLIENT_SECRET"):
        print("Spotify: credenciales no configuradas, se genero staging sin consulta externa.")
    if not os.getenv("YOUTUBE_API_KEY"):
        print("YouTube: API key no configurada, videos quedan pendientes.")


if __name__ == "__main__":
    main()
