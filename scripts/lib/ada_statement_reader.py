"""Certified ADA Excel-only native reader. No operational writers or financial policies."""

from __future__ import annotations

import hashlib

import itertools

import json

import math

import posixpath

import re

import unicodedata

import xml.etree.ElementTree as ET

import zipfile

from collections import defaultdict

from datetime import datetime

from decimal import Decimal, InvalidOperation, localcontext

from pathlib import Path
from functools import lru_cache

import polars as pl

RULE = "ADA-LECTURA-1"

READER = "ADA-EXCEL-READER-1"

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

FIELDS = ["Marketing Owner", "Artist Name", "Project Title", "Catalogue Number", "UPC",
          "Local Product Number", "ISRC", "Parent Product ID", "Catalogue Title", "Reported Month",
          "Territory", "Country Code", "Country Description", "Price Name", "Revenue Type Desc",
          "Sales", "RTL", "PPD", "RBP", "Exch Rate:", "Receipts Value", "Artist Royalties",
          "Distribution Fees", "Mechanical Fees", "Admin Fees", "Upload Fees", "Other Fees",
          "Royalty Earnings"]

ACCOUNTS = {"99500": "indyana_records", "99205": "mawz"}

ZERO_COMPONENTS = ["Artist Royalties", "Mechanical Fees", "Admin Fees", "Upload Fees", "Other Fees"]

FOOTERS = {"sub totals", "previously accounted deductions", "totals"}

class ReadError(ValueError):
    pass

def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def stable_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

def month(value: str | None, consumption: bool = False) -> str:
    value = str(value or "").strip()
    pattern = r"\d{6}" if consumption else r"\d{4}-\d{2}"
    if not re.fullmatch(pattern, value):
        raise ReadError(f"Invalid month: {value!r}")
    try:
        parsed = datetime.strptime(value, "%Y%m" if consumption else "%Y-%m")
    except ValueError as error:
        raise ReadError(f"Invalid month: {value!r}") from error
    return parsed.strftime("%Y-%m")

def filename_identity(path: Path, original_account: str) -> tuple[str, str]:
    m = re.fullmatch(r"(\d+)_(\d{6})_(\d{6})_\1_DTL\.xlsx", path.name, re.I)
    if not m or m[1] != original_account or m[1] not in ACCOUNTS or m[2] != m[3]:
        raise ReadError(f"Account/filename mismatch: {path.name}, expected {original_account}")
    return ACCOUNTS[original_account], month(m[2], True)

def select_files(paths: list[tuple[Path, str]]) -> tuple[list[tuple[Path, str]], list[str]]:
    selected, excluded = {}, []
    seen_hashes = set()
    for path, account in sorted(paths, key=lambda item: str(item[0])):
        if path.name.startswith("~$"):
            excluded.append(path.name)
            continue
        normalized, period = filename_identity(path, account)
        sha = digest(path)
        scope = (normalized, period)
        if (*scope, sha) in seen_hashes:
            excluded.append(f"resend:{path}")
            continue
        if scope in selected:
            raise ReadError(f"Explicit replacement/revision required: {scope}")
        selected[scope] = (path, account)
        seen_hashes.add((*scope, sha))
    return [selected[key] for key in sorted(selected)], excluded

def decimal_value(value: str | None, path: Path, row: int, field: str) -> Decimal:
    try:
        result = Decimal(str(value).replace(",", "").strip())
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ReadError(f"{path.name}!{row}, {field}: invalid required number {value!r}") from error

def legacy_number(value: str | None):
    if value is None:
        return None
    return float(value) if any(c in value for c in ".eE") else int(value)

def compatibility_net(gross: str, fees: str) -> float:
    # Matches the approved openpyxl -> string -> Decimal -> Float64 projection.
    return float(Decimal(str(legacy_number(gross))) - Decimal(str(legacy_number(fees))))

def projection_bound(gross: float, fees: float, net: float) -> Decimal:
    # Fixed before reading: includes source float/string and final rounding stages.
    return sum((Decimal.from_float(math.ulp(v)) * 2 for v in (gross, fees, net)), Decimal(0))

def clean_isrc(value: str | None) -> str | None:
    value = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    return value if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}\d{7}", value) else None

def valid_gtin(value: str | None) -> bool:
    if not value or not re.fullmatch(r"(?:[0-9]{8}|[0-9]{12,14})", value) or not int(value):
        return False
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(value[-2::-1]))
    return (total + int(value[-1])) % 10 == 0

