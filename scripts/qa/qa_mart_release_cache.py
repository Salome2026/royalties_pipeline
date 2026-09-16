from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import threading
from typing import Any

from google.api_core.exceptions import NotFound

from scripts.lib.mart_release import publish_mart_release
from scripts.lib.mart_release_cache import MartReleaseCache


FILES = ("a.parquet", "b.parquet")


class FakeBlob:
    def __init__(self, bucket: "FakeBucket", name: str, generation: int | None = None) -> None:
        self.bucket = bucket
        self.name = name
        self.generation = generation
        self.size: int | None = None
        self.md5_hash: str | None = None
        self.crc32c: str | None = None

    def _record(self) -> dict[str, Any]:
        with self.bucket.lock:
            generation = self.generation or self.bucket.current.get(self.name)
            record = self.bucket.objects.get((self.name, generation))
        if record is None:
            raise NotFound(self.name)
        return record

    def reload(self, client: Any = None) -> None:
        record = self._record()
        self.generation = record["generation"]
        self.size = len(record["data"])
        self.md5_hash = record["md5_hash"]
        self.crc32c = None

    def download_as_bytes(self, if_generation_match: int | None = None) -> bytes:
        record = self._record()
        if if_generation_match and record["generation"] != if_generation_match:
            raise RuntimeError("generation changed")
        return record["data"]

    def download_to_filename(
        self,
        filename: str,
        if_generation_match: int | None = None,
    ) -> None:
        data = self.download_as_bytes(if_generation_match=if_generation_match)
        with self.bucket.lock:
            self.bucket.downloads[self.name] = self.bucket.downloads.get(self.name, 0) + 1
        Path(filename).write_bytes(data)

    def upload_from_filename(self, filename: str, if_generation_match: int | None = None) -> None:
        if if_generation_match == 0 and self.name in self.bucket.current:
            raise RuntimeError("object already exists")
        self.bucket.put(self.name, Path(filename).read_bytes(), self)

    def upload_from_string(self, value: str, content_type: str | None = None) -> None:
        self.bucket.put(self.name, value.encode("utf-8"), self)


class FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, int], dict[str, Any]] = {}
        self.current: dict[str, int] = {}
        self.downloads: dict[str, int] = {}
        self.events: list[str] = []
        self.next_generation = 1
        self.lock = threading.RLock()

    def blob(self, name: str, generation: int | None = None) -> FakeBlob:
        return FakeBlob(self, name, generation)

    def put(self, name: str, data: bytes, blob: FakeBlob | None = None) -> FakeBlob:
        with self.lock:
            generation = self.next_generation
            self.next_generation += 1
            record = {
                "generation": generation,
                "data": data,
                "md5_hash": hashlib.md5(data).hexdigest(),  # noqa: S324 - test double only
            }
            self.objects[(name, generation)] = record
            self.current[name] = generation
            self.events.append(f"put:{name}")
        target = blob or FakeBlob(self, name, generation)
        target.generation = generation
        target.size = len(data)
        target.md5_hash = record["md5_hash"]
        return target

    def copy_blob(self, source: FakeBlob, bucket: "FakeBucket", new_name: str) -> FakeBlob:
        source.reload()
        return bucket.put(new_name, source.download_as_bytes())


class FakeClient:
    def __init__(self, bucket: FakeBucket) -> None:
        self._bucket = bucket

    def bucket(self, name: str) -> FakeBucket:
        return self._bucket


def validate_test_parquet(path: Path) -> None:
    data = path.read_bytes()
    if not (data.startswith(b"PAR1") and data.endswith(b"PAR1")):
        raise ValueError(f"invalid parquet test payload: {path.name}")


def write_release_files(root: Path, marker: str, *, corrupt_a: bool = False) -> list[tuple[str, Path]]:
    uploads = []
    for filename in FILES:
        payload = f"PAR1-{marker}-{filename}-PAR1".encode("ascii")
        if filename == "a.parquet" and corrupt_a:
            payload = b"broken"
        path = root / f"{marker}-{filename}"
        path.write_bytes(payload)
        uploads.append((filename, path))
    return uploads


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="vpo-mart-cache-") as temporary:
        root = Path(temporary)
        bucket = FakeBucket()
        client = FakeClient(bucket)
        first = publish_mart_release(
            bucket,
            "marts",
            write_release_files(root, "r1"),
            release_id="r1",
        )
        manifest_event = bucket.events.index("put:marts/release_manifest.json")
        assert manifest_event > bucket.events.index("put:marts/releases/r1/a.parquet")
        assert manifest_event > bucket.events.index("put:marts/releases/r1/b.parquet")

        cache = MartReleaseCache(
            cache_dir=root / "cache",
            bucket_name="bucket",
            prefix="marts",
            required_files=FILES,
            client_factory=lambda: client,
            validator=validate_test_parquet,
            check_interval_seconds=0,
        )
        first_path = cache.ensure(["a.parquet"])["a.parquet"]
        assert b"r1" in first_path.read_bytes()
        assert cache.status()["active_release_id"] == first["release_id"]

        second_start = len(bucket.events)
        publish_mart_release(
            bucket,
            "marts",
            write_release_files(root, "r2", corrupt_a=True),
            release_id="r2",
        )
        assert bucket.events[second_start:][-1] == "put:marts/release_manifest.json"
        fallback_path = cache.ensure(["a.parquet"])["a.parquet"]
        assert fallback_path == first_path
        assert cache.status()["using_stale_fallback"] is True
        assert cache.status()["last_error"]

        publish_mart_release(
            bucket,
            "marts",
            write_release_files(root, "r3"),
            release_id="r3",
        )
        before = bucket.downloads.get("marts/releases/r3/b.parquet", 0)
        with ThreadPoolExecutor(max_workers=8) as executor:
            paths = list(executor.map(lambda _: cache.ensure(["b.parquet"])["b.parquet"], range(8)))
        after = bucket.downloads.get("marts/releases/r3/b.parquet", 0)
        assert len(set(paths)) == 1
        assert after - before == 1
        assert b"r3" in paths[0].read_bytes()
        assert cache.status()["active_release_id"] == "r3"
        assert cache.status()["using_stale_fallback"] is False

        manifest_generation = bucket.current["marts/release_manifest.json"]
        manifest = json.loads(
            bucket.objects[("marts/release_manifest.json", manifest_generation)]["data"]
        )
        assert set(manifest["files"]) == set(FILES)
        print({
            "ok": True,
            "active_release": cache.status()["active_release_id"],
            "concurrent_downloads": after - before,
            "fallback_verified": True,
            "manifest_last": True,
        })


if __name__ == "__main__":
    main()
