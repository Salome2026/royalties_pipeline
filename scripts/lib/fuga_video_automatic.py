"""Resolve future Extended identities from audited native identifiers, without user queues.

Titles alone cannot prove the same recording. A native Sale ID bridge is evidence;
conflicting bridges remain closed without linking and are reconsidered next run.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import polars as pl

from .catalog_video_metadata import apply_catalog_video_metadata, load_decisions, values
from .fuga_extended import METADATA_FILE, _atomic_parquet
from .fuga_recording_lookup import RecordingLookup, normalized, artist_names, recording_title


def resolve_extended(catalog: pl.DataFrame, metadata: pl.DataFrame, decisions: dict, lookup=None) -> tuple[pl.DataFrame, list[dict]]:
    decisions = {**decisions, "entries": list(decisions["entries"])}
    known = {entry["video_isrc"] for entry in decisions["entries"]}
    rows = {row["catalog_key"]: row for row in catalog.to_dicts()}
    outcomes = []
    required = {"YouTube Asset ISRC", "YouTube Video ID", "principal_asset_isrc", "source_file", "economic_role"}
    if required <= set(metadata.columns):
        groups: dict[str, list[dict]] = {}
        extra = {"YouTube Asset Title", "YouTube Asset Artists"} & set(metadata.columns)
        for row in metadata.select(sorted(required | extra)).unique().to_dicts():
            code = (row["YouTube Asset ISRC"] or "").strip().upper()
            if row["economic_role"] == "supplementary_metadata_only" and re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}", code):
                groups.setdefault(code, []).append(row)
        for code, evidence in sorted(groups.items()):
            if code in known:
                continue
            videos = sorted({(r["YouTube Video ID"] or "").strip() for r in evidence} - {""})
            native_codes = {(r["principal_asset_isrc"] or "").strip().upper() for r in evidence} - {""}
            principals = sorted(native_codes - {code})
            # Never treat an audio ISRC repeated verbatim as a second video identity.
            if not principals and "ISRC:" + code in rows:
                continue
            targets = [key for key, row in rows.items() if values(row.get("video_ids")) & set(videos)]
            audio = principals[0] if len(principals) == 1 and "ISRC:" + principals[0] in rows else None
            confirmed = bool(audio and code not in native_codes and videos and len(targets) <= 1)
            recording_evidence = {"native_audio_isrcs": principals, "basis": "audited_native_sale_id", "audio_fingerprint_comparison_performed": False}
            if not audio and not principals and videos and len(targets) == 1 and lookup:
                artist_sets = [{normalized(name) for name in artist_names(r.get("YouTube Asset Artists"))} for r in evidence]
                titles = {recording_title(r.get("YouTube Asset Title"), artist_names(r.get("YouTube Asset Artists"))) for r in evidence} - {""}
                candidates = [row for candidate_key, row in rows.items() if candidate_key.startswith("ISRC:") and normalized(row.get("track_title")) in titles and {normalized(name) for name in artist_names(row.get("artist_statement"))} in artist_sets and artist_names(row.get("artist_statement"))]
                if len(candidates) == 1:
                    candidate = candidates[0]
                    verified = lookup.verify(candidate["catalog_key"][5:], candidate["track_title"], artist_names(candidate["artist_statement"]), videos)
                    if verified:
                        audio = candidate["catalog_key"][5:]
                        confirmed = True
                        recording_evidence = verified
            key = targets[0] if len(targets) == 1 else ("ISRC:" + audio if confirmed else None)
            # An ISRC-keyed record cannot be relabelled as another audio master.
            if confirmed and key.startswith("ISRC:") and key != "ISRC:" + audio:
                confirmed = False
            reason = (("Vinculo exacto por Sale ID del Extended y del statement tradicional auditado." if recording_evidence["basis"] == "audited_native_sale_id" else "Lanzamiento y video coinciden en ISRC de audio, titulo, artista, fecha y duracion.")
                      if confirmed else "Sin vinculo: identificadores nativos ambiguos o sin audio unico existente; los titulos no prueban la misma grabacion.")
            entry = {"video_isrc": code, "catalog_key": key, "video_ids": videos,
                     "source_file": " | ".join(sorted({r["source_file"] for r in evidence})),
                     "audio_relationship_status": "confirmed" if confirmed else "not_linked",
                     "confirmed_audio_isrc": audio if confirmed else None,
                     "review_closed": True, "requires_user_confirmation": False,
                     "notes": reason, "automatic_policy_version": 1,
                     "recording_evidence": recording_evidence}
            outcomes.append(entry)
            if key and videos:
                if confirmed:
                    rows[key]["video_ids"] = " | ".join(sorted(values(rows[key].get("video_ids")) | set(videos)))
                decisions["entries"].append(entry)
    enriched = pl.DataFrame(list(rows.values()), schema=catalog.schema)
    return apply_catalog_video_metadata(enriched, decisions=decisions), outcomes


def apply_automatic_extended(catalog: pl.DataFrame, root: Path) -> pl.DataFrame:
    metadata_path = root / "warehouse/marts" / METADATA_FILE
    seed = load_decisions(root / "warehouse/registry/fuga_video_catalog_decisions.json")
    metadata = pl.read_parquet(metadata_path) if metadata_path.exists() else pl.DataFrame()
    from build_catalog_release_metadata import load_env_file
    load_env_file(root / ".env")
    lookup = RecordingLookup()
    if "automatic_resolution_json" in metadata.columns:
        for serialized in metadata["automatic_resolution_json"].drop_nulls().unique().to_list():
            for entry in json.loads(serialized):
                evidence = entry.get("recording_evidence", {})
                if entry.get("confirmed_audio_isrc") and evidence.get("basis") == "exact_isrc_release_and_official_video_metadata":
                    lookup.cache[(entry["confirmed_audio_isrc"], tuple(entry["video_ids"]))] = evidence
    result, outcomes = resolve_extended(catalog, metadata, seed, lookup=lookup)
    if metadata_path.exists():
        # This existing supplementary artifact travels with normal publication.
        mapping = {entry["video_isrc"]: json.dumps([entry], ensure_ascii=False, sort_keys=True) for entry in outcomes}
        if "YouTube Asset ISRC" in metadata.columns:
            metadata = metadata.with_columns(pl.col("YouTube Asset ISRC").str.strip_chars().str.to_uppercase().replace_strict(mapping, default="[]").alias("automatic_resolution_json"))
        _atomic_parquet(metadata, metadata_path)
    print(f"Extended: {len(outcomes)} decisiones automaticas nuevas; 0 confirmaciones de usuario.")
    return result
