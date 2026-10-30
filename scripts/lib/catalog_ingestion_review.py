"""Grouped, non-financial reading incidents over the existing native evidence."""
from collections import defaultdict
import json
from pathlib import Path
import re
import unicodedata

import polars as pl

from .ingestion_controls import CONTROL_FILE, SOURCES, VERSION, validate_no_failed_batches
from .catalog_manual_metadata import CORRECTIONS_PATH

SCHEMA = {name: pl.String for name in ("row_type", "source", "account", "code", "identity", "details", "base_release_id", "rule")}
BAD_STATUSES = {"contradictory", "conflicting_participants", "reference_mismatch", "tokenization_unresolved", "ambiguous_serialization"}


def normalized_title(value):
    text = unicodedata.normalize("NFKD", str(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\((?:cover|feat\.?[^)]*|featuring[^)]*|ft\.?[^)]*)\)", "", text)
    return " ".join(re.findall(r"\w+", text))


def reading_incidents(catalog: pl.DataFrame) -> list[dict]:
    grouped = defaultdict(lambda: {"identities": set(), "files": set(), "samples": []})
    def add(source, account, code, identity, evidence):
        item = grouped[(source or "catalog", account or "", code)]
        item["identities"].add(identity)
        if evidence.get("statement_file_name"):
            item["files"].add(evidence["statement_file_name"])
        if len(item["samples"]) < 5:
            sample = {key: evidence.get(key) for key in ("field", "raw", "statement_period", "statement_file_name", "statement_file_hash", "source_rule") if evidence.get(key)}
            sample["identity"] = identity
            if sample not in item["samples"]:
                item["samples"].append(sample)
    for row in catalog.iter_rows(named=True):
        identity = row.get("catalog_key") or row.get("asset_isrc") or ""
        entries = json.loads(row.get("catalog_artist_evidence") or "[]")
        def inspect(entry, parent=None):
            if not isinstance(entry, dict):
                return
            entry = {**(parent or {}), **entry}
            source, account = entry.get("source"), entry.get("account")
            for credit in entry.get("credits") or []:
                if credit.get("role") == "unknown":
                    add(source, account, "UNKNOWN_ROLE", identity, {**entry, "raw": credit.get("role_original")})
            if entry.get("manual_protected") or row.get("catalog_manual_correction_id"):
                return
            statuses = {entry.get(key) for key in ("participant_resolution_status", "native_resolution_status", "status", "grammar_status")}
            bad = statuses & (BAD_STATUSES | {"ambiguous", "ambiguous_grammar"})
            if not row.get("catalog_artists") and row.get("asset_isrc") and "incomplete" in statuses:
                bad.add("incomplete")
            if bad and entry.get("field") != "Product Artist":
                conflict = any("conflict" in status or status == "contradictory" for status in bad)
                raw = entry.get("raw") or entry.get("artist_catalog_style") or entry.get("Artist Name")
                add(source, account, "PARTICIPANTS_CONFLICT" if conflict else "UNRESOLVED_CREDIT", identity, {**entry, "raw": raw})
            for key in ("observations", "native_observations", "evidence"):
                nested = entry.get(key)
                if isinstance(nested, list):
                    for child in nested:
                        inspect(child, {key: entry.get(key) for key in ("source", "account", "source_rule")})
        for entry in entries:
            inspect(entry)
    result = []
    for (source, account, code), item in sorted(grouped.items()):
        result.append({"row_type": "incident", "source": source, "account": account, "code": code, "identity": "",
            "details": json.dumps({"status": "needs_metadata_review", "economic_status": "preserved", "identity_count": len(item["identities"]),
                "identities": sorted(item["identities"]), "files": sorted(item["files"]), "samples": item["samples"],
                "action": "Revisar la regla o confirmar evidencia; no inferir porcentajes ni reasignar ingresos."}, ensure_ascii=True),
            "base_release_id": "", "rule": VERSION})
    return result


