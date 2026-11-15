"""Replay a new FUGA statement through the isolated Cloud report publisher."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import polars as pl
from google.api_core.exceptions import Conflict, NotFound, PreconditionFailed
from google.cloud import bigquery

from app.royalty_reports.bigquery_backend.publication import LABELS, PROJECT, digest, file_sha, read_json, table_binding, write_json
from app.wml_job import immutable_upload
from scripts.qa.royalty_bigquery_ingest_preview import load_component

MONTH = "2026-04"
NAME = "April2026StatementRun_INDYANARECORDSLLC-royalty_product_and_asset.csv"
PREFIX = "fuga_arrival_april_2026"
BASE = "regular_connected_complete_f_20261110"
CUT = "regular_fuga_before_april_2026"
DATASET = f"{PROJECT}.report_app_test_cloud_20261111"
MARTS = {"raw": "standardized_raw_all_sources.parquet", "song": "song_level_all_sources.parquet",
         "eligible": "royalties_dashboard_summary.parquet"}
QUEUE = "regular_fuga_arrivals"


def quoted(name):
    return chr(96) + name + chr(96)


def table_for(release, kind):
    return f"{DATASET}.report_{kind}_{digest(release)[:24]}"


def predicate(kind, component, month=MONTH, filename=NAME):
    if kind == "eligible":
        return f"source='fuga' AND account='indyana_records' AND statement_month=DATE '{month}-01'"
    fields = {f["name"]: f["column"] for f in component["manifest"]["fields"]}
    condition = f"{quoted(fields['source'])}='fuga' AND {quoted(fields['account'])}='indyana_records'"
    if kind == "raw":
        return condition + f" AND {quoted(fields['statement_file_name'])}='{filename}'"
    return condition + f" AND _statement_month='{month}'"


def start_query(client, sql, identity, destination=None):
    job_id = f"report_fuga_cloud_{identity[:32]}"
    config = bigquery.QueryJobConfig(labels=LABELS, maximum_bytes_billed=200_000_000_000)
    if destination is not None:
        config.destination = destination
        config.write_disposition = "WRITE_EMPTY"
    for attempt in range(3):
        attempt_id = f"{job_id}_{attempt}"
        try:
            job = client.query(sql, job_id=attempt_id, job_config=config, location="US", job_retry=None)
        except Conflict:
            job = client.get_job(attempt_id, location="US")
        if job.query != sql:
            raise RuntimeError("El trabajo de BigQuery pertenece a otra consulta.")
        try:
            job.result(timeout=1200)
        except Exception:
            if job.state == "DONE" and job.error_result:
                if job.error_result.get("reason") in {"backendError", "internalError", "rateLimitExceeded"}:
                    continue
            raise
        return job
    raise RuntimeError("BigQuery agotó los reintentos de la publicación FUGA.")


def combined_component(pub, base, kind, release_id, *, delta=None, arrival=None, removed=()):
    """Keep historical occurrences and their fields. Rebind them to the new release."""
    parent = base["components"][kind]
    manifest = dict(parent["manifest"])
    manifest["release_id"] = release_id
    identity = digest({"base": digest(base), "delta": delta, "kind": kind, "release": release_id,
                       "excluded": removed})
    destination = f"{pub.dataset}.ingest_{kind}_{identity[:24]}"
    original = quoted(table_for(base, kind))
    excluded = " OR ".join(f"({predicate(kind, parent, month, name)})" for month, name in removed)
    where = f" WHERE NOT COALESCE(({excluded}), FALSE)" if excluded else ""
    if kind == "eligible":
        left = f"SELECT * REPLACE ('{release_id}' AS release_id) FROM {original}{where}"
        right = f"SELECT * FROM {quoted(delta['source_table'])}" if delta else None
    else:
        manifest["source_id"] = f"{parent['manifest']['source_id']}|{release_id}"
        manifest["selection"] = {"complete": True, "parent_publication": base["publication_id"], "arrival": arrival}
        marker = manifest["source_id"].replace("'", "''")
        changes = f"'{release_id}' AS _release_id, '{marker}' AS _source_id"
        left = (f"SELECT * REPLACE ({changes}, CONCAT('{marker}:',CAST(_origin_position AS STRING)) AS _source_record_key) "
                f"FROM {original}{where}")
        right = None
        if delta:
            fields = {f["name"]: f for f in delta["manifest"]["fields"]}
            if set(fields) - {f["name"] for f in manifest["fields"]}:
                raise RuntimeError(f"El statement introduce campos {kind} fuera del esquema del histórico.")
            columns = []
            for f in manifest["fields"]:
                alias = f["column"]
                if not alias:
                    continue
                current = fields.get(f["name"])
                if not current:
                    value = "NULL"
                elif current["column"]:
                    value = quoted(current["column"])
                else:
                    value = f"JSON_VALUE(_source_extension_json, '$.\"{f['name']}\"')"
                columns.append(f"CAST({value} AS {f['bigquery_type']}) AS {quoted(alias)}")
            extra = {}
            for f in manifest["fields"]:
                if f["column"] or f["name"] not in fields:
                    continue
                current = fields[f["name"]]
                value = quoted(current["column"]) if current["column"] else f"JSON_VALUE(_source_extension_json, '$.\"{f['name']}\"')"
                extra[f["name"]] = f"CAST({value} AS {f['bigquery_type']})"
            extension = ("TO_JSON_STRING(STRUCT(" + ", ".join(f"{v} AS {quoted(k)}" for k, v in extra.items()) + "))"
                         if extra else "'{}'")
            offset = next(iter(pub.client.query(
                f"SELECT COALESCE(MAX(_origin_position)+1, 0) AS next_position FROM {original}",
                job_config=bigquery.QueryJobConfig(labels=LABELS)).result())).next_position
            position = f"_origin_position + {offset}"
            right = (f"SELECT '{release_id}' AS _release_id, '{manifest['schema_id']}' AS _schema_id, "
                     f"'{marker}' AS _source_id, {position} AS _origin_position, "
                     f"CONCAT('{marker}:', CAST({position} AS STRING)) AS _source_record_key, "
                     f"_statement_month, _transaction_month, {', '.join(columns)}, {extension} AS _source_extension_json "
                     f"FROM {quoted(delta['source_table'])}")
    query = left if right is None else left + " UNION ALL BY NAME " + right
    job = start_query(pub.client, query, identity, destination)
    table = pub.client.get_table(destination)
    labels = {**LABELS, "role": kind}
    if table.labels != labels:
        table.labels = labels
        table = pub.client.update_table(table, ["labels"])
    return {"source_table": destination, "source_binding": table_binding(table), "manifest": manifest,
            "manifest_sha256": digest(manifest)}, job.job_id


def release_context(pub, base, release_id, details):
    folder = pub.root / "contexts" / release_id
    write_json(folder / "fuga_arrival.json", details)
    path = folder / "fuga_arrival.json"
    context = dict(base["context"])
    context["artifacts"] = [a for a in context["artifacts"] if a["role"] != "publication/fuga_arrival.json"]
    context["artifacts"].append({"role": "publication/fuga_arrival.json",
                                 "path": path.relative_to(pub.root).as_posix(), "sha256": file_sha(path)})
    return context


def publish_cut(pub):
    current = pub.read_active("regular")
    if current["id"] == CUT:
        return
    if current["id"] != BASE:
        raise RuntimeError("El catálogo activo no corresponde al histórico de la prueba.")
    base = pub.checked(pub.pin("regular"))
    components, jobs = {}, {}
    for kind in MARTS:
        components[kind], jobs[kind] = combined_component(pub, base, kind, CUT, removed=((MONTH, NAME),))
    context = release_context(pub, base, CUT, {"base": current, "month_excluded": MONTH, "excluded_file": NAME, "jobs": jobs})
    release = {"scope": "regular", "publication_id": CUT, "source_release_id": CUT, "sequence": current["sequence"] + 1,
               "manifest_generation": base["manifest_generation"], "context": context,
               "context_id": digest(context), "components": components}
    assert components["raw"]["source_binding"]["rows"] == base["components"]["raw"]["source_binding"]["rows"] - 344636
    pub.publish(release)
    print(f"Histórico previo a la llegada activo: {CUT}.", flush=True)


def staged_blob(bucket, name, entry, destination, *, prefix=PREFIX):
    if (not name.startswith(prefix + "/") or int(entry["generation"]) <= 0
            or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])):
        raise ValueError("Objeto fuera de la llegada aislada.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    blob = bucket.blob(name, generation=int(entry["generation"]))
    blob.download_to_filename(destination, if_generation_match=blob.generation, checksum="crc32c")
    if file_sha(destination) != entry["sha256"] or destination.stat().st_size != int(entry["bytes"]):
        raise RuntimeError("La entrada cambió de contenido.")
    return destination


def package_marts(pub, bucket, marts, folder, release_id, *, prefix=PREFIX):
    entries = {}
    for name in MARTS.values():
        path = marts / name
        obj = immutable_upload(bucket, f"{prefix}/marts/{release_id}/{file_sha(path)}/{name}", path)
        entries[name] = {"object_name": obj.name, "generation": str(obj.generation), "size_bytes": obj.size}
    package = {"release_id": release_id, "files": entries}
    components, jobs = {}, {}
    for kind in ("raw", "song"):
        components[kind], jobs[kind] = load_component(pub, bucket, package, marts, kind, MARTS[kind])
    from scripts.load_bigquery_release import build_dashboard
    encoded = folder / "eligible.parquet"
    build_dashboard(marts / MARTS["eligible"], encoded, release_id)
    identity = digest({"release": release_id, "package": package})[:24]
    destination = f"{pub.dataset}.ingest_eligible_{identity}"
    job_id = f"report_fuga_cloud_load_eligible_{identity}"
    try:
        job = pub.client.get_job(job_id, location="US")
    except NotFound:
        config = bigquery.LoadJobConfig(source_format="PARQUET", write_disposition="WRITE_EMPTY", labels=LABELS)
        try:
            with encoded.open("rb") as stream:
                job = pub.client.load_table_from_file(stream, destination, job_config=config, job_id=job_id, location="US")
        except Conflict:
            job = pub.client.get_job(job_id, location="US")
    if str(job.destination) != destination:
        raise RuntimeError("La carga de elegibles no corresponde a esta entrega.")
    job.result(timeout=900)
    table = pub.client.get_table(destination)
    labels = {**LABELS, "role": "eligible"}
    if table.labels != labels:
        table.labels = labels
        table = pub.client.update_table(table, ["labels"])
    assert table.num_rows == pl.scan_parquet(encoded).select(pl.len()).collect().item()
    manifest = {"release_id": release_id, "rows": table.num_rows, "native_sha256": file_sha(encoded)}
    components["eligible"] = {"source_table": destination, "source_binding": table_binding(table),
                              "manifest": manifest, "manifest_sha256": digest(manifest)}
    jobs["eligible"] = job_id
    return components, jobs, package


def process_arrival(pub):
    import os
    from scripts.qa.royalty_bigquery_cloud_preview import ROOT

    bucket = pub.state.bucket
    pointer, generation = pub.state.current(f"{PREFIX}/latest.json")
    if pointer is None:
        print("FUGA: todavía no hay un statement anunciado.", flush=True)
        return
    if pointer["file"] != NAME or not re.fullmatch(r"[a-f0-9]{64}", pointer["sha256"]):
        raise ValueError("El manifiesto no corresponde al statement autorizado.")
    release_id = f"fuga-{pointer['sha256'][:24]}"
    publication_id = release_id.replace("-", "_")
    current = pub.read_active("regular")
    if current["id"] == publication_id and pub.state.read(f"{PREFIX}/receipt.json"):
        print(f"FUGA: {publication_id} ya está activo.", flush=True)
        return
    if current["id"] not in {CUT, publication_id}:
        raise RuntimeError("La llegada no corresponde al corte aislado preparado.")
    cut = pub.read_ready(CUT)["release"]
    pub.checked({"scope": "regular", "publication_id": CUT, "envelope_sha256": digest(cut)})
    original = pub.read_ready(BASE)["release"]
    root = ROOT / "fuga-arrival"
    # Worker subprocess keeps its sandboxed paths separate from the publisher.
    source = staged_blob(bucket, pointer["object"], pointer, root / "inputs" / NAME)
    context = root / "source_context"
    for name, entry in pointer["context"].items():
        if Path(name).name != name:
            raise ValueError("Nombre de contexto inválido.")
        staged_blob(bucket, entry["object"], entry, context / name)
    candidate = root / "candidate"
    subprocess.run([sys.executable, "-B", "-m", "scripts.qa.royalty_bigquery_fuga_native", "--cloud-arrival",
                    "--code", str(Path(__file__).resolve().parents[2]), "--target", str(candidate),
                    "--statement", str(source), "--context", str(context)], check=True)
    native = json.loads((candidate / "native_receipt.json").read_text(encoding="utf-8"))
    assert native["package_validation"]["ok"] and native["input_sha256"] == pointer["sha256"]
    marts = Path(native["marts"])
    # The report song projection is by statement. Native single-file FUGA aggregates omit that constant.
    song = marts / MARTS["song"]
    frame = pl.read_parquet(song)
    frame.with_columns(pl.lit(MONTH).alias("statement_period")).write_parquet(song)
    delta, loads, package = package_marts(pub, bucket, marts, root, release_id)
    assert delta["raw"]["source_binding"]["rows"] == native["metrics"]["rows"] == 344636
    components, jobs = {}, {}
    for kind in MARTS:
        components[kind], jobs[kind] = combined_component(pub, cut, kind, release_id, delta=delta[kind],
                                                           arrival=pointer["sha256"])
        assert components[kind]["source_binding"]["rows"] == (cut["components"][kind]["source_binding"]["rows"]
                                                                + delta[kind]["source_binding"]["rows"])
    assert components["raw"]["source_binding"]["rows"] == original["components"]["raw"]["source_binding"]["rows"]
    details = {"arrival": pointer, "arrival_generation": generation, "base_publication": CUT,
               "package": package, "loads": loads, "publication_queries": jobs, "metrics": native["metrics"]}
    context = release_context(pub, cut, release_id, details)
    release = {"scope": "regular", "publication_id": publication_id, "source_release_id": release_id,
               "sequence": cut["sequence"] + 1, "manifest_generation": int(generation), "context": context,
               "context_id": digest(context), "components": components}
    if pub.state.current(f"{PREFIX}/latest.json")[1] != generation:
        raise RuntimeError("Cambió la entrada antes de la publicación.")
    ready = pub.publish(release)
    pin = pub.pin("regular")
    assert pin["publication_id"] == publication_id
    try:
        pub.state.write(f"{PREFIX}/receipt.json", {
            **details, "pin": pin, "sequence": release["sequence"], "execution": os.environ["CLOUD_RUN_EXECUTION"],
            "attempt": int(os.environ["CLOUD_RUN_TASK_ATTEMPT"]), "rows": {k: v["binding"]["rows"] for k, v in ready["tables"].items()},
        }, 0)
    except PreconditionFailed:
        if pub.state.read(f"{PREFIX}/receipt.json")["pin"] != pin:
            raise
    print(f"FUGA publicado automáticamente: {publication_id}.", flush=True)


def arrival_coordinates(filename):
    from scripts.lib.statement_period import from_fuga_filename

    if not re.fullmatch(r"[A-Za-z0-9_ -]+-royalty_product_and_asset\.csv", filename):
        raise ValueError("La entrega debe ser un CSV FUGA regular.")
    period = from_fuga_filename(filename).period
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        raise ValueError("El statement FUGA no tiene período válido.")
    return period, filename


def prepare_recurring_cut(pub):
    """Build a rehearsal baseline. The inbox worker has no dependency on the excluded filenames."""
    control = pub.state.read(f"{QUEUE}/baseline.json")
    current = pub.read_active("regular")
    if current["id"] == control["id"]:
        return
    if current != control["parent"]:
        raise RuntimeError("Cambió la publicación de partida de la prueba.")
    base = pub.checked(pub.pin("regular"))
    excluded = tuple(arrival_coordinates(name) for name in control["excluded"])
    components, jobs = {}, {}
    for kind in MARTS:
        components[kind], jobs[kind] = combined_component(pub, base, kind, control["id"], removed=excluded)
        if components[kind]["source_binding"]["rows"] >= base["components"][kind]["source_binding"]["rows"]:
            raise RuntimeError(f"El corte no excluyó movimientos de {kind}.")
    context = release_context(pub, base, control["id"], {"baseline": current, "excluded": excluded, "jobs": jobs})
    release = {"scope": "regular", "publication_id": control["id"], "source_release_id": control["id"],
               "sequence": current["sequence"] + 1, "manifest_generation": base["manifest_generation"],
               "context": context, "context_id": digest(context), "components": components}
    pub.publish(release)
    print(f"Corte de prueba activo: {control['id']}.", flush=True)


def save_state_once(state, key, value):
    try:
        state.write(key, value, 0)
    except PreconditionFailed:
        if state.read(key) != value:
            raise RuntimeError(f"La entrega ya tiene otro comprobante: {key}.")


def announce_raw_arrivals(state):
    """Bind regular FUGA files dropped in the private bucket to one approved source context."""
    prefix = f"{QUEUE}/raw/"
    arrivals = sorted(state.bucket.list_blobs(prefix=prefix), key=lambda blob: (blob.time_created, blob.name))
    if not arrivals:
        return
    context = state.read(f"{QUEUE}/source_context.json")
    if not context or "binding.json" not in context:
        raise RuntimeError("Falta configurar el contexto de ingesta FUGA de la copia.")
    for blob in arrivals:
        filename = blob.name.removeprefix(prefix)
        arrival_coordinates(filename)
        generation = int(blob.generation)
        discovered = f"{QUEUE}/discovered/{digest([blob.name, generation])}.json"
        if state.read(discovered) is not None:
            continue
        with blob.open("rb", if_generation_match=generation, chunk_size=8 * 1024 * 1024) as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        pointer = {"file": filename, "object": blob.name, "generation": generation,
                   "sha256": checksum, "bytes": int(blob.size), "context": context}
        key = f"{QUEUE}/inbox/{checksum}.json"
        try:
            state.write(key, pointer, 0)
        except PreconditionFailed:
            existing = state.read(key)
            if existing is None or any(existing[k] != pointer[k] for k in ("file", "sha256", "bytes")):
                raise RuntimeError("El mismo contenido FUGA aparece con otro nombre o período.")
        save_state_once(state, discovered, {"file": filename, "generation": generation, "sha256": checksum})


def merge_product_indexes(previous, incoming):
    from scripts.lib.product_income import validate_index

    previous = validate_index(previous)
    incoming = validate_index(incoming)
    if any(previous[k] != incoming[k] for k in ("schema_version", "rule", "scope")):
        raise RuntimeError("La asignación de productos no corresponde al catálogo acumulado.")
    products = dict(previous["products"])
    for key, value in incoming["products"].items():
        old = products.get(key)
        if old is None:
            products[key] = value
            continue
        field = "native_product_scopes"
        if {k: v for k, v in old.items() if k != field} != {k: v for k, v in value.items() if k != field}:
            raise RuntimeError("El reparto de UPC cambió respecto de la versión acumulada.")
        scopes = sorted(set(old.get(field, ())) | set(value.get(field, ())))
        products[key] = {**old, field: scopes} if scopes else old
    if products == previous["products"]:
        return previous
    evidence = {key: previous[key] for key in ("schema_version", "rule", "scope")}
    evidence["products"] = products
    checksum = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    return validate_index({**evidence, "evidence_hash": checksum})


def append_delivery(pub, base, pointer, publication_id, generation):
    from scripts.qa.royalty_bigquery_cloud_preview import ROOT

    month, filename = arrival_coordinates(pointer["file"])
    release_id = publication_id.replace("_", "-", 1)
    bucket = pub.state.bucket
    root = ROOT / "fuga-arrival"
    source = staged_blob(bucket, pointer["object"], pointer, root / "inputs" / filename, prefix=QUEUE)
    context_folder = root / "source_context"
    for name, entry in pointer["context"].items():
        if Path(name).name != name:
            raise ValueError("Nombre de contexto inválido.")
        staged_blob(bucket, entry["object"], entry, context_folder / name, prefix=QUEUE)
    candidate = root / "candidate"
    subprocess.run([sys.executable, "-B", "-m", "scripts.qa.royalty_bigquery_fuga_native", "--cloud-arrival",
                    "--code", str(Path(__file__).resolve().parents[2]), "--target", str(candidate),
                    "--statement", str(source), "--context", str(context_folder)], check=True)
    native = read_json(candidate / "native_receipt.json")
    if not native["package_validation"]["ok"] or native["input_sha256"] != pointer["sha256"]:
        raise RuntimeError("La ingesta no corresponde a la entrega anunciada.")
    marts = Path(native["marts"])
    song = marts / MARTS["song"]
    pl.read_parquet(song).with_columns(pl.lit(month).alias("statement_period")).write_parquet(song)
    delta, loads, package = package_marts(pub, bucket, marts, root, release_id, prefix=QUEUE)
    components, jobs = {}, {}
    for kind in MARTS:
        parent = base["components"][kind]
        old_table = quoted(table_for(base, kind))
        where = predicate(kind, parent, month, filename)
        if kind == "raw":
            # One regular statement per period. Corrections use their own ingestion path.
            fields = {f["name"]: f["column"] for f in parent["manifest"]["fields"]}
            where = (f"{quoted(fields['source'])}='fuga' AND {quoted(fields['account'])}='indyana_records' "
                     f"AND (_statement_month='{month}' OR {quoted(fields['statement_file_name'])}='{filename}')")
        found = next(iter(pub.client.query(
            f"SELECT COUNTIF({where}) AS matches FROM {old_table}",
            job_config=bigquery.QueryJobConfig(labels=LABELS)).result())).matches
        if found:
            raise RuntimeError(f"El período o archivo FUGA ya está incorporado en {kind}.")
        component, jobs[kind] = combined_component(pub, base, kind, release_id, delta=delta[kind],
                                                      arrival=pointer["sha256"])
        if component["source_binding"]["rows"] != parent["source_binding"]["rows"] + delta[kind]["source_binding"]["rows"]:
            raise RuntimeError(f"La entrega no conserva exactamente las ocurrencias de {kind}.")
        components[kind] = component
    if delta["raw"]["source_binding"]["rows"] != native["metrics"]["rows"]:
        raise RuntimeError("Cambió la cantidad de movimientos de la entrega.")
    details = {"arrival": pointer, "arrival_generation": generation, "parent": base["publication_id"],
               "package": package, "loads": loads, "append_queries": jobs, "metrics": native["metrics"],
               "new_rows": {kind: value["source_binding"]["rows"] for kind, value in delta.items()}}
    context = release_context(pub, base, release_id, details)
    inherited = pub.paths(base)["marts/product_income_allocations.json"]
    previous, incoming = read_json(inherited), read_json(marts / "product_income_allocations.json")
    merged = merge_product_indexes(previous, incoming)
    if merged != previous:
        allocation = pub.root / "contexts" / release_id / "product_income_allocations.json"
        write_json(allocation, merged)
        role = "marts/product_income_allocations.json"
        context["artifacts"] = [
            {"role": role, "path": allocation.relative_to(pub.root).as_posix(), "sha256": file_sha(allocation)}
            if artifact["role"] == role else artifact for artifact in context["artifacts"]
        ]
    return {"scope": "regular", "publication_id": publication_id, "source_release_id": release_id,
            "sequence": base["sequence"] + 1, "manifest_generation": generation,
            "context": context, "context_id": digest(context), "components": components}


def process_pending_arrival(pub):
    state = pub.state
    announce_raw_arrivals(state)
    inbox = state.blob(f"{QUEUE}/inbox/").name
    for obj in sorted(state.bucket.list_blobs(prefix=inbox), key=lambda blob: (blob.time_created, blob.name)):
        identity = obj.name.removeprefix(inbox).removesuffix(".json")
        if not re.fullmatch(r"[a-f0-9]{64}", identity) or obj.name != f"{inbox}{identity}.json":
            raise ValueError("Entrada fuera de la bandeja de statements.")
        receipt_key = f"{QUEUE}/receipts/{identity}.json"
        if state.read(receipt_key):
            continue
        break
    else:
        print("No hay un statement FUGA pendiente.", flush=True)
        return

    pointer = json.loads(obj.download_as_bytes(if_generation_match=obj.generation))
    if pointer["sha256"] != identity:
        raise ValueError("La identidad de la entrada no coincide.")
    if state.read(receipt_key):
        return
    publication_id = f"fuga_{identity[:24]}"
    current = pub.read_active("regular")
    ready = pub.read_ready(publication_id)
    if ready is None:
        parent = pub.checked({"scope": "regular", "publication_id": current["id"],
                              "envelope_sha256": current["sha256"]})
        release = append_delivery(pub, parent, pointer, publication_id, int(obj.generation))
        # A scheduler tick can overlap a prior execution of the same immutable input.
        # Adopt the committed preparation only after checking its lineage below.
        from app.royalty_reports.bigquery_backend.publication import PublicationError
        try:
            ready = pub.prepare(release)
        except PublicationError:
            ready = pub.read_ready(publication_id)
            if ready is None:
                raise
    release = ready["release"]
    paths = pub.paths(release)
    details = read_json(paths["publication/fuga_arrival.json"])
    if details["arrival"] != pointer or details["arrival_generation"] != int(obj.generation):
        raise RuntimeError("La publicación preparada corresponde a otro manifiesto.")
    if state.read(receipt_key):
        return
    current = pub.read_active("regular")
    if current["id"] not in {details["parent"], publication_id}:
        raise RuntimeError("La publicación activa cambió mientras se preparaba el statement.")
    execution = os.environ["CLOUD_RUN_EXECUTION"]
    attempt = int(os.environ["CLOUD_RUN_TASK_ATTEMPT"])
    save_state_once(state, f"{QUEUE}/attempts/{execution}-{attempt}.json", {
        "execution": execution, "attempt": attempt, "active": current,
        "prepared": publication_id, "sequence": release["sequence"], "tables": ready["tables"],
    })
    if attempt == 0 and os.getenv("VPO_REPORT_PREVIEW_INTERRUPT_FUGA") == identity:
        raise RuntimeError("Interrupción de prueba con las tres tablas listas y antes de activar FUGA.")
    if pub.read_active("regular")["id"] not in {details["parent"], publication_id}:
        raise RuntimeError("Cambió la versión activa antes de publicar el statement.")
    pub.activate(release)
    pin = pub.pin("regular")
    if pin["publication_id"] != publication_id:
        raise RuntimeError("El statement quedó detrás de una publicación posterior.")
    receipt = {**details, "pin": pin, "sequence": release["sequence"],
               "execution": execution, "attempt": attempt, "tables": ready["tables"]}
    try:
        state.write(receipt_key, receipt, 0)
    except PreconditionFailed:
        existing = state.read(receipt_key)
        if existing["pin"] != pin or existing["arrival"] != pointer:
            raise RuntimeError("Otro trabajo confirmó una entrega diferente.")
    print(f"FUGA publicado automáticamente: {publication_id}.", flush=True)


def main():
    from scripts.qa.royalty_bigquery_cloud_preview import publications
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("fuga-cut", "fuga-arrival", "regular-fuga-cut", "regular-fuga-inbox"))
    operation = parser.parse_args().operation
    pub = publications(operation)
    if operation == "regular-fuga-cut":
        prepare_recurring_cut(pub)
    elif operation == "regular-fuga-inbox":
        process_pending_arrival(pub)
    elif operation == "fuga-cut":
        publish_cut(pub)
    else:
        process_arrival(pub)


if __name__ == "__main__":
    main()
