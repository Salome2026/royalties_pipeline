from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid
from typing import Any, Iterable

from google.api_core.exceptions import NotFound


RELEASE_SCHEMA_VERSION = 1
RELEASE_MANIFEST_FILE = "release_manifest.json"
RELEASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def prefixed_object_name(prefix: str, name: str) -> str:
    normalized = prefix.strip("/")
    return f"{normalized}/{name}" if normalized else name


def release_object_name(prefix: str, release_id: str, filename: str) -> str:
    return prefixed_object_name(prefix, f"releases/{release_id}/{filename}")


def manifest_object_name(prefix: str) -> str:
    return prefixed_object_name(prefix, RELEASE_MANIFEST_FILE)


def new_release_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid.uuid4().hex[:12]}"


def validate_release_manifest(document: Any, required_files: Iterable[str]) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("Release manifest must be a JSON object.")
    if int(document.get("schema_version") or 0) != RELEASE_SCHEMA_VERSION:
        raise ValueError("Unsupported release manifest schema version.")
    release_id = str(document.get("release_id") or "")
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise ValueError("Invalid release_id in release manifest.")
    files = document.get("files")
    if not isinstance(files, dict):
        raise ValueError("Release manifest has no files map.")

    missing = [filename for filename in required_files if filename not in files]
    if missing:
        raise ValueError(f"Release manifest is missing files: {', '.join(missing)}")
    for filename, entry in files.items():
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid manifest entry for {filename}.")
        if not str(entry.get("object_name") or ""):
            raise ValueError(f"Manifest entry has no object_name: {filename}.")
        if int(entry.get("generation") or 0) <= 0:
            raise ValueError(f"Manifest entry has no generation: {filename}.")
        if int(entry.get("size_bytes") or 0) <= 0:
            raise ValueError(f"Manifest entry has no size: {filename}.")
    return document


def publish_mart_release(
    bucket: Any,
    prefix: str,
    uploads: Iterable[tuple[str, Path]],
    *,
    release_id: str | None = None,
) -> dict[str, Any]:
    release_id = release_id or new_release_id()
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise ValueError("Invalid release_id.")

    upload_items = [(filename, Path(path)) for filename, path in uploads]
    if not upload_items:
        raise ValueError("A release requires at least one mart.")
    for filename, path in upload_items:
        if not path.exists():
            raise FileNotFoundError(path)

    entries: dict[str, dict[str, Any]] = {}
    release_blobs: dict[str, Any] = {}
    for filename, path in upload_items:
        object_name = release_object_name(prefix, release_id, filename)
        blob = bucket.blob(object_name)
        blob.upload_from_filename(str(path), if_generation_match=0)
        blob.reload()
        release_blobs[filename] = blob
        entries[filename] = {
            "object_name": object_name,
            "generation": str(blob.generation),
            "size_bytes": int(blob.size or path.stat().st_size),
            "md5_hash": blob.md5_hash,
            "crc32c": blob.crc32c,
        }

    manifest = {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "release_id": release_id,
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": entries,
    }
    manifest_blob = bucket.blob(manifest_object_name(prefix))
    manifest_payload = json.dumps(manifest, ensure_ascii=True, sort_keys=True, indent=2)
    try:
        manifest_blob.reload()
        first_release = False
    except NotFound:
        first_release = True

    # On the first migration there is no prior manifest protecting readers
    # from sequential canonical copies. Activate the complete immutable package
    # first. Later releases keep the old manifest active until every copy ends.
    if first_release:
        manifest_blob.upload_from_string(manifest_payload, content_type="application/json")

    for filename, _ in upload_items:
        bucket.copy_blob(
            release_blobs[filename],
            bucket,
            new_name=prefixed_object_name(prefix, filename),
        )

    if not first_release:
        manifest_blob.upload_from_string(manifest_payload, content_type="application/json")
    manifest_blob.reload()
    return {
        **manifest,
        "manifest_object_name": manifest_blob.name,
        "manifest_generation": str(manifest_blob.generation),
    }
