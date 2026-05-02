from pathlib import Path

import polars as pl


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
]

SONG_FILES = [
    MARTS / "song_level_dashgo.parquet",
    MARTS / "song_level_fuga.parquet",
    MARTS / "song_level_onerpm.parquet",
    MARTS / "song_level_orchard.parquet",
    MARTS / "song_level_soundon.parquet",
]


def read_parts(paths: list[Path]) -> list[pl.DataFrame]:
    parts = []

    for path in paths:
        if not path.exists():
            print(f"  - No existe: {path.name}. Se omite.")
            continue

        print(f"  - Leyendo: {path.name}")

        part = (
            pl.read_parquet(path)
            .with_columns(pl.lit(path.name).alias("mart_source_file"))
        )

        parts.append(part)

    return parts


def consolidate(paths: list[Path], output_path: Path):
    parts = read_parts(paths)

    if not parts:
        print(f"No hay partes para generar {output_path.name}")
        return

    print(f"  - Consolidando {len(parts)} parte(s)...")

    final = pl.concat(parts, how="diagonal_relaxed")
    final.write_parquet(output_path)

    print(f"  - OK: {output_path}")
    print(f"  - Filas: {final.height}")

    if "amount_usd" in final.columns:
        print(f"  - Total amount_usd: {final['amount_usd'].sum()}")


def main():
    print("Generando marts consolidados...")

    print("\n=== STANDARDIZED ALL SOURCES ===")
    consolidate(STANDARDIZED_FILES, STANDARDIZED_OUTPUT)

    print("\n=== SONG LEVEL ALL SOURCES ===")
    consolidate(SONG_FILES, SONG_OUTPUT)

    print("\nListo.")


if __name__ == "__main__":
    main()
