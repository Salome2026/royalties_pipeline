from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
import sys
from typing import Any


BASE = Path(__file__).resolve().parents[2]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from app.operational_db import operational_connect, operational_db_settings
from .distributor_adjustment import adjustment_percent, adjustment_schedule


POLICY_SCHEMA_VERSION = 1
_POLICY_SNAPSHOT: ContextVar[dict[str, Any] | None] = ContextVar(
    "distributor_policy_snapshot",
    default=None,
)


def _require_postgres() -> None:
    settings = operational_db_settings()
    if settings.driver != "postgres":
        raise RuntimeError("Distributor policies require the operational Cloud SQL database.")


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        import json

        return json.loads(value)
    return value


def _document_from_rows(settings_row: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(_json_value(row["policy_payload"]) or {})
        payload.update({
            "policy_id": row["policy_id"],
            "source": row["source"],
            "account": row["account"],
            "display_name": row["display_name"],
            "report_net_adjustment_pct": float(row["report_net_adjustment_pct"] or 0.0),
        })
        entries.append(payload)

    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "mode": "production_policy",
        "description": "Production distributor policies stored in the operational Cloud SQL database.",
        "policy_version": int(settings_row["policy_version"]),
        "updated_at": settings_row["updated_at"].isoformat() if settings_row.get("updated_at") else None,
        "updated_by": settings_row.get("updated_by"),
        "report_personalization": {
            "enabled": bool(settings_row["personalization_enabled"]),
            "amount_basis": settings_row["amount_basis"],
            "scope": settings_row["scope"],
        },
        "entries": entries,
    }


def load_distributor_policy_document() -> dict[str, Any]:
    snapshot = _POLICY_SNAPSHOT.get()
    if snapshot is not None:
        return deepcopy(snapshot)
    from app.royalty_scope import is_wml, wml_policy
    if is_wml():
        return wml_policy()
    _require_postgres()
    with operational_connect() as conn:
        return read_distributor_policy_document(conn)


def read_distributor_policy_document(conn) -> dict[str, Any]:
    settings_row = conn.execute(
        "SELECT * FROM distributor_policy_settings WHERE singleton_id = 1"
    ).fetchone()
    rows = conn.execute(
        """
        SELECT policy_id, source, account, display_name, policy_payload,
               report_net_adjustment_pct, active, policy_version, updated_by, updated_at
        FROM distributor_account_policies
        WHERE active = TRUE
        ORDER BY source, account
        """
    ).fetchall()
    if settings_row is None:
        raise RuntimeError("Distributor policy settings are not initialized in Cloud SQL.")
    if not rows:
        raise RuntimeError("Distributor account policies are not initialized in Cloud SQL.")
    return _document_from_rows(settings_row, rows)


@contextmanager
def use_distributor_policy_snapshot(document: dict[str, Any]):
    if int(document.get("schema_version") or 0) != POLICY_SCHEMA_VERSION:
        raise RuntimeError("El snapshot de policies del reporte no es valido.")
    if int(document.get("policy_version") or 0) <= 0:
        raise RuntimeError("El snapshot de policies no tiene una version valida.")
    if not isinstance(document.get("entries"), list) or not document["entries"]:
        raise RuntimeError("El snapshot de policies no contiene distribuidoras.")
    token = _POLICY_SNAPSHOT.set(deepcopy(document))
    try:
        yield
    finally:
        _POLICY_SNAPSHOT.reset(token)


def replace_distributor_policy_document(payload: dict[str, Any], updated_by: str) -> dict[str, Any]:
    """One-time/bootstrap replacement of the complete policy document."""
    _require_postgres()
    entries = payload.get("entries") or []
    if not entries:
        raise ValueError("Distributor policy document has no entries.")

    personalization = payload.get("report_personalization") or {}
    with operational_connect() as conn:
        settings_row = conn.execute(
            "SELECT policy_version FROM distributor_policy_settings WHERE singleton_id = 1 FOR UPDATE"
        ).fetchone()
        version = int(settings_row["policy_version"] if settings_row else 0) + 1
        conn.execute("DELETE FROM distributor_account_policies")
        for entry in entries:
            policy = dict(entry)
            policy_id = str(policy.pop("policy_id", "")).strip()
            source = str(policy.pop("source", "")).strip().lower()
            account = str(policy.pop("account", "")).strip().lower()
            display_name = str(policy.pop("display_name", "")).strip()
            adjustment = float(policy.pop("report_net_adjustment_pct", 0.0) or 0.0)
            if not policy_id or not source or not account or not display_name:
                raise ValueError("Invalid distributor policy entry.")
            conn.execute(
                """
                INSERT INTO distributor_account_policies(
                    policy_id, source, account, display_name, policy_payload,
                    report_net_adjustment_pct, policy_version, updated_by
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                """,
                (policy_id, source, account, display_name, __import__("json").dumps(policy), adjustment, version, updated_by),
            )
        conn.execute(
            """
            INSERT INTO distributor_policy_settings(
                singleton_id, personalization_enabled, amount_basis, scope,
                policy_version, updated_by, updated_at
            ) VALUES (1, %s, %s, %s, %s, %s, now())
            ON CONFLICT (singleton_id) DO UPDATE SET
                personalization_enabled = EXCLUDED.personalization_enabled,
                amount_basis = EXCLUDED.amount_basis,
                scope = EXCLUDED.scope,
                policy_version = EXCLUDED.policy_version,
                updated_by = EXCLUDED.updated_by,
                updated_at = now()
            """,
            (
                bool(personalization.get("enabled", False)),
                str(personalization.get("amount_basis") or "net_amount_after_distributor"),
                str(personalization.get("scope") or "royalty_reports"),
                version,
                updated_by,
            ),
        )
        after = load_document_in_transaction(conn)
        conn.execute(
            """
            INSERT INTO distributor_policy_audit(policy_version, action, changed_by, after_json)
            VALUES (%s, 'bootstrap', %s, %s::jsonb)
            """,
            (version, updated_by, __import__("json").dumps(after)),
        )
    return load_distributor_policy_document()


