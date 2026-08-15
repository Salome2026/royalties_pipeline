# Identity normalization policy

This document defines how raw distributor identifiers become stable catalog and song-level identities.

## Goal

Distributor files can contain different identifier types in similarly named columns. The system must not treat every `ID` as an ISRC. Each candidate must be classified before it reaches `song_level` or `catalog_master`.

## Identifier types

- `asset_isrc`: only a valid ISRC, normalized to uppercase without separators. Example: `US3DF2408987`.
- `product_upc`: numeric UPC/EAN-like product id, 8 to 14 digits.
- `track_id`: a platform/content id when there is no ISRC-level identity. For YouTube this is the 11-character video id.
- `channel_id`: YouTube channel id. This is context, not a catalog key and not a song identity.
- text fallback: title + artist only when no trusted id exists.

## ONErpm rules

### Masters

- `asset_isrc`: first valid ISRC from `ISRC`, `ID`, `Parent ID`.
- `product_upc`: first valid UPC from `UPC`, `Parent ID`.
- `track_id`: empty unless a future source gives a trusted track/video id outside ISRC.

### Youtube Channels

- `track_id`: valid YouTube `Video ID`.
- `asset_isrc`: only if a valid ISRC is explicitly present.
- `channel_id`: `Channel ID`.
- Never store `Video ID` in `asset_isrc`.

### Shares In & Out

- `ID` is mixed:
  - valid ISRC -> `asset_isrc`
  - valid YouTube video id -> `track_id`
  - valid UPC is not an ISRC
- `Parent ID` is mixed:
  - UPC-like value -> `product_upc`
  - YouTube channel id -> `channel_id`
- This sheet can be used as rows or flags depending on account configuration, but identifiers must still be classified.

## DashGo rules

- `asset_isrc`: valid ISRC from `asset_isrc` or `ISRC`.
- `track_id`: valid YouTube video id from `video_id` or `VideoId` only when no ISRC exists.
- ISRC with separators must normalize to the canonical ISRC.

## FUGA rules

FUGA `royalty_product_and_asset` can report income at two different levels:

- `Asset`: the row normally contains `Asset ISRC`, `Asset Title`, `Asset Artist`
  and `Asset Quantity`.
- `Product`: the row can contain `Product UPC`, `Product Title`,
  `Product Artist` and `Product Quantity`, while `Asset ISRC` and asset fields
  are blank.

The standardized ingest must preserve that difference exactly:

- `asset_isrc` must be copied only from `Asset ISRC`.
- `product_upc` must be copied from `Product UPC`.
- `asset_product_type` must preserve `Asset/Product`.
- A blank `Asset ISRC` in a product-level row is not an ingest error by itself.
- Never write an inferred ISRC back into `standardized_raw_fuga.parquet`.

Product-level FUGA rows may be linked to a canonical ISRC only in derived
catalog/report layers, and only when the UPC relationship is unambiguous.

### YouTube Channel Income

FUGA does not expose a column literally named `Video ID` for YouTube channel
income. The raw file can still contain trusted YouTube video identifiers:

- `DSP Container ID`: use it as `track_id` only when it is exactly an
  11-character YouTube video id.
- `Product Reference`: use it as `track_id` only when it matches
  `YT-V-<11-character-video-id>`; store only the 11-character id.
- `DSP Unit ID`: do not use as video id. It behaves like an internal asset/unit
  identifier.
- `DSP Collection ID`: do not use as video id. It behaves like a channel or
  collection identifier.

This rule does not infer an ISRC. If FUGA leaves `Asset ISRC` blank, the row
remains non-ISRC and can become a `VIDEO:<track_id>` catalog item only when a
trusted video id is present.

Validated example:

- Source file: `March2026StatementRun_INDYANARECORDSLLC-royalty_product_and_asset.csv`
- Row type: `Product`
- UPC: `198474357444`
- Title: `Perreo TL`
- Artist: `mamiyosoyelth and Lihueeel`
- Original `Asset ISRC`: blank
- Safe derived ISRC: `QZK6L2413497`
- Reason: the same UPC maps to a single ISRC in catalog evidence, and Spotify
  confirms the UPC/ISRC pair on a one-track release.

## Catalog key priority

1. `ISRC:<asset_isrc>`
2. `VIDEO:<track_id>`
3. `TEXT:<normalized_title>|<normalized_artist>`

UPC and video aliases can map to ISRC when the relationship is unambiguous. This avoids duplicate catalog rows where a source has both metadata and money for the same work.

## Report identity and traceability

Reports must group economic rows by the canonical identity resolved through the
catalog, not by the distributor's display code.

Rules:

1. Resolve every row to `catalog_key` through the shared catalog alias layer.
2. Use that `catalog_key` as the grouping key in summaries by track.
3. Keep distributor identifiers (`ISRC`, video id, asset reference, sale id,
   track id) as traceability fields. They must not create additional summary
   rows when they resolve to the same `catalog_key`.
4. Never merge two valid, distinct ISRCs only because title and artist are
   similar.
5. Store, territory, monetization and content origin are analysis dimensions;
   they do not form part of track identity.

The visible `Resumen por tema` therefore has one row per resolved catalog item.
The row detail remains available in the report for source-level audit.

## UPC to ISRC derived identity

UPC-to-ISRC mapping is allowed only as a derived identity, never as a raw data
rewrite.

A row without ISRC can inherit a canonical ISRC for catalog/report purposes when
all conditions are true:

1. The row has a valid UPC.
2. Across the current catalog evidence, that UPC maps to exactly one valid ISRC.
3. Title/artist evidence does not contradict the mapped work.
4. External metadata, when available, supports the relationship. Example:
   Spotify album UPC + track ISRC on a one-track release.
5. The output keeps enough provenance to distinguish:
   - original ISRC;
   - original UPC;
   - resolved ISRC;
   - resolution method;
   - resolution confidence.

If a UPC maps to multiple ISRCs, or there is not enough evidence, the row remains
unresolved/pending review. It must not be forced into an ISRC.

## Audit rule

After changing identity rules:

1. Total `amount_usd` must remain unchanged.
2. Totals by `source + account + artist_statement_style + transaction_month` must remain unchanged.
3. Totals by `source + account + source_sheet + content_type + transaction_month` must remain unchanged.
4. Expected movement is allowed only between identity keys, for example `TEXT` to `VIDEO` or non-canonical ISRC to canonical ISRC.

## Current implementation

- Shared identity expressions live in `scripts/lib/identity.py`.
- ONErpm canonical identifiers are populated during
  `scripts/ingest_standardized_onerpm.py`, before consolidated marts and reports.
- ONErpm identity rules are applied in `scripts/build_song_level_onerpm.py`.
- DashGo identity rules are applied in `scripts/build_song_level_dashgo.py`.
- Catalog aliasing and key selection are applied in `scripts/build_catalog_master.py`.
- Report output identity/status resolution is centralized in
  `scripts/lib/catalog_report_filter.py`.
- Generic keyword royalty reports group their track summary by the resolved
  `catalog_key`; source codes remain visible only as provenance.
