"""Prepare immutable BigQuery inputs from the complete, published catalog."""

from math import isclose
import json
from pathlib import Path

from google.api_core.exceptions import Conflict, NotFound
from google.cloud import bigquery
import polars as pl
import pyarrow.parquet as pq

from . import projection
from .publication import PublicationError, digest, file_sha, table_binding, write_json


REPO = Path(__file__).resolve().parents[3]
MARTS = {"raw": "standardized_raw_all_sources.parquet", "song": "song_level_all_sources.parquet",
         "eligible": "royalties_dashboard_summary.parquet"}
CONTEXT = {"marts/catalog_master.parquet": "catalog_master.parquet",
           "marts/catalog_release_metadata.parquet": "catalog_release_metadata.parquet",
           "marts/catalog_status.parquet": "catalog_status.parquet",
           "marts/product_income_allocations.json": "product_income_allocations.json",
           "policy/policy_snapshot.json": "policy_snapshot.json"}


def load_component(publications, bucket, package, folder, kind, name, *, upload=None):
    client = publications.client
    labels = publications.labels
    source = folder / name
    entry = package["files"][name]
    native = pl.scan_parquet(source)
    manifest = projection.prepare_manifest(
        native.collect_schema(), repo=REPO,
        source={"uri": f"gs://{bucket.name}/{entry['object_name']}", "generation": int(entry["generation"]),
                "sha256": file_sha(source)},
        release_id=package["release_id"], selection={"complete": True},
    )
    schema = [bigquery.SchemaField.from_api_repr(field) for field in projection.bigquery_schema(manifest)]
    identity = digest({"dataset": publications.dataset, "kind": kind, "manifest": manifest})[:24]
    destination = f"{publications.dataset}.ingest_{kind}_{identity}"
    job_id = f"report_ingest_load_{kind}_{identity}"
    try:
        job = client.get_job(job_id, location="US")
    except NotFound:
        encoded = folder / f"{kind}_{identity}.parquet"
        if upload is None:
            projection.project(native.with_row_index("_origin_position"), manifest).sink_parquet(encoded, compression="zstd")
        else:
            import pyarrow.parquet as pq

            offset = 0
            writer = None
            try:
                for batch in pq.ParquetFile(source).iter_batches(batch_size=16_384, use_threads=False):
                    frame = pl.from_arrow(batch).with_row_index("_origin_position", offset=offset)
                    projected = projection.project(frame.lazy(), manifest).collect(engine="streaming").to_arrow()
                    if writer is None:
                        writer = pq.ParquetWriter(encoded, projected.schema, compression="zstd")
                    writer.write_table(projected)
                    offset += batch.num_rows
            finally:
                if writer is not None:
                    writer.close()
            if writer is None:
                projection.project(native.with_row_index("_origin_position"), manifest).sink_parquet(encoded, compression="zstd")
        config = bigquery.LoadJobConfig(schema=schema, source_format="PARQUET",
                                       write_disposition="WRITE_EMPTY", labels=labels)
        try:
            if upload is None:
                with encoded.open("rb") as stream:
                    job = client.load_table_from_file(stream, destination, job_id=job_id, job_config=config,
                                                      location="US", size=encoded.stat().st_size)
            else:
                job = client.load_table_from_uri(upload(encoded), destination, job_id=job_id,
                                                 job_config=config, location="US")
        except Conflict:
            job = client.get_job(job_id, location="US")
    if job.job_type != "load" or str(job.destination) != destination:
        raise RuntimeError("El trabajo de BigQuery no corresponde a la proyección esperada.")
    job.result(timeout=900)
    loaded = client.get_table(destination)
    rows = native.select(pl.len()).collect().item()
    aliases = {"INTEGER": "INT64", "FLOAT": "FLOAT64", "BOOLEAN": "BOOL"}
    def fields(columns):
        return [(field.name, aliases.get(field.field_type, field.field_type), field.mode) for field in columns]
    if loaded.num_rows != rows or fields(loaded.schema) != fields(schema):
        raise RuntimeError(f"La proyección de {kind} no conserva el esquema o las filas.")
    check = next(iter(client.query(
        f"""SELECT COUNT(DISTINCT _origin_position) AS positions, MIN(_origin_position) AS first,
                   MAX(_origin_position) AS last, COUNTIF(_source_id != @source) AS foreign_rows
            FROM `{destination}`""",
        job_config=bigquery.QueryJobConfig(labels=labels, query_parameters=[
            bigquery.ScalarQueryParameter("source", "STRING", manifest["source_id"]),
        ]),
    ).result()))
    if (check.positions, check.first, check.last, check.foreign_rows) != (rows, 0, rows - 1, 0):
        raise RuntimeError(f"La proyección de {kind} perdió posiciones de origen.")
    wanted_labels = {**labels, "role": kind}
    if loaded.labels != wanted_labels:
        loaded.labels = wanted_labels
        loaded = client.update_table(loaded, ["labels"])
    return {"source_table": destination, "source_binding": table_binding(loaded),
            "manifest": manifest, "manifest_sha256": digest(manifest)}, job_id


