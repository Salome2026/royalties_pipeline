from pathlib import Path

import polars as pl

from lib.store_taxonomy import add_store_dimensions


BASE = Path(r"C:\royalties_pipeline")
MARTS = BASE / "warehouse" / "marts"

STANDARDIZED_OUTPUT = MARTS / "standardized_raw_all_sources.parquet"
SONG_OUTPUT = MARTS / "song_level_all_sources.parquet"

STANDARDIZED_FILES = [
    MARTS / "standardized_raw_dashgo.parquet",
    MARTS / "standardized_raw_fuga.parquet",
    MARTS / "standardized_raw_onerpm.parquet",
    MARTS / "standardized_raw_orchard.parquet",
    MARTS / "standardized_raw_soundon.parquet",
    MARTS / "standardized_raw_ada.parquet",
]

SONG_FILES = [
    MARTS / "song_level_dashgo.parquet",
    MARTS / "song_level_fuga.parquet",
    MARTS / "song_level_onerpm.parquet",
    MARTS / "song_level_orchard.parquet",
    MARTS / "song_level_soundon.parquet",
    MARTS / "song_level_ada.parquet",
]


def read_parts(paths: list[Path]) -> list[pl.LazyFrame]:
    parts = []

    for path in paths:
        if not path.exists():
            print(f"  - No existe: {path.name}. Se omite.")
            continue

        print(f"  - Leyendo: {path.name}")

        part = pl.scan_parquet(path).with_columns(
            pl.lit(path.name).alias("mart_source_file")
        )

        parts.append(part)

    return parts


def consolidate(paths: list[Path], output_path: Path, add_reporting_dimensions: bool = False):
    parts = read_parts(paths)

    if not parts:
        print(f"No hay partes para generar {output_path.name}")
        return

    print(f"  - Consolidando {len(parts)} parte(s)...")

    final = pl.concat(parts, how="diagonal_relaxed")
    if add_reporting_dimensions:
        final = add_store_dimensions(final, set(final.collect_schema().names()))
    temporary_path = output_path.with_name(f"{output_path.name}.tmp")
    if temporary_path.exists():
        temporary_path.unlink()
    final.sink_parquet(
        temporary_path,
        compression="zstd",
        engine="streaming",
    )
    temporary_path.replace(output_path)

    result = pl.scan_parquet(output_path)
    schema = set(result.collect_schema().names())
    metrics = result.select([
        pl.len().alias("rows"),
        *(
            [pl.sum("amount_usd").alias("amount_usd")]
            if "amount_usd" in schema
            else []
        ),
    ]).collect()
    print(f"  - OK: {output_path}")
    print(f"  - Filas: {metrics['rows'][0]}")

    if "amount_usd" in metrics.columns:
        print(f"  - Total amount_usd: {metrics['amount_usd'][0]}")


def main():
    print("Generando marts consolidados...")

    print("\n=== STANDARDIZED ALL SOURCES ===")
    consolidate(STANDARDIZED_FILES, STANDARDIZED_OUTPUT, add_reporting_dimensions=True)

    print("\n=== SONG LEVEL ALL SOURCES ===")
    consolidate(SONG_FILES, SONG_OUTPUT)

    print("\nListo.")


if __name__ == "__main__":
    main()
