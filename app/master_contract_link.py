"""Explicit links use existing contract decisions, never financial-row mutations."""
from copy import deepcopy
import hashlib
import json

from app.master_contract_associations import association_key, candidates, decision_scope
from app.master_contract_income import associated_income_isrc


def validate_row_destinations(rows, old_index, new_index, keys, isrc):
    keys = set(keys)
    affected = 0
    for row in rows:
        references = [association_key(kind, row[field], row["source"], row["account"])
            for kind, field in (("VIDEO", "video_id"), ("TRACK", "track_id"), ("UPC", "product_upc")) if row.get(field)]
        if not keys.intersection(references):
            continue
        before, after = associated_income_isrc(row, old_index), associated_income_isrc(row, new_index)
        if (before and before != isrc) or after != isrc:
            raise ValueError("La referencia contiene identificadores de distintos destinos; no se puede asociar entera a este tema.")
        affected += 1
    if not affected:
        raise ValueError("La referencia ya no tiene movimientos disponibles para asociar.")


def prepare_link(reference, isrc, evidence, aliases, claims, choices, release_id, version):
    kind, code = reference["kind"], reference.get("code")
    if kind == "PRODUCT":
        raise ValueError("Este producto sin ISRC conserva su identidad propia; no se puede asignar entero a una cancion.")
    if kind not in {"VIDEO", "TRACK", "UPC"} or not code:
        raise ValueError("Esta referencia no tiene un codigo estable. No se puede asociar solamente por el texto.")
    accounts = {(r["source"], r["account"]) for r in reference["source_accounts"]}
    scope = [row for row in evidence if row["kind"] == kind and row["code"] == code
             and (kind != "TRACK" or (row["source"], row["account"]) in accounts)]
    keys = {association_key(kind, code, source, account) for source, account in accounts}
    proposed = [dict(key=key, included=True, manual=True, evidence_signature="") for key in sorted(keys)]
    available = {row["key"]: row for row in candidates(isrc, scope, aliases, proposed, claims)}
    if not keys or not keys <= available.keys():
        raise ValueError("La referencia cambio o ya no tiene evidencia publicada. Actualiza la lista.")
    for key in keys:
        if not available[key]["selectable"]:
            raise ValueError(available[key]["reason"])
    scopes = {decision_scope(key) for key in keys}
    decisions = [deepcopy(row) for row in choices if row["key"] not in keys
                 and (decision_scope(row["key"]) not in scopes or row["included"])]
    decisions.extend(dict(key=key, included=True, manual=True, evidence_signature=available[key]["evidence_signature"])
                     for key in sorted(keys))
    if len(decisions) > 2000:
        raise ValueError("El contrato supera el limite de 2000 decisiones de codigos asociados.")
    signature = hashlib.sha256(json.dumps([reference, isrc, release_id, version,
        [(key, available[key]["evidence_signature"]) for key in sorted(keys)]],
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"reference_signature": signature, "choices": decisions, "keys": sorted(keys)}
