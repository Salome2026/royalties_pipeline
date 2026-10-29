"""SoundOn track-credit metadata; no financial or contractual mutation."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re

import polars as pl

from .catalog_manual_metadata import CORRECTIONS_PATH
from .soundon_identity import ISRC_PATTERN, REFERENCE_PATH
from .catalog_artist_dictionary import comparison_key as artist_key

RULE_VERSION = "SOUNDON-LECTURA-1"
EVIDENCE_VERSION = "SOUNDON-CAT003-adapter-1"
ARTIST_COLUMNS = {"catalog_artists": pl.List(pl.String), "catalog_artist_statement": pl.String,
                  "catalog_artist_evidence": pl.String, "catalog_artist_rule": pl.String}


def credit_parts(value: str) -> list[str]:
    names, seen = [], set()
    for part in str(value or "").split(","):
        name = part.strip()
        if name and artist_key(name) not in seen:
            names.append(name)
            seen.add(artist_key(name))
    return names


def keys(names):
    return {artist_key(name) for name in names}


def references(path):
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("version") != 1:
        raise ValueError("Unsupported SoundOn reference version")
    for isrc, entry in document["entries"].items():
        names = entry.get("artists") or []
        if (not ISRC_PATTERN.fullmatch(isrc) or not names or not entry.get("evidence")
                or any(not isinstance(name, str) or not name.strip() for name in names)
                or len(keys(names)) != len(names)):
            raise ValueError("Invalid approved SoundOn ISRC reference")
    return document["entries"]


def collect_soundon_artists(frame: pl.LazyFrame, *, reference_path: Path = REFERENCE_PATH) -> dict[str, dict]:
    columns = set(frame.collect_schema().names())
    if "source" not in columns:
        raise ValueError("SoundOn metadata requires source")
    soundon = frame.filter(pl.col("source") == "soundon")
    if soundon.select(pl.len()).collect().item() == 0:
        return {}
    required = {"account", "source_sheet", "asset_isrc", "ISRC", "Reporting Period", "Track Artists", "Track ID", "UPC Code",
                "statement_period", "statement_file_name", "statement_file_hash"}
    if missing := required - columns:
        raise ValueError("Missing SoundOn metadata evidence: " + ", ".join(sorted(missing)))
    if soundon.filter((pl.col("account").fill_null("") != "soundon")
                      | (pl.col("source_sheet").fill_null("") != "my_royalty")).select(pl.len()).collect().item():
        raise ValueError("Uncertified SoundOn account or nonempty Shares/control input")
    # Locators refer to the pinned SoundOn subset of standardized, not physical CSV lines.
    rows = (soundon.with_row_index("standardized_soundon_row", offset=1).select(
        "standardized_soundon_row", *sorted(required)).collect(engine="streaming").to_dicts())
    grouped, track_owners = defaultdict(list), defaultdict(set)
    for row in rows:
        isrc = str(row["asset_isrc"] or "")
        if not ISRC_PATTERN.fullmatch(isrc) or row["ISRC"] != isrc:
            raise ValueError("SoundOn native/normalized ISRC mismatch; no inferred identity")
        filename = re.fullmatch(r"SoundOn_royalty_monthly_statement_(\d{4})_(\d{2})_My Royalty\.csv", str(row["statement_file_name"] or ""))
        if (not row["Track Artists"] or not credit_parts(row["Track Artists"])
                or not row["statement_file_name"]
                or row["Reporting Period"] != row["statement_period"] or not filename
                or "-".join(filename.groups()) != row["statement_period"]
                or not re.fullmatch(r"[a-fA-F0-9]{64}", str(row["statement_file_hash"] or ""))
                or not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", str(row["statement_period"] or ""))):
            raise ValueError("Incomplete SoundOn track provenance")
        grouped[isrc].append(row)
        if row["Track ID"]:
            track_owners[row["Track ID"]].add(isrc)
    approved = references(reference_path)
    results = {}
    for isrc, values in sorted(grouped.items()):
        observations = {}
        for row in values:
            identifying = {name: row[name] for name in sorted(required)}
            token = json.dumps(identifying, ensure_ascii=True, sort_keys=True)
            if token not in observations:
                observations[token] = {**identifying, "artists": credit_parts(row["Track Artists"]),
                    "locator_kind": "standardized_soundon_subset_row", "standardized_rows": []}
            observations[token]["standardized_rows"].append(row["standardized_soundon_row"])
        observations = [observations[token] for token in sorted(observations)]
        alternatives = {frozenset(keys(row["artists"])) for row in observations}
        names = list(observations[0]["artists"])
        firsts = keys([row["artists"][0] for row in observations])
        status = "as_reported" if len(alternatives) == 1 else "conflicting_participants"
        principal_status = "single_artist" if len(names) == 1 else "order_only" if len(firsts) == 1 else "unresolved"
        ref = approved.get(isrc)
        if ref and alternatives == {frozenset(keys(ref["artists"]))}:
            names = list(ref["artists"])
            principal_status = "verified_isrc_reference"
        elif ref:
            status = "tokenization_unresolved" if any("," in name for name in ref["artists"]) else "reference_mismatch"
            principal_status = "unresolved"
        if status != "as_reported":
            principal_status = "unresolved"
        reported = []
        for name in [*names, *(name for row in observations for name in row["artists"])]:
            if artist_key(name) not in keys(reported):
                reported.append(name)
        results[isrc] = {"source": "soundon", "account": "soundon", "source_sheet": "my_royalty", "level": "track",
            "field": "Track Artists", "asset_isrc": isrc, "rule": RULE_VERSION, "adapter_version": EVIDENCE_VERSION,
            "identity_status": "resolved", "native_resolution_status": status, "native_artists": names,
            "artists_reported": reported, "principal_status": principal_status,
            "principal_proposed": names[0] if principal_status != "unresolved" else None,
            "principal_scope": "observed_credit_order_not_contract_rights", "isrc_reference": ref,
            "identity_relationship_status": "conflicting_track_id" if any(len(track_owners[row["Track ID"]]) > 1 for row in values if row["Track ID"]) else "compatible",
            "identity_relationship_conflicts": [{"track_id": track, "isrcs": sorted(owners)} for track, owners in sorted(track_owners.items())
                if len(owners) > 1 and isrc in owners],
            "observation_count": len(values), "observations": observations}
    return results


def enrich_soundon_catalog(catalog: pl.DataFrame, frame: pl.LazyFrame, *, reference_path: Path = REFERENCE_PATH,
                           corrections_path: Path = CORRECTIONS_PATH) -> pl.DataFrame:
    if catalog["catalog_key"].n_unique() != catalog.height:
        raise ValueError("Duplicate catalog keys in SoundOn metadata merge")
    metadata = collect_soundon_artists(frame, reference_path=reference_path)
    manual = {item["catalog_key"] for item in json.loads(corrections_path.read_text(encoding="utf-8"))["corrections"]
              if item.get("confirmed_by") and "artist_statement" in item}
    output = {name: [] for name in ARTIST_COLUMNS}
    for row in catalog.to_dicts():
        current = {name: row.get(name) for name in ARTIST_COLUMNS}
        entry = metadata.get(row.get("asset_isrc"))
        if entry is not None:
            entry = dict(entry)
            previous = row.get("catalog_artists")
            evidence = json.loads(current["catalog_artist_evidence"] or "[]")
            if not isinstance(evidence, list) or any(not isinstance(record, dict) for record in evidence):
                raise ValueError("Catalog evidence must be a list of source records")
            previous_proof = next((record for record in evidence if record.get("source") == "soundon"
                                   and record.get("adapter_version") == EVIDENCE_VERSION), None)
            protected = row["catalog_key"] in manual or bool(row.get("catalog_manual_correction_confirmed_by"))
            native = entry["native_artists"]
            if previous is None and not protected:
                current["catalog_artists"] = native if entry["native_resolution_status"] == "as_reported" else []
                current["catalog_artist_statement"] = " / ".join(current["catalog_artists"])
            artists = list(current["catalog_artists"] or [])
            prior_keys, native_keys = keys(artists), keys(native)
            status = entry["native_resolution_status"]
            if status == "as_reported" and prior_keys and prior_keys != native_keys:
                status = "cross_source_membership_difference" if prior_keys <= native_keys or native_keys <= prior_keys else "conflicting_participants"
            reported = list(artists)
            for name in entry["artists_reported"]:
                if artist_key(name) not in keys(reported):
                    reported.append(name)
            original_prior = previous_proof.get("prior_artists") if previous_proof and previous_proof.get("artists") == artists else previous
            entry.update(artists=artists, artists_reported=reported, prior_artists=original_prior,
                         participant_resolution_status=status, manual_protected=protected,
                         used_for_catalog=bool(artists and entry["native_resolution_status"] == "as_reported" and native_keys <= prior_keys))
            evidence = [record for record in evidence if not (record.get("source") == "soundon"
                        and record.get("adapter_version") == EVIDENCE_VERSION)]
            current["catalog_artist_evidence"] = json.dumps([*evidence, entry], ensure_ascii=True, sort_keys=True)
            rules = [value for value in str(current["catalog_artist_rule"] or "").split(" | ") if value]
            current["catalog_artist_rule"] = " | ".join(dict.fromkeys([*rules, RULE_VERSION]))
        for name in ARTIST_COLUMNS:
            output[name].append(current[name])
    return catalog.with_columns([pl.Series(name, output[name], dtype=dtype) for name, dtype in ARTIST_COLUMNS.items()])


def enrich_soundon_catalog_file(catalog: pl.DataFrame, path: Path) -> pl.DataFrame:
    if not path.exists():
        raise FileNotFoundError("Missing validated standardized SoundOn input")
    return enrich_soundon_catalog(catalog, pl.scan_parquet(path))
