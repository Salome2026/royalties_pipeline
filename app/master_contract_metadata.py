"""Derived video associations for Contracts, never raw/catalog identity rewrites."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import re
import unicodedata

from app.master_contracts import parse_artists

RULE_VERSION = "video-title-performers-v1"
DISPLAY_MARKERS = {
    "video oficial", "official video", "official music video", "audio oficial",
    "official audio", "lyric video", "video clip oficial", "videoclip oficial",
}
VERSION_MARKERS = re.compile(
    r"\b(remix|live|en vivo|acoustic|acustic[oa]|sped up|slowed|instrumental|"
    r"karaoke|session|sesion|set game|set session)\b"
)


def normalized(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def performer_set(value: str | None) -> frozenset[str]:
    return frozenset(normalized(part).replace(" ", "") for part in
                     parse_artists(str(value or "").replace(" | ", ","), "catalog")
                     if normalized(part))


def strip_display_marker(value: str) -> str:
    value = value.strip()
    while match := re.search(r"\s*[\(\[]([^\)\]]+)[\)\]]\s*$", value):
        if normalized(match[1]) not in DISPLAY_MARKERS:
            break
        value = value[:match.start()].rstrip()
    return value


def complete_performers(block: str, performers: frozenset[str]) -> bool:
    remaining, seen = normalized(block).replace(" ", ""), set()
    while remaining:
        available = sorted((name for name in performers - seen if remaining.startswith(name)),
                           key=len, reverse=True)
        if available:
            name = available[0]
            seen.add(name)
            remaining = remaining[len(name):]
            continue
        connector = next((word for word in ("featuring", "feat", "ft", "and", "con", "x", "y")
                          if seen and remaining.startswith(word)
                          and any(remaining[len(word):].startswith(name) for name in performers - seen)), None)
        if not connector:
            return False
        remaining = remaining[len(connector):]
    return bool(performers) and seen == set(performers)


def infer_video_evidence(catalog: list[dict], evidence: list[dict]) -> list[dict]:
    """Compare full credits; alternate credits can veto uniqueness, not prove it."""
    by_title: dict[str, list[dict]] = defaultdict(list)
    for row in catalog:
        isrc = str(row.get("asset_isrc") or "")
        if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}", isrc):
            continue
        primary = performer_set(row.get("artist_statement"))
        variants = {performer_set(value) for value in str(row.get("artist_variants") or "").split(" | ") if value}
        credit_conflict = any(names - primary for names in variants)
        item = {"isrc": isrc, "primary": primary, "variants": variants | {primary},
                "credit_conflict": credit_conflict, "title": normalized(row.get("track_title"))}
        for title in {row.get("track_title"), *str(row.get("title_variants") or "").split(" | ")}:
            if normalized(title):
                by_title[normalized(title)].append(item)

    videos: dict[str, list[dict]] = defaultdict(list)
    for row in evidence:
        if row["kind"] == "VIDEO" and re.fullmatch(r"[A-Za-z0-9_-]{11}", row["code"]):
            videos[row["code"]].append(row)
    inferred: dict[str, dict] = {}
    for code, items in videos.items():
        matches, strict, identities = set(), set(), set()
        credit_conflict, version_warning, unmatched_title = False, False, False
        for item in items:
            artists = item.get("artists") or []
            for title in item.get("titles") or []:
                found = False
                parts = re.split(r"\s+[-\u2013\u2014|]\s+", strip_display_marker(title))
                pairs = []
                for position in range(1, len(parts)):
                    left, right = " - ".join(parts[:position]), " - ".join(parts[position:])
                    pairs.extend([(left, right), (right, left)])
                # A ONErpm channel name is not a complete performer credit.
                if item["source"] != "onerpm":
                    pairs.extend((strip_display_marker(title), artist) for artist in artists
                                 if normalized(artist) != normalized(title))
                for track, block in pairs:
                    for candidate in by_title.get(normalized(track), []):
                        if not any(complete_performers(block, names) for names in candidate["variants"]):
                            continue
                        found = True
                        matches.add(candidate["isrc"])
                        identities.add((candidate["isrc"], candidate["title"], tuple(sorted(candidate["primary"]))))
                        credit_conflict |= candidate["credit_conflict"]
                        if complete_performers(block, candidate["primary"]):
                            strict.add(candidate["isrc"])
                        reported_versions = {match[0] for value in [track, *artists]
                                             for match in VERSION_MARKERS.finditer(normalized(value))}
                        audio_versions = {match[0] for match in VERSION_MARKERS.finditer(candidate["title"])}
                        version_warning |= reported_versions != audio_versions
                unmatched_title |= not found
        if not matches:
            continue
        status = "strong"
        note = "Coinciden tema y todos los participantes con un unico ISRC."
        if len(matches) != 1:
            status, note = "ambiguous", "Tema y participantes coinciden con varios ISRC; requiere elegir el asset correcto."
        elif version_warning:
            status, note = "version", "La referencia indica una version o sesion; requiere validar que corresponde a este contrato."
        elif strict != matches or credit_conflict or unmatched_title:
            status, note = "incomplete", "Hay creditos o titulos incompletos/diferentes entre las referencias; requiere validacion."
        fingerprint = hashlib.sha256(json.dumps(
            [RULE_VERSION, status, sorted(identities)], separators=(",", ":"),
        ).encode()).hexdigest()
        inferred[code] = {"inferred_isrcs": sorted(matches), "inference_status": status,
                          "inference_reason": note, "inference_signature": fingerprint,
                          "inference_rule": RULE_VERSION}
    derived_fields = {"inferred_isrcs", "inference_status", "inference_reason", "inference_signature", "inference_rule"}
    return [{**{key: value for key, value in row.items() if key not in derived_fields},
             **(inferred.get(row["code"], {}) if row["kind"] == "VIDEO" else {})} for row in evidence]
