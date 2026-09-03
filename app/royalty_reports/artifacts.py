from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from google.cloud import storage

from app.royalty_reports.contracts import StoredArtifact


@dataclass(frozen=True)
class GcsReportArtifactStore:
    bucket_name: str
    results_prefix: str
    client_factory: Callable[[], storage.Client]

    def upload(self, job_id: int, output_path: Path, content_type: str) -> StoredArtifact:
        if not self.bucket_name:
            raise RuntimeError("GCS_BUCKET no esta configurado para guardar el reporte.")
        size_bytes = output_path.stat().st_size
        digest = hashlib.sha256()
        with output_path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        sha256 = digest.hexdigest()
        prefix = self.results_prefix.strip("/")
        object_path = f"{prefix}/{job_id}/{output_path.name}" if prefix else (
            f"{job_id}/{output_path.name}"
        )
        client = self.client_factory()
        blob = client.bucket(self.bucket_name).blob(object_path)
        blob.metadata = {
            "vpo-report-run-id": str(job_id),
            "vpo-sha256": sha256,
        }
        blob.upload_from_filename(
            str(output_path),
            content_type=content_type,
            if_generation_match=0,
        )
        return StoredArtifact(
            uri=f"gs://{self.bucket_name}/{object_path}",
            size_bytes=size_bytes,
            sha256=sha256,
        )
