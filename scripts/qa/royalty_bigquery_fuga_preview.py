"""Publish and verify the isolated FUGA statement in the regular report scope."""

import argparse
import base64
import hashlib
import json
from math import isclose
from pathlib import Path
import shutil
import sys

from google.api_core.exceptions import NotFound
from google.cloud import bigquery, storage
from openpyxl import load_workbook
import polars as pl
import psycopg

from app.royalty_reports.bigquery_backend.publication import LABELS, digest, file_sha, read_json, table_binding, write_json
from scripts.lib.mart_release import publish_mart_release, validate_release_manifest
from scripts.qa.royalty_bigquery_app_preview import (
    CONFIG, DEPENDENCIES, FUGA_SCENARIO, PGDATA, PROJECT, RUNTIME, LocalCloudCredentials, cloud_publications,
)
from scripts.qa.royalty_bigquery_ingest_compare import compare_native_movements, compare_workbooks
from scripts.qa.royalty_bigquery_ingest_preview import load_component


BUCKET = f"{PROJECT}-fuga-ingest-test-20261111"
STATEMENT_UPC = "00655857944443"
ALBUM_SALE = "18477552999"
TRACK = "ES71G1921229"
MARTS = ("standardized_raw_all_sources.parquet", "song_level_all_sources.parquet", "catalog_master.parquet",
         "statement_summary_all_sources.parquet", "digital_income_statement_summary.parquet",
         "royalties_dashboard_summary.parquet", "product_income_allocations.json", "catalog_status.parquet",
         "catalog_release_metadata.parquet", "catalog_ingestion_controls.parquet", "native_identity_proofs.json")


def checked_bucket():
    bucket = storage.Client(project=PROJECT, credentials=LocalCloudCredentials()).get_bucket(BUCKET)
    if (bucket.location != "US" or bucket.labels != LABELS
            or not bucket.iam_configuration.uniform_bucket_level_access_enabled
            or bucket.iam_configuration.public_access_prevention != "enforced"):
        raise ValueError("El bucket no corresponde a la prueba aislada de FUGA.")
    return bucket


def native_package(bucket, directory, release_id):
    manifest = bucket.get_blob("marts/release_manifest.json")
    if manifest is None:
        package = publish_mart_release(bucket, "marts", [(name, directory / name) for name in MARTS],
                                       release_id=release_id)
    else:
        package = json.loads(manifest.download_as_text(if_generation_match=manifest.generation))
        package["manifest_generation"] = str(manifest.generation)
        package["manifest_object_name"] = manifest.name
    validate_release_manifest(package, MARTS)
    assert package["release_id"] == release_id
    for name, entry in package["files"].items():
        assert entry["object_name"] == f"marts/releases/{release_id}/{name}"
        blob = bucket.get_blob(entry["object_name"], generation=int(entry["generation"]))
        with (directory / name).open("rb") as stream:
            checksum = base64.b64encode(hashlib.file_digest(stream, "md5").digest()).decode("ascii")
        assert blob.md5_hash == entry["md5_hash"] == checksum and blob.size == entry["size_bytes"]
    return package


def load_eligible(publications, directory, release_id):
    from scripts.load_bigquery_release import build_dashboard

    source = directory / "royalties_dashboard_summary.parquet"
    identity = digest({"release": release_id, "sha256": file_sha(source)})[:24]
    destination = f"{publications.dataset}.ingest_eligible_{identity}"
    job_id = f"report_fuga_load_eligible_{identity}"
    encoded = RUNTIME / "eligible.parquet"
    if not encoded.exists():
        build_dashboard(source, encoded, release_id)
    client = publications.client
    try:
        job = client.get_job(job_id, location="US")
    except NotFound:
        config = bigquery.LoadJobConfig(source_format="PARQUET", write_disposition="WRITE_EMPTY", labels=LABELS)
        with encoded.open("rb") as stream:
            job = client.load_table_from_file(stream, destination, job_id=job_id, job_config=config, location="US")
    assert job.job_type == "load" and str(job.destination) == destination
    job.result(timeout=900)
    table = client.get_table(destination)
    fields = ["amount_usd", "units", "raw_rows"]
    native = pl.scan_parquet(encoded).select(pl.len().alias("rows"), *[pl.col(f).sum() for f in fields]).collect().row(0, named=True)
    observed = next(iter(client.query(
        f"SELECT COUNT(*) AS `rows`, SUM(amount_usd) amount_usd, SUM(units) units, SUM(raw_rows) raw_rows FROM `{destination}`",
        job_config=bigquery.QueryJobConfig(labels=LABELS),
    ).result()))
    assert table.num_rows == observed.rows == native["rows"]
    assert all(isclose(observed[f], native[f], rel_tol=1e-12, abs_tol=1e-9) for f in fields)
    if table.labels != {**LABELS, "role": "eligible"}:
        table.labels = {**LABELS, "role": "eligible"}
        table = client.update_table(table, ["labels"])
    manifest = {"release_id": release_id, "native_sha256": file_sha(source), "rows": table.num_rows}
    return {"source_table": destination, "source_binding": table_binding(table), "manifest": manifest,
            "manifest_sha256": digest(manifest)}, job_id


