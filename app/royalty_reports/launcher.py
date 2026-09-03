from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

import google.auth
from google.auth.transport.requests import AuthorizedSession


CredentialsProvider = Callable[..., tuple[Any, str | None]]
SessionFactory = Callable[[Any], AuthorizedSession]


@dataclass(frozen=True)
class CloudRunReportJobLauncher:
    project: str
    location: str
    job_name: str
    credentials_provider: CredentialsProvider = google.auth.default
    session_factory: SessionFactory = AuthorizedSession

    @classmethod
    def from_environment(cls) -> "CloudRunReportJobLauncher":
        project = os.environ.get("VPO_REPORT_JOB_PROJECT", "").strip()
        location = os.environ.get("VPO_REPORT_JOB_LOCATION", "").strip()
        job_name = os.environ.get("VPO_REPORT_JOB_NAME", "").strip()
        if not project or not location or not job_name:
            raise RuntimeError("El Cloud Run Job de reportes no esta configurado.")
        return cls(project=project, location=location, job_name=job_name)

    def run(self, report_run_id: int) -> str:
        if report_run_id <= 0:
            raise ValueError("report_run_id debe ser positivo.")
        credentials, _ = self.credentials_provider(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        session = self.session_factory(credentials)
        resource = (
            f"projects/{self.project}/locations/{self.location}/jobs/{self.job_name}"
        )
        response = session.post(
            f"https://run.googleapis.com/v2/{resource}:run",
            json={
                "overrides": {
                    "containerOverrides": [
                        {
                            "env": [
                                {
                                    "name": "VPO_REPORT_RUN_ID",
                                    "value": str(report_run_id),
                                }
                            ]
                        }
                    ]
                }
            },
            timeout=30,
        )
        response.raise_for_status()
        operation_name = str(response.json().get("name") or "").strip()
        if not operation_name:
            raise RuntimeError("Cloud Run no devolvio la operacion del reporte.")
        return operation_name
