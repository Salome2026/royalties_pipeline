"""Read the versioned ingestion audit without changing the financial cache."""
from functools import lru_cache
import io
import json
from pathlib import Path

import polars as pl

from scripts.lib.ingestion_controls import CONTROL_FILE, checksum, file_context

LABELS = {"UNKNOWN_ROLE": "Rol no reconocido", "PARTICIPANTS_CONFLICT": "Participantes por confirmar",
          "UNRESOLVED_CREDIT": "Credito por confirmar", "TITLE_CONTRADICTION": "Titulos diferentes para un ISRC"}


@lru_cache(maxsize=2048)
def _fingerprint(path, size, mtime, ctime):
    return checksum(Path(path))


def raw_fingerprint(path):
    stat = path.stat()
    return _fingerprint(str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def classify_fingerprint(source, path, records):
    if not records:
        return None
    digest = raw_fingerprint(path)
    named = [row for row in records if row.get("file_name") == path.name]
    if named:
        matched = next((row for row in named if row.get("file_hash") == digest), None)
        if matched:
            return {"file_name": path.name, "status": "ignored_duplicate" if matched.get("status") == "duplicate" else "loaded_to_mart",
                "reason": "Copia ya reconocida; no suma ingresos." if matched.get("status") == "duplicate" else "Contenido cargado y verificado.", "file_hash": digest}
        return {"file_name": path.name, "status": "pending_real", "reason": "El contenido cambio: reprocesar reemplazara la version anterior, sin sumar ambas.", "change_type": "replacement", "file_hash": digest}
    same = [row for row in records if row.get("file_hash") == digest]
    if same:
        try:
            _, period, kind = file_context(path, source)
            def compatible(row):
                native_kind = row.get("kind") or ""
                if source == "onerpm":
                    native_kind = "details"
                elif source in {"ada", "dashgo", "orchard"}:
                    native_kind = "detail" if source == "ada" else "statement"
                elif source == "fuga":
                    native_kind = "correction" if "correction" in row.get("file_name", "").lower() else "regular"
                return row.get("period") == period and native_kind == kind
            if any(compatible(row) for row in same):
                return {"file_name": path.name, "status": "ignored_duplicate", "reason": "Mismo contenido y periodo con otro nombre; no se vuelve a sumar.", "file_hash": digest}
        except (ValueError, pl.exceptions.PolarsError):
            pass
    return None


def load_controls(*, client, bucket_name, prefix, local_marts=None):
    if local_marts is not None:
        path = Path(local_marts) / CONTROL_FILE
        return pl.read_parquet(path) if path.exists() else None
    bucket = client.bucket(bucket_name)
    root = prefix.strip("/")
    manifest = bucket.get_blob((root + "/" if root else "") + "release_manifest.json")
    if manifest is None:
        return None
    document = json.loads(manifest.download_as_bytes(if_generation_match=manifest.generation))
    entry = document.get("files", {}).get(CONTROL_FILE)
    if entry:
        blob = bucket.blob(entry["object_name"], generation=int(entry["generation"]))
        data = blob.download_as_bytes(if_generation_match=int(entry["generation"]))
    else:
        # Metadata-only adoption over the existing release; future releases pin
        # the audit in their own manifest and no longer use this bootstrap object.
        blob = bucket.get_blob((root + "/" if root else "") + CONTROL_FILE)
        if blob is None:
            return None
        data = blob.download_as_bytes(if_generation_match=blob.generation)
    frame = pl.read_parquet(io.BytesIO(data))
    if not entry and frame.height and set(frame["base_release_id"].drop_nulls().unique().to_list()) != {document["release_id"]}:
        return None
    return frame


def source_controls(frame, source, account):
    if frame is None:
        return {"files": [], "incidents": []}
    selected = frame.filter((pl.col("source") == source) & pl.col("account").is_in([account, ""]))
    files, incidents = [], []
    for row in selected.iter_rows(named=True):
        details = json.loads(row["details"])
        if row["row_type"] == "file":
            files.append(details)
        else:
            incidents.append({"code": row["code"], "label": LABELS.get(row["code"], "Lectura por revisar"), **details})
    return {"files": files, "incidents": incidents}