def publish():
    arrival = read_json(RUNTIME / "arrival.json")
    receipt = read_json(RUNTIME / "candidate/native_receipt.json")
    assert receipt["package_validation"]["ok"] and receipt["input_sha256"] == arrival["sha256"]
    marts = Path(receipt["marts"]).resolve()
    assert marts == RUNTIME / "candidate/warehouse/marts"
    bucket = checked_bucket()
    assert arrival["bucket"] == bucket.name
    incoming = bucket.get_blob(arrival["object_name"], generation=int(arrival["generation"]))
    assert incoming.metadata["sha256"] == receipt["input_sha256"]
    release_id = f"fuga-{arrival['sha256'][:24]}"
    publication_id = release_id.replace("-", "_")
    package = native_package(bucket, marts, release_id)
    folder = RUNTIME / "contexts" / release_id
    folder.mkdir(parents=True, exist_ok=True)
    for name in MARTS:
        shutil.copyfile(marts / name, folder / name)
    shutil.copyfile(RUNTIME / "source_context/policy_snapshot.json", folder / "policy_snapshot.json")
    write_json(folder / "release_manifest.json", package)
    write_json(folder / "statement_arrival.json", arrival)
    publications = cloud_publications()
    publications.initialize()
    components, jobs = {}, {}
    for kind, name in (("raw", MARTS[0]), ("song", MARTS[1])):
        components[kind], jobs[kind] = load_component(publications, bucket, package, folder, kind, name)
    components["eligible"], jobs["eligible"] = load_eligible(publications, folder, release_id)
    assert components["raw"]["source_binding"]["rows"] == receipt["metrics"]["rows"]
    roles = {f"marts/{name}": name for name in MARTS} | {
        "publication/source_manifest.json": "release_manifest.json",
        "publication/statement_arrival.json": "statement_arrival.json",
        "policy/policy_snapshot.json": "policy_snapshot.json",
    }
    context = {"scope": "regular", "policy_version": read_json(folder / "policy_snapshot.json")["policy_version"],
               "artifacts": [{"role": role, "path": (folder / name).relative_to(RUNTIME).as_posix(),
                              "sha256": file_sha(folder / name)} for role, name in sorted(roles.items())]}
    release = {"scope": "regular", "publication_id": publication_id, "source_release_id": release_id,
               "sequence": 1, "manifest_generation": int(package["manifest_generation"]),
               "context": context, "context_id": digest(context), "components": components}
    publications.validate(release)
    write_json(RUNTIME / "incoming" / f"{publication_id}.json", release)
    write_json(RUNTIME / "fuga_publication.json", {"publication_id": publication_id, "release": release_id,
               "input_sha256": arrival["sha256"], "raw_rows": receipt["metrics"]["rows"], "jobs": jobs,
               "package_generation": package["manifest_generation"]})
    print("Paquete de FUGA conciliado, entregado al publicador de reportes.", flush=True)


def selected_rows(path):
    book = load_workbook(path, read_only=True)
    try:
        rows = iter(book["detalle"].values)
        header = next(rows)
        fields = [header.index(name) for name in ("ISRC", "Unidades", "Ingresos USD")]
        return [tuple(row[i] for i in fields) for row in rows
                if isinstance(row[fields[1]], (int, float)) and isclose(row[fields[1]], 1 / 14, rel_tol=1e-13)]
    finally:
        book.close()


def roundtrip():
    sys.path.insert(0, str(DEPENDENCIES / "python"))
    from app.royalty_reports.bigquery_backend.reader import read_source
    from scripts import build_keyword_royalty_report

    receipt = read_json(RUNTIME / "fuga_publication.json")
    publications = cloud_publications()
    release = publications.checked(publications.pin("regular"))
    assert release["publication_id"] == receipt["publication_id"]
    params = {"keywords": [], "mode": "any", "period_basis": "statement_period", "start_month": "2024-12",
              "end_month": "2024-12", "source": "fuga", "account": "indyana_records"}
    original = RUNTIME / "contexts" / release["source_release_id"] / MARTS[0]
    directory = RUNTIME / "bigquery_roundtrip"
    downloaded = read_source(publications, release, "raw", params, build_keyword_royalty_report, directory)
    comparison = compare_native_movements(original, downloaded)
    assert comparison["rows"] == receipt["raw_rows"]
    write_json(directory / "comparison.json", comparison | {"actual_read": read_json(directory / "raw_read.json")})
    print("Valores de origen completos recuperados desde BigQuery", comparison, flush=True)


