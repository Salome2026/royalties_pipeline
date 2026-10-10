from __future__ import annotations

import json
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

import polars as pl

from app.master_contracts import artist_key, parse_artists
from app.royalty_reports.manifests import require_manifest_object


def published_catalog_frame(client, manifest: dict) -> pl.DataFrame:
    entry = require_manifest_object(manifest, "catalog_master.parquet")
    payload = client.bucket(manifest["bucket"]).blob(entry["object"], generation=int(entry["generation"])).download_as_bytes()
    return pl.read_parquet(BytesIO(payload))


def contract_catalog_rows(frame: pl.DataFrame) -> list[dict]:
    frame = frame.filter(pl.col("asset_isrc").str.contains(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$"))
    frame = frame.sort(["amount_usd", "asset_isrc"], descending=[True, False]).unique(subset=["asset_isrc"], keep="first", maintain_order=True)
    return [{"isrc": row["asset_isrc"], "title": row.get("track_title") or "Sin título",
             "artists_informed": row.get("artist_statement") or "", "artist_variants": row.get("artist_variants") or ""} for row in frame.to_dicts()]


def published_contract_catalog(client, manifest: dict) -> list[dict]:
    return contract_catalog_rows(published_catalog_frame(client, manifest))


def freeze_contract_associations(snapshot: dict, frame: pl.DataFrame, contracts: list[dict], release_id: str,
                                *, input_manifest: dict) -> dict:
    from app.master_contract_income import associated_income_isrc, income_association_index, published_unassigned_income
    from app.master_contract_metadata import infer_video_evidence
    from scripts.lib.catalog_report_filter import catalog_alias_lookup
    from app.royalty_reports.contract_identity import unsafe_ranking_slot_keys

    if not release_id:
        raise ValueError("Falta la version publicada para validar los codigos asociados.")
    if input_manifest.get("release_id") != release_id:
        raise ValueError("El detalle de identidades y el catalogo deben tener la misma version.")
    entry = require_manifest_object(input_manifest, "standardized_raw_all_sources.parquet")
    rows, evidence = published_unassigned_income(release_id)
    aliases = {row["alias_catalog_key"]: row["catalog_key"]
               for row in catalog_alias_lookup(catalog=frame).to_dicts()}
    choices = {row["isrc"]: row["split"].get("code_association_overrides") or [] for row in contracts}
    claims = {choice["key"]: root for root, values in choices.items() for choice in values if choice.get("included")}
    index = income_association_index(infer_video_evidence(frame.to_dicts(), evidence), aliases, choices, claims)
    codes: dict[str, set[tuple[str, str]]] = {}
    for row in evidence:
        if row["kind"] in {"VIDEO", "TRACK"}:
            key = json.dumps([row["code"].lower(), row["source"], row["account"]], separators=(",", ":"))
            codes.setdefault(key, set()).add((row["kind"], row["code"]))
            if " " in row["code"]:
                unsafe = json.dumps([row["code"].lower().partition(" ")[0], row["source"], row["account"]], separators=(",", ":"))
                codes.setdefault(unsafe, set()).update({("unsafe", ""), (row["kind"], row["code"])})
    search_codes = {key: list(next(iter(values))) if len(values) == 1 else None for key, values in codes.items()}
    roots: dict[str, set] = defaultdict(set)
    totals: dict[str, dict] = {}
    for row in rows:
        if not row.get("source") or not row.get("account"):
            continue
        slot = row.get("video_id") or row.get("track_id")
        code = slot or row.get("product_upc")
        if not code or not row.get("statement_period"):
            continue
        key = json.dumps([row["source"], row["account"], row.get("source_sheet") or "", row["statement_period"],
                          "ID" if slot else "UPC", code.lower() if slot else code], separators=(",", ":"))
        roots[key].add(associated_income_isrc(row, index))
        total = totals.setdefault(key, {"amount_usd": 0.0, "raw_rows": 0})
        total["amount_usd"] += float(row.get("amount_usd") or 0)
        total["raw_rows"] += int(row.get("raw_rows") or 0)
    selected = {row["isrc"] for row in snapshot["catalog"]}
    owners = {key: {"isrc": next(iter(values)), **totals[key]} for key, values in roots.items()
              if len(values) == 1 and next(iter(values)) in selected}
    if owners:
        include_upc = any(json.loads(key)[4] == "UPC" for key in owners)
        unsafe = unsafe_ranking_slot_keys(input_manifest["bucket"], entry["object"], int(entry["generation"]), include_upc=include_upc)
        owners = {key: value for key, value in owners.items() if key not in unsafe}
    return {**snapshot, "schema_version": 2,
            "associations": {"release_id": release_id, "ranking_layout": "artist-title-isrc-upc-id-v1",
                             "search_codes": search_codes, "ranking_owners": owners, **index}}


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