def release_codes(records: list[dict]) -> None:
    contexts = defaultdict(dict)
    for r in records:
        upc, parent = r.get("UPC"), r.get("Parent Product ID")
        upc = upc if valid_gtin(upc) else None
        parent = parent if valid_gtin(parent) else None
        if upc and parent and upc.zfill(14) != parent.zfill(14):
            raise ReadError(f"Contradictory UPC/Parent Product ID: row {r['source_row']}")
        r["product_upc"] = upc or parent
        r["product_upc_source"] = "UPC" if upc else "Parent Product ID" if parent else None
        r["product_upc_status"] = "reported" if upc or parent else "unavailable"
        if r["asset_isrc"] and r["product_upc"]:
            contexts[(r.get("Project Title"), r.get("Artist Name"))].setdefault(r["product_upc"].zfill(14), set()).add(r["product_upc"])
    for r in records:
        key = (r.get("Project Title"), r.get("Artist Name"))
        proof = contexts[key]
        if (not r["asset_isrc"] and not r["product_upc"] and all(key)
                and r.get("Catalogue Title") == key[0] and len(proof) == 1):
            r["product_upc"] = min(next(iter(proof.values())))
            r["product_upc_source"] = "same_statement_release"
            r["product_upc_status"] = "derived_release"

def iter_xml_rows(z: zipfile.ZipFile, member: str, strings: list[str]):
    with z.open(member) as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag != f"{{{NS['s']}}}row":
                continue
            cells = {}
            for cell in element.findall("s:c", NS):
                address = cell.attrib["r"]
                kind = cell.attrib.get("t", "n")
                v = cell.find("s:v", NS)
                raw = v.text if v is not None else None
                if kind == "s" and raw is not None:
                    value = strings[int(raw)]
                elif kind == "inlineStr":
                    value = "".join(t.text or "" for t in cell.findall(".//s:t", NS))
                else:
                    value = raw
                cells[re.sub(r"\d+$", "", address)] = {
                    "value": value, "type": kind, "formula": cell.findtext("s:f", namespaces=NS),
                }
            yield int(element.attrib["r"]), cells
            element.clear()

