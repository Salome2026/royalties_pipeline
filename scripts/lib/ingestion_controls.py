"""Shared file admission and diagnostics; never deduplicate economic rows."""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime
from functools import wraps
import hashlib
import json
from pathlib import Path
import re

import polars as pl

from .statement_period import from_ada_filename, from_dashgo_filename, from_fuga_filename, from_onerpm_filename, from_soundon_filename, FUGA_CORRECTION_STATEMENT_PERIOD

VERSION = "catalog-ingestion-controls-1"
CONTROL_FILE = "catalog_ingestion_controls.parquet"
SOURCES = ("ada", "dashgo", "fuga", "onerpm", "orchard", "soundon")
_CURRENT: ContextVar[Batch | None] = ContextVar("ingestion_batch", default=None)
FILE_SCHEMA = {name: pl.String for name in ("source", "account", "period", "kind", "file_name", "file_hash", "status", "duplicate_of", "rule", "reader_sha256")}


class IngestionControlError(ValueError):
    def __init__(self, code: str, message: str, **evidence):
        self.code, self.evidence = code, evidence
        super().__init__(message)


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def file_context(path: Path, source: str, account: str = "") -> tuple[str, str, str]:
    if source == "orchard":
        # The native column, not the filename, defines Orchard's settlement month.
        frame = pl.read_csv(path, infer_schema=False, encoding="utf8-lossy").rename(lambda name: name.strip().lstrip("\ufeff").replace('"', ''))
        if frame.is_empty():
            return account or "mawzrecords", "empty:" + path.name, "statement"
        needed = {"STATEMENT PERIOD", "ACCOUNT NAME"}
        if not needed <= set(frame.columns):
            raise IngestionControlError("UNKNOWN_LAYOUT", f"Orchard: faltan campos de periodo/cuenta en {path.name}", file=path.name)
        try:
            months = sorted({datetime.strptime(value.strip(), "%B %Y").strftime("%Y-%m") for value in frame["STATEMENT PERIOD"].drop_nulls()})
        except ValueError as error:
            raise IngestionControlError("UNKNOWN_PERIOD", f"Orchard: periodo no reconocido en {path.name}", file=path.name) from error
        accounts = sorted(set(frame["ACCOUNT NAME"].drop_nulls().to_list()))
        return " | ".join(accounts), " | ".join(months), "statement"
    if source == "fuga":
        kind = "correction" if "correction" in path.name.lower() else "regular"
        period = FUGA_CORRECTION_STATEMENT_PERIOD if kind == "correction" else from_fuga_filename(path.name).period
        return account or "indyana_records", period, kind
    if source == "onerpm":
        return account or path.parent.name, from_onerpm_filename(path.name).period if len(path.stem) > 7 else "unknown", "details"
    if source == "ada":
        return account or path.parent.name, from_ada_filename(path.name).period, "detail"
    if source == "dashgo":
        return account or "mawzrecords", from_dashgo_filename(path.name).period, "statement"
    if source == "soundon":
        match = re.search(r"SoundOn_royalty_monthly_statement_\d{4}_\d{2}_(.+)\.csv$", path.name, re.I)
        return account or "soundon", from_soundon_filename(path.name).period, match[1].casefold().replace(" ", "_") if match else "unknown"
    raise ValueError("Unconfigured source: " + source)


def select_inputs(paths, source: str, account: str = "") -> list[Path]:
    batch = _CURRENT.get()
    groups = {}
    for path in sorted(paths):
        if path.name.startswith("~$"):
            continue
        acct, period, kind = file_context(path, source, account)
        if period == "unknown" or kind == "unknown":
            raise IngestionControlError("UNKNOWN_LAYOUT", f"{source}: nombre o periodo no reconocido: {path.name}", file=path.name)
        key = (acct, period, kind)
        groups.setdefault(key, []).append((path, checksum(path)))
    selected, records = [], []
    for (acct, period, kind), entries in sorted(groups.items()):
        hashes = {digest for _, digest in entries}
        if len(hashes) > 1:
            names = ", ".join(path.name for path, _ in entries)
            raise IngestionControlError("UNDECLARED_REPLACEMENT", f"{source}/{acct}: archivos distintos para {period} ({kind}): {names}. Conservar la version correcta; un suplemento requiere una regla explicita.", files=names, account=acct, period=period)
        # Keep an already admitted filename where possible. Otherwise prefer the
        # certified export name over a copy-prefixed name, not filesystem mtime.
        prior = batch.prior_names if batch else set()
        chosen = min(entries, key=lambda item: (item[0].name not in prior, bool(re.search(r"copy|copia|\(\d+\)", item[0].name, re.I)), item[0].name))
        selected.append(chosen[0])
        for path, digest in entries:
            records.append(dict(source=source, account=acct, period=period, kind=kind, file_name=path.name, file_hash=digest,
                status="selected" if path == chosen[0] else "duplicate", duplicate_of="" if path == chosen[0] else chosen[0].name, rule=VERSION, reader_sha256=batch.reader_hash if batch else ""))
    if batch:
        batch.records.extend(records)
    return sorted(selected)


