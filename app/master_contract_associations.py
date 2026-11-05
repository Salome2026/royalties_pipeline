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
                      release_id: str | None = None, _review_seeds: dict | None = None) -> list[dict[str, Any]]:
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
             title, artist, catalog_number, content_origin, channel_id, source_sheet
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
      SELECT DISTINCT kind, value, scope_source, scope_account FROM codes
      WHERE asset_isrc = @isrc OR asset_isrc IN UNNEST(@review_isrcs)
        OR (@include_unassigned AND COALESCE(asset_isrc, '') = '')
      UNION DISTINCT SELECT 'UPC', value, '', '' FROM UNNEST(@upcs) value
      UNION DISTINCT SELECT 'VIDEO', value, '', '' FROM UNNEST(@videos) value
      UNION DISTINCT SELECT JSON_VALUE(value,'$[0]'), JSON_VALUE(value,'$[1]'),
        IF(JSON_VALUE(value,'$[0]')='TRACK',JSON_VALUE(value,'$[2]'),''),
        IF(JSON_VALUE(value,'$[0]')='TRACK',JSON_VALUE(value,'$[3]'),'') FROM UNNEST(@saved_codes) value
    )
    SELECT c.kind, c.value AS code, c.source, c.account,
      ARRAY_AGG(DISTINCT NULLIF(c.asset_isrc, '') IGNORE NULLS) AS isrcs,
      ARRAY_AGG(DISTINCT NULLIF(c.title, '') IGNORE NULLS ORDER BY NULLIF(c.title, '')) AS titles,
      ARRAY_AGG(DISTINCT NULLIF(c.artist, '') IGNORE NULLS ORDER BY NULLIF(c.artist, '')) AS artists,
      ARRAY_AGG(DISTINCT NULLIF(c.content_origin, '') IGNORE NULLS) AS content_origins,
      ARRAY_AGG(DISTINCT TO_JSON_STRING(STRUCT(c.title AS title,c.artist AS artist,c.channel_id AS channel_id,c.source_sheet AS source_sheet))) AS source_contexts,
      LOGICAL_AND(COALESCE(c.content_origin, '') = 'UGC / Content ID') AS only_ugc_rows,
      LOGICAL_OR(COALESCE(c.asset_isrc, '') != '') AS has_identified_rows,
      LOGICAL_OR(COALESCE(c.asset_isrc, '') = '') AS has_unassigned_rows,
      LOGICAL_OR(c.source = 'ada' AND COALESCE(c.asset_isrc, '') = ''
                 AND COALESCE(c.catalog_number, '') != '') AS native_ada_product
    FROM codes c JOIN seeds s USING (kind, value, scope_source, scope_account)
    GROUP BY c.kind, c.value, c.source, c.account
    """
    seeds = _review_seeds or {}
    config = bigquery.QueryJobConfig(
        maximum_bytes_billed=5_000_000_000,
        query_parameters=[
            bigquery.ScalarQueryParameter("release_id", "STRING", release_id),
            bigquery.ScalarQueryParameter("isrc", "STRING", isrc),
            bigquery.ArrayQueryParameter("upcs", "STRING", seeds.get("upcs", split_codes(catalog_row.get("upcs")))),
            bigquery.ArrayQueryParameter("videos", "STRING", seeds.get("videos", split_codes(catalog_row.get("video_ids")))),
            bigquery.ArrayQueryParameter("review_isrcs", "STRING", seeds.get("isrcs", [])),
            bigquery.ScalarQueryParameter("include_unassigned", "BOOL", bool(_review_seeds)),
            bigquery.ArrayQueryParameter("saved_codes", "STRING", [json.dumps(row, separators=(",", ":")) for row in seeds.get("saved_codes", [])]),
        ],
    )
    return [dict(row) for row in query_client.query(sql, job_config=config, location=DEFAULT_LOCATION).result(timeout=60)]


def review_identity_evidence(release_id: str, catalog: list[dict], choices: dict[str, list[dict]], *, client=None) -> list[dict]:
    """Same complete evidence as the editor, batched once for every saved contract.

    Discovery also includes unassigned codes. Saved and native identifiers seed
    all their occurrences, even when every income row already has an ISRC.
    """
    if not choices:
        return []
    selected = [row for row in catalog if row.get("asset_isrc") in choices]
    seeds = {"isrcs": sorted(choices),
             "upcs": sorted({v for row in selected for v in split_codes(row.get("upcs"))}),
             "videos": sorted({v for row in selected for v in split_codes(row.get("video_ids"))}),
             "saved_codes": sorted({tuple(json.loads(c["key"])) for values in choices.values() for c in values})}
    return identity_evidence("", {}, release_id=release_id, client=client, _review_seeds=seeds)


def split_codes(value: Any) -> list[str]:
    return sorted({part.strip() for part in str(value or "").split(" | ") if part.strip()})


def decision_scope(key: str) -> tuple:
    values = json.loads(key)
    return tuple(values if values[0] in {"TRACK", "TEXT"} else values[:2])


def unresolved_associations(items: list[dict], choices: list[dict]) -> list[str]:
    known = {item["key"] for item in items}
    unresolved = []
    for item in items:
        if item.get("reference_group") == "ugc":
            continue
        scoped = [choice for choice in choices if decision_scope(choice["key"]) == decision_scope(item["key"])]
        choice = next((value for value in scoped if not value["included"]), None)
        choice = choice or next((value for value in scoped if value["key"] == item["key"]), None)
        if choice:
            pending = choice["included"] and (
                not item["selectable"] or choice.get("evidence_signature") != item["evidence_signature"])
        else:
            pending = item["kind"] != "TEXT" and not item["automatic"] and (item["selectable"] or item.get("requires_review", False))
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
            **({"text_reference": choice["text_reference"], "manual": True,
                "titles": [choice["text_reference"].get("title", "")]} if kind == "TEXT" and choice.get("text_reference") else {}),
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
    reference_only: dict[tuple, bool] = {}
    for row in evidence:
        scope = (row["kind"], row["code"])
        if row["kind"] in {"TRACK", "TEXT"}:
            scope += (row["source"], row["account"])
        all_isrcs.setdefault(scope, set()).update(row.get("isrcs") or [])
        reference_only[scope] = reference_only.get(scope, True) and (
            row["kind"] == "VIDEO" and row.get("only_ugc_rows") is True
            and row.get("has_identified_rows") is True and row.get("has_unassigned_rows") is False)
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
        choice = choices.get(key)
        manual = bool(choice and choice.get("manual"))
        # Manual video links allocate only rows lacking a native ISRC. Native
        # occurrences of the same video keep their own recording identity.
        manual_unassigned_video = manual and kind == "VIDEO" and row.get("has_unassigned_rows") is True
        scope = (kind, code, source, account) if kind in {"TRACK", "TEXT"} else (kind, code)
        observed = sorted(all_isrcs[scope])
        canonical = aliases.get(f"{kind}:{code}") if kind != "TRACK" else None
        inferred = isrc in (row.get("inferred_isrcs") or [])
        standalone_video = (kind == "VIDEO" and canonical == f"VIDEO:{code}" and (inferred or manual)) or manual_unassigned_video
        blocked = (bool(set(observed) - {isrc}) and not manual_unassigned_video) or bool(row.get("native_ada_product"))
        if canonical and canonical != f"ISRC:{isrc}" and not standalone_video:
            blocked = True
        other_owners = claimed_scopes.get(decision_scope(key), set()) - {isrc}
        if other_owners:
            blocked = True
        exact = (
            canonical == f"ISRC:{isrc}" or (kind == "TRACK" and observed == [isrc])
        )
        # Only native, exact identifiers are facts. Every metadata proposal needs a person.
        automatic = not blocked and exact
        if other_owners:
            reason = f"Incluido en el contrato de {', '.join(sorted(other_owners))}."
        elif row.get("native_ada_product"):
            reason = "Producto ADA sin ISRC: conserva su identidad e ingreso propios."
        elif manual_unassigned_video:
            reason = "Asociacion manual de ingresos sin ISRC; los ingresos con ISRC informado conservan su destino."
        elif set(observed) - {isrc}:
            reason = "Código compartido con otros ISRC; no se asignan al tema ingresos de otros assets."
        elif blocked:
            reason = "El catálogo lo identifica como otro asset."
        elif automatic:
            reason = "Asociación exacta y única al ISRC." if exact else row["inference_reason"]
        elif manual:
            reason = "Asociacion manual confirmada desde Sin identificar."
        elif inferred:
            reason = row["inference_reason"]
        else:
            reason = "Sin asociación única confirmada en el catálogo; requiere validación."
        identity = [isrc, kind, code, source, account, observed, canonical, bool(row.get("native_ada_product"))]
        if manual:
            identity.append("manual-reference-v1")
        elif inferred and not exact:
            identity.append(row["inference_signature"])
        signature = hashlib.sha256(json.dumps(
            identity + ([row.get("text_signature")] if kind == "TEXT" else []),
            sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        included = automatic
        status = "automatic" if automatic else "pending"
        if choice:
            if not choice["included"]:
                included, status = False, "excluded"
            elif choice.get("evidence_signature") == signature and not blocked:
                included, status = True, "confirmed"
            else:
                included, status = False, "pending"
                if choice.get("evidence_signature"):
                    reason = "La evidencia cambió desde la confirmación; requiere nueva validación. " + reason
        if blocked and status != "excluded":
            included, status = False, "blocked"
        if decision_scope(key) in excluded_scopes:
            included, status = False, "excluded"
        origins = sorted(set(row.get("content_origins") or []))
        # A code is reference-only only if every source/account is identified UGC.
        # A new unassigned or non-UGC occurrence restores normal financial review.
        ugc_reference = reference_only[scope]
        items.append({
            "key": key, "kind": kind, "code": code, "source": source, "account": account,
            "titles": row.get("titles") or [], "artists": row.get("artists") or [],
            "isrcs": observed, "automatic": automatic, "included": included,
            "status": status, "selectable": not blocked, "reason": reason,
            "evidence_signature": signature,
            "requires_review": inferred and not exact,
            "inference_rule": row.get("inference_rule") if inferred and not exact else None,
            "proposed_isrcs": row.get("inferred_isrcs") or [],
            "reference_group": "ugc" if ugc_reference else "associated",
            "content_origins": origins,
            **({"manual": True} if manual else {}),
            **({"text_reference": row["text_reference"], "related_video_ids": row.get("related_video_ids") or []}
               if kind == "TEXT" else {}),
        })
    pending_codes = set(unresolved_associations(items, overrides))
    return sorted(items, key=lambda item: (item["code"] not in pending_codes,
                                         {"UPC": 0, "TRACK": 1, "VIDEO": 2, "TEXT": 3}[item["kind"]],
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
            if bool(choice.get("manual")) != bool(item.get("manual")):
                raise ValueError("Las asociaciones manuales se confirman desde Sin identificar.")
            if not item["selectable"]:
                raise ValueError(item["reason"])
            if choice.get("evidence_signature") != item["evidence_signature"]:
                raise ValueError("La evidencia cambió desde que la abriste. Actualizá los códigos asociados.")
            if item["kind"] == "TEXT" and choice.get("text_reference") != item.get("text_reference"):
                raise ValueError("La referencia de origen cambio. Volve a elegir el contrato.")


def read_claims(conn: Any) -> dict[str, str]:
    from app.royalty_scope import is_wml
    if is_wml():return {}
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
