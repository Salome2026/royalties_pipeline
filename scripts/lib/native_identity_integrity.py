"""Conserve original CSV identifier cells, independently of parsed intermediates.

These are lexical witnesses, not rules assigning recordings, artists or money.
Excel sources retain their source-specific sheet admission and are not silently
treated as CSV. Historic adoption must explicitly audit their native sheets.
"""
from pathlib import Path
import json
import re
import polars as pl
from .native_csv import clean_native_headers

VERSION = "native-original-identity-1"
PROOF_FILE = "native_identity_proofs.json"
FIELDS = {
    "fuga": ("Asset ISRC", "Product UPC", "Product Reference", "Asset Reference",
             "DSP Container ID", "DSP Unit ID", "DSP Collection ID", "Sale ID", "Report ID", "Report Run ID"),
    "dashgo": ("ISRC", "UPC", "Label Track ID", "VideoId", "ChannelId"),
    "orchard": ("ISRC", "PRODUCT CODE", "DISPLAY UPC", "MANUFACTURER UPC", "YOUTUBE VIDEO ID"),
    "soundon": ("ISRC", "UPC Code", "Track ID"),
}
CSV_SOURCES = frozenset(FIELDS)
FIELDS.update({
    "ada": ("ISRC", "UPC", "Catalogue Number", "Parent Product ID", "Local Product Number"),
    "onerpm": ("ISRC", "UPC", "ID", "Parent ID", "Video ID", "Channel ID"),
})


def lexical(name: str) -> pl.Expr:
    return pl.col(name).cast(pl.String, strict=True).str.strip_chars().fill_null("").alias(name)


def fingerprint(frame: pl.DataFrame | pl.LazyFrame, fields: list[str]) -> dict:
    lazy = frame.lazy() if isinstance(frame, pl.DataFrame) else frame
    normalized = lazy.select([lexical(name) for name in fields])
    values = normalized.select(
        pl.len().alias("rows"),
        pl.struct(fields).hash(seed=81643).sum().cast(pl.String).alias("tuple_sum_1"),
        pl.struct(fields).hash(seed=734921).sum().cast(pl.String).alias("tuple_sum_2"),
        *[(pl.col(name) != "").sum().alias("present_" + name) for name in fields],
    ).collect(engine="streaming").row(0, named=True)
    return {"rule": VERSION, "hash_runtime": "polars-" + pl.__version__, "fields": fields, **values}


def original_csv(path: Path, source: str) -> pl.DataFrame:
    # Read the original independently of the ingestion helper: a regression in
    # that helper must not also change the expected evidence.
    return clean_native_headers(pl.read_csv(path, infer_schema=False, ignore_errors=False,
        encoding="utf8-lossy" if source in {"orchard", "dashgo"} else "utf8"))


def compare_original_frame(original: pl.DataFrame, written: pl.DataFrame | pl.LazyFrame,
                           source: str) -> dict:
    fields = sorted(set(FIELDS[source]) & set(original.columns))
    if not fields:
        return {"rule": VERSION, "status": "no_identifier_columns", "fields": []}
    schema = written.collect_schema() if isinstance(written, pl.LazyFrame) else written.schema
    missing = set(fields) - set(schema)
    if missing:
        raise ValueError("Faltan columnas originales de identificadores: " + ", ".join(sorted(missing)))
    expected, actual = fingerprint(original, fields), fingerprint(written, fields)
    if expected != actual:
        lost = {name: {"original": expected["present_" + name], "processed": actual["present_" + name]}
                for name in fields if expected["present_" + name] != actual["present_" + name]}
        raise ValueError(f"Los identificadores procesados no coinciden con el original: {lost or 'valores, filas o correspondencias diferentes'}")
    return {**expected, "status": "verified_against_original"}


