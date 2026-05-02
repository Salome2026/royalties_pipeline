import subprocess
import sys
from pathlib import Path

# =========================
# CONFIG
# =========================
BASE_DIR = Path(r"C:\royalties_pipeline\scripts")

SCRIPTS = [
    "ingest_fuga_incremental.py",
    "ingest_fuga_corrections.py",
    "ingest_onerpm_henry_remix_incremental.py",
    "ingest_onerpm_mawzrecords_incremental.py",
    "ingest_dashgo_incremental.py",
    "ingest_orchard_incremental.py",
    "ingest_orchard_altafonte_legacy.py",
    "ingest_soundon_incremental.py",
]

# =========================
# RUNNER
# =========================
def run_script(script_name):
    script_path = BASE_DIR / script_name

    print(f"\n🚀 Ejecutando: {script_name}")

    if not script_path.exists():
        print(f"❌ No existe: {script_path}")
        return False

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=BASE_DIR
    )

    if result.returncode != 0:
        print(f"❌ Error en: {script_name}")
        return False

    print(f"✅ OK: {script_name}")
    return True


# =========================
# MAIN
# =========================
def main():
    print("🔥 INICIO PIPELINE COMPLETO\n")

    for script in SCRIPTS:
        ok = run_script(script)

        if not ok:
            print("\n⛔ Pipeline detenido por error.")
            return

    print("\n🎉 Pipeline completado correctamente.")


if __name__ == "__main__":
    main()
