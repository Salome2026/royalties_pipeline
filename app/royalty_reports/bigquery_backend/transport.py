"""Read Arrow batches with the transport allowed for this worker."""

import os

from google.cloud.bigquery_storage_v1 import BigQueryReadClient


def use_storage_read_api() -> bool:
    return os.environ.get("VPO_REPORT_BQ_USE_STORAGE_READ", "1") == "1"


def arrow_batches(result, credentials):
    if not use_storage_read_api():
        yield from result.to_arrow_iterable()
        return
    storage = BigQueryReadClient(credentials=credentials)
    try:
        yield from result.to_arrow_iterable(bqstorage_client=storage, max_queue_size=1, max_stream_count=1)
    finally:
        storage.transport.close()
