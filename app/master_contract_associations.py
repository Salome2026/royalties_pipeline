"""Contract-only identity decisions. Catalog and royalty calculations remain unchanged."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from google.cloud import bigquery

from app.bigquery_dashboard import DEFAULT_DATASET, DEFAULT_LOCATION, DEFAULT_PROJECT, dashboard_client


def association_key(kind: str, code: str, source: str, account: str) -> str:
    return json.dumps([kind, code, source, account], separators=(",", ":"))


def identity_evidence(isrc: str, catalog_row: dict[str, Any], *, client: Any = None,
                      release_id: str | None = None) -> list[dict[str, Any]]:
    query_client = client or dashboard_client(DEFAULT_PROJECT, DEFAULT_LOCATION)
    if release_id is None:
        release = next(iter(query_client.query(
            f"SELECT release_id FROM `{DEFAULT_PROJECT}.{DEFAULT_DATASET}.current_release`",
            job_config=bigquery.QueryJobConfig(maximum_bytes_billed=5_000_000_000),
            location=DEFAULT_LOCATION,
        ).result(timeout=30)), None)
        if release is None:
            raise RuntimeError("No hay una version publicada disponible.")
        release_id = release["release_id"]
    # Expand from exact identifiers, then inspect every occurrence, including other ISRCs.
    sql = f"""
    WITH facts AS (
      SELECT source, account, asset_isrc, product_upc, video_id, track_id,
             title, artist, catalog_number
      FROM `{DEFAULT_PROJECT}.{DEFAULT_DATASET}.royalty_statement_fact`
      WHERE release_id = @release_id
    ), codes AS (
      SELECT f.*, code.kind, code.value,
             IF(code.kind = 'TRACK', source, '') AS scope_source,
             IF(code.kind = 'TRACK', account, '') AS scope_account
      FROM facts f, UNNEST([
        STRUCT('UPC' AS kind, product_upc AS value),
        STRUCT('VIDEO' AS kind, video_id AS value),
        STRUCT('TRACK' AS kind, track_id AS value)
      ]) code
      WHERE code.value IS NOT NULL AND code.value != ''
    ), seeds AS (
      SELECT DISTINCT kind, value, scope_source, scope_account FROM codes WHERE asset_isrc = @isrc
      UNION DISTINCT SELECT 'UPC', value, '', '' FROM UNNEST(@upcs) value
      UNION DISTINCT SELECT 'VIDEO', value, '', '' FROM UNNEST(@videos) value
    )
    SELECT c.kind, c.value AS code, c.source, c.account,
      ARRAY_AGG(DISTINCT NULLIF(c.asset_isrc, '') IGNORE NULLS) AS isrcs,
      ARRAY_AGG(DISTINCT NULLIF(c.title, '') IGNORE NULLS LIMIT 3) AS titles,
      ARRAY_AGG(DISTINCT NULLIF(c.artist, '') IGNORE NULLS LIMIT 3) AS artists,
      LOGICAL_OR(c.source = 'ada' AND COALESCE(c.asset_isrc, '') = ''
                 AND COALESCE(c.catalog_number, '') != '') AS native_ada_product
    FROM codes c JOIN seeds s USING (kind, value, scope_source, scope_account)
    GROUP BY c.kind, c.value, c.source, c.account
    """
    config = bigquery.QueryJobConfig(
        maximum_bytes_billed=5_000_000_000,
        query_parameters=[
            bigquery.ScalarQueryParameter("release_id", "STRING", release_id),
            bigquery.ScalarQueryParameter("isrc", "STRING", isrc),
            bigquery.ArrayQueryParameter("upcs", "STRING", split_codes(catalog_row.get("upcs"))),
            bigquery.ArrayQueryParameter("videos", "STRING", split_codes(catalog_row.get("video_ids"))),
        ],
    )
    return [dict(row) for row in query_client.query(sql, job_config=config, location=DEFAULT_LOCATION).result(timeout=60)]


def split_codes(value: Any) -> list[str]:
    return sorted({part.strip() for part in str(value or "").split(" | ") if part.strip()})


def decision_scope(key: str) -> tuple:
    values = json.loads(key)
    return tuple(values if values[0] == "TRACK" else values[:2])


def unresolved_associations(items: list[dict], choices: list[dict]) -> list[str]:
    known = {item["key"] for item in items}
    unresolved = []
    for item in items:
        scoped = [choice for choice in choices if decision_scope(choice["key"]) == decision_scope(item["key"])]
        choice = next((value for value in scoped if not value["included"]), None)
        choice = choice or next((value for value in scoped if value["key"] == item["key"]), None)
        if choice:
            pending = choice["included"] and (
                not item["selectable"] or choice.get("evidence_signature") != item["evidence_signature"])
        else:
            pending = not item["automatic"] and (item["selectable"] or item.get("requires_review", False))
        if pending:
            unresolved.append(item["code"])
    unresolved.extend(json.loads(choice["key"])[1] for choice in choices
                      if choice["included"] and choice["key"] not in known)
    return sorted(set(unresolved))


def validate_closure(items: list[dict], choices: list[dict]) -> None:
    pending = unresolved_associations(items, choices)
    if pending:
        raise ValueError(f"No se puede cerrar el contrato: hay {len(pending)} codigo(s) por validar. "
                         "Inclui o descarta las propuestas en Codigos asociados.")


def append_missing_choices(items: list[dict], choices: list[dict]) -> list[dict]:
    result = list(items)
    known = {item["key"] for item in items}
    for choice in choices:
        if not choice["included"] or choice["key"] in known:
            continue
        kind, code, source, account = json.loads(choice["key"])
        result.append({
            "key": choice["key"], "kind": kind, "code": code, "source": source, "account": account,
            "titles": [], "artists": [], "isrcs": [], "automatic": False, "included": False,
            "status": "pending", "selectable": False, "requires_review": True,
            "reason": "El codigo incluido ya no aparece en la evidencia publicada; descarta la asociacion antes de cerrar.",
            "evidence_signature": hashlib.sha256(("missing:" + choice["key"]).encode()).hexdigest(),
            "inference_rule": None,
        })
    return result


def candidates(
    isrc: str,
    evidence: list[dict[str, Any]],
    aliases: dict[str, str],
    overrides: list[dict[str, Any]],
    claims: dict[str, str],
) -> list[dict[str, Any]]:
    all_isrcs: dict[tuple[str, ...], set[str]] = {}
    for row in evidence:
        scope = (row["kind"], row["code"])
        if row["kind"] == "TRACK":
            scope += (row["source"], row["account"])
        all_isrcs.setdefault(scope, set()).update(row.get("isrcs") or [])
    choices = {row["key"]: row for row in overrides}
    excluded_scopes = {decision_scope(row["key"]) for row in overrides if not row["included"]}
    claimed_scopes: dict[tuple, set[str]] = {}
    for claim_key, root in claims.items():
        claimed_scopes.setdefault(decision_scope(claim_key), set()).add(root)
    items = []
    for row in evidence:
        kind, code = row["kind"], row["code"]
        source, account = row["source"], row["account"]
        key = association_key(kind, code, source, account)
        scope = (kind, code, source, account) if kind == "TRACK" else (kind, code)
        observed = sorted(all_isrcs[scope])
        canonical = aliases.get(f"{kind}:{code}") if kind != "TRACK" else None
        inferred = isrc in (row.get("inferred_isrcs") or [])
        standalone_video = kind == "VIDEO" and canonical == f"VIDEO:{code}" and inferred
        blocked = bool(set(observed) - {isrc}) or bool(row.get("native_ada_product"))
        if canonical and canonical != f"ISRC:{isrc}" and not standalone_video:
            blocked = True
        other_owners = claimed_scopes.get(decision_scope(key), set()) - {isrc}
        if other_owners:
            blocked = True
        exact = (
            canonical == f"ISRC:{isrc}" or (kind == "TRACK" and observed == [isrc])
        )
        automatic = not blocked and (exact or (inferred and row.get("inference_status") == "strong"))
        if other_owners:
            reason = f"Incluido en el contrato de {', '.join(sorted(other_owners))}."
        elif row.get("native_ada_product"):
            reason = "Producto ADA sin ISRC: conserva su identidad e ingreso propios."
        elif set(observed) - {isrc}:
            reason = "Código compartido con otros ISRC; no se asignan al tema ingresos de otros assets."
        elif blocked:
            reason = "El catálogo lo identifica como otro asset."
        elif automatic:
            reason = "Asociación exacta y única al ISRC." if exact else row["inference_reason"]
        elif inferred:
            reason = row["inference_reason"]
        else:
            reason = "Sin asociación única confirmada en el catálogo; requiere validación."
        identity = [isrc, kind, code, source, account, observed, canonical, bool(row.get("native_ada_product"))]
        if inferred and not exact:
            identity.append(row["inference_signature"])
        signature = hashlib.sha256(json.dumps(
            identity,
            sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        choice = choices.get(key)
        included = automatic
        status = "automatic" if automatic else "pending"
        if choice:
            if not choice["included"]:
                included, status = False, "excluded"
            elif choice.get("evidence_signature") == signature and not blocked:
                included, status = True, "confirmed"
            else:
                included, status = False, "pending"
                reason = "La evidencia cambió desde la confirmación; requiere nueva validación. " + reason
        if blocked and status != "excluded":
            included, status = False, "blocked"
        if decision_scope(key) in excluded_scopes:
            included, status = False, "excluded"
        items.append({
            "key": key, "kind": kind, "code": code, "source": source, "account": account,
            "titles": row.get("titles") or [], "artists": row.get("artists") or [],
            "isrcs": observed, "automatic": automatic, "included": included,
            "status": status, "selectable": not blocked, "reason": reason,
            "evidence_signature": signature,
            "requires_review": inferred and not exact,
            "inference_rule": row.get("inference_rule") if inferred and not exact else None,
        })
    pending_codes = set(unresolved_associations(items, overrides))
    return sorted(items, key=lambda item: (item["code"] not in pending_codes,
                                         {"UPC": 0, "TRACK": 1, "VIDEO": 2}[item["kind"]],
                                         item["code"], item["source"], item["account"]))


def validate_choices(choices: list[dict[str, Any]], previous: list[dict[str, Any]], items: list[dict[str, Any]]) -> None:
    if len({item["key"] for item in choices}) != len(choices):
        raise ValueError("Hay códigos asociados repetidos.")
    known = {item["key"]: item for item in items}
    old = {item["key"]: item for item in previous}
    for choice in choices:
        if choice == old.get(choice["key"]):
            continue
        item = known.get(choice["key"])
        if item is None:
            raise ValueError("El código asociado ya no está disponible. Actualizá la ficha.")
        if choice["included"]:
            if not item["selectable"]:
                raise ValueError(item["reason"])
            if choice.get("evidence_signature") != item["evidence_signature"]:
                raise ValueError("La evidencia cambió desde que la abriste. Actualizá los códigos asociados.")


def read_claims(conn: Any) -> dict[str, str]:
    rows = conn.execute("SELECT isrc, payload_json FROM master_contract_splits").fetchall()
    claims: dict[str, str] = {}
    for row in rows:
        payload = json.loads(row["payload_json"])
        for choice in payload.get("code_association_overrides") or []:
            if choice.get("included"):
                claims[choice["key"]] = row["isrc"]
    return claims


def preserve_choices(split: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if split.get("code_association_overrides") is None:
        split.pop("code_association_overrides", None)
        old = (previous or {}).get("split", {})
        if "code_association_overrides" in old:
            split["code_association_overrides"] = old["code_association_overrides"]
    return split
