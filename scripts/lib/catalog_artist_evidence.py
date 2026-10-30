"""Preserve source-owned artist evidence across catalogue enrichment steps."""
from __future__ import annotations

from collections import Counter
import json

import polars as pl


def records(value: str | None) -> list[dict]:
    entries = json.loads(value or "[]")
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError("Catalog artist evidence must be a list of source records")
    return entries


def replace_source(value: str | None, source: str, replacement: list[dict]) -> str:
    if any(entry.get("source") != source for entry in replacement):
        raise ValueError("A catalogue reader cannot replace another source's artist evidence")
    retained = [entry for entry in records(value) if entry.get("source") != source]
    return json.dumps([*retained, *replacement], ensure_ascii=False, sort_keys=True)


def evidence_tokens(value: str | None, *, excluding: str) -> Counter:
    return Counter(json.dumps(entry, ensure_ascii=True, sort_keys=True)
                   for entry in records(value) if entry.get("source") != excluding)


def assert_other_sources_preserved(before: pl.DataFrame, after: pl.DataFrame, source: str) -> None:
    """Fail before publication if a reader removes or rewrites unrelated proof."""
    if before["catalog_key"].n_unique() != before.height or after["catalog_key"].n_unique() != after.height:
        raise ValueError("Duplicate catalogue keys while checking artist evidence")
    if "catalog_artist_evidence" not in before.columns:
        return
    if "catalog_artist_evidence" not in after.columns:
        raise ValueError(f"{source}: catalogue artist evidence was removed")
    current = dict(after.select("catalog_key", "catalog_artist_evidence").iter_rows())
    for key, value in before.select("catalog_key", "catalog_artist_evidence").iter_rows():
        if key not in current:
            raise ValueError(f"{source}: catalogue identity disappeared: {key}")
        expected = evidence_tokens(value, excluding=source)
        actual = evidence_tokens(current[key], excluding=source)
        if expected - actual:
            raise ValueError(f"{source}: another source's artist evidence was lost or changed for {key}")


def enrich_checked(catalog: pl.DataFrame, source: str, reader, *args, **kwargs) -> pl.DataFrame:
    result = reader(catalog, *args, **kwargs)
    assert_other_sources_preserved(catalog, result, source)
    return result
