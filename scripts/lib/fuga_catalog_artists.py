from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import polars as pl

from .catalog_manual_metadata import CORRECTIONS_PATH
from .catalog_artist_dictionary import canonical
from .catalog_artist_evidence import assert_other_sources_preserved, records, replace_source


RULE_VERSION = "FUGA-ARTISTS-2"
REFERENCES_PATH = Path(__file__).with_name("fuga_catalog_artist_references.json")
ARTIST_COLUMNS = {
    "catalog_artists": pl.List(pl.Utf8),
    "catalog_artist_statement": pl.Utf8,
    "catalog_artist_evidence": pl.Utf8,
    "catalog_artist_rule": pl.Utf8,
}


def name_key(value: str) -> str:
    value = canonical(value)
    return re.sub(r"\s+", " ", value.strip()).casefold()


def split_unquoted(text: str, marker: str, *, insensitive: bool = False) -> list[str]:
    result, start, cursor, quoted = [], 0, 0, False
    while cursor < len(text):
        if text[cursor] == '"':
            quoted = not quoted
            cursor += 1
            continue
        sample = text[cursor:cursor + len(marker)]
        matches = sample.casefold() == marker.casefold() if insensitive else sample == marker
        if matches and not quoted:
            result.append(text[start:cursor])
            cursor += len(marker)
            start = cursor
        else:
            cursor += 1
    if quoted:
        raise ValueError("Unbalanced FUGA artist quotation marks.")
    return result + [text[start:]]


def parse_credit(raw: str) -> tuple[list[str], str]:
    text = raw.strip()
    if not text:
        return [], "empty"
    if ";" in text or "|" in text:
        return [], "ambiguous_serialization"
    try:
        featuring = split_unquoted(text, " featuring ", insensitive=True)
        if len(featuring) > 2:
            return [], "ambiguous_serialization"
        result = []
        for section in featuring:
            sections = split_unquoted(section, " and ")
            if len(sections) > 2:
                return [], "ambiguous_serialization"
            if len(sections) == 2:
                before, last = sections
                if len(split_unquoted(last, ",")) > 1 or not before.strip() or not last.strip():
                    return [], "ambiguous_serialization"
                parts = split_unquoted(before, ", ") + [last]
            elif len(split_unquoted(section, ",")) > 1:
                return [], "ambiguous_serialization"
            else:
                parts = [section]
            if any(not part.strip() or len(split_unquoted(part, ",")) > 1 for part in parts):
                return [], "ambiguous_serialization"
            result.extend(part.strip() for part in parts)
    except ValueError:
        return [], "ambiguous_serialization"
    unique = {}
    for name in result:
        unique.setdefault(name_key(name), name)
    return list(unique.values()), "fuga_comma_and_featuring"


def parse_catalog_credit(text: str) -> list[str]:
    if "(performer)" in text.casefold() or "(featuring)" in text.casefold():
        return re.findall(r"(?:^|,)\s*([^,]+?)\s*\(\s*(?:performer|featuring)\s*\)", text, re.I)
    parts = [text]
    try:
        for marker in (",", " and ", " & ", " featuring ", " feat. ", " feat "):
            parts = [part for value in parts for part in split_unquoted(value, marker, insensitive=True)]
    except ValueError:
        return [text] if text.strip() else []
    return [part.strip() for part in parts if part.strip()]


