"""ADA participant metadata; no monetary changes or inferred contractual rights."""

from __future__ import annotations

import itertools
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import polars as pl

from .catalog_manual_metadata import CORRECTIONS_PATH

RULE_VERSION = "ADA-LECTURA-1"
EVIDENCE_VERSION = "ADA-CAT003-adapter-1"
METADATA_FILE = "catalog_ada_artists.parquet"
ARTIST_COLUMNS = {"catalog_artists": pl.List(pl.String), "catalog_artist_statement": pl.String,
                  "catalog_artist_rule": pl.String, "catalog_artist_evidence": pl.String}

def name_key(value: str) -> str:
    s = unicodedata.normalize("NFKD", value)
    return re.sub(r"\s+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip().casefold()

def parse_credit(value: str, atomic_names: tuple[str, ...] = ()) -> tuple[list[str], str]:
    value = str(value or "").strip()
    if not value:
        return [], "incomplete"
    protected = {}
    for i, atomic in enumerate(sorted(atomic_names, key=len, reverse=True)):
        token = f"\x00{i}\x00"
        if atomic in value:
            value = value.replace(atomic, token)
            protected[token] = atomic
    unsupported = bool(re.search(r"\s+(?:and|featuring|feat\.?)\s+", value, re.I))
    parts = [value] if unsupported else re.split(r"\s*,\s*|\s+&\s+", value)
    out, seen = [], set()
    for part in parts:
        for token, atomic in protected.items():
            part = part.replace(token, atomic)
        part = re.sub(r"\s+", " ", part).strip()
        if part and name_key(part) not in seen:
            out.append(part)
            seen.add(name_key(part))
    return out, "ambiguous_grammar" if unsupported else "resolved"

def evidence_sort(r: dict) -> tuple:
    return (-int(str(r.get("statement_period", "0000-00")).replace("-", "")),
            r.get("source", "ada"), r.get("account", ""), r.get("statement_file_hash", ""),
            r.get("native_source_sheet", ""), int(r.get("source_row", 0)))

def complete_prefixes(observations: list[dict]) -> list[dict]:
    by_isrc = defaultdict(dict)
    for r in sorted(observations, key=evidence_sort):
        raw = str(r.get("Artist Name") or "").strip()
        if r.get("asset_isrc") and raw:
            by_isrc[r["asset_isrc"]].setdefault(raw.casefold(), r)
    out = []
    for r in observations:
        raw = str(r.get("Artist Name") or "").strip()
        matches = [v for k, v in by_isrc[r.get("asset_isrc")].items()
                   if len(raw) == 30 and len(str(v["Artist Name"])) > 30 and k.startswith(raw.casefold())]
        row = dict(r)
        row["artist_catalog_style"] = str(matches[0]["Artist Name"]) if len(matches) == 1 else raw
        row["artist_credit_status"] = ("confirmed_prefix" if len(matches) == 1 else "conflicting_prefix"
                                       if len(matches) > 1 else "possible_truncation" if len(raw) == 30 else "as_reported")
        row["prefix_evidence"] = ({k: matches[0].get(k) for k in ["account", "statement_file_name", "statement_file_hash", "source_row"]}
                                  if len(matches) == 1 else None)
        row["artists"], row["grammar_status"] = parse_credit(row["artist_catalog_style"])
        out.append(row)
    return out

def resolve_participants(observations: list[dict], prior: list[str] | None = None, identity_conflict: bool = False) -> dict:
    ordered = sorted(observations, key=evidence_sort)
    usable = [r for r in ordered if r.get("artists") and r.get("grammar_status", "resolved") == "resolved"]
    sets = [frozenset(map(name_key, r["artists"])) for r in usable]
    conflict = identity_conflict or any(not (a <= b or b <= a) for a, b in itertools.combinations(sets, 2))
    if conflict:
        return {"artists": prior or [], "status": "contradictory", "principal": None,
                "principal_status": "uncertain", "alternatives": [r["artists"] for r in usable]}
    if not sets:
        return {"artists": prior or [], "status": "incomplete", "principal": None,
                "principal_status": "unknown", "alternatives": []}
    maximum = max(sets, key=len)
    complete = [r for r in usable if frozenset(map(name_key, r["artists"])) == maximum]
    chosen = complete[0]["artists"]
    names = list(chosen)
    if prior:
        mapping = {name_key(v): v for v in prior}
        names = [mapping.get(name_key(v), v) for v in chosen]
    firsts = {name_key(r["artists"][0]) for r in complete}
    return {"artists": names, "status": "resolved", "principal": names[0] if len(firsts) == 1 else None,
            "principal_status": "order_only" if len(firsts) == 1 else "uncertain", "alternatives": []}


def metadata_observations(native: pl.DataFrame) -> pl.DataFrame:
    columns = ["asset_isrc", "native_entity_key", "Artist Name", "Catalogue Title", "Project Title", "source", "account",
               "statement_period", "statement_file_name", "statement_file_hash", "source_row", "native_source_sheet"]
    return native.select(columns).sort("source_row").unique(
        subset=[c for c in columns if c != "source_row"], maintain_order=True)


def evidence_entry(observations: list[dict], resolution: dict) -> dict:
    if not any(row.get("source") == "ada" for row in observations):
        raise ValueError("Falta evidencia ADA nativa")
    return {"source": "ada", "field": "Artist Name", "adapter_version": EVIDENCE_VERSION,
        "used_for_catalog": resolution["status"] == "resolved", "artists": resolution["artists"],
        "native_resolution_status": resolution["status"], "principal_status": resolution["principal_status"],
        "principal_proposed": resolution["principal"], "principal_scope": "interpreted_credit_order_not_contract_rights",
        "identity_status": "contradictory" if resolution["status"] == "contradictory" else "resolved",
        "alternatives": resolution.get("alternatives", []),
        "observations": sorted(observations, key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=True))}


