"""Approved metadata-only dictionary and explicit ADA title credits."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re

import polars as pl

from .catalog_artist_dictionary import ALIASES, canonical, key, unique

RULE = "ADA-FEAT-TITLE-TRIAL-1"
ISRC = re.compile(r"[A-Z]{2}[A-Z0-9]{3}\d{7}")
FEAT = re.compile(r"\((?:feat\.?|featuring|ft\.?)\s+([^()]+)\)", re.I)
PENDING_KEYS = frozenset()
ARTIST_COLUMNS = {"catalog_artists": pl.List(pl.String), "catalog_artist_statement": pl.String,
                  "catalog_artist_rule": pl.String, "catalog_artist_evidence": pl.String}


def credit_identity_evidence(value):
    """Compare approved name aliases without changing literal source fields."""
    if isinstance(value, list):
        return [credit_identity_evidence(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {name: credit_identity_evidence(item) for name, item in value.items()}
    for name in ("artists", "native_artists"):
        if isinstance(value.get(name), list):
            result[name] = [canonical(artist) if isinstance(artist, str) else artist for artist in value[name]]
    if isinstance(value.get("principal_proposed"), str):
        result["principal_proposed"] = canonical(value["principal_proposed"])
    return result


def detect(row):
    isrc = str(row.get("asset_isrc") or "")
    if (row.get("scope", "habitual") != "habitual" or row.get("source") != "ada"
            or row.get("account") not in {"indyana_records", "mawz"}
            or not ISRC.fullmatch(isrc) or row.get("native_entity_key") != "ISRC:" + isrc
            or row.get("native_source_sheet") != "Distribution Statement"):
        return {"candidates": [], "status": "outside_certified_track_scope"}
    if not str(row.get("Artist Name") or "").strip():
        return {"candidates": [], "status": "missing_native_artist_credit"}
    title = str(row.get("Catalogue Title") or "")
    balance = 0
    for char in title:
        if char == "(":
            balance += 1
        elif char == ")":
            balance -= 1
        if balance not in (0, 1):
            return {"candidates": [], "status": "ambiguous_parentheses"}
    if balance:
        return {"candidates": [], "status": "ambiguous_parentheses"}
    candidates = []
    for match in FEAT.finditer(title):
        if not any(char.isalnum() for char in title[:match.start()]):
            return {"candidates": [], "status": "missing_base_track_title"}
        guest = match.group(1).strip()
        # Multi-name bodies remain evidence until a separate grammar is approved.
        if (re.search(r"[,;&/|]|\band\b|\bfeat\b|\bfeaturing\b|\bft\b", guest, re.I)
                or not any(char.isalpha() for char in guest)
                or key(guest) in {"remix", "cover", "live", "en vivo", "radio edit", "instrumental", "n/a", "unknown"}):
            return {"candidates": [], "status": "ambiguous_or_non_artist_body"}
        candidates.append({"name": canonical(guest), "raw_fragment": match.group(0),
                           "source_field": "Catalogue Title", "role_evidence": "explicit_feat_marker"})
    return {"candidates": candidates, "status": "explicit_title_credit" if candidates else "no_explicit_feat"}


def enrich(catalog_row, observations):
    if catalog_row.get("scope", "habitual") != "habitual":
        return dict(catalog_row), {"detected_names": [], "issues": [{"status": "outside_workspace"}],
                                   "manual_protected": False, "copy_only": True}
    original = list(catalog_row.get("catalog_artists") or [])
    current = unique(original)
    evidence = json.loads(catalog_row.get("catalog_artist_evidence") or "[]")
    evidence_seen = {json.dumps(item, ensure_ascii=True, sort_keys=True) for item in evidence}
    candidates, issues = [], []
    for row in sorted(observations, key=lambda v: (str(v.get("statement_period") or ""), int(v.get("source_row") or 0)), reverse=True):
        detected = detect(row)
        if detected["candidates"]:
            candidates.extend(detected["candidates"])
            entry = {"source": "ada", "field": "Catalogue Title", "rule": RULE,
                "isrc": row["asset_isrc"], "title_raw": row["Catalogue Title"], "artist_raw": row["Artist Name"],
                "account": row.get("account"), "file": row.get("statement_file_name"),
                "file_hash": row.get("statement_file_hash"), "sheet": row.get("native_source_sheet"),
                "row": row.get("source_row"), "candidate_names": [v["name"] for v in detected["candidates"]],
                "copy_only": True, "contractual_rights_inferred": False}
            token = json.dumps(entry, ensure_ascii=True, sort_keys=True)
            if token not in evidence_seen:
                evidence.append(entry)
                evidence_seen.add(token)
        elif detected["status"] not in {"no_explicit_feat", "outside_certified_track_scope"}:
            issues.append({"status": detected["status"], "file": row.get("statement_file_name"),
                           "row": row.get("source_row"), "title": row.get("Catalogue Title")})
    protected = bool(catalog_row.get("catalog_manual_correction_confirmed_by") or catalog_row.get("artist_exclusions"))
    diagnosis = {"detected_names": unique([r["name"] for r in candidates]), "issues": issues,
                 "manual_protected": protected, "copy_only": True}
    if protected or (not candidates and current == original):
        return dict(catalog_row), diagnosis
    if candidates and not protected:
        current = unique([*current, *(r["name"] for r in candidates)])
    rules = [v for v in str(catalog_row.get("catalog_artist_rule") or "").split(" | ") if v]
    if candidates:
        rules.append(RULE)
    if current != original:
        rules.append("HUMAN-ALIAS-APPROVAL-20261027" if unique(original) != original else RULE)
    output = {**catalog_row, "catalog_artists": current,
        "catalog_artist_statement": " / ".join(current) if current != original else catalog_row.get("catalog_artist_statement"),
        "catalog_artist_rule": " | ".join(dict.fromkeys(rules)) or catalog_row.get("catalog_artist_rule"),
        "catalog_artist_evidence": json.dumps(evidence, ensure_ascii=True, sort_keys=True) if candidates else catalog_row.get("catalog_artist_evidence")}
    return output, diagnosis


def enrich_catalog_artist_extensions(catalog: pl.DataFrame, native: pl.DataFrame) -> pl.DataFrame:
    if catalog["catalog_key"].n_unique() != catalog.height:
        raise ValueError("Claves duplicadas en extension de artistas")
    by_key = defaultdict(list)
    for observation in native.to_dicts():
        by_key[observation.get("native_entity_key")].append(observation)
    values = {name: [] for name in ARTIST_COLUMNS}
    for row in catalog.to_dicts():
        enriched = row if row["catalog_key"] in PENDING_KEYS else enrich(row, by_key[row["catalog_key"]])[0]
        for name in values:
            values[name].append(enriched.get(name))
    return catalog.with_columns([pl.Series(name, values[name], dtype=dtype) for name, dtype in ARTIST_COLUMNS.items()])


def enrich_catalog_artist_extensions_file(catalog: pl.DataFrame, path: Path) -> pl.DataFrame:
    return enrich_catalog_artist_extensions(catalog, pl.read_parquet(path))


def contract_credit_base(isrc: str, artists: list[str] | None, evidence_json: str | None) -> dict | None:
    """Explicit guests extend participation, not the pre-existing principal evidence."""
    if artists is None or "ISRC:" + isrc in PENDING_KEYS:
        return None
    evidence = json.loads(evidence_json or "[]")
    titles = [entry for entry in evidence if entry.get("source") == "ada" and entry.get("rule") == RULE]
    if not titles:
        return None
    guests = set()
    for entry in titles:
        if (entry.get("isrc") != isrc or not entry.get("file") or not entry.get("file_hash")
                or not isinstance(entry.get("row"), int) or entry["row"] < 1):
            return None
        observation = {"scope": "habitual", "source": "ada", "account": entry.get("account"), "asset_isrc": isrc,
            "native_entity_key": "ISRC:" + isrc, "native_source_sheet": entry.get("sheet"),
            "Artist Name": entry.get("artist_raw"), "Catalogue Title": entry.get("title_raw")}
        detected = detect(observation)
        found = [candidate["name"] for candidate in detected["candidates"]]
        if not found or found != entry.get("candidate_names"):
            return None
        guests.update(key(name) for name in found)
    native = {key(canonical(name)) for entry in evidence if entry not in titles and entry.get("used_for_catalog")
              for name in entry.get("artists", []) if isinstance(name, str)}
    base = [name for name in artists if key(name) not in guests or key(name) in native]
    if not base or not guests <= {key(name) for name in artists}:
        return None
    return {"artists": base, "evidence": json.dumps([entry for entry in evidence if entry not in titles], ensure_ascii=True, sort_keys=True),
        "title_evidence": [{"source": "ada", "field": "Catalogue Title", "raw": entry["title_raw"],
            "artists": entry["candidate_names"], "used": True, "file": entry["file"], "row": entry["row"],
            "rule": RULE, "contractual_rights_inferred": False} for entry in titles]}
