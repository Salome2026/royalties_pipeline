"""Optional columns on the ordinary Excel results; never select or add income."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import json
import math
from zoneinfo import ZoneInfo

import polars as pl

from app.master_contracts import parse_artists, validate_split, _period_start, _period_end
from app.master_contract_income import associated_income_isrc
from app.royalty_reports.contractual import allocation_rows, beneficiary_key


def freeze_snapshot(frame: pl.DataFrame, contracts: list[dict], manifest: dict) -> dict:
    from app.master_contract_income import income_association_index, published_unassigned_income
    from app.master_contract_metadata import infer_video_evidence, with_external_titles
    from scripts.lib.catalog_report_filter import catalog_alias_lookup
    from google.cloud import storage

    release = manifest.get("release_id")
    if not release:
        raise ValueError("Falta la version publicada para verificar el reparto del Excel.")
    _, evidence = published_unassigned_income(release)
    catalog = frame.to_dicts()
    metadata = manifest.get("objects", {}).get("catalog_release_metadata.parquet")
    if metadata:
        content = storage.Client().bucket(manifest["bucket"]).blob(
            metadata["object"], generation=int(metadata["generation"])).download_as_bytes()
        catalog = with_external_titles(catalog, pl.read_parquet(BytesIO(content)).to_dicts())
    choices = {row["isrc"]: row["split"].get("code_association_overrides") or [] for row in contracts}
    claims = {choice["key"]: root for root, items in choices.items() for choice in items if choice.get("included")}
    aliases = {row["alias_catalog_key"]: row["catalog_key"] for row in catalog_alias_lookup(catalog=frame).to_dicts()}
    index = income_association_index(infer_video_evidence(catalog, evidence), aliases, choices, claims)
    fields = ("catalog_key", "asset_isrc", "artist_statement", "catalog_artists")
    return {"schema_version": 1, "kind": "excel_contract_columns", "release_id": release,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "as_of": datetime.now(ZoneInfo("America/New_York")).date().isoformat(),
        "contracts": deepcopy(contracts), "catalog": [{key: row.get(key) for key in fields} for row in catalog],
        "associations": index}


def require_snapshot(snapshot: dict | None) -> dict:
    if not snapshot or snapshot.get("schema_version") != 1 or snapshot.get("kind") != "excel_contract_columns":
        raise ValueError("Falta la copia de contratos del pedido de Excel.")
    if not snapshot.get("release_id") or not snapshot.get("as_of"):
        raise ValueError("La copia de contratos no tiene version o fecha.")
    if not isinstance(snapshot.get("contracts"), list) or not isinstance(snapshot.get("catalog"), list):
        raise ValueError("La copia de contratos del Excel esta incompleta.")
    index = snapshot.get("associations") or {}
    if any(not isinstance(index.get(name), dict) for name in ("included", "excluded")):
        raise ValueError("Falta la validacion de asociados del Excel.")
    return snapshot


def _text(columns: set[str], names: tuple[str, ...]) -> pl.Expr:
    values = [pl.col(name).cast(pl.String, strict=False).str.strip_chars().replace("", None)
              for name in names if name in columns]
    return pl.coalesce(values) if values else pl.lit(None, dtype=pl.String)


def reference_fragments(frame: pl.LazyFrame) -> pl.DataFrame:
    from scripts.build_keyword_royalty_report import report_identity_expr
    columns = set(frame.collect_schema().names())
    track = pl.when(_text(columns, ("source",)) == "ada").then(
        _text(columns, ("source_asset_id", "catalog_number"))).otherwise(
        _text(columns, ("track_id", "Label Track ID", "Track ID", "gpid")))
    keys = ["identity", "source", "account", "statement_period", "asset_isrc",
            "product_upc", "video_id", "track_id", "catalog_number"]
    return frame.select(
        report_identity_expr(columns).alias("identity"),
        *[_text(columns, (name,)).fill_null("").alias(name) for name in ("source", "account")],
        _text(columns, ("statement_period",)).str.slice(0, 7).alias("statement_period"),
        _text(columns, ("asset_isrc", "isrc", "ISRC", "Asset ISRC")).alias("asset_isrc"),
        _text(columns, ("product_upc", "UPC Code", "UPC")).alias("product_upc"),
        _text(columns, ("video_id", "Video ID", "VideoId")).alias("video_id"),
        track.alias("track_id"),
        _text(columns, ("catalog_number",)).alias("catalog_number"),
        pl.col("amount_usd"),
    ).group_by(keys).agg(pl.col("amount_usd").sum()).collect(engine="streaming")


def _credit_names(row: dict) -> list[str]:
    names = row.get("catalog_artists")
    if isinstance(names, list):
        return [name for name in names if isinstance(name, str) and name.strip()]
    return parse_artists(row.get("artist_statement") or "", "catalog")


def _contract_names(split: dict) -> list[str]:
    names = []
    for agreement in split.get("agreements") or []:
        if agreement.get("commercialization") == "distribution":
            names.extend(item.get("name") for item in agreement.get("distribution_recipients") or [])
            if not agreement.get("distribution_recipients"):
                names.append(agreement.get("company_name") or "Indyana")
        names.extend(owner.get("name") for owner in agreement.get("owners") or [])
        allocation = agreement.get("allocation") or split
        for item in [{"artist": allocation.get("principal"), "rule": allocation.get("principal_rule")},
                     *(allocation.get("participants") or [])]:
            names.append(item.get("artist"))
            rule = item.get("rule") or {}
            names.append(rule.get("retained_recipient"))
            names.extend(part.get("name") for part in rule.get("beneficiaries") or [])
    return [name.strip() for name in names if isinstance(name, str) and name.strip()]


def participant_columns(summary: pl.DataFrame, fragments: pl.DataFrame, snapshot: dict,
                        keywords: list[str], scope: str) -> tuple[list[str], list[dict]]:
    require_snapshot(snapshot)
    if scope not in {"all", "matching"}:
        raise ValueError("La seleccion de participantes del Excel no es valida.")
    contracts = {row["isrc"]: row for row in snapshot["contracts"]}
    catalog = defaultdict(list)
    for row in snapshot["catalog"]:
        key = row.get("catalog_key") or ("ISRC:" + row["asset_isrc"] if row.get("asset_isrc") else "")
        catalog[key].extend(_credit_names(row))
    by_identity = defaultdict(list)
    for item in fragments.to_dicts():
        by_identity[item["identity"]].append(item)
    prepared = {}
    registry = {}
    results = []

    def register(names):
        keys = set()
        for name in names:
            key = beneficiary_key(name)
            if key:
                registry.setdefault(key, name.strip())
                keys.add(key)
        return keys

    def rules(root):
        if root not in prepared:
            saved = contracts.get(root) or {}
            split = saved.get("split") or {}
            agreements = split.get("agreements") or []
            rows = []
            if saved.get("is_closed") and agreements:
                try:
                    validate_split(split, True, False)
                    for agreement in agreements:
                        shares = allocation_rows(agreement, split)
                        rows.append((_period_start(agreement["effective_from"]),
                            _period_end(agreement["effective_until"]) if agreement.get("effective_until") else _period_start(snapshot["as_of"]), shares))
                except (ValueError, TypeError, KeyError, ZeroDivisionError):
                    rows = []
            prepared[root] = rows
        return prepared[root]

    for row in summary.to_dicts():
        identity = row["_report_identity"]
        pieces = by_identity.get(identity, [])
        row_keys = register(catalog.get(identity, []) or parse_artists(row.get("artist_statement_style") or "", "catalog"))
        amounts = defaultdict(float)
        rates = defaultdict(set)
        applied = False
        for piece in pieces:
            root = identity[5:] if identity.startswith("ISRC:") else (
                piece.get("asset_isrc") or associated_income_isrc(piece, snapshot["associations"]))
            if not root:
                continue
            row_keys |= register(catalog.get("ISRC:" + root, []))
            saved = contracts.get(root) or {}
            row_keys |= register(_contract_names(saved.get("split") or {}))
            month = piece.get("statement_period")
            if not month:
                continue
            try:
                day = _period_start(month)
            except ValueError:
                continue
            for start, end, shares in rules(root):
                if not start <= day <= end:
                    continue
                value = float(piece["amount_usd"] or 0)
                applied = True
                combined = defaultdict(float)
                for share in shares:
                    key = next(iter(register([share["artist"]])))
                    row_keys.add(key)
                    combined[key] += float(share["percent"]) / 100
                for key, percent in combined.items():
                    amounts[key] += value * percent
                for key in row_keys:
                    rates[key].add(combined.get(key, 0.0))
                break
        total = float(row.get("amount_usd") or 0)
        reconciled = bool(pieces) and math.isclose(sum(float(p["amount_usd"] or 0) for p in pieces), total, rel_tol=1e-9, abs_tol=0.00001)
        cells = {}
        if applied and reconciled:
            for key in row_keys:
                percentage = amounts[key] / total if abs(total) > 1e-12 else (
                    None if abs(amounts[key]) > 1e-12 else next(iter(rates[key])) if len(rates[key]) == 1 else None)
                cells[key] = (percentage, amounts[key])
        results.append(cells)
    names = sorted(registry, key=lambda key: (key != "indyana", key))
    if scope == "matching":
        from scripts.lib.text_search import normalize_search_text
        import re
        terms = [normalize_search_text(term) for term in keywords if term.strip()]
        def matches(key):
            name = normalize_search_text(registry[key])
            compact = re.sub(r"[\s_-]+", "", name)
            return any(term in name or re.sub(r"[\s_-]+", "", term) in compact for term in terms)
        names = [key for key in names if matches(key)]
    return [registry[key] for key in names], [{registry[key]: item.get(key) for key in names} for item in results]


def enrich_tables(tables: dict, summary: pl.DataFrame, frame: pl.LazyFrame, snapshot: dict,
                  keywords: list[str], scope: str) -> None:
    import pandas as pd
    names, values = participant_columns(summary, reference_fragments(frame), snapshot, keywords, scope)
    table = tables["resumen por tema"]
    if len(names) * 2 + len(table.columns) > 16384:
        raise ValueError("La cantidad de participantes supera el limite de columnas de Excel.")
    formats = {}
    columns = [table]
    for name in names:
        amount_name = "Importe " + name
        columns.append(pd.Series([item[name][0] if item[name] is not None else None for item in values], index=table.index, name=name))
        columns.append(pd.Series([item[name][1] if item[name] is not None else None for item in values], index=table.index, name=amount_name))
        position = len(table.columns) + len(formats) + 1
        formats[position] = "0.00%"
        formats[position + 1] = '$#,##0.00'
    table = pd.concat(columns, axis=1)
    table.attrs["contract_formats"] = formats
    tables["resumen por tema"] = table
