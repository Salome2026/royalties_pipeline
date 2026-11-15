"""Cloud Run entry points for the private royalty report test deployment."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from google.cloud import bigquery, storage

from app.royalty_reports.bigquery_backend.publication import PROJECT, digest
from app.royalty_reports.bigquery_backend.shared_state import SharedReportPublications, SharedReportState


API = "vpo-report-preview-api-20261111"
WORKER = "vpo-report-preview-worker-20261111"
PUBLISHER = "vpo-report-preview-publisher-20261111"
WML_INGEST = "vpo-report-preview-wml-20261112"
FUGA_INGEST = "vpo-report-preview-fuga-20261113"
WML_INGEST_BUCKET = f"{PROJECT}-wml-ingest-test-20261112"
WML_INGEST_DATASET = "report_app_test_ingest_20261112"
SQL = f"{PROJECT}:us-central1:vpo-report-preview-20261111"
DATASET = "report_app_test_cloud_20261111"
BUCKET = "vpo-corp-royalties-report-ops-test-20261112"
NAMESPACE = "cloud_preview"
ROOT = Path("/tmp/royalty-cloud-preview")
MAX_RETRIES = 1


def check_environment(role: str) -> None:
    service, job = os.getenv("K_SERVICE"), os.getenv("CLOUD_RUN_JOB")
    expected = {"api": service == API, "worker": job == WORKER, "publish": job == PUBLISHER,
                "regular-close": job == PUBLISHER,
                "wml-ingest": job == WML_INGEST,
                "fuga-cut": job == FUGA_INGEST, "fuga-arrival": job == FUGA_INGEST,
                "regular-fuga-cut": job == FUGA_INGEST, "regular-fuga-inbox": job == FUGA_INGEST}
    if (os.getenv("VPO_REPORT_CLOUD_PREVIEW") != "1" or not expected[role]
            or os.getenv("GCS_BUCKET") != BUCKET or os.getenv("VPO_BIGQUERY_DATASET") != DATASET):
        raise RuntimeError("El proceso debe pertenecer al despliegue aislado del reporte.")
    if role in {"api", "worker", "wml-ingest", "regular-close"} and (
        os.getenv("VPO_OPERATIONAL_DB_DRIVER") != "postgres"
        or os.getenv("VPO_POSTGRES_CONNECT_MODE") != "cloudsql_socket"
        or os.getenv("VPO_CLOUDSQL_CONNECTION_NAME") != SQL
        or os.getenv("VPO_OPERATIONAL_DB_NAME") != "report_preview"
    ):
        raise RuntimeError("La conexión del reporte no pertenece a la base aislada.")


def publications(role: str):
    check_environment(role)
    state = SharedReportState(storage.Client(project=PROJECT), BUCKET, NAMESPACE)
    return SharedReportPublications(bigquery.Client(project=PROJECT, location="US"), ROOT, DATASET, state)


def serve() -> None:
    pub = publications("api")
    from starlette.responses import JSONResponse
    import uvicorn
    from app import vpo_corp_api as api
    from app.royalty_reports.bigquery_backend.runtime import BigQueryReportBackend
    from app.royalty_reports.launcher import CloudRunReportJobLauncher
    from app.royalty_reports.reconciliation import reconcile_report_job_if_stale

    launcher = CloudRunReportJobLauncher.from_environment()
    if (launcher.project, launcher.location, launcher.job_name) != (PROJECT, "us-central1", WORKER):
        raise RuntimeError("El destino del pedido no es el worker aislado.")
    api.GCS_BUCKET = BUCKET
    api.GCS_PREFIX = "regular_fuga_legacy"
    api.gcs_client = lambda: storage.Client(project=PROJECT)
    backend = BigQueryReportBackend(
        pub, shared_state=pub.state, watch_inbox=False, dispatch_job=launcher.run,
        reconcile_job=reconcile_report_job_if_stale, live_contracts=True,
    )
    api.app.state.royalty_report_backend = backend
    api.app.state.royalty_report_intake = lambda: (
        pub.state.read("routing/report_intake.json") or {"engine": "bigquery"}
    )["engine"]

    def legacy_manifest(client, bucket_name, prefix, **options):
        from app.royalty_reports.manifests import build_gcs_input_manifest

        if bucket_name != BUCKET or prefix != "regular_fuga_legacy":
            raise RuntimeError("La reversión de prueba solo admite el catálogo habitual aislado.")
        return build_gcs_input_manifest(client=client, bucket_name=bucket_name, prefix=prefix, **options)

    api.build_gcs_input_manifest = legacy_manifest

    async def restricted(scope, receive, send):
        import re

        if scope["type"] == "http":
            path = scope["path"]
            if not (path in {"/auth/login", "/auth/session", "/me/permissions", "/wml/workspace", "/openapi.json"}
                    or re.fullmatch(r"/reports/jobs(?:/\d+(?:/download)?)?", path)
                    or path in {"/reports/royalty/options", "/reports/royalty/detail-count",
                                "/reports/royalty/contract-options", "/reports/royalty/distribution-contract-options"}):
                await JSONResponse({"detail": "Ruta fuera de la prueba del reporte."}, status_code=404)(scope, receive, send)
                return
        await api.app(scope, receive, send)

    uvicorn.run(restricted, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


def worker() -> None:
    pub = publications("worker")
    from app.operational_db import close_operational_db_pool
    from app.royalty_reports import job_main
    from app.royalty_reports.bigquery_backend.runtime import BigQueryReportBackend

    backend = BigQueryReportBackend(pub, shared_state=pub.state, export_bucket=BUCKET, watch_inbox=False)

    def build(request, job):
        control = pub.state.read(f"retry_controls/{request.job_id}.json")
        result = backend.build(request, job)
        if control is not None:
            attempt = int(os.environ["CLOUD_RUN_TASK_ATTEMPT"])
            pin = job["input_manifest"]["report_publication"]
            assert result.output_uri and control["pinned_publication"] == pin["publication_id"]
            pub.state.write(f"retry_receipts/{request.job_id}-{attempt}.json", {
                "execution": os.environ["CLOUD_RUN_EXECUTION"], "attempt": attempt,
                "pin": pin, "output_uri": result.output_uri, "sha256": result.result_sha256,
                "active_when_built": pub.pin(pin["scope"])["publication_id"],
            }, 0)
            if attempt == 0:
                for _ in range(100):
                    if pub.pin(pin["scope"])["publication_id"] == control["next_publication"]:
                        print("Interrupción de prueba después de guardar el resultado y antes de cerrar el pedido.", flush=True)
                        os._exit(86)
                    time.sleep(3)
                raise RuntimeError("No llegó el cambio de publicación de la prueba de reintento.")
        return result

    try:
        job_main.main(pinned_builder=build, max_cloud_retries=MAX_RETRIES)
    finally:
        close_operational_db_pool()


def publish() -> None:
    pub = publications("publish")
    name = os.environ["VPO_REPORT_PREVIEW_PUBLICATION"]
    if name not in {"regular_e", "regular_connected_f"}:
        raise ValueError("La entrega no pertenece al catálogo de pruebas.")
    release = pub.state.read(f"incoming/{name}.json")
    if release is None:
        raise RuntimeError("Todavía no existe la entrega de prueba.")
    ready = pub.publish(release)
    print(f"Publicación {release['publication_id']} lista, {digest(release)}: "
          + str({kind: item['binding']['rows'] for kind, item in ready['tables'].items()}), flush=True)


def publish_regular_close() -> None:
    from app.operational_db import close_operational_db_pool
    from scripts.qa.royalty_bigquery_regular_close import process_close

    try:
        process_close(publications("regular-close"))
    finally:
        close_operational_db_pool()


def ingest_wml() -> None:
    from google.api_core.exceptions import PreconditionFailed
    from app.operational_db import close_operational_db_pool
    from app.royalty_workspace_store import settings, update_settings
    from app.wml_cloud import INPUT_PREFIX, input_manifest, launch_processing
    from app.wml_job import main as run_ingest, require_isolated_destination
    from scripts.qa.royalty_bigquery_ingest_preview import prepare_handoff

    pub = publications("wml-ingest")
    storage_client = storage.Client(project=PROJECT)
    bucket = storage_client.get_bucket(WML_INGEST_BUCKET)
    require_isolated_destination(bucket, pub.client, PROJECT, WML_INGEST_DATASET)
    try:
        arrival = bucket.get_blob(f"{INPUT_PREFIX}/latest.json")
        if arrival is None:
            print("WML: todavía no hay una entrada anunciada.", flush=True)
            return
        pointer = json.loads(arrival.download_as_bytes(if_generation_match=arrival.generation))
        source = input_manifest(bucket, pointer)
        release_id = "wml-" + source["fingerprint"][:24]
        publication_id = release_id.replace("-", "_")
        current = pub.read_active("wml")
        state = settings()
        key = f"wml_arrivals/{source['fingerprint']}.json"
        if (current and current["id"] == publication_id
                and state["config"].get("published_release_id") == release_id
                and state["config"].get("processing_status") == "completed" and state["enabled"]
                and pub.state.read(key) is not None):
            print(f"WML: {release_id} ya está disponible para reportes.", flush=True)
            return

        def before_activate(release):
            latest = bucket.get_blob(arrival.name)
            if latest is None or latest.generation != arrival.generation:
                raise RuntimeError("Llegó otro manifiesto WML antes de activar el reporte.")
            if os.getenv("VPO_REPORT_PREVIEW_INTERRUPT_WML") != source["fingerprint"]:
                return
            attempt = int(os.environ["CLOUD_RUN_TASK_ATTEMPT"])
            execution = os.environ["CLOUD_RUN_EXECUTION"]
            pub.state.write(f"wml_retry_receipts/{execution}-{attempt}.json", {
                "attempt": attempt, "release_id": release["source_release_id"],
                "sequence": release["sequence"], "active_before": pub.read_active("wml"),
                "workspace_before": settings()["config"].get("published_release_id"),
                "report_publication_prepared": True,
            }, 0)
            if attempt == 0:
                raise RuntimeError("Interrupción de prueba antes de activar la publicación WML.")

        receipt = None

        def publish_for_reports(selected_release_id, selected_pointer):
            nonlocal receipt
            receipt = prepare_handoff(pub, bucket, selected_release_id, selected_pointer,
                                      analytics_dataset=f"{PROJECT}.{WML_INGEST_DATASET}", activate=True,
                                      before_activate=before_activate)
            if pub.pin("wml")["publication_id"] != publication_id:
                raise RuntimeError("El statement WML quedó detrás de una publicación más reciente.")

        def dispatch(token):
            run_ingest(token=token, bucket=bucket, bigquery_client=pub.client,
                       dataset=WML_INGEST_DATASET, isolated_test=True, before_publish=publish_for_reports)
            return os.environ["CLOUD_RUN_EXECUTION"]

        result = launch_processing(client_factory=lambda: storage_client, bucket_name=bucket.name,
                                   actor="prueba-cloud-wml", dispatch=dispatch, input_pointer=pointer)
        state = settings()
        if (result["release_id"] != release_id or state["config"].get("published_release_id") != release_id
                or state["config"].get("processing_status") != "completed"):
            raise RuntimeError("La ingesta aún no terminó para el statement anunciado.")
        if receipt is None:
            # The workspace can have completed before this deployment or before writing the receipt.
            publish_for_reports(release_id, pointer)
        if not state["enabled"]:
            update_settings(enabled=True, actor="prueba-cloud-wml", expected_version=state["version"])
        try:
            pub.state.write(key, {
                **receipt, "execution": os.environ["CLOUD_RUN_EXECUTION"],
                "attempt": int(os.environ["CLOUD_RUN_TASK_ATTEMPT"]),
                "arrival_generation": int(arrival.generation), "ingest_reused": result["reused"],
                "input": source["files"], "pin": pub.pin("wml"),
            }, 0)
        except PreconditionFailed:
            pass
        print(f"WML: {release_id} publicado para reportes.", flush=True)
    finally:
        close_operational_db_pool()


if __name__ == "__main__":
    {"api": serve, "worker": worker, "publish": publish, "wml-ingest": ingest_wml,
     "regular-close": publish_regular_close}[sys.argv[1]]()
