"""Durable catalog-driven dashboard refreshes, executed by a dedicated Cloud Run Job."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.api_core.exceptions import NotFound
from google.cloud import storage


def enabled() -> bool:
    return bool(os.environ.get("VPO_CATALOG_REFRESH_JOB", "").strip())


def object_name(filename: str) -> str:
    prefix = os.environ.get("GCS_PREFIX", "marts").strip("/")
    return f"{prefix}/{filename}" if prefix else filename


def status_object() -> str:
    return os.environ.get("VPO_CATALOG_STATUS_GCS_OBJECT", "").strip() or object_name("catalog_status.parquet")


def bucket(client=None):
    return (client or storage.Client()).bucket(os.environ["GCS_BUCKET"])


def read_json(name: str, client=None) -> dict:
    blob = bucket(client).blob(object_name(name))
    try:
        blob.reload()
        return json.loads(blob.download_as_bytes(if_generation_match=int(blob.generation)))
    except NotFound:
        return {}


def catalog_generation(client=None) -> str:
    blob = bucket(client).blob(status_object())
    try:
        blob.reload()
    except NotFound:
        return "0"
    return str(blob.generation)


def snapshot_id(release_id: str, generation: str) -> str:
    digest = hashlib.sha256(f"{release_id}:{generation}".encode()).hexdigest()[:24]
    return f"catalog-{digest}"


def validation_sql(table: str, refresh_id: str) -> str:
    return f"SELECT COUNT(*) AS row_count, COALESCE(SUM(amount_usd),0) AS amount FROM `{table}` WHERE release_id = '{refresh_id}'"


def dashboard_state(client=None) -> dict:
    generation = catalog_generation(client)
    ready = read_json("catalog_dashboard_ready.json", client)
    return {"catalog_generation": generation, "ready": ready}


def launch_refresh() -> str:
    project = os.environ["VPO_REPORT_JOB_PROJECT"]
    location = os.environ["VPO_REPORT_JOB_LOCATION"]
    name = os.environ["VPO_CATALOG_REFRESH_JOB"]
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    response = AuthorizedSession(credentials).post(
        f"https://run.googleapis.com/v2/projects/{project}/locations/{location}/jobs/{name}:run",
        json={}, timeout=20,
    )
    response.raise_for_status()
    return response.json()["name"]


def request_refresh() -> dict:
    if not enabled():
        return {"status": "disabled"}
    try:
        operation = launch_refresh()
        return {"status": "queued", "operation": operation}
    except Exception as exc:
        # The GCS notification remains in Pub/Sub until launch is acknowledged.
        print(json.dumps({"event": "catalog_refresh_launch_failed", "error": str(exc)}), flush=True)
        return {"status": "pending_retry"}


def receive_change_event(payload: dict, authorization: str | None) -> dict:
    from fastapi import HTTPException
    from google.oauth2 import id_token
    from google.auth.transport.requests import Request

    audience = os.environ.get("VPO_CATALOG_EVENT_AUDIENCE", "")
    email = os.environ.get("VPO_CATALOG_EVENT_SERVICE_ACCOUNT", "")
    if not audience or not email:
        raise HTTPException(status_code=503, detail="Notificaciones de catálogo no configuradas.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Notificacion no autenticada.")
    try:
        claims = id_token.verify_oauth2_token(authorization[7:], Request(), audience=audience)
        if claims.get("email") != email or claims.get("email_verified") is not True:
            raise ValueError("Identidad incorrecta.")
    except (ValueError, google.auth.exceptions.GoogleAuthError) as exc:
        raise HTTPException(status_code=401, detail="Identidad de notificacion invalida.") from exc
    message = payload.get("message") or {}
    attributes = message.get("attributes") or {}
    if attributes.get("eventType") != "OBJECT_FINALIZE" or attributes.get("bucketId") != os.environ["GCS_BUCKET"]:
        return {"ignored": True}
    if attributes.get("objectId") not in {status_object(), object_name("release_manifest.json")}:
        return {"ignored": True}
    try:
        operation = launch_refresh()
    except Exception as exc:
        # Non-2xx keeps the message in Pub/Sub for durable automatic redelivery.
        raise HTTPException(status_code=503, detail="Se reintentara la actualizacion del catalogo.") from exc
    return {"queued": True, "operation": operation}


def select_dashboard_release(base_release: str, state: dict) -> tuple[str, str]:
    ready = state.get("ready") or {}
    if ready.get("base_release_id") == base_release and str(ready.get("catalog_generation")) == str(state["catalog_generation"]):
        return ready["dashboard_release_id"], "ready"
    # Keep a complete, validated version visible until its successor is ready.
    if ready.get("base_release_id") == base_release:
        return ready["dashboard_release_id"], "pending"
    return base_release, "pending"


def fallback_summary(default_path):
    """The parquet fallback must use the same validated catalog snapshot as BQ."""
    if not enabled():
        return default_path, "ready"
    client = storage.Client()
    state = dashboard_state(client)
    release = read_json("release_manifest.json", client).get("release_id")
    selected, status = select_dashboard_release(release, state)
    if selected == release:
        return default_path, status
    ready = state["ready"]
    target = default_path.with_name(f"{selected}.parquet")
    if not target.exists():
        temporary = target.with_suffix(".tmp")
        bucket(client).blob(ready["summary_object"], generation=int(ready["summary_generation"])).download_to_filename(str(temporary))
        temporary.replace(target)
    return target, status


def pin_report_dashboard(manifest: dict) -> None:
    if not enabled():
        return
    state = dashboard_state()
    generation = str(manifest["objects"]["catalog_status.parquet"]["generation"])
    selected, status = select_dashboard_release(manifest["release_id"], {**state, "catalog_generation": generation})
    if status != "ready":
        raise RuntimeError("El catálogo se está actualizando. Volvé a generar el PDF contractual cuando termine.")
    manifest["catalog_dashboard"] = {"release_id": selected, "catalog_generation": generation}


def run_refresh() -> None:
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from google.cloud import bigquery
    from app.operational_db import operational_connect
    from app.royalty_reports.manifests import build_gcs_input_manifest
    from scripts.load_bigquery_release import build_dashboard

    client = storage.Client()
    bq = bigquery.Client(project=os.environ.get("VPO_BIGQUERY_PROJECT", "vpo-corp-royalties"))
    dataset = os.environ.get("VPO_BIGQUERY_DATASET", "royalties_analytics")
    project = bq.project
    location = os.environ.get("VPO_BIGQUERY_LOCATION", "US")
    table = f"{project}.{dataset}.royalty_catalog_dashboard"
    with operational_connect() as conn:
        # One worker at a time; the lock is released even if the container dies.
        locked = conn.execute("SELECT pg_try_advisory_lock(721064221) AS locked").fetchone()["locked"]
        if not locked:
            return
        conn.commit()
        try:
            for _ in range(30):
                state = dashboard_state(client)
                release = next(iter(bq.query(f"SELECT release_id FROM `{project}.{dataset}.current_release`", location=location).result()))["release_id"]
                manifest = build_gcs_input_manifest(
                    client=client, bucket_name=os.environ["GCS_BUCKET"], prefix=os.environ.get("GCS_PREFIX", "marts"),
                    filenames=["standardized_raw_all_sources.parquet", "catalog_master.parquet"],
                )
                if manifest["release_id"] != release:
                    time.sleep(30)
                    continue
                from app.catalog_participant_review import review_published_participants
                review_published_participants(client, manifest)
                from app.master_contract_review import review_published_release
                review_published_release(client, manifest)
                _, status = select_dashboard_release(release, state)
                if status == "ready":
                    # An event may have arrived while this worker held the lock.
                    # Its other execution exits; this worker must pick up the latest release.
                    latest = read_json("release_manifest.json", client).get("release_id")
                    if latest != release or catalog_generation(client) != state["catalog_generation"]:
                        continue
                    return
                generation = state["catalog_generation"]
                refresh_id = snapshot_id(release, generation)
                with TemporaryDirectory(prefix="catalog-refresh-") as directory:
                    root = Path(directory)
                    for filename, item in manifest["objects"].items():
                        client.bucket(manifest["bucket"]).blob(item["object"], generation=int(item["generation"])).download_to_filename(str(root / filename))
                    status_path = root / "catalog_status.parquet"
                    if generation != "0":
                        bucket(client).blob(status_object(), generation=int(generation)).download_to_filename(str(status_path))
                    os.environ["VPO_CATALOG_STATUS_PATH"] = str(status_path)
                    os.environ["VPO_CATALOG_MASTER_PATH"] = str(root / "catalog_master.parquet")
                    from app import vpo_corp_api as api
                    # Read the complete published source, including previously excluded tracks.
                    summary = api.build_royalties_dashboard_summary_mart(
                        root / "standardized_raw_all_sources.parquet", refresh_cache=True,
                        output_path=root / "dashboard.parquet",
                    )
                    prepared = root / "rankings.parquet"
                    build_dashboard(summary, prepared, refresh_id)
                    import polars as pl
                    expected = pl.scan_parquet(prepared).select(pl.len().alias("rows"), pl.col("amount_usd").sum().alias("amount")).collect().row(0)
                    stage = f"{project}.catalog_refresh_work._{refresh_id.replace('-', '_')}"
                    try:
                        with prepared.open("rb") as stream:
                            bq.load_table_from_file(stream, stage, location=location, job_config=bigquery.LoadJobConfig(source_format="PARQUET", write_disposition="WRITE_TRUNCATE")).result()
                        columns = ", ".join(f"`{field.name}`" for field in bq.get_table(stage).schema)
                        bq.query(f"""BEGIN TRANSACTION;
