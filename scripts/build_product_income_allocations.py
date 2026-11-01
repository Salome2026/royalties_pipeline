"""Prepare the shared product-income snapshot for historical data and each new release."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path

import polars as pl
import requests

try:
    from lib.product_income import FILE, cached_metadata, compile_index
except ModuleNotFoundError:
    from scripts.lib.product_income import FILE, cached_metadata, compile_index

BASE = Path(os.environ.get("VPO_PROJECT_ROOT", r"C:\royalties_pipeline"))


class SpotifyEvidence:
    """Read exact identifiers, retaining complete responses for subsequent offline builds."""
    def __init__(self, cache: dict):
        self.cache = cache
        self.session = requests.Session()
        self.token = None
        self.unavailable = False

    def fetch(self, upc):
        if self.unavailable:
            return {}, {}
        try:
            if self.token is None:
                client, secret = os.environ.get("SPOTIFY_CLIENT_ID"), os.environ.get("SPOTIFY_CLIENT_SECRET")
                if not client or not secret:
                    self.unavailable = True
                    return {}, {}
                response = self.session.post("https://accounts.spotify.com/api/token", auth=(client, secret),
                    data={"grant_type": "client_credentials"}, timeout=20)
                response.raise_for_status()
                self.token = response.json()["access_token"]
                self.session.headers["Authorization"] = "Bearer " + self.token
            response = self.session.get("https://api.spotify.com/v1/search", params={"q": "upc:" + upc, "type": "album", "limit": 10}, timeout=20)
            response.raise_for_status()
            albums, tracks = {}, {}
            for item in response.json().get("albums", {}).get("items", []):
                result = self.session.get("https://api.spotify.com/v1/albums/" + item["id"], timeout=20)
                result.raise_for_status()
                album = result.json()
                # Paginate until all positions are present; never treat the first page as a complete release.
                page = album.get("tracks") or {}
                items = list(page.get("items") or [])
                next_url = page.get("next")
                while next_url:
                    result = self.session.get(next_url, timeout=20); result.raise_for_status()
                    part = result.json(); items.extend(part.get("items") or []); next_url = part.get("next")
                album["tracks"] = {**page, "items": items, "next": None}
                for track in items:
                    tid = track.get("id")
                    full = self.cache.get("tracks", {}).get(tid)
                    if not full:
                        result = self.session.get("https://api.spotify.com/v1/tracks/" + tid, timeout=20)
                        result.raise_for_status(); full = result.json()
                    tracks[tid] = full
                albums[album["id"]] = album
            self.cache.setdefault("albums", {}).update(albums)
            self.cache.setdefault("tracks", {}).update(tracks)
            return albums, tracks
        except (requests.RequestException, ValueError, KeyError):
            # Source revenue remains visible as a pending native product if verification is unavailable.
            self.unavailable = True
            return {}, {}


def build(source: Path, catalog: Path, output: Path, *, lookup_cache: Path | None = None,
          metadata_cache: Path | None = None, online: bool = True, scope="regular") -> dict:
    albums, tracks = cached_metadata(lookup_cache) if lookup_cache else ({}, {})
    metadata = {"albums": {}, "tracks": {}}
    if metadata_cache and metadata_cache.exists():
        metadata = json.loads(metadata_cache.read_text(encoding="utf-8"))
        albums.update(metadata.get("albums", {})); tracks.update(metadata.get("tracks", {}))
    metadata["albums"].update(albums); metadata["tracks"].update(tracks)
    provider = SpotifyEvidence(metadata)
    document = compile_index(source, albums=albums, tracks=tracks,
        catalog=pl.read_parquet(catalog) if catalog.exists() else None, scope=scope,
        fetch=provider.fetch if online else None,
        prior_index=json.loads(output.read_text(encoding='utf-8')) if output.exists() else None)
    document["source_size_bytes"] = source.stat().st_size
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.replace(output)
    if metadata_cache:
        metadata_cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = metadata_cache.with_suffix(".tmp.json")
        temporary.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        temporary.replace(metadata_cache)
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=BASE/"warehouse/marts/standardized_raw_all_sources.parquet")
    parser.add_argument("--catalog", type=Path, default=BASE/"warehouse/marts/catalog_master.parquet")
    parser.add_argument("--output", type=Path, default=BASE/"warehouse/marts"/FILE)
    parser.add_argument("--lookup-cache", type=Path, default=BASE/"warehouse/registry/catalog_release_lookup_cache.parquet")
    parser.add_argument("--metadata-cache", type=Path, default=BASE/"warehouse/registry/product_income_metadata.json")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--scope", choices=["regular", "wml"], default="regular")
    args = parser.parse_args()
    # Same configured service credentials as the existing metadata updater; never log them.
    env = BASE/".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.strip() in {"SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"}:
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    doc = build(args.source, args.catalog, args.output, lookup_cache=args.lookup_cache,
        metadata_cache=args.metadata_cache, online=not args.offline, scope=args.scope)
    print(json.dumps({"output": str(args.output), "statuses": dict(Counter(p["status"] for p in doc["products"].values()))}))


if __name__ == "__main__":
    main()