def read_excel(path: Path, original_account: str) -> tuple[pl.DataFrame, dict]:
    account, statement = filename_identity(path, original_account)
    sha = digest(path)
    records, controls, control_issues = [], [], []
    package = f"ada:{original_account}:{statement}:{sha}"
    header_map = None
    header_evidence, header_values = [], {}
    scales = defaultdict(int)
    with zipfile.ZipFile(path) as z:
        if "[Content_Types].xml" not in z.namelist() or any(v.lower().endswith("vbaproject.bin") for v in z.namelist()):
            raise ReadError(f"Uncertified XLSX package: {path.name}")
        book = ET.fromstring(z.read("xl/workbook.xml"))
        sheets = book.find("s:sheets", NS)
        if len(sheets) != 1 or sheets[0].attrib["name"] != "Distribution Statement":
            raise ReadError(f"Uncertified sheet set: {path.name}")
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = next(r.attrib["Target"] for r in rels if r.attrib["Id"] == sheets[0].attrib[REL])
        member = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = ["".join(t.text or "" for t in e.findall(".//s:t", NS))
                       for e in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("s:si", NS)]
        for row_number, cells in iter_xml_rows(z, member, strings):
            values = [(col, str(c["value"] or "").strip()) for col, c in cells.items()]
            if header_map is None:
                for i, (_, text) in enumerate(values[:-1]):
                    if text.rstrip(":") in {"Contract", "Royalties Statement for Period", "Currency"}:
                        header_values[text.rstrip(":")] = values[i + 1][1]
                names = [v for _, v in values if v]
                if "Artist Name" not in names:
                    if row_number > 40:
                        raise ReadError(f"Header missing: {path.name}")
                    continue
                if len(set(names)) != len(names):
                    raise ReadError(f"Duplicate header: {path.name}")
                expected = set(FIELDS) - ({"Parent Product ID"} if "Parent Product ID" not in names else set())
                if set(names) != expected:
                    raise ReadError(f"Uncertified column map: {path.name}: {sorted(set(names) ^ expected)}")
                if not header_values.get("Contract", "").startswith(original_account + "-"):
                    raise ReadError(f"Contract mismatch: {path.name}")
                stamp = datetime.strptime(statement, "%Y-%m").strftime("%m/%y")
                if re.sub(r"\s", "", header_values.get("Royalties Statement for Period", "")) != stamp + "-" + stamp:
                    raise ReadError(f"Workbook period mismatch: {path.name}")
                if header_values.get("Currency", "USD") != "USD":
                    raise ReadError(f"Uncertified currency: {path.name}")
                header_map = {name: col for col, name in values if name}
                header_evidence = [{"column": col, "original": cells[col]["value"], "normalized": name}
                                   for name, col in header_map.items()]
                layout = stable_hash(sorted(header_map))
                continue
            if not any(text for _, text in values):
                continue
            r = {field: cells.get(header_map.get(field), {}).get("value") for field in FIELDS}
            r = {k: (str(v).strip() if v is not None and str(v).strip() else None) for k, v in r.items()}
            first = next((v for _, v in values if v), "").rstrip(":").lower()
            if first in FOOTERS and not (r["ISRC"] or r["Catalogue Number"]):
                controls.append({"source_row": row_number, "label": first, "cells": cells})
                continue
            for field in ["Artist Name", "Catalogue Title", "Project Title"]:
                if r[field] and cells.get(header_map[field], {}).get("type") not in {"s", "inlineStr", "str"}:
                    raise ReadError(f"Uncertified credit/title cell type: {path.name}!{row_number}: {field}")
            if any(c["formula"] and c["value"] is None for col, c in cells.items()
                   if col in {header_map[f] for f in ["Receipts Value", "Distribution Fees", "Sales", *ZERO_COMPONENTS]}):
                raise ReadError(f"Required formula missing cache: {path.name}!{row_number}")
            for field in ["Receipts Value", "Distribution Fees", "Sales", *ZERO_COMPONENTS]:
                c = cells.get(header_map[field], {})
                if c.get("type") in {"e", "b", "s", "inlineStr"}:
                    raise ReadError(f"Uncertified numeric cell type: {path.name}!{row_number}: {field}")
            with localcontext() as context:
                context.prec = 80
                nums = {f: decimal_value(r[f], path, row_number, f) for f in ["Receipts Value", "Distribution Fees", "Sales", *ZERO_COMPONENTS]}
                if any(nums[f] != 0 for f in ZERO_COMPONENTS):
                    raise ReadError(f"Unexpected financial component: {path.name}!{row_number}")
                for f, v in nums.items():
                    scales[f] = max(scales[f], max(0, -v.as_tuple().exponent))
                native_net = nums["Receipts Value"] - nums["Distribution Fees"]
                try:
                    earnings = decimal_value(r["Royalty Earnings"], path, row_number, "Royalty Earnings")
                    status = "equal" if earnings == native_net else "different"
                except ReadError:
                    earnings, status = None, "unavailable"
                if status != "equal":
                    control_issues.append({"source_row": row_number, "status": status, "net": str(native_net), "earnings": r["Royalty Earnings"]})
            isrc = clean_isrc(r["ISRC"])
            if not isrc and not r["Catalogue Number"]:
                raise ReadError(f"Missing identity: {path.name}!{row_number}")
            consumed = month(r["Reported Month"], True)
            formulas = {col: c["formula"] for col, c in cells.items() if c["formula"]}
            r.update({
                "source": "ada", "account": account, "ada_account_id": original_account,
                "statement_period": statement, "transaction_month": consumed, "receipt_month": None,
                "consumption_precision": "month", "currency_original": "USD", "source_sheet": "royalty_detail",
                "native_source_sheet": "Distribution Statement", "source_row": row_number,
                "statement_file_name": path.name, "statement_file_hash": sha,
                "package_id": package, "package_revision": sha, "layout_signature": layout,
                "source_rule_version": RULE, "reader_version": READER, "output_contract_version": "CAT-003-1.2",
                "observation_id": stable_hash([package, "Distribution Statement", row_number]),
                "native_entity_key": "ISRC:" + isrc if isrc else f"ADA:{original_account}:CATALOG:{r['Catalogue Number']}",
                "asset_isrc": isrc, "identity_status": "invalid_isrc_native_fallback" if r["ISRC"] and not isrc else "resolved",
                "catalog_number": r["Catalogue Number"], "source_asset_id": r["Catalogue Number"],
                "parent_product_id": r["Parent Product ID"], "artist_statement_original": r["Artist Name"],
                "track_statement_style": r["Catalogue Title"], "release_statement_style": r["Project Title"],
                "store_name": r["Territory"], "territory": r["Country Code"],
                "use_type": r["Revenue Type Desc"], "product_type": r["Price Name"],
                "native_gross": str(nums["Receipts Value"]), "native_fees": str(nums["Distribution Fees"]),
                "native_net": str(native_net), "native_units": str(nums["Sales"]),
                "gross_royalty_usd": float(nums["Receipts Value"]), "deductible_fees_usd": float(nums["Distribution Fees"]),
                "amount_usd": compatibility_net(r["Receipts Value"], r["Distribution Fees"]),
                "units": float(nums["Sales"]), "earnings_control_status": status,
                "raw_cell_types": json.dumps({col: c["type"] for col, c in cells.items()}, separators=(",", ":")),
                "raw_formulas": json.dumps(formulas, separators=(",", ":")),
            })
            records.append(r)
    if header_map is None:
        raise ReadError(f"Header missing: {path.name}")
    release_codes(records)
    metadata = {"file": path.name, "account": account, "original_account": original_account,
                "sha256": sha, "statement": statement, "rows": len(records), "header": header_evidence,
                "layout_signature": layout, "controls": controls, "earnings_issues": control_issues,
                "decimal_scales": dict(scales), "certifiable": not control_issues}
    return pl.DataFrame(records, infer_schema_length=None) if records else pl.DataFrame(), metadata


