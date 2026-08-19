from __future__ import annotations

import sys
from pathlib import Path

import polars as pl


BASE = Path(__file__).resolve().parents[2]
SCRIPTS = BASE / "scripts"
MART_PATH = BASE / "warehouse" / "marts" / "standardized_raw_all_sources.parquet"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib.store_taxonomy import build_normalized_store_summary  # noqa: E402


def assert_close(actual: float, expected: float, label: str) -> None:
    if abs(actual - expected) > 1e-8:
        raise AssertionError(f"{label}: {actual} != {expected}")


def values_for(
    summary: pl.DataFrame,
    source: str,
    dsp: str,
    column: str,
) -> set[str]:
    return set(
        summary
        .filter(
            (pl.col("source") == source)
            & (pl.col("dsp_normalized") == dsp)
        )
        .get_column(column)
        .to_list()
    )


def main() -> None:
    if not MART_PATH.exists():
        raise FileNotFoundError(MART_PATH)

    base = pl.scan_parquet(MART_PATH)
    columns = set(base.collect_schema().names())
    summary = build_normalized_store_summary(base, columns).collect()

    base_totals = (
        base.group_by("source")
        .agg(pl.sum("amount_usd").alias("amount_usd"))
        .collect()
        .sort("source")
    )
    summary_totals = (
        summary.group_by("source")
        .agg(pl.sum("amount_usd").alias("amount_usd"))
        .sort("source")
    )
    for row in base_totals.join(summary_totals, on="source", suffix="_summary").iter_rows(named=True):
        assert_close(
            float(row["amount_usd_summary"]),
            float(row["amount_usd"]),
            f"total {row['source']}",
        )

    ada_spotify = values_for(summary, "ada", "Spotify", "monetization_normalized")
    if not {"Premium", "Ads"}.issubset(ada_spotify):
        raise AssertionError(f"ADA Spotify no separa Premium/Ads: {sorted(ada_spotify)}")

    fuga_youtube = values_for(summary, "fuga", "YouTube", "content_origin_normalized")
    expected_youtube_origins = {"Music / Art Track", "Video / Channel", "UGC / Content ID"}
    if not expected_youtube_origins.issubset(fuga_youtube):
        raise AssertionError(f"FUGA YouTube perdio origenes: {sorted(fuga_youtube)}")

    dashgo_spotify = values_for(summary, "dashgo", "Spotify", "plan_normalized")
    expected_plans = {"Individual", "Family", "Duo", "Advertising"}
    if not expected_plans.issubset(dashgo_spotify):
        raise AssertionError(f"DashGo Spotify perdio planes: {sorted(dashgo_spotify)}")

    print("OK: resumen Store/DSP normalizado reconcilia y conserva categorias.")


if __name__ == "__main__":
    main()
