"""Run the actual application on loopback with an isolated database and BigQuery."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
from threading import Event

import psycopg
from google.auth.credentials import Credentials
from google.cloud import bigquery, storage
from google.api_core.exceptions import Conflict

from app.royalty_reports.bigquery_backend.publication import (
    ARCHIVE_DATASET, LABELS, PROJECT, ReportPublications, digest, file_sha, read_json, table_binding,
    watch_publications, write_json,
)
from app.royalty_reports.bigquery_backend.shared_state import SharedReportPublications, SharedReportState


REPO = Path(__file__).resolve().parents[2]
SCENARIO = os.environ.get("ROYALTY_PREVIEW_SCENARIO")
INGEST_SCENARIO = SCENARIO == "ingest"
FUGA_SCENARIO = SCENARIO == "fuga"
OPERATIONS_SCENARIO = SCENARIO == "operational"
CLOUD_SCENARIO = SCENARIO == "cloud"
DEPENDENCIES = REPO / "tmp" / "app_integration"
RUNTIME = {
    "ingest": REPO / "tmp" / "statement_ingest_preview",
    "fuga": REPO / "tmp" / "fuga_ingest_preview",
    "operational": REPO / "tmp" / "report_operational_preview",
    "cloud": REPO / "tmp" / "report_cloud_preview",
}.get(SCENARIO, DEPENDENCIES)
PGDATA = RUNTIME / "postgres"
BIN = DEPENDENCIES / "node_modules" / "@embedded-postgres" / "windows-x64" / "native" / "bin"
CONFIG = RUNTIME / "local_config.json"
EVIDENCE = Path("C:/royalties_pipeline/tmp/bq_validation_control_20261105")
DATASET = {
    "ingest": "report_app_test_ingest_20261111",
    "fuga": "report_app_test_fuga_20261111",
    "operational": "report_app_test_ops_20261111",
}.get(SCENARIO, "report_app_test_20261111")
RELEASES = {"regular_e": 1, "wml_c": 1, "regular_connected_f": 2, "wml_d": 2}
CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
OPERATIONS_BUCKET = "vpo-corp-royalties-report-ops-test-20261111"
OPERATIONS_NAMESPACE = "operational_preview"


class LocalCloudCredentials(Credentials):
    def refresh(self, request):
        command = shutil.which("gcloud.cmd") or shutil.which("gcloud")
        if command is None:
            raise RuntimeError("Falta la sesión de Google Cloud de pruebas.")
        result = subprocess.check_output(
            [command, "config", "config-helper", "--format=json"],
            text=True, creationflags=CREATION_FLAGS,
        )
        credential = json.loads(result)["credential"]
        self.token = credential["access_token"]
        self.expiry = datetime.fromisoformat(credential["token_expiry"]).astimezone(timezone.utc).replace(tzinfo=None)


def cloud_publications(root=RUNTIME):
    client = bigquery.Client(project=PROJECT, location="US", credentials=LocalCloudCredentials())
    if OPERATIONS_SCENARIO:
        state = SharedReportState(storage.Client(project=PROJECT, credentials=LocalCloudCredentials()),
                                  OPERATIONS_BUCKET, OPERATIONS_NAMESPACE)
        return SharedReportPublications(client, root, DATASET, state)
    return ReportPublications(client, root, DATASET)


def provision_operational_state():
    client = storage.Client(project=PROJECT, credentials=LocalCloudCredentials())
    bucket = client.bucket(OPERATIONS_BUCKET)
    bucket.labels = LABELS
    bucket.iam_configuration.public_access_prevention = "enforced"
    bucket.iam_configuration.uniform_bucket_level_access_enabled = True
    bucket.add_lifecycle_delete_rule(age=30)
    try:
        client.create_bucket(bucket, location="US")
    except Conflict:
        pass
    cloud_publications().initialize()


def dispatch_operational_job(job_id):
    env = {**os.environ, "VPO_REPORT_RUN_ID": str(job_id)}
    logs = RUNTIME / "worker_logs"
    logs.mkdir(exist_ok=True)
    with (logs / f"{job_id}.log").open("ab") as log:
        process = subprocess.Popen([sys.executable, "-B", "-m", "scripts.qa.royalty_bigquery_app_preview", "worker"],
                                   cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=CREATION_FLAGS | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    write_json(logs / f"{job_id}.json", {"pid": process.pid, "job_id": job_id, "parent_pid": os.getpid()})


def run_operational_worker():
    job_id_env = os.environ.get("VPO_REPORT_RUN_ID", "")
    isolated_environment(read_json(CONFIG))
    os.environ["VPO_REPORT_RUN_ID"] = job_id_env
    from app.operational_db import close_operational_db_pool
    from app.royalty_reports import job_main
    from app.royalty_reports.bigquery_backend.runtime import BigQueryReportBackend

    job_id = job_main.report_run_id()
    root = RUNTIME / "worker_cache" / f"job-{job_id}"
    write_json(RUNTIME / "worker_logs" / f"{job_id}.worker.json", {"job_id": job_id, "pid": os.getpid()})
    publications = cloud_publications(root)
    backend = BigQueryReportBackend(publications, shared_state=publications.state,
                                    export_bucket=OPERATIONS_BUCKET, watch_inbox=False)
    try:
        job_main.main(pinned_builder=backend.build)
    finally:
        close_operational_db_pool()


def contract_context():
    old = Path("C:/royalties_pipeline/tmp")
    original = read_json(old / "bq_full_20261104/146/from_bigquery/context/request_snapshot.json")
    filters = [original["input_manifest_json"]["distribution_contract_filter"]]
    prior = read_json(EVIDENCE / "T06/income_pdf_numbered_contracts/execution_binding.json")
    filters.append(prior["cases"]["FLT-CONTRACT_MANY-C"]["frozen_filter"])
    templates = {item["number"]: item for frozen in filters for item in frozen["templates"]}
    payouts = {}
    for path in sorted((EVIDENCE / "T05").glob("BASE-F06-*/frozen_job.json")):
        manifest = read_json(path)["input_manifest"]
        snapshot = manifest["contract_snapshot"]
        key = tuple(snapshot["artists"])
        payouts.setdefault(key, {name: manifest[name] for name in ("release_id", "catalog_dashboard", "contract_snapshot")})
    return {"number_filters": filters, "templates": list(templates.values()), "payouts": list(payouts.values())}


def enqueue(name: str) -> None:
    old_root = EVIDENCE / "T08"
    envelope = read_json(old_root / "envelopes" / (name + ".json"))
    old_identity = digest(envelope)
    context = envelope["context"]
    for item in context["artifacts"]:
        source = old_root / item["path"]
        if file_sha(source) != item["sha256"]:
            raise RuntimeError("Cambió un contexto previamente verificado.")
        target = RUNTIME / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)
        if file_sha(target) != item["sha256"]:
            raise RuntimeError("La copia del contexto no coincide.")
    if envelope["scope"] == "regular":
        fixture = contract_context()
        path = RUNTIME / "contexts" / "contract_replay" / (digest(fixture) + ".json")
        if not path.exists():
            write_json(path, fixture)
        context["artifacts"].append({
            "role": "contracts/app_test_context.json",
            "path": path.relative_to(RUNTIME).as_posix(),
            "sha256": file_sha(path),
        })
    publications = cloud_publications()
    components = {}
    for kind, item in envelope["components"].items():
        source = f"{PROJECT}.{ARCHIVE_DATASET}.report_{kind}_{old_identity[:24]}"
        prior = read_json(old_root / "checks" / old_identity / (kind + ".json"))
        table = publications.source_archive(source, kind)
        if (prior["copy_modified"] != table.modified.isoformat() or prior["destination"] != source
                or not prior["all_original_fields_compared"] or prior["result"]["differing"]):
            raise RuntimeError("Cambió la copia de BigQuery previamente conciliada.")
        components[kind] = {
            "source_table": source,
            "source_binding": table_binding(table),
            "manifest": item["manifest"],
            "manifest_sha256": item["manifest_sha256"],
        }
    release = {key: envelope[key] for key in ("scope", "publication_id", "source_release_id", "manifest_generation")}
    release.update(sequence=RELEASES[name], components=components, context=context, context_id=digest(context))
    path = RUNTIME / "incoming" / (name + ".json")
    if path.exists() and read_json(path) != release:
        raise RuntimeError("Ya existe otra versión de este manifiesto de prueba.")
    if not path.exists():
        write_json(path, release)
    print(f"Entrada publicada en la bandeja local: {name}", flush=True)


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def local_config():
    if CONFIG.exists():
        return read_json(CONFIG)
    config = {
        "api_port": free_port(),
        "web_port": free_port(),
        "pg_port": free_port(),
        "pg_password": secrets.token_urlsafe(28),
        "api_key": secrets.token_urlsafe(28),
        "session_secret": secrets.token_urlsafe(28),
        "user_password": secrets.token_urlsafe(16),
    }
    write_json(CONFIG, config)
    return config


def start_postgres(config):
    if not (PGDATA / "PG_VERSION").exists():
        password_path = RUNTIME / "initdb_password"
        password_path.write_text(config["pg_password"] + "\n", encoding="utf-8")
        try:
            subprocess.run([
                str(BIN / "initdb.exe"), "-D", str(PGDATA), "-U", "report_preview", "--auth=scram-sha-256",
                "--encoding=UTF8", "--locale=C", f"--pwfile={password_path}",
            ], check=True, creationflags=CREATION_FLAGS)
        finally:
            password_path.unlink(missing_ok=True)
    control = str(BIN / "pg_ctl.exe")
    status = subprocess.run([control, "-D", str(PGDATA), "status"], capture_output=True, creationflags=CREATION_FLAGS)
    if status.returncode != 0:
        subprocess.run([control, "-D", str(PGDATA), "-l", str(RUNTIME / "postgres.log"),
            "-o", f"-p {config['pg_port']} -h 127.0.0.1", "start"], check=True, creationflags=CREATION_FLAGS)


def isolated_environment(config):
    for name in list(os.environ):
        if name.startswith(("VPO_", "GCS_", "GOOGLE_", "CLOUD_RUN_", "CLOUDSQL_")):
            os.environ.pop(name)
    os.environ.update(
        VPO_API_KEY=config["api_key"], VPO_SESSION_SECRET=config["session_secret"],
        VPO_API_URL=f"http://127.0.0.1:{config['api_port']}",
        VPO_OPERATIONAL_DB_DRIVER="postgres", VPO_POSTGRES_CONNECT_MODE="local_proxy",
        VPO_POSTGRES_LOCAL_PROXY_HOST="127.0.0.1", VPO_POSTGRES_LOCAL_PROXY_PORT=str(config["pg_port"]),
        VPO_OPERATIONAL_DB_NAME="postgres", VPO_OPERATIONAL_DB_USER="report_preview",
        VPO_OPERATIONAL_DB_PASSWORD=config["pg_password"], VPO_BIGQUERY_DATASET=DATASET,
        VPO_API_CACHE_DIR=str(RUNTIME / "cache"), VPO_API_REPORTS_DIR=str(RUNTIME / "artifacts"),
        POLARS_MAX_THREADS="2", NEXT_TELEMETRY_DISABLED="1",
    )
    if INGEST_SCENARIO or FUGA_SCENARIO or OPERATIONS_SCENARIO or CLOUD_SCENARIO:
        return
    folder = read_json(Path("C:/royalties_pipeline/tmp/bq_all_options_20261104/live_sheets_native/folder.json"))
    if not folder["created_for_this_test_only"] or folder["sharing_enabled"]:
        raise RuntimeError("El destino de Sheets debe ser la carpeta privada de pruebas.")
    token = Path("C:/royalties_pipeline/.secrets/bq_report_tests/20261104_ruben/google_oauth_token.json")
    if token.is_file():
        os.environ["GOOGLE_OAUTH_TOKEN_JSON"] = token.read_text(encoding="utf-8")
        os.environ["GOOGLE_DRIVE_FOLDER_ID"] = folder["id"]


def seed_database(config, api):
    with psycopg.connect(host="127.0.0.1", port=config["pg_port"], user="report_preview",
                         password=config["pg_password"], dbname="postgres", autocommit=True) as conn:
        directory = conn.execute("SHOW data_directory").fetchone()[0]
        if Path(directory).resolve() != PGDATA.resolve():
            raise RuntimeError("La base conectada no pertenece a esta copia.")
        if not conn.execute("SELECT to_regclass('app_users')").fetchone()[0]:
            conn.execute((REPO / "database/postgres_schema_v1.sql").read_text(encoding="utf-8"))
        conn.execute("ALTER TABLE module_permissions ADD COLUMN IF NOT EXISTS scope_json jsonb DEFAULT '[]'::jsonb")
        if not conn.execute("SELECT 1 FROM schema_migrations WHERE version='019_report_runs_bigquery_publication'").fetchone():
            conn.execute((REPO / "database/migrations/019_report_runs_bigquery_publication.sql").read_text(encoding="utf-8-sig"))
        if conn.execute("SELECT 1 FROM app_users WHERE username='reportes-prueba'").fetchone():
            return
        conn.execute((REPO / "database/migrations/015_wml_isolated_workspace.sql").read_text(encoding="utf-8"))
        seed = {} if INGEST_SCENARIO or FUGA_SCENARIO else {"published_release_id": "wml-93a2c6fc977d03dd9283c7c8"}
        conn.execute("UPDATE royalty_workspaces SET enabled=%s, config=config || %s::jsonb WHERE scope_key='wml'",
                     (not FUGA_SCENARIO, json.dumps(seed)))
        for username in ("reportes-prueba", "otro-usuario-prueba"):
            employee = conn.execute("INSERT INTO employees(display_name) VALUES (%s) RETURNING id", (username,)).fetchone()[0]
            conn.execute("""INSERT INTO app_users(employee_id,username,password_hash,global_role,must_change_password)
                VALUES (%s,%s,%s,'editor',false)""", (employee, username, api.hash_web_password(config["user_password"])))
            for module in ("royalty_reports", "master_contracts"):
                conn.execute("INSERT INTO app_modules(module_key,label) VALUES (%s,%s) ON CONFLICT DO NOTHING", (module, module))
                conn.execute("""INSERT INTO module_permissions(employee_id,module_key,can_access,can_create,can_view_history)
                    VALUES (%s,%s,true,true,true)""", (employee, module))


def serve():
    import uvicorn

    if CLOUD_SCENARIO:
        raise RuntimeError("La API del escenario cloud se ejecuta en el servicio aislado de Cloud Run.")
    config = local_config()
    start_postgres(config)
    isolated_environment(config)
    sys.path.insert(0, str(DEPENDENCIES / "python"))
    from app import vpo_corp_api as api
    from app.royalty_reports.bigquery_backend.runtime import BigQueryReportBackend

    seed_database(config, api)
    with api.operational_connect() as conn:
        queued = tuple(row["id"] for row in conn.execute(
            "SELECT id FROM report_runs WHERE status='queued' ORDER BY id"
        ).fetchall())
    if OPERATIONS_SCENARIO:
        publications = cloud_publications(RUNTIME / "api_cache" / str(os.getpid()))
        backend = BigQueryReportBackend(publications, shared_state=publications.state,
                                        queued_jobs=queued, dispatch_job=dispatch_operational_job, watch_inbox=False)
    else:
        backend = BigQueryReportBackend(cloud_publications(), publish_interval=3,
                                        export_bucket="vpo-corp-royalties-report-app-test-20261111",
                                        queued_jobs=queued)
    api.app.state.royalty_report_backend = backend
    # The test copy exposes only the screens and routes exercised by these checks.
    def allowed(path, method):
        return (
            path in {"/auth/login", "/auth/session", "/me/permissions", "/wml/workspace", "/openapi.json"}
            or re.fullmatch(r"/reports/jobs(?:/\d+(?:/download)?)?", path)
            or path in {"/reports/royalty/options", "/reports/royalty/detail-count",
                        "/reports/royalty/contract-options", "/reports/royalty/distribution-contract-options"}
        )

    async def application(scope, receive, send):
        if scope["type"] == "http" and not allowed(scope["path"], scope["method"]):
            from starlette.responses import JSONResponse
            await JSONResponse({"detail": "Esta ruta está fuera de la copia del Reporte de regalías."}, status_code=404)(scope, receive, send)
            return
        await api.app(scope, receive, send)

    write_json(RUNTIME / "server.json", {"pid": os.getpid(), "api_port": config["api_port"], "web_port": config["web_port"]})
    uvicorn.run(application, host="127.0.0.1", port=config["api_port"])


def web():
    config = read_json(CONFIG)
    isolated_environment(config)
    command = ["node", str(REPO / "web/node_modules/next/dist/bin/next"), "dev", "--hostname", "127.0.0.1",
               "--port", str(config["web_port"])]
    subprocess.run(command, cwd=REPO / "web", check=True)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    sub.add_parser("web")
    if OPERATIONS_SCENARIO:
        sub.add_parser("provision")
        sub.add_parser("publish-loop")
        sub.add_parser("worker")
    publish = sub.add_parser("enqueue")
    publish.add_argument("name", choices=sorted(RELEASES))
    args = parser.parse_args()
    if args.command == "enqueue":
        enqueue(args.name)
    elif args.command == "serve":
        serve()
    elif args.command == "web":
        web()
    elif args.command == "provision":
        provision_operational_state()
    elif args.command == "publish-loop":
        watch_publications(cloud_publications(), Event(), 3)
    elif args.command == "worker":
        sys.path.insert(0, str(DEPENDENCIES / "python"))
        run_operational_worker()


if __name__ == "__main__":
    main()