def enrich_ada_catalog(catalog: pl.DataFrame, native_metadata: pl.DataFrame, *, orchard_metadata: pl.DataFrame | None = None,
                       atomic_names: tuple[str, ...] = (), corrections_path: Path | None = None) -> pl.DataFrame:
    if catalog["catalog_key"].n_unique() != catalog.height:
        raise ValueError("Claves duplicadas en catalogo ADA")
    observations = complete_prefixes(native_metadata.to_dicts())
    by_key = defaultdict(list)
    for row in observations:
        row["artists"], row["grammar_status"] = parse_credit(row["artist_catalog_style"], atomic_names)
        by_key[row["native_entity_key"]].append(row)
    if orchard_metadata is not None:
        for row in orchard_metadata.to_dicts():
            key = "ISRC:" + str(row.get("asset_isrc") or "")
            if key not in by_key:
                continue
            artists = [v.strip() for v in (row.get("TRACK ARTIST") or "").split("|") if v.strip()]
            by_key[key].append({**row, "artists": artists, "grammar_status": "resolved",
                               "native_source_sheet": "Orchard existing TRACK ARTIST", "source_row": 0})
    corrections = json.loads((corrections_path or CORRECTIONS_PATH).read_text(encoding="utf-8"))
    manual = {r["catalog_key"]: r["id"] for r in corrections["corrections"] if "artist_statement" in r and r.get("confirmed_by")}
    values = {field: [] for field in ARTIST_COLUMNS}
    for row in catalog.to_dicts():
        output = {field: row.get(field) for field in ARTIST_COLUMNS}
        key, prior = row["catalog_key"], row.get("catalog_artists")
        if key in by_key:
            comparisons = list(by_key[key])
            if prior:
                comparisons.append({"source": "catalog", "account": "", "statement_period": "0000-00",
                                    "artists": prior, "grammar_status": "resolved", "source_row": 0})
            resolved = resolve_participants(comparisons, prior=prior)
            if (manual.get(key) and row.get("catalog_manual_correction_id") == manual[key]
                    and not set(map(name_key, resolved["artists"])) <= set(map(name_key, prior or []))):
                resolved = resolve_participants(comparisons, prior=prior, identity_conflict=True)
            if resolved["status"] == "resolved":
                output["catalog_artists"] = resolved["artists"]
                output["catalog_artist_statement"] = " / ".join(resolved["artists"])
                rules = [v for v in str(output["catalog_artist_rule"] or "").split(" | ") if v]
                output["catalog_artist_rule"] = " | ".join(dict.fromkeys([*rules, RULE_VERSION]))
            elif prior is None:
                # An explicit unresolved list prevents the legacy raw parser from
                # silently reinterpreting grammar the ADA reader did not certify.
                output["catalog_artists"] = []
            evidence = json.loads(output["catalog_artist_evidence"] or "[]")
            evidence = [v for v in evidence if not (v.get("source") == "ada" and v.get("adapter_version") == EVIDENCE_VERSION)]
            evidence.append(evidence_entry(by_key[key], resolved))
            output["catalog_artist_evidence"] = json.dumps(evidence, ensure_ascii=True, sort_keys=True)
        for field in values:
            values[field].append(output[field])
    return catalog.with_columns([pl.Series(field, values[field], dtype=dtype) for field, dtype in ARTIST_COLUMNS.items()])


def orchard_credit_evidence(path: Path, isrcs: list[str]) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    frame = pl.scan_parquet(path)
    names = set(frame.collect_schema().names())
    if not {"source", "asset_isrc", "TRACK ARTIST"} <= names:
        raise ValueError("Metadata Orchard sin campos nativos certificados")
    columns = [c for c in ["source", "account", "asset_isrc", "statement_period", "statement_file_hash", "statement_file_name", "TRACK ARTIST", "TRACK"] if c in names]
    return frame.filter((pl.col("source") == "orchard") & pl.col("asset_isrc").is_in(isrcs)).select(columns).unique().collect()


def enrich_ada_catalog_file(catalog: pl.DataFrame, metadata_path: Path, orchard_path: Path) -> pl.DataFrame:
    if not metadata_path.exists():
        raise FileNotFoundError("Falta metadata ADA: ejecutar su ingesta antes de reconstruir el catalogo")
    native = pl.read_parquet(metadata_path)
    isrcs = native["asset_isrc"].drop_nulls().unique().to_list()
    other = orchard_credit_evidence(orchard_path, isrcs)
    return enrich_ada_catalog(catalog, native, orchard_metadata=other)
