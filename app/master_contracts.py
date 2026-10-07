from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import polars as pl

from app.operational_db import db_sql, is_postgres_connection


ISRC_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")
ARTIST_FIELDS = {
    "soundon": ("Track Artists",),
    "fuga": ("Asset Artist",),
    "onerpm": ("artists_raw",),
    "orchard": ("TRACK ARTIST",),
    "ada": ("artist_catalog_style", "Artist Name"),
    "dashgo": ("Track Artist",),
}
CONTEXT_FIELDS = {
    "ada": ("Project Title", "Catalogue Title", "artist_credit_status", "artist_credit_evidence_file"),
    "fuga": ("Product Artist",),
    "orchard": ("PRODUCT ARTIST",),
    "dashgo": ("Artist Name",),
}
KNOWN_ARTISTS = {
    "aneley": "Aneley",
    "candu dominguez": "Candu Dominguez",
    "g sony": "G Sony",
    "gusty dj": "Gusty DJ",
    "la juntada de los artistas": "La Juntada de los Artistas",
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
    return KNOWN_ARTISTS.get(artist_key(cleaned), cleaned)


def parse_artists(raw: str, source: str) -> list[str]:
    if source == "onerpm":
        matches = re.findall(
            r"(?:^|,)\s*([^,]+?)\s*\(\s*(performer|featuring)\s*\)", raw, re.I
        )
        return [canonical_artist(name) for name, _role in matches]
    separator = {
        "orchard": r"\|",
        "soundon": r"\s*,\s*",
        "dashgo": r"(?!)",
        "fuga": r"\s*,\s*|\s+and\s+|\s+featuring\s+|\s+feat\.?\s+",
    }.get(source, r"\s*,\s*|\s+and\s+|\s+&\s+|\s+featuring\s+|\s+feat\.?\s+")
    parts = re.split(separator, raw, flags=re.I)
    return [canonical_artist(name) for name in parts if name.strip()]


def _ada_artists(raw: str, project_title: str) -> tuple[list[str], str | None]:
    del project_title
    parts = parse_artists(raw, "ada")
    if len(raw) == 30 and parts and (len(parts[-1]) <= 2 or raw.endswith(("&", ","))):
        return parts[:-1] if len(parts[-1]) <= 2 else parts, "Credito ADA posiblemente recortado; no se infieren participantes desde el titulo."
    return parts, None


@lru_cache(maxsize=512)
def _artist_suggestions(isrc: str, raw_path: str, file_mtime_ns: int) -> dict[str, Any]:
    del file_mtime_ns
    frame = pl.scan_parquet(raw_path)
    schema = set(frame.collect_schema().names())
    filtered = frame.filter(pl.col("asset_isrc") == isrc) if "asset_isrc" in schema else None
    first_sale_date = None
    first_sale_precision = None
    if filtered is not None:
        date_fields = [name for name in ("sale_start_date", "transaction_date") if name in schema]
        day_values = [
            pl.col(name).cast(pl.Utf8).str.extract(r"^(\d{4}-\d{2}-\d{2})", 1).str.strptime(pl.Date, "%Y-%m-%d", strict=False)
            for name in date_fields
        ]
        day_expr = pl.min_horizontal(day_values) if day_values else pl.lit(None).cast(pl.Date)
        month_expr = (
            pl.col("transaction_month").cast(pl.Utf8).str.extract(r"^(\d{4}-(?:0[1-9]|1[0-2]))$", 1)
            if "transaction_month" in schema else pl.lit(None).cast(pl.Utf8)
        )
        first = filtered.select(day_expr.min().alias("day"), month_expr.min().alias("month")).collect().row(0, named=True)
        day = first["day"].isoformat() if first["day"] else None
        month = first["month"]
        if month and (not day or month < day[:7]):
            first_sale_date, first_sale_precision = month, "month"
        elif day:
            first_sale_date, first_sale_precision = day, "day"
    columns = ["source"] + sorted({
        field for fields in (*ARTIST_FIELDS.values(), *CONTEXT_FIELDS.values())
        for field in fields if field in schema
    })
    if "asset_isrc" not in schema or len(columns) == 1:
        return {"artists": [], "evidence": [], "warnings": ["Sin campos de artistas en el crudo."],
                "first_sale_date": first_sale_date, "first_sale_precision": first_sale_precision}
    rows = (
        filtered
        .select(columns)
        .unique()
        .collect()
        .to_dicts()
    )
    rows.sort(key=lambda row: tuple(str(row.get(column) or "") for column in columns))
    evidence: list[dict[str, Any]] = []
    candidates: list[tuple[list[str], bool]] = []
    warnings: list[str] = []
    evidence_seen: set[tuple[str, str, str]] = set()
    for row in rows:
        source = str(row.get("source") or "").lower()
        for field in ARTIST_FIELDS.get(source, ()):
            raw = str(row.get(field) or "").strip()
            if not raw:
                continue
            if source == "ada":
                artists, warning = _ada_artists(raw, str(row.get("Project Title") or ""))
                used = field == "artist_catalog_style" or not row.get("artist_catalog_style")
                if row.get("artist_credit_status") in {"possible_truncation", "conflicting_prefix"}:
                    warning = warning or "Credito ADA posiblemente incompleto; se conserva la evidencia original."
            else:
                artists, warning = parse_artists(raw, source), None
                used = True
            if warning and used:
                warnings.append(warning)
            if artists and used:
                candidates.append((artists, warning is None))
            evidence_key = (source, field, raw)
            if evidence_key not in evidence_seen:
                evidence.append({"source": source, "field": field, "raw": raw, "artists": artists, "used": used})
                evidence_seen.add(evidence_key)
        for field in CONTEXT_FIELDS.get(source, ()):
            raw = str(row.get(field) or "").strip()
            evidence_key = (source, field, raw)
            if raw and evidence_key not in evidence_seen:
                evidence.append({"source": source, "field": field, "raw": raw, "artists": [],
                                 "used": False})
                evidence_seen.add(evidence_key)
    complete = [names for names, reliable in candidates if reliable]
    comparable = complete or [names for names, _ in candidates]
    artists = max(comparable, key=len, default=[])
    principal_uncertain = False
    if comparable:
        common = set.intersection(*(set(map(artist_key, names)) for names in comparable))
        if any(set(map(artist_key, names)) != common for names in comparable):
            artists = [name for name in artists if artist_key(name) in common]
            warnings.append("Las fuentes de pista discrepan; sugerimos solo los nombres comunes. Revisar antes de cerrar.")
        if len({artist_key(names[0]) for names in comparable if names}) > 1:
            principal_uncertain = True
            warnings.append("Las fuentes difieren en el artista principal; confirmar el orden manualmente.")
    if len(artists) > 11:
        warnings.append("Hay más de diez participantes sugeridos; revisar el crudo.")
    return {"artists": artists, "evidence": evidence, "warnings": list(dict.fromkeys(warnings)),
            "principal_uncertain": principal_uncertain,
            "first_sale_date": first_sale_date, "first_sale_precision": first_sale_precision}


def artist_suggestions(isrc: str, raw_path: Path | None, fallback: str | None) -> dict[str, Any]:
    raw_result = None
    if raw_path and raw_path.exists():
        try:
            raw_result = _artist_suggestions(isrc, str(raw_path), raw_path.stat().st_mtime_ns)
            if raw_result["evidence"]:
                return raw_result
        except (OSError, pl.PolarsError):
            pass
    fallback = fallback or ""
    artists = parse_artists(fallback, "catalog")
    return {
        "artists": artists,
        "evidence": [{"source": "catalog", "field": "artist_statement", "raw": fallback, "artists": artists, "used": True}],
        "warnings": ["Sugerencia basada en el catálogo; confirmar con el statement."],
        "principal_uncertain": False,
        "first_sale_date": raw_result.get("first_sale_date") if raw_result else None,
        "first_sale_precision": raw_result.get("first_sale_precision") if raw_result else None,
    }


def contract_statement_baseline(summary: pl.LazyFrame, cutoff_month: str) -> pl.DataFrame:
    required = {"statement_period", "source", "account", "isrc", "amount_usd"}
    missing = required - set(summary.collect_schema().names())
    if missing:
        raise ValueError(f"Faltan columnas en la base de Contratos: {', '.join(sorted(missing))}.")
    return (
        summary
        .filter(
            (pl.col("statement_period") <= cutoff_month)
            & pl.col("isrc").fill_null("").str.contains(ISRC_PATTERN.pattern)
        )
        .group_by(["isrc", "source", "account"])
        .agg([
            pl.sum("amount_usd").alias("amount_usd"),
            pl.min("statement_period").alias("first_statement_month"),
            pl.max("statement_period").alias("last_statement_month"),
        ])
        .rename({"isrc": "asset_isrc"})
        .collect(engine="streaming")
    )


def contract_analysis_catalog(current: pl.DataFrame, baseline_net: pl.DataFrame) -> pl.DataFrame:
    if baseline_net.get_column("asset_isrc").n_unique() != baseline_net.height:
        raise ValueError("La base neta de Contratos tiene ISRC duplicados.")
    historical_amounts = baseline_net.select([
        "asset_isrc",
        pl.col("amount_usd").alias("_contract_analysis_amount_usd"),
        pl.col("first_statement_month").alias("_contract_first_statement_month"),
        pl.col("last_statement_month").alias("_contract_last_statement_month"),
    ])
    return (
        current
        .join(historical_amounts, on="asset_isrc", how="left")
        .with_columns(pl.col("_contract_analysis_amount_usd").fill_null(0.0).alias("amount_usd"))
        .drop("_contract_analysis_amount_usd")
        .sort(["amount_usd", "asset_isrc"], descending=[True, False])
    )


def suggested_split(
    artists: list[str], contracts: dict[str, dict[str, Any]] | None = None,
    first_sale_date: str | None = None,
) -> dict[str, Any]:
    contracts = contracts or {}
    principal = artists[0] if artists else ""
    main_contract = contracts.get(artist_key(principal))
    base = main_contract["indyana_percent"] if main_contract else None
    is_project = bool(main_contract and main_contract["is_project"])
    return {
        "agreements": [{
            "id": "principal",
            "label": "Contrato principal",
            "commercialization": "pending",
            "owners": [],
            "effective_from": first_sale_date,
            "effective_until": None,
        }],
        "master_type": "pending",
        "other_master_artist": None,
        "has_contract": main_contract["has_contract"] if main_contract else None,
        "agreement_confirmed": False,
        "effective_from": first_sale_date,
        "principal": principal,
        "indyana_percent": base,
        "principal_percent": 100 - base if base is not None and len(artists) == 1 else None,
        "apply_guest_contracts": is_project,
        "participants": [
            {
                "artist": artist,
                "percent": None,
                "internal_contract_indyana_percent": contracts.get(artist_key(artist), {}).get("indyana_percent"),
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


def ensure_artist_contract_tables(conn: Any) -> None:
    if is_postgres_connection(conn):
        return
    conn.execute(
        """CREATE TABLE IF NOT EXISTS master_artist_contracts (
            artist_key TEXT PRIMARY KEY, artist_name TEXT NOT NULL,
            indyana_percent REAL NOT NULL, has_contract INTEGER NOT NULL,
            effective_from TEXT, is_project INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1, notes TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL, updated_by TEXT NOT NULL, updated_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS master_artist_contract_history (
            artist_key TEXT NOT NULL, version INTEGER NOT NULL, payload_json TEXT NOT NULL,
            updated_by TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY (artist_key, version)
        )"""
    )


def list_artist_contracts(conn: Any) -> list[dict[str, Any]]:
    ensure_artist_contract_tables(conn)
    rows = conn.execute("SELECT * FROM master_artist_contracts ORDER BY artist_name").fetchall()
    return [
        {
            "artist_key": row["artist_key"],
            "artist_name": row["artist_name"],
            "indyana_percent": float(row["indyana_percent"]),
            "has_contract": bool(row["has_contract"]),
            "effective_from": row["effective_from"],
            "is_project": bool(row["is_project"]),
            "is_active": bool(row["is_active"]),
            "notes": row["notes"],
            "version": int(row["version"]),
            "updated_by": row["updated_by"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def active_artist_contracts(conn: Any) -> dict[str, dict[str, Any]]:
    return {row["artist_key"]: row for row in list_artist_contracts(conn) if row["is_active"]}


def save_artist_contract(
    conn: Any, contract: dict[str, Any], *, expected_version: int, actor: str,
) -> dict[str, Any]:
    ensure_artist_contract_tables(conn)
    name = canonical_artist(str(contract.get("artist_name") or ""))
    key = artist_key(name)
    if not key or len(name) > 200:
        raise ValueError("Indicá un nombre de artista válido.")
    percent = float(contract["indyana_percent"])
    if not math.isfinite(percent) or percent < 0 or percent > 100:
        raise ValueError("El porcentaje de Indyana debe estar entre 0 y 100.")
    effective_from = contract.get("effective_from") or None
    if effective_from and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(effective_from)):
        raise ValueError("La vigencia debe tener formato AAAA-MM.")
    notes = str(contract.get("notes") or "").strip()
    if len(notes) > 3000:
        raise ValueError("Las notas no pueden superar 3000 caracteres.")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    version = expected_version + 1
    values = (
        name, percent, int(bool(contract["has_contract"])), effective_from,
        int(bool(contract.get("is_project"))), int(bool(contract.get("is_active", True))),
        notes, version, actor, now, key,
    )
    if expected_version == 0:
        insert = """INSERT INTO master_artist_contracts
            (artist_name, indyana_percent, has_contract, effective_from, is_project,
             is_active, notes, version, updated_by, updated_at, artist_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(artist_key) DO NOTHING"""
        if is_postgres_connection(conn):
            cursor = conn.execute(db_sql(conn, f"WITH inserted AS ({insert} RETURNING artist_key) SELECT artist_key FROM inserted"), values)
            saved = cursor.fetchone() is not None
        else:
            saved = conn.execute(insert, values).rowcount == 1
    else:
        cursor = conn.execute(
            db_sql(conn, """UPDATE master_artist_contracts SET artist_name = ?, indyana_percent = ?,
                has_contract = ?, effective_from = ?, is_project = ?, is_active = ?,
                notes = ?, version = ?, updated_by = ?, updated_at = ?
                WHERE artist_key = ? AND version = ?"""), values + (expected_version,),
        )
        saved = cursor.rowcount == 1
    if not saved:
        raise ValueError("El contrato cambió desde que lo abriste. Actualizalo antes de guardar.")
    result = {
        "artist_key": key, "artist_name": name, "indyana_percent": percent,
        "has_contract": bool(contract["has_contract"]), "effective_from": effective_from,
        "is_project": bool(contract.get("is_project")), "is_active": bool(contract.get("is_active", True)),
        "notes": notes, "version": version, "updated_by": actor, "updated_at": now,
    }
    history_values = (key, version, json.dumps(result, ensure_ascii=False, sort_keys=True), actor, now)
    history_insert = """INSERT INTO master_artist_contract_history
        (artist_key, version, payload_json, updated_by, updated_at) VALUES (?, ?, ?, ?, ?)"""
    if is_postgres_connection(conn):
        conn.execute(db_sql(conn, f"WITH inserted AS ({history_insert} RETURNING artist_key) SELECT artist_key FROM inserted"), history_values)
    else:
        conn.execute(history_insert, history_values)
    return result


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
    if effective_from and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])(?:-(0[1-9]|[12][0-9]|3[01]))?", str(effective_from)):
        raise ValueError("La vigencia debe tener formato AAAA-MM o AAAA-MM-DD.")
    if effective_from and len(str(effective_from)) == 10:
        try:
            date.fromisoformat(str(effective_from))
        except ValueError as exc:
            raise ValueError("La fecha de vigencia no es válida.") from exc
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
    agreements = split.get("agreements")
    if agreements:
        if len(agreements) > 20:
            raise ValueError("Se admiten hasta veinte contratos por ISRC.")
        ids: set[str] = set()
        for index, agreement in enumerate(agreements, start=1):
            agreement_id = str(agreement.get("id") or "").strip()
            if not agreement_id or agreement_id in ids:
                raise ValueError("Cada contrato debe tener un identificador único.")
            ids.add(agreement_id)
            label = str(agreement.get("label") or f"Contrato {index}").strip()
            commercialization = agreement.get("commercialization")
            if commercialization not in {"distribution", "master"}:
                raise ValueError(f"{label}: elegí Distribución o Master.")
            start = agreement.get("effective_from")
            end = agreement.get("effective_until")
            if not start:
                raise ValueError(f"{label}: completá Vigente desde.")
            try:
                start_date = _period_start(str(start)) if start else None
                end_date = _period_end(str(end)) if end else None
            except ValueError as exc:
                raise ValueError(f"{label}: la vigencia debe ser una fecha o un mes válido.") from exc
            if start_date and end_date and start_date > end_date:
                raise ValueError(f"{label}: la vigencia hasta es anterior a la vigencia desde.")
            owners = agreement.get("owners") or []
            if commercialization == "distribution" and owners:
                raise ValueError(f"{label}: una distribución no lleva titulares de master.")
            if commercialization == "master":
                if not owners:
                    raise ValueError(f"{label}: agregá al menos un titular del master.")
                owner_keys = [artist_key(str(owner.get("name") or "")) for owner in owners]
                if any(not key for key in owner_keys) or len(set(owner_keys)) != len(owner_keys):
                    raise ValueError(f"{label}: los titulares deben tener nombres únicos.")
                percentages = [owner.get("percent") for owner in owners]
                if any(value is None or not math.isfinite(float(value)) or not 0 <= float(value) <= 100 for value in percentages) or abs(sum(float(value) for value in percentages) - 100) > 0.0001:
                    raise ValueError(f"{label}: los titulares del master deben sumar 100%.")
    else:
        if split.get("master_type") == "pending" or split.get("has_contract") is None:
            raise ValueError("Para cerrar, indicá el tipo de master y si existe contrato.")
        if split.get("master_type") in {"indyana_and_other", "mawz_and_other"} and not str(split.get("other_master_artist") or "").strip():
            raise ValueError("Para cerrar, elegí el otro artista titular del master.")
    percentages = [split.get("indyana_percent"), split.get("principal_percent")]
    percentages.extend(item.get("percent") for item in participants)
    if any(value is None for value in percentages):
        raise ValueError("Para cerrar, completá todos los porcentajes.")
    if abs(sum(float(value) for value in percentages) - 100.0) > 0.0001:
        raise ValueError("Para cerrar, Indyana y los artistas deben sumar 100%.")


def _period_start(value: str) -> date:
    if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        return date.fromisoformat(value + "-01")
    if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])-\d{2}", value):
        return date.fromisoformat(value)
    raise ValueError("Fecha o mes inválido.")


def _period_end(value: str) -> date:
    if len(value) == 7:
        _period_start(value)
        from calendar import monthrange
        year, month = map(int, value.split("-"))
        return date(year, month, monthrange(year, month)[1])
    return _period_start(value)


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
        if is_postgres_connection(conn):
            cursor = conn.execute(
                db_sql(conn, """WITH inserted AS (
                    INSERT INTO master_contract_splits
                    (payload_json, is_closed, future_reports_selected, version, updated_by, updated_at, isrc)
                    VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(isrc) DO NOTHING RETURNING isrc
                ) SELECT isrc FROM inserted"""), values
            )
            saved = cursor.fetchone() is not None
        else:
            cursor = conn.execute(
                """INSERT INTO master_contract_splits
                (payload_json, is_closed, future_reports_selected, version, updated_by, updated_at, isrc)
                VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(isrc) DO NOTHING""", values
            )
            saved = cursor.rowcount == 1
    else:
        cursor = conn.execute(
            db_sql(conn, """UPDATE master_contract_splits SET
                payload_json = ?, is_closed = ?, future_reports_selected = ?, version = ?,
                updated_by = ?, updated_at = ? WHERE isrc = ? AND version = ?"""),
            values + (expected_version,),
        )
        saved = cursor.rowcount == 1
    if not saved:
        raise ValueError("La ficha cambió desde que la abriste. Actualizala antes de guardar.")
    history_values = (isrc, version, payload, int(closed), int(future_reports_selected), actor, now)
    if is_postgres_connection(conn):
        conn.execute(
            db_sql(conn, """WITH inserted AS (
                INSERT INTO master_contract_split_history
                (isrc, version, payload_json, is_closed, future_reports_selected, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING isrc
            ) SELECT isrc FROM inserted"""), history_values,
        )
    else:
        conn.execute(
            """INSERT INTO master_contract_split_history
            (isrc, version, payload_json, is_closed, future_reports_selected, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", history_values,
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
