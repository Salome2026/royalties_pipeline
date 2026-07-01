from __future__ import annotations

import argparse
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from build_catalog_release_metadata import (
    BASE,
    CACHE_PATH,
    MARTS_DIR,
    OUTPUT_PATH,
    get_spotify_token,
    load_cache,
    load_env_file,
    normalize_match_text,
    primary_lookup_artist,
    spotify_lookup_candidate,
    write_cache,
    youtube_lookup_batch,
)


CATALOG_MASTER_PATH = MARTS_DIR / "catalog_master.parquet"
RETRY_LOOKUP_STATUSES = {
    None,
    "",
    "lookup_error",
    "rate_limited",
    "pending_credentials_or_manual_review",
}


def rate_limit_still_cooling(cached: dict) -> bool:
    cooldown_seconds = int(os.getenv("VPO_SPOTIFY_RATE_LIMIT_COOLDOWN_SECONDS", "86400"))
    if cooldown_seconds <= 0:
        return False
    looked_up_at = cached.get("looked_up_at")
    if not looked_up_at:
        return True
    try:
        looked_up = datetime.fromisoformat(str(looked_up_at))
    except ValueError:
        return True
    return (datetime.now() - looked_up).total_seconds() < cooldown_seconds


def spotify_global_rate_limit_still_cooling(cache: dict) -> bool:
    default_cooldown_seconds = int(os.getenv("VPO_SPOTIFY_RATE_LIMIT_COOLDOWN_SECONDS", "86400"))
    now = datetime.now()
    for (provider, _lookup_key), cached in cache.items():
        if provider != "spotify":
            continue
        if cached.get("metadata_status") != "rate_limited":
            continue
        looked_up_at = cached.get("looked_up_at")
        if not looked_up_at:
            return True
        try:
            looked_up = datetime.fromisoformat(str(looked_up_at))
        except ValueError:
            return True
        raw_json = str(cached.get("raw_json") or "")
        retry_after_match = re.search(r"Retry-After=(\d+)", raw_json)
        cooldown_seconds = (
            int(retry_after_match.group(1))
            if retry_after_match
            else default_cooldown_seconds
        )
        if (now - looked_up).total_seconds() < cooldown_seconds:
            return True
    return False


def lookup_sleep_seconds() -> float:
    try:
        return max(float(os.getenv("VPO_METADATA_LOOKUP_SLEEP_SECONDS", "1.0")), 0.0)
    except ValueError:
        return 1.0


def first_non_empty(row: dict, names: list[str]) -> str | None:
    for name in names:
        value = row.get(name)
        if value is None:
            continue
        value = str(value).strip()
        if value:
            return value
    return None


def valid_youtube_video_id(value: str | None) -> str | None:
    if not value:
        return None
    candidate = str(value).strip()
    return candidate if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate) else None


def video_id_from_catalog_key(catalog_key: str | None) -> str | None:
    if not catalog_key:
        return None
    if str(catalog_key).startswith("VIDEO:"):
        return valid_youtube_video_id(str(catalog_key).replace("VIDEO:", "", 1))
    return None


def build_candidates(
    limit: int | None = None,
    only_missing: bool = True,
    min_amount_usd: float | None = None,
    allow_text_lookup: bool = False,
) -> list[dict]:
    if not CATALOG_MASTER_PATH.exists():
        raise FileNotFoundError(f"No existe {CATALOG_MASTER_PATH}")

    catalog = pl.read_parquet(CATALOG_MASTER_PATH)
    if only_missing and "external_release_date" in catalog.columns:
        catalog = catalog.filter(
            pl.col("external_release_date").is_null()
            | (pl.col("external_release_date").cast(pl.Utf8).str.strip_chars() == "")
        )
    if min_amount_usd is not None:
        catalog = catalog.filter(pl.col("amount_usd").cast(pl.Float64, strict=False) >= min_amount_usd)

    candidates: list[dict] = []
    cache = load_cache()
    spotify_global_cooling = spotify_global_rate_limit_still_cooling(cache)
    for row in catalog.to_dicts():
        catalog_key = row.get("catalog_key")
        isrc = first_non_empty(row, ["asset_isrc"])
        upc = first_non_empty(row, ["primary_upc"])
        video_id = video_id_from_catalog_key(catalog_key) or valid_youtube_video_id(first_non_empty(row, ["track_id"]))
        title = first_non_empty(row, ["track_title"])
        artist = first_non_empty(row, ["artist_statement"])

        provider = None
        preferred_lookup_key = None
        if isrc:
            provider = "spotify"
            preferred_lookup_key = f"isrc:{isrc.upper()}"
        elif upc:
            provider = "spotify"
            preferred_lookup_key = f"upc:{upc}"
        elif catalog_key and str(catalog_key).startswith("VIDEO:") and video_id:
            provider = "youtube"
            preferred_lookup_key = f"video:{video_id}"
        elif allow_text_lookup and title and artist:
            provider = "spotify"
            preferred_lookup_key = f"text:{normalize_match_text(title)}|{primary_lookup_artist(artist)}"

        if not provider or not preferred_lookup_key:
            continue
        if provider == "spotify" and spotify_global_cooling:
            continue
        cached = cache.get((provider, preferred_lookup_key))
        if cached:
            status = cached.get("metadata_status")
            if status == "rate_limited" and rate_limit_still_cooling(cached):
                continue
            if status not in RETRY_LOOKUP_STATUSES:
                if not cached.get("release_date"):
                    continue

        candidates.append({
            "source": "catalog",
            "account": "global",
            "source_sheet": row.get("source_sheets"),
            "lookup_isrc": isrc,
            "lookup_upc": upc,
            "lookup_video_id": video_id if provider == "youtube" else None,
            "lookup_title": title,
            "lookup_artist": artist,
            "preferred_provider": provider,
            "preferred_lookup_key": preferred_lookup_key,
            "amount_usd": float(row.get("amount_usd") or 0.0),
            "first_transaction_month": row.get("first_transaction_month"),
            "first_statement_period": None,
            "row_count": int(row.get("song_level_rows") or 0),
            "catalog_key": catalog_key,
            "allow_text_fallback": allow_text_lookup,
        })
        if limit and len(candidates) >= limit:
            break
    return candidates


