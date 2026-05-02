from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path

import duckdb


BASE = Path(r"C:\royalties_pipeline")

DETAIL_PATH = BASE / "warehouse" / "detail" / "royalties_detail.parquet"
PROCESSED_FILES_PATH = BASE / "warehouse" / "registry" / "processed_files.parquet"
EXCHANGE_RATES_PATH = BASE / "warehouse" / "registry" / "exchange_rates.parquet"
SONG_LEVEL_REGISTRY_PATH = BASE / "warehouse" / "registry" / "song_level_registry.parquet"

MARTS_DIR = BASE / "warehouse" / "marts"
STAGING_DIR = BASE / "staging"
REPORTS_DIR = BASE / "reports"

PROTECTED_PATHS = {
    BASE / "input_raw",
    BASE / "docs",
    BASE / "_cleanup_archive",
    EXCHANGE_RATES_PATH,
}

MART_FILES_BY_SOURCE = {
    "fuga": [
        "standardized_raw_fuga.parquet",
        "song_level_fuga.parquet",
    ],
    "dashgo": [
        "standardized_raw_dashgo.parquet",
        "song_level_dashgo.parquet",
    ],
    "orchard": [
        "standardized_raw_orchard.parquet",
        "song_level_orchard.parquet",
    ],
    "onerpm": [
        "standardized_raw_onerpm.parquet",
        "song_level_onerpm.parquet",
    ],
    "soundon": [
        "standardized_raw_soundon.parquet",
        "song_level_soundon.parquet",
    ],
}

CONSOLIDATED_MART_FILES = [
    "standardized_raw_all_sources.parquet",
    "song_level_all_sources.parquet",
    "catalog_candidates.parquet",
]


@dataclass
class Action:
    kind: str
    path: Path
    description: str


def is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def is_protected(path: Path) -> bool:
    resolved = path.resolve()
    for protected in PROTECTED_PATHS:
        protected_resolved = protected.resolve()
        if resolved == protected_resolved or is_inside(resolved, protected_resolved):
            return True
    return False


def parquet_count(path: Path) -> int | None:
    if not path.exists():
        return None

    con = duckdb.connect()
    try:
        return con.execute(
            "SELECT COUNT(*) FROM read_parquet(?)",
            [str(path)],
        ).fetchone()[0]
    finally:
        con.close()


def matching_count(path: Path, source: str | None, account: str | None) -> int:
    if not path.exists():
        return 0

    where_parts = []
    params: list[str] = []

    if source:
        where_parts.append("source = ?")
        params.append(source)

    if account:
        where_parts.append("account = ?")
        params.append(account)

    if not where_parts:
        return parquet_count(path) or 0

    con = duckdb.connect()
    try:
        return con.execute(
            f"""
            SELECT COUNT(*)
            FROM read_parquet(?)
            WHERE {" AND ".join(where_parts)}
            """,
            [str(path), *params],
        ).fetchone()[0]
    finally:
        con.close()


def filter_parquet(path: Path, source: str | None, account: str | None) -> int:
    if not path.exists():
        return 0

    where_parts = []
    params: list[str] = []

    if source:
        where_parts.append("source = ?")
        params.append(source)

    if account:
        where_parts.append("account = ?")
        params.append(account)

    if not where_parts:
        deleted = parquet_count(path) or 0
        path.unlink()
        return deleted

    con = duckdb.connect()
    temp_path = path.with_name(f"{path.stem}.reset_tmp{path.suffix}")

    try:
        before = parquet_count(path) or 0
        con.execute(
            f"""
            COPY (
                SELECT *
                FROM read_parquet(?)
                WHERE NOT ({" AND ".join(where_parts)})
            )
            TO ?
            (FORMAT PARQUET)
            """,
            [str(path), *params, str(temp_path)],
        )
        path.unlink()
        temp_path.replace(path)
        after = parquet_count(path) or 0
        return before - after
    finally:
        con.close()
        if temp_path.exists():
            temp_path.unlink()


def add_existing_file(actions: list[Action], path: Path, description: str) -> None:
    if path.exists():
        actions.append(Action("delete_file", path, description))


def add_matching_files(actions: list[Action], root: Path, pattern: str, description: str) -> None:
    if not root.exists():
        return

    for path in sorted(root.rglob(pattern)):
        if path.is_file():
            actions.append(Action("delete_file", path, description))


def old_detail_actions(source: str | None, account: str | None) -> list[Action]:
    if not source and not account:
        return [
            Action("delete_file", DETAIL_PATH, "delete old detail parquet"),
            Action("delete_file", PROCESSED_FILES_PATH, "delete processed files registry"),
        ]

    return [
        Action("filter_parquet", DETAIL_PATH, "filter old detail rows"),
        Action("filter_parquet", PROCESSED_FILES_PATH, "filter processed files registry rows"),
    ]


def marts_actions(source: str | None) -> list[Action]:
    actions: list[Action] = []

    if source:
        for filename in MART_FILES_BY_SOURCE.get(source, []):
            add_existing_file(actions, MARTS_DIR / filename, f"delete {source} mart")

        for filename in CONSOLIDATED_MART_FILES:
            add_existing_file(actions, MARTS_DIR / filename, "delete consolidated mart for rebuild")

        if source == "onerpm":
            actions.append(Action("filter_parquet", SONG_LEVEL_REGISTRY_PATH, "filter ONErpm song-level registry rows"))

        return actions

    for filenames in MART_FILES_BY_SOURCE.values():
        for filename in filenames:
            add_existing_file(actions, MARTS_DIR / filename, "delete source mart")

    for filename in CONSOLIDATED_MART_FILES:
        add_existing_file(actions, MARTS_DIR / filename, "delete consolidated mart")

    add_existing_file(actions, SONG_LEVEL_REGISTRY_PATH, "delete song-level registry")
    return actions