def compare():
    prior = read_json(RUNTIME / "current_system/native_receipt.json")
    candidate = read_json(RUNTIME / "candidate/native_receipt.json")
    published = read_json(RUNTIME / "fuga_publication.json")
    assert prior["input_sha256"] == candidate["input_sha256"] == published["input_sha256"]
    pin = published["publication_id"]
    assert read_json(RUNTIME / "active/regular.json")["id"] == pin
    accepted = read_json(RUNTIME / "publication_status" / f"{pin}.json")
    assert accepted["status"] == "ready" and set(accepted["tables"]) == {"raw", "song", "eligible"}
    assert read_json(RUNTIME / "before_activation.json")["report_publication_active"] is False
    marts = RUNTIME / "contexts" / published["release"]
    native = compare_native_movements(Path(prior["marts"]) / MARTS[0], marts / MARTS[0],
                                     exclude=("statement_file_path", "ingested_at"))
    assert native["rows"] == published["raw_rows"]
    assert accepted["tables"]["raw"]["binding"]["rows"] == published["raw_rows"]
    allocation = read_json(marts / "product_income_allocations.json")["products"][f"UPC:{STATEMENT_UPC}"]
    expected_tracks = {t["isrc"] for t in allocation["tracks"]}
    assert allocation["status"] == "validated" and len(expected_tracks) == 14
    fact = pl.scan_parquet(marts / MARTS[0]).filter(pl.col("sale_id") == ALBUM_SALE).collect()
    assert fact.height == 1 and fact["asset_isrc"][0] is None and fact["product_quantity_num"][0] == 1
    raw_usd = fact["amount_usd"][0]
    policy = read_json(marts / "policy_snapshot.json")
    entry = next(item for item in policy["entries"]
                 if item["source"] == "fuga" and item["account"] == "indyana_records")
    adjustment = entry["report_net_adjustment_pct"] if policy["report_personalization"]["enabled"] else 0
    report_usd = raw_usd * (1 - adjustment / 100)
    config = read_json(CONFIG)
    cases = {}
    for case, baseline in prior["reports"].items():
        path = RUNTIME / "browser" / case
        browser = read_json(path / "acceptance.json")
        terminal = read_json(path / "terminal.json")
        assert terminal["engine_version"] == "bigquery" and terminal["status"] == "completed"
        assert all(terminal["params"][k] == v for k, v in baseline["params"].items() if k != "keywords")
        assert [k.casefold() for k in terminal["params"]["keywords"]] == [k.casefold() for k in baseline["params"]["keywords"]]
        with psycopg.connect(host="127.0.0.1", port=config["pg_port"], user="report_preview",
                             password=config["pg_password"], dbname="postgres") as db:
            assert Path(db.execute("SHOW data_directory").fetchone()[0]).resolve() == PGDATA.resolve()
            pinned = db.execute("SELECT input_manifest_json #>> '{report_publication,publication_id}' FROM report_runs WHERE id=%s",
                                (browser["job"],)).fetchone()[0]
        assert pinned == pin
        base = Path(baseline["xlsx"])
        assert file_sha(base) == baseline["sha256"]
        book = Path(browser["automatic_downloads"][0]["path"])
        compared = compare_workbooks(base, book, allow_rounded_units=True, allow_rounding_widths=True)
        portion = selected_rows(book)
        required = expected_tracks if case.endswith("-upc") else {TRACK}
        assert len(portion) == len(required) and {row[0] for row in portion} == required
        assert all(isclose(row[2], report_usd / 14, rel_tol=1e-12, abs_tol=1e-12) for row in portion)
        cases[case] = {"job": browser["job"], "comparison": compared, "distributed_rows": len(portion),
                       "distributed_usd": sum(row[2] for row in portion), "distributed_units": sum(row[1] for row in portion),
                       "browser_excel": str(book), "legacy_excel": str(base)}
    result = {"publication": pin, "raw_rows": published["raw_rows"], "native_ingest": native, "album_movement_usd": raw_usd,
              "album_movement_eur": fact["net_amount_eur"][0], "album_report_usd": report_usd, "cases": cases}
    write_json(RUNTIME / "fuga_report_comparison.json", result)
    assert all(c["comparison"]["passed"] for c in cases.values()), "El Excel difiere. Revisar la comparación por hoja."
    print("Excel FUGA verificados desde la pantalla", [(k, v["distributed_rows"]) for k, v in cases.items()])


if __name__ == "__main__":
    if not FUGA_SCENARIO:
        raise RuntimeError("Este comando requiere el escenario aislado de FUGA.")
    parser = argparse.ArgumentParser()
    commands = {"publish": publish, "compare": compare, "roundtrip": roundtrip}
    parser.add_argument("action", choices=commands)
    args = parser.parse_args()
    commands[args.action]()