def enrich_candidates(candidates: list[dict]) -> pl.DataFrame:
    cache = load_cache()
    spotify_token = get_spotify_token()
    youtube_key = __import__("os").getenv("YOUTUBE_API_KEY")
    new_cache_rows = 0

    for row in candidates:
        provider = row.get("preferred_provider")
        lookup_key = row.get("preferred_lookup_key")
        if not provider or not lookup_key:
            continue
        cache_key = (provider, lookup_key)
        cached = cache.get(cache_key)
        if cached and cached.get("release_date"):
            continue
        if provider == "spotify":
            if not spotify_token:
                continue
            try:
                result = spotify_lookup_candidate(row, spotify_token)
            except Exception as exc:
                status = "lookup_error"
                raw_error = str(exc)
                response = getattr(exc, "response", None)
                if response is not None and getattr(response, "status_code", None) == 429:
                    status = "rate_limited"
                    retry_after = response.headers.get("Retry-After")
                    raw_error = f"Spotify rate limited. Retry-After={retry_after}"
                result = {
                    "lookup_provider": "spotify",
                    "lookup_key": lookup_key,
                    "metadata_status": status,
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
                    "raw_json": raw_error,
                    "looked_up_at": datetime.now().isoformat(timespec="seconds"),
                }
            if result:
                cache[cache_key] = result
                new_cache_rows += 1
                if result.get("metadata_status") == "rate_limited":
                    break
            time.sleep(lookup_sleep_seconds())

    if youtube_key:
        missing_video_ids = [
            str(row["preferred_lookup_key"]).replace("video:", "", 1)
            for row in candidates
            if row.get("preferred_provider") == "youtube"
            and row.get("preferred_lookup_key")
            and ("youtube", row["preferred_lookup_key"]) not in cache
        ]
        for idx in range(0, len(missing_video_ids), 50):
            for item in youtube_lookup_batch(missing_video_ids[idx: idx + 50], youtube_key):
                cache[(item["lookup_provider"], item["lookup_key"])] = item
                new_cache_rows += 1
            time.sleep(lookup_sleep_seconds())

    write_cache(cache)

    rows = []
    for row in candidates:
        provider = row.get("preferred_provider")
        lookup_key = row.get("preferred_lookup_key")
        cached = cache.get((provider, lookup_key), {})
        rows.append({
            **row,
            "metadata_status": cached.get("metadata_status") or "pending_credentials_or_manual_review",
            "metadata_confidence": cached.get("metadata_confidence"),
            "metadata_match_method": cached.get("metadata_match_method"),
            "release_date": cached.get("release_date"),
            "release_date_precision": cached.get("release_date_precision"),
            "release_year_month": cached.get("release_year_month"),
            "match_title": cached.get("match_title"),
            "match_artist": cached.get("match_artist"),
            "match_url": cached.get("match_url"),
            "external_label": cached.get("external_label"),
            "spotify_album_id": cached.get("spotify_album_id"),
            "match_count": cached.get("match_count"),
            "raw_json": cached.get("raw_json"),
            "looked_up_at": cached.get("looked_up_at"),
            "_new_cache_rows_this_run": new_cache_rows,
            "built_at": datetime.now().isoformat(timespec="seconds"),
        })
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def main() -> None:
    load_env_file()
    parser = argparse.ArgumentParser(description="Build global release metadata from catalog_master.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--min-amount-usd", type=float, default=None)
    parser.add_argument("--allow-text", action="store_true", help="Permite fallback global por titulo/artista exacto.")
    parser.add_argument("--all", action="store_true", help="Consultar todo el catalogo, no solo faltantes.")
    args = parser.parse_args()

    candidates = build_candidates(
        limit=args.limit,
        only_missing=not args.all,
        min_amount_usd=args.min_amount_usd,
        allow_text_lookup=args.allow_text,
    )
    enriched = enrich_candidates(candidates)

    if OUTPUT_PATH.exists():
        existing = pl.read_parquet(OUTPUT_PATH)
        if not enriched.is_empty():
            current_keys = enriched.select([
                "source",
                "account",
                "preferred_provider",
                "preferred_lookup_key",
            ]).unique()
            existing = existing.join(
                current_keys,
                on=["source", "account", "preferred_provider", "preferred_lookup_key"],
                how="anti",
            )
            final = pl.concat([existing, enriched], how="diagonal_relaxed")
        else:
            final = existing
    else:
        final = enriched
    final.write_parquet(OUTPUT_PATH)

    found = enriched.filter(pl.col("release_date").is_not_null()).height if not enriched.is_empty() else 0
    print("Catalog global release metadata")
    print(f"Candidatos consultados: {len(candidates)}")
    print(f"Con release_date: {found}")
    print(f"Pendientes: {len(candidates) - found}")
    print(f"Output metadata: {OUTPUT_PATH}")
    print(f"Cache: {CACHE_PATH}")


if __name__ == "__main__":
    main()
