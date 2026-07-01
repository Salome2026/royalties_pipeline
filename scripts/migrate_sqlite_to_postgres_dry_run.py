from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\royalties_pipeline")
DEFAULT_SQLITE = ROOT / "warehouse" / "booking" / "live" / "booking_live.sqlite"
DEFAULT_SCHEMA = ROOT / "database" / "postgres_schema_v1.sql"
DEFAULT_OUT_ROOT = ROOT / "migration_exports" / "cloud_postgres"


TABLE_MAP: dict[str, dict[str, Any]] = {
    "employees": {"target": "employees"},
    "employee_functions": {"target": "employee_functions"},
    "app_users": {"target": "app_users"},
    "app_modules": {"target": "app_modules"},
    "module_permissions": {"target": "module_permissions"},
    "app_audit_log": {"target": "app_audit_log"},
    "booking_artists": {"target": "artists"},
    "booking_shows": {"target": "booking_shows"},
    "booking_show_expenses": {"target": "booking_show_expenses"},
    "booking_movements": {"target": "booking_movements"},
    "booking_pre_split_adjustments": {"target": "booking_pre_split_adjustments"},
    "booking_direct_commissions": {"target": "booking_direct_commissions"},
    "booking_external_shares": {"target": "booking_external_shares"},
    "booking_artist_adjustments": {"target": "booking_artist_adjustments"},
    "booking_artist_ledger": {"target": "booking_artist_ledger"},
    "booking_composite_events": {"target": "booking_composite_events"},
    "booking_composite_event_expenses": {"target": "booking_composite_event_expenses"},
    "booking_composite_event_lines": {"target": "booking_composite_event_lines"},
    "caserio_events": {"target": "caserio_events"},
    "caserio_event_lines": {"target": "caserio_event_lines"},
    "finance_projects": {"target": "finance_projects"},
    "finance_staging_movements": {"target": "finance_movements"},
    "finance_recovery_applications": {"target": "finance_recovery_applications"},
}


REFERENCE_ONLY_SOURCE_TABLES = {}


