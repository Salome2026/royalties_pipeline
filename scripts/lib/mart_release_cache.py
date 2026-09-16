from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
from typing import Any, Callable, Iterable
import uuid

from google.api_core.exceptions import NotFound

from .mart_release import manifest_object_name, prefixed_object_name, validate_release_manifest


class MartReleaseCacheError(RuntimeError):
    pass


class MartReleaseCache:
    def __init__(
        self,
        *,
        cache_dir: Path,
        bucket_name: str,
        prefix: str,
        required_files: Iterable[str],
        client_factory: Callable[[], Any],
        validator: Callable[[Path], None],
        check_interval_seconds: float = 15.0,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.bucket_name = bucket_name
        self.prefix = prefix.strip("/")
        self.required_files = tuple(required_files)
        self.client_factory = client_factory
        self.validator = validator
        self.check_interval_seconds = max(0.0, float(check_interval_seconds))
        self._lock = threading.RLock()
        self._snapshot: dict[str, Any] | None = None
        self._snapshot_checked_at = 0.0
        self._last_error: str | None = None
        self._using_stale_fallback = False

    @property
    def active_path(self) -> Path:
        return self.cache_dir / "active_release.json"

    def ensure(self, requested_files: Iterable[str], *, refresh: bool = False) -> dict[str, Path]:
        requested = tuple(dict.fromkeys(requested_files))
        unsupported = [name for name in requested if name not in self.required_files]
        if unsupported:
            raise MartReleaseCacheError(f"Unsupported mart files: {', '.join(unsupported)}")

        with self._lock:
            previous = self._read_active()
            try:
                snapshot = self._remote_snapshot(force=refresh)
                paths = self._activate(snapshot, requested, refresh=refresh)
                self._last_error = None
                self._using_stale_fallback = False
                return paths
            except Exception as exc:
                self._last_error = str(exc)
                fallback = self._paths_for_active(previous, requested)
                if fallback and not refresh:
                    self._using_stale_fallback = True
                    return fallback
                if isinstance(exc, MartReleaseCacheError):
                    raise
                raise MartReleaseCacheError(str(exc)) from exc

    def status(self) -> dict[str, Any]:
        with self._lock:
            active = self._read_active() or {}
            return {
                "active_release_id": active.get("release_id"),
                "active_cache_key": active.get("cache_key"),
                "source_mode": active.get("source_mode"),
                "manifest_generation": active.get("manifest_generation"),
                "activated_at": active.get("activated_at"),
                "using_stale_fallback": self._using_stale_fallback,
                "last_error": self._last_error,
            }

    def _remote_snapshot(self, *, force: bool) -> dict[str, Any]:
        now = time.monotonic()
        if (
            not force
            and self._snapshot is not None
            and now - self._snapshot_checked_at < self.check_interval_seconds
        ):
            return self._snapshot

        client = self.client_factory()
        bucket = client.bucket(self.bucket_name)
        manifest_blob = bucket.blob(manifest_object_name(self.prefix))
        try:
            manifest_blob.reload(client=client)
        except NotFound:
            snapshot = self._legacy_snapshot(bucket, client)
        else:
            generation = int(manifest_blob.generation)
            payload = manifest_blob.download_as_bytes(if_generation_match=generation)
            manifest = validate_release_manifest(json.loads(payload), self.required_files)
            snapshot = {
                **manifest,
                "source_mode": "manifest",
                "manifest_generation": str(generation),
                "cache_key": f"manifest-{generation}",
            }
        self._snapshot = snapshot
        self._snapshot_checked_at = now
        return snapshot

    def _legacy_snapshot(self, bucket: Any, client: Any) -> dict[str, Any]:
        files: dict[str, dict[str, Any]] = {}
        identity: list[str] = []
        for filename in self.required_files:
            blob = bucket.blob(prefixed_object_name(self.prefix, filename))
            try:
                blob.reload(client=client)
            except NotFound as exc:
                raise MartReleaseCacheError(
                    f"GCS object not found: gs://{self.bucket_name}/{blob.name}"
                ) from exc
            generation = str(blob.generation)
            files[filename] = {
                "object_name": blob.name,
                "generation": generation,
                "size_bytes": int(blob.size or 0),
                "md5_hash": blob.md5_hash,
                "crc32c": blob.crc32c,
            }
            identity.append(f"{filename}:{generation}")
        digest = hashlib.sha256("|".join(identity).encode("utf-8")).hexdigest()[:20]
        return {
            "schema_version": 0,
            "release_id": f"legacy-{digest}",
            "published_at": None,
            "files": files,
            "source_mode": "legacy_generations",
            "manifest_generation": None,
            "cache_key": f"legacy-{digest}",
        }

    def _activate(
        self,
        snapshot: dict[str, Any],
        requested: tuple[str, ...],
        *,
        refresh: bool,
    ) -> dict[str, Path]:
        release_dir = self._release_dir(snapshot)
        existing = {name: release_dir / name for name in requested}
        missing = [name for name, path in existing.items() if refresh or not path.exists()]
        if missing:
            self._download_files(snapshot, release_dir, missing)
        for path in existing.values():
            self.validator(path)

        active = {
            "schema_version": 1,
            "release_id": snapshot["release_id"],
            "cache_key": snapshot["cache_key"],
            "source_mode": snapshot["source_mode"],
            "manifest_generation": snapshot.get("manifest_generation"),
            "release_dir": str(release_dir),
            "activated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._write_json_atomic(self.active_path, active)
        return existing

    def _download_files(
        self,
        snapshot: dict[str, Any],
        release_dir: Path,
        filenames: list[str],
    ) -> None:
        client = self.client_factory()
        bucket = client.bucket(self.bucket_name)
        staging = self.cache_dir / "staging" / f"{snapshot['cache_key']}-{uuid.uuid4().hex}"
        staging.mkdir(parents=True, exist_ok=False)
        try:
            staged: dict[str, Path] = {}
            for filename in filenames:
                entry = snapshot["files"][filename]
                generation = int(entry["generation"])
                blob = bucket.blob(entry["object_name"], generation=generation)
                temp_path = staging / filename
                blob.download_to_filename(
                    str(temp_path),
                    if_generation_match=generation,
                )
                expected_size = int(entry.get("size_bytes") or 0)
                if expected_size and temp_path.stat().st_size != expected_size:
                    raise MartReleaseCacheError(
                        f"Downloaded size mismatch for {filename}: "
                        f"{temp_path.stat().st_size} != {expected_size}"
                    )
                self.validator(temp_path)
                staged[filename] = temp_path

            release_dir.mkdir(parents=True, exist_ok=True)
            for filename, temp_path in staged.items():
                os.replace(temp_path, release_dir / filename)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def _release_dir(self, snapshot: dict[str, Any]) -> Path:
        suffix = hashlib.sha256(snapshot["cache_key"].encode("utf-8")).hexdigest()[:12]
        return self.cache_dir / "releases" / f"{snapshot['release_id']}-{suffix}"

    def _read_active(self) -> dict[str, Any] | None:
        if not self.active_path.exists():
            return None
        try:
            document = json.loads(self.active_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        release_dir = Path(str(document.get("release_dir") or ""))
        try:
            release_dir.resolve().relative_to((self.cache_dir / "releases").resolve())
        except (OSError, ValueError):
            return None
        return document

    def _paths_for_active(
        self,
        active: dict[str, Any] | None,
        requested: tuple[str, ...],
    ) -> dict[str, Path] | None:
        if not active:
            return None
        release_dir = Path(active["release_dir"])
        paths = {name: release_dir / name for name in requested}
        if not all(path.exists() for path in paths.values()):
            return None
        try:
            for path in paths.values():
                self.validator(path)
        except Exception:
            return None
        return paths

    @staticmethod
    def _write_json_atomic(path: Path, document: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(document, ensure_ascii=True, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