def staging_actions(source: str | None, account: str | None) -> list[Action]:
    actions: list[Action] = []
    if not STAGING_DIR.exists():
        return actions

    if not source and not account:
        for path in sorted(STAGING_DIR.iterdir()):
            actions.append(Action("delete_tree", path, "delete staging item"))
        return actions

    keywords = [value.lower() for value in [source, account] if value]
    for path in sorted(STAGING_DIR.rglob("*")):
        path_text = str(path).lower()
        if any(keyword in path_text for keyword in keywords):
            actions.append(Action("delete_tree" if path.is_dir() else "delete_file", path, "delete matching staging item"))

    return actions


def reports_actions(source: str | None) -> list[Action]:
    actions: list[Action] = []

    if not REPORTS_DIR.exists():
        return actions

    if source:
        add_matching_files(actions, REPORTS_DIR, f"*{source}*", "delete matching report")
        for filename in [
            "reporte_ingresos_digitales_por_mes_de_statement.xlsx",
            "reporte_ingresos_digitales_por_mes_de_statement_marts.xlsx",
            "catalog_candidates_review.xlsx",
        ]:
            add_existing_file(actions, REPORTS_DIR / filename, "delete derived report for rebuild")
        return actions

    add_matching_files(actions, REPORTS_DIR, "*.xlsx", "delete generated report")
    add_matching_files(actions, REPORTS_DIR, "*.csv", "delete generated report")
    return actions


def collect_actions(scope: str, source: str | None, account: str | None) -> list[Action]:
    actions: list[Action] = []

    scopes = ["old-detail", "marts", "staging", "reports"] if scope == "all" else [scope]

    for item in scopes:
        if item == "old-detail":
            actions.extend(old_detail_actions(source, account))
        elif item == "marts":
            actions.extend(marts_actions(source))
        elif item == "staging":
            actions.extend(staging_actions(source, account))
        elif item == "reports":
            actions.extend(reports_actions(source))

    unique: dict[Path, Action] = {}
    for action in actions:
        unique[action.path] = action

    return list(unique.values())


def describe_action(action: Action, source: str | None, account: str | None) -> str:
    if action.kind == "filter_parquet":
        count = matching_count(action.path, source, account)
        return f"FILTER {action.path} | matching rows: {count} | {action.description}"

    exists = action.path.exists()
    return f"DELETE {action.path} | exists: {exists} | {action.description}"


def execute_action(action: Action, source: str | None, account: str | None) -> str:
    if is_protected(action.path):
        return f"SKIPPED protected path: {action.path}"

    if action.kind == "filter_parquet":
        deleted = filter_parquet(action.path, source, account)
        return f"FILTERED {action.path} | deleted rows: {deleted}"

    if not action.path.exists():
        return f"SKIPPED missing path: {action.path}"

    if action.kind == "delete_tree":
        if action.path.is_dir():
            shutil.rmtree(action.path)
            return f"DELETED DIR {action.path}"
        action.path.unlink()
        return f"DELETED FILE {action.path}"

    if action.kind == "delete_file":
        if action.path.is_dir():
            return f"SKIPPED expected file but found dir: {action.path}"
        action.path.unlink()
        return f"DELETED FILE {action.path}"

    return f"SKIPPED unknown action {action.kind}: {action.path}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reset seguro de datos generados del royalties pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Scopes:
  old-detail   Limpia royalties_detail + processed_files del pipeline viejo.
  marts        Limpia standardized_raw/song_level/consolidados del pipeline nuevo.
  staging      Limpia archivos temporales regenerables.
  reports      Limpia reportes generados.
  all          Limpia old-detail + marts + staging + reports.

Ejemplos:
  python reset_pipeline_data.py --scope old-detail --source fuga --account indyana_records
  python reset_pipeline_data.py --scope marts --source dashgo
  python reset_pipeline_data.py --scope staging --apply
  python reset_pipeline_data.py --scope all --apply

Seguridad:
  Por defecto es DRY RUN: solo muestra lo que haria.
  Para ejecutar realmente hay que agregar --apply.
  Nunca toca input_raw, docs, exchange_rates ni _cleanup_archive.
""",
    )
    parser.add_argument(
        "--scope",
        choices=["old-detail", "marts", "staging", "reports", "all"],
        required=True,
        help="Zona de datos generados que queres limpiar.",
    )
    parser.add_argument("--source", help="Fuente a resetear, por ejemplo fuga, dashgo, orchard, onerpm, soundon.")
    parser.add_argument("--account", help="Cuenta a resetear, por ejemplo indyana_records o mawzrecords.")
    parser.add_argument("--apply", action="store_true", help="Ejecuta los cambios. Sin esto solo muestra un dry-run.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    source = args.source.strip().lower() if args.source else None
    account = args.account.strip().lower() if args.account else None

    if account and not source:
        parser.error("--account requiere --source para evitar limpiezas ambiguas.")

    actions = collect_actions(args.scope, source, account)

    print("RESET PIPELINE DATA")
    print(f"Base:    {BASE}")
    print(f"Scope:   {args.scope}")
    print(f"Source:  {source or '(all)'}")
    print(f"Account: {account or '(all)'}")
    print(f"Mode:    {'APPLY' if args.apply else 'DRY RUN'}")
    print()

    if not actions:
        print("No hay acciones para ejecutar.")
        return

    for action in actions:
        print(describe_action(action, source, account))

    if not args.apply:
        print()
        print("DRY RUN terminado. Para ejecutar realmente, agrega --apply.")
        return

    print()
    print("Ejecutando...")
    for action in actions:
        print(execute_action(action, source, account))

    print()
    print("Listo.")


if __name__ == "__main__":
    main()