DELETE FROM `{table}` WHERE release_id = '{refresh_id}';
INSERT INTO `{table}` ({columns}) SELECT {columns} FROM `{stage}`;
COMMIT TRANSACTION;""", location=location).result()
                    finally:
                        bq.delete_table(stage, not_found_ok=True)
                    checked = next(iter(bq.query(validation_sql(table, refresh_id), location=location).result()))
                    if int(checked["row_count"]) != expected[0] or abs(float(checked["amount"]) - float(expected[1] or 0)) > .01:
                        raise RuntimeError("La actualizacion del catalogo no concilia con BigQuery.")
                    # A change made during this build is processed on the next iteration.
                    if catalog_generation(client) != generation:
                        continue
                    current = next(iter(bq.query(f"SELECT release_id FROM `{project}.{dataset}.current_release`", location=location).result()))["release_id"]
                    if current != release:
                        continue
                    target = bucket(client).blob(object_name(f"catalog_refresh/{refresh_id}/dashboard.parquet"))
                    target.upload_from_filename(str(summary))
                    ready = {"base_release_id": release, "catalog_generation": generation,
                             "dashboard_release_id": refresh_id, "summary_object": target.name,
                             "summary_generation": str(target.generation), "rows": expected[0],
                             "updated_at": datetime.now(timezone.utc).isoformat()}
                    bucket(client).blob(object_name("catalog_dashboard_ready.json")).upload_from_string(json.dumps(ready), content_type="application/json")
                    print(json.dumps({"event": "catalog_refresh_completed", **ready}), flush=True)
                    if catalog_generation(client) == generation:
                        return
            raise RuntimeError("El catalogo sigue cambiando; la conciliacion programada retomara la ultima version.")
        finally:
            conn.execute("SELECT pg_advisory_unlock(721064221)")
            conn.commit()


if __name__ == "__main__":
    run_refresh()
