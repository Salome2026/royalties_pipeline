"""Common, evidence-backed completion of track participants; never financial rights."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import polars as pl

from .catalog_artist_dictionary import canonical, comparison_key, unique
from .catalog_artist_evidence import records
from .catalog_manual_metadata import CORRECTIONS_PATH

RULE = "AUTO-002-COMMON-1"
FIELD = "catalog_participant_resolution"
ISRC = re.compile(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}")
HASH = re.compile(r"[a-fA-F0-9]{64}")
PERIOD = re.compile(r"20\d{2}-(?:0[1-9]|1[0-2])")
ARTIST_COLUMNS = {"catalog_artists": pl.List(pl.String), "catalog_artist_statement": pl.String,
                  "catalog_artist_evidence": pl.String, "catalog_artist_rule": pl.String}
SCOPES = {"fuga": "Asset Artist", "onerpm": "Artists", "ada": "Artist Name",
          "orchard": "TRACK ARTIST", "soundon": "Track Artists", "dashgo": "Track Artist"}


def keys(names):
    return frozenset(comparison_key(name) for name in names)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def native_records(evidence):
    return [entry for entry in evidence if not (entry.get("source") == "catalog" and entry.get("field") == FIELD)]


def native_digest(evidence):
    return digest(sorted(json.dumps(entry, ensure_ascii=True, sort_keys=True) for entry in native_records(evidence)))


def provenance(row):
    return bool(row.get("account") and row.get("statement_file_name")
                and HASH.fullmatch(str(row.get("statement_file_hash") or ""))
                and PERIOD.fullmatch(str(row.get("statement_period") or "")))


def names_valid(value):
    return isinstance(value, list) and bool(value) and all(isinstance(name, str) and name.strip() for name in value)


def _same_names(left, right):
    return names_valid(left) and names_valid(right) and list(map(comparison_key, left)) == list(map(comparison_key, right))


def _scoped_fuga_names(isrc, names):
    path = Path(__file__).with_name("fuga_catalog_artist_references.json")
    refs = json.loads(path.read_text(encoding="utf-8"))
    if refs.get("version") != 1:
        raise ValueError("Unknown FUGA reference version")
    aliases = {comparison_key(item["original_name"]): item["confirmed_name"] for item in refs["references"]
               if item.get("confirmed_by") and item["isrc"] == isrc}
    return unique([aliases.get(comparison_key(name), name) for name in names])


def _ada_title_guests(entry, observation, evidence, isrc):
    from .catalog_artist_extensions import RULE as FEAT_RULE, detect
    guests = []
    for title in evidence:
        if not (title.get("source") == "ada" and title.get("field") == "Catalogue Title" and title.get("rule") == FEAT_RULE
                and title.get("isrc") == isrc and title.get("file_hash") == observation.get("statement_file_hash")
                and title.get("file") == observation.get("statement_file_name") and title.get("row") == observation.get("source_row")):
            continue
        supplied = {"source": "ada", "asset_isrc": isrc, "native_entity_key": "ISRC:" + isrc,
            "account": title.get("account"), "native_source_sheet": title.get("sheet"),
            "Artist Name": title.get("artist_raw"), "Catalogue Title": title.get("title_raw")}
        if (title.get("artist_raw") != observation.get("Artist Name")
                or title.get("title_raw") != observation.get("Catalogue Title")
                or title.get("account") != observation.get("account")):
            raise ValueError("ADA title credit does not match its native observation")
        found = [item["name"] for item in detect(supplied)["candidates"]]
        if not found or found != title.get("candidate_names"):
            raise ValueError("Invalid certified ADA title-credit evidence")
        guests.extend(found)
    return unique(guests)


def track_claims(row, evidence):
    """Consume certified structured credits, keeping each source's grammar and scope."""
    isrc, claims, issues = row["asset_isrc"], [], []

    def add(entry, observation, artists, *, can_complete=True):
        reference = {name: observation.get(name) for name in
                     ("account", "statement_file_name", "statement_file_hash", "statement_period", "source_row", "row", "standardized_row")
                     if observation.get(name) is not None}
        claims.append({"source": entry["source"], "field": entry["field"], "artists": unique(artists),
                       "reference": reference, "can_complete": can_complete})

    for entry in sorted(evidence, key=lambda item: json.dumps(item, sort_keys=True)):
        source = entry.get("source")
        if entry.get("field") != SCOPES.get(source) or source not in SCOPES:
            continue
        try:
            if source == "fuga":
                from .fuga_catalog_artists import parse_credit
                parsed, status = parse_credit(str(entry.get("raw") or ""))
                valid = (entry.get("used_for_catalog") is True and entry.get("status") == status == "fuga_comma_and_featuring"
                    and provenance(entry) and str(entry.get("Product Reference") or "").isdigit()
                    and str(entry.get("Asset Reference") or "").isdigit() and _same_names(entry.get("artists"), parsed))
                if not valid:
                    raise ValueError("Invalid native FUGA track proof")
                add(entry, entry, _scoped_fuga_names(isrc, parsed))
            elif source == "onerpm":
                from .onerpm_catalog_artists import RULE_VERSION, parse_credits
                parsed = parse_credits(entry.get("raw") or "")
                valid = (entry.get("catalog_rule") == RULE_VERSION and entry.get("identity_status") == "resolved"
                    and entry.get("native_resolution_status") == entry.get("status") == parsed["status"] == "resolved"
                    and entry.get("level") == "track" and entry.get("sheet") in {"Masters", "Shares In & Out"}
                    and entry.get("product_type") in {"Track", "Video Track"} and provenance(entry)
                    and type(entry.get("row")) is int and entry["row"] > 1
                    and _same_names(entry.get("artists"), parsed["artists"]) and entry.get("credits") == parsed["credits"])
                if not valid:
                    raise ValueError("Invalid native ONErpm track proof")
                add(entry, entry, parsed["artists"])
            elif source == "ada":
                from .ada_catalog_artists import EVIDENCE_VERSION, parse_credit
                from .statement_period import from_ada_filename
                if (entry.get("adapter_version") != EVIDENCE_VERSION or entry.get("identity_status") != "resolved"
                        or entry.get("native_resolution_status") != "resolved"):
                    raise ValueError("Unresolved ADA interpretation")
                observations = [item for item in entry.get("observations") or [] if item.get("source") == "ada"]
                if not observations:
                    raise ValueError("Missing native ADA observations")
                for item in observations:
                    parsed, grammar = parse_credit(item.get("artist_catalog_style") or "")
                    if (item.get("asset_isrc") != isrc or item.get("native_entity_key") != "ISRC:" + isrc
                            or item.get("native_source_sheet") != "Distribution Statement" or not provenance(item)
                            or item.get("account") not in {"indyana_records", "mawz"}
                            or from_ada_filename(str(item.get("statement_file_name") or "")).period != item.get("statement_period")
                            or type(item.get("source_row")) is not int or item["source_row"] < 1
                            or item.get("grammar_status") != grammar or not _same_names(item.get("artists"), parsed)):
                        raise ValueError("Invalid native ADA credit observation")
                    if grammar != "resolved":
                        raise ValueError("Unresolved ADA credit grammar")
                    add(entry, item, [*parsed, *_ada_title_guests(entry, item, evidence, isrc)],
                        can_complete=item.get("artist_credit_status") in {"as_reported", "confirmed_prefix"})
            else:
                if source == "orchard":
                    from .orchard_catalog_artists import EVIDENCE_VERSION, RULE_VERSION, parse_credit
                    parser, native_field, good = parse_credit, "TRACK ARTIST", "resolved"
                elif source == "soundon":
                    from .soundon_catalog_artists import EVIDENCE_VERSION, RULE_VERSION, credit_parts
                    parser, native_field, good = credit_parts, "Track Artists", "as_reported"
                else:
                    from .dashgo_catalog_artists import EVIDENCE_VERSION, RULE_VERSION, native_names, valid_dashgo_evidence
                    parser, native_field, good = native_names, "Track Artist", "as_reported"
                    if not valid_dashgo_evidence(entry, isrc):
                        raise ValueError("Invalid native DashGo evidence")
                native, observations = entry.get("native_artists"), entry.get("observations")
                if (entry.get("adapter_version") != EVIDENCE_VERSION or entry.get("rule") != RULE_VERSION
                        or entry.get("asset_isrc") != isrc or entry.get("level") != "track"
                        or entry.get("identity_status") != "resolved" or entry.get("native_resolution_status") != good
                        or entry.get("identity_relationship_conflicts") or not names_valid(native)
                        or not isinstance(observations, list) or not observations):
                    raise ValueError("Unresolved native track interpretation")
                for item in observations:
                    parsed = parser(item.get(native_field))
                    native_isrc, asset_isrc = item.get("ISRC"), item.get("asset_isrc")
                    if source == "orchard":
                        native_isrc = re.sub(r"[\s-]", "", str(native_isrc or "").strip().upper())
                    elif source == "dashgo":
                        from .dashgo_catalog_artists import normalized_isrc
                        native_isrc = normalized_isrc(native_isrc)
                        asset_isrc = normalized_isrc(asset_isrc)
                    if (asset_isrc != isrc or native_isrc != isrc or not provenance(item)
                            or not _same_names(item.get("artists"), parsed) or keys(parsed) != keys(native)):
                        raise ValueError("Native track list lacks consistent ISRC/credit proof")
                    if source == "soundon":
                        filename = re.fullmatch(r"SoundOn_royalty_monthly_statement_(\d{4})_(\d{2})_My Royalty\.csv", str(item.get("statement_file_name") or ""))
                        positions = item.get("standardized_rows")
                        if (item.get("account") != "soundon" or item.get("source_sheet") != "my_royalty"
                                or item.get("Reporting Period") != item.get("statement_period") or not filename
                                or "-".join(filename.groups()) != item.get("statement_period")
                                or item.get("locator_kind") != "standardized_soundon_subset_row"
                                or not isinstance(positions, list) or not positions
                                or any(type(index) is not int or index < 1 for index in positions)):
                            raise ValueError("SoundOn credit outside certified scope")
                    add(entry, item, parsed)
        except (ValueError, TypeError, KeyError) as exc:
            issues.append({"source": source, "field": entry.get("field"), "reason": str(exc)})
    # Repeated months are observations, not votes for an artist list.
    grouped = {}
    for item in claims:
        token = (item["source"], item["field"], tuple(sorted(keys(item["artists"]))), item["can_complete"])
        group = grouped.setdefault(token, {"source": item["source"], "field": item["field"],
            "artists": sorted(item["artists"], key=comparison_key), "can_complete": item["can_complete"], "references": []})
        if item["reference"] not in group["references"]:
            group["references"].append(item["reference"])
    result = []
    for token in sorted(grouped):
        item = grouped[token]
        item["references"].sort(key=lambda ref: json.dumps(ref, sort_keys=True))
        result.append(item)
    return result, sorted({json.dumps(item, sort_keys=True) for item in issues})


