"""Reviewed video identifiers enrich existing catalog entries, never financial rows."""
from __future__ import annotations

import json
from pathlib import Path
import re

import polars as pl

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "warehouse/registry/fuga_video_catalog_decisions.json"
VIDEO_FIELDS = {"video_isrcs": pl.List(pl.String), "catalog_aliases": pl.List(pl.String),
                "video_relationships_json": pl.String}
ECONOMIC_FIELDS = ["amount_usd", "observed_amount_usd", "transfer_amount_usd",
                   "policy_unmatched_amount_usd", "units", "song_level_rows"]


def values(value: str | None) -> set[str]:
    return {item.strip() for item in (value or "").split(" | ") if item.strip()}


def load_decisions(path: Path = REGISTRY_PATH) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("version") != 1:
        raise ValueError("Version de decisiones de video no soportada.")
    entries = document["entries"]
    codes = [entry["video_isrc"] for entry in entries]
    if len(codes) != len(set(codes)):
        raise ValueError("ISRC de video repetido en decisiones.")
    aliases = document["aliases"]
    sources = [entry["alias_catalog_key"] for entry in aliases]
    if len(sources) != len(set(sources)) or any(entry["catalog_key"] in sources for entry in aliases):
        raise ValueError("Alias de catalogo ambiguo o encadenado.")
    for entry in entries:
        if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}", entry["video_isrc"]):
            raise ValueError("ISRC de video invalido.")
        if entry["audio_relationship_status"] not in {"confirmed", "pending_confirmation", "video_only"}:
            raise ValueError("Estado de relacion de video invalido.")
        if entry["audio_relationship_status"] == "confirmed":
            if entry["catalog_key"] != "ISRC:" + entry["confirmed_audio_isrc"]:
                raise ValueError("La relacion confirmada no coincide con la ficha de audio.")
        elif entry.get("confirmed_audio_isrc"):
            raise ValueError("Una propuesta no puede figurar como relacion confirmada.")
        if not entry.get("video_ids") or not entry.get("source_file"):
            raise ValueError("Falta evidencia de la relacion de video.")
    return document


def apply_catalog_video_metadata(catalog: pl.DataFrame, *, decisions: dict | None = None,
                                 registry_path: Path = REGISTRY_PATH) -> pl.DataFrame:
    decisions = decisions if decisions is not None else load_decisions(registry_path)
    rows = {row["catalog_key"]: row for row in catalog.to_dicts()}
    if len(rows) != catalog.height:
        raise ValueError("Catalogo con claves duplicadas.")
    # Retain old aliases as redirects, and preserve provenance without adding their evidence to income.
    for alias in decisions["aliases"]:
        old_key, key = alias["alias_catalog_key"], alias["catalog_key"]
        if key not in rows:
            raise ValueError(f"No existe destino de alias: {key}")
        target = rows[key]
        target["catalog_aliases"] = sorted(set(target.get("catalog_aliases") or []) | {old_key})
        if old_key not in rows:
            continue  # Reapplying the same reviewed revision is idempotent.
        old = rows[old_key]
        if any(float(old.get(field) or 0) != 0 for field in ECONOMIC_FIELDS):
            raise ValueError(f"El alias {old_key} tiene filas o valores economicos propios; requiere revision.")
        for field in ["isrcs", "upcs", "video_ids", "channel_ids", "track_ids", "sources", "accounts",
                      "identity_sources", "identity_accounts", "identity_source_sheets",
                      "identity_title_variants", "identity_artist_variants", "title_variants", "artist_variants"]:
            if field not in catalog.columns:
                continue
            merged = values(target.get(field)) | values(old.get(field))
            if field == "title_variants": merged |= values(old.get("track_title"))
            if field == "artist_variants": merged |= values(old.get("artist_statement"))
            target[field] = " | ".join(sorted(merged))
        for field in ["identity_amount_usd", "identity_rows"]:
            if field in catalog.columns:
                target[field] = (target.get(field) or 0) + (old.get(field) or 0)
        for field in ["identity_first_transaction_month", "identity_last_transaction_month"]:
            if field in catalog.columns:
                dates = [value for value in [target.get(field), old.get(field)] if value]
                target[field] = (min(dates) if "first" in field else max(dates)) if dates else None
        del rows[old_key]

    grouped: dict[str, list[dict]] = {}
    for entry in decisions["entries"]:
        key = entry["catalog_key"]
        if key not in rows:
            raise ValueError(f"No existe ficha para incorporar {entry['video_isrc']}: {key}")
        if not (values(rows[key].get("video_ids")) & set(entry["video_ids"])):
            raise ValueError(f"La ficha {key} ya no coincide con el video revisado.")
        grouped.setdefault(key, []).append(entry)
    for key, row in rows.items():
        relations = sorted(grouped.get(key, []), key=lambda item: item["video_isrc"])
        row["video_isrcs"] = sorted(entry["video_isrc"] for entry in relations)
        row["catalog_aliases"] = row.get("catalog_aliases") or []
        row["video_relationships_json"] = json.dumps(relations, ensure_ascii=False, sort_keys=True)
    schema = {**catalog.schema, **VIDEO_FIELDS}
    return pl.DataFrame(list(rows.values()), schema=schema)


def video_search_expr(schema: set[str], needle: str) -> pl.Expr:
    """Only identifier/title/credit fields, never pending candidate names or ISRCs."""
    expressions = [pl.col(field).list.join(" ").str.to_lowercase().str.contains(needle, literal=True)
                   for field in ["video_isrcs", "catalog_aliases"] if field in schema]
    return pl.any_horizontal(expressions).fill_null(False) if expressions else pl.lit(False)