JSON_COLUMNS = {
    "receipt_refs_json",
    "proof_refs_json",
    "before_json",
    "after_json",
    "scope_json",
    "config_json",
    "params_json",
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


def sqlite_tables(con: sqlite3.Connection) -> dict[str, list[str]]:
    tables = [
        row[0]
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    result: dict[str, list[str]] = {}
    for table in tables:
        result[table] = [row[1] for row in con.execute(f'PRAGMA table_info("{table}")')]
    return result


def parse_json_maybe(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    if text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def mapped_row(
    row: sqlite3.Row,
    source_cols: list[str],
    target_cols: list[str],
    renames: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = {col: row[col] for col in source_cols}
    reverse_renames = {target: source for source, target in renames.items()}
    out: dict[str, Any] = {}

    for col in target_cols:
        source_col = reverse_renames.get(col, col)
        if source_col in raw:
            value = raw[source_col]
            out[col] = parse_json_maybe(value) if col in JSON_COLUMNS else value
        elif col == "legacy_sqlite_id" and "id" in raw:
            out[col] = raw["id"]

    extras = {
        source: value
        for source, value in raw.items()
        if source not in set(target_cols) and renames.get(source) not in target_cols
    }
    return out, extras


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                    for key, value in row.items()
                }
            )


def derive_permission_scopes(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seq = 1
    for row in con.execute(
        "SELECT id, scope_json, created_at FROM module_permissions "
        "WHERE scope_json IS NOT NULL AND TRIM(scope_json) <> '' ORDER BY id"
    ):
        try:
            scopes = json.loads(row["scope_json"])
        except json.JSONDecodeError:
            scopes = []
        if not isinstance(scopes, list):
            continue
        for scope in scopes:
            if not isinstance(scope, dict):
                continue
            rows.append(
                {
                    "id": seq,
                    "permission_id": row["id"],
                    "scope_type": scope.get("scope_type") or "unknown",
                    "scope_ref": scope.get("scope_ref") or "",
                    "created_at": row["created_at"],
                }
            )
            seq += 1
    return rows


def run(args: argparse.Namespace) -> Path:
    sqlite_path = Path(args.sqlite)
    schema_path = Path(args.schema)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_OUT_ROOT / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    target_schema = parse_target_schema(schema_path)
    con = sqlite3.connect(sqlite_path)
    con.row_factory = sqlite3.Row
    source_schema = sqlite_tables(con)

    manifest: dict[str, Any] = {
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "mode": "dry_run",
        "sqlite_path": str(sqlite_path),
        "schema_path": str(schema_path),
        "out_dir": str(out_dir),
        "mapped_tables": [],
        "reference_only_tables": [],
        "unmapped_source_tables": [],
        "target_tables_without_source": [],
        "warnings": [],
    }

    used_targets: set[str] = set()
    for source_table, source_cols in sorted(source_schema.items()):
        if source_table in REFERENCE_ONLY_SOURCE_TABLES:
            count = con.execute(f'SELECT COUNT(*) FROM "{source_table}"').fetchone()[0]
            manifest["reference_only_tables"].append(
                {
                    "source_table": source_table,
                    "source_count": count,
                    "reason": REFERENCE_ONLY_SOURCE_TABLES[source_table],
                }
            )
            continue

        spec = TABLE_MAP.get(source_table)
        if not spec:
            count = con.execute(f'SELECT COUNT(*) FROM "{source_table}"').fetchone()[0]
            manifest["unmapped_source_tables"].append(
                {"source_table": source_table, "source_count": count, "source_columns": source_cols}
            )
            continue

        target_table = spec["target"]
        used_targets.add(target_table)
        target_cols = target_schema.get(target_table)
        if not target_cols:
            manifest["warnings"].append(f"Target table {target_table} not found for source {source_table}.")
            continue

        renames = spec.get("renames", {})
        source_count = con.execute(f'SELECT COUNT(*) FROM "{source_table}"').fetchone()[0]
        rows: list[dict[str, Any]] = []
        extras_seen: dict[str, int] = {}
        for row in con.execute(f'SELECT * FROM "{source_table}" ORDER BY id' if "id" in source_cols else f'SELECT * FROM "{source_table}"'):
            mapped, extras = mapped_row(row, source_cols, target_cols, renames)
            rows.append(mapped)
            for key in extras:
                extras_seen[key] = extras_seen.get(key, 0) + 1

        write_jsonl(out_dir / f"{target_table}.jsonl", rows)
        write_csv(out_dir / f"{target_table}.csv", rows[:1000])

        manifest["mapped_tables"].append(
            {
                "source_table": source_table,
                "target_table": target_table,
                "source_count": source_count,
                "exported_rows": len(rows),
                "source_columns": source_cols,
                "target_columns_used": sorted({key for row in rows for key in row}),
                "source_columns_not_loaded": sorted(extras_seen),
                "sample_csv": f"{target_table}.csv",
                "jsonl": f"{target_table}.jsonl",
            }
        )

    permission_scope_rows = derive_permission_scopes(con)
    if permission_scope_rows:
        target_table = "permission_scopes"
        used_targets.add(target_table)
        write_jsonl(out_dir / f"{target_table}.jsonl", permission_scope_rows)
        write_csv(out_dir / f"{target_table}.csv", permission_scope_rows[:1000])
        manifest["mapped_tables"].append(
            {
                "source_table": "module_permissions.scope_json",
                "target_table": target_table,
                "source_count": len(permission_scope_rows),
                "exported_rows": len(permission_scope_rows),
                "source_columns": ["module_permissions.id", "module_permissions.scope_json"],
                "target_columns_used": sorted({key for row in permission_scope_rows for key in row}),
                "source_columns_not_loaded": [],
                "sample_csv": f"{target_table}.csv",
                "jsonl": f"{target_table}.jsonl",
                "derived": True,
            }
        )

    for target_table in sorted(set(target_schema) - used_targets):
        if target_table == "schema_migrations":
            continue
        manifest["target_tables_without_source"].append(
            {
                "target_table": target_table,
                "target_columns": target_schema[target_table],
                "note": "Tabla nueva, seed/configuracion futura o derivacion pendiente.",
            }
        )

    totals = {
        "source_tables": len(source_schema),
        "target_tables": len(target_schema),
        "mapped_tables": len(manifest["mapped_tables"]),
        "reference_only_tables": len(manifest["reference_only_tables"]),
        "unmapped_source_tables": len(manifest["unmapped_source_tables"]),
        "target_tables_without_source": len(manifest["target_tables_without_source"]),
        "exported_rows": sum(item["exported_rows"] for item in manifest["mapped_tables"]),
    }
    manifest["totals"] = totals

    (out_dir / "migration_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    summary_lines = [
        "# Cloud Migration Dry Run",
        "",
        f"- Created at: {manifest['created_at']}",
        f"- SQLite: `{sqlite_path}`",
        f"- Target schema: `{schema_path}`",
        f"- Output: `{out_dir}`",
        "",
        "## Totals",
        "",
    ]
    summary_lines.extend(f"- {key}: {value}" for key, value in totals.items())
    summary_lines.extend(["", "## Manual Review", ""])
    if manifest["reference_only_tables"]:
        summary_lines.append("No hay tablas pendientes de decision. Las siguientes quedan solo como referencia:")
        for item in manifest["reference_only_tables"]:
            summary_lines.append(
                f"- `{item['source_table']}` ({item['source_count']} rows): {item['reason']}"
            )
    else:
        summary_lines.append("- No manual source tables.")
    summary_lines.extend(["", "## Target Tables Without Source", ""])
    for item in manifest["target_tables_without_source"]:
        summary_lines.append(f"- `{item['target_table']}`: {item['note']}")
    (out_dir / "migration_summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(json.dumps({"out_dir": str(out_dir), "totals": totals}, ensure_ascii=False, indent=2))
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a dry-run migration set from production SQLite to Postgres v1 shape.")
    parser.add_argument("--sqlite", default=str(DEFAULT_SQLITE))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--dry-run", action="store_true", help="Kept for readability; this script never writes to Postgres.")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
