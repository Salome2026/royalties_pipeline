from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterator, Sequence


BASE = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_PATH = BASE / "warehouse" / "booking" / "live" / "booking_live.sqlite"


class OperationalDbConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class OperationalDbSettings:
    driver: str
    sqlite_path: Path
    postgres_mode: str
    database_name: str
    user: str
    password_configured: bool
    cloudsql_connection_name: str
    local_proxy_host: str
    local_proxy_port: int
    allow_direct_tcp: bool

    @property
    def safe_summary(self) -> dict[str, str]:
        return {
            "driver": self.driver,
            "sqlite_path": str(self.sqlite_path) if self.driver == "sqlite" else "",
            "postgres_mode": self.postgres_mode if self.driver == "postgres" else "",
            "database_name": self.database_name if self.driver == "postgres" else "",
            "user": self.user if self.driver == "postgres" else "",
            "password_configured": "yes" if self.password_configured else "no",
            "cloudsql_connection_name": self.cloudsql_connection_name if self.driver == "postgres" else "",
            "local_proxy": f"{self.local_proxy_host}:{self.local_proxy_port}" if self.driver == "postgres" else "",
            "direct_tcp_allowed": "yes" if self.allow_direct_tcp else "no",
        }


def operational_db_settings() -> OperationalDbSettings:
    driver = os.environ.get("VPO_OPERATIONAL_DB_DRIVER", "postgres").strip().lower()
    if driver not in {"sqlite", "postgres"}:
        raise OperationalDbConfigError("VPO_OPERATIONAL_DB_DRIVER must be sqlite or postgres.")
    if driver == "sqlite" and os.environ.get("VPO_ALLOW_LEGACY_SQLITE_OPERATIONAL", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise OperationalDbConfigError(
            "SQLite operational mode is frozen/legacy. Set "
            "VPO_ALLOW_LEGACY_SQLITE_OPERATIONAL=1 only for controlled historical access/audit."
        )

    sqlite_path = Path(os.environ.get("VPO_BOOKING_DB_PATH", DEFAULT_SQLITE_PATH)).expanduser()
    postgres_mode = os.environ.get("VPO_POSTGRES_CONNECT_MODE", "cloudsql_socket").strip().lower()
    if postgres_mode not in {"cloudsql_socket", "local_proxy", "direct_tcp"}:
        raise OperationalDbConfigError(
            "VPO_POSTGRES_CONNECT_MODE must be cloudsql_socket, local_proxy or direct_tcp."
        )

    database_name = os.environ.get("VPO_OPERATIONAL_DB_NAME", "vpo_corp").strip()
    user = os.environ.get("VPO_OPERATIONAL_DB_USER", "postgres").strip()
    password = os.environ.get("VPO_OPERATIONAL_DB_PASSWORD", "")
    connection_name = os.environ.get("VPO_CLOUDSQL_CONNECTION_NAME", "").strip()
    proxy_host = os.environ.get("VPO_POSTGRES_LOCAL_PROXY_HOST", "127.0.0.1").strip()
    proxy_port = int(os.environ.get("VPO_POSTGRES_LOCAL_PROXY_PORT", "5432"))
    allow_direct_tcp = os.environ.get("VPO_ALLOW_DIRECT_POSTGRES_TCP", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    return OperationalDbSettings(
        driver=driver,
        sqlite_path=sqlite_path,
        postgres_mode=postgres_mode,
        database_name=database_name,
        user=user,
        password_configured=bool(password),
        cloudsql_connection_name=connection_name,
        local_proxy_host=proxy_host,
        local_proxy_port=proxy_port,
        allow_direct_tcp=allow_direct_tcp,
    )


def _postgres_connect_params(settings: OperationalDbSettings) -> dict[str, Any]:
    password = os.environ.get("VPO_OPERATIONAL_DB_PASSWORD", "")
    if not password:
        raise OperationalDbConfigError("VPO_OPERATIONAL_DB_PASSWORD is required for postgres.")

    params: dict[str, Any] = {
        "dbname": settings.database_name,
        "user": settings.user,
        "password": password,
        "connect_timeout": int(os.environ.get("VPO_POSTGRES_CONNECT_TIMEOUT", "10")),
    }

    if settings.postgres_mode == "cloudsql_socket":
        if not settings.cloudsql_connection_name:
            raise OperationalDbConfigError(
                "VPO_CLOUDSQL_CONNECTION_NAME is required when VPO_POSTGRES_CONNECT_MODE=cloudsql_socket."
            )
        params["host"] = f"/cloudsql/{settings.cloudsql_connection_name}"
        return params

    if settings.postgres_mode == "local_proxy":
        if settings.local_proxy_host not in {"127.0.0.1", "localhost", "::1"}:
            raise OperationalDbConfigError("local_proxy mode only allows localhost proxy hosts.")
        params["host"] = settings.local_proxy_host
        params["port"] = settings.local_proxy_port
        return params

    if settings.postgres_mode == "direct_tcp":
        if not settings.allow_direct_tcp:
            raise OperationalDbConfigError(
                "direct_tcp is blocked by default. Use Cloud SQL socket/proxy, or set "
                "VPO_ALLOW_DIRECT_POSTGRES_TCP=1 only for a short controlled migration."
            )
        host = os.environ.get("VPO_POSTGRES_HOST", "").strip()
        if not host:
            raise OperationalDbConfigError("VPO_POSTGRES_HOST is required for direct_tcp.")
        params["host"] = host
        params["port"] = int(os.environ.get("VPO_POSTGRES_PORT", "5432"))
        params["sslmode"] = os.environ.get("VPO_POSTGRES_SSLMODE", "require")
        return params

    raise OperationalDbConfigError(f"Unsupported postgres mode: {settings.postgres_mode}")


def is_postgres_connection(conn: Any) -> bool:
    module = type(conn).__module__
    return module.startswith("psycopg") or type(conn).__name__ == "PostgresSqliteCompatConnection"


def db_sql(conn: Any, sql: str) -> str:
    if is_postgres_connection(conn):
        return sql.replace("?", "%s")
    return sql


def db_bool(value: bool) -> Any:
    return bool(value)


POSTGRES_BOOLEAN_COMPAT_COLUMNS = {
    "active",
    "must_change_password",
    "can_access",
    "can_create",
    "can_view_history",
    "can_edit",
    "can_approve",
    "booking_commission_exempt",
    "recovery_auto_apply",
    "cash_handled_by_vpo",
    "recoverable",
    "include_in_reports",
    "include_in_cash_view",
    "include_in_catalog_view",
    "include_in_statement_view",
}


def _split_sql_columns(raw: str) -> list[str]:
    return [part.strip().strip('"') for part in raw.split(",") if part.strip()]


def _postgres_sqlite_compat_params(sql: str, params: Sequence[Any]) -> tuple[Any, ...]:
    values = list(params)
    insert_match = re.search(
        r"^\s*INSERT\s+INTO\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\((.*?)\)\s*VALUES\s*\(",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if insert_match:
        columns = _split_sql_columns(insert_match.group(1))
        for index, column in enumerate(columns[: len(values)]):
            if column.lower() in POSTGRES_BOOLEAN_COMPAT_COLUMNS and values[index] is not None:
                values[index] = bool(values[index])
        return tuple(values)

    update_match = re.search(
        r"^\s*UPDATE\s+[a-zA-Z_][a-zA-Z0-9_]*\s+SET\s+(.*?)\s+WHERE\s+",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if update_match:
        assignments = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\?", update_match.group(1))
        for index, column in enumerate(assignments[: len(values)]):
            if column.lower() in POSTGRES_BOOLEAN_COMPAT_COLUMNS and values[index] is not None:
                values[index] = bool(values[index])
    return tuple(values)


def _postgres_sqlite_compat_sql(sql: str) -> str:
    translated = sql.replace("?", "%s")
    translated = re.sub(r"%(?![sbt%])", "%%", translated)
    insert_ignore = re.match(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", translated, flags=re.IGNORECASE)
    if insert_ignore:
        translated = re.sub(
            r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+",
            "INSERT INTO ",
            translated,
            count=1,
            flags=re.IGNORECASE,
        )
        if "ON CONFLICT" not in translated.upper():
            translated = translated.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    translated = re.sub(r"\bbooking_artists\b", "artists", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bfinance_staging_movements\b", "finance_movements", translated, flags=re.IGNORECASE)
    for column in POSTGRES_BOOLEAN_COMPAT_COLUMNS:
        translated = re.sub(
            rf"COALESCE\(\s*{column}\s*,\s*0\s*\)\s*=\s*1\b",
            f"COALESCE({column}, FALSE) = TRUE",
            translated,
            flags=re.IGNORECASE,
        )
        translated = re.sub(
            rf"COALESCE\(\s*{column}\s*,\s*0\s*\)\s*=\s*0\b",
            f"COALESCE({column}, FALSE) = FALSE",
            translated,
            flags=re.IGNORECASE,
        )
        translated = re.sub(
            rf"COALESCE\(\s*{column}\s*,\s*0\s*\)",
            f"COALESCE({column}, FALSE)",
            translated,
            flags=re.IGNORECASE,
        )
        translated = re.sub(rf"\b{column}\s*=\s*1\b", f"{column} = TRUE", translated, flags=re.IGNORECASE)
        translated = re.sub(rf"\b{column}\s*=\s*0\b", f"{column} = FALSE", translated, flags=re.IGNORECASE)
    translated = re.sub(
        r"substr\(\s*show_date\s*,\s*1\s*,\s*7\s*\)",
        "to_char(show_date, 'YYYY-MM')",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"GROUP_CONCAT\(\s*DISTINCT\s+(CASE\b.*?\bEND)\s*\)",
        r"STRING_AGG(DISTINCT \1, ', ')",
        translated,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return translated


class PostgresSqliteCompatCursor:
    def __init__(self, cursor: Any, lastrowid: int | None = None) -> None:
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self) -> Any:
        return self._normalize_row(self._cursor.fetchone())

    def fetchall(self) -> list[Any]:
        return [self._normalize_row(row) for row in self._cursor.fetchall()]

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def __iter__(self) -> Any:
        return (self._normalize_row(row) for row in self._cursor)

    @staticmethod
    def _normalize_row(row: Any) -> Any:
        if not isinstance(row, dict):
            return row
        return {
            key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
            for key, value in row.items()
        }


class PostgresSqliteCompatConnection:
    """Small adapter for legacy operational routes while Cloud SQL is the real DB."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> PostgresSqliteCompatCursor:
        translated = _postgres_sqlite_compat_sql(sql)
        prepared_params = _postgres_sqlite_compat_params(sql, tuple(params or ()))
        cursor = self._conn.execute(translated, prepared_params)
        return PostgresSqliteCompatCursor(cursor, self._last_insert_id(sql))

    def executemany(self, sql: str, params_seq: Sequence[Sequence[Any]]) -> PostgresSqliteCompatCursor:
        translated = _postgres_sqlite_compat_sql(sql)
        cursor = self._conn.executemany(translated, params_seq)
        return PostgresSqliteCompatCursor(cursor)

    def _last_insert_id(self, sql: str) -> int | None:
        translated = _postgres_sqlite_compat_sql(sql)
        match = re.search(r"^\s*INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", translated, flags=re.IGNORECASE)
        if not match:
            return None
        table_name = match.group(1)
        sequence_row = self._conn.execute(
            "SELECT pg_get_serial_sequence(%s, 'id') AS sequence_name",
            (table_name,),
        ).fetchone()
        sequence_name = sequence_row["sequence_name"] if sequence_row else None
        if not sequence_name:
            return None
        row = self._conn.execute("SELECT currval(%s::regclass) AS id", (sequence_name,)).fetchone()
        return int(row["id"]) if row and row["id"] is not None else None


@contextmanager
def operational_connect() -> Iterator[Any]:
    settings = operational_db_settings()
    if settings.driver == "sqlite":
        settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(settings.sqlite_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise OperationalDbConfigError("psycopg[binary] is required for postgres operational DB.") from exc

    params = _postgres_connect_params(settings)
    conn = psycopg.connect(**params, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def operational_sqlite_compatible_connect() -> Iterator[Any]:
    with operational_connect() as conn:
        if is_postgres_connection(conn):
            yield PostgresSqliteCompatConnection(conn)
        else:
            yield conn


def operational_db_healthcheck() -> dict[str, str]:
    try:
        settings = operational_db_settings()
        payload = settings.safe_summary
        with operational_connect() as conn:
            cursor = conn.execute("SELECT 1 AS ok")
            row = cursor.fetchone()
            ok_value = row["ok"] if isinstance(row, dict) else row[0]
            payload["status"] = "ok" if int(ok_value) == 1 else "unexpected"
    except Exception as exc:
        payload = {
            "driver": os.environ.get("VPO_OPERATIONAL_DB_DRIVER", "postgres").strip().lower(),
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    return payload
