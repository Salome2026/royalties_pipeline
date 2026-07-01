from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import polars as pl
import requests

from build_catalog_global_release_metadata import (
    build_candidates,
    enrich_candidates,
)
from build_catalog_master import OUTPUT_PATH as CATALOG_MASTER_OUTPUT_PATH
from build_catalog_master import build_catalog_master
from build_catalog_release_metadata import (
    CACHE_PATH,
    OUTPUT_PATH,
    get_spotify_token,
    load_cache,
    load_env_file,
    spotify_album_detail,
    spotify_album_label,
    write_cache,
)


BASE = Path(r"C:\royalties_pipeline")
STAGING_DIR = BASE / "staging" / "catalog_metadata_worker"
LOG_PATH = STAGING_DIR / "catalog_metadata_worker.log"
LOCK_PATH = STAGING_DIR / "catalog_metadata_worker.lock"


def log(message: str) -> None:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')} | {message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def parse_amounts(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def parse_retry_after_seconds(enriched: pl.DataFrame) -> int | None:
    if enriched.is_empty() or "raw_json" not in enriched.columns:
        return None
    retry_after_values: list[int] = []
    rows = enriched.filter(pl.col("metadata_status") == "rate_limited").select("raw_json").to_dicts()
    for row in rows:
        raw = str(row.get("raw_json") or "")
        match = re.search(r"Retry-After=(\d+)", raw)
        if match:
            retry_after_values.append(int(match.group(1)))
    return max(retry_after_values) if retry_after_values else None


def merge_metadata(enriched: pl.DataFrame) -> None:
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


def extract_album_id(cache_row: dict) -> str | None:
    existing = cache_row.get("spotify_album_id")
    if existing:
        return str(existing)
    raw_json = cache_row.get("raw_json")
    if not raw_json:
        return None
    try:
        data = json.loads(raw_json)
    except Exception:
        return None

    selected_album = data.get("selected_album") or {}
    if selected_album.get("id"):
        return str(selected_album["id"])

    selected = data.get("selected") or {}
    if selected.get("type") == "album" and selected.get("id"):
        return str(selected["id"])
    album = selected.get("album") or {}
    if album.get("id"):
        return str(album["id"])
    return None


def backfill_spotify_labels(limit: int) -> int:
    if limit <= 0:
        return 0
    token = get_spotify_token()
    if not token:
        log("spotify label backfill skipped: missing credentials")
        return 0

    cache = load_cache()
    targets: list[tuple[tuple[str, str], str]] = []
    seen_album_ids: set[str] = set()
    for key, row in cache.items():
        provider, _lookup_key = key
        if provider != "spotify":
            continue
        if row.get("metadata_status") != "found":
            continue
        if row.get("external_label"):
            continue
        album_id = extract_album_id(row)
        if not album_id or album_id in seen_album_ids:
            continue
        seen_album_ids.add(album_id)
        targets.append((key, album_id))
        if len(targets) >= limit:
            break

    if not targets:
        return 0

    updated = 0
    label_sleep_seconds = max(float(os.getenv("VPO_METADATA_LABEL_SLEEP_SECONDS", "2.0")), 0.0)
    for key, album_id in targets:
        try:
            album = spotify_album_detail({"id": album_id}, token)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 403:
                log("spotify label backfill skipped: album detail returned 403")
                break
            raise
        external_label = spotify_album_label(album) if album else None
        if not external_label:
            continue
        row = dict(cache[key])
        row["external_label"] = external_label
        row["spotify_album_id"] = album.get("id")
        row["label_backfilled_at"] = datetime.now().isoformat(timespec="seconds")
        cache[key] = row
        updated += 1
        time.sleep(label_sleep_seconds)

    if updated:
        write_cache(cache)
    return updated


