"""Connect the versioned report backend to the API and Cloud Run worker."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from google.api_core.exceptions import GoogleAPICallError
from google.cloud import bigquery, storage
from psycopg import OperationalError

from .publication import PublicationError
from .shared_state import SharedReportPublications, SharedReportState


PILOT_CONFIG = "routing/pilot.json"


def configured() -> bool:
    return bool(os.getenv("VPO_REPORT_PUBLICATION_NAMESPACE", "").strip())


def pilot_formats(config, username: str, scope: str) -> tuple[str, ...]:
    if not isinstance(config, dict) or config.get("mode") != "pilot" or not username:
        return ()
    users, scopes, formats = (config.get(key) for key in ("users", "scopes", "formats"))
    if not all(isinstance(items, list) and all(isinstance(item, str) for item in items)
               for items in (users, scopes, formats)):
        return ()
    if username.casefold() not in {user.casefold() for user in users} or scope not in scopes:
        return ()
    return tuple(output for output in ("excel", "executive_pdf", "google_sheet") if output in formats)


def pilot_includes(config, username: str, scope: str, output: str | None) -> bool:
    formats = pilot_formats(config, username, scope)
    return bool(formats) if output is None else output in formats


@lru_cache(maxsize=1)
def publications() -> SharedReportPublications:
    project = os.environ["VPO_BIGQUERY_PROJECT"]
    location = os.getenv("VPO_BIGQUERY_LOCATION", "US")
    profile = os.getenv("VPO_REPORT_PUBLICATION_PROFILE", "preview")
    if profile not in {"preview", "live"}:
        raise ValueError("Perfil de publicación de regalías inválido.")
    live = profile == "live"
    bucket = os.environ["VPO_REPORT_PUBLICATION_BUCKET"] if live else os.environ["GCS_BUCKET"]
    dataset = os.environ["VPO_REPORT_PUBLICATION_DATASET"] if live else os.environ["VPO_BIGQUERY_DATASET"]
    state = SharedReportState(storage.Client(project=project), bucket,
                              os.environ["VPO_REPORT_PUBLICATION_NAMESPACE"], live=live)
    published = SharedReportPublications(bigquery.Client(project=project, location=location),
                                         Path("/tmp/vpo-report/publications"), dataset, state)
    if live:
        published.check_dataset(published.client.get_dataset(published.dataset))
    return published


def available_formats(state: SharedReportState, username: str, scope: str) -> tuple[str, ...]:
    try:
        formats = pilot_formats(state.read(PILOT_CONFIG), username, scope)
        if formats and state.live:
            from .live_publication import matches_current_cut

            if scope != "regular" or not matches_current_cut(state):
                return ()
        return formats
    except (GoogleAPICallError, OperationalError, PublicationError, ValueError):
        logging.warning("No se pudo leer el control del piloto. El pedido nuevo usará Parquet.", exc_info=True)
        return ()


def api_backend():
    from app.royalty_reports.launcher import CloudRunReportJobLauncher
    from app.royalty_reports.reconciliation import reconcile_report_job_if_stale
    from .runtime import BigQueryReportBackend

    published = publications()
    return BigQueryReportBackend(
        published, shared_state=published.state, watch_inbox=False,
        dispatch_job=CloudRunReportJobLauncher.from_environment().run,
        reconcile_job=reconcile_report_job_if_stale, live_contracts=True,
    )


def build_pinned(request, job):
    from .runtime import BigQueryReportBackend

    published = publications()
    return BigQueryReportBackend(published, shared_state=published.state, watch_inbox=False,
                                 export_bucket=published.state.bucket.name).build(request, job)