def validate_amounts(frame: pl.DataFrame, *, source: str, path: Path, field: str, column: str = "amount_usd") -> None:
    if frame.is_empty():
        return
    value = pl.col(column).cast(pl.Float64, strict=False)
    invalid = frame.with_row_index("_data_row", offset=1).filter(value.is_null() | ~value.is_finite())
    if invalid.height:
        rows = invalid["_data_row"].head(5).to_list()
        batch = _CURRENT.get()
        if batch:
            accounts = invalid["account"].drop_nulls().unique().to_list() if "account" in invalid.columns else []
            batch.incidents.append({"code": "INVALID_AMOUNT", "file": path.name, "field": field, "accounts": accounts, "affected_rows": invalid.height, "sample_rows": rows})
        raise IngestionControlError("INVALID_AMOUNT", f"{source}: importe invalido en {field}, {path.name}; {invalid.height} filas (datos {rows}). No se actualiza el lote.", file=path.name, field=field, affected_rows=invalid.height, sample_rows=rows)


class Batch:
    def __init__(self, source: str, output: Path):
        self.source, self.output, self.records, self.incidents = source, output, [], []
        self.receipt = output.parent / f"ingestion_control_{source}.parquet"
        self.failure = output.parent.parent / "registry" / f"ingestion_failure_{source}.json"
        self.prior_names = set()
        self.reader_hash = ""
        self.staged = None
        if self.receipt.exists():
            self.prior_names.update(pl.read_parquet(self.receipt).filter(pl.col("status") == "selected")["file_name"].to_list())
        elif output.exists():
            scan = pl.scan_parquet(output)
            if "statement_file_name" in scan.collect_schema():
                self.prior_names.update(scan.select(pl.col("statement_file_name").drop_nulls().unique()).collect().to_series().to_list())

    def failed(self, error):
        self.failure.parent.mkdir(parents=True, exist_ok=True)
        message = str(error).casefold()
        fallback = "UNKNOWN_LAYOUT" if any(word in message for word in ("column", "hojas", "formato", "layout", "tipo de producto", "unrecognized", "no reconocido")) else "INVALID_BATCH"
        code = getattr(error, "code", self.incidents[0]["code"] if self.incidents else fallback)
        document = {"source": self.source, "rule": VERSION, "status": "blocked", "code": code,
            "message": str(error), "evidence": getattr(error, "evidence", {}), "checked_at": datetime.now().isoformat(timespec="seconds")}
        document["incidents"] = self.incidents
        temporary = self.failure.with_suffix(".tmp")
        temporary.write_text(json.dumps(document, ensure_ascii=True), encoding="utf-8")
        temporary.replace(self.failure)
        print("INGESTION_INCIDENT=" + json.dumps(document, ensure_ascii=True))

    def stage(self, economic_path=None):
        staged = []
        if self.records:
            unique = {json.dumps(row, sort_keys=True): row for row in self.records}
            frame = pl.DataFrame(list(unique.values()), schema=FILE_SCHEMA).sort("account", "period", "kind", "file_name")
            temporary = self.receipt.with_suffix(".tmp.parquet")
            frame.write_parquet(temporary)
            staged.append((temporary, self.receipt))
        if self.source in SOURCES and economic_path is not None and Path(economic_path).exists():
            from .catalog_ingestion_review import native_title_incidents, SCHEMA
            review = self.output.parent / f"ingestion_control_{self.source}_review.parquet"
            temporary = review.with_suffix(".tmp.parquet")
            pl.DataFrame(native_title_incidents(pl.scan_parquet(economic_path)), schema=SCHEMA).write_parquet(temporary)
            staged.append((temporary, review))
        self.staged = staged

    def completed(self):
        if self.staged is None:
            self.stage(self.output)
        for temporary, destination in self.staged:
            temporary.replace(destination)
        self.failure.unlink(missing_ok=True)


def controlled_ingestion(source):
    def decorate(function):
        @wraps(function)
        def run(*args, **kwargs):
            batch = Batch(source, function.__globals__["OUTPUT_PATH"])
            batch.reader_hash = checksum(Path(function.__globals__["__file__"]))
            token = _CURRENT.set(batch)
            try:
                result = function(*args, **kwargs)
                batch.completed()
                return result
            except Exception as error:
                batch.failed(error)
                raise
            finally:
                _CURRENT.reset(token)
        return run
    return decorate


def stage_controls(economic_path):
    batch = _CURRENT.get()
    if batch:
        batch.stage(economic_path)


def validate_no_failed_batches(marts: Path, *, ignore=()) -> None:
    failures = sorted(path for path in (marts.parent / "registry").glob("ingestion_failure_*.json") if path.stem.removeprefix("ingestion_failure_") not in ignore)
    if failures:
        document = json.loads(failures[0].read_text(encoding="utf-8"))
        raise ValueError("Publicacion bloqueada. Corregir y reprocesar la fuente: " + document["source"] + ". " + document["message"])
