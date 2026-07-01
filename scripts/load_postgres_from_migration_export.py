from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\royalties_pipeline")
DEFAULT_SCHEMA = ROOT / "database" / "postgres_schema_v1.sql"


LOAD_ORDER = [
    "employees",
    "employee_functions",
    "app_users",
    "app_modules",
    "module_permissions",
    "permission_scopes",
    "app_audit_log",
    "artists",
    "booking_shows",
    "booking_show_expenses",
    "booking_movements",
    "booking_pre_split_adjustments",
    "booking_direct_commissions",
    "booking_external_shares",
    "booking_artist_adjustments",
    "booking_artist_ledger",
    "booking_composite_events",
    "booking_composite_event_expenses",
    "booking_composite_event_lines",
    "caserio_events",
    "caserio_event_lines",
    "finance_projects",
    "finance_movements",
    "finance_recovery_applications",
]

BOOLEAN_COLUMNS = {
    "active",
    "must_change_password",
    "can_access",
    "can_create",
    "can_view_history",
    "can_edit",
    "can_approve",
    "cash_handled_by_vpo",
    "booking_commission_exempt",
    "recoverable",
    "recovery_auto_apply",
    "include_in_cash_view",
    "include_in_catalog_view",
    "include_in_statement_view",
}


def parse_target_schema(schema_path: Path) -> dict[str, list[str]]:
    sql = schema_path.read_text(encoding="utf-8")
    tables: dict[str, list[str]] = {}
    pattern = re.compile(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)\s*\((.*?)\);",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(sql):
        table = match.group(1)
        body = match.group(2)
        cols: list[str] = []
        for raw_line in body.splitlines():
            line = raw_line.strip().rstrip(",")
            if not line:
                continue
            upper = line.upper()
            if upper.startswith(("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK")):
                continue
            cols.append(line.split()[0].strip('"'))
        tables[table] = cols
    return tables


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def normalize_for_postgres(col: str, value: Any) -> Any:
    if col not in BOOLEAN_COLUMNS or value is None:
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "t", "yes", "y", "si", "sí"}:
            return True
        if text in {"0", "false", "f", "no", "n"}:
            return False
    return value


def validate_export(export_dir: Path, schema_path: Path) -> dict[str, Any]:
    manifest_path = export_dir / "migration_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing migration_manifest.json in {export_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = parse_target_schema(schema_path)

    report: dict[str, Any] = {
        "export_dir": str(export_dir),
        "schema_path": str(schema_path),
        "tables": [],
        "warnings": [],
        "total_rows": 0,
    }

    for table in LOAD_ORDER:
        jsonl = export_dir / f"{table}.jsonl"
        rows = read_jsonl(jsonl)
        if not rows:
            report["tables"].append({"table": table, "rows": 0, "status": "empty_or_missing"})
            continue
        target_cols = set(schema.get(table, []))
        row_cols = {key for row in rows for key in row}
        unknown_cols = sorted(row_cols - target_cols)
        missing_schema = table not in schema
        status = "ok"
        if missing_schema or unknown_cols:
            status = "needs_review"
            report["warnings"].append(
                {"table": table, "missing_schema": missing_schema, "unknown_cols": unknown_cols}
            )
        report["tables"].append(
            {
                "table": table,
                "rows": len(rows),
                "status": status,
                "columns": sorted(row_cols),
            }
        )
        report["total_rows"] += len(rows)

    reference_only = manifest.get("reference_only_tables", [])
    if reference_only:
        report["reference_only_tables"] = reference_only
    manual = manifest.get("manual_tables", [])
    if manual:
        report["manual_tables"] = manual
    return report


def load_to_postgres(export_dir: Path, schema_path: Path, database_url: str, reset: bool) -> None:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise SystemExit(
            "psycopg is required to load Postgres. Install psycopg[binary] before using --apply."
        ) from exc

    schema_sql = schema_path.read_text(encoding="utf-8")
    validation = validate_export(export_dir, schema_path)
    warnings = validation.get("warnings") or []
    if warnings:
        raise SystemExit(f"Export validation has warnings; refusing to load: {warnings}")

    with psycopg.connect(database_url) as con:
        with con.cursor() as cur:
            if reset:
                cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
            cur.execute(schema_sql)
            for table in LOAD_ORDER:
                rows = read_jsonl(export_dir / f"{table}.jsonl")
                if not rows:
                    continue
                cols = sorted({key for row in rows for key in row})
                placeholders = ", ".join(["%s"] * len(cols))
                col_sql = ", ".join(f'"{col}"' for col in cols)
                sql = f'INSERT INTO "{table}" ({col_sql}) VALUES ({placeholders})'
                values = []
                for row in rows:
                    values.append(
                        [
                            Jsonb(row.get(col))
                            if isinstance(row.get(col), (dict, list))
                            else normalize_for_postgres(col, row.get(col))
                            for col in cols
                        ]
                    )
                cur.executemany(sql, values)
            for table in LOAD_ORDER:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = %s
                      AND column_default LIKE 'nextval%%'
                    """,
                    (table,),
                )
                serial_cols = [row[0] for row in cur.fetchall()]
                for col in serial_cols:
                    cur.execute(
                        f"""
                        SELECT setval(
                            pg_get_serial_sequence(%s, %s),
                            COALESCE((SELECT MAX("{col}") FROM "{table}"), 1),
                            true
                        )
                        """,
                        (table, col),
                    )
        con.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate or load a migration export into a Postgres database.")
    parser.add_argument("export_dir", help="Path to migration export folder.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--database-url", default=os.environ.get("VPO_CLOUDSQL_URL", ""))
    parser.add_argument("--apply", action="store_true", help="Actually write to Postgres.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate public schema before loading.")
    args = parser.parse_args()

    export_dir = Path(args.export_dir)
    schema_path = Path(args.schema)
    report = validate_export(export_dir, schema_path)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    if not args.apply:
        return
    if not args.database_url:
        raise SystemExit("Missing --database-url or VPO_CLOUDSQL_URL.")
    load_to_postgres(export_dir, schema_path, args.database_url, reset=args.reset)


if __name__ == "__main__":
    main()
