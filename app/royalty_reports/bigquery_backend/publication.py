"""Publish complete, versioned report inputs for the isolated application."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from pathlib import Path
from uuid import uuid4

from google.api_core.exceptions import Conflict, NotFound
from google.cloud import bigquery


LOGGER = logging.getLogger(__name__)
PROJECT = "vpo-corp-royalties"
ARCHIVE_DATASET = "report_g2_isolated_20261110"
LABELS = {"purpose": "report_equivalence", "scope": "isolated_app_test"}
LIVE_LABELS = {"purpose": "royalty_reports", "scope": "royalty_report_live"}
LIVE_DATASET = "royalty_report_publications"
LIVE_BUCKET = "vpo-corp-royalties-report-publications"
LIVE_NAMESPACE = "royalty_reports"


class PublicationError(ValueError):
    pass


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def file_sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4().hex}.pending")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def table_binding(table: bigquery.Table) -> dict:
    return {
        "rows": table.num_rows,
        "schema": [field.to_api_repr() for field in table.schema],
        "modified": table.modified.isoformat(),
        "etag": table.etag,
    }


class ReportPublications:
    def __init__(self, client: bigquery.Client, root: Path, dataset: str, *, live: bool = False) -> None:
        valid_dataset = dataset == LIVE_DATASET if live else re.fullmatch(r"report_app_test_[a-z0-9_]+", dataset)
        if client.project != PROJECT or not valid_dataset:
            raise ValueError("El dataset no corresponde al entorno de publicación de regalías.")
        self.client = client
        self.root = root.resolve()
        self.dataset = f"{PROJECT}.{dataset}"
        self.labels = LIVE_LABELS if live else LABELS
        self.live = live
        self.lock = threading.RLock()

    def initialize(self) -> None:
        dataset = bigquery.Dataset(self.dataset)
        dataset.location = "US"
        dataset.labels = self.labels
        if not self.live:
            dataset.default_table_expiration_ms = 30 * 24 * 60 * 60 * 1000
        actual = self.client.create_dataset(dataset, exists_ok=True)
        self.check_dataset(actual)

    def check_dataset(self, dataset: bigquery.Dataset) -> None:
        if (f"{dataset.project}.{dataset.dataset_id}" != self.dataset or dataset.location != "US"
                or any(dataset.labels.get(k) != v for k, v in self.labels.items())):
            raise PublicationError("El dataset no pertenece al entorno de publicación de regalías.")

    def source_archive(self, name: str, kind: str) -> bigquery.Table:
        prefix = f"{PROJECT}.{ARCHIVE_DATASET}."
        ingested = re.fullmatch(re.escape(self.dataset) + rf"\.ingest_{kind}_[0-9a-f]{{24}}", name)
        if not ingested and (self.live or not re.fullmatch(re.escape(prefix) + rf"report_{kind}_[0-9a-f]{{24}}", name)):
            raise PublicationError("El origen no pertenece a la copia verificada.")
        table = self.client.get_table(name)
        expected_scope = self.labels["scope"] if ingested else "isolated_g2_test"
        if table.labels.get("scope") != expected_scope or table.labels.get("role") != kind:
            raise PublicationError("El origen no corresponde al componente de prueba.")
        return table

    def paths(self, release: dict) -> dict[str, Path]:
        paths = {}
        for item in release["context"]["artifacts"]:
            path = (self.root / item["path"]).resolve()
            if not path.is_relative_to(self.root / "contexts") or file_sha(path) != item["sha256"]:
                raise PublicationError("Cambió un archivo del contexto fijado.")
            if item["role"] in paths:
                raise PublicationError("El contexto contiene un componente duplicado.")
            paths[item["role"]] = path
        return paths

    def validate(self, release: dict) -> None:
        scope = release["scope"]
        required = {"raw", "song", "eligible"} if scope == "regular" else {"raw", "song"}
        if scope not in {"regular", "wml"} or set(release["components"]) != required:
            raise PublicationError("Faltan componentes de la publicación.")
        if not re.fullmatch(r"[a-z0-9_]{1,80}", release["publication_id"]):
            raise PublicationError("El identificador de publicación es inválido.")
        if type(release["sequence"]) is not int or release["sequence"] < 1:
            raise PublicationError("La secuencia de publicación es inválida.")
        if release["context_id"] != digest(release["context"]):
            raise PublicationError("La identidad del contexto no coincide.")
        for kind, component in release["components"].items():
            manifest = component["manifest"]
            if digest(manifest) != component["manifest_sha256"]:
                raise PublicationError("La identidad del esquema no coincide.")
            if kind != "eligible" and manifest["release_id"] != release["source_release_id"]:
                raise PublicationError("El esquema no corresponde a la versión del reporte.")
        self.paths(release)

    def component_table(self, release: dict, kind: str) -> str:
        if kind not in release["components"]:
            raise PublicationError("El componente no está publicado.")
        return f"{self.dataset}.report_{kind}_{digest(release)[:24]}"

    def _copy(self, release: dict, kind: str, component: dict) -> dict:
        source = self.source_archive(component["source_table"], kind)
        if table_binding(source) != component["source_binding"]:
            raise PublicationError("El origen de la publicación cambió.")
        destination = self.component_table(release, kind)
        identity = digest({"dataset": self.dataset, "release": release, "kind": kind})
        job_id = f"report_app_copy_{identity[:36]}"
        try:
            job = self.client.get_job(job_id, location="US")
        except NotFound:
            try:
                job = self.client.copy_table(
                    source.reference,
                    destination,
                    job_id=job_id,
                    location="US",
                    job_config=bigquery.CopyJobConfig(write_disposition="WRITE_EMPTY", labels=self.labels),
                )
            except Conflict:
                job = self.client.get_job(job_id, location="US")
        if job.job_type != "copy" or str(job.destination) != destination or list(map(str, job.sources)) != [str(source.reference)]:
            raise PublicationError("El trabajo de copia corresponde a otra publicación.")
        job.result(timeout=900)
        after = self.source_archive(component["source_table"], kind)
        if table_binding(after) != component["source_binding"]:
            raise PublicationError("El origen cambió durante la copia.")
        copied = self.client.get_table(destination)
        binding = table_binding(copied)
        if any(binding[key] != component["source_binding"][key] for key in ("schema", "rows")):
            raise PublicationError("La copia no conserva el esquema o la cantidad completa de filas.")
        return {"binding": binding, "copy_job_id": job_id, "source": str(source.reference)}

    def prepare(self, release: dict) -> dict:
        self.validate(release)
        ready = self.read_ready(release["publication_id"])
        if ready is not None:
            if ready["release"] != release:
                raise PublicationError("Ya existe otra publicación con el mismo identificador.")
        else:
            checks = {
                kind: self._copy(release, kind, component)
                for kind, component in release["components"].items()
            }
            ready = {"release": release, "tables": checks}
            self.write_ready(ready)
        return ready

    def publish(self, release: dict) -> dict:
        ready = self.prepare(release)
        self.activate(release)
        return ready

    def read_ready(self, publication_id: str) -> dict | None:
        path = self.root / "ready" / (publication_id + ".json")
        return read_json(path) if path.exists() else None

    def write_ready(self, ready: dict) -> None:
        release = ready["release"]
        self.paths(release)
        write_json(self.root / "ready" / (release["publication_id"] + ".json"), ready)

    def activate(self, release: dict) -> None:
        with self.lock:
            pointer = self.root / "active" / (release["scope"] + ".json")
            current = read_json(pointer) if pointer.exists() else None
            if current and current["sequence"] == release["sequence"] and current["id"] != release["publication_id"]:
                raise PublicationError("Dos publicaciones tienen la misma secuencia.")
            if current is None or current["sequence"] < release["sequence"]:
                write_json(pointer, {
                    "id": release["publication_id"],
                    "sequence": release["sequence"],
                    "sha256": digest(release),
                })

    def read_active(self, scope: str) -> dict | None:
        path = self.root / "active" / (scope + ".json")
        with self.lock:
            return read_json(path) if path.exists() else None

    def pin(self, scope: str) -> dict:
        if scope not in {"regular", "wml"}:
            raise PublicationError("El ámbito del reporte es inválido.")
        active = self.read_active(scope)
        if active is None:
            raise PublicationError("Todavía no hay una publicación lista para este ámbito.")
        return {"scope": scope, "publication_id": active["id"], "envelope_sha256": active["sha256"]}

    def checked(self, pin: dict) -> dict:
        publication_id = pin["publication_id"]
        if not re.fullmatch(r"[a-z0-9_]{1,80}", publication_id):
            raise PublicationError("La publicación fijada es inválida.")
        ready = self.read_ready(publication_id)
        if ready is None:
            raise PublicationError("No está disponible la publicación fijada.")
        release = ready["release"]
        if release["scope"] != pin["scope"] or digest(release) != pin["envelope_sha256"]:
            raise PublicationError("La publicación fijada no coincide con el pedido.")
        if set(ready["tables"]) != set(release["components"]):
            raise PublicationError("Faltan verificaciones de tablas en la publicación fijada.")
        for kind, expected in ready["tables"].items():
            actual = self.client.get_table(self.component_table(release, kind))
            if table_binding(actual) != expected["binding"]:
                raise PublicationError("Cambió una tabla de la publicación fijada.")
        self.paths(release)
        return release


def watch_publications(publications: ReportPublications, stop: threading.Event, interval: float) -> None:
    """Publish complete envelopes from the local test pipeline as they arrive."""
    inbox = publications.root / "incoming"
    last_seen: dict[Path, tuple[int, int]] = {}
    while not stop.is_set():
        for path in sorted(inbox.glob("*.json")):
            if stop.is_set():
                return
            stat = path.stat()
            revision = (stat.st_mtime_ns, stat.st_size)
            if last_seen.get(path) == revision:
                continue
            status_path = publications.root / "publication_status" / path.name
            try:
                release = read_json(path)
                result = publications.publish(release)
                write_json(status_path, {
                    "status": "ready",
                    "publication": release["publication_id"],
                    "tables": result["tables"],
                })
                last_seen[path] = revision
            except (PublicationError, KeyError, FileNotFoundError, json.JSONDecodeError) as exc:
                write_json(status_path, {"status": "rejected", "reason": str(exc)})
                last_seen[path] = revision
                LOGGER.warning("Se rechazó la publicación %s: %s", path.name, exc)
            except Exception:
                LOGGER.exception("La publicación %s se reintentará", path.name)
                stop.wait(15)
        stop.wait(interval)
