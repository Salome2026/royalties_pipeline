# Spotify metadata review

Catalog > Nuestro catálogo vs. Spotify compares the active published catalog with
stored Spotify observations. Historical lookup results are imported as consulted,
never as approved. YouTube and album/UPC-only lookups remain in their original
cache and are not misclassified as track matches. Track and album artists are
separate throughout the importer, refresh and UI.

Postgres migration 017 stores observations, current field decisions/overrides and
append-only review history. Each decision checks both observation and review
versions under the same transaction lock. Only exact ISRC track observations can
be accepted. Ambiguous and missing observations remain visible without accepting
an inferred identity. Refresh changes observations only; previous approvals remain.

Manual catalog corrections and ISRC-scoped artist references are protected.
Existing manual label overrides retain precedence. A protected field cannot be
replaced even through a direct API call. Accept/keep require catalog.edit and a
real session identity, and reads/writes enforce the existing catalog artist scope.

Approved values are a display-only operational overlay shared by Catalog and
Contracts. Source statements, identifiers, ownership percentages, money and
existing reports are never rewritten. Published rebuilds cannot erase review
history or protected manual data. No lookup performs a bulk financial rebuild.

A selection is refreshed sequentially through bounded, single-track requests;
progress is visible and a Spotify 429 stops the block. This version does not
schedule unattended recurring lookups. Credential values live in Secret Manager,
not browser bundles or source. Existing scripts/cache remain available for bulk
maintenance. Future scheduled jobs must use the same observations/decisions.

Rollback: redeploy the previous code; preserve the three operational tables and
history. No manual correction or cache must be deleted to roll back the screen.


## Provider priority
Every refresh queries Spotify first. Exact ISRC Spotify matches take precedence;
otherwise YouTube is queried using only the catalog identity_video_id (never
an arbitrary claimed/UGC video from the video_ids list). Video-only catalog rows
are included: Spotify is searched by title/artist without treating that text
search as confirmed identity, then the linked YouTube video is consulted.
YouTube only proposes video title and duration. Channel and publication date
are shown separately, never converted into artist, label or release date.
The original Spotify miss/ambiguity remains inside the fallback observation.
Approvals remain explicit, protected fields are enforced server-side, and the
history records provider and URL. A provider rate limit stops the block.
