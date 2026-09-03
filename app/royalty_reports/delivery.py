from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import google.auth
from google.auth.credentials import Signing
from google.auth.transport.requests import Request
from google.cloud import storage


CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def parse_gcs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError("El reporte no tiene un archivo GCS valido.")
    bucket_name, separator, object_name = uri[5:].partition("/")
    if not separator or not bucket_name or not object_name:
        raise ValueError("La ubicacion GCS del reporte es invalida.")
    return bucket_name, object_name


def create_signed_download_url(
    *,
    client: storage.Client,
    output_uri: str,
    filename: str,
    expiration_minutes: int,
    signer_service_account: str | None = None,
) -> str:
    bucket_name, object_name = parse_gcs_uri(output_uri)
    blob = client.bucket(bucket_name).blob(object_name)
    blob.reload(client)
    if not blob.generation:
        raise FileNotFoundError("El archivo del reporte ya no esta disponible.")

    credentials: Any = client._credentials
    if not isinstance(credentials, Signing):
        credentials, _ = google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
    signing_options: dict[str, Any] = {"credentials": credentials}
    if not isinstance(credentials, Signing):
        signer = (signer_service_account or "").strip()
        if not signer:
            raise RuntimeError("No esta configurada la identidad que firma descargas.")
        credentials.refresh(Request())
        signing_options.update(
            service_account_email=signer,
            access_token=credentials.token,
        )

    safe_filename = Path(filename).name.replace('"', "")
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=max(1, min(expiration_minutes, 60))),
        method="GET",
        response_disposition=f'attachment; filename="{safe_filename}"',
        generation=blob.generation,
        **signing_options,
    )
