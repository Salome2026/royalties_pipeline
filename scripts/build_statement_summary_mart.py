from __future__ import annotations

from pathlib import Path

import polars as pl

from build_statement_report_from_mart import aggregate_statement_data


BASE = Path(r"C:\royalties_pipeline")
MARTS_DIR = BASE / "warehouse" / "marts"
STANDARDIZED_PATH = MARTS_DIR / "standardized_raw_all_sources.parquet"
OUTPUT_PATH = MARTS_DIR / "statement_summary_all_sources.parquet"


def main() -> None:
    print("Generando statement_summary_all_sources...")

    totals, fuga_eur = aggregate_statement_data(STANDARDIZED_PATH)
    if totals.empty:
        raise ValueError("No hay datos para statement summary.")

    totals = totals.copy()
    totals["row_type"] = "artist_total"
    totals["total_eur"] = None

    if not fuga_eur.empty:
        fuga_rows = fuga_eur.copy()
        fuga_rows["artist"] = "__TOTAL_EUR__"
        fuga_rows["total"] = None
        fuga_rows["has_share_in_out"] = 0
        fuga_rows["row_type"] = "fuga_eur_total"
        totals = totals[
            ["source", "account", "artist", "statement_period", "total", "has_share_in_out", "total_eur", "row_type"]
        ]
        fuga_rows = fuga_rows[
            ["source", "account", "artist", "statement_period", "total", "has_share_in_out", "total_eur", "row_type"]
        ]
        output = pl.concat(
            [pl.from_pandas(totals), pl.from_pandas(fuga_rows)],
            how="diagonal_relaxed",
        )
    else:
        totals = totals[
            ["source", "account", "artist", "statement_period", "total", "has_share_in_out", "total_eur", "row_type"]
        ]
        output = pl.from_pandas(totals)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output.write_parquet(OUTPUT_PATH)

    print("Listo.")
    print(f"Archivo: {OUTPUT_PATH}")
    print(f"Filas: {output.height}")
    print(f"Peso MB: {OUTPUT_PATH.stat().st_size / 1024 / 1024:.2f}")


if __name__ == "__main__":
    main()
