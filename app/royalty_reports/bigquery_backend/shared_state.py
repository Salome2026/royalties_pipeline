"""Publication pointers and complete downloads shared by isolated report processes."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from uuid import uuid4

from google.api_core.exceptions import NotFound, PreconditionFailed

from app.royalty_reports.contracts import ReportBuildResult
from .publication import LABELS, LIVE_BUCKET, LIVE_LABELS, LIVE_NAMESPACE, PROJECT, PublicationError, ReportPublications, digest, file_sha


class SharedReportState:
    def __init__(self, client, bucket_name: str, namespace: str, *, live: bool = False):
        valid_target = ((bucket_name, namespace) == (LIVE_BUCKET, LIVE_NAMESPACE) if live else
                        re.fullmatch(r"vpo-corp-royalties-report-ops-test-[0-9]{8}", bucket_name)
                        and re.fullmatch(r"[a-z0-9_]+", namespace))
        if client.project != PROJECT or not valid_target:
            raise ValueError("El estado compartido no corresponde al entorno de publicación de regalías.")
        self.bucket = client.get_bucket(bucket_name)
        labels = LIVE_LABELS if live else LABELS
        if (self.bucket.location != "US" or self.bucket.iam_configuration.public_access_prevention != "enforced"
                or not self.bucket.iam_configuration.uniform_bucket_level_access_enabled
                or any(self.bucket.labels.get(key) != value for key, value in labels.items())):
            raise ValueError("El bucket compartido no pertenece al entorno de publicación de regalías.")
        self.namespace = namespace
        self.live = live

    def blob(self, name: str, generation: int | None = None):
        return self.bucket.blob(f"{self.namespace}/{name}", generation=generation)

    def read(self, name: str, generation: int | None = None):
        blob = self.blob(name, generation)
        if generation is not None:
            return json.loads(blob.download_as_bytes(if_generation_match=generation))
        return self.current(name)[0]

    def current(self, name: str):
        for _ in range(8):
            blob = self.bucket.get_blob(self.blob(name).name)
            if blob is None:
                return None, 0
            try:
                return json.loads(blob.download_as_bytes(if_generation_match=blob.generation)), blob.generation
            except (NotFound, PreconditionFailed):
                continue
        raise PublicationError("El objeto compartido cambió durante la lectura.")

    def write(self, name: str, value, generation: int):
        blob = self.blob(name)
        blob.upload_from_string(json.dumps(value, ensure_ascii=False, allow_nan=False),
                                content_type="application/json", if_generation_match=generation)
        return blob.generation

    def result(self, job_id: int, files=None) -> ReportBuildResult | None:
        key = f"results/{job_id}/download.json"
        manifest, generation = self.current(key)
        if manifest is None and files is not None:
            attempt = uuid4().hex
            entries = []
            for item in files:
                name = item["name"]
                if Path(name).name != name:
                    raise ValueError("El nombre de descarga es inválido.")
                key_file = f"results/{job_id}/{attempt}/{name}"
                blob = self.blob(key_file)
                blob.chunk_size = 8 * 1024 * 1024
                blob.metadata = {"vpo-sha256": item["sha256"]}
                blob.upload_from_filename(str(item["path"]), content_type=item["content_type"],
                                          if_generation_match=0, checksum="crc32c", timeout=180)
                if blob.size != item["bytes"]:
                    raise ValueError("El tamaño guardado no coincide con el archivo generado.")
                entries.append({**{k: v for k, v in item.items() if k != "path"},
                                "object": key_file, "generation": blob.generation})
            manifest = {"job_id": job_id, "files": entries}
            try:
                generation = self.write(key, manifest, 0)
            except PreconditionFailed:
                manifest, generation = self.current(key)
        if manifest is None:
            return None
        first = manifest["files"][0]
        uri = f"report-bundle://{self.bucket.name}/{self.namespace}/{key}#{generation}"
        return ReportBuildResult(uri, first["name"], first["content_type"], None, first["bytes"], first["sha256"])

    def files(self, job_id: int) -> list[dict]:
        manifest = self.read(f"results/{job_id}/download.json")
        return manifest["files"] if manifest is not None else []

    def download(self, job_id: int, part: str, uri: str):
        key = f"results/{job_id}/download.json"
        expected = f"report-bundle://{self.bucket.name}/{self.namespace}/{key}#"
        generation = uri.removeprefix(expected)
        if not generation.isascii() or not generation.isdigit():
            raise FileNotFoundError("La referencia de descarga es inválida.")
        try:
            manifest = self.read(key, int(generation))
            index = 0 if part == "primary" else 1
            if index >= len(manifest["files"]) or manifest["job_id"] != job_id:
                raise FileNotFoundError("El reporte no tiene ese archivo.")
            item = manifest["files"][index]
            blob = self.blob(item["object"], item["generation"])
            blob.reload(if_generation_match=blob.generation)
            if blob.size != item["bytes"] or (blob.metadata or {}).get("vpo-sha256") != item["sha256"]:
                raise FileNotFoundError("El archivo guardado no coincide con el reporte.")
        except (NotFound, PreconditionFailed) as exc:
            raise FileNotFoundError("El archivo del reporte ya no está disponible.") from exc
        return blob, item


class SharedReportPublications(ReportPublications):
    def __init__(self, client, root: Path, dataset: str, state: SharedReportState):
        super().__init__(client, root, dataset, live=state.live)
        self.state = state

    def paths(self, release: dict) -> dict[str, Path]:
        for item in release["context"]["artifacts"]:
            path = (self.root / item["path"]).resolve()
            sha256 = item["sha256"]
            if not path.is_relative_to(self.root / "contexts") or not re.fullmatch(r"[0-9a-f]{64}", sha256):
                raise PublicationError("La ruta del contexto fijado es inválida.")
            if path.is_file():
                continue
            blob = self.state.bucket.get_blob(self.state.blob(f"context/{sha256}").name)
            if blob is None:
                raise PublicationError("Falta un archivo del contexto publicado.")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f"{path.name}.{uuid4().hex}.pending")
            try:
                blob.download_to_filename(str(temporary), if_generation_match=blob.generation)
                if file_sha(temporary) != sha256:
                    raise PublicationError("Cambió un archivo del contexto compartido.")
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        return super().paths(release)

    def read_ready(self, publication_id: str) -> dict | None:
        return self.state.read(f"ready/{publication_id}.json")

    def write_ready(self, ready: dict) -> None:
        release = ready["release"]
        paths = super().paths(release)
        for item in release["context"]["artifacts"]:
            path = paths[item["role"]]
            blob = self.state.blob(f"context/{item['sha256']}")
            try:
                blob.upload_from_filename(str(path), if_generation_match=0, checksum="crc32c")
            except PreconditionFailed:
                pass  # An existing object has the same content address. Readers verify its SHA-256.
        key = f"ready/{release['publication_id']}.json"
        try:
            self.state.write(key, ready, 0)
        except PreconditionFailed:
            if self.state.read(key) != ready:
                raise PublicationError("Ya existe otra publicación con el mismo identificador.")

    def read_active(self, scope: str) -> dict | None:
        return self.state.read(f"active/{scope}.json")

    def activate(self, release: dict) -> None:
        pointer = {"id": release["publication_id"], "sequence": release["sequence"], "sha256": digest(release)}
        key = f"active/{release['scope']}.json"
        self.checked({"scope": release["scope"], "publication_id": pointer["id"],
                      "envelope_sha256": pointer["sha256"]})
        for _ in range(8):
            current, generation = self.state.current(key)
            if current and current["sequence"] >= pointer["sequence"]:
                if current["sequence"] == pointer["sequence"] and current != pointer:
                    raise PublicationError("Dos publicaciones tienen la misma secuencia.")
                return
            try:
                self.state.write(key, pointer, generation)
                return
            except PreconditionFailed:
                continue
        raise PublicationError("No se pudo fijar la publicación activa por cambios simultáneos.")