def validate_projection(frame: pl.DataFrame) -> dict:
    maximum_digits = 0
    with localcontext() as context:
        context.prec = 160
        for row in frame.select("statement_file_name", "source_row", "native_gross", "native_fees", "native_net",
                                "gross_royalty_usd", "deductible_fees_usd", "amount_usd", "units").iter_rows(named=True):
            for field in ["native_gross", "native_fees", "native_net"]:
                value = Decimal(row[field])
                required = len(value.as_tuple().digits) + abs(value.as_tuple().exponent)
                maximum_digits = max(maximum_digits, required)
                if required > 60:
                    raise ReadError(f"Uncertified decimal capacity: {row['statement_file_name']}!{row['source_row']}: {field}")
            if Decimal(row["native_gross"]) - Decimal(row["native_fees"]) != Decimal(row["native_net"]):
                raise ReadError("Native Decimal computation lost precision")
            if not all(math.isfinite(row[f]) for f in ["gross_royalty_usd", "deductible_fees_usd", "amount_usd", "units"]):
                raise ReadError(f"Insufficient Float64 capacity: {row['statement_file_name']}!{row['source_row']}")
    return {"rows_validated": frame.height, "max_digits_plus_abs_exponent": maximum_digits,
            "allowed_reference_capacity": 60, "exact_check_context": 160, "overflow_or_underflow_accepted": False}


@lru_cache(maxsize=1)
def known_controls() -> dict:
    return json.loads(Path(__file__).with_name("ada_known_controls.json").read_text(encoding="utf-8"))


def control_disposition(row: dict) -> str:
    if row["earnings_control_status"] == "equal":
        return "equal"
    rule = known_controls()
    if (row.get("source_rule_version") == rule["source_rule_version"]
            and row.get("ada_account_id") == rule["account"]
            and row.get("statement_period") == rule["statement_period"]
            and row.get("statement_file_hash") == rule["file_sha256"]):
        checksum = stable_hash({field: row.get(field) for field in rule["fields"]})
        if any(item["source_row"] == row["source_row"] and item["control_sha256"] == checksum
               for item in rule["observations"]):
            return "accepted_known_auxiliary_observation"
    return "review_required"


def read_operational_package(path: Path, original_account: str) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
    """Keep the approved operational projection separate from exact native evidence."""
    native, metadata = read_excel(path, original_account)
    if not native.is_empty():
        metadata["projection_capacity"] = validate_projection(native)
    headers = [item for item in metadata["header"] if item["normalized"] != "Royalty Earnings"]
    fields = [item["normalized"] for item in headers]
    records, dispositions = [], []
    for row in native.iter_rows(named=True):
        disposition = control_disposition(row)
        if disposition == "review_required":
            raise ReadError(f"ADA {path.name}!{row['source_row']}: Royalty Earnings requiere revision; no se publica un paquete parcial")
        dispositions.append(disposition)
        kinds = json.loads(row["raw_cell_types"])
        record = {}
        for item in headers:
            field, column = item["normalized"], item["column"]
            value = row.get(field)
            record[field] = str(legacy_number(value)) if value is not None and kinds.get(column) == "n" else value
        record.update({name: row[name] for name in ["ada_account_id", "statement_period", "transaction_month",
            "gross_royalty_usd", "deductible_fees_usd", "amount_usd"]})
        record["catalog_number"] = record["Catalogue Number"]
        record["parent_product_id"] = record.get("Parent Product ID")
        record["ada_explicit_upc"] = record.get("UPC")
        records.append(record)
    schema = {field: pl.String for field in fields}
    schema.update({name: pl.String for name in ["catalog_number", "parent_product_id", "ada_explicit_upc",
                                               "ada_account_id", "statement_period", "transaction_month"]})
    schema.update({name: pl.Float64 for name in ["gross_royalty_usd", "deductible_fees_usd", "amount_usd"]})
    operational = pl.DataFrame(records, schema=schema)
    if not native.is_empty():
        native = native.with_columns(pl.Series("earnings_control_disposition", dispositions, dtype=pl.String))
    return operational, native, {**metadata, "control_acceptance_version": known_controls()["acceptance_version"],
                                  "adoption_certifiable": True}
