from __future__ import annotations

from typing import Any, Iterable

from google.cloud import storage


REPORT_INPUT_FILENAMES = (
    "song_level_all_sources.parquet",
    "standardized_raw_all_sources.parquet",
    "catalog_master.parquet",
    "catalog_status.parquet",
)


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
    names = {gcs_object_name(prefix, filename): filename for filename in expected}
    objects: dict[str, dict[str, Any]] = {}
    for blob in client.list_blobs(bucket_name, prefix=prefix.strip("/") or None):
        filename = names.get(blob.name)
        if filename is None:
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
