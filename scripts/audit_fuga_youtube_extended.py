"""The same preflight used by Procesar nuevos, runnable without rebuilding incomes."""
import argparse
from pathlib import Path
from lib.fuga_extended import audit_directory
from lib.fuga_extended import _atomic_parquet
from lib.fuga_video_automatic import apply_automatic_extended
import polars as pl

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(r"C:\royalties_pipeline"))
    args = parser.parse_args()
    audit_directory(args.root)
    catalog_path = args.root / "warehouse/marts/catalog_master.parquet"
    if catalog_path.exists():
        _atomic_parquet(apply_automatic_extended(pl.read_parquet(catalog_path), args.root), catalog_path)