def load_prepared(pub, path, kind, identity, upload):
    labels = pub.labels
    dest = f"{pub.dataset}.ingest_{kind}_{identity[:24]}"
    job_id = f"report_regular_load_{kind}_{identity[:24]}"
    try:
        job = pub.client.get_job(job_id, location="US")
    except NotFound:
        config = bigquery.LoadJobConfig(source_format="PARQUET", write_disposition="WRITE_EMPTY", labels=pub.labels)
        if kind == "evidence":
            config.time_partitioning = bigquery.TimePartitioning(type_="MONTH", field="statement_month")
            config.clustering_fields = ["source", "account"]
        try:
            job = pub.client.load_table_from_uri(upload(path), dest, location="US", job_id=job_id, job_config=config)
        except Conflict:
            job = pub.client.get_job(job_id, location="US")
    if job.job_type != "load" or str(job.destination) != dest:
        raise PublicationError("La carga no corresponde al cierre fijado.")
    job.result(timeout=1800)
    table = pub.client.get_table(dest)
    if table.num_rows != pq.ParquetFile(path).metadata.num_rows:
        raise PublicationError("La carga del cierre quedó incompleta.")
    wanted = {**labels, "role": kind}
    if table.labels != wanted:
        table.labels = wanted
        table = pub.client.update_table(table, ["labels"])
    return table, job_id


def reconcile_input(pub, component, path, *, table=None):
    projected = {field['name']: field['column'] for field in component['manifest']['fields']}
    source, account, usd, units = (f"`{projected[key]}`" for key in ('source', 'account', 'amount_usd', 'units'))
    table = table or component['source_table']
    query = pub.client.query(f"""
        SELECT {source} AS source, {account} AS account, COUNT(*) AS row_count,
               COUNT({usd}) AS economic_rows, SUM(CAST({usd} AS BIGNUMERIC)) AS usd,
               SUM(CAST({units} AS BIGNUMERIC)) AS units
        FROM `{table}` GROUP BY source, account
    """, job_config=bigquery.QueryJobConfig(labels=pub.labels, maximum_bytes_billed=10_000_000_000))
    remote = {(row.source, row.account): row for row in query.result(timeout=180)}
    local = (pl.scan_parquet(path).group_by('source', 'account').agg(
        pl.len().alias('row_count'), pl.col('amount_usd').count().alias('economic_rows'),
        pl.col('amount_usd').sum().alias('usd'), pl.col('units').sum()).collect())
    if set(local.select('source', 'account').iter_rows()) != set(remote):
        raise PublicationError("El corte de Parquet y la publicación tienen cuentas diferentes.")
    result = []
    for native in local.sort('source', 'account').to_dicts():
        actual = remote[native['source'], native['account']]
        if (actual.row_count != native['row_count'] or actual.economic_rows != native['economic_rows']
                or not all(isclose(float(actual[key] or 0), native[key] or 0, rel_tol=1e-11, abs_tol=1e-7)
                           for key in ('usd', 'units'))):
            raise PublicationError(f"No concilian los registros de {native['source']} / {native['account']}.")
        result.append({**native, 'delta_usd': float(actual.usd or 0) - (native['usd'] or 0),
                       'delta_units': float(actual.units or 0) - (native['units'] or 0)})
    return {'table': table, 'job_id': query.job_id, 'accounts': result}


