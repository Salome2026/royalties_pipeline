from __future__ import annotations

import json
from typing import Any, Iterable

from google.api_core.exceptions import NotFound
from google.cloud import storage


REPORT_INPUT_FILENAMES = (
    "song_level_all_sources.parquet",
    "standardized_raw_all_sources.parquet",
    "catalog_master.parquet",
    "catalog_status.parquet",
)
RELEASE_MANIFEST_FILENAME = "release_manifest.json"


def gcs_object_name(prefix: str, filename: str) -> str:
    clean_prefix = prefix.strip("/")
    return f"{clean_prefix}/{filename}" if clean_prefix else filename


def build_gcs_input_manifest(
    *,
    client: storage.Client,
    bucket_name: str,
    prefix: str,
    filenames: Iterable[str] = REPORT_INPUT_FILENAMES,
) -> dict[str, Any]:
    if not bucket_name:
        raise RuntimeError("GCS_BUCKET no esta configurado para resolver los marts.")

    expected = list(dict.fromkeys(filenames))
    bucket = client.bucket(bucket_name)
    release_blob = bucket.blob(gcs_object_name(prefix, RELEASE_MANIFEST_FILENAME))
    release_document: dict[str, Any] | None = None
    try:
        release_blob.reload(client=client)
        release_document = json.loads(
            release_blob.download_as_bytes(if_generation_match=int(release_blob.generation))
        )
    except NotFound:
        release_document = None

    objects: dict[str, dict[str, Any]] = {}
    if release_document is not None:
        if int(release_document.get("schema_version") or 0) != 1:
            raise RuntimeError("El manifiesto de publicacion no es valido.")
        release_files = release_document.get("files")
        if not isinstance(release_files, dict):
            raise RuntimeError("El manifiesto de publicacion no contiene archivos.")
        for filename in expected:
            entry = release_files.get(filename)
            if not isinstance(entry, dict):
                continue
            object_name = str(entry.get("object_name") or "")
            generation = int(entry.get("generation") or 0)
            if not object_name or generation <= 0:
                raise RuntimeError(f"La version publicada de {filename} no es valida.")
            objects[filename] = {
                "uri": f"gs://{bucket_name}/{object_name}",
                "object": object_name,
                "generation": generation,
                "size_bytes": int(entry.get("size_bytes") or 0),
                "crc32c": entry.get("crc32c"),
                "updated_at": release_document.get("published_at"),
            }

    # Governance and legacy objects that are not in the analytics release keep
    # their own pinned canonical generation.
    for filename in expected:
        if filename in objects:
            continue
        blob = bucket.blob(gcs_object_name(prefix, filename))
        try:
            blob.reload(client=client)
        except NotFound:
            continue
        objects[filename] = {
            "uri": f"gs://{bucket_name}/{blob.name}",
            "object": blob.name,
            "generation": int(blob.generation),
            "size_bytes": int(blob.size or 0),
            "crc32c": blob.crc32c,
            "updated_at": blob.updated.isoformat() if blob.updated else None,
        }

    missing = [filename for filename in expected if filename not in objects]
    if missing:
        raise RuntimeError(
            "Faltan entradas publicadas para el reporte: " + ", ".join(missing)
        )

    return {
        "schema_version": 1,
        "bucket": bucket_name,
        "prefix": prefix.strip("/"),
        "release_id": release_document.get("release_id") if release_document else None,
        "release_manifest_generation": (
            int(release_blob.generation) if release_document is not None else None
        ),
        "objects": {filename: objects[filename] for filename in expected},
    }


def require_manifest_object(
    manifest: dict[str, Any],
    filename: str,
) -> dict[str, Any]:
    if int(manifest.get("schema_version") or 0) != 1:
        raise RuntimeError("El manifiesto de entrada del reporte no es valido.")
    objects = manifest.get("objects")
    if not isinstance(objects, dict):
        raise RuntimeError("El manifiesto de entrada no contiene objetos.")
    item = objects.get(filename)
    if not isinstance(item, dict):
        raise RuntimeError(f"El manifiesto no contiene {filename}.")
    if not item.get("object") or not item.get("generation"):
        raise RuntimeError(f"La version publicada de {filename} no es valida.")
    return item
