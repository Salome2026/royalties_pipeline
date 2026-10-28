"""Versioned catalog-driven contract review; open contracts never retain approved report treatment."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any
import polars as pl
from app.master_contracts import artist_key, parse_artists, read_split, save_split
from app.master_contract_participants import allocations, names, EXCLUSIONS
from app.operational_db import db_sql, is_postgres_connection
from scripts.lib.catalog_artist_extensions import canonical

REVIEW = "catalog_participant_review"
PLAN_FILE = "catalog_participant_changes.json"


def identity(name):
    return artist_key(canonical(name))


def catalog_names(row):
    return list(row["catalog_artists"]) if row.get("catalog_artists") is not None else parse_artists(row.get("artist_statement") or "", "catalog")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def build_review_plan(before: pl.DataFrame, after: pl.DataFrame, previous_plan=None):
    old = {row["catalog_key"]: row for row in before.to_dicts()}
    new = {row["catalog_key"]: row for row in after.to_dicts()}
    changes = {}
    for event in (previous_plan or {}).get("changes", []):
        row = new.get("ISRC:" + event["isrc"])
        if row and set(map(identity, catalog_names(row))) == set(map(identity, event["after"])):
            changes[event["isrc"]] = event
    for key in sorted(old.keys() & new.keys()):
        if not key.startswith("ISRC:"):
            continue
        left, right = catalog_names(old[key]), catalog_names(new[key])
        before_keys, after_keys = set(map(identity, left)), set(map(identity, right))
        if before_keys == after_keys:
            continue
        event = {"isrc": key[5:], "before": left, "after": right,
            "added": [name for name in right if identity(name) not in before_keys],
            "removed": [name for name in left if identity(name) not in after_keys]}
        event["fingerprint"] = digest({"isrc": event["isrc"], "before": sorted(before_keys), "after": sorted(after_keys)})
        changes[event["isrc"]] = event
    return {"version": 1, "changes": [changes[key] for key in sorted(changes)]}


def project_review(saved: dict, event: dict, *, history: list[dict] | None = None):
    prior = saved["split"]
    if (prior.get(REVIEW) or {}).get("fingerprint") == event["fingerprint"]:
        return None
    proposed = copy.deepcopy(prior)
    old_allocations = dict(allocations(prior))
    removed_by_user = {}
    for record in history or []:
        for scope, allocation in allocations(json.loads(record["payload_json"])):
            removed_by_user.setdefault(scope, set()).update(
                set(map(identity, names(allocation))) - set(map(identity, names(old_allocations.get(scope, {})))))
    added, effective_new = {}, set()
    for scope, allocation in allocations(proposed):
        present = set(map(identity, names(allocation)))
        excluded = set(map(identity, allocation.get(EXCLUSIONS) or [])) | removed_by_user.get(scope, set())
        effective_new.update(identity(name) for name in event["added"] if identity(name) not in excluded)
        new = []
        for name in event["after"]:
            key = identity(name)
            if key in present or key in excluded:
                continue
            allocation.setdefault("participants", []).append({"artist": name, "percent": None,
                "internal_contract_indyana_percent": None, "rule": {"treatment": "direct"}})
            present.add(key)
            new.append(name)
        if new:
            added[scope] = new
    if not effective_new and not event["removed"]:
        return None
    proposed["agreement_confirmed"] = False
    proposed[REVIEW] = {"status": "pending", "fingerprint": event["fingerprint"],
        "catalog_before": event["before"], "catalog_after": event["after"], "added": added,
        "removed": event["removed"], "previous_version": saved["version"],
        "previously_closed": saved["closed"], "previous_future_reports_selected": saved["future_reports_selected"]}
    if any(len(allocation.get("participants") or []) > 10 for _, allocation in allocations(proposed)):
        # Keep the approved allocation intact; expose every missing name in the
        # review form without persisting an allocation rejected by existing limits.
        review = {**proposed[REVIEW], "capacity_exceeded": True}
        proposed = copy.deepcopy(prior)
        proposed["agreement_confirmed"] = False
        proposed[REVIEW] = review
    return proposed


def apply_review_plan(conn, plan, *, actor="catalog:participants"):
    if plan.get("version") != 1:
        raise ValueError("Unsupported contract review plan")
    if is_postgres_connection(conn):
        conn.execute(db_sql(conn, "SELECT pg_advisory_xact_lock(?, ?)"), (20261009, 1)).fetchone()
    results = []
    for event in plan["changes"]:
        if is_postgres_connection(conn):
            conn.execute(db_sql(conn, "SELECT isrc FROM master_contract_splits WHERE isrc=? FOR UPDATE"), (event["isrc"],)).fetchone()
        saved = read_split(conn, event["isrc"])
        if saved is None:
            continue
        history = [dict(row) for row in conn.execute(db_sql(conn,
            "SELECT payload_json FROM master_contract_split_history WHERE isrc=? ORDER BY version"), (event["isrc"],)).fetchall()]
        proposed = project_review(saved, event, history=history)
        if proposed is None:
            continue
        result = save_split(conn, event["isrc"], proposed, closed=False, future_reports_selected=False,
            expected_version=saved["version"], actor=actor)
        results.append({"isrc": event["isrc"], "version": result["version"], "was_closed": saved["closed"],
            "added": proposed[REVIEW]["added"], "removed": event["removed"]})
    return {"changed_contracts": results, "reopened": sum(row["was_closed"] for row in results)}


def preserve_review(submitted, previous, *, closed, actor):
    result = copy.deepcopy(submitted)
    previous_review = ((previous or {}).get("split") or {}).get(REVIEW)
    if previous_review:
        result[REVIEW] = copy.deepcopy(previous_review)
        if closed:
            result[REVIEW].update(status="reviewed", reviewed_by=actor)
    return result


def pending_review_projection(split):
    result = copy.deepcopy(split)
    review = result[REVIEW]
    if review.get("capacity_exceeded"):
        for scope, allocation in allocations(result):
            present = set(map(identity, names(allocation)))
            for name in review.get("added", {}).get(scope, []):
                if identity(name) not in present:
                    allocation.setdefault("participants", []).append({"artist": name, "percent": None,
                        "internal_contract_indyana_percent": None, "rule": {"treatment": "direct"}})
                    present.add(identity(name))
    return result


def guard_identity_contract_split(conn, before, after):
    from scripts.lib.catalog_identity_corrections import corrections
    old_keys, new_keys = set(before["catalog_key"]), set(after["catalog_key"])
    for rule in corrections():
        old, new = "ISRC:" + rule["reported_isrc"], "ISRC:" + rule["canonical_isrc"]
        if old in old_keys and new not in old_keys and old in new_keys and new in new_keys:
            if read_split(conn, rule["reported_isrc"]) is not None:
                raise ValueError("El ISRC reutilizado tiene un contrato guardado. Identificar su grabacion antes de separar los contratos; no se copia automaticamente a dos artistas.")


def publish_with_participant_review(bucket, prefix, uploads, *, publisher, connection_factory):
    """Carry immutable review events so a failed post-publication write can be retried."""
    from google.api_core.exceptions import NotFound
    from scripts.lib.mart_release import manifest_object_name
    files = list(uploads)
    catalog = next((Path(path) for name, path in files if name == "catalog_master.parquet"), None)
    if catalog is None:
        return publisher(bucket, prefix, files)
    after = pl.read_parquet(catalog)
    # WML has its own workspace and does not use the regular contract tables.
    if "scope" in after.columns and after["scope"].drop_nulls().unique().to_list() == ["wml91230"]:
        return publisher(bucket, prefix, files)
    with tempfile.TemporaryDirectory(prefix="catalog-contract-review-") as directory:
        before, old_plan = after.head(0), None
        try:
            manifest = json.loads(bucket.blob(manifest_object_name(prefix)).download_as_text())
        except NotFound:
            manifest = None
        if manifest:
            item = manifest["files"]["catalog_master.parquet"]
            path = Path(directory) / "before.parquet"
            bucket.blob(item["object_name"], generation=int(item["generation"])).download_to_filename(str(path), if_generation_match=int(item["generation"]))
            before = pl.read_parquet(path)
            if PLAN_FILE in manifest["files"]:
                item = manifest["files"][PLAN_FILE]
                old_plan = json.loads(bucket.blob(item["object_name"], generation=int(item["generation"])).download_as_text(if_generation_match=int(item["generation"])))
        plan = build_review_plan(before, after, old_plan)
        with connection_factory() as conn:
            if not is_postgres_connection(conn):
                raise ValueError("La publicacion del catalogo y su revision contractual requieren Cloud SQL configurado.")
            guard_identity_contract_split(conn, before, after)
        plan_path = Path(directory) / PLAN_FILE
        plan_path.write_text(json.dumps(plan, ensure_ascii=True, sort_keys=True), encoding="utf-8")
        result = publisher(bucket, prefix, [*files, (PLAN_FILE, plan_path)])
        with connection_factory() as conn:
            guard_identity_contract_split(conn, before, after)
            summary = apply_review_plan(conn, plan)
        return {**result, "contract_participant_review": summary}


def review_published_participants(client, manifest):
    """Retry the immutable publication event from the durable catalog worker."""
    from app.operational_db import operational_connect
    from scripts.lib.mart_release import manifest_object_name
    blob = client.bucket(manifest["bucket"]).blob(manifest_object_name(manifest.get("prefix", "marts")))
    blob.reload()
    published = json.loads(blob.download_as_bytes(if_generation_match=int(blob.generation)))
    if published["release_id"] != manifest["release_id"]:
        raise ValueError("El release cambio durante la revision contractual; reintentar con la version vigente.")
    entry = published["files"].get(PLAN_FILE)
    if not entry:
        return {"changed_contracts": [], "reopened": 0}
    plan = json.loads(client.bucket(manifest["bucket"]).blob(entry["object_name"], generation=int(entry["generation"]))
        .download_as_bytes(if_generation_match=int(entry["generation"])))
    with operational_connect() as conn:
        if not is_postgres_connection(conn):
            raise ValueError("La revision contractual durable requiere Cloud SQL.")
        return apply_review_plan(conn, plan)
