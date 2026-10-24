"""Spotify observations and explicit, versioned display-metadata decisions (Postgres only)."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import requests
from fastapi import HTTPException

from app.operational_db import operational_connect

FIELDS = {"track_title", "artists", "duration_seconds", "release_date", "label"}
CORRECTIONS = Path(__file__).resolve().parents[1] / "scripts/lib/catalog_manual_metadata.json"


def norm(value):
    return re.sub(r"\s+", " ", "".join(c for c in unicodedata.normalize("NFKD", str(value)) if not unicodedata.combining(c))).strip().casefold()


def document(value):
    return json.loads(value) if isinstance(value, str) else value


def protection(row):
    result = {}
    mapping = {"track_title": "track_title", "artist_statement": "artists", "catalog_duration_seconds": "duration_seconds"}
    for correction in json.loads(CORRECTIONS.read_text(encoding="utf-8"))["corrections"]:
        if correction["catalog_key"] == row["catalog_key"] and correction.get("confirmed_by"):
            for source, target in mapping.items():
                if source in correction:
                    result[target] = {"value": correction[source], "by": correction["confirmed_by"], "date": correction.get("confirmed_on"), "reason": correction.get("reason")}
    references = json.loads(CORRECTIONS.with_name("fuga_catalog_artist_references.json").read_text(encoding="utf-8"))["references"]
    for reference in references:
        if reference["isrc"] == row.get("asset_isrc") and reference.get("confirmed_by"):
            result.setdefault("artists", {"by": reference["confirmed_by"], "date": reference.get("confirmed_on"), "reason": "Nombre de artista confirmado manualmente"})
    # A newer published manual correction is protected even before this image knows its source.
    if row.get("catalog_manual_correction_id") and not result:
        result = {key: {"by": row.get("catalog_manual_correction_confirmed_by"), "date": row.get("catalog_manual_correction_confirmed_on")} for key in ("track_title", "artists", "duration_seconds")}
    if row.get("label_normalized_override"):
        result["label"] = {"value": row["label_normalized_override"], "by": "Corrección del catálogo"}
    return result


def observation_from_cache(record, isrc):
    raw = document(record.get("raw_json") or "{}")
    selected = raw.get("selected") or {}
    exact = bool(isrc) and (selected.get("external_ids") or {}).get("isrc", "").upper() == isrc.upper()
    album = raw.get("selected_album") or selected.get("album") or {}
    return {"provider": "spotify", "status": record.get("metadata_status") or "not_consulted", "exact_isrc": exact,
            "track_title": selected.get("name") or record.get("match_title"),
            "artists": [x["name"] for x in selected.get("artists") or []],
            "album": album.get("name"), "album_artists": [x["name"] for x in album.get("artists") or []],
            "duration_seconds": round(selected["duration_ms"] / 1000) if selected.get("duration_ms") is not None else None,
            "release_date": album.get("release_date") or record.get("release_date"),
            "release_date_precision": album.get("release_date_precision") or record.get("release_date_precision"),
            "label": album.get("label") or record.get("external_label"),
            "url": (selected.get("external_urls") or {}).get("spotify") or record.get("match_url"),
            "looked_up_at": record.get("looked_up_at"), "match_method": record.get("metadata_match_method")}


def store_observation(key, payload, actor, origin, fetched_at=None, import_only=False):
    now = datetime.now(timezone.utc)
    with operational_connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("spotify:" + key,))
        previous = conn.execute("SELECT version FROM catalog_metadata_observations WHERE catalog_key=%s", (key,)).fetchone()
        if import_only and previous:
            return
        version = int(previous["version"]) + 1 if previous else 1
        conn.execute("""INSERT INTO catalog_metadata_observations(catalog_key,payload_json,version,fetched_at,origin,updated_by)
          VALUES (%s,%s::jsonb,%s,%s,%s,%s) ON CONFLICT(catalog_key) DO UPDATE SET
          payload_json=EXCLUDED.payload_json,version=EXCLUDED.version,fetched_at=EXCLUDED.fetched_at,origin=EXCLUDED.origin,updated_by=EXCLUDED.updated_by""",
                     (key, json.dumps(payload), version, fetched_at or now, origin, actor))


def current_values(row):
    artists = row.get("catalog_artists") or re.split(r"\s*/\s*|\s+and\s+", row.get("artist_statement") or "")
    return {"track_title": row.get("track_title"), "artists": artists,
            "duration_seconds": row.get("catalog_duration_seconds"), "release_date": row.get("external_release_date"),
            "label": row.get("label_normalized_override") or row.get("external_label") or row.get("label_normalized")}


def read_state():
    with operational_connect() as conn:
        observations = {r["catalog_key"]: dict(r) for r in conn.execute("SELECT * FROM catalog_metadata_observations").fetchall()}
        reviews = {r["catalog_key"]: dict(r) for r in conn.execute("SELECT * FROM catalog_metadata_reviews").fetchall()}
    return observations, reviews


def comparison(row, observation=None, review=None):
    observation, review = observation or {}, review or {}
    spotify = document(observation.get("payload_json") or {})
    ours = current_values(row)
    protected = protection(row)
    overrides = document(review.get("overrides_json") or {})
    ours.update({k: v for k, v in overrides.items() if k not in protected})
    differences = []
    for field in sorted(FIELDS):
        left, right = ours.get(field), spotify.get(field)
        equal = {norm(x) for x in left or []} == {norm(x) for x in right or []} if field == "artists" else norm(left or "") == norm(right or "")
        if right is not None and not equal:
            differences.append(field)
    reviewed = review.get("observation_version") == observation.get("version")
    decisions = document(review.get("decisions_json") or {}) if reviewed else {}
    pending = [f for f in differences if f not in protected and f not in decisions]
    status = "not_consulted" if not observation else "protected" if protected else "reviewed" if reviewed and not pending else "pending" if differences else "matching"
    if observation and spotify.get("status") != "found":
        status = spotify.get("status") or "not_found"
    return {"catalog_key": row["catalog_key"], "isrc": row.get("asset_isrc"), "title": ours["track_title"],
            "ours": ours, "spotify": spotify, "protected": protected, "differences": differences, "decisions": decisions,
            "status": status, "observation_version": observation.get("version", 0), "review_version": review.get("version", 0),
            "origin": observation.get("origin"), "fetched_at": str(observation.get("fetched_at") or ""),
            "reviewed_by": review.get("updated_by"), "reviewed_at": str(review.get("updated_at") or ""), "sources": row.get("sources"), "provider": spotify.get("provider", "spotify")}


def decide(row, body, actor):
    key = row["catalog_key"]
    field, decision = body.get("field"), body.get("decision")
    if field not in FIELDS or decision not in {"accept", "keep"}:
        raise HTTPException(400, "Elegí un campo y una decisión válidos.")
    with operational_connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("spotify:" + key,))
        observation = conn.execute("SELECT * FROM catalog_metadata_observations WHERE catalog_key=%s FOR UPDATE", (key,)).fetchone()
        review = conn.execute("SELECT * FROM catalog_metadata_reviews WHERE catalog_key=%s FOR UPDATE", (key,)).fetchone()
        if not observation or observation["version"] != body.get("observation_version") or (review["version"] if review else 0) != body.get("review_version"):
            raise HTTPException(409, "La ficha cambió. Actualizala antes de validar.")
        payload = document(observation["payload_json"])
        if decision == "accept" and field in protection(row):
            raise HTTPException(409, "Este campo tiene una corrección manual confirmada y está protegido.")
        if decision == "accept" and not acceptable(payload, row, field):
            raise HTTPException(400, "Se requiere una coincidencia verificable y un valor informado para este campo.")
        decisions = document(review["decisions_json"]) if review and review["observation_version"] == observation["version"] else {}
        overrides = document(review["overrides_json"]) if review else {}
        decisions[field] = decision
        if decision == "accept":
            overrides[field] = payload[field]
        # Keep means preserve the current effective value, including earlier approvals.
        version = (review["version"] if review else 0) + 1
        now = datetime.now(timezone.utc)
        conn.execute("""INSERT INTO catalog_metadata_reviews VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
          ON CONFLICT(catalog_key) DO UPDATE SET observation_version=EXCLUDED.observation_version,version=EXCLUDED.version,
          decisions_json=EXCLUDED.decisions_json,overrides_json=EXCLUDED.overrides_json,updated_by=EXCLUDED.updated_by,updated_at=EXCLUDED.updated_at""",
                     (key, observation["version"], version, json.dumps(decisions), json.dumps(overrides), actor, now))
        audit = {"field": field, "decision": decision, "proposed": payload.get(field), "previous": comparison(row, observation, review)["ours"].get(field), "provider": payload.get("provider", "spotify"), "source_url": payload.get("url"), "decisions": decisions, "overrides": overrides}
        conn.execute("""INSERT INTO catalog_metadata_review_history(catalog_key,version,observation_version,payload_json,updated_by,updated_at)
          VALUES (%s,%s,%s,%s::jsonb,%s,%s)""", (key, version, observation["version"], json.dumps(audit), actor, now))


def apply_approved(frame):
    from app.royalty_scope import is_wml
    if is_wml():return frame
    """Display-only overlay. Raw identity and financial columns are never touched."""
    _, reviews = read_state()
    if not reviews:
        return frame
    rows = frame.to_dicts()
    mapping = {"track_title": "track_title", "artists": "catalog_artists", "duration_seconds": "catalog_duration_seconds", "release_date": "external_release_date", "label": "external_label"}
    for row in rows:
        review = reviews.get(row["catalog_key"])
        if not review:
            continue
        protected = protection(row)
        for field, value in document(review["overrides_json"]).items():
            if field not in protected and field in mapping:
                row[mapping[field]] = value
                if field == "artists":
                    row["catalog_artist_statement"] = " / ".join(value)
                elif field == "label":
                    row["label_normalized_auto"] = value
                    row["label_normalized"] = value
    return pl.DataFrame(rows, infer_schema_length=None, schema_overrides={name: dtype for name, dtype in frame.schema.items()})


def acceptable(payload, row, field):
    if payload.get("status") != "found" or payload.get(field) is None:
        return False
    if payload.get("provider", "spotify") == "youtube":
        return field in {"track_title", "duration_seconds"} and bool(payload.get("video_id")) and payload["video_id"] == row.get("identity_video_id")
    return bool(payload.get("exact_isrc"))


def youtube_observation(item, spotify):
    snippet = item.get("snippet") or {}
    duration = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", (item.get("contentDetails") or {}).get("duration", ""))
    seconds = sum(int(x or 0) * scale for x, scale in zip(duration.groups(), [3600, 60, 1])) if duration else None
    return {"provider": "youtube", "status": "found", "exact_isrc": False,
            "video_id": item["id"], "track_title": snippet.get("title"), "duration_seconds": seconds,
            "artists": None, "release_date": None, "label": None,
            "channel": snippet.get("channelTitle"), "published_at": snippet.get("publishedAt"),
            "url": "https://www.youtube.com/watch?v=" + item["id"], "spotify_observation": spotify}


def refresh(isrc, actor, row=None):
    valid_isrc = bool(re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}", isrc or ""))
    if not valid_isrc and not re.fullmatch(r"[A-Za-z0-9_-]{11}", (row or {}).get("identity_video_id") or ""):
        raise HTTPException(400, "ISRC inválido.")
    client, secret = os.getenv("SPOTIFY_CLIENT_ID"), os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client or not secret:
        raise HTTPException(503, "La conexión con Spotify todavía no está configurada.")
    try:
        token_response = requests.post("https://accounts.spotify.com/api/token", auth=(client, secret), data={"grant_type": "client_credentials"}, timeout=10)
        token_response.raise_for_status()
        response = requests.get("https://api.spotify.com/v1/search", headers={"Authorization": "Bearer " + token_response.json()["access_token"]}, params={"q": "isrc:" + isrc if valid_isrc else "track:" + str(row.get("track_title") or "") + " artist:" + " ".join(current_values(row)["artists"] or []), "type": "track", "limit": 10}, timeout=15)
        if response.status_code == 429:
            raise HTTPException(429, "Spotify pidió una pausa. No se modificaron tus validaciones.", headers={"Retry-After": response.headers.get("Retry-After", "60")})
        response.raise_for_status()
        items = response.json().get("tracks", {}).get("items", [])
        matches = [x for x in items if valid_isrc and (x.get("external_ids") or {}).get("isrc", "").upper() == isrc]
        unique = {json.dumps({"title": norm(x.get("name", "")), "artists": sorted(norm(a["name"]) for a in x.get("artists", [])), "duration": x.get("duration_ms")}, sort_keys=True) for x in matches}
        selected = matches[0] if len(unique) == 1 else {}
        record = {"raw_json": {"selected": selected, "items": items}, "metadata_status": "found" if selected else "ambiguous" if matches else "not_found", "looked_up_at": datetime.now(timezone.utc).isoformat(), "metadata_match_method": "isrc_exact"}
        payload = observation_from_cache(record, isrc or "")
        if not valid_isrc:
            payload["search_candidates"] = [{"title": x.get("name"), "url": x.get("external_urls", {}).get("spotify")} for x in items[:5]]
        origin = "spotify_live"
        video_id = (row or {}).get("identity_video_id")
        if not payload.get("exact_isrc") and video_id and re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            api_key = os.getenv("YOUTUBE_API_KEY")
            if not api_key:
                payload["fallback_note"] = "YouTube todavía no está configurado."
            else:
                try:
                    youtube = requests.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "snippet,contentDetails", "id": video_id, "key": api_key}, timeout=12)
                    if youtube.status_code in {403, 429}:
                        raise HTTPException(429, "YouTube pidió una pausa. Las validaciones se conservaron.", headers={"Retry-After": youtube.headers.get("Retry-After", "60")})
                    youtube.raise_for_status()
                    videos = [v for v in youtube.json().get("items", []) if v.get("id") == video_id]
                    if videos:
                        payload = youtube_observation(videos[0], payload)
                        origin = "youtube_live"
                    else:
                        payload["fallback_note"] = "El video vinculado no está disponible en YouTube."
                except requests.RequestException:
                    raise HTTPException(502, "No se pudo consultar YouTube. Se conservaron las observaciones y validaciones anteriores.")
        elif not payload.get("exact_isrc"):
            payload["fallback_note"] = "No hay un video vinculado para consultar YouTube con seguridad."
        store_observation((row or {}).get("catalog_key") or "ISRC:" + isrc, payload, actor, origin)
    except HTTPException:
        raise
    except (requests.RequestException, KeyError, ValueError):
        raise HTTPException(502, "No se pudo consultar Spotify. Las validaciones anteriores se conservaron.")
