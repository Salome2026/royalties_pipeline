"""DashGo native track-credit metadata. No money, identity or contract mutation."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

import polars as pl

from .catalog_manual_metadata import CORRECTIONS_PATH
from .catalog_artist_dictionary import comparison_key as artist_key

RULE_VERSION = "DASHGO-LECTURA-1"
EVIDENCE_VERSION = "DASHGO-CAT003-adapter-1"
ARTIST_COLUMNS = {"catalog_artists": pl.List(pl.String), "catalog_artist_statement": pl.String,
                  "catalog_artist_evidence": pl.String, "catalog_artist_rule": pl.String}
NATIVE_FIELDS = ["Transaction Date", "Store", "Region", "Artist Name", "Label Name", "Album Name", "Track Artist",
    "UPC", "Track Title", "VideoId", "ChannelId", "ISRC", "Label Track ID", "Composers", "Units", "Currency",
    "Product Type", "Use Type", "Revenue", "Exchange Rate", "USD Revenue", "Distribution Rate", "Net Revenue",
    "Deal Share", "Cover Song", "Mechanical Royalty", "Pub Admin Fee", "Payable", "Revenue Split (Y/N)"]
CONTROL_LABELS = {"Gross Deal Revenue:", "Split Pay Revenue:", "Total Payable (US):", "Total Payable (NON-US):", "Total Payable:"}
PROVENANCE = {"account", "asset_isrc", "statement_period", "statement_file_name", "statement_file_hash"}
CREDIT_FIELDS = ["asset_isrc", "ISRC", "Track Artist", "Artist Name", "account", "statement_period", "statement_file_name", "statement_file_hash"]
CONTEXT_FIELDS = ["Track Title", "Album Name", "Composers", "Label Name", "UPC", "VideoId", "ChannelId", "Label Track ID", "Product Type"]


def normalized_isrc(value) -> str | None:
    cleaned = re.sub(r"[^A-Z0-9]", "", str(value or "").strip().upper())
    return cleaned if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}", cleaned) else None


def keys(names):
    return {artist_key(name) for name in names}


def native_names(value) -> list[str]:
    # DashGo has no certified multi-artist delimiter; a group name remains intact.
    name = str(value or "").strip()
    return [name] if name else []


def provenance_complete(row: dict) -> bool:
    filename = re.fullmatch(r"MAWZ Records-(0[1-9]|1[0-2])-(\d{2})\.csv", str(row.get("statement_file_name") or ""))
    return bool(row.get("account") == "mawzrecords" and filename
        and row.get("statement_period") == "20" + filename[2] + "-" + filename[1]
        and re.fullmatch(r"[a-fA-F0-9]{64}", str(row.get("statement_file_hash") or "")))


def collect_dashgo_artists(frame: pl.LazyFrame) -> dict[str, dict]:
    columns = set(frame.collect_schema().names())
    if "source" not in columns:
        raise ValueError("DashGo metadata requires source")
    subset = frame.filter(pl.col("source") == "dashgo")
    if subset.select(pl.len()).collect().item() == 0:
        return {}
    if missing := (set(NATIVE_FIELDS) | PROVENANCE) - columns:
        raise ValueError("Missing DashGo native metadata evidence: " + ", ".join(sorted(missing)))
    selected = sorted(set(NATIVE_FIELDS) | PROVENANCE | ({"source_sheet"} if "source_sheet" in columns else set()))
    # These positions refer to the entire DashGo standardized subset, including its legacy footers.
    rows = subset.with_row_index("standardized_dashgo_row", offset=1).select("standardized_dashgo_row", *selected).collect(engine="streaming").to_dicts()
    grouped = defaultdict(list)
    for row in rows:
        if not provenance_complete(row) or row.get("source_sheet") not in (None, "", "detail"):
            raise ValueError("Uncertified DashGo account, policy sheet or statement provenance")
        payable = row.get("Payable")
        if payable is None or str(payable).strip() == "":
            blank = not any(row.get(name) not in (None, "") for name in NATIVE_FIELDS)
            control = row.get("ISRC") in CONTROL_LABELS and not any(row.get(name) not in (None, "") for name in NATIVE_FIELDS[:11] + NATIVE_FIELDS[13:])
            if not blank and not control:
                raise ValueError("Unclassified DashGo row without Payable; metadata cannot discard it")
            if control:
                try:
                    if not Decimal(str(row["Label Track ID"])).is_finite():
                        raise ValueError("Non-finite DashGo control")
                except (InvalidOperation, TypeError):
                    raise ValueError("Invalid DashGo control")
            continue
        try:
            if not Decimal(str(payable)).is_finite():
                raise ValueError("Non-finite DashGo Payable")
        except InvalidOperation:
            raise ValueError("Invalid DashGo Payable")
        native, reported = normalized_isrc(row["ISRC"]), normalized_isrc(row["asset_isrc"])
        if native != reported:
            raise ValueError("DashGo native/standardized ISRC mismatch; no inferred identity")
        if native is None and (str(row["ISRC"] or "").strip() or str(row["asset_isrc"] or "").strip()):
            raise ValueError("Uncertified DashGo ISRC metadata; original income is not rewritten")
        if native is None:
            # Product/video/text money and its context stay in the unchanged source, not in ISRC participants.
            continue
        grouped[native].append(row)
    output = {}
    for isrc, values in sorted(grouped.items()):
        grouped_observations = {}
        for row in values:
            original = {field: row[field] for field in CREDIT_FIELDS}
            token = json.dumps(original, ensure_ascii=True, sort_keys=True)
            if token not in grouped_observations:
                grouped_observations[token] = {**original, "artists": native_names(row["Track Artist"]),
                    "locator_kind": "standardized_dashgo_subset_row", "standardized_rows": []}
            grouped_observations[token]["standardized_rows"].append(row["standardized_dashgo_row"])
        observations = [grouped_observations[token] for token in sorted(grouped_observations)]
        alternatives = {frozenset(keys(row["artists"])) for row in observations}
        native = []
        for observation in observations:
            for name in observation["artists"]:
                if artist_key(name) not in keys(native):
                    native.append(name)
        status = "as_reported" if len(alternatives) == 1 and native else "incomplete" if not native else "conflicting_participants"
        context_conflict = any(row["Track Artist"] and row["Artist Name"] and keys(native_names(row["Track Artist"])) != keys(native_names(row["Artist Name"])) for row in observations)
        if status == "as_reported" and context_conflict:
            status = "conflicting_context"
        principal_ok = status == "as_reported" and len(native) == 1
        output[isrc] = {"source": "dashgo", "account": "mawzrecords", "source_sheet": "detail",
            "source_sheet_origin": "dashgo_detail_policy", "native_source_sheet": None, "level": "track",
            "field": "Track Artist", "asset_isrc": isrc, "rule": RULE_VERSION, "adapter_version": EVIDENCE_VERSION,
            "identity_status": "resolved", "native_resolution_status": status, "native_artists": native,
            "artists_reported": native, "principal_status": "single_artist" if principal_ok else "unresolved",
            "principal_proposed": native[0] if principal_ok else None, "principal_scope": "sole_declared_track_credit_not_explicit_role_or_contract_rights",
            "observation_count": len(values), "observations": observations,
            "context_original": {field: sorted({str(row[field]) for row in values if row[field] not in (None, "")}) for field in CONTEXT_FIELDS}}
    return output


def valid_dashgo_evidence(entry: dict, isrc: str) -> bool:
    if (entry.get("source") != "dashgo" or entry.get("account") != "mawzrecords"
            or entry.get("source_sheet") != "detail" or entry.get("source_sheet_origin") != "dashgo_detail_policy"
            or entry.get("adapter_version") != EVIDENCE_VERSION or entry.get("rule") != RULE_VERSION
            or entry.get("asset_isrc") != isrc or entry.get("identity_status") != "resolved"
            or entry.get("field") != "Track Artist" or entry.get("level") != "track"):
        return False
    observations, native = entry.get("observations"), entry.get("native_artists")
    if not isinstance(observations, list) or not observations or not isinstance(native, list) or any(not isinstance(name, str) or not name.strip() for name in native):
        return False
    observed = set()
    count = 0
    for row in observations:
        if not isinstance(row, dict) or not provenance_complete(row):
            return False
        positions = row.get("standardized_rows")
        if (normalized_isrc(row.get("asset_isrc")) != isrc or normalized_isrc(row.get("ISRC")) != isrc
                or not isinstance(row.get("Track Artist"), (str, type(None)))
                or not isinstance(row.get("Artist Name"), (str, type(None)))
                or not isinstance(row.get("artists"), list)
                or any(not isinstance(name, str) for name in row["artists"])
                or list(map(artist_key, row["artists"])) != list(map(artist_key, native_names(row.get("Track Artist"))))
                or row.get("locator_kind") != "standardized_dashgo_subset_row"
                or not isinstance(positions, list) or not positions
                or any(type(index) is not int or index < 1 for index in positions)):
            return False
        observed.update(keys(row["artists"]))
        count += len(positions)
    return observed == keys(native) and entry.get("observation_count") == count


def enrich_dashgo_catalog(catalog: pl.DataFrame, frame: pl.LazyFrame, *, corrections_path: Path = CORRECTIONS_PATH) -> pl.DataFrame:
    if catalog["catalog_key"].n_unique() != catalog.height:
        raise ValueError("Duplicate catalog keys in DashGo metadata merge")
    metadata = collect_dashgo_artists(frame)
    corrections = json.loads(corrections_path.read_text(encoding="utf-8"))["corrections"]
    manual = {entry["catalog_key"] for entry in corrections if entry.get("confirmed_by") and "artist_statement" in entry}
    output = {name: [] for name in ARTIST_COLUMNS}
    for row in catalog.to_dicts():
        current = {name: row.get(name) for name in ARTIST_COLUMNS}
        source_entry = metadata.get(row.get("asset_isrc"))
        if source_entry is not None:
            entry = dict(source_entry)
            evidence = json.loads(current["catalog_artist_evidence"] or "[]")
            if not isinstance(evidence, list) or any(not isinstance(record, dict) for record in evidence):
                raise ValueError("Catalog evidence must be a list of source records")
            prior_proof = next((record for record in evidence if record.get("source") == "dashgo" and record.get("adapter_version") == EVIDENCE_VERSION), None)
            previous = row.get("catalog_artists")
            protected = row["catalog_key"] in manual or bool(row.get("catalog_manual_correction_confirmed_by"))
            if previous is None and not protected:
                current["catalog_artists"] = entry["native_artists"] if entry["native_resolution_status"] == "as_reported" else []
                names = current["catalog_artists"]
                prior_display = row.get("artist_statement")
                # The display is shared with existing reports; completing credits must not rewrite it.
                current["catalog_artist_statement"] = prior_display if prior_display is not None else " / ".join(names) if names else None
            artists = list(current["catalog_artists"] or [])
            status = entry["native_resolution_status"]
            if status == "as_reported" and artists and keys(artists) != keys(entry["native_artists"]):
                status = "cross_source_membership_difference" if keys(artists) <= keys(entry["native_artists"]) or keys(entry["native_artists"]) <= keys(artists) else "conflicting_participants"
            reported = list(artists)
            for name in entry["artists_reported"]:
                if artist_key(name) not in keys(reported):
                    reported.append(name)
            original_prior = prior_proof.get("prior_artists") if prior_proof and prior_proof.get("artists") == artists else previous
            entry.update(artists=artists, artists_reported=reported, prior_artists=original_prior,
                participant_resolution_status=status, manual_protected=protected,
                display_scope="preserved_current_catalog_display",
                used_for_catalog=bool(artists and entry["native_resolution_status"] == "as_reported" and keys(entry["native_artists"]) <= keys(artists)))
            evidence = [record for record in evidence if not (record.get("source") == "dashgo" and record.get("adapter_version") == EVIDENCE_VERSION)]
            current["catalog_artist_evidence"] = json.dumps([*evidence, entry], ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            rules = [rule for rule in str(current["catalog_artist_rule"] or "").split(" | ") if rule]
            current["catalog_artist_rule"] = " | ".join(dict.fromkeys([*rules, RULE_VERSION]))
        for name in ARTIST_COLUMNS:
            output[name].append(current[name])
    return catalog.with_columns([pl.Series(name, output[name], dtype=dtype) for name, dtype in ARTIST_COLUMNS.items()])


def enrich_dashgo_catalog_file(catalog: pl.DataFrame, path: Path) -> pl.DataFrame:
    if not path.exists():
        raise FileNotFoundError("Missing validated standardized DashGo input")
    return enrich_dashgo_catalog(catalog, pl.scan_parquet(path))
