"""Durable association review, independent of the approved economic agreement."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json

from app.master_contract_associations import (
    append_missing_choices, association_key, candidates, unresolved_associations, decision_scope, split_codes,
)
from app.operational_db import is_postgres_connection

REVIEW_RULE = "complete-identity-evidence-v4"
SCHEMA = """
CREATE TABLE IF NOT EXISTS master_contract_association_reviews (
    isrc text PRIMARY KEY,
    release_id text NOT NULL,
    contract_version bigint NOT NULL,
    pending_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    review_fingerprint text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS master_contract_association_review_history (
    id bigserial PRIMARY KEY,
    isrc text NOT NULL,
    release_id text NOT NULL,
    contract_version bigint NOT NULL,
    pending_json jsonb NOT NULL,
    review_fingerprint text NOT NULL,
    changed_by text NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS master_contract_association_review_runs (
    release_id text NOT NULL,
    rule_version text NOT NULL,
    checked_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (release_id, rule_version)
);
"""


def ensure_schema(conn) -> None:
    if not is_postgres_connection(conn):
        raise ValueError("La revision de asociaciones usa exclusivamente Cloud SQL Postgres.")
    for statement in SCHEMA.split(";"):
        if statement.strip():
            conn.execute(statement)


def document(value):
    return json.loads(value) if isinstance(value, str) else value


def review_state(pending: list[dict], release_id: str = "", updated_at=None) -> dict:
    codes = sorted({row["code"] for row in pending})
    return {"association_review_pending": bool(codes), "association_pending_count": len(codes),
            "association_pending_codes": codes, "association_review_release": release_id,
            "association_reviewed_at": str(updated_at or "")}


def read_states(conn) -> dict[str, dict]:
    from app.royalty_scope import is_wml
    if is_wml():
        return {}
    ensure_schema(conn)
    return {row["isrc"]: review_state(document(row["pending_json"]), row["release_id"], row["updated_at"])
            for row in conn.execute("SELECT * FROM master_contract_association_reviews").fetchall()}


def pending_details(items: list[dict], choices: list[dict]) -> list[dict]:
    codes = set(unresolved_associations(items, choices))
    return sorted([{"key": row["key"], "code": row["code"], "reason": row["reason"],
                    "evidence_signature": row["evidence_signature"]}
                   for row in items if row["code"] in codes], key=lambda row: row["key"])


def save_review(conn, isrc: str, version: int, release_id: str, items: list[dict],
                choices: list[dict], actor: str) -> dict:
    pending = pending_details(append_missing_choices(items, choices), choices)
    fingerprint = hashlib.sha256(json.dumps(pending, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    previous = conn.execute("SELECT review_fingerprint FROM master_contract_association_reviews WHERE isrc=%s",
                            (isrc,)).fetchone()
    values = (isrc, release_id, version, json.dumps(pending), fingerprint)
    conn.execute("""INSERT INTO master_contract_association_reviews
        (isrc,release_id,contract_version,pending_json,review_fingerprint) VALUES (%s,%s,%s,%s::jsonb,%s)
        ON CONFLICT(isrc) DO UPDATE SET release_id=EXCLUDED.release_id,contract_version=EXCLUDED.contract_version,
        pending_json=EXCLUDED.pending_json,review_fingerprint=EXCLUDED.review_fingerprint,updated_at=now()""", values)
    if not previous or previous["review_fingerprint"] != fingerprint:
        conn.execute("""INSERT INTO master_contract_association_review_history
            (isrc,release_id,contract_version,pending_json,review_fingerprint,changed_by)
            VALUES (%s,%s,%s,%s::jsonb,%s,%s)""", (*values, actor))
    return review_state(pending, release_id)


def evidence_by_contract(evidence: list[dict], aliases: dict[str, str], choices: dict[str, list[dict]],
                         claims: dict[str, str], *, catalog: list[dict] | None = None) -> dict[str, list[dict]]:
    scopes: dict[tuple, list[dict]] = defaultdict(list)
    saved: dict[tuple, set[str]] = defaultdict(set)
    for row in catalog or []:
        root = row.get("asset_isrc")
        if root in choices:
            for kind, field in (("UPC", "upcs"), ("VIDEO", "video_ids")):
                for code in split_codes(row.get(field)):
                    saved[(kind, code)].add(root)
    for root, decisions in choices.items():
        for decision in decisions:
            kind, code, source, account = json.loads(decision["key"])
            saved[(kind, code, source, account) if kind in {"TRACK", "TEXT"} else (kind, code)].add(root)
    for row in evidence:
        scope = (row["kind"], row["code"])
        if row["kind"] in {"TRACK", "TEXT"}:
            scope += (row["source"], row["account"])
        scopes[scope].append(row)
    result: dict[str, list[dict]] = defaultdict(list)
    for scope, rows in scopes.items():
        roots = set(saved.get(scope, set()))
        canonical = aliases.get(f"{scope[0]}:{scope[1]}")
        if canonical and canonical.startswith("ISRC:"):
            roots.add(canonical[5:])
        for row in rows:
            roots.update(row.get("isrcs") or [])
            roots.update(row.get("inferred_isrcs") or [])
            claim = claims.get(association_key(row["kind"], row["code"], row["source"], row["account"]))
            if claim:
                roots.add(claim)
        for root in roots:
            result[root].extend(rows)
    return result


def reconcile_reviews(conn, release_id: str, evidence: list[dict], aliases: dict[str, str], *,
                      expected_choices: dict | None = None, rule_version: str = REVIEW_RULE,
                      actor: str = "statement-review", catalog: list[dict] | None = None) -> dict:
    """Re-read decisions under the same lock as human saves; never write contracts."""
    ensure_schema(conn)
    conn.execute("SELECT pg_advisory_xact_lock(%s,%s)", (20261009, 1))
    stored = conn.execute("SELECT isrc,payload_json,version FROM master_contract_splits").fetchall()
    choices = {row["isrc"]: document(row["payload_json"]).get("code_association_overrides") or [] for row in stored}
    if expected_choices is not None and choices != expected_choices:
        raise RuntimeError("Las decisiones cambiaron durante la verificación; se debe reintentar con la evidencia actual.")
    claims = {choice["key"]: root for root, values in choices.items() for choice in values if choice["included"]}
    targets = evidence_by_contract(evidence, aliases, choices, claims, catalog=catalog)
    pending_contracts = 0
    for row in stored:
        root = row["isrc"]
        items = candidates(root, targets.get(root, []), aliases, choices[root], claims)
        state = save_review(conn, root, row["version"], release_id, items, choices[root], actor)
        pending_contracts += bool(state["association_review_pending"])
    conn.execute("""INSERT INTO master_contract_association_review_runs(release_id,rule_version)
        VALUES (%s,%s) ON CONFLICT DO NOTHING""", (release_id, rule_version))
    return {"release_id": release_id, "contracts": len(stored), "pending_contracts": pending_contracts}


def review_revision(manifest: dict, metadata_entry: dict | None) -> str:
    inputs = [manifest["bucket"], *[
        [entry["object"], str(entry["generation"])] if entry else None
        for entry in (manifest["objects"]["catalog_master.parquet"], metadata_entry,
                      manifest["objects"].get("product_income_allocations.json"))]]
    return REVIEW_RULE + ":" + hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:20]


def enrich_review_evidence(catalog: list[dict], evidence: list[dict]) -> list[dict]:
    """Discovery mirrors the editor: metadata proposes only unassigned scopes.

    Full native evidence is still retained for saved/known identifiers. A title
    resemblance of an already identified recording is not a new proposal.
    """
    from app.master_contract_metadata import infer_video_evidence
    def scope(row):
        return decision_scope(association_key(row["kind"], row["code"], row["source"], row["account"]))
    unknown = {scope(row) for row in evidence if row.get("has_unassigned_rows") is True}
    derived = {association_key(row["kind"], row["code"], row["source"], row["account"]): row
               for row in infer_video_evidence(catalog, [r for r in evidence if scope(r) in unknown])}
    return [{**row, **derived.get(association_key(row["kind"], row["code"], row["source"], row["account"]), {})}
            for row in evidence]


def review_aliases(frame, product_index):
    # The editor resolves validated single-track products before evaluating UPCs.
    # A background process must use that exact pinned input, never ambient files.
    from scripts.lib.catalog_report_filter import catalog_alias_lookup
    from scripts.lib.product_income import use_product_income
    with use_product_income(product_index):
        return {row["alias_catalog_key"]: row["catalog_key"]
                for row in catalog_alias_lookup(catalog=frame).to_dicts()}


def review_published_release(client, manifest: dict, *, actor: str = "statement-review") -> None:
    """Called by the durable release event Job, including when the dashboard is ready."""
    from io import BytesIO
    import polars as pl
    from app.operational_db import operational_connect
    from app.master_contract_income import read_choices, published_unassigned_income
    from app.master_contract_associations import review_identity_evidence
    from app.master_contract_metadata import with_external_titles
    from scripts.lib.catalog_report_filter import catalog_alias_lookup
    release = manifest["release_id"]
    metadata_entry = manifest["objects"].get("catalog_release_metadata.parquet")
    if metadata_entry is None:
        from google.api_core.exceptions import NotFound
        blob = client.bucket(manifest["bucket"]).blob(
            "/".join(filter(None, [manifest.get("prefix", "").strip("/"), "catalog_release_metadata.parquet"])))
        try:
            blob.reload()
            metadata_entry = {"object": blob.name, "generation": str(blob.generation)}
        except NotFound:
            pass
    # A metadata-only catalog publication can change proposals without changing
    # the financial release. Check each pinned evidence input, not just its ID.
    revision = review_revision(manifest, metadata_entry)
    with operational_connect() as conn:
        ensure_schema(conn)
        if conn.execute("SELECT 1 FROM master_contract_association_review_runs WHERE release_id=%s AND rule_version=%s",
                        (release, revision)).fetchone():
            return
        choices = read_choices(conn)
    frame = None
    metadata = []
    for filename in ("catalog_master.parquet", "catalog_release_metadata.parquet"):
        entry = metadata_entry if filename == "catalog_release_metadata.parquet" else manifest["objects"].get(filename)
        if entry:
            data = client.bucket(manifest["bucket"]).blob(entry["object"], generation=int(entry["generation"])).download_as_bytes()
            loaded = pl.read_parquet(BytesIO(data))
            if filename == "catalog_master.parquet":
                frame = loaded
            else:
                metadata = loaded.to_dicts()
    if frame is None:
        raise ValueError("Falta el catalogo publicado para revisar asociaciones.")
    evidence = review_identity_evidence(release, frame.to_dicts(), choices)
    enriched = with_external_titles(frame.to_dicts(), metadata)
    evidence = enrich_review_evidence(enriched, evidence)
    product_entry = manifest["objects"].get("product_income_allocations.json")
    product_index = None
    if product_entry:
        product_index = json.loads(client.bucket(manifest["bucket"]).blob(
            product_entry["object"], generation=int(product_entry["generation"])).download_as_bytes())
    aliases = review_aliases(frame, product_index)
    from app.contract_text_reference import enrich_text_proposals
    _, published = published_unassigned_income(release)
    evidence = enrich_text_proposals(evidence + [r for r in published if r["kind"] == "TEXT"], enriched,
        aliases, choices, {c["key"]: root for root, values in choices.items() for c in values if c.get("included")})
    with operational_connect() as conn:
        result = reconcile_reviews(conn, release, evidence, aliases, expected_choices=choices, rule_version=revision, actor=actor, catalog=enriched)
    print(json.dumps({"event": "contract_association_review_completed", **result}), flush=True)
