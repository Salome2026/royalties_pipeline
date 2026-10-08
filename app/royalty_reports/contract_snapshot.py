from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

import polars as pl

from app.master_contracts import artist_key, parse_artists
from app.royalty_reports.manifests import require_manifest_object


def published_contract_catalog(client, manifest: dict) -> list[dict]:
    entry = require_manifest_object(manifest, "catalog_master.parquet")
    payload = client.bucket(manifest["bucket"]).blob(entry["object"], generation=int(entry["generation"])).download_as_bytes()
    frame = pl.read_parquet(BytesIO(payload)).filter(pl.col("asset_isrc").str.contains(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$"))
    frame = frame.sort(["amount_usd", "asset_isrc"], descending=[True, False]).unique(subset=["asset_isrc"], keep="first", maintain_order=True)
    return [{"isrc": row["asset_isrc"], "title": row.get("track_title") or "Sin título",
             "artists_informed": row.get("artist_statement") or "", "artist_variants": row.get("artist_variants") or ""} for row in frame.to_dicts()]


def stored_contracts(conn) -> list[dict]:
    rows = conn.execute("SELECT isrc, payload_json, is_closed, version, updated_at FROM master_contract_splits ORDER BY isrc").fetchall()
    return [{"isrc": row["isrc"], "split": json.loads(row["payload_json"]), "is_closed": bool(row["is_closed"]),
             "version": int(row["version"]), "updated_at": str(row["updated_at"])} for row in rows]


def contract_artist_names(contracts: list[dict], catalog: list[dict]) -> list[str]:
    names: dict[str, str] = {}
    for row in catalog:
        for name in parse_artists(row["artists_informed"], "catalog"):
            names.setdefault(artist_key(name), name)
    for row in contracts:
        split = row["split"]
        for allocation in [split, *[(a.get("allocation") or split) for a in split.get("agreements") or []]]:
            for name in [allocation.get("principal"), *[p.get("artist") for p in allocation.get("participants") or []]]:
                if name:
                    names[artist_key(name)] = name
    return sorted([name for key, name in names.items() if key], key=artist_key)


def freeze_contract_snapshot(artists: list[str], catalog: list[dict], contracts: list[dict]) -> dict:
    known = {artist_key(name): name for name in contract_artist_names(contracts, catalog)}
    if any(artist_key(name) not in known for name in artists):
        raise ValueError("Elegí artistas o proyectos del catálogo.")
    selected = list(dict.fromkeys(known[artist_key(name)] for name in artists))
    keys = {artist_key(name) for name in selected}
    by_isrc = {row["isrc"]: row for row in contracts}
    result = []
    for row in catalog:
        names = {artist_key(name) for name in parse_artists(row["artists_informed"], "catalog")}
        saved = by_isrc.get(row["isrc"], {}).get("split") or {}
        for allocation in [saved, *[(a.get("allocation") or saved) for a in saved.get("agreements") or []]]:
            names.update(artist_key(name) for name in [allocation.get("principal") or "", *[p.get("artist") or "" for p in allocation.get("participants") or []]])
        if names & keys:
            result.append(row)
    if not result:
        raise ValueError("Los artistas seleccionados no tienen ISRC en el catálogo.")
    isrcs = {row["isrc"] for row in result}
    return {"schema_version": 1, "template_version": "contractual-v1", "captured_at": datetime.now(timezone.utc).isoformat(),
            "as_of": datetime.now(ZoneInfo("America/New_York")).date().isoformat(), "artists": selected,
            "catalog": deepcopy(result), "contracts": deepcopy([row for row in contracts if row["isrc"] in isrcs])}
