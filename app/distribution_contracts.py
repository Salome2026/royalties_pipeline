"""Reusable distribution initial allocations; saved songs retain their own copy."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any

from app.master_contracts import artist_key, distribution_recipient_rows
from app.operational_db import db_sql, is_postgres_connection
from app.royalty_scope import is_wml


def require_distribution_scope(conn: Any) -> None:
    if is_wml() or not is_postgres_connection(conn):
        raise ValueError("Los contratos de distribución corresponden al catálogo habitual en Cloud SQL Postgres.")


def validate_terms(contract: dict) -> dict:
    label = re.sub(r"\s+", " ", str(contract.get("label") or "")).strip()
    sublabel = re.sub(r"\s+", " ", str(contract.get("sublabel") or "")).strip()
    if not label or max(len(label), len(sublabel)) > 200:
        raise ValueError("Ingresá un sello; sello y subsello admiten hasta 200 caracteres.")
    pool = contract.get("master_pool_percent")
    if pool is None or not math.isfinite(float(pool)) or not 0 <= float(pool) <= 100:
        raise ValueError("Completá el porcentaje de comercialización entre 0 y 100.")
    agreement = {"commercialization": "distribution", "allocation_model": "pools",
                 "master_pool_percent": float(pool), "company_name": str(contract.get("company_name") or "").strip(),
                 "distribution_recipients": contract.get("distribution_recipients")}
    rows = distribution_recipient_rows(agreement)
    if any(not row["name"].strip() or len(row["name"].strip()) > 200 for row in rows):
        raise ValueError("Completá los destinatarios; admiten hasta 200 caracteres.")
    if agreement["distribution_recipients"] is not None:
        cleaned = [{"name": row["name"].strip(), "percent": float(row["percent"])} for row in rows]
        if len(cleaned) == 1:
            agreement.update(company_name=cleaned[0]["name"], distribution_recipients=None)
        else:
            agreement["distribution_recipients"] = cleaned
    notes = str(contract.get("notes") or "").strip()
    if len(notes) > 3000:
        raise ValueError("Las notas no pueden superar 3000 caracteres.")
    return {"label": label, "sublabel": sublabel, "master_pool_percent": float(pool),
            "company_name": agreement["company_name"], "distribution_recipients": agreement["distribution_recipients"],
            "notes": notes}


def _record(row) -> dict:
    return {"number": int(row["number"]), **json.loads(row["payload_json"]), "version": int(row["version"]),
            "updated_by": row["updated_by"], "updated_at": row["updated_at"]}


def list_distribution_contracts(conn: Any) -> list[dict]:
    require_distribution_scope(conn)
    return [_record(row) for row in conn.execute("SELECT * FROM master_distribution_contracts ORDER BY number").fetchall()]


def save_distribution_contract(conn: Any, contract: dict, *, number: int | None, expected_version: int, actor: str) -> dict:
    require_distribution_scope(conn)
    terms = validate_terms(contract)
    if number is None and expected_version != 0:
        raise ValueError("Un contrato nuevo debe comenzar en versión cero.")
    # Serialize number allocation, label uniqueness, and edits in one transaction.
    conn.execute("SELECT singleton FROM master_distribution_contract_counter WHERE singleton = 1 FOR UPDATE").fetchone()
    duplicate = conn.execute(db_sql(conn, """SELECT number FROM master_distribution_contracts
        WHERE label_key = ? AND sublabel_key = ? AND number <> ?"""),
        (artist_key(terms["label"]), artist_key(terms["sublabel"]), number or 0)).fetchone()
    if duplicate:
        raise ValueError(f"El sello y subsello ya pertenecen al contrato nro. {duplicate['number']}. Usá un subsello diferente.")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    version = expected_version + 1
    payload = json.dumps(terms, ensure_ascii=False, sort_keys=True)
    if number is None:
        row = conn.execute("""UPDATE master_distribution_contract_counter SET last_number = last_number + 1
            WHERE singleton = 1 RETURNING last_number""").fetchone()
        if row is None:
            raise ValueError("Falta instalar la numeración de contratos de distribución.")
        number = int(row["last_number"])
        conn.execute(db_sql(conn, """INSERT INTO master_distribution_contracts
            (number, label_key, sublabel_key, payload_json, version, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)"""),
            (number, artist_key(terms["label"]), artist_key(terms["sublabel"]), payload, version, actor, now))
    else:
        cursor = conn.execute(db_sql(conn, """UPDATE master_distribution_contracts SET label_key = ?, sublabel_key = ?,
            payload_json = ?, version = ?, updated_by = ?, updated_at = ? WHERE number = ? AND version = ?"""),
            (artist_key(terms["label"]), artist_key(terms["sublabel"]), payload, version, actor, now, number, expected_version))
        if cursor.rowcount != 1:
            raise ValueError("El contrato cambió desde que lo abriste. Actualizalo antes de guardar.")
    conn.execute(db_sql(conn, """INSERT INTO master_distribution_contract_history
        (number, version, payload_json, updated_by, updated_at) VALUES (?, ?, ?, ?, ?)"""),
        (number, version, payload, actor, now))
    return {"number": number, **terms, "version": version, "updated_by": actor, "updated_at": now}


def validate_distribution_references(conn: Any, split: dict) -> None:
    for agreement in split.get("agreements") or []:
        number, version = agreement.get("distribution_contract_number"), agreement.get("distribution_contract_version")
        if number is None and version is None:
            continue
        require_distribution_scope(conn)
        if number is None or version is None or agreement.get("commercialization") != "distribution":
            raise ValueError("La referencia al contrato de distribución debe tener número, versión y comercialización Distribución.")
        row = conn.execute(db_sql(conn, "SELECT number FROM master_distribution_contract_history WHERE number = ? AND version = ?"),
                           (number, version)).fetchone()
        if row is None:
            raise ValueError("El contrato de distribución o su versión no existe. Volvé a seleccionarlo.")
