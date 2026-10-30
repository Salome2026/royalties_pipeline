"""ONErpm artist metadata only; monetary and Shares policies remain separate."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

import polars as pl

from .catalog_manual_metadata import CORRECTIONS_PATH
from .catalog_artist_dictionary import canonical
from .catalog_identity_references import materialize_identity_references
from .fuga_catalog_artists import ARTIST_COLUMNS, parse_catalog_credit


RULE_VERSION = "ONERPM-ARTISTS-1"
METADATA_FILE = "catalog_onerpm_artists.parquet"
SHEETS = {"Summary", "Masters", "Youtube Channels", "Publishing Rights", "Shares In & Out", "Commissions"}
ROLES = {"performer", "featuring", "writer", "musician", "producer", "mixing_engineer", "mastering_engineer", "executive_producer"}
ISRC_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")
XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def name_key(value: str) -> str:
    value = canonical(value)
    text = unicodedata.normalize("NFKD", " ".join(value.split())).casefold()
    return "".join(char for char in text if not unicodedata.combining(char))


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def parse_credits(raw: str) -> dict:
    raw = str(raw or "").strip()
    credits, cursor = [], 0
    pattern = re.compile(r"\s*([^,()]+?)\s*\(\s*([A-Za-z_][A-Za-z_ ]*)\s*\)\s*(?:,\s*|$)")
    while cursor < len(raw):
        match = pattern.match(raw, cursor)
        if not match:
            return {"credits": credits, "artists": [], "performers": [], "status": "ambiguous", "unparsed": raw[cursor:]}
        name, role = " ".join(match[1].split()), " ".join(match[2].split()).casefold()
        credits.append({"name": name, "role_original": match[2], "role": role if role in ROLES else "unknown"})
        cursor = match.end()
    artists, performers = [], []
    for credit in credits:
        for target, roles in ((artists, {"performer", "featuring"}), (performers, {"performer"})):
            if credit["role"] in roles and name_key(credit["name"]) not in {name_key(name) for name in target}:
                target.append(credit["name"])
    return {"credits": credits, "artists": artists, "performers": performers,
            "status": "resolved" if artists else "incomplete", "unparsed": ""}


def resolve(observations: list[dict]) -> dict:
    observations = sorted(observations, key=lambda row: (row["sheet"], row["account"], row["statement"], row["file_hash"], row["row"], row["raw"]))
    incomplete = sum(row["parsed"]["status"] != "resolved" or row["identity_status"] != "resolved" for row in observations)
    state = {"credit_status": "incomplete" if incomplete else "resolved", "incomplete_evidence_count": incomplete}
    valid = [row for row in observations if row["parsed"]["status"] == "resolved" and row["parsed"]["artists"]
             and row["level"] == "track" and row["identity_status"] == "resolved"]
    if not valid:
        return {**state, "artists": [], "status": "incomplete", "principal": None, "principal_status": "unknown"}
    sets = {frozenset(name_key(name) for name in row["parsed"]["artists"]) for row in valid}
    if not all(a <= b or b <= a for a in sets for b in sets):
        return {**state, "artists": [], "status": "contradictory", "principal": None, "principal_status": "uncertain"}
    maximum = max(sets, key=len)
    complete = [row for row in valid if frozenset(name_key(name) for name in row["parsed"]["artists"]) == maximum]
    chosen = min(complete, key=lambda row: (0 if row["sheet"] == "Masters" else 1, -int(row["statement"].replace("-", "")),
                                          row["account"], row["file_hash"], row["sheet"], row["row"]))
    masters = [row for row in valid if row["sheet"] == "Masters" and row["parsed"]["performers"]]
    first = {name_key(row["parsed"]["performers"][0]) for row in masters}
    principal = next((name for name in chosen["parsed"]["artists"] if name_key(name) in first), None) if len(first) == 1 else None
    return {**state, "artists": chosen["parsed"]["artists"], "status": "resolved", "principal": principal,
            "principal_status": "order_only" if principal else "uncertain" if masters else "unknown",
            "reference": {key: chosen[key] for key in ("sheet", "account", "statement", "file_hash", "row")}}


def physical_rows(path: Path, sheet: str) -> list[int]:
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {relation.attrib["Id"]: relation.attrib["Target"] for relation in relations}
        selected = next(item for item in workbook.find(XML_NS + "sheets") if item.attrib["name"] == sheet)
        relation = selected.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = targets[relation]
        member = target.lstrip("/") if target.startswith("/") else "xl/" + target
        rows = []
        with archive.open(member) as stream:
            for _, node in ET.iterparse(stream, events=("end",)):
                if node.tag == XML_NS + "row":
                    number = int(node.attrib["r"])
                    if number > 1 and any(cell.find(XML_NS + "v") is not None or cell.find(XML_NS + "is") is not None for cell in node):
                        rows.append(number)
                    node.clear()
        return rows


def read_file_metadata(path: Path, account: str) -> list[dict]:
    period = re.match(r"^(20\d\d-(?:0[1-9]|1[0-2]))-", path.name)
    if not period:
        raise ValueError(f"ONErpm: nombre de statement no reconocido: {path.name}")
    books = pl.read_excel(path, sheet_id=0, infer_schema_length=None, raise_if_empty=False)
    if set(books) != SHEETS:
        raise ValueError(f"ONErpm: hojas nuevas o faltantes: {path.name}")
    checksum = file_hash(path)
    observations = []
    for sheet in ("Masters", "Shares In & Out"):
        frame = books[sheet]
        if frame.is_empty():
            continue
        headers = [column.strip().lstrip("\ufeff") for column in frame.columns]
        if len(headers) != len(set(headers)):
            raise ValueError("ONErpm: columnas duplicadas")
        frame = frame.rename(dict(zip(frame.columns, headers)))
        required = {"Artists", "Product Type", "ISRC", "UPC"} if sheet == "Masters" else {"Artists", "Product Type", "ID", "Parent ID"}
        if not required <= set(frame.columns):
            raise ValueError(f"ONErpm: faltan columnas de identidad en {sheet}")
        rows = physical_rows(path, sheet)
        if len(rows) != frame.height:
            raise ValueError(f"ONErpm: no se puede garantizar la fila original de {path.name}/{sheet}")
        metadata_columns = [name for name in ("ISRC", "UPC", "ID", "Parent ID", "Product Type", "Artists", "Track Title", "Album Title", "Title") if name in frame.columns]
        metadata = frame.with_columns(pl.Series("_excel_row", rows)).group_by(metadata_columns).agg(pl.col("_excel_row").min())
        for row in metadata.iter_rows(named=True):
            product = str(row.get("Product Type") or "").strip()
            accepted = {"Track", "Video Track", "Album"} if sheet == "Masters" else {"Track", "Video Track", "Album", "YouTube Video"}
            if product not in accepted:
                raise ValueError(f"ONErpm: tipo de producto no reconocido: {product}")
            if product not in {"Track", "Video Track"}:
                continue
            code = str(row.get("ISRC" if sheet == "Masters" else "ID") or "").strip().upper()
            if re.fullmatch(r"[A-Z]{2}-[A-Z0-9]{3}-[0-9]{2}-[0-9]{5}", code):
                code = code.replace("-", "")
            if not ISRC_PATTERN.fullmatch(code):
                continue
            upc = str(row.get("UPC" if sheet == "Masters" else "Parent ID") or "").strip() or None
            raw = str(row.get("Artists") or "")
            observations.append({"isrc": code, "title": row.get("Track Title") or row.get("Title") or row.get("Album Title"),
                "sheet": sheet, "account": account, "statement": period[1], "file_hash": checksum,
                "file": path.name, "row": row["_excel_row"], "raw": raw, "parsed": parse_credits(raw),
                "level": "track", "identity_status": "resolved" if not upc or re.fullmatch(r"\d{8,14}", upc) else "incomplete",
                "product_type": product, "upc": upc})
    return observations


def read_onerpm_metadata(input_root: Path, *, allowed_accounts: set[str] | None = None, selected_paths: list[Path] | None = None) -> pl.DataFrame:
    groups, scopes, hashes = defaultdict(list), {}, {}
    unsupported = sorted(path for path in input_root.rglob("*") if path.is_file()
                         and not path.name.startswith("~$") and path.suffix.lower() in {".xls", ".xlsm", ".xlsb"})
    if unsupported:
        raise ValueError(f"ONErpm: formato no certificado ({unsupported[0].name}); exportar el statement como XLSX")
    if selected_paths is None:
        from .ingestion_controls import select_inputs
        selected_paths = select_inputs((path for path in input_root.rglob("*.xlsx") if not path.name.startswith("~$")), "onerpm")
    paths = sorted(selected_paths)
    if not paths:
        raise ValueError("ONErpm: no hay statements para construir la metadata de artistas")
    for path in paths:
        account = path.parent.name
        if allowed_accounts is not None and account not in allowed_accounts:
            raise ValueError(f"ONErpm: cuenta no configurada ({account}); revisar la carpeta antes de procesar")
        checksum = file_hash(path)
        period = re.match(r"^(20\d\d-(?:0[1-9]|1[0-2]))-", path.name)
        if not period:
            raise ValueError(f"ONErpm: periodo no reconocido: {path.name}")
        scope = (account, period[1])
        if checksum in hashes and hashes[checksum] != scope:
            raise ValueError("ONErpm: archivo repetido con cuenta o periodo contradictorio")
        if scope in scopes:
            if scopes[scope] == checksum:
                continue
            raise ValueError("ONErpm: reemplazo o suplemento no declarado para una cuenta/periodo")
        scopes[scope], hashes[checksum] = checksum, scope
        for observation in read_file_metadata(path, account):
            groups[observation["isrc"]].append(observation)
    result = []
    for isrc, observations in sorted(groups.items()):
        unique = {}
        for row in observations:
            key = json.dumps({name: value for name, value in row.items() if name != "row"}, sort_keys=True, ensure_ascii=True)
            if key not in unique or row["row"] < unique[key]["row"]:
                unique[key] = row
        observations = [unique[key] for key in sorted(unique)]
        resolved = resolve(observations)
        reference = resolved.get("reference")
        chosen = next((row for row in observations if reference and all(row[key] == value for key, value in reference.items())), observations[0])
        has_masters = any(row["sheet"] == "Masters" for row in observations)
        result.append({"asset_isrc": isrc, "title": chosen["title"], "catalog_artists": resolved["artists"],
            "status": resolved["status"], "principal": resolved["principal"], "principal_status": resolved["principal_status"],
            "has_masters": has_masters, "rule": RULE_VERSION, "evidence": json.dumps(observations, ensure_ascii=False),
            "credit_status": resolved["credit_status"], "incomplete_evidence_count": resolved["incomplete_evidence_count"],
            "source_only_shares": not has_masters})
    return pl.DataFrame(result, schema_overrides={"catalog_artists": pl.List(pl.String)})


def known_names(row: dict, native: dict) -> list[str]:
    if row.get("catalog_artists") is not None:
        return list(row["catalog_artists"])
    raw = str(row.get("artist_statement") or "")
    for observation in json.loads(native["evidence"]):
        if observation["parsed"]["status"] != "resolved" or observation["identity_status"] != "resolved":
            continue
        for names in (observation["parsed"]["performers"], observation["parsed"]["artists"]):
            if names and name_key(raw) == name_key(", ".join(names)):
                return [part.strip() for part in raw.split(",") if part.strip()]
    return parse_catalog_credit(raw)


def enrich_onerpm_catalog(catalog: pl.DataFrame, native: pl.DataFrame, *, corrections_path: Path | None = None) -> pl.DataFrame:
    if catalog["catalog_key"].n_unique() != catalog.height or native["asset_isrc"].n_unique() != native.height:
        raise ValueError("ONErpm: claves duplicadas en el catalogo o la metadata")
    corrections = json.loads((corrections_path or CORRECTIONS_PATH).read_text(encoding="utf-8"))
    manual = {item["catalog_key"]: item["id"] for item in corrections["corrections"] if "artist_statement" in item and item.get("confirmed_by")}
    by_isrc = {row["asset_isrc"]: row for row in native.to_dicts()}
    values = {name: [] for name in ARTIST_COLUMNS}
    matched = set()
    for row in catalog.to_dicts():
        output = {name: row.get(name) for name in ARTIST_COLUMNS}
        item = by_isrc.get(row.get("asset_isrc"))
        if item is not None:
            if item["asset_isrc"] in matched:
                raise ValueError("ONErpm: un ISRC tiene mas de una ficha maestra")
            matched.add(item["asset_isrc"])
            before = known_names(row, item)
            a, b = {name_key(name) for name in before}, {name_key(name) for name in item["catalog_artists"]}
            active = (item["status"] == "resolved" and bool(b) and (a <= b or b <= a)
                      and not (manual.get(row["catalog_key"]) and row.get("catalog_manual_correction_id") == manual[row["catalog_key"]]))
            if active:
                added = [name for name in item["catalog_artists"] if name_key(name) not in a]
                output["catalog_artists"] = before + added
                if added or row.get("catalog_artists") is None:
                    output["catalog_artist_statement"] = " / ".join(before + added)
                rules = [rule for rule in str(output["catalog_artist_rule"] or "").split(" | ") if rule]
                if RULE_VERSION not in rules:
                    rules.append(RULE_VERSION)
                output["catalog_artist_rule"] = " | ".join(rules)
            previous = json.loads(output["catalog_artist_evidence"] or "[]")
            # Replace only this reader's prior observations on reconstruction.
            evidence = [entry for entry in previous if not (entry.get("source") == "onerpm" and entry.get("catalog_rule") == RULE_VERSION)]
            for observation in json.loads(item["evidence"]):
                evidence.append({"source": "onerpm", "field": "Artists", "raw": observation["raw"],
                    "artists": observation["parsed"]["artists"], "credits": observation["parsed"]["credits"],
                    "status": observation["parsed"]["status"], "identity_status": observation["identity_status"],
                    "account": observation["account"], "sheet": observation["sheet"], "statement_period": observation["statement"],
                    "statement_file_name": observation["file"], "statement_file_hash": observation["file_hash"], "row": observation["row"],
                    "level": observation["level"], "product_type": observation["product_type"], "upc": observation.get("upc"),
                    "used_for_catalog": active and observation["parsed"]["status"] == "resolved" and observation["identity_status"] == "resolved",
                    "native_resolution_status": item["status"], "principal_proposed": item["principal"], "principal_status": item["principal_status"],
                    "source_rule": RULE_VERSION, "catalog_rule": RULE_VERSION})
            output["catalog_artist_evidence"] = json.dumps(evidence, sort_keys=True, ensure_ascii=False)
        for name in values:
            values[name].append(output[name])
    return catalog.with_columns([pl.Series(name, values[name], dtype=dtype) for name, dtype in ARTIST_COLUMNS.items()])


def enrich_onerpm_catalog_file(catalog: pl.DataFrame, path: Path) -> pl.DataFrame:
    if not path.exists():
        raise FileNotFoundError("Falta metadata ONErpm: ejecutar su ingesta antes de reconstruir el catalogo")
    return enrich_onerpm_catalog(catalog, pl.read_parquet(path))


def materialize_onerpm_identity_file(catalog: pl.DataFrame, path: Path) -> pl.DataFrame:
    """Consume all native ISRC observations, even Shares excluded from money.

    read_onerpm_metadata runs on every ingestion independently of load_shares_as_rows.
    Artist-credit ambiguity must not discard an otherwise explicit recording ISRC.
    """
    if not path.exists():
        raise FileNotFoundError("Falta metadata ONErpm: ejecutar su ingesta antes de reconstruir el catalogo")
    native = pl.read_parquet(path)
    references = []
    for item in native.iter_rows(named=True):
        for observation in json.loads(item["evidence"]):
            references.append({**observation, "source": "onerpm", "isrc": item["asset_isrc"],
                "recording_artists": item["catalog_artists"] if item["status"] == "resolved" else []})
    return materialize_identity_references(catalog, references)
