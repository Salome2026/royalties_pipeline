"""Read-only catalog income without a currently valid contract destination."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import re
import unicodedata

from app.master_contract_associations import association_key
from app.master_contract_income import income_association_index, associated_income_isrc


def normalized(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", str(value or "")).casefold()
                            if not unicodedata.combining(c)).split())


def reference(row):
    # These keys describe the economic reference, not a proposed ISRC.
    if row.get("video_id"):
        return ("VIDEO", row["video_id"])
    if row.get("source") == "ada" and row.get("catalog_number"):
        return ("PRODUCT", row["catalog_number"], row["source"], row["account"])
    if row.get("track_id"):
        return ("TRACK", row["track_id"], row["source"], row["account"])
    if row.get("product_upc"):
        return ("UPC", row["product_upc"])
    return ("TEXT", normalized(row.get("title")), normalized(row.get("artist")), row["source"], row["account"])


def unidentified_income(rows, evidence, catalog, aliases, choices, *, keyword="", source=None,
                        account=None, offset=0, limit=50, reference_id=None):
    """Subtract actual assignments first, then group remaining money once.

    Candidate discovery/exclusion is not allocation. Use the same current
    evidence/signatures/ownership rules as Contracts, without saving decisions.
    Filtering never changes those global ownership rules.
    """
    known = {r["asset_isrc"]: r for r in catalog if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}", r.get("asset_isrc") or "")}
    claims = {c["key"]: root for root, values in choices.items() for c in values if c.get("included")}
    index = income_association_index(evidence, aliases, choices, claims, with_candidates=True)
    grouped = {}
    options = set()
    for row in rows:
        amount = float(row.get("amount_usd") or 0)
        if row.get("asset_isrc") or not math.isfinite(amount):
            continue
        options.add((row["source"], row["account"]))
        if associated_income_isrc(row, index) in known:
            continue
        if (source and row["source"] != source) or (account and row["account"] != account):
            continue
        key = reference(row)
        item = grouped.setdefault(key, {"titles": Counter(), "artists": Counter(), "codes": set(),
            "accounts": set(), "periods": set(), "amounts": [], "has_money": False, "candidates": {}})
        item["amounts"].append(amount)
        item["has_money"] |= abs(amount) > 1e-10
        for field in ["title", "artist"]:
            if row.get(field):
                item["titles" if field == "title" else "artists"][row[field]] += int(row.get("raw_rows") or 1)
        item["accounts"].add((row["source"], row["account"]))
        if row.get("statement_period"):
            item["periods"].add(row["statement_period"])
        for kind, field in [("VIDEO", "video_id"), ("UPC", "product_upc"), ("TRACK", "track_id")]:
            if not row.get(field):
                continue
            item["codes"].add((kind, row[field]))
            k = association_key(kind, row[field], row["source"], row["account"])
            for root, state in index["proposed"].get(k, {}).items():
                if root not in known:
                    continue
                candidate = item["candidates"].setdefault(root, {"isrc": root,
                    "title": known[root].get("track_title") or root,
                    "artists": known[root].get("artist_statement") or "", "statuses": set(), "reasons": set()})
                candidate["statuses"].add(state["status"])
                candidate["reasons"].add(state["reason"])
    items = []
    for key, value in grouped.items():
        if not value["has_money"]:
            continue
        title = min(value["titles"], key=lambda t: (-value["titles"][t], t)) if value["titles"] else "Sin título informado"
        artist = min(value["artists"], key=lambda t: (-value["artists"][t], t)) if value["artists"] else "No identificado"
        video = key[1] if key[0] == "VIDEO" else None
        # Some old reports embed a Video ID in text. A link is useful evidence,
        # but it must not turn into an automatic financial association.
        embedded = re.fullmatch(r"Auto generated asset\s*-\s*([A-Za-z0-9_-]{11})", title, re.I)
        video = video or (embedded[1] if embedded else None)
        candidates = [{**c, "statuses": sorted(c["statuses"]), "reasons": sorted(c["reasons"])}
                      for _, c in sorted(value["candidates"].items())]
        item = {"id": hashlib.sha256(json.dumps(key).encode()).hexdigest(), "kind": key[0],
            "code": key[1] if key[0] != "TEXT" else None, "title": title, "artist": artist,
            "titles": sorted(value["titles"]), "artists": sorted(value["artists"]),
            "video_url": "https://www.youtube.com/watch?v=" + video if video else None,
            "amount_usd": math.fsum(value["amounts"]),
            "source_accounts": [{"source": s, "account": a} for s, a in sorted(value["accounts"])],
            "first_month": min(value["periods"], default=None), "last_month": max(value["periods"], default=None),
            "candidates": candidates}
        if reference_id is not None and item["id"] != reference_id:
            continue
        text = normalized(" ".join([*item["titles"], *item["artists"], key[1], *[c["isrc"] for c in candidates], *[c["title"] for c in candidates]]))
        if all(token in text for token in normalized(keyword).split()):
            items.append(item)
    items.sort(key=lambda i: (-abs(i["amount_usd"]), i["id"]))
    offset, limit = max(0, offset), max(1, min(limit, 100))
    if offset >= len(items):
        offset = ((len(items) - 1) // limit) * limit if items else 0
    return {"items": [], "unidentified_items": items[offset:offset + limit], "total": len(items),
        "summary": {"open": 0, "closed": 0, "review": 0}, "offset": offset, "limit": limit,
        "source_accounts": [{"source": s, "account": a} for s, a in sorted(options)],
        "unidentified_summary": {"amount_usd": math.fsum(i["amount_usd"] for i in items),
            "with_candidates": sum(bool(i["candidates"]) for i in items),
            "without_candidates": sum(not i["candidates"] for i in items)},
        "amount_basis": "published_catalog_usd", "period_basis": "all_published_history", "reports_effective": False}
