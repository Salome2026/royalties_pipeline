"""Orchard track-credit metadata. Financial observations and identities are never rewritten."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
import unicodedata

import polars as pl

from .catalog_manual_metadata import CORRECTIONS_PATH

RULE_VERSION = "ORCHARD-LECTURA-1"
EVIDENCE_VERSION = "ORCHARD-CAT003-adapter-1"
ARTIST_COLUMNS = {"catalog_artists": pl.List(pl.String), "catalog_artist_statement": pl.String,
                  "catalog_artist_evidence": pl.String, "catalog_artist_rule": pl.String}
ISRC = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")


def name_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    return re.sub(r"\s+", " ", "".join(c for c in text if not unicodedata.combining(c))).strip().casefold()


def parse_credit(value: str) -> list[str]:
    result, seen = [], set()
    for part in str(value or "").split("|"):
        name = re.sub(r"\s+", " ", part).strip()
        if name and name_key(name) not in seen:
            result.append(name)
            seen.add(name_key(name))
    return result


def collect_orchard_artists(frame: pl.LazyFrame) -> dict[str, dict]:
    columns = set(frame.collect_schema().names())
    if not {"source", "statement_type"} <= columns:
        raise ValueError("Orchard metadata requires source and statement_type")
    modern = frame.filter((pl.col("source") == "orchard") & (pl.col("statement_type") == "orchard_statement"))
    if modern.select(pl.len()).collect().item() == 0:
        return {}
    required = {"asset_isrc", "ISRC", "TRACK", "TRACK ARTIST", "PRODUCT ARTIST", "account",
                "statement_period", "statement_file_name", "statement_file_hash"}
    if not required <= columns:
        raise ValueError("Missing Orchard track evidence: " + ", ".join(sorted(required - columns)))
    selected = sorted(required | ({"TRACK VERSION", "PRODUCT", "PRODUCT VERSION"} & columns))
    # This locator is a row in the pinned standardized dataset, not a fabricated CSV line number.
    rows = modern.with_row_index("standardized_row", offset=1).select("standardized_row", *selected).unique(
        subset=selected, maintain_order=True).collect(engine="streaming").to_dicts()
    by_isrc = defaultdict(list)
    for row in rows:
        original_isrc = str(row["asset_isrc"] or "")
        key = re.sub(r"[\s-]", "", original_isrc.strip().upper())
        if not ISRC.fullmatch(key):
            continue
        if original_isrc != key:
            row["asset_isrc_original"] = original_isrc
            row["asset_isrc"] = key
        native_isrc = re.sub(r"[\s-]", "", str(row["ISRC"] or "").strip().upper())
        row["identity_status"] = "resolved" if native_isrc == key else "contradictory"
        row["artists"] = parse_credit(row["TRACK ARTIST"])
        row["provenance_complete"] = bool(row["account"] and row["statement_file_name"]
            and re.fullmatch(r"[a-fA-F0-9]{64}", str(row["statement_file_hash"] or ""))
            and re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", str(row["statement_period"] or "")))
        by_isrc[key].append(row)
    result = {}
    for isrc, observations in sorted(by_isrc.items()):
        observations.sort(key=lambda row: (row["statement_period"] or "", row["statement_file_hash"] or "",
                                          row["standardized_row"], row["TRACK ARTIST"] or ""))
        usable = [row for row in observations if row["artists"] and row["provenance_complete"]
                  and row["identity_status"] == "resolved"]
        alternatives = {frozenset(map(name_key, row["artists"])) for row in usable}
        identity_ok = all(row["identity_status"] == "resolved" for row in observations)
        status = "contradictory" if not identity_ok or len(alternatives) > 1 else "resolved" if alternatives else "incomplete"
        artists = list(usable[0]["artists"]) if status == "resolved" else []
        firsts = {name_key(row["artists"][0]) for row in usable}
        principal_status = "single_artist" if len(artists) == 1 else "order_only" if artists and len(firsts) == 1 else "unresolved"
        result[isrc] = {"source": "orchard", "field": "TRACK ARTIST", "level": "track", "asset_isrc": isrc,
            "rule": RULE_VERSION, "adapter_version": EVIDENCE_VERSION,
            "identity_status": "resolved" if identity_ok else "contradictory", "native_resolution_status": status,
            "native_artists": artists, "principal_status": principal_status,
            "principal_proposed": usable[0]["artists"][0] if artists and len(firsts) == 1 else None,
            "principal_scope": "interpreted_credit_order_not_contract_rights",
            "incomplete_observations": len(observations) - len(usable),
            "observations": observations}
    return result


def enrich_orchard_catalog(catalog: pl.DataFrame, frame: pl.LazyFrame, *, corrections_path: Path | None = None) -> pl.DataFrame:
    if catalog["catalog_key"].n_unique() != catalog.height:
        raise ValueError("Duplicate catalog keys in Orchard metadata merge")
    metadata = collect_orchard_artists(frame)
    corrections = json.loads((corrections_path or CORRECTIONS_PATH).read_text(encoding="utf-8"))
    manual = {item["catalog_key"] for item in corrections["corrections"]
              if item.get("confirmed_by") and "artist_statement" in item}
    values = {name: [] for name in ARTIST_COLUMNS}
    for row in catalog.to_dicts():
        output = {name: row.get(name) for name in ARTIST_COLUMNS}
        entry = metadata.get(row.get("asset_isrc"))
        if entry is not None:
            entry = dict(entry)
            prior = row.get("catalog_artists")
            protected = row["catalog_key"] in manual or bool(row.get("catalog_manual_correction_confirmed_by") and prior is not None)
            native = entry["native_artists"]
            compatible = entry["native_resolution_status"] == "resolved" and (
                not prior or set(map(name_key, native)) <= set(map(name_key, prior)))
            if compatible and prior:
                artists = list(prior)
            elif compatible and prior is None and not protected:
                artists = list(native)
                output["catalog_artists"] = artists
                output["catalog_artist_statement"] = " / ".join(artists)
            else:
                artists = list(prior or [])
                if prior is None and not protected:
                    output["catalog_artists"] = []
            entry.update(artists=artists, used_for_catalog=bool(compatible and artists), manual_protected=protected)
            old = json.loads(output["catalog_artist_evidence"] or "[]")
            old = [record for record in old if not (record.get("source") == "orchard"
                                                   and record.get("adapter_version") == EVIDENCE_VERSION)]
            output["catalog_artist_evidence"] = json.dumps([*old, entry], ensure_ascii=True, sort_keys=True)
            rules = [value for value in str(output["catalog_artist_rule"] or "").split(" | ") if value]
            output["catalog_artist_rule"] = " | ".join(dict.fromkeys([*rules, RULE_VERSION]))
        for name in ARTIST_COLUMNS:
            values[name].append(output[name])
    return catalog.with_columns([pl.Series(name, values[name], dtype=dtype) for name, dtype in ARTIST_COLUMNS.items()])


def enrich_orchard_catalog_file(catalog: pl.DataFrame, raw_path: Path) -> pl.DataFrame:
    if not raw_path.exists():
        raise FileNotFoundError("Missing standardized Orchard input for artist metadata")
    return enrich_orchard_catalog(catalog, pl.scan_parquet(raw_path))