def sync_metadata_labels_from_cache() -> int:
    if not OUTPUT_PATH.exists() or not CACHE_PATH.exists():
        return 0
    metadata = pl.read_parquet(OUTPUT_PATH)
    if metadata.is_empty():
        return 0
    cache_rows = list(load_cache().values())
    if not cache_rows:
        return 0

    raw_cache_df = pl.DataFrame(cache_rows)
    if "external_label" not in raw_cache_df.columns:
        raw_cache_df = raw_cache_df.with_columns(pl.lit(None).cast(pl.Utf8).alias("external_label"))
    if "spotify_album_id" not in raw_cache_df.columns:
        raw_cache_df = raw_cache_df.with_columns(pl.lit(None).cast(pl.Utf8).alias("spotify_album_id"))

    cache_df = (
        raw_cache_df
        .select([
            pl.col("lookup_provider").alias("_cache_provider"),
            pl.col("lookup_key").alias("_cache_key"),
            pl.col("external_label").alias("_cache_external_label"),
            pl.col("spotify_album_id").alias("_cache_spotify_album_id"),
        ])
        .filter(
            pl.col("_cache_external_label").is_not_null()
            | pl.col("_cache_spotify_album_id").is_not_null()
        )
        .unique(["_cache_provider", "_cache_key"])
    )
    if cache_df.is_empty():
        return 0

    if "external_label" not in metadata.columns:
        metadata = metadata.with_columns(pl.lit(None).cast(pl.Utf8).alias("external_label"))
    if "spotify_album_id" not in metadata.columns:
        metadata = metadata.with_columns(pl.lit(None).cast(pl.Utf8).alias("spotify_album_id"))

    before = metadata.filter(pl.col("external_label").is_not_null()).height
    updated = (
        metadata
        .join(
            cache_df,
            left_on=["preferred_provider", "preferred_lookup_key"],
            right_on=["_cache_provider", "_cache_key"],
            how="left",
        )
        .with_columns([
            pl.coalesce(["external_label", "_cache_external_label"]).alias("external_label"),
            pl.coalesce(["spotify_album_id", "_cache_spotify_album_id"]).alias("spotify_album_id"),
        ])
        .drop(["_cache_external_label", "_cache_spotify_album_id"], strict=False)
    )
    after = updated.filter(pl.col("external_label").is_not_null()).height
    if after > before:
        updated.write_parquet(OUTPUT_PATH)
    return after - before


def run_release_batch(min_amount_usd: float, batch_size: int, allow_text: bool) -> tuple[int, int, int, bool, int | None]:
    candidates = build_candidates(
        limit=batch_size,
        only_missing=True,
        min_amount_usd=min_amount_usd,
        allow_text_lookup=allow_text,
    )
    if not candidates:
        return 0, 0, 0, False, None

    enriched = enrich_candidates(candidates)
    merge_metadata(enriched)

    found = enriched.filter(pl.col("release_date").is_not_null()).height if not enriched.is_empty() else 0
    rate_limited = (
        not enriched.is_empty()
        and "metadata_status" in enriched.columns
        and enriched.filter(pl.col("metadata_status") == "rate_limited").height > 0
    )
    retry_after_seconds = parse_retry_after_seconds(enriched) if rate_limited else None
    pending = len(candidates) - found
    return len(candidates), found, pending, rate_limited, retry_after_seconds