def collect_fuga_artists(frame: pl.LazyFrame) -> dict[str, dict[str, Any]]:
    from .catalog_identity_corrections import correct_recording_identity
    frame = correct_recording_identity(frame)
    schema = set(frame.collect_schema().names())
    required = {"source", "asset_isrc", "Asset Artist", "Product Artist", "Product Reference", "Asset Reference"}
    if not required <= schema:
        raise ValueError(f"Missing FUGA artist evidence fields: {', '.join(sorted(required - schema))}")
    context = [name for name in (
        "account", "statement_period", "statement_file_name", "statement_file_hash", "Product UPC",
    ) if name in schema]
    columns = ["asset_isrc", "Asset Artist", "Product Artist", "Product Reference", "Asset Reference", *context]
    rows = (
        frame.filter(
            (pl.col("source") == "fuga")
            & pl.col("asset_isrc").cast(pl.Utf8).fill_null("").str.contains(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")
            & pl.col("Product Reference").cast(pl.Utf8).fill_null("").str.contains(r"^[0-9]+$")
            & ~pl.col("Asset Reference").cast(pl.Utf8).fill_null("").str.starts_with("YT-A")
        )
        .select([pl.col(name).cast(pl.Utf8, strict=False) for name in columns])
        .unique()
        .sort(list(dict.fromkeys(name for name in ("asset_isrc", "statement_period", "statement_file_name", *columns[1:]) if name in columns)))
        .collect(engine="streaming").to_dicts()
    )
    result: dict[str, dict[str, Any]] = {}
    # Only track credits define participants; album credits remain evidence.
    for field in ("Asset Artist", "Product Artist"):
        for row in rows:
            raw = str(row.get(field) or "")
            artists, status = parse_credit(raw)
            entity = result.setdefault(row["asset_isrc"], {"artists": {}, "evidence": []})
            if field == "Asset Artist":
                for artist in artists:
                    entity["artists"].setdefault(name_key(artist), artist)
            entity["evidence"].append({
                "source": "fuga", "field": field, "raw": raw, "artists": artists,
                "status": status, "used_for_catalog": field == "Asset Artist", **{name: row.get(name) for name in context},
                "Product Reference": row["Product Reference"], "Asset Reference": row["Asset Reference"],
            })
    return result


def enrich_fuga_catalog(
    catalog: pl.DataFrame, frame: pl.LazyFrame, *, corrections_path: Path | None = None,
) -> pl.DataFrame:
    evidence = collect_fuga_artists(frame)
    corrections = json.loads((corrections_path or CORRECTIONS_PATH).read_text(encoding="utf-8"))
    artist_corrections = {
        item["catalog_key"]: item for item in corrections["corrections"]
        if "artist_statement" in item and item.get("confirmed_by")
    }
    references = json.loads(REFERENCES_PATH.read_text(encoding="utf-8"))
    if references.get("version") != 1:
        raise ValueError("Unsupported FUGA artist reference version.")
    aliases = {}
    for item in references["references"]:
        if not item.get("confirmed_by") or not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}", item["isrc"]):
            raise ValueError("A FUGA artist reference requires an ISRC and human confirmation.")
        key = (item["isrc"], name_key(item["original_name"]))
        if key in aliases:
            raise ValueError("Duplicate scoped FUGA artist reference.")
        aliases[key] = item["confirmed_name"]
    values: dict[str, list] = {name: [] for name in ARTIST_COLUMNS}
    for row in catalog.to_dicts():
        entity = evidence.get(row.get("asset_isrc"))
        if not entity:
            for name, entries in values.items():
                entries.append(row.get(name))
            continue
        resolved = {}
        for name in entity["artists"].values():
            name = aliases.get((row["asset_isrc"], name_key(name)), name)
            resolved.setdefault(name_key(name), name)
        artists = list(resolved.values())
        # A source-specific list must not erase names already shared by another distributor.
        original = str(row.get("artist_statement") or "")
        other_track_artists = {name_key(name) for entry in records(row.get("catalog_artist_evidence"))
                               if entry.get("source") != "fuga" and entry.get("used_for_catalog")
                               for name in entry.get("artists") or []}
        album_only = ({name_key(name) for entry in entity["evidence"] if entry["field"] == "Product Artist" for name in entry["artists"]}
                      - set(entity["artists"]) - other_track_artists)
        previous = [aliases.get((row["asset_isrc"], name_key(name)), name) for name in [*parse_catalog_credit(original), *(row.get("catalog_artists") or [])]
                    if name_key(name) not in album_only]
        correction = artist_corrections.get(row.get("catalog_key"))
        if correction and row.get("catalog_manual_correction_id") == correction["id"]:
            artists = [aliases.get((row["asset_isrc"], name_key(name)), name) for name in parse_catalog_credit(original)]
        else:
            seen = {name_key(name) for name in artists}
            for name in previous:
                if name_key(name) not in seen:
                    artists.append(name)
                    seen.add(name_key(name))
        values["catalog_artists"].append(artists)
        values["catalog_artist_statement"].append(" / ".join(artists) or original or None)
        values["catalog_artist_evidence"].append(replace_source(row.get("catalog_artist_evidence"), "fuga", entity["evidence"]))
        rules = [rule for rule in str(row.get("catalog_artist_rule") or "").split(" | ")
                 if rule and not rule.startswith("FUGA-ARTISTS-")]
        values["catalog_artist_rule"].append(" | ".join(dict.fromkeys([RULE_VERSION, *rules])))
    result = catalog.with_columns([pl.Series(name, values[name], dtype=dtype) for name, dtype in ARTIST_COLUMNS.items()])
    assert_other_sources_preserved(catalog, result, "fuga")
    return result


def enrich_fuga_catalog_file(catalog: pl.DataFrame, raw_path: Path) -> pl.DataFrame:
    if not raw_path.exists():
        raise FileNotFoundError(f"FUGA artist evidence is unavailable: {raw_path}")
    return enrich_fuga_catalog(catalog, pl.scan_parquet(raw_path))


def catalog_artist_display(catalog: pl.DataFrame) -> pl.DataFrame:
    if "catalog_artist_statement" not in catalog.columns:
        return catalog
    return catalog.with_columns(
        pl.coalesce([pl.col("catalog_artist_statement"), pl.col("artist_statement")]).alias("artist_statement")
    )
