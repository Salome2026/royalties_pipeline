"""Bind the current operational contracts to the already selected publication."""

import polars as pl

from app.distribution_contracts import list_distribution_contracts
from app.operational_db import operational_connect
from app.royalty_reports.contract_filter import freeze_filter
from app.royalty_reports.contract_snapshot import (
    contract_artist_names, contract_catalog_rows, freeze_contract_associations,
    freeze_contract_snapshot, stored_contracts,
)
from app.royalty_reports.excel_contracts import freeze_snapshot
from .publication import PublicationError, read_json


def distribution_options():
    with operational_connect() as conn:
        return list_distribution_contracts(conn)


def artist_options(paths):
    catalog = contract_catalog_rows(pl.read_parquet(paths["marts/catalog_master.parquet"]))
    with operational_connect() as conn:
        return contract_artist_names(stored_contracts(conn), catalog)


def capture_contracts(manifest, params, release, paths):
    numbers = params.get("distribution_contract_numbers")
    enriched = params.get("include_contracts")
    mode = params.get("executive_mode")
    payout = mode in {"contractual", "artist_settlement"}
    if not (numbers or enriched or payout):
        return manifest

    with operational_connect() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        contracts = stored_contracts(conn)
        templates = list_distribution_contracts(conn) if numbers else []

    catalog = pl.read_parquet(paths["marts/catalog_master.parquet"])
    metadata = pl.read_parquet(paths["marts/catalog_release_metadata.parquet"])
    evidence = read_json(paths["contracts/published_evidence.json"])
    if numbers or enriched:
        snapshot = freeze_snapshot(catalog, contracts, manifest, published_evidence=evidence,
                                   release_metadata=metadata,
                                   allocation_document=read_json(paths["marts/product_income_allocations.json"]))
        if enriched:
            manifest["excel_contract_snapshot"] = snapshot
        if numbers:
            manifest["distribution_contract_filter"] = freeze_filter(numbers, templates, snapshot)
    if payout:
        guard = read_json(paths["contracts/identity_guard.json"])
        if not guard["published_cache_found"] or not isinstance(guard["keys"], list):
            raise PublicationError("Falta la validación de identidades de la publicación.")
        snapshot = freeze_contract_snapshot(params["contract_artists"], contract_catalog_rows(catalog), contracts)
        if mode == "artist_settlement":
            snapshot["template_version"] = "artist-settlement-v1"
        snapshot = freeze_contract_associations(
            snapshot, catalog, contracts, manifest["release_id"], input_manifest=manifest,
            ranking_guard=frozenset(guard["keys"]), release_metadata=metadata,
            unassigned_income=(read_json(paths["contracts/published_rows.json"]), evidence),
        )
        if numbers:
            roots = set(manifest["distribution_contract_filter"]["isrcs"])
            snapshot["catalog"] = [row for row in snapshot["catalog"] if row["isrc"] in roots]
            snapshot["contracts"] = [row for row in snapshot["contracts"] if row["isrc"] in roots]
        manifest["contract_snapshot"] = snapshot
        manifest["catalog_dashboard"] = {"release_id": release["components"]["eligible"]["manifest"]["release_id"]}
    return manifest