def protected_keys():
    return {item["catalog_key"] for item in json.loads(CORRECTIONS_PATH.read_text(encoding="utf-8"))["corrections"]
            if item.get("confirmed_by") and "artist_statement" in item}


def resolution_from_evidence(isrc, artists, evidence_json):
    evidence = records(evidence_json)
    derived = [item for item in evidence if item.get("source") == "catalog" and item.get("field") == FIELD]
    if not derived:
        return None
    if len(derived) != 1:
        raise ValueError("Multiple common participant resolutions")
    result = derived[0]
    if (result.get("rule") != RULE or result.get("catalog_key") != "ISRC:" + isrc
            or result.get("native_digest") != native_digest(evidence) or result.get("artists") != artists
            or result.get("result_digest") != digest({key: value for key, value in result.items() if key != "result_digest"})):
        raise ValueError("Common participant resolution does not match catalogue/evidence")
    return result


def resolve_row(row, *, manual_keys=None):
    if (row.get("scope", "habitual") != "habitual" or not ISRC.fullmatch(str(row.get("asset_isrc") or ""))
            or row.get("catalog_key") != "ISRC:" + row["asset_isrc"]):
        return dict(row), None
    evidence = records(row.get("catalog_artist_evidence"))
    manual_keys = protected_keys() if manual_keys is None else manual_keys
    protected = bool(row["catalog_key"] in manual_keys or row.get("catalog_manual_correction_confirmed_by")
                     or row.get("artist_exclusions"))
    existing = [item for item in evidence if item.get("source") == "catalog" and item.get("field") == FIELD]
    if existing:
        try:
            cached = resolution_from_evidence(row["asset_isrc"], row.get("catalog_artists"), row.get("catalog_artist_evidence"))
            if cached.get("manual_protected") == protected:
                return dict(row), cached
        except ValueError:
            pass
    before = row.get("catalog_artists")
    prior = list(before or [])
    claims, issues = track_claims(row, native_records(evidence))
    if not claims and not issues:
        return dict(row), None
    artists = list(prior)
    union = keys([*prior, *(name for item in claims for name in item["artists"])])
    complete = [item for item in claims if item["can_complete"] and keys(item["artists"]) == union]
    if protected:
        status = "manual_protected"
    elif issues:
        status = "review_required"
    elif union == keys(prior):
        status = "consistent"
    elif not complete:
        status = "conflicting_participants"
    else:
        display = {comparison_key(name): canonical(name) for item in complete for name in item["artists"]}
        artists.extend(display[key] for key in sorted(union - keys(prior)))
        status = "completed_from_native_track" if keys(artists) != keys(prior) else "consistent"
    result = {"source": "catalog", "field": FIELD, "rule": RULE, "catalog_key": row["catalog_key"],
        "native_digest": native_digest(evidence), "original_artists": before, "artists": artists if artists else before,
        "status": status, "manual_protected": protected, "claims": claims,
        "issues": [json.loads(value) for value in issues], "added": [name for name in artists if comparison_key(name) not in keys(prior)],
        "ordering_scope": "preserve_existing_first_and_order_no_new_principal_or_rights",
        "contractual_rights_inferred": False}
    result["result_digest"] = digest(result)
    native = native_records(evidence)
    rules = [value for value in str(row.get("catalog_artist_rule") or "").split(" | ") if value and value != RULE]
    output = {**row, "catalog_artists": result["artists"],
        "catalog_artist_statement": " / ".join(artists) if result["added"] else row.get("catalog_artist_statement"),
        "catalog_artist_evidence": json.dumps([*native, result], ensure_ascii=True, sort_keys=True),
        "catalog_artist_rule": " | ".join([*rules, RULE])}
    return output, result


def resolve_catalog_participants(catalog):
    if catalog["catalog_key"].n_unique() != catalog.height:
        raise ValueError("Duplicate catalogue keys before common participant resolution")
    manual, values = protected_keys(), {name: [] for name in ARTIST_COLUMNS}
    for row in catalog.to_dicts():
        resolved, _ = resolve_row(row, manual_keys=manual)
        for name in values:
            values[name].append(resolved.get(name))
    return catalog.with_columns([pl.Series(name, values[name], dtype=dtype) for name, dtype in ARTIST_COLUMNS.items()])
