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
    "CREATE TABLE IF NOT EXISTS",
    "AUTOINCREMENT",
)


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
