"""Materialize native recording references independently of financial admission.

An ISRC observed on a transfer is evidence of identity, not additional revenue.
Never merge recordings by title, UPC, artist or participation percentage here.
"""
from __future__ import annotations

from collections import defaultdict
import json
import re

import polars as pl


RULE_VERSION = "NATIVE-IDENTITY-REFERENCES-1"
ISRC = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")
ZERO_FIELDS = {"amount_usd", "observed_amount_usd", "transfer_amount_usd",
               "policy_unmatched_amount_usd", "units", "song_level_rows",
               "source_count", "account_count", "identity_amount_usd", "identity_rows"}


def materialize_identity_references(catalog: pl.DataFrame, references: list[dict]) -> pl.DataFrame:
    """Add missing ISRC fiches with zero money and traceable native evidence.

    Existing fiches (including manual metadata, aliases and balances) remain
    byte-for-byte equivalent at the column-value level. A provider adapter must
    supply explicit track-level ISRC evidence; fuzzy matches are not accepted.
    """
    if catalog["catalog_key"].n_unique() != catalog.height:
        raise ValueError("Native identity: duplicate catalog keys")
    groups = defaultdict(list)
    for item in references:
        code = str(item.get("isrc") or "").strip().upper().replace("-", "")
        if item.get("level") != "track" or not ISRC.fullmatch(code):
            raise ValueError("Native identity requires an explicit track-level ISRC")
        if not item.get("source") or not item.get("file_hash") or not item.get("row"):
            raise ValueError("Native identity requires source/file/row provenance")
        groups[code].append({**item, "isrc": code})
    present = set(catalog["asset_isrc"].drop_nulls().to_list())
    keys = set(catalog["catalog_key"].to_list())
    additions = []
    for code in sorted(set(groups) - present):
        key = "ISRC:" + code
        if key in keys:
            raise ValueError("Native identity: conflicting existing ISRC key")
        evidence = sorted(groups[code], key=lambda r: (
            0 if r.get("sheet") == "Masters" else 1,
            str(r.get("statement") or ""), r["source"], str(r.get("account") or ""),
            r["file_hash"], r["row"]))
        evidence = list({json.dumps(r, sort_keys=True, ensure_ascii=False): r for r in evidence}.values())
        titled = [r for r in evidence if str(r.get("title") or "").strip()]
        title = str(titled[0]["title"]).strip() if titled else None
        sources = sorted({r["source"] for r in evidence})
        accounts = sorted({r["account"] for r in evidence if r.get("account")})
        upcs = sorted({str(r["upc"]).strip() for r in evidence
                       if re.fullmatch(r"\d{8,14}", str(r.get("upc") or "").strip())})
        # Only role-aware lists explicitly resolved by the adapter are usable.
        # A payer/receiver or writer is never promoted to recording artist here.
        credit_lists = {tuple(r["recording_artists"]) for r in evidence if r.get("recording_artists")}
        artists = list(next(iter(credit_lists))) if len(credit_lists) == 1 else []
        artist = ", ".join(artists) or None
        row = {name: None for name in catalog.columns}
        row.update({name: 0 for name in ZERO_FIELDS if name in row})
        row.update(catalog_key=key, asset_isrc=code, track_title=title, artist_statement=artist,
                   sources=" | ".join(sources), accounts=" | ".join(accounts),
                   source_sheets=" | ".join(sorted({r["sheet"] for r in evidence})),
                   source_count=len(sources), account_count=len(accounts),
                   isrcs=code, upcs="", primary_upc=None,
                   title_variants=" | ".join(sorted({str(r["title"]).strip() for r in titled})),
                   track_title_normalized=" ".join(title.lower().split()) if title else None,
                   artist_statement_normalized=" ".join(artist.lower().split()) if artist else None,
                   catalog_identity_rule=RULE_VERSION,
                   catalog_identity_upcs=upcs,
                   catalog_identity_evidence=json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                   catalog_identity_reference_only=True)
        # Retain UPCs as evidence, outside fields consumed by the automatic
        # alias lookup. A participation's Parent ID can identify an album.
        if "catalog_aliases" in row:
            row["catalog_aliases"] = []
        additions.append(row)
    if not additions:
        return catalog
    schema = {**catalog.schema, "catalog_identity_rule": pl.String,
              "catalog_identity_evidence": pl.String, "catalog_identity_reference_only": pl.Boolean,
              "catalog_identity_upcs": pl.List(pl.String)}
    extra = pl.DataFrame(additions, schema=schema, strict=True)
    result = pl.concat([catalog, extra], how="diagonal_relaxed")
    if result["catalog_key"].n_unique() != result.height:
        raise ValueError("Native identity: duplicate output keys")
    return result