def load_document_in_transaction(conn: Any) -> dict[str, Any]:
    settings_row = conn.execute(
        "SELECT * FROM distributor_policy_settings WHERE singleton_id = 1"
    ).fetchone()
    rows = conn.execute(
        """
        SELECT policy_id, source, account, display_name, policy_payload,
               report_net_adjustment_pct, active, policy_version, updated_by, updated_at
        FROM distributor_account_policies
        WHERE active = TRUE
        ORDER BY source, account
        """
    ).fetchall()
    if settings_row is None or not rows:
        raise RuntimeError("Distributor policies are not initialized in Cloud SQL.")
    return _document_from_rows(settings_row, rows)


def update_report_personalization(
    *,
    enabled: bool,
    accounts: list[dict[str, Any]],
    updated_by: str,
) -> dict[str, Any]:
    _require_postgres()
    requested = {}
    for item in accounts:
        policy_id = str(item["policy_id"])
        if policy_id in requested:
            raise ValueError("La misma cuenta no se puede configurar dos veces.")
        base = item.get("report_net_adjustment_pct")
        requested[policy_id] = (
            adjustment_percent(base) if base is not None else None,
            adjustment_schedule(item.get("schedule_additions") or []),
        )

    with operational_connect() as conn:
        settings_row = conn.execute(
            "SELECT * FROM distributor_policy_settings WHERE singleton_id = 1 FOR UPDATE"
        ).fetchone()
        if settings_row is None:
            raise RuntimeError("Distributor policy settings are not initialized in Cloud SQL.")
        before = load_document_in_transaction(conn)
        available = {row["policy_id"]: row for row in before["entries"]}
        missing = sorted(set(requested) - set(available))
        if missing:
            raise KeyError(f"Unknown distributor policies: {', '.join(missing)}")

        version = int(settings_row["policy_version"]) + 1
        import json
        updates = []
        for policy_id, (adjustment, additions) in requested.items():
            entry = available[policy_id]
            base = entry["report_net_adjustment_pct"]
            schedule = adjustment_schedule(entry.get("report_adjustment_schedule") or [])
            if adjustment is not None and adjustment != base and (schedule or additions):
                raise ValueError("El porcentaje historico no se puede cambiar al agregar o usar vigencias.")
            if schedule and additions and additions[0]["from_statement"] <= schedule[-1]["from_statement"]:
                raise ValueError("El nuevo cambio debe ser posterior a la ultima vigencia guardada.")
            if additions or (adjustment is not None and adjustment != base):
                updates.append((policy_id, base if adjustment is None else adjustment, additions, schedule))
        if not updates and enabled == before["report_personalization"]["enabled"]:
            return before
        for policy_id, adjustment, additions, schedule in updates:
            conn.execute(
                """
                UPDATE distributor_account_policies
                SET report_net_adjustment_pct = %s, policy_version = %s,
                    policy_payload = CASE WHEN %s THEN
                        jsonb_set(policy_payload, '{report_adjustment_schedule}', %s::jsonb)
                        ELSE policy_payload END,
                    updated_by = %s, updated_at = now()
                WHERE policy_id = %s
                """,
                (adjustment, version, bool(additions), json.dumps(schedule + additions), updated_by, policy_id),
            )
        conn.execute(
            """
            UPDATE distributor_policy_settings
            SET personalization_enabled = %s, policy_version = %s,
                updated_by = %s, updated_at = now()
            WHERE singleton_id = 1
            """,
            (enabled, version, updated_by),
        )
        after = load_document_in_transaction(conn)
        conn.execute(
            """
            INSERT INTO distributor_policy_audit(
                policy_version, action, changed_by, before_json, after_json
            ) VALUES (%s, 'update_report_personalization', %s, %s::jsonb, %s::jsonb)
            """,
            (
                version,
                updated_by,
                json.dumps(before),
                json.dumps(after),
            ),
        )

    return load_distributor_policy_document()
