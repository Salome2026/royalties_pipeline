"""Prepare a private BigQuery publication from the production Parquet cut."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

from google.cloud import bigquery, storage
import requests

from app.operational_db import operational_connect
from app.royalty_scope import RELEASE, WML_DATASET, WML_FILES, WML_OPTIONAL_FILES, wml_policy, wml_release_prefix
from app.royalty_workspace_store import settings as wml_settings
from scripts.lib.distributor_policy_store import read_distributor_policy_document
from scripts.lib.mart_release import validate_release_manifest
from .publication import LIVE_BUCKET, LIVE_DATASET, LIVE_NAMESPACE, PROJECT, PublicationError, digest, file_sha, write_json
from .publication_input import CONTEXT, MARTS, load_component, prepare_regular, reconcile_input
from .shared_state import SharedReportPublications, SharedReportState


SOURCE_BUCKET = "vpo-corp-royalties-marts"
SOURCE_PREFIX = "marts"
MUTABLE_INPUTS = ("catalog_status.parquet", "catalog_release_metadata.parquet")
REQUIRED_INPUTS = (*MARTS.values(), "catalog_master.parquet", "product_income_allocations.json", "native_identity_proofs.json")
WML_COMPONENTS = {kind: MARTS[kind] for kind in ("raw", "song")}


@contextmanager
def policy_connection():
    with operational_connect() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        if conn.execute("SELECT current_database() AS name").fetchone()["name"] != "vpo_corp":
            raise PublicationError("La publicación operativa requiere las reglas del catálogo de producción.")
        yield conn


def capture_source(bucket, *, connection=policy_connection):
    if bucket.name != SOURCE_BUCKET:
        raise PublicationError("El origen de la publicación de regalías es inválido.")
    manifest_blob = bucket.get_blob(f"{SOURCE_PREFIX}/release_manifest.json")
    if manifest_blob is None:
        raise PublicationError("Todavía no hay un cierre de Parquet publicado.")
    package = validate_release_manifest(
        json.loads(manifest_blob.download_as_bytes(if_generation_match=manifest_blob.generation)), REQUIRED_INPUTS
    )
    with connection() as conn:
        policy = read_distributor_policy_document(conn)
    files = {name: dict(package["files"][name]) for name in REQUIRED_INPUTS}
    for name, entry in files.items():
        expected = rf"{SOURCE_PREFIX}/releases/[0-9]{{8}}T[0-9]{{6}}Z-[a-f0-9]{{12}}/{re.escape(name)}"
        if not re.fullmatch(expected, entry["object_name"]):
            raise PublicationError(f"El origen fijado del archivo {name} es inválido.")
    for name in MUTABLE_INPUTS:
        item = bucket.get_blob(f"{SOURCE_PREFIX}/{name}")
        if item is None or not item.md5_hash:
            raise PublicationError(f"Falta el archivo de contexto {name}.")
        files[name] = {"object_name": item.name, "generation": str(item.generation),
                       "md5_hash": item.md5_hash, "size_bytes": item.size}
    sources = {"bucket": bucket.name, "generation": int(manifest_blob.generation),
               "release_id": package["release_id"], "files": files, "policy_sha256": digest(policy)}
    return sources, policy


def md5_file(path):
    with path.open("rb") as stream:
        return base64.b64encode(hashlib.file_digest(stream, "md5").digest()).decode("ascii")


def publication_id(sources):
    return f"regular_live_{digest(sources)[:32]}"


def wml_source_manifest(bucket, release_id):
    if bucket.name != SOURCE_BUCKET:
        raise PublicationError("El origen de la publicación WML es inválido.")
    return bucket.get_blob(f"{wml_release_prefix(release_id)}/release_manifest.json")


def wml_publication_id(release_id, manifest_generation):
    return f"wml_live_{digest({'release_id': release_id, 'generation': int(manifest_generation)})[:32]}"


def matches_current_cut(state, scope="regular"):
    active = state.read(f"active/{scope}.json")
    if active is None:
        return False
    bucket = state.bucket.client.bucket(SOURCE_BUCKET)
    if scope == "wml":
        release_id = RELEASE.get()
        manifest = wml_source_manifest(bucket, release_id) if release_id else None
        return manifest is not None and active["id"] == wml_publication_id(release_id, manifest.generation)
    sources, _ = capture_source(bucket)
    return active["id"] == publication_id(sources)


def download_inputs(bucket, sources, policy, folder, *, cache=None):
    folder.mkdir(parents=True, exist_ok=True)
    for name, entry in sources["files"].items():
        path = folder / name
        cached = cache / name if cache is not None else path
        if cached.is_file() and cached.stat().st_size == int(entry["size_bytes"]) and md5_file(cached) == entry["md5_hash"]:
            if path != cached:
                shutil.copyfile(cached, path)
            continue
        generation = int(entry["generation"])
        blob = bucket.blob(entry["object_name"], generation=generation)
        blob.download_to_filename(str(path), if_generation_match=generation, checksum="crc32c", timeout=180)
        if path.stat().st_size != int(entry["size_bytes"]) or md5_file(path) != entry["md5_hash"]:
            raise PublicationError(f"El archivo {name} cambió durante la lectura del corte publicado.")
    write_json(folder / CONTEXT["policy/policy_snapshot.json"], policy)
    write_json(folder / "release_manifest.json", sources)


def prepare_current(pub, source_bucket, *, connection=policy_connection, cache=None):
    """Advance the private readiness pointer after validating the complete cut."""
    if not pub.live:
        raise PublicationError("El publicador operativo requiere su destino exclusivo.")
    pub.check_dataset(pub.client.get_dataset(pub.dataset))
    sources, policy = capture_source(source_bucket, connection=connection)
    identity = publication_id(sources)
    current = pub.read_active("regular")
    if current and current["id"] == identity:
        return pub.checked(pub.pin("regular"))
    ready = pub.read_ready(identity)
    if ready is None:
        folder = pub.root / "contexts" / identity
        download_inputs(source_bucket, sources, policy, folder, cache=cache)
        release = prepare_regular(pub, source_bucket, sources, folder, sources["generation"], identity, current,
                                  staging_prefix=f"{pub.state.namespace}/prepared")
    else:
        release = ready["release"]
    latest, _ = capture_source(source_bucket, connection=connection)
    if latest != sources:
        raise PublicationError("El catálogo o sus reglas cambiaron durante la preparación. Se conserva la versión anterior.")
    pub.activate(release)
    pinned = pub.checked(pub.pin("regular"))
    if pinned["publication_id"] != identity:
        raise PublicationError("Otro cierre tomó el lugar de la publicación preparada.")
    return pinned


def prepare_current_wml(pub, source_bucket):
    """Publish the WML version already reconciled and accepted by the ingestion job."""
    if not pub.live:
        raise PublicationError("La publicación WML requiere su destino operativo.")
    pub.check_dataset(pub.client.get_dataset(pub.dataset))
    release_id = wml_settings()["config"].get("published_release_id")
    if not release_id:
        return None
    manifest = wml_source_manifest(source_bucket, release_id)
    if manifest is None:
        raise PublicationError("Falta el cierre publicado de WML.")
    generation = int(manifest.generation)
    identity = wml_publication_id(release_id, generation)
    current = pub.read_active("wml")
    if current and current["id"] == identity:
        return pub.checked(pub.pin("wml"))

    expected_files = (*WML_FILES, *WML_OPTIONAL_FILES, "wml_manifest.json")
    package = validate_release_manifest(
        json.loads(manifest.download_as_bytes(if_generation_match=generation)), expected_files,
    )
    prefix = wml_release_prefix(release_id) + "/files/"
    files = {name: package["files"][name] for name in expected_files}
    if (package["release_id"] != release_id or package["royalty_scope"] != "wml"
            or any(not re.fullmatch(re.escape(prefix) + r"[a-f0-9]{64}/" + re.escape(name), entry["object_name"])
                   for name, entry in files.items())):
        raise PublicationError("Los archivos publicados no corresponden a la versión de WML.")
    check = pub.client.query(
        f"SELECT status, manifest_generation FROM `{PROJECT}.{WML_DATASET}.analytics_releases` WHERE release_id=@release",
        job_config=bigquery.QueryJobConfig(labels=pub.labels, query_parameters=[
            bigquery.ScalarQueryParameter("release", "STRING", release_id),
        ]),
    ).result(timeout=60)
    if [(row.status, int(row.manifest_generation)) for row in check] != [("ready", generation)]:
        raise PublicationError("El cierre analítico de WML no concilia con el manifiesto vigente.")

    folder = pub.root / "contexts" / identity
    policy = wml_policy()
    download_inputs(source_bucket, {**package, "files": files}, policy, folder)
    ready = pub.read_ready(identity)
    if ready is None:
        from app.wml_job import immutable_upload

        def upload(path):
            target = f"{pub.state.namespace}/prepared/{identity}/{path.name}"
            return f"gs://{pub.state.bucket.name}/{immutable_upload(pub.state.bucket, target, path).name}"

        components = {kind: load_component(pub, source_bucket, package, folder, kind, name, upload=upload)[0]
                      for kind, name in WML_COMPONENTS.items()}
        roles = {f"marts/{name}": name for name in (*WML_OPTIONAL_FILES, "catalog_master.parquet",
                                                     "catalog_status.parquet", "wml_isrc_references.parquet")}
        roles.update({"publication/source_manifest.json": "release_manifest.json",
                      "policy/policy_snapshot.json": CONTEXT["policy/policy_snapshot.json"]})
        context = {"scope": "wml", "policy_version": policy["policy_version"], "artifacts": [
            {"role": role, "path": (folder / name).relative_to(pub.root).as_posix(),
             "sha256": file_sha(folder / name)}
            for role, name in sorted(roles.items())
        ]}
        release = {"scope": "wml", "source_release_id": release_id, "publication_id": identity,
                   "manifest_generation": generation, "sequence": current["sequence"] + 1 if current else 1,
                   "context": context, "context_id": digest(context), "components": components}
        ready = pub.prepare(release)
    else:
        release = ready["release"]

    reconciliation = {kind: reconcile_input(pub, release["components"][kind], folder / name,
                                           table=pub.component_table(release, kind))
                      for kind, name in WML_COMPONENTS.items()}
    latest = wml_source_manifest(source_bucket, release_id)
    if (wml_settings()["config"].get("published_release_id") != release_id
            or latest is None or int(latest.generation) != generation):
        raise PublicationError("El cierre de WML cambió durante la publicación.")
    pub.activate(release)
    print(json.dumps({"wml_reconciliation": reconciliation}), flush=True)
    return pub.checked(pub.pin("wml"))


def main():
    client = storage.Client(project=PROJECT)
    state = SharedReportState(client, LIVE_BUCKET, LIVE_NAMESPACE, live=True)
    if sys.argv[1:] == ["--verify-signer"]:
        from app.royalty_reports.delivery import create_signed_blob_download_url
        from .deployment import PILOT_CONFIG

        pointer, generation = state.current(PILOT_CONFIG)
        if pointer != {"mode": "parquet"} or not generation:
            raise PublicationError("La comprobación de firma requiere el piloto apagado.")
        blob = state.blob(PILOT_CONFIG, generation)
        url = create_signed_blob_download_url(client=client, blob=blob, filename="pilot-check.json", expiration_minutes=2,
                                               signer_service_account=os.environ["VPO_REPORT_SIGNER_SERVICE_ACCOUNT"])
        with requests.get(url, timeout=20) as response:
            if response.status_code != 200 or response.json() != pointer:
                raise PublicationError("El enlace firmado no recuperó el objeto autorizado.")
        print(json.dumps({"signed_download_verified": True, "generation": generation}), flush=True)
        return
    published = SharedReportPublications(bigquery.Client(project=PROJECT, location="US"),
                                        Path("/tmp/vpo-report/publisher"), LIVE_DATASET, state)
    source_bucket = client.bucket(SOURCE_BUCKET)
    failed = []
    with policy_connection() as lock:
        if not lock.execute("SELECT pg_try_advisory_lock(20261114, 2) AS acquired").fetchone()["acquired"]:
            print("Ya hay una publicación de reportes en preparación.", flush=True)
            return
        lock.commit()
        try:
            for scope, prepare in (("regular", prepare_current), ("wml", prepare_current_wml)):
                try:
                    release = prepare(published, source_bucket)
                except Exception:
                    failed.append(scope)
                    logging.exception("Falló la publicación de reportes del ámbito %s", scope)
                    continue
                if release is not None:
                    print(json.dumps({"scope": scope, "publication_id": release["publication_id"],
                                      "source_release_id": release["source_release_id"],
                                      "rows": {kind: item["source_binding"]["rows"]
                                               for kind, item in release["components"].items()}}), flush=True)
        finally:
            lock.execute("SELECT pg_advisory_unlock(20261114, 2)")
    if failed:
        raise PublicationError(f"Falló la publicación de {', '.join(failed)}.")


if __name__ == "__main__":
    main()