def validate_original_csv_batch(source: str, output: Path, selected: list[dict],
                                paths: dict[Path, str]) -> list[dict]:
    if source not in CSV_SOURCES:
        return []
    available = {(path.name, digest): path for path, digest in paths.items()}
    scan = pl.scan_parquet(output)
    schema = set(scan.collect_schema().names())
    if selected and not {"statement_file_hash", "statement_file_name"} <= schema:
        raise ValueError("La salida no conserva archivo y huella para verificar sus identificadores originales.")
    result = []
    for item in selected:
        path = available[(item["file_name"], item["file_hash"])]
        if path.suffix.casefold() != ".csv":
            raise ValueError("Formato no certificado por el control CSV: " + path.name)
        written = scan.filter((pl.col("statement_file_hash") == item["file_hash"])
                              & (pl.col("statement_file_name") == item["file_name"]))
        if "source" in schema:
            written = written.filter(pl.col("source") == source)
        proof = compare_original_frame(original_csv(path, source), written, source)
        result.append({"source": source, "account": item["account"], "file_name": item["file_name"],
                       "file_hash": item["file_hash"], "period": item["period"], **proof})
    return result


def validate_original_input_batch(source: str, output: Path, selected: list[dict],
                                 paths: dict[Path, str], *, accounts: dict | None = None) -> list[dict]:
    if source in CSV_SOURCES:
        return validate_original_csv_batch(source, output, selected, paths)
    if source not in {"ada", "onerpm"}:
        return []
    scan = pl.scan_parquet(output)
    available = {(path.name, digest): path for path, digest in paths.items()}
    results = []
    for item in selected:
        path = available[(item["file_name"], item["file_hash"])]
        scoped = scan.filter((pl.col("statement_file_hash") == item["file_hash"])
                             & (pl.col("statement_file_name") == item["file_name"]))
        if source == "ada":
            from .ada_statement_reader import read_operational_package
            native, _, _ = read_operational_package(path, path.name.split("_")[0])
            frames = {"royalty_detail": native}
        else:
            if not accounts or item["account"] not in accounts:
                raise ValueError("Falta la admision explicita de hojas ONErpm para " + item["account"])
            admission = accounts[item["account"]]
            all_frames = pl.read_excel(path, sheet_id=0, infer_schema_length=None,
                read_options={"dtypes": "string"}, raise_if_empty=False)
            from .onerpm_catalog_artists import METADATA_FILE
            metadata_path = output.parent / METADATA_FILE
            pending_metadata = metadata_path.with_suffix(".tmp.parquet")
            metadata_path = pending_metadata if pending_metadata.exists() else metadata_path
            validate_onerpm_metadata_references(all_frames, metadata_path, item["file_hash"])
            options = {"Masters": "load_masters", "Youtube Channels": "load_youtube_channels",
                       "Shares In & Out": "load_shares_as_rows"}
            frames = {sheet: frame for sheet, frame in all_frames.items()
                      if sheet in options and admission.get(options[sheet]) is True}
        for sheet, native in frames.items():
            if native.is_empty():
                continue
            native = clean_native_headers(native)
            proof = compare_original_frame(native, scoped.filter(pl.col("source_sheet") == sheet), source)
            results.append({"source": source, "account": item["account"], "file_name": item["file_name"],
                            "file_hash": item["file_hash"], "period": item["period"], "sheet": sheet, **proof})
    return results


