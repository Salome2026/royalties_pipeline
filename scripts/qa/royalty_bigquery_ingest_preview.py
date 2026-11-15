"""Run a WML statement through the actual worker and the isolated report publisher."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from google.api_core.exceptions import Conflict, NotFound
from google.cloud import bigquery, storage
import polars as pl
import psycopg

from app.royalty_reports.bigquery_backend.publication_input import load_component
from app.royalty_reports.bigquery_backend.publication import LABELS, digest, file_sha, read_json, table_binding, write_json
from scripts.qa.royalty_bigquery_app_preview import (
    CONFIG, DATASET, INGEST_SCENARIO, PGDATA, PROJECT, REPO, RUNTIME,
    LocalCloudCredentials, cloud_publications, isolated_environment,
)


BUCKET = f"{PROJECT}-wml-ingest-test-20261111"
MARTS = {"raw": "standardized_raw_all_sources.parquet", "song": "song_level_all_sources.parquet"}


def isolated_storage():
    client = storage.Client(project=PROJECT, credentials=LocalCloudCredentials())
    bucket = client.get_bucket(BUCKET)
    if (bucket.location != "US" or bucket.labels != LABELS
            or bucket.iam_configuration.public_access_prevention != "enforced"
            or not bucket.iam_configuration.uniform_bucket_level_access_enabled
            or any(member in {"allUsers", "allAuthenticatedUsers"}
                   for binding in bucket.get_iam_policy().bindings for member in binding["members"])):
        raise RuntimeError("El bucket no tiene las protecciones de la prueba WML.")
    return client, bucket


def stage(source: Path):
    from app.wml_cloud import input_manifest, stage_inputs

    client, bucket = isolated_storage()
    folder = RUNTIME / "raw_arrival"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / source.name
    if not target.exists():
        shutil.copyfile(source, target)
    if file_sha(target) != file_sha(source):
        raise RuntimeError("La copia local no coincide con el TXT de origen.")
    pointer = stage_inputs(folder, client_factory=lambda: client, bucket_name=bucket.name)
    document = input_manifest(bucket, pointer)
    if len(document["files"]) != 1 or document["files"][0]["sha256"] != file_sha(target):
        raise RuntimeError("El manifiesto no contiene exactamente el statement de la prueba.")
    write_json(RUNTIME / "staged_statement.json", {"bucket": bucket.name, "pointer": pointer, "input": document})


def fetch_package(bucket, release_id, context):
    from app.royalty_scope import WML_FILES, WML_OPTIONAL_FILES, wml_release_prefix
    from scripts.lib.mart_release import validate_release_manifest

    prefix = wml_release_prefix(release_id)
    manifest = bucket.get_blob(f"{prefix}/release_manifest.json")
    if not manifest:
        raise RuntimeError("El Job WML no dejó un paquete publicado.")
    package = validate_release_manifest(
        json.loads(manifest.download_as_text(if_generation_match=manifest.generation)),
        (*WML_FILES, *WML_OPTIONAL_FILES, "wml_manifest.json"),
    )
    if package["release_id"] != release_id or package["royalty_scope"] != "wml":
        raise RuntimeError("El paquete publicado corresponde a otro ámbito o versión.")
    context.mkdir(parents=True, exist_ok=True)
    for name, entry in package["files"].items():
        if Path(name).name != name or not entry["object_name"].startswith(f"{prefix}/files/"):
            raise RuntimeError("El manifiesto contiene un archivo ajeno a la versión.")
        generation = int(entry["generation"])
        blob = bucket.get_blob(entry["object_name"], generation=generation)
        if not blob or blob.size != entry["size_bytes"]:
            raise RuntimeError(f"Falta el archivo fijado de la versión: {name}")
        expected = (blob.metadata or {}).get("sha256")
        path = context / name
        if not path.exists():
            pending = path.with_suffix(".pending")
            blob.download_to_filename(pending, if_generation_match=generation, checksum="auto")
            if file_sha(pending) != expected:
                raise RuntimeError(f"El contenido del paquete cambió: {name}")
            pending.replace(path)
        if not expected or file_sha(path) != expected:
            raise RuntimeError(f"El archivo local no coincide con su versión: {name}")
    write_json(context / "release_manifest.json", package)
    return package, int(manifest.generation)


def prepare_handoff(publications, bucket, release_id, pointer, *, analytics_dataset=None, activate=False,
                    before_activate=None):
    from app.royalty_scope import wml_policy

    client = publications.client
    context_folder = publications.root / "contexts" / release_id
    package, generation = fetch_package(bucket, release_id, context_folder)
    config = bigquery.QueryJobConfig(labels=LABELS, query_parameters=[
        bigquery.ScalarQueryParameter("release", "STRING", release_id),
    ])
    analytics_dataset = analytics_dataset or publications.dataset
    rows = list(client.query(
        f"SELECT status, manifest_generation FROM `{analytics_dataset}.analytics_releases` WHERE release_id=@release",
        job_config=config,
    ).result())
    if len(rows) != 1 or rows[0].status != "ready" or int(rows[0].manifest_generation) != generation:
        raise RuntimeError("La publicación analítica de BigQuery todavía no está conciliada.")
    summary = read_json(context_folder / "wml_manifest.json")
    if summary["fingerprint"] != pointer["fingerprint"]:
        raise RuntimeError("La ingesta publicó una entrada diferente al statement fijado.")
    components, jobs = {}, {}
    for kind, name in MARTS.items():
        components[kind], jobs[kind] = load_component(publications, bucket, package, context_folder, kind, name)
    roles = {f"marts/{name}": name for name in package["files"]}
    roles["publication/source_manifest.json"] = "release_manifest.json"
    context = {"scope": "wml", "policy_version": wml_policy()["policy_version"],
               "artifacts": [{"role": role, "path": (context_folder / name).relative_to(publications.root).as_posix(),
                              "sha256": file_sha(context_folder / name)} for role, name in sorted(roles.items())]}
    publication_id = release_id.replace("-", "_")
    ready = publications.read_ready(publication_id)
    active = publications.read_active("wml")
    sequence = ready["release"]["sequence"] if ready else (active["sequence"] + 1 if active else 1)
    release = {"scope": "wml", "source_release_id": release_id, "publication_id": publication_id,
               "manifest_generation": generation, "sequence": sequence, "context": context,
               "context_id": digest(context), "components": components}
    publications.validate(release)
    if activate:
        if before_activate is not None:
            before_activate(release)
        publications.publish(release)
    else:
        path = publications.root / "incoming" / f"{release['publication_id']}.json"
        if path.exists() and read_json(path) != release:
            raise RuntimeError("Ya existe otra publicación del mismo statement.")
        if not path.exists():
            write_json(path, release)
    return {"release_id": release_id, "publication_id": release["publication_id"],
            "manifest_generation": generation, "sequence": sequence, "analytics_reconciled": True, "load_jobs": jobs,
            "native_rows": summary["rows"], "amount_usd": summary["amount_usd"],
            "reported_royalty_usd": summary["warner_royalty_usd"], "input_fingerprint": summary["fingerprint"]}


def process():
    config = read_json(CONFIG)
    isolated_environment(config)
    with psycopg.connect(host="127.0.0.1", port=config["pg_port"], user="report_preview",
                         password=config["pg_password"], dbname="postgres") as db:
        if Path(db.execute("SHOW data_directory").fetchone()[0]).resolve() != PGDATA.resolve():
            raise RuntimeError("La base no pertenece a la prueba de ingesta.")
    from app import wml_job
    from app.royalty_workspace_store import settings
    from app.wml_cloud import INPUT_PREFIX, launch_processing

    client, bucket = isolated_storage()
    publications = cloud_publications()
    wml_job.require_isolated_destination(bucket, publications.client, PROJECT, DATASET)
    pointer = read_json(RUNTIME / "staged_statement.json")["pointer"]
    if json.loads(bucket.blob(f"{INPUT_PREFIX}/latest.json").download_as_text()) != pointer:
        raise RuntimeError("Cambió el statement seleccionado en la entrada.")
    before = settings()["config"].get("published_release_id")

    def run_local(token):
        wml_job.main(token=token, bucket=bucket, bigquery_client=publications.client,
                     dataset=DATASET, isolated_test=True)
        return "local/statement-ingest/" + pointer["fingerprint"][:24]

    result = launch_processing(client_factory=lambda: client, bucket_name=bucket.name,
                               actor="prueba-ingesta-wml", dispatch=run_local)
    state = settings()["config"]
    if state["processing_status"] != "completed" or state["published_release_id"] != result["release_id"]:
        raise RuntimeError("El Job de ingesta no completó la publicación conciliada.")
    receipt = prepare_handoff(publications, bucket, result["release_id"], pointer)
    write_json(RUNTIME / "ingest_to_bigquery.json", receipt | {
        "previous_release_id": before, "processing_status": state["processing_status"],
        "dispatch": "local_real_wml_worker", "launcher_reused": result["reused"],
    })
    print("Statement conciliado. Entrega disponible para el publicador de reportes.", flush=True)


def main():
    if not INGEST_SCENARIO:
        raise RuntimeError("Este comando requiere el escenario aislado de ingesta.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path)
    args = parser.parse_args()
    if args.stage:
        stage(args.stage)
    else:
        from app.operational_db import close_operational_db_pool
        try:
            process()
        finally:
            close_operational_db_pool()


if __name__ == "__main__":
    main()
