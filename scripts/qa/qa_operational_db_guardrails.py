from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WATCHED_FILES = {
    "app/vpo_corp_api.py",
    "app/operational_db.py",
    "database/postgres_schema_v1.sql",
}
SQLITE_EXPANSION_MARKERS = (
    "ensure_sqlite_column(",
    "sqlite3.connect(",
    "AUTOINCREMENT",
)
POSTGRES_SCHEMA_FILE = "database/postgres_schema_v1.sql"
APP_FILE = "app/vpo_corp_api.py"


def git_diff_cached_or_worktree() -> str:
    cached = subprocess.run(
        ["git", "diff", "--cached", "--", *WATCHED_FILES],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    worktree = subprocess.run(
        ["git", "diff", "--", *WATCHED_FILES],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    return cached + "\n" + worktree


def create_table_has_postgres_guard(file_name: str, added_line: str) -> bool:
    if file_name != APP_FILE:
        return False
    lines = (ROOT / file_name).read_text(encoding="utf-8").splitlines()
    target = added_line.strip()
    for index, line in enumerate(lines):
        if line.strip() != target:
            continue
        function_start = index
        while function_start >= 0 and not lines[function_start].startswith("def "):
            function_start -= 1
        if function_start < 0:
            continue
        function_prefix = "\n".join(lines[function_start:index])
        if "if not is_postgres_connection(conn):" in function_prefix and "raise HTTPException" in function_prefix:
            return True
    return False


def main() -> int:
    diff = git_diff_cached_or_worktree()
    offenders: list[str] = []
    current_file = ""
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line.removeprefix("+++ b/")
            continue
        if current_file not in WATCHED_FILES:
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        added_line = line[1:].strip()
        if current_file != POSTGRES_SCHEMA_FILE and "CREATE TABLE IF NOT EXISTS" in line:
            if create_table_has_postgres_guard(current_file, added_line):
                continue
            offenders.append(f"{current_file}: {line[1:].strip()}")
            continue
        if any(marker in line for marker in SQLITE_EXPANSION_MARKERS):
            offenders.append(f"{current_file}: {line[1:].strip()}")

    if offenders:
        print("ERROR: posible expansion SQLite en cambio operativo nuevo.")
        print("Regla vigente: modulo nuevo operativo = Postgres-only.")
        print("Revisar docs/production_guardrails.md antes de continuar.\n")
        for offender in offenders:
            print(f"- {offender}")
        return 1

    print("OK: no se detectaron ramas SQLite nuevas en el diff operativo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
