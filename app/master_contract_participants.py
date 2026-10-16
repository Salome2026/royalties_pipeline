"""Editable participant proposals. Stored contracts remain report authority."""
from __future__ import annotations

import copy
import json
from typing import Any

from app.master_contracts import artist_key
from app.operational_db import db_sql, is_postgres_connection

EXCLUSIONS = "catalog_participant_exclusions"


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
