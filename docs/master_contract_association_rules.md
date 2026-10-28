# Contract associated-code rules

Scope: Contracts only. Raw statements, catalog identities, ordinary royalty
reports and the royalties dashboard are not rewritten or changed by these rules.
The validation income cutoff remains June 2026 inclusive, by statement date.

## Published generations

Each published release is evaluated automatically when Contracts reads it. The
release ID keys the existing read cache; a new ingestion/publication therefore
needs no operator repair, restart or manual association-refresh job. Evidence
queries and catalog readers must use the same immutable release. Rules apply to
the complete identity history, independently of the income cutoff. Live royalty
eligibility and distributor deductions still control the money being summed.

## Exact identifiers

Existing unique catalog aliases and scoped platform IDs remain automatic.
Different valid ISRCs are separate assets, even when their titles are identical.
A shared UPC is not a basis for allocating album income to one recording.
Native ADA products without ISRC retain their own identity and income.

## Video metadata rule: video-title-performers-v1

Only trusted 11-character video IDs can use the new metadata rule. This is a
derived contract relationship, not an inferred ISRC in a statement or catalog.

- Compare the full title and all performer credits to the complete catalog.
- Ignore capitalization, accents, punctuation and performer order; retain
  title words and version information.
- Remove only explicit terminal presentation labels such as Video Oficial or
  Official Video. Do not remove remix, live, session, slowed or similar labels.
- FUGA: title can contain both the song and credits; the artist fallback can
  preserve additional raw version information, which must also be checked.
- ONErpm: channel artist/name is not a complete performer list. A metadata
  proposal needs full credits in the video title, not merely the channel name.
- Canonical full credits establish a strong match. Alternate catalog credits
  can reveal a competing ISRC but cannot turn missing guests into strong proof.
- Exactly one consistent ISRC, complete credits and compatible version evidence
  allow automatic inclusion. Conflicting titles, incomplete credits, competing
  ISRCs or inconsistent versions produce a pending proposal instead.
- Explicit identifiers, other catalog assets and claims by another contract
  take precedence over metadata. Contradictions prohibit inclusion.
- Product UPCs and arbitrary platform IDs do not receive title-only inference.

## Human decisions and closing

### Sin identificar

Contracts has an additional read-only `Sin identificar` view. It lists published
catalog generation/correction income without an ISRC whose current effective
association does not resolve to a valid catalog contract. It covers all published
months, including external reference accounts; it is not a new contractual report
and does not apply its June cutoff or report deductions. Catalog-view policy
controls admission; transfers are excluded, so Shares are not counted again.
Existing report/governance filters and totals are not changed.

The effective destination uses the same association index, evidence signatures,
exclusion and ownership checks as Contracts. Proposals and explicit discards stay
visible. A valid automatic or confirmed inclusion removes the assigned income;
stale/contradictory evidence returns it to the list. An exclusion in one contract
does not undo a valid destination in another. Contract closure is independent.

Subtract assigned rows before grouping the remaining rows. Keep native identifiers
together so a row with video+UPC+track ID is counted once. Group videos/UPCs across
accounts, scope platform IDs and native ADA products by source/account, and retain
provenance and negative adjustments. No-money metadata is omitted, but offsetting
nonzero monthly movements remain visible. Embedded IDs in old text provide links,
not financial associations. Candidate links open the existing contract editor;
the choices and save/permission rules are unchanged. Search and pagination filter
visibility only, never global ownership. WML remains isolated.

- Choices are Automatic, Include or Discard; absence of a choice for a doubtful
  proposal means Pending, not Discard.
- A decision groups the same video/UPC across its source accounts. Platform
  TRACK IDs remain namespaced by source and account.
- Explicit discards survive future statements/accounts. Restoring Automatic or
  Pending removes those explicit decisions for the code.
- Decisions use the existing Cloud SQL payload, version checks and audit
  history. There is no SQLite write path or parallel operational store.
- Metadata signatures include the rule version, compatible ISRCs, normalized
  full credits and validation outcome, not month, revenue or display spelling.
- Contradictory new evidence suspends an old confirmation. Closed contracts are
  not silently reopened or saved; the next close/closed save must resolve it.
- Drafts can be saved with pending proposals. Closing always rechecks current
  evidence under the global association lock, even without edited choices.
- Pending proposals, stale included decisions and disappeared included codes
  prevent closing. Rule-blocked unrelated shared products need no forced human
  decision; blocked metadata proposals can be explicitly discarded.
- API verification failures prevent closing, rather than declaring zero pending.

## Income conservation

Keep all identifiers of an economic row together. Add only rows without an ISRC
that resolve to one included contract, once. Never re-add existing ISRC revenue,
absorb an ADA native product, split ambiguous income, ignore a discard or bypass
the existing generation/transfer eligibility and royalty discount policies.

## Contract display groups

- Group UPC/video references by code across distributor accounts, retaining every
  underlying key, account, title, artist, signature and saved decision. TRACK IDs
  remain scoped by distributor/account.
- The main list contains UPCs, Art Tracks, channel videos, codes with unidentified
  rows, unknown/mixed origins, pending validations and existing manual decisions.
- A separate collapsed UGC reference list contains only video codes whose complete
  evidence consists of UGC / Content ID rows already identified by ISRC. Shared
  videos retain all observed ISRCs and their existing assignment blocks.
- UGC reference rows are informational; they do not need an additional contract
  selection for money that already carries an ISRC. Existing manual decisions
  stay editable in the main list. Pending evidence always remains visible there.
- Classify from statement evidence in the active immutable release, never from a
  fixed song, distributor whitelist or saved count. New published statements
  automatically reevaluate the display grouping.
- This is presentation metadata only: no change to income associations, evidence
  signatures, close validation, contract payloads, catalogs or any royalty report.

## Verification

Run the Contracts association, metadata, income, pilot and contractual-executive
QA suites, frontend contract-logic QA, frontend production build and the database
guardrails. Before release, compare representative cloud data without saving
test contracts. After release, verify API/Job image alignment, healthy readiness,
published generation, unchanged ordinary-dashboard amounts and stored contracts.
