"""Postgres-only operational state for isolated royalty workspaces."""
from __future__ import annotations
import json
from typing import Any
from app.operational_db import operational_connect, operational_db_settings

def require_postgres() -> None:
    if operational_db_settings().driver != 'postgres':
        raise RuntimeError('Los ámbitos de regalías usan exclusivamente Cloud SQL Postgres.')

def json_value(value):
    return json.loads(value) if isinstance(value, str) else value

def settings() -> dict[str, Any]:
    require_postgres()
    with operational_connect() as conn:
        installed = conn.execute("SELECT to_regclass('royalty_workspaces') AS name").fetchone()
        if not installed or not installed['name']:
            return {'scope': 'wml', 'enabled': False, 'installed': False, 'version': 0,
                    'config': {'frequency': 'semiannual', 'delivery_lag_months': 3}}
        row = conn.execute("SELECT * FROM royalty_workspaces WHERE scope_key='wml'").fetchone()
    if not row:
        raise RuntimeError('Falta la configuración WML en Cloud SQL.')
    return {'scope': 'wml', 'installed': True, 'enabled': bool(row['enabled']),
            'version': int(row['version']), 'config': json_value(row['config']),
            'updated_by': row['updated_by'], 'updated_at': row['updated_at'].isoformat()}

def update_settings(*, enabled: bool, actor: str, expected_version: int,
                    delivery_lag_months: int | None = None) -> dict:
    require_postgres()
    if delivery_lag_months is not None and not 0 <= delivery_lag_months <= 6:
        raise ValueError('El plazo semestral debe estar entre 0 y 6 meses.')
    with operational_connect() as conn:
        row = conn.execute("SELECT * FROM royalty_workspaces WHERE scope_key='wml' FOR UPDATE").fetchone()
        if not row or int(row['version']) != expected_version:
            raise ValueError('La configuración cambió. Actualizá la pantalla.')
        config = dict(json_value(row['config']))
        if delivery_lag_months is not None:
            config['delivery_lag_months'] = delivery_lag_months
        if bool(row['enabled']) != enabled or config != json_value(row['config']):
            version = expected_version + 1
            conn.execute("UPDATE royalty_workspaces SET enabled=%s,config=%s::jsonb,version=%s,updated_by=%s,updated_at=now() WHERE scope_key='wml'",
                         (enabled, json.dumps(config), version, actor))
            conn.execute("INSERT INTO royalty_workspace_audit(scope_key,record_type,record_key,version,before_json,after_json,changed_by) VALUES ('wml','settings','wml',%s,%s::jsonb,%s::jsonb,%s)",
                (version, json.dumps({'enabled': bool(row['enabled']), 'config': json_value(row['config'])}),
                 json.dumps({'enabled': enabled, 'config': config}), actor))
    return settings()

def merge_config(changes: dict, *, actor: str, claim: str | None = None, run_token: str | None = None) -> dict:
    """Atomic publication/processing metadata; never changes the enabled flag."""
    require_postgres()
    with operational_connect() as conn:
        row=conn.execute("SELECT * FROM royalty_workspaces WHERE scope_key='wml' FOR UPDATE").fetchone()
        if not row:raise RuntimeError('Primero instalá la migración WML en Cloud SQL.')
        before=dict(json_value(row['config'])); after={**before,**changes}
        if claim and before.get('processing_status') in {'queued','running'}:
            raise ValueError('WML ya tiene un procesamiento en curso.')
        if run_token and before.get('run_token') != run_token:
            raise ValueError('Este procesamiento WML ya no es el vigente.')
        version=int(row['version'])+1
        conn.execute("UPDATE royalty_workspaces SET config=%s::jsonb,version=%s,updated_by=%s,updated_at=now() WHERE scope_key='wml'",(json.dumps(after),version,actor))
        conn.execute("INSERT INTO royalty_workspace_audit(scope_key,record_type,record_key,version,before_json,after_json,changed_by) VALUES ('wml','processing','wml',%s,%s::jsonb,%s::jsonb,%s)",(version,json.dumps(before),json.dumps(after),actor))
    return settings()

def records(record_type: str, *, conn=None) -> dict[str, dict]:
    require_postgres()
    if conn is None:
        with operational_connect() as opened:
            return records(record_type, conn=opened)
    rows = conn.execute("SELECT * FROM royalty_workspace_records WHERE scope_key='wml' AND record_type=%s", (record_type,)).fetchall()
    return {r['record_key']: {'payload': json_value(r['payload_json']), 'version': int(r['version']),
            'updated_by': r['updated_by'], 'updated_at': r['updated_at'].isoformat()} for r in rows}

def save_record(record_type: str, key: str, payload: dict, *, expected_version: int, actor: str, conn=None) -> dict:
    require_postgres()
    if record_type not in {'master_split', 'catalog_status', 'reference'}:
        raise ValueError('Tipo de registro inválido.')
    if conn is None:
        with operational_connect() as opened:
            return save_record(record_type,key,payload,expected_version=expected_version,actor=actor,conn=opened)
    # Lock the workspace to serialize inserts as well as updates.
    conn.execute("SELECT scope_key FROM royalty_workspaces WHERE scope_key='wml' FOR UPDATE").fetchone()
    row = conn.execute("SELECT * FROM royalty_workspace_records WHERE scope_key='wml' AND record_type=%s AND record_key=%s", (record_type,key)).fetchone()
    if (int(row['version']) if row else 0) != expected_version:
        raise ValueError('La ficha cambió. Actualizala antes de guardar.')
    version = expected_version + 1
    encoded = json.dumps(payload,ensure_ascii=False)
    conn.execute("""INSERT INTO royalty_workspace_records(scope_key,record_type,record_key,payload_json,version,updated_by)
        VALUES ('wml',%s,%s,%s::jsonb,%s,%s) ON CONFLICT(scope_key,record_type,record_key)
        DO UPDATE SET payload_json=EXCLUDED.payload_json,version=EXCLUDED.version,updated_by=EXCLUDED.updated_by,updated_at=now()""",
        (record_type,key,encoded,version,actor))
    conn.execute("INSERT INTO royalty_workspace_audit(scope_key,record_type,record_key,version,before_json,after_json,changed_by) VALUES ('wml',%s,%s,%s,%s::jsonb,%s::jsonb,%s)",
        (record_type,key,version,json.dumps(json_value(row['payload_json'])) if row else None,encoded,actor))
    return records(record_type,conn=conn)[key]