def validate_onerpm_metadata_references(frames: dict[str, pl.DataFrame], metadata_path: Path,
                                       file_hash: str) -> None:
    # Transfers may be excluded as money but still carry valid recording IDs.
    # Never make admission of their cash a prerequisite for keeping identity.
    expected = set()
    for sheet, field in [("Masters", "ISRC"), ("Shares In & Out", "ID")]:
        frame = clean_native_headers(frames.get(sheet, pl.DataFrame()))
        if frame.is_empty() or not {field, "Product Type"} <= set(frame.columns):
            continue
        for value in frame.filter(pl.col("Product Type").is_in(["Track", "Video Track"]))[field].drop_nulls():
            code = str(value).strip().replace("-", "").upper()
            if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}", code):
                expected.add((code, sheet))
    if not expected:
        return
    if not metadata_path.exists():
        raise ValueError("Falta conservar la identidad ONErpm de Masters/Shares, independientemente de su dinero")
    present = set()
    for row in pl.read_parquet(metadata_path).select("asset_isrc", "evidence").iter_rows(named=True):
        for observation in json.loads(row["evidence"] or "[]"):
            if observation.get("file_hash") == file_hash:
                present.add((row["asset_isrc"], observation["sheet"]))
    missing = expected - present
    if missing:
        raise ValueError("Se pierden referencias originales ONErpm de Masters/Shares: " + str(sorted(missing)[:5]))


def validate_original_witnesses(source: Path, document: dict) -> dict:
    """Recheck original-derived witnesses at later projections/publication.

    The immutable source checksum authenticates provenance; a pair of seeded
    multiset fingerprints checks cells and row correspondence/multiplicity.
    A Polars upgrade requires re-reading originals, never silently rehashing an
    already-normalized frame and calling it native evidence.
    """
    if document.get("rule") != VERSION:
        raise ValueError("Version de evidencia original no reconocida")
    scan = pl.scan_parquet(source)
    checked = []
    for proof in document.get("files", []):
        if proof.get("status") != "verified_against_original":
            continue
        if proof.get("hash_runtime") != "polars-" + pl.__version__:
            raise ValueError("Cambio el runtime de huellas; volver a certificar desde los originales")
        scoped = scan.filter((pl.col("source") == proof["source"])
                             & (pl.col("statement_file_hash") == proof["file_hash"])
                             & (pl.col("statement_file_name") == proof["file_name"]))
        if proof.get("account"):
            scoped = scoped.filter(pl.col("account") == proof["account"])
        if proof.get("sheet"):
            scoped = scoped.filter(pl.col("source_sheet") == proof["sheet"])
        actual = fingerprint(scoped, proof["fields"])
        if any(actual[k] != proof[k] for k in actual):
            raise ValueError("Una reconstruccion pierde identificadores originales de " + proof["file_name"])
        checked.append((proof["source"], proof["file_hash"], proof.get("sheet")))
    return {"rule": VERSION, "verified_files_or_sheets": len(checked)}


def publication_witnesses(source: Path, *, require_coverage: bool = True) -> tuple[Path, dict]:
    """Assemble original-derived receipts and reject silent historical fallback."""
    scan = pl.scan_parquet(source)
    columns = set(scan.collect_schema().names())
    path = source.parent / PROOF_FILE
    document = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"rule": VERSION, "files": []}
    for receipt in sorted(source.parent.glob("ingestion_control_*_native_identity.json")):
        item = json.loads(receipt.read_text(encoding="utf-8"))
        if item.get("rule") != VERSION:
            raise ValueError("Recibo original no certificado: " + receipt.name)
        updated_sources = {p["source"] for p in item["files"]}
        document["files"] = [p for p in document["files"] if p["source"] not in updated_sources] + item["files"]
    if {"source", "statement_file_hash", "statement_file_name"} <= columns:
        eligible = scan.filter(pl.col("source").is_in(list(FIELDS)))
        if "statement_type" in columns:
            eligible = eligible.filter(pl.col("statement_type").fill_null("") != "altafonte_legacy")
        scopes = eligible.select("source", "statement_file_hash", "statement_file_name").unique().collect().to_dicts()
        represented = {(p["source"], p["file_hash"], p["file_name"]) for p in document["files"]}
        missing = [row for row in scopes if (row["source"], row["statement_file_hash"], row["statement_file_name"]) not in represented]
        if require_coverage and missing:
            raise ValueError("Falta certificar identificadores contra archivos originales: " + str(missing[:5]))
    result = validate_original_witnesses(source, document)
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(document, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    return path, result
