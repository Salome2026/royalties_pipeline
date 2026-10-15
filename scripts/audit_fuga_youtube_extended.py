"""The same preflight used by Procesar nuevos, runnable without rebuilding incomes."""
import argparse
from pathlib import Path
from lib.fuga_extended import audit_directory

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(r"C:\royalties_pipeline"))
    args = parser.parse_args()
    audit_directory(args.root)