def prepare_regular(pub, source_bucket, package, folder, generation, identity, current, *, staging_prefix):
    from app.master_contract_income import unassigned_income_for_release
    from app.royalty_reports.contract_identity import GUARD_ALGORITHM, unsafe_parquet_ranking_keys
    from app.royalty_scope import use_scope
    from scripts.lib.native_identity_integrity import validate_original_witnesses
    from scripts.lib.product_income import validate_index
    from scripts.load_bigquery_release import build_dashboard, build_detail
    from app.wml_job import immutable_upload

    release_id = package["release_id"]
    raw = folder / MARTS["raw"]

    def upload(path):
        bucket = pub.state.bucket
        key = f"{staging_prefix}/{identity}/{file_sha(path)}/{path.name}"
        return f"gs://{bucket.name}/{immutable_upload(bucket, key, path).name}"

    evidence = validate_original_witnesses(raw, json.loads((folder / "native_identity_proofs.json").read_text(encoding="utf-8")))
    allocation = validate_index(json.loads((folder / CONTEXT["marts/product_income_allocations.json"]).read_text(encoding="utf-8")))
    if allocation.get("source_size_bytes") != raw.stat().st_size:
        raise PublicationError("La asignación de UPC no corresponde al crudo del cierre.")
    components = {}
    jobs = {}
    for kind in ("raw", "song"):
        name = MARTS[kind]
        print(f"Cierre habitual {release_id}: cargando {kind}.", flush=True)
        components[kind], jobs[kind] = load_component(pub, source_bucket, package, folder, kind, name, upload=upload)
    reconciled = {kind: reconcile_input(pub, components[kind], folder / MARTS[kind]) for kind in ("raw", "song")} if pub.live else {}
    eligible = folder / "eligible.parquet"
    with use_scope("regular"):
        build_dashboard(folder / MARTS["eligible"], eligible, release_id)
    eligible_table, jobs["eligible"] = load_prepared(pub, eligible, "eligible", digest([pub.dataset, identity, "eligible"]), upload)
    metrics = (pl.len().alias("n"), pl.col("amount_usd").sum(), pl.col("units").sum(), pl.col("raw_rows").cast(pl.Int64).sum())
    local = pl.scan_parquet(eligible).select(*metrics).collect().row(0, named=True)
    remote = next(iter(pub.client.query(f"""
        SELECT COUNT(*) n, SUM(amount_usd) amount_usd, SUM(units) units, SUM(raw_rows) raw_rows
        FROM `{eligible_table.reference}`
    """, job_config=bigquery.QueryJobConfig(labels=pub.labels, maximum_bytes_billed=10_000_000_000)).result(timeout=180)))
    if (local["n"] != remote.n or local["raw_rows"] != remote.raw_rows
            or not all(isclose(local[key], remote[key], rel_tol=1e-11, abs_tol=1e-7) for key in ("amount_usd", "units"))):
        raise PublicationError("La base elegible del cierre no concilia en filas, importes o unidades.")
    eligible_manifest = {"release_id": release_id, "rows": eligible_table.num_rows, "native_sha256": file_sha(eligible)}
    components["eligible"] = {"source_table": str(eligible_table.reference), "source_binding": table_binding(eligible_table),
                              "manifest": eligible_manifest, "manifest_sha256": digest(eligible_manifest)}

    normalized = folder / "normalized_statement_fact.parquet"
    print(f"Cierre habitual {release_id}: reconstruyendo evidencia contractual.", flush=True)
    build_detail(raw, normalized, release_id)
    fact, jobs["contract_evidence"] = load_prepared(pub, normalized, "evidence", digest([pub.dataset, identity, "evidence"]), upload)
    if fact.num_rows != components["raw"]["source_binding"]["rows"]:
        raise PublicationError("La evidencia contractual perdió movimientos del cierre.")
    rows, associations = unassigned_income_for_release(pub.client, release_id, fact_table=str(fact.reference))
    guard = sorted(unsafe_parquet_ranking_keys(pq.ParquetFile(raw)))
    write_json(folder / "published_rows.json", rows)
    write_json(folder / "published_evidence.json", associations)
    write_json(folder / "identity_guard.json", {"published_cache_found": True, "keys": guard, "algorithm": GUARD_ALGORITHM})
    write_json(folder / "catalog_close.json", {"manifest_generation": generation, "release_id": release_id,
               "jobs": jobs, "native_witnesses": evidence, "contract_evidence_table": str(fact.reference),
               "eligible_totals": {"parquet": local, "bigquery": dict(remote), "relative_tolerance": 1e-11},
               "accounts": reconciled,
               "unassigned_groups": len(rows), "association_groups": len(associations), "guard_slots": len(guard)})
    roles = {**CONTEXT, "contracts/published_rows.json": "published_rows.json",
             "contracts/published_evidence.json": "published_evidence.json", "contracts/identity_guard.json": "identity_guard.json",
             "publication/source_manifest.json": "release_manifest.json", "publication/catalog_close.json": "catalog_close.json"}
    policy = json.loads((folder / CONTEXT["policy/policy_snapshot.json"]).read_text(encoding="utf-8"))
    if int(policy["policy_version"]) <= 0:
        raise PublicationError("El cierre carece de versión de políticas.")
    context = {"scope": "regular", "policy_version": policy["policy_version"],
               "artifacts": [{"role": role, "path": (folder / name).relative_to(pub.root).as_posix(),
                              "sha256": file_sha(folder / name)} for role, name in sorted(roles.items())]}
    parent_sequence = current["sequence"] if current is not None else 0
    release = {"scope": "regular", "source_release_id": release_id, "publication_id": identity,
               "manifest_generation": generation, "sequence": parent_sequence + 1, "context": context,
               "context_id": digest(context), "components": components}
    return pub.prepare(release)["release"]
