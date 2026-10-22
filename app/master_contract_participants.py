"""Editable participant proposals. Stored contracts remain report authority."""
from __future__ import annotations

import copy
import json
from typing import Any

from app.master_contracts import artist_key, canonical_artist
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


def soundon_suggestions(result: dict, evidence: list[dict], artists: list[str], raw: dict | None, *, isrc: str) -> dict | None:
    import re
    from lib.soundon_catalog_artists import EVIDENCE_VERSION, RULE_VERSION, credit_parts
    from lib.soundon_identity import artist_key as native_key

    records = [entry for entry in evidence if entry.get("source") == "soundon"
               and entry.get("adapter_version") == EVIDENCE_VERSION]
    if not records:
        return None
    result = copy.deepcopy(result)
    valid = len(records) == 1
    entry = records[0]
    native, observations = entry.get("native_artists"), entry.get("observations")
    valid = valid and (entry.get("rule") == RULE_VERSION and entry.get("asset_isrc") == isrc
        and entry.get("level") == "track" and entry.get("field") == "Track Artists"
        and entry.get("account") == "soundon" and entry.get("source_sheet") == "my_royalty"
        and entry.get("identity_status") == "resolved" and isinstance(native, list) and bool(native)
        and all(isinstance(name, str) and name.strip() for name in native)
        and isinstance(observations, list) and bool(observations))
    if valid:
        for row in observations:
            filename = re.fullmatch(r"SoundOn_royalty_monthly_statement_(\d{4})_(\d{2})_My Royalty\.csv", str(row.get("statement_file_name") or "")) if isinstance(row, dict) else None
            valid = isinstance(row, dict) and (row.get("asset_isrc") == row.get("ISRC") == isrc
                and row.get("account") == "soundon" and row.get("source_sheet") == "my_royalty"
                and filename and "-".join(filename.groups()) == row.get("statement_period") == row.get("Reporting Period")
                and re.fullmatch(r"[a-fA-F0-9]{64}", str(row.get("statement_file_hash") or ""))
                and re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", str(row.get("statement_period") or ""))
                and isinstance(row.get("standardized_rows"), list) and bool(row["standardized_rows"])
                and all(isinstance(index, int) and index > 0 for index in row["standardized_rows"])
                and row.get("locator_kind") == "standardized_soundon_subset_row"
                and isinstance(row.get("Track Artists"), str) and row.get("artists") == credit_parts(row["Track Artists"]))
            if not valid:
                break
        observed = {native_key(name) for row in observations for name in row.get("artists", [])} if valid else set()
        valid = valid and {native_key(name) for name in native} <= observed
    if not valid:
        result["principal_uncertain"] = True
        result["warnings"] = [*result.get("warnings", []), "Evidencia SoundOn incompleta; se conserva la propuesta anterior."]
        return result
    # Recover only names directly evidenced in track credits, not unchecked serialized proposals.
    reported = list(artists)
    for name in [*native, *(name for row in observations for name in row["artists"])]:
        if native_key(name) not in {native_key(value) for value in reported}:
            reported.append(name)
    target = keys(artists[:1])
    first = entry.get("principal_proposed")
    uncertain = bool((raw or {}).get("principal_uncertain"))
    uncertain = uncertain or entry.get("principal_status") not in {"single_artist", "order_only", "verified_isrc_reference"}
    uncertain = uncertain or not first or keys([first]) != target
    observed_sets = {frozenset(keys(row["artists"])) for row in observations}
    observed_firsts = keys([row["artists"][0] for row in observations])
    if entry.get("native_resolution_status") != "as_reported" or observed_sets != {frozenset(keys(native))}:
        uncertain = True
    elif entry.get("principal_status") == "verified_isrc_reference":
        from lib.soundon_catalog_artists import references
        from lib.soundon_identity import REFERENCE_PATH
        approved = references(REFERENCE_PATH).get(isrc)
        uncertain = uncertain or not approved or approved != entry.get("isrc_reference") or keys(approved["artists"]) != keys(native) or native_key(approved["artists"][0]) != native_key(first)
    else:
        uncertain = uncertain or observed_firsts != keys([first] if first else [])
    fuga = keys([record["artists"][0] for record in evidence
                 if record.get("source") == "fuga" and record.get("field") == "Asset Artist" and record.get("artists")])
    uncertain = uncertain or bool(fuga and fuga != target)
    uncertain = uncertain or ada_principal(evidence, artists) is True or onerpm_principal(evidence, artists, False) is True
    uncertain = uncertain or orchard_principal(evidence, artists, bool((raw or {}).get("principal_uncertain")), isrc=isrc) is True
    result.update(artists=reported, artists_reported=reported, principal_uncertain=bool(uncertain),
        participant_resolution_status=entry["participant_resolution_status"], principal_resolution_status="unresolved" if uncertain else entry["principal_status"],
        identity_relationship_status=entry.get("identity_relationship_status", "unknown"),
        identity_relationship_conflicts=entry.get("identity_relationship_conflicts", []),
        participant_alternatives=[{"source": "catalog_prior", "artists": artists},
            *[{"source": "soundon", "artists": row["artists"], "statement_period": row["statement_period"]} for row in observations]])
    result["evidence"] = [*result.get("evidence", []), entry]
    if entry["participant_resolution_status"] != "as_reported":
        obsolete = "Las fuentes de pista discrepan; sugerimos solo los nombres comunes. Revisar antes de cerrar."
        result["warnings"] = [warning for warning in result.get("warnings", []) if warning != obsolete]
        result["warnings"].append("Las fuentes difieren en participantes; se conservan los nombres informados, sin asignar porcentajes.")
    if entry.get("identity_relationship_conflicts"):
        result["warnings"].append("Un Track ID declara mas de un ISRC; se conservan las grabaciones separadas.")
    return result


