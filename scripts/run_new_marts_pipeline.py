import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(r"C:\royalties_pipeline\scripts")


STEPS = [
    ("Standardized", "ingest_standardized_fuga.py"),
    ("Standardized", "ingest_standardized_dashgo.py"),
    ("Standardized", "ingest_standardized_orchard.py"),
    ("Standardized", "ingest_standardized_onerpm.py"),
    ("Standardized", "ingest_standardized_soundon.py"),

    ("Song level", "build_song_level_fuga.py"),
    ("Song level", "build_song_level_dashgo.py"),
    ("Song level", "build_song_level_orchard.py"),
    ("Song level", "build_song_level_onerpm.py"),
    ("Song level", "build_song_level_soundon.py"),

    ("Consolidated marts", "build_consolidated_marts.py"),
    ("Consolidated marts", "build_statement_summary_mart.py"),
    ("Audit", "audit_marts_general.py"),
    ("Audit", "audit_consolidated_marts.py"),

    ("Report", "build_ingresos_por_statement_from_marts.py"),
]


def run_step(group: str, script_name: str) -> bool:
    script_path = BASE_DIR / script_name

    print(f"\n=== {group}: {script_name} ===")

    if not script_path.exists():
        print(f"ERROR: no existe {script_path}")
        return False

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=BASE_DIR,
    )

    if result.returncode != 0:
        print(f"ERROR: fallo {script_name} con exit code {result.returncode}")
        return False

    print(f"OK: {script_name}")
    return True


def main():
    print("Inicio pipeline nuevo de marts")

    for group, script_name in STEPS:
        if not run_step(group, script_name):
            print("\nPipeline detenido por error.")
            raise SystemExit(1)

    print("\nPipeline nuevo completado correctamente.")


if __name__ == "__main__":
    main()
