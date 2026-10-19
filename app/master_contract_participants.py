"""Editable participant proposals. Stored contracts remain report authority."""
from __future__ import annotations

import copy
import json
from typing import Any

from app.master_contracts import artist_key
from app.operational_db import db_sql, is_postgres_connection

EXCLUSIONS = "catalog_participant_exclusions"


def ada_principal(evidence: list[dict], artists: list[str]) -> bool | None:
    from lib.ada_catalog_artists import EVIDENCE_VERSION

    records = [entry for entry in evidence if entry.get("source") == "ada"
               and entry.get("adapter_version") == EVIDENCE_VERSION]
    if not records:
        return None
    if len(records) != 1:
        return True
    entry = records[0]
    if (entry.get("identity_status") != "resolved"
            or entry.get("native_resolution_status") != "resolved"
            or not entry.get("used_for_catalog")):
        return True
    names = entry.get("artists") or []
    if (not artists or set(map(artist_key, names)) != set(map(artist_key, artists))
            or entry.get("principal_status") != "order_only"
            or not entry.get("principal_proposed")):
        return True
    return artist_key(entry["principal_proposed"]) != artist_key(artists[0])


def orchard_principal(evidence: list[dict], artists: list[str], raw_uncertain: bool, *, isrc: str) -> bool | None:
    from lib.orchard_catalog_artists import EVIDENCE_VERSION, RULE_VERSION

    orchard = [entry for entry in evidence if entry.get("source") == "orchard"
               and entry.get("adapter_version") == EVIDENCE_VERSION]
    if not orchard:
        return None
    if len(orchard) != 1:
        return True
    entry = orchard[0]
    if (entry.get("rule") != RULE_VERSION or entry.get("field") != "TRACK ARTIST"
            or entry.get("level") != "track" or entry.get("asset_isrc") != isrc
            or entry.get("identity_status") != "resolved" or entry.get("native_resolution_status") != "resolved"
            or not entry.get("used_for_catalog") or not entry.get("observations")):
        return True
    native = entry.get("native_artists") or []
    proof_artists = entry.get("artists") or []
    if not all(isinstance(value, list) and all(isinstance(name, str) and name.strip() for name in value)
               for value in (native, artists, proof_artists)):
        return True
    if (not artists or not native or keys(entry.get("artists") or []) != keys(artists)
            or not keys(native) <= keys(artists) or entry.get("principal_status") not in {"single_artist", "order_only"}
            or not entry.get("principal_proposed") or artist_key(entry["principal_proposed"]) != artist_key(artists[0])):
        return True
    if entry["principal_status"] == "single_artist" and len(native) != 1:
        return True
    target = {artist_key(artists[0])}
    observations = entry["observations"]
    if not isinstance(observations, list) or any(not isinstance(row, dict) for row in observations):
        return True
    if any(row.get("asset_isrc") != isrc or row.get("identity_status") != "resolved"
           or not row.get("provenance_complete") for row in observations):
        return True
    if any(not isinstance(row.get("artists"), list) or any(not isinstance(name, str) for name in row["artists"])
           or (row["artists"] and keys(row["artists"]) != keys(native)) for row in observations):
        return True
    firsts = {artist_key(row["artists"][0]) for row in observations if row.get("artists")}
    if firsts != target:
        return True
    # Only remove the generic missing-FUGA warning. Other-source uncertainty remains authoritative.
    if raw_uncertain or ada_principal(evidence, artists) is True or onerpm_principal(evidence, artists, False) is True:
        return True
    fuga = {artist_key(record["artists"][0]) for record in evidence
            if record.get("source") == "fuga" and record.get("field") == "Asset Artist" and record.get("artists")}
    return bool(fuga and fuga != target)


def allocations(split: dict) -> list[tuple[str, dict]]:
    return [("fallback", split), *[("agreement:" + str(item["id"]), item["allocation"])
        for item in split.get("agreements") or [] if isinstance(item.get("allocation"), dict)]]