def rebuild_catalog() -> None:
    catalog = build_catalog_master()
    catalog.write_parquet(CATALOG_MASTER_OUTPUT_PATH)
    with_label = (
        catalog.filter(pl.col("external_label").is_not_null()).height
        if "external_label" in catalog.columns
        else 0
    )
    with_release = catalog.filter(pl.col("external_release_date").is_not_null()).height
    log(f"catalog_master rebuilt rows={catalog.height} release_dates={with_release} labels={with_label}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Slow catalog metadata worker.")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--sleep-seconds", type=int, default=600)
    parser.add_argument("--rate-limit-sleep-seconds", type=int, default=3600)
    parser.add_argument("--max-batches", type=int, default=12)
    parser.add_argument("--min-amounts", default="100,50,10,0")
    parser.add_argument("--allow-text-stage", action="store_true")
    parser.add_argument("--label-backfill-limit", type=int, default=40)
    parser.add_argument("--max-retry-after-seconds", type=int, default=1800)
    parser.add_argument("--lookup-sleep-seconds", type=float, default=2.0)
    parser.add_argument("--label-sleep-seconds", type=float, default=2.0)
    parser.add_argument("--continue-after-rate-limit", action="store_true")
    parser.add_argument("--allow-infinite-zero-floor", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-rebuild-catalog", action="store_true")
    args = parser.parse_args()

    load_env_file()
    os.environ["VPO_METADATA_LOOKUP_SLEEP_SECONDS"] = str(max(args.lookup_sleep_seconds, 0.0))
    os.environ["VPO_METADATA_LABEL_SLEEP_SECONDS"] = str(max(args.label_sleep_seconds, 0.0))
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be >= 1")
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.exists():
        raise SystemExit(f"Worker already appears to be running: {LOCK_PATH}")
    LOCK_PATH.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")

    try:
        min_amounts = parse_amounts(args.min_amounts)
        if not min_amounts:
            raise SystemExit("--min-amounts must include at least one value")
        if (
            args.max_batches <= 0
            and any(amount <= 0 for amount in min_amounts)
            and not args.allow_infinite_zero_floor
        ):
            raise SystemExit(
                "Refusing infinite worker with min_amount <= 0. "
                "Use a finite --max-batches or pass --allow-infinite-zero-floor explicitly."
            )
        log(
            "worker start "
            f"batch_size={args.batch_size} sleep_seconds={args.sleep_seconds} "
            f"min_amounts={min_amounts} allow_text_stage={args.allow_text_stage} "
            f"lookup_sleep_seconds={args.lookup_sleep_seconds} "
            f"label_sleep_seconds={args.label_sleep_seconds}"
        )
        batch_index = 0
        while args.max_batches <= 0 or batch_index < args.max_batches:
            phase = min_amounts[min(batch_index, len(min_amounts) - 1)]
            allow_text = bool(args.allow_text_stage and batch_index >= len(min_amounts))
            try:
                label_updates = backfill_spotify_labels(args.label_backfill_limit)
                metadata_label_updates = sync_metadata_labels_from_cache()
                consulted, found, pending, rate_limited, retry_after_seconds = run_release_batch(
                    min_amount_usd=phase,
                    batch_size=args.batch_size,
                    allow_text=allow_text,
                )
                log(
                    f"batch={batch_index + 1} min_amount={phase:g} "
                    f"consulted={consulted} found={found} pending={pending} "
                    f"labels_backfilled={label_updates} "
                    f"metadata_labels_synced={metadata_label_updates} "
                    f"rate_limited={rate_limited} "
                    f"retry_after={retry_after_seconds if retry_after_seconds is not None else ''}"
                )
                if not args.no_rebuild_catalog and (found or label_updates or metadata_label_updates):
                    rebuild_catalog()
                if rate_limited:
                    if not args.continue_after_rate_limit:
                        log("spotify rate limit detected; stopping worker")
                        break
                    if (
                        retry_after_seconds is not None
                        and retry_after_seconds > args.max_retry_after_seconds
                    ):
                        log(
                            "spotify rate limit retry_after is too large; "
                            f"stopping worker retry_after={retry_after_seconds}s"
                        )
                        break
                    sleep_seconds = retry_after_seconds or args.rate_limit_sleep_seconds
                    log(f"spotify rate limit detected; sleeping {sleep_seconds}s")
                    time.sleep(sleep_seconds)
                elif consulted == 0 and label_updates == 0:
                    log("no work left for current safe stages")
                    break
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status == 429:
                    if not args.continue_after_rate_limit:
                        log("spotify/http rate limit exception; stopping worker")
                        break
                    log(f"spotify/http rate limit exception; sleeping {args.rate_limit_sleep_seconds}s")
                    time.sleep(args.rate_limit_sleep_seconds)
                else:
                    raise

            batch_index += 1
            if args.once:
                break
            if batch_index < args.max_batches or args.max_batches <= 0:
                time.sleep(args.sleep_seconds)
        log("worker finished")
    finally:
        LOCK_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
