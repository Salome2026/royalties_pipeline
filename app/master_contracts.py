from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import polars as pl

from app.operational_db import db_sql, is_postgres_connection


ISRC_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")
ARTIST_FIELDS = {
    "soundon": ("Track Artists",),
    "fuga": ("Asset Artist", "Product Artist"),
    "onerpm": ("artists_raw",),
    "orchard": ("TRACK ARTIST", "PRODUCT ARTIST"),
    "ada": ("Artist Name",),
    "dashgo": ("Track Artist", "Artist Name"),
}
FIELD_RANK = {
    "Track Artists": 5,
    "Asset Artist": 5,
    "TRACK ARTIST": 5,
    "Track Artist": 5,
    "artists_raw": 5,
    "Artist Name": 4,
    "Product Artist": 3,
    "PRODUCT ARTIST": 3,
}
KNOWN_ARTISTS = {
    "aneley": ("Aneley", 50.0),
    "candu dominguez": ("Candu Dominguez", 70.0),
    "g sony": ("G Sony", 50.0),
    "gusty dj": ("Gusty DJ", 70.0),
    "la juntada de los artistas": ("La Juntada de los Artistas", 70.0),
}


def clean_isrc(value: str) -> str:
    isrc = re.sub(r"[^A-Z0-9]", "", value.strip().upper())
    if not ISRC_PATTERN.fullmatch(isrc):
        raise ValueError("ISRC inválido.")
    return isrc


def artist_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip())
    unaccented = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", unaccented.casefold())


