from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


BASE = Path(__file__).resolve().parents[2]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from app.royalty_reports.artifacts import GcsReportArtifactStore  # noqa: E402
from app.royalty_reports.cloud_runtime import GcsReportInputStore  # noqa: E402


class FakeBlob:
    def __init__(self, name: str, payload: bytes = b"mart") -> None:
        self.name = name
        self.payload = payload
        self.metadata: dict[str, str] | None = None
        self.upload: dict | None = None
        self.generation = 7
        self.size = len(payload)
        self.crc32c = "crc"
        self.updated = None

    def exists(self, client) -> bool:
        return True

    def download_to_filename(self, filename: str) -> None:
        Path(filename).write_bytes(self.payload)

    def upload_from_filename(self, filename: str, **kwargs) -> None:
        self.payload = Path(filename).read_bytes()
        self.upload = kwargs


class FakeBucket:
    def __init__(self) -> None:
        self.blobs: dict[str, FakeBlob] = {}

    def blob(self, name: str, generation: int | None = None) -> FakeBlob:
        return self.blobs.setdefault(name, FakeBlob(name))


class FakeClient:
    def __init__(self) -> None:
        self.buckets: dict[str, FakeBucket] = {}

    def bucket(self, name: str) -> FakeBucket:
        return self.buckets.setdefault(name, FakeBucket())


def main() -> None:
    if "app.vpo_corp_api" in sys.modules:
        raise AssertionError("El Job no debe importar la API web.")

    client = FakeClient()
    with tempfile.TemporaryDirectory(prefix="vpo-cloud-job-qa-") as raw_dir:
        root = Path(raw_dir)
        inputs = GcsReportInputStore(
            bucket_name="bucket",
            marts_prefix="marts",
            cache_dir=root / "marts",
            client_factory=lambda: client,
        )
        paths = inputs.resolve(
            {
                "schema_version": 1,
                "bucket": "bucket",
                "objects": {
                    "song.parquet": {
                        "object": "marts/song.parquet",
                        "generation": 7,
                        "size_bytes": 4,
                    },
                    "catalog_status.parquet": {
                        "object": "marts/catalog_status.parquet",
                        "generation": 7,
                        "size_bytes": 4,
                    },
                },
            },
            ["song.parquet"],
        )
        if set(paths) != {"song.parquet", "catalog_status.parquet"}:
            raise AssertionError(f"Entradas cloud inesperadas: {sorted(paths)}")
        if not all(path.exists() for path in paths.values()):
            raise AssertionError("Los marts no fueron materializados.")

        output = root / "report.xlsx"
        output.write_bytes(b"report-binary")
        artifacts = GcsReportArtifactStore(
            bucket_name="bucket",
            results_prefix="reports/jobs",
            client_factory=lambda: client,
        )
        stored = artifacts.upload(44, output, "application/test")
        blob = client.bucket("bucket").blob("reports/jobs/44/report.xlsx")
        if blob.upload != {
            "content_type": "application/test",
            "if_generation_match": 0,
        }:
            raise AssertionError(f"Publicacion GCS no atomica: {blob.upload}")
        if stored.size_bytes != len(b"report-binary") or len(stored.sha256) != 64:
            raise AssertionError("Metadata de integridad invalida.")
        if blob.metadata != {
            "vpo-report-run-id": "44",
            "vpo-sha256": stored.sha256,
        }:
            raise AssertionError("La metadata del objeto no coincide con Cloud SQL.")

    os.environ.pop("VPO_CATALOG_MASTER_PATH", None)
    os.environ.pop("VPO_CATALOG_STATUS_PATH", None)
    print("OK: runtime cloud aislado, entradas GCS y publicacion integra.")


if __name__ == "__main__":
    main()
