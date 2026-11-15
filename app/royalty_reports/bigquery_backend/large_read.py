"""Stage large query results as compressed Parquet in the isolated bucket."""

from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pyarrow.parquet as pq
from google.cloud import bigquery, storage

from .publication import LABELS, LIVE_BUCKET, LIVE_LABELS, PROJECT, PublicationError


BUCKET_PREFIXES = ("vpo-corp-royalties-report-app-test-", "vpo-corp-royalties-report-ops-test-")
MIN_EXPORT_ROWS = 500_000
LOGGER = logging.getLogger(__name__)


def parquet_batches(client, table, bucket_name, folder):
    if client.project != PROJECT or not (bucket_name == LIVE_BUCKET or bucket_name.startswith(BUCKET_PREFIXES)):
        raise PublicationError("La lectura temporal requiere un bucket de reportes autorizado.")
    storage_client = storage.Client(project=PROJECT, credentials=client._credentials)
    bucket = storage_client.get_bucket(bucket_name)
    labels = LIVE_LABELS if bucket_name == LIVE_BUCKET else LABELS
    if (bucket.location != "US" or any(bucket.labels.get(key) != value for key, value in labels.items())
            or not bucket.iam_configuration.uniform_bucket_level_access_enabled
            or bucket.iam_configuration.public_access_prevention != "enforced"):
        raise PublicationError("El destino temporal no corresponde a la publicación de regalías.")
    prefix = f"query-results/{uuid4().hex}/part-"
    export = client.extract_table(
        table, f"gs://{bucket.name}/{prefix}*.parquet", location="US",
        job_config=bigquery.ExtractJobConfig(destination_format="PARQUET", compression="SNAPPY"),
    )
    export.result(timeout=900)
    blobs = sorted(bucket.list_blobs(prefix=prefix), key=lambda blob: blob.name)
    if not blobs or len(blobs) != sum(export.destination_uri_file_counts or []):
        raise PublicationError("La exportación temporal no contiene todas sus partes.")

    def fetch(blob, destination):
        blob.download_to_filename(destination, if_generation_match=blob.generation, timeout=180)
        with pq.ParquetFile(destination) as parquet:
            index = parquet.schema.names.index("_origin_position")
            lower = min(parquet.metadata.row_group(i).column(index).statistics.min
                        for i in range(parquet.num_row_groups))
        return lower, destination

    try:
        with TemporaryDirectory(dir=folder) as temp, ThreadPoolExecutor(max_workers=4) as pool:
            pending = [pool.submit(fetch, blob, Path(temp) / f"{i:05}.parquet")
                       for i, blob in enumerate(blobs)]
            for _, part in sorted(future.result() for future in pending):
                with pq.ParquetFile(part) as parquet:
                    yield from parquet.iter_batches(batch_size=16_384, use_threads=False)
    finally:
        for blob in blobs:
            try:
                blob.delete(if_generation_match=blob.generation, timeout=30)
            except Exception:
                # The isolated bucket also has a lifecycle rule for abandoned objects.
                LOGGER.exception("No se retiró una parte temporal de la exportación")