def canonical_artist(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    return KNOWN_ARTISTS.get(artist_key(cleaned), (cleaned, None))[0]


def parse_artists(raw: str, source: str) -> list[str]:
    if source == "onerpm":
        matches = re.findall(
            r"(?:^|,)\s*([^,]+?)\s*\(\s*(performer|featuring)\s*\)", raw, re.I
        )
        return [canonical_artist(name) for name, _role in matches]
    parts = re.split(r"\s*,\s*|\s+and\s+|\s+&\s+|\s+featuring\s+|\s+feat\.?\s+", raw, flags=re.I)
    return [canonical_artist(name) for name in parts if name.strip()]


@lru_cache(maxsize=512)
def _artist_suggestions(isrc: str, raw_path: str, file_mtime_ns: int) -> dict[str, Any]:
    del file_mtime_ns
    frame = pl.scan_parquet(raw_path)
    schema = set(frame.collect_schema().names())
    columns = ["source"] + sorted({field for fields in ARTIST_FIELDS.values() for field in fields if field in schema})
    if "asset_isrc" not in schema or len(columns) == 1:
        return {"artists": [], "evidence": [], "warnings": ["Sin campos de artistas en el crudo."]}
    rows = (
        frame.filter(pl.col("asset_isrc") == isrc)
        .select(columns)
        .unique()
        .collect()
        .to_dicts()
    )
    evidence: list[dict[str, Any]] = []
    for row in rows:
        source = str(row.get("source") or "").lower()
        for field in ARTIST_FIELDS.get(source, ()):
            raw = str(row.get(field) or "").strip()
            if not raw:
                continue
            artists = parse_artists(raw, source)
            if artists:
                evidence.append({"source": source, "field": field, "raw": raw, "artists": artists})
    evidence.sort(key=lambda item: (len(item["artists"]), FIELD_RANK.get(item["field"], 0)), reverse=True)
    artists: list[str] = []
    seen: set[str] = set()
    for item in evidence:
        for artist in item["artists"]:
            key = artist_key(artist)
            if key and key not in seen:
                artists.append(artist)
                seen.add(key)
    first_names = {artist_key(item["artists"][0]) for item in evidence}
    warnings = ["Las fuentes difieren en el artista principal."] if len(first_names) > 1 else []
    if len(artists) > 11:
        warnings.append("Hay más de diez participantes sugeridos; revisar el crudo.")
    return {"artists": artists, "evidence": evidence, "warnings": warnings}


def artist_suggestions(isrc: str, raw_path: Path | None, fallback: str | None) -> dict[str, Any]:
    if raw_path and raw_path.exists():
        try:
            result = _artist_suggestions(isrc, str(raw_path), raw_path.stat().st_mtime_ns)
            if result["artists"]:
                return result
        except (OSError, pl.PolarsError):
            pass
    artists = parse_artists(fallback or "", "catalog")
    return {
        "artists": artists,
        "evidence": [{"source": "catalog", "field": "artist_statement", "raw": fallback or "", "artists": artists}],
        "warnings": ["Sugerencia basada en el catálogo; confirmar con el statement."],
    }


def suggested_split(artists: list[str]) -> dict[str, Any]:
    principal = artists[0] if artists else ""
    base = KNOWN_ARTISTS.get(artist_key(principal), (None, None))[1]
    return {
        "master_type": "pending",
        "has_contract": None,
        "agreement_confirmed": False,
        "effective_from": None,
        "principal": principal,
        "indyana_percent": base,
        "principal_percent": None,
        "apply_guest_contracts": artist_key(principal) == "la juntada de los artistas",
        "participants": [
            {
                "artist": artist,
                "percent": None,
                "internal_contract_indyana_percent": (
                    KNOWN_ARTISTS[artist_key(artist)][1]
                    if artist_key(principal) == "la juntada de los artistas" and artist_key(artist) in KNOWN_ARTISTS
                    else None
                ),
            }
            for artist in artists[1:11]
        ],
        "notes": "",
    }


def ensure_sqlite_tables(conn: Any) -> None:
    if is_postgres_connection(conn):
        return
    conn.execute(
        """CREATE TABLE IF NOT EXISTS master_contract_splits (
            isrc TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            is_closed INTEGER NOT NULL DEFAULT 0,
            future_reports_selected INTEGER NOT NULL DEFAULT 0,
            version INTEGER NOT NULL,
            updated_by TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS master_contract_split_history (
            isrc TEXT NOT NULL,
            version INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            is_closed INTEGER NOT NULL,
            future_reports_selected INTEGER NOT NULL,
            updated_by TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (isrc, version)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_master_contract_splits_closed ON master_contract_splits(is_closed)")


def read_split(conn: Any, isrc: str) -> dict[str, Any] | None:
    ensure_sqlite_tables(conn)
    row = conn.execute(
        db_sql(conn, "SELECT * FROM master_contract_splits WHERE isrc = ?"), (isrc,)
    ).fetchone()
    if row is None:
        return None
    return {
        "isrc": isrc,
        "split": json.loads(row["payload_json"]),
        "closed": bool(row["is_closed"]),
        "future_reports_selected": bool(row["future_reports_selected"]),
        "version": int(row["version"]),
        "updated_by": row["updated_by"],
        "updated_at": row["updated_at"],
    }


def read_split_statuses(conn: Any) -> dict[str, dict[str, Any]]:
    ensure_sqlite_tables(conn)
    rows = conn.execute(
        "SELECT isrc, is_closed, future_reports_selected, version, updated_at FROM master_contract_splits"
    ).fetchall()
    return {
        row["isrc"]: {
            "closed": bool(row["is_closed"]),
            "future_reports_selected": bool(row["future_reports_selected"]),
            "version": int(row["version"]),
            "updated_at": row["updated_at"],
        }
        for row in rows
    }


def validate_split(split: dict[str, Any], closed: bool, future_reports_selected: bool) -> None:
    principal = str(split.get("principal") or "").strip()
    effective_from = split.get("effective_from")
    if effective_from and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(effective_from)):
        raise ValueError("La vigencia debe tener formato AAAA-MM.")
    participants = split.get("participants") or []
    if len(participants) > 10:
        raise ValueError("El piloto admite hasta diez participantes por ISRC.")
    seen = {artist_key(principal)} if principal else set()
    for item in participants:
        artist = str(item.get("artist") or "").strip()
        key = artist_key(artist)
        if not key or key in seen:
            raise ValueError("Cada participante debe tener un nombre único y distinto del principal.")
        seen.add(key)
    if future_reports_selected and not closed:
        raise ValueError("Solo un ISRC cerrado puede quedar seleccionado para una futura aplicación.")
    if not closed:
        return
    if not principal or not split.get("agreement_confirmed"):
        raise ValueError("Para cerrar, confirmá el acuerdo y el artista principal.")
    if split.get("master_type") == "pending" or split.get("has_contract") is None:
        raise ValueError("Para cerrar, indicá el tipo de master y si existe contrato.")
    percentages = [split.get("indyana_percent"), split.get("principal_percent")]
    percentages.extend(item.get("percent") for item in participants)
    if any(value is None for value in percentages):
        raise ValueError("Para cerrar, completá todos los porcentajes.")
    if abs(sum(float(value) for value in percentages) - 100.0) > 0.0001:
        raise ValueError("Para cerrar, Indyana y los artistas deben sumar 100%.")


def save_split(
    conn: Any,
    isrc: str,
    split: dict[str, Any],
    *,
    closed: bool,
    future_reports_selected: bool,
    expected_version: int,
    actor: str,
) -> dict[str, Any]:
    ensure_sqlite_tables(conn)
    validate_split(split, closed, future_reports_selected)
    payload = json.dumps(split, ensure_ascii=False, sort_keys=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    version = expected_version + 1
    values = (payload, int(closed), int(future_reports_selected), version, actor, now, isrc)
    if expected_version == 0:
        cursor = conn.execute(
            db_sql(conn, """INSERT INTO master_contract_splits
                (payload_json, is_closed, future_reports_selected, version, updated_by, updated_at, isrc)
                VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(isrc) DO NOTHING"""), values
        )
    else:
        cursor = conn.execute(
            db_sql(conn, """UPDATE master_contract_splits SET
                payload_json = ?, is_closed = ?, future_reports_selected = ?, version = ?,
                updated_by = ?, updated_at = ? WHERE isrc = ? AND version = ?"""),
            values + (expected_version,),
        )
    if cursor.rowcount != 1:
        raise ValueError("La ficha cambió desde que la abriste. Actualizala antes de guardar.")
    conn.execute(
        db_sql(conn, """INSERT INTO master_contract_split_history
            (isrc, version, payload_json, is_closed, future_reports_selected, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)"""),
        (isrc, version, payload, int(closed), int(future_reports_selected), actor, now),
    )
    return {
        "isrc": isrc,
        "split": split,
        "closed": closed,
        "future_reports_selected": future_reports_selected,
        "version": version,
        "updated_by": actor,
        "updated_at": now,
    }
