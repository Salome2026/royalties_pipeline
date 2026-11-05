"""Scoped contractual references, never invented native identifiers or asset aliases."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import re
import unicodedata

RULE = "contract-text-reference-v1"
FIELDS = ("source", "account", "source_sheet", "channel_id", "title", "artist")
TITLE_FIELDS = ("asset_title_statement", "track_statement_style", "product_title_statement", "Track Title", "title")
ARTIST_FIELDS = ("artist_best_available", "asset_artist_statement", "artist_statement_style", "product_artist_statement", "track_artist_statement", "Artist Name", "artist")


def text(value):
    return " ".join(unicodedata.normalize("NFC", str(value or "")).split())


def value(row, *names):
    return next((text(row.get(name)) for name in names if text(row.get(name))), "")


def context(row):
    if any(value(row, *names) for names in [
        ("asset_isrc", "isrc", "ISRC"), ("product_upc", "upc", "UPC"),
        ("video_id", "VideoId", "Video ID"), ("track_id",), ("catalog_number",),
    ]):
        return None
    if row.get("_income_product_pending") or value(row, "product_type", "asset_product_type").lower() in {
        "a", "album", "product", "release", "internet album",
    } or value(row, "content_type").lower() in {"product", "album"}:
        return None
    result = {"source": value(row, "source"), "account": value(row, "account"),
              "source_sheet": value(row, "source_sheet"), "channel_id": value(row, "channel_id", "ChannelId"),
              "title": value(row, "title", "track_statement_style", "asset_title_statement"),
              "artist": value(row, "artist", "artist_statement_style", "asset_artist_statement")}
    return result if result["source"] and result["account"] and result["title"] else None


def code_for_context(reference):
    return hashlib.sha256(json.dumps([RULE, *[reference.get(name, "") for name in FIELDS]],
                                     ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def reference_code(row):
    reference = context(row)
    return code_for_context(reference) if reference else None


def with_reference_code(frame):
    """Hash distinct fact contexts, then join back without changing row cardinality."""
    import polars as pl
    columns = set(frame.collect_schema().names())
    def field(names):
        values = [pl.col(name).cast(pl.String, strict=False).str.strip_chars().replace("", None)
                  for name in names if name in columns]
        return pl.coalesce(values) if values else pl.lit(None, dtype=pl.String)
    names = {"source": ("source",), "account": ("account",), "source_sheet": ("source_sheet",),
        "channel_id": ("channel_id", "Channel ID", "ChannelId", "YOUTUBE CHANNEL ID"), "title": TITLE_FIELDS, "artist": ARTIST_FIELDS,
        "asset_isrc": ("asset_isrc", "Asset ISRC", "ISRC", "isrc"),
        "product_upc": ("product_upc", "UPC Code", "UPC"), "video_id": ("video_id", "Video ID", "VideoId"),
        "track_id": ("track_id", "Label Track ID", "Track ID", "gpid"), "catalog_number": ("catalog_number",),
        "product_type": ("product_type", "Product Type", "asset_product_type", "Asset/Product")}
    temporary = ["_text_context_" + name for name in names]
    frame = frame.with_columns([field(fields).fill_null("").alias("_text_context_" + name)
                                for name, fields in names.items()])
    distinct = frame.select(temporary).unique().collect(engine="streaming")
    codes = [reference_code({name: row["_text_context_" + name] for name in names}) for row in distinct.to_dicts()]
    lookup = distinct.with_columns(pl.Series("_contract_text_code", codes, dtype=pl.String))
    return frame.join(lookup.lazy(), on=temporary, how="left", maintain_order="left").drop(temporary)


def row_keys(row):
    from app.master_contract_associations import association_key
    keys = [association_key(kind, row[field], row["source"], row["account"])
            for kind, field in (("UPC", "product_upc"), ("VIDEO", "video_id"), ("TRACK", "track_id"))
            if row.get(field) and not (kind == "UPC" and row.get("_income_upc_pending"))]
    code = reference_code(row)
    if code:
        keys.append(association_key("TEXT", code, row["source"], row["account"]))
    return keys


def text_evidence(rows):
    found = {}
    for row in rows:
        reference = context(row)
        if reference is None:
            continue
        code = code_for_context(reference)
        found[code] = {"kind": "TEXT", "code": code, "source": reference["source"],
            "account": reference["account"], "isrcs": [], "titles": [reference["title"]],
            "artists": [reference["artist"]] if reference["artist"] else [],
            "text_reference": reference, "text_signature": code, "has_unassigned_rows": True}
    return list(found.values())


def enrich_text_proposals(evidence, catalog, aliases, choices, claims):
    """Propose agreements using native context. Every new TEXT assignment is manual."""
    from app.master_contract_income import income_association_index
    from app.master_contract_associations import association_key
    native = [row for row in evidence if row["kind"] != "TEXT"]
    index = income_association_index(native, aliases, choices, claims, with_candidates=True)
    videos = defaultdict(set)
    for row in native:
        if row["kind"] != "VIDEO":
            continue
        for raw in row.get("source_contexts") or []:
            item = json.loads(raw) if isinstance(raw, str) else raw
            channel, title = text(item.get("channel_id")), text(item.get("title"))
            if channel and title:
                videos[(row["source"], row["account"], channel, title)].add(row["code"])
    exact_catalog = defaultdict(set)
    for row in catalog:
        if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}", row.get("asset_isrc") or ""):
            exact_catalog[(text(row.get("track_title")), text(row.get("artist_statement")))].add(row["asset_isrc"])
    result = []
    for row in evidence:
        if row["kind"] != "TEXT":
            result.append(row)
            continue
        reference = row["text_reference"]
        anchors = set(videos.get((row["source"], row["account"], reference["channel_id"], reference["title"]), ()))
        embedded = re.fullmatch(r"Auto generated asset\s*-\s*([A-Za-z0-9_-]{11})", reference["title"], re.I)
        if embedded and reference["channel_id"]:
            anchors.update(code for (source, account, channel, _), codes in videos.items()
                           if (source, account, channel) == (row["source"], row["account"], reference["channel_id"])
                           for code in codes if code == embedded[1])
        roots = set()
        for video in anchors:
            key = association_key("VIDEO", video, row["source"], row["account"])
            roots.update(index["included"].get(key) or [root for root, state in index["proposed"].get(key, {}).items()
                if state["selectable"] and state["status"] != "excluded"])
        if reference["artist"] and reference["artist"] != reference["title"]:
            roots.update(exact_catalog.get((reference["title"], reference["artist"]), ()))
        signature = hashlib.sha256(json.dumps([RULE, reference, sorted(anchors)], sort_keys=True,
                                             separators=(",", ":")).encode()).hexdigest()
        result.append({**row, "text_signature": signature, "inferred_isrcs": sorted(roots),
            "inference_rule": RULE, "inference_signature": signature,
            "inference_reason": "Posible contrato por referencia de origen; confirmar no fusiona los items del catalogo.",
            "related_video_ids": sorted(anchors)})
    return result