def dashgo_suggestions(result: dict, evidence: list[dict], artists: list[str], raw: dict | None, *, isrc: str) -> dict | None:
    from lib.dashgo_catalog_artists import EVIDENCE_VERSION, valid_dashgo_evidence, native_names

    records = [entry for entry in evidence if entry.get("source") == "dashgo"
               and entry.get("adapter_version") == EVIDENCE_VERSION]
    if not records:
        return None
    result = copy.deepcopy(result)
    if len(records) != 1 or not valid_dashgo_evidence(records[0], isrc):
        result["principal_uncertain"] = True
        result["warnings"] = [*result.get("warnings", []), "Evidencia DashGo incompleta; se conserva la propuesta anterior."]
        return result
    entry = records[0]
    observations, native = entry["observations"], entry["native_artists"]
    inherited = entry.get("prior_artists") is not None or entry.get("manual_protected")
    reported = [name if inherited else canonical_artist(name) for name in (result.get("artists") or artists)]
    for observation in observations:
        for name in observation["artists"]:
            if artist_key(name) not in keys(reported):
                reported.append(canonical_artist(name))
    observed_sets = {frozenset(keys(row["artists"])) for row in observations}
    context_conflict = any(row.get("Track Artist") and row.get("Artist Name")
        and keys(native_names(row["Track Artist"])) != keys(native_names(row["Artist Name"])) for row in observations)
    native_status = "as_reported" if len(observed_sets) == 1 and native else "incomplete" if not native else "conflicting_participants"
    if native_status == "as_reported" and context_conflict:
        native_status = "conflicting_context"
    status = native_status
    if status == "as_reported" and artists and keys(artists) != keys(native):
        status = "cross_source_membership_difference" if keys(artists) <= keys(native) or keys(native) <= keys(artists) else "conflicting_participants"
    target = keys(artists[:1])
    uncertain = bool((raw or {}).get("principal_uncertain"))
    uncertain = uncertain or native_status != "as_reported" or len(native) != 1 or keys(native) != target
    uncertain = uncertain or entry.get("principal_status") != "single_artist" or keys([entry.get("principal_proposed") or ""]) != target
    uncertain = uncertain or keys(entry.get("artists") or []) != keys(artists) or bool(entry.get("manual_protected"))
    fuga = keys([record["artists"][0] for record in evidence if record.get("source") == "fuga"
                 and record.get("field") == "Asset Artist" and record.get("artists")])
    uncertain = uncertain or bool(fuga and fuga != target)
    uncertain = uncertain or ada_principal(evidence, artists) is True or onerpm_principal(evidence, artists, False) is True
    uncertain = uncertain or orchard_principal(evidence, artists, bool((raw or {}).get("principal_uncertain")), isrc=isrc) is True
    soundon = soundon_suggestions(result, evidence, artists, raw, isrc=isrc)
    uncertain = uncertain or bool(soundon and soundon.get("principal_uncertain"))
    uncertain = uncertain or any(record.get("principal_status") == "unresolved" for record in evidence
                                  if record.get("source") not in {None, "dashgo"})
    # Only DashGo's missing-source recognition is removed; real uncertainty stays independent.
    result.update(artists=reported, artists_reported=reported, principal_uncertain=bool(uncertain),
        participant_resolution_status=status, principal_resolution_status="unresolved" if uncertain else "single_artist",
        principal_scope="sole_declared_track_credit_not_explicit_role_or_contract_rights",
        participant_alternatives=[*result.get("participant_alternatives", []),
            {"source": "catalog_prior", "artists": artists},
            *[{"source": "dashgo", "artists": row["artists"], "statement_period": row["statement_period"]} for row in observations]])
    result["evidence"] = [*result.get("evidence", []), entry]
    if status != "as_reported":
        obsolete = "Las fuentes de pista discrepan; sugerimos solo los nombres comunes. Revisar antes de cerrar."
        result["warnings"] = [warning for warning in result.get("warnings", []) if warning != obsolete]
        result["warnings"].append("Los creditos DashGo difieren; se conserva la evidencia sin asignar porcentajes.")
    return result


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
