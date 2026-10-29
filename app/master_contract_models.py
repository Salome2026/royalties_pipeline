"""Read-only contract model metadata; no income or association calculations."""
from __future__ import annotations

import json
from typing import Any

from app.master_contracts import artist_suggestions


def closed_models(catalog: list[dict], saved: list[dict]) -> list[dict[str, Any]]:
    by_isrc = {row["asset_isrc"]: row for row in catalog}
    items = []
    for record in saved:
        row = by_isrc.get(record["isrc"])
        if row is None or not record["is_closed"]:
            continue
        payload = record["payload_json"]
        split = json.loads(payload) if isinstance(payload, str) else payload
        suggestions = artist_suggestions(record["isrc"], None, row.get("artist_statement"),
                                         row.get("catalog_artists"), row.get("catalog_artist_evidence"))
        items.append({"isrc": record["isrc"], "title": row.get("track_title") or record["isrc"],
                      "split": split, "version": int(record["version"]), "closed": True,
                      "first_statement_date": None, "artist_suggestions": {"artists": suggestions["artists"]}})
    return sorted(items, key=lambda item: (item["title"].casefold(), item["isrc"]))
