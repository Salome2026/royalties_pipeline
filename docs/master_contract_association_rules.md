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

## Verification

Run the Contracts association, metadata, income, pilot and contractual-executive
QA suites, frontend contract-logic QA, frontend production build and the database
guardrails. Before release, compare representative cloud data without saving
test contracts. After release, verify API/Job image alignment, healthy readiness,
published generation, unchanged ordinary-dashboard amounts and stored contracts.
