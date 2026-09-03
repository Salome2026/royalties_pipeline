from __future__ import annotations

import sys
from pathlib import Path

from google.auth.credentials import Signing


BASE = Path(__file__).resolve().parents[2]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from app.royalty_reports.delivery import create_signed_download_url, parse_gcs_uri  # noqa: E402
from app.royalty_reports.launcher import CloudRunReportJobLauncher  # noqa: E402
from app.royalty_reports.manifests import (  # noqa: E402
    REPORT_INPUT_FILENAMES,
    build_gcs_input_manifest,
)


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"name": "projects/p/locations/r/operations/op-1"}


class FakeSession:
    def __init__(self) -> None:
        self.request: dict | None = None

    def post(self, url: str, **kwargs) -> FakeResponse:
        self.request = {"url": url, **kwargs}
        return FakeResponse()


class FakeSigningCredentials(Signing):
    @property
    def signer_email(self) -> str:
        return "api@example.iam.gserviceaccount.com"

    @property
    def signer(self):
        return self

    def sign_bytes(self, message: bytes) -> bytes:
        return b"signature"


class FakeBlob:
    def __init__(self, name: str, *, generation: int = 11, size: int = 25) -> None:
        self.name = name
        self.generation = generation
        self.size = size
        self.crc32c = "crc32c"
        self.updated = None
        self.signed_options: dict | None = None

    def reload(self, client) -> None:
        return None

    def generate_signed_url(self, **kwargs) -> str:
        self.signed_options = kwargs
        return "https://storage.googleapis.com/bucket/report.xlsx?signed=1"


class FakeBucket:
    def __init__(self) -> None:
        self.blobs: dict[str, FakeBlob] = {}

    def blob(self, name: str, generation: int | None = None) -> FakeBlob:
        return self.blobs.setdefault(name, FakeBlob(name, generation=generation or 11))


class FakeStorageClient:
    def __init__(self) -> None:
        self._credentials = FakeSigningCredentials()
        self._bucket = FakeBucket()

    def bucket(self, name: str) -> FakeBucket:
        return self._bucket

    def list_blobs(self, bucket_name: str, prefix: str | None = None):
        return [FakeBlob(f"marts/{filename}") for filename in REPORT_INPUT_FILENAMES]


def main() -> None:
    session = FakeSession()
    scopes: list[str] = []

    def credentials_provider(*, scopes: list[str]):
        return object(), "p"

    launcher = CloudRunReportJobLauncher(
        project="p",
        location="r",
        job_name="job",
        credentials_provider=credentials_provider,
        session_factory=lambda credentials: session,
    )
    operation = launcher.run(42)
    if operation != "projects/p/locations/r/operations/op-1":
        raise AssertionError("No se conservo la operacion de Cloud Run.")
    expected_url = "https://run.googleapis.com/v2/projects/p/locations/r/jobs/job:run"
    if session.request is None or session.request["url"] != expected_url:
        raise AssertionError("El lanzador no apunto al Job configurado.")
    override = session.request["json"]["overrides"]["containerOverrides"][0]
    if override["env"] != [{"name": "VPO_REPORT_RUN_ID", "value": "42"}]:
        raise AssertionError("El Job debe recibir solamente report_run_id.")

    client = FakeStorageClient()
    manifest = build_gcs_input_manifest(
        client=client,
        bucket_name="bucket",
        prefix="marts",
    )
    if set(manifest["objects"]) != set(REPORT_INPUT_FILENAMES):
        raise AssertionError("El manifiesto no congelo todas las entradas requeridas.")
    if any(item["generation"] != 11 for item in manifest["objects"].values()):
        raise AssertionError("El manifiesto no congelo generaciones GCS.")

    if parse_gcs_uri("gs://bucket/reports/42/report.xlsx") != (
        "bucket",
        "reports/42/report.xlsx",
    ):
        raise AssertionError("La URI GCS no se interpreto correctamente.")
    signed_url = create_signed_download_url(
        client=client,
        output_uri="gs://bucket/reports/42/report.xlsx",
        filename="report.xlsx",
        expiration_minutes=10,
    )
    if not signed_url.startswith("https://storage.googleapis.com/"):
        raise AssertionError("La descarga no se entrega directamente desde GCS.")

    print("OK: manifiesto, lanzamiento del Job y descarga directa cumplen el contrato.")


if __name__ == "__main__":
    main()
