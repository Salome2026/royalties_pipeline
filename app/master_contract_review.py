"""Durable association review, independent of the approved economic agreement."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json

from app.master_contract_associations import (
    append_missing_choices, association_key, candidates, unresolved_associations,
)
from app.operational_db import is_postgres_connection

REVIEW_RULE = "manual-metadata-and-version-proposals-v1"
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
                         claims: dict[str, str]) -> dict[str, list[dict]]:
    scopes: dict[tuple, list[dict]] = defaultdict(list)
    saved: dict[tuple, set[str]] = defaultdict(set)
    for root, decisions in choices.items():
        for decision in decisions:
            kind, code, source, account = json.loads(decision["key"])
            saved[(kind, code, source, account) if kind == "TRACK" else (kind, code)].add(root)
    for row in evidence:
        scope = (row["kind"], row["code"])
        if row["kind"] == "TRACK":
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


def reconcile_reviews(conn, release_id: str, evidence: list[dict], aliases: dict[str, str]) -> dict:
    """Re-read decisions under the same lock as human saves; never write contracts."""
    ensure_schema(conn)
    conn.execute("SELECT pg_advisory_xact_lock(%s,%s)", (20261009, 1))
    stored = conn.execute("SELECT isrc,payload_json,version FROM master_contract_splits").fetchall()
    choices = {row["isrc"]: document(row["payload_json"]).get("code_association_overrides") or [] for row in stored}
    claims = {choice["key"]: root for root, values in choices.items() for choice in values if choice["included"]}
    targets = evidence_by_contract(evidence, aliases, choices, claims)
    pending_contracts = 0
    for row in stored:
        root = row["isrc"]
        items = candidates(root, targets.get(root, []), aliases, choices[root], claims)
        state = save_review(conn, root, row["version"], release_id, items, choices[root], "statement-review")
        pending_contracts += bool(state["association_review_pending"])
    conn.execute("""INSERT INTO master_contract_association_review_runs(release_id,rule_version)
        VALUES (%s,%s) ON CONFLICT DO NOTHING""", (release_id, REVIEW_RULE))
    return {"release_id": release_id, "contracts": len(stored), "pending_contracts": pending_contracts}


def review_published_release(client, manifest: dict) -> None:
    """Called by the durable release event Job, including when the dashboard is ready."""
    from io import BytesIO
    import polars as pl
    from app.operational_db import operational_connect
    from app.master_contract_income import published_unassigned_income
    from app.master_contract_metadata import infer_video_evidence, with_external_titles
    from scripts.lib.catalog_report_filter import catalog_alias_lookup
    release = manifest["release_id"]
    with operational_connect() as conn:
        ensure_schema(conn)
        if conn.execute("SELECT 1 FROM master_contract_association_review_runs WHERE release_id=%s AND rule_version=%s",
                        (release, REVIEW_RULE)).fetchone():
            return
    frame = None
    metadata = []
    for filename in ("catalog_master.parquet", "catalog_release_metadata.parquet"):
        entry = manifest["objects"].get(filename)
        if entry:
            data = client.bucket(manifest["bucket"]).blob(entry["object"], generation=int(entry["generation"])).download_as_bytes()
            loaded = pl.read_parquet(BytesIO(data))
            if filename == "catalog_master.parquet":
                frame = loaded
            else:
                metadata = loaded.to_dicts()
    if not metadata:
        from google.api_core.exceptions import NotFound
        # Optional governance metadata is outside older six-file releases; pin its generation.
        blob = client.bucket(manifest["bucket"]).blob(
            "/".join(filter(None, [manifest.get("prefix", "").strip("/"), "catalog_release_metadata.parquet"])))
        try:
            blob.reload()
            metadata = pl.read_parquet(BytesIO(blob.download_as_bytes(if_generation_match=int(blob.generation)))).to_dicts()
        except NotFound:
            pass
    if frame is None:
        raise ValueError("Falta el catalogo publicado para revisar asociaciones.")
    _, evidence = published_unassigned_income(release)
    enriched = with_external_titles(frame.to_dicts(), metadata)
    evidence = infer_video_evidence(enriched, evidence)
    aliases = {row["alias_catalog_key"]: row["catalog_key"]
               for row in catalog_alias_lookup(catalog=frame).to_dicts()}
    with operational_connect() as conn:
        result = reconcile_reviews(conn, release, evidence, aliases)
    print(json.dumps({"event": "contract_association_review_completed", **result}), flush=True)
