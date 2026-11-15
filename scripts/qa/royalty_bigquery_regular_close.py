"""Connect the ordinary catalog closure to reports in the private Cloud copy."""

from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import os


from app.royalty_reports.bigquery_backend.publication import LABELS, PublicationError, write_json
from scripts.lib.mart_release import manifest_object_name, release_object_name, validate_release_manifest
from app.royalty_reports.bigquery_backend.publication_input import CONTEXT, MARTS, prepare_regular


PREFIX = "regular_catalog_closed"
REQUIRED = (*MARTS.values(), *CONTEXT.values(), "native_identity_proofs.json", "catalog_participant_changes.json",
            "statement_summary_all_sources.parquet", "digital_income_statement_summary.parquet")


def close_handoff(bucket, prefix, uploads, publish_with_review, connection_factory, policy, load_catalog_status):
    from scripts.lib.mart_release import publish_mart_release
    from scripts.qa.royalty_bigquery_cloud_preview import BUCKET

    if bucket.name != BUCKET or prefix != PREFIX:
        raise ValueError("El cierre para reportes exige el bucket y prefijo de la copia.")
    bucket.reload()
    if (not bucket.iam_configuration.uniform_bucket_level_access_enabled
            or bucket.iam_configuration.public_access_prevention != "enforced"
            or any(bucket.labels.get(k) != v for k, v in LABELS.items())):
        raise ValueError("El destino no pertenece a la copia aislada.")
    with connection_factory() as db:
        if not hasattr(db, "info") or db.info.dbname != "report_preview":
            raise ValueError("El cierre habitual requiere la base operativa de la copia.")
    with TemporaryDirectory(prefix="report-close-") as temp:
        item = Path(temp) / "policy_snapshot.json"
        status = Path(temp) / "catalog_status.parquet"
        write_json(item, policy)
        load_catalog_status().write_parquet(status)
        return publish_with_review(bucket, prefix, [*uploads, (item.name, item), (status.name, status)],
                                   publisher=publish_mart_release, connection_factory=connection_factory)


def read_package(bucket, pointer, generation, folder):
    import base64

    package = validate_release_manifest(json.loads(pointer.download_as_bytes(if_generation_match=generation)), REQUIRED)
    release_id = package["release_id"]
    folder.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED:
        item = package["files"][name]
        if item["object_name"] != release_object_name(PREFIX, release_id, name):
            raise PublicationError("Un archivo del cierre pertenece a otra publicación.")
        blob = bucket.blob(item["object_name"], generation=int(item["generation"]))
        path = folder / name
        blob.download_to_filename(path, if_generation_match=blob.generation, checksum="crc32c")
        with path.open("rb") as stream:
            md5 = base64.b64encode(hashlib.file_digest(stream, "md5").digest()).decode("ascii")
        if path.stat().st_size != int(item["size_bytes"]) or md5 != item["md5_hash"]:
            raise PublicationError(f"El paquete cambió durante la lectura: {name}.")
    write_json(folder / "release_manifest.json", {"bucket": bucket.name, "generation": generation, "package": package})
    return package


def prepare_close(pub, pointer, generation, identity, current):
    folder = pub.root / "contexts" / identity
    package = read_package(pub.state.bucket, pointer, generation, folder)
    return prepare_regular(pub, pub.state.bucket, package, folder, generation, identity, current,
                           staging_prefix=f"{PREFIX}/prepared")


def process_close(pub):
    from app.catalog_participant_review import review_published_participants
    from app.operational_db import operational_connect

    bucket = pub.state.bucket
    dataset = pub.client.get_dataset(pub.dataset)
    if dataset.location != "US" or any(dataset.labels.get(key) != value for key, value in LABELS.items()):
        raise PublicationError("BigQuery no corresponde a la copia aislada.")
    key = manifest_object_name(PREFIX)
    pointer = bucket.get_blob(key)
    if pointer is None:
        print("No hay catálogo habitual cerrado en la copia.", flush=True)
        return
    generation = int(pointer.generation)
    identity = f"regular_close_{generation}"
    current = pub.read_active("regular")
    if current and current["id"] == identity:
        print("El cierre habitual ya está publicado para reportes.", flush=True)
        return
    # Scheduler ticks may overlap a full catalog load. Serialize preparation,
    # review and activation of the active regular publication in the private DB.
    with operational_connect() as db:
        if db.execute("SELECT current_database() AS name").fetchone()["name"] != "report_preview":
            raise RuntimeError("La revisión contractual requiere la base de la copia.")
        db.execute("SET LOCAL idle_in_transaction_session_timeout = 0")
        lock = db.execute("SELECT pg_try_advisory_xact_lock(20261114, 1) AS locked").fetchone()["locked"]
        if not lock:
            print("Ya hay un cierre habitual en preparación.", flush=True)
            return
        activate_close(pub, pointer, generation, identity, key, review_published_participants)


def activate_close(pub, pointer, generation, identity, key, review_published_participants):
    bucket = pub.state.bucket
    if int(bucket.get_blob(key).generation) != generation:
        return
    current = pub.read_active("regular")
    if current and current["id"] == identity:
        return
    ready = pub.read_ready(identity)
    release = ready["release"] if ready is not None else prepare_close(pub, pointer, generation, identity, current)
    if int(bucket.get_blob(key).generation) != generation:
        print("Llegó un cierre posterior. Se conserva la versión activa.", flush=True)
        return
    review = review_published_participants(bucket.client, {"bucket": bucket.name, "prefix": PREFIX,
                                                           "release_id": release["source_release_id"]})
    if int(bucket.get_blob(key).generation) != generation:
        print("El catálogo cambió durante la revisión. Se conserva la versión activa.", flush=True)
        return
    pub.activate(release)
    pin = pub.pin("regular")
    if pin["publication_id"] != identity:
        raise PublicationError("Otro cierre tomó la versión de reportes durante la activación.")
    print(json.dumps({"publication": pin, "manifest_generation": generation,
                      "review": review, "execution": os.environ.get("CLOUD_RUN_EXECUTION")}), flush=True)
