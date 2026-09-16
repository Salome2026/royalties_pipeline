from __future__ import annotations

from pathlib import Path

import polars as pl


BASE = Path(__file__).resolve().parents[2]
MARTS = BASE / "warehouse" / "marts"


def source_accounts(filename: str) -> set[tuple[str, str]]:
    return set(
        pl.scan_parquet(MARTS / filename)
        .select([
            pl.col("source").cast(pl.Utf8, strict=False).str.to_lowercase(),
            pl.col("account").cast(pl.Utf8, strict=False).str.to_lowercase(),
        ])
        .drop_nulls()
        .unique()
        .collect()
        .rows()
    )


def main() -> None:
    detailed = source_accounts("standardized_raw_all_sources.parquet")
    compact = source_accounts("song_level_all_sources.parquet")
    if detailed != compact:
        raise AssertionError({
            "only_detailed": sorted(detailed - compact),
            "only_compact": sorted(compact - detailed),
        })
    print({"ok": True, "source_accounts": len(compact)})


if __name__ == "__main__":
    main()