def names(allocation: dict) -> list[str]:
    return [name for name in [allocation.get("principal") or "", *(row.get("artist") or "" for row in allocation.get("participants") or [])] if name.strip()]


def keys(values: list[str]) -> set[str]:
    return {artist_key(value) for value in values if value.strip()}


def read_participant_history(conn: Any, isrc: str) -> list[dict]:
    if not is_postgres_connection(conn):
        raise ValueError("El completado de participantes guardados usa exclusivamente Cloud SQL Postgres.")
    return [dict(row) for row in conn.execute(db_sql(conn,
        "SELECT version, payload_json, is_closed, future_reports_selected FROM master_contract_split_history WHERE isrc = ? ORDER BY version"), (isrc,)).fetchall()]


def propose_participants(initial: dict, artists: list[str], *, saved: dict | None, history: list[dict]) -> tuple[dict, dict]:
    if saved and (saved["closed"] or any(row["is_closed"] for row in history)):
        return saved["split"], {"status": "closed_or_previously_closed", "added": {}, "capacity_exceeded": False}
    removed: dict[str, set[str]] = {}
    if saved:
        complete = [int(row["version"]) for row in history] == list(range(1, saved["version"] + 1))
        complete = complete and json.loads(history[-1]["payload_json"]) == saved["split"]
        complete = complete and bool(history[-1]["is_closed"]) == saved["closed"]
        complete = complete and bool(history[-1]["future_reports_selected"]) == saved["future_reports_selected"]
        if not complete:
            return saved["split"], {"status": "history_incomplete", "added": {}, "capacity_exceeded": False}
        current = dict(allocations(saved["split"]))
        for row in history[:-1]:
            for scope, allocation in allocations(json.loads(row["payload_json"])):
                removed.setdefault(scope, set()).update(keys(names(allocation)) - keys(names(current.get(scope, {}))))
    split = copy.deepcopy(saved["split"] if saved else initial)
    added = {}
    for scope, allocation in allocations(split):
        present = keys(names(allocation))
        excluded = keys(allocation.get(EXCLUSIONS) or []) | removed.get(scope, set())
        new = []
        for artist in artists:
            key = artist_key(artist)
            if not key or key in present or key in excluded:
                continue
            allocation.setdefault("participants", []).append({"artist": artist, "percent": None,
                "internal_contract_indyana_percent": None, "rule": {"treatment": "direct"}})
            new.append(artist)
            present.add(key)
        if new:
            added[scope] = new
    return split, {"status": "open_never_closed" if saved else "new_unsaved", "added": added,
                   "capacity_exceeded": any(len(allocation.get("participants") or []) > 10 for _, allocation in allocations(split))}


def onerpm_principal(evidence: list[dict], artists: list[str], raw_uncertain: bool) -> bool | None:
    source = [entry for entry in evidence if entry.get("source") == "onerpm" and entry.get("field") == "Artists"]
    if not source:
        return None
    used = [entry for entry in source if entry.get("used_for_catalog") is True]
    masters = [entry for entry in used if entry.get("sheet") == "Masters"]
    valid = [entry for entry in masters if entry.get("level") == "track" and entry.get("product_type") in {"Track", "Video Track"}
             and entry.get("status") == entry.get("identity_status") == entry.get("native_resolution_status") == "resolved"
             and entry.get("principal_status") == "order_only" and isinstance(entry.get("principal_proposed"), str)
             and entry["principal_proposed"].strip()]
    if not valid or len(valid) != len(masters):
        return True
    native = keys([entry["principal_proposed"] for entry in valid])
    other = keys([entry["artists"][0] for entry in evidence if entry.get("source") == "fuga"
                  and entry.get("field") == "Asset Artist" and entry.get("artists")])
    return bool(raw_uncertain or len(native) != 1 or native != keys(artists[:1]) or (other and other != native))
