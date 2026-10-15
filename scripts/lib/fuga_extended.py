"""FUGA YouTube evidence: never a second source of royalty income."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import uuid

import polars as pl

VERSION = 1
EXTENDED_SUFFIX = "-youtube_extended.csv"
ECONOMIC_SUFFIX = "-royalty_product_and_asset.csv"
AUDIT_FILE = "fuga_youtube_extended_audit.parquet"
METADATA_FILE = "fuga_youtube_extended_metadata.parquet"
FINANCIAL_PAIRS = {
    "Reported Royalty": ("Reported Royalty", True),
    "Converted Gross Income": ("Converted Gross Income", True),
    "Quantity": ("Asset Quantity", True),
    "Currency": ("Currency", False),
    "Territory": ("Territory", False),
    "Service": ("DSP", False),
    "Contract deal term": ("Contract deal term", False),
    "YouTube Claim Type": ("Sale Type", False),
    "Sale Start date": ("Sale Start date", False),
    "Sale End date": ("Sale End date", False),
}


def is_extended(path: Path) -> bool:
    return path.name.lower().endswith(EXTENDED_SUFFIX)


@lru_cache(maxsize=256)
def _hash_file(path: str, size: int, modified_ns: int) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(path: Path) -> str:
    stat = path.stat()
    return _hash_file(str(path.resolve()), stat.st_size, stat.st_mtime_ns)


def partner(path: Path) -> Path | None:
    name = path.name[:-len(EXTENDED_SUFFIX)] + ECONOMIC_SUFFIX
    return next((item for item in path.parent.iterdir()
                 if item.is_file() and item.name.casefold() == name.casefold()), None)


def evidence_dir(root: Path, path: Path) -> Path:
    return root / "warehouse" / "supplementary" / "fuga" / path.stem


def _atomic_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _atomic_parquet(frame: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    frame.write_parquet(temp)
    os.replace(temp, path)


def current_report(root: Path, path: Path) -> dict | None:
    """A changed input or missing evidence must be processed again."""
    try:
        folder = evidence_dir(root, path)
        report = json.loads((folder / "audit.json").read_text(encoding="utf-8"))
        regular = partner(path)
        if (report.get("version") != VERSION
                or report.get("extended_sha256") != fingerprint(path)
                or report.get("statement_sha256") != (fingerprint(regular) if regular else None)):
            return None
        if report.get("status") == "validated":
            for name in ["metadata.parquet", "isrc_review.parquet"]:
                if not (folder / name).exists() or report.get("evidence_sha256", {}).get(name) != fingerprint(folder / name):
                    return None
        return report
    except (OSError, ValueError):
        return None


def inventory_item(root: Path, path: Path) -> dict:
    report = current_report(root, path)
    valid = report is not None and report.get("status") == "validated"
    return {
        "file_name": path.name,
        "status": "ignored_audit_detail" if valid else "pending_real",
        "reason": report["reason"] if report else "YouTube Extended pendiente de comparar con su statement completo.",
        "rows": report.get("rows") if report else None,
    }


def monitor_directory(root: Path) -> list[dict]:
    folder = root / "input_raw" / "fuga"
    return [current_report(root, path) or {
        "file_name": path.name, "status": "pending", "rows": 0,
        "reason": "YouTube Extended pendiente de comparar con su statement completo.",
    } for path in sorted(folder.iterdir()) if path.is_file() and is_extended(path)]


def audit_file(root: Path, path: Path) -> dict:
    cached = current_report(root, path)
    if cached and cached.get("status") == "validated":
        return cached
    regular = partner(path)
    report = {
        "version": VERSION, "file_name": path.name,
        "statement_file_name": regular.name if regular else None,
        "extended_sha256": fingerprint(path),
        "statement_sha256": fingerprint(regular) if regular else None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "economic_role": "supplementary_metadata_only",
        "status": "blocked", "rows": 0, "issues": [], "comparisons": {},
    }
    folder = evidence_dir(root, path)
    try:
        if regular is None:
            raise ValueError("Falta el statement completo del mismo periodo y cuenta.")
        extended = pl.read_csv(path, infer_schema=False)
        native = pl.read_csv(regular, infer_schema=False)
        report["rows"] = extended.height
        required_e = {"Sale ID", "YouTube Asset ISRC", *FINANCIAL_PAIRS}
        required_r = {"Sale ID", "Asset ISRC", *(pair[0] for pair in FINANCIAL_PAIRS.values())}
        for label, frame, required in [("Extended", extended, required_e), ("Statement", native, required_r)]:
            missing = sorted(required - set(frame.columns))
            if missing:
                raise ValueError(f"{label}: faltan columnas {', '.join(missing)}.")
            if frame["Sale ID"].null_count() or frame.filter(pl.col("Sale ID").str.strip_chars() == "").height:
                raise ValueError(f"{label}: hay Sale ID vacios.")
            if frame["Sale ID"].n_unique() != frame.height:
                raise ValueError(f"{label}: hay Sale ID duplicados.")
        # Keep native fields under a separate namespace; ISRCs may identify videos rather than audio.
        regular_names = {column: f"native__{column}" for column in native.columns if column != "Sale ID"}
        joined = extended.join(native.rename(regular_names), on="Sale ID", how="inner", validate="1:1")
        report["matched_rows"] = joined.height
        missing = extended.join(native.select("Sale ID"), on="Sale ID", how="anti")
        youtube = native.filter(pl.col("DSP").str.to_lowercase().is_in(["youtube music", "youtube ad supported"]))
        uncovered = youtube.join(extended.select("Sale ID"), on="Sale ID", how="anti")
        report["unmatched_extended_rows"] = missing.height
        report["uncovered_youtube_rows"] = uncovered.height
        if missing.height or uncovered.height:
            report["issues"].append(f"Cobertura diferente: {missing.height} filas sin principal; {uncovered.height} filas YouTube sin Extended.")
        for column, (native_column, numeric) in FINANCIAL_PAIRS.items():
            left, right = pl.col(column), pl.col(f"native__{native_column}")
            if numeric:
                left, right = left.cast(pl.Decimal(38, 20)), right.cast(pl.Decimal(38, 20))
            diff = joined.filter(~left.eq_missing(right))
            report["comparisons"][column] = {"different_rows": diff.height,
                "samples": diff.select("Sale ID", column, f"native__{native_column}").head(3).to_dicts()}
            if diff.height:
                report["issues"].append(f"{column}: {diff.height} filas diferentes.")
        isrc_extended = pl.col("YouTube Asset ISRC").str.strip_chars().str.to_uppercase().replace("", None)
        isrc_native = pl.col("native__Asset ISRC").str.strip_chars().str.to_uppercase().replace("", None)
        needs_review = joined.filter(isrc_extended.is_not_null() & ~isrc_extended.eq_missing(isrc_native))
        report["isrc_review_rows"] = needs_review.height
        report["isrc_review_examples"] = needs_review.select("Sale ID", "YouTube Asset ISRC", "native__Asset ISRC").head(8).to_dicts()
        report["additional_fields"] = {
            column: {"filled_rows": extended[column].drop_nulls().len(),
                     "distinct_values": extended[column].drop_nulls().n_unique()}
            for column in ["YouTube Video Title", "YouTube Channel Display Name", "YouTube Asset Type"]
            if column in extended.columns
        }
        metadata = extended.with_row_index("source_row", offset=2).join(
            native.select("Sale ID", pl.col("Asset ISRC").alias("principal_asset_isrc")),
            on="Sale ID", how="left", validate="1:1", maintain_order="left",
        ).with_columns(
            pl.lit(path.name).alias("source_file"),
            pl.lit(regular.name).alias("statement_file_name"),
            pl.lit("supplementary_metadata_only").alias("economic_role"),
        )
        _atomic_parquet(metadata, folder / "metadata.parquet")
        _atomic_parquet(needs_review.select("Sale ID", "YouTube Asset ISRC", "native__Asset ISRC"), folder / "isrc_review.parquet")
        report["evidence_sha256"] = {name: fingerprint(folder / name) for name in ["metadata.parquet", "isrc_review.parquet"]}
        if not report["issues"]:
            report["status"] = "validated"
    except (ValueError, OSError, pl.exceptions.PolarsError) as exc:
        report["issues"].append(str(exc))
    report["reason"] = (
        f"YouTube Extended validado: {report['rows']} filas; sin ingresos adicionales. "
        f"ISRC para revisar: {report.get('isrc_review_rows', 0)}."
        if report["status"] == "validated" else "YouTube Extended requiere revision: " + " ".join(report["issues"])
    )
    _atomic_json(folder / "audit.json", report)
    return report


def audit_directory(root: Path, input_dir: Path | None = None) -> list[dict]:
    input_dir = input_dir or root / "input_raw" / "fuga"
    paths = sorted(item for item in input_dir.iterdir() if item.is_file() and is_extended(item)) if input_dir.exists() else []
    reports = [audit_file(root, path) for path in paths]
    summary = pl.DataFrame({
        "file_name": [item["file_name"] for item in reports],
        "report_json": [json.dumps(item, ensure_ascii=False) for item in reports],
    }, schema={"file_name": pl.String, "report_json": pl.String})
    marts = root / "warehouse" / "marts"
    _atomic_parquet(summary, marts / AUDIT_FILE)
    valid_paths = [evidence_dir(root, path) / "metadata.parquet" for path, report in zip(paths, reports) if report["status"] == "validated"]
    if valid_paths:
        target = marts / METADATA_FILE
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        pl.concat([pl.scan_parquet(path) for path in valid_paths], how="diagonal_relaxed").sink_parquet(temporary)
        os.replace(temporary, target)
    else:
        _atomic_parquet(pl.DataFrame(schema={"source_file": pl.String, "economic_role": pl.String}), marts / METADATA_FILE)
    for report in reports:
        print(report["file_name"] + ": " + report["reason"])
    failed = [report for report in reports if report["status"] != "validated"]
    if failed:
        raise ValueError("No se modificaron ingresos: " + " | ".join(report["reason"] for report in failed))
    return reports


def load_reports(path: Path) -> list[dict]:
    return [json.loads(value) for value in pl.read_parquet(path)["report_json"].to_list()]