def native_title_incidents(frame: pl.LazyFrame) -> list[dict]:
    """Compare native track titles only, never associated-video/title variants."""
    columns = set(frame.collect_schema().names())
    required = {"source", "account", "asset_isrc", "statement_file_name"}
    if not required <= columns:
        return []
    approved = {row["catalog_key"] for row in json.loads(CORRECTIONS_PATH.read_text(encoding="utf-8"))["corrections"] if row.get("confirmed_by") and row.get("track_title")}
    source_fields = {"fuga": "Asset Title", "onerpm": "Track Title", "ada": "Catalogue Title", "orchard": "TRACK", "soundon": "Track Title", "dashgo": "Track Title"}
    groups = defaultdict(lambda: {"identities": set(), "files": set(), "samples": []})
    for source, field in source_fields.items():
        if field not in columns:
            continue
        values = (frame.filter((pl.col("source") == source) & pl.col("asset_isrc").is_not_null())
            .select("account", "asset_isrc", "statement_file_name", pl.col(field).cast(pl.String).alias("title"))
            .unique().collect(engine="streaming"))
        for data in values.partition_by(["account", "asset_isrc"], as_dict=True).values():
            identity = "ISRC:" + str(data["asset_isrc"][0])
            if identity in approved:
                continue
            titles = sorted({normalized_title(value) for value in data["title"].drop_nulls() if str(value).strip()})
            if not any(not (set(a.split()) & set(b.split())) for i, a in enumerate(titles) for b in titles[i + 1:]):
                continue
            group = groups[(source, str(data["account"][0] or ""))]
            group["identities"].add(identity)
            group["files"].update(data["statement_file_name"].drop_nulls().to_list())
            if len(group["samples"]) < 5:
                group["samples"].append({"identity": identity, "field": field, "raw": " | ".join(data["title"].drop_nulls().unique().to_list())})
    return [{"row_type": "incident", "source": source, "account": account, "code": "TITLE_CONTRADICTION", "identity": "", "details": json.dumps({
        "status": "needs_metadata_review", "economic_status": "preserved", "identity_count": len(group["identities"]), "identities": sorted(group["identities"]),
        "files": sorted(group["files"]), "samples": group["samples"], "action": "Comparar titulos nativos de pista y cronologia; no reasignar ingresos."}, ensure_ascii=True),
        "base_release_id": "", "rule": VERSION} for (source, account), group in sorted(groups.items())]


def control_frame(marts: Path, catalog: pl.DataFrame, *, base_release_id="") -> pl.DataFrame:
    validate_no_failed_batches(marts, ignore={"catalog"})
    rows = []
    receipts = [marts / f"ingestion_control_{source}.parquet" for source in SOURCES]
    admitted = {path.stem.removeprefix("ingestion_control_") for path in receipts if path.exists()}
    for path in receipts:
        if path.exists():
            for row in pl.read_parquet(path).iter_rows(named=True):
                rows.append({"row_type": "file", "source": row["source"], "account": row["account"], "code": row["status"], "identity": row["file_name"],
                    "details": json.dumps(row, ensure_ascii=True), "base_release_id": base_release_id, "rule": VERSION})
    for source in admitted:
        review = marts / f"ingestion_control_{source}_review.parquet"
        if review.exists():
            rows.extend({**row, "base_release_id": base_release_id} for row in pl.read_parquet(review).to_dicts())
    raw = marts / "standardized_raw_all_sources.parquet"
    if raw.exists():
        scan = pl.scan_parquet(raw)
        columns = set(scan.collect_schema().names())
        required = {"source", "account", "statement_period", "statement_file_name", "statement_file_hash"}
        if required <= columns:
            kind = pl.col("source_sheet") if "source_sheet" in columns else pl.lit("")
            files = scan.filter(~pl.col("source").is_in(sorted(admitted))).select(*sorted(required), kind.alias("kind")).unique().collect()
            for item in files.iter_rows(named=True):
                record = {"source": item["source"], "account": item["account"], "period": item["statement_period"], "kind": item["kind"],
                    "file_name": item["statement_file_name"], "file_hash": item["statement_file_hash"], "status": "selected", "duplicate_of": "", "rule": "published-provenance"}
                rows.append({"row_type": "file", "source": item["source"], "account": item["account"], "code": "selected", "identity": item["statement_file_name"],
                    "details": json.dumps(record, ensure_ascii=True), "base_release_id": base_release_id, "rule": VERSION})
        rows.extend({**row, "base_release_id": base_release_id} for row in native_title_incidents(scan.filter(~pl.col("source").is_in(sorted(admitted)))))
    rows.extend({**row, "base_release_id": base_release_id} for row in reading_incidents(catalog))
    return pl.DataFrame(rows, schema=SCHEMA).unique().sort("row_type", "source", "account", "code", "identity")


def save_controls(marts: Path, catalog: pl.DataFrame, *, base_release_id="") -> Path:
    frame = control_frame(marts, catalog, base_release_id=base_release_id)
    output = marts / CONTROL_FILE
    temporary = output.with_suffix(".tmp.parquet")
    frame.write_parquet(temporary)
    temporary.replace(output)
    return output
