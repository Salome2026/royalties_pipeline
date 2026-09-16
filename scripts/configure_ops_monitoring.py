from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from urllib.parse import urlparse


API_ROOT = "https://monitoring.googleapis.com/v3"
CHANNEL_DISPLAY_NAME = "VPO operaciones"
UPTIME_DISPLAY_NAME = "VPO API readiness"


def access_token() -> str:
    executable = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not executable:
        raise RuntimeError("No se encontro gcloud en PATH.")
    result = subprocess.run(
        [executable, "auth", "print-access-token"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class MonitoringClient:
    def __init__(self, project: str) -> None:
        self.project = project
        self.parent = f"projects/{project}"
        self.token = access_token()

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{API_ROOT}/{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                content = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Monitoring API {method} {path} failed: {exc.code} {detail}") from exc
        return json.loads(content) if content else {}

    def list_items(self, collection: str, response_key: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token = ""
        while True:
            query = "?pageSize=1000"
            if page_token:
                query += f"&pageToken={urllib.parse.quote(page_token)}"
            payload = self.request("GET", f"{self.parent}/{collection}{query}")
            items.extend(payload.get(response_key, []))
            page_token = str(payload.get("nextPageToken") or "")
            if not page_token:
                return items


def metric_filter(metric_type: str, resource_type: str, *parts: str) -> str:
    expressions = [
        f'resource.type = "{resource_type}"',
        f'metric.type = "{metric_type}"',
        *parts,
    ]
    return " AND ".join(expressions)


def threshold_condition(
    *,
    display_name: str,
    filter_value: str,
    comparison: str,
    threshold: float,
    duration: str,
    aligner: str,
    reducer: str,
    alignment_period: str = "300s",
) -> dict[str, Any]:
    return {
        "displayName": display_name,
        "conditionThreshold": {
            "filter": filter_value,
            "comparison": comparison,
            "thresholdValue": threshold,
            "duration": duration,
            "aggregations": [
                {
                    "alignmentPeriod": alignment_period,
                    "perSeriesAligner": aligner,
                    "crossSeriesReducer": reducer,
                }
            ],
            "trigger": {"count": 1},
        },
    }


def alert_policy(
    display_name: str,
    summary: str,
    condition: dict[str, Any],
    channel_name: str,
) -> dict[str, Any]:
    return {
        "displayName": display_name,
        "documentation": {
            "content": summary,
            "mimeType": "text/markdown",
        },
        "combiner": "OR",
        "conditions": [condition],
        "notificationChannels": [channel_name],
        "alertStrategy": {"autoClose": "1800s"},
        "enabled": True,
        "userLabels": {"managed_by": "vpo_ops"},
    }


def desired_policies(
    *,
    service_name: str,
    job_name: str,
    check_id: str,
    channel_name: str,
) -> list[dict[str, Any]]:
    service_filter = f'resource.label.service_name = "{service_name}"'
    job_filter = f'resource.label.job_name = "{job_name}"'
    return [
        alert_policy(
            "VPO API - disponibilidad",
            "La verificacion publica de `/health/ready` dejo de responder saludable.",
            threshold_condition(
                display_name="Readiness por debajo de 100%",
                filter_value=metric_filter(
                    "monitoring.googleapis.com/uptime_check/check_passed",
                    "uptime_url",
                    f'metric.label.check_id = "{check_id}"',
                ),
                comparison="COMPARISON_LT",
                threshold=1,
                duration="120s",
                aligner="ALIGN_FRACTION_TRUE",
                reducer="REDUCE_MEAN",
                alignment_period="60s",
            ),
            channel_name,
        ),
        alert_policy(
            "VPO API - errores 5xx",
            "El API devolvio al menos un error de servidor en una ventana de cinco minutos.",
            threshold_condition(
                display_name="Errores 5xx detectados",
                filter_value=metric_filter(
                    "run.googleapis.com/request_count",
                    "cloud_run_revision",
                    service_filter,
                    'metric.label.response_code_class = "5xx"',
                ),
                comparison="COMPARISON_GT",
                threshold=0,
                duration="0s",
                aligner="ALIGN_SUM",
                reducer="REDUCE_SUM",
            ),
            channel_name,
        ),
        alert_policy(
            "VPO API - latencia p95",
            "La latencia p95 del API supero 30 segundos durante cinco minutos.",
            threshold_condition(
                display_name="p95 mayor a 30 segundos",
                filter_value=metric_filter(
                    "run.googleapis.com/request_latencies",
                    "cloud_run_revision",
                    service_filter,
                ),
                comparison="COMPARISON_GT",
                threshold=30000,
                duration="300s",
                aligner="ALIGN_PERCENTILE_95",
                reducer="REDUCE_MAX",
            ),
            channel_name,
        ),
        alert_policy(
            "VPO API - memoria",
            "La utilizacion p95 de memoria del contenedor supero 85% durante cinco minutos.",
            threshold_condition(
                display_name="Memoria mayor a 85%",
                filter_value=metric_filter(
                    "run.googleapis.com/container/memory/utilizations",
                    "cloud_run_revision",
                    service_filter,
                ),
                comparison="COMPARISON_GT",
                threshold=0.85,
                duration="300s",
                aligner="ALIGN_PERCENTILE_95",
                reducer="REDUCE_MAX",
            ),
            channel_name,
        ),
        alert_policy(
            "VPO reportes - ejecucion fallida",
            "Un Cloud Run Job de reportes termino con resultado fallido.",
            threshold_condition(
                display_name="Job fallido detectado",
                filter_value=metric_filter(
                    "run.googleapis.com/job/completed_execution_count",
                    "cloud_run_job",
                    job_filter,
                    'metric.label.result = "failed"',
                ),
                comparison="COMPARISON_GT",
                threshold=0,
                duration="0s",
                aligner="ALIGN_SUM",
                reducer="REDUCE_SUM",
            ),
            channel_name,
        ),
    ]


def ensure_channel(client: MonitoringClient, email: str) -> str:
    channels = client.list_items("notificationChannels", "notificationChannels")
    for channel in channels:
        if channel.get("type") == "email" and channel.get("labels", {}).get("email_address") == email:
            return str(channel["name"])
    payload = {
        "type": "email",
        "displayName": CHANNEL_DISPLAY_NAME,
        "description": "Alertas operativas de VPO Corp.",
        "labels": {"email_address": email},
        "enabled": True,
        "userLabels": {"managed_by": "vpo_ops"},
    }
    return str(client.request("POST", f"{client.parent}/notificationChannels", payload)["name"])


def ensure_uptime_check(client: MonitoringClient, api_url: str) -> str:
    checks = client.list_items("uptimeCheckConfigs", "uptimeCheckConfigs")
    for check in checks:
        if check.get("displayName") == UPTIME_DISPLAY_NAME:
            return str(check["name"]).rsplit("/", 1)[-1]

    parsed = urlparse(api_url)
    payload = {
        "displayName": UPTIME_DISPLAY_NAME,
        "monitoredResource": {
            "type": "uptime_url",
            "labels": {"project_id": client.project, "host": parsed.hostname},
        },
        "httpCheck": {
            "useSsl": parsed.scheme == "https",
            "path": "/health/ready",
            "port": 443 if parsed.scheme == "https" else 80,
            "validateSsl": parsed.scheme == "https",
            "requestMethod": "GET",
        },
        "period": "60s",
        "timeout": "30s",
        "contentMatchers": [
            {
                "content": json.dumps("ok"),
                "matcher": "MATCHES_JSON_PATH",
                "jsonPathMatcher": {"jsonPath": "$.status", "jsonMatcher": "EXACT_MATCH"},
            }
        ],
        "selectedRegions": ["USA", "SOUTH_AMERICA", "EUROPE"],
        "checkerType": "STATIC_IP_CHECKERS",
        "userLabels": {"managed_by": "vpo_ops"},
    }
    result = client.request("POST", f"{client.parent}/uptimeCheckConfigs", payload)
    return str(result["name"]).rsplit("/", 1)[-1]


def upsert_policy(client: MonitoringClient, payload: dict[str, Any]) -> str:
    policies = client.list_items("alertPolicies", "alertPolicies")
    existing = next((item for item in policies if item.get("displayName") == payload["displayName"]), None)
    if not existing:
        result = client.request("POST", f"{client.parent}/alertPolicies", payload)
        return f"created {result['name']}"

    name = str(existing["name"])
    update_mask = ",".join(
        [
            "displayName",
            "documentation",
            "conditions",
            "combiner",
            "enabled",
            "notificationChannels",
            "alertStrategy",
            "userLabels",
        ]
    )
    payload = {**payload, "name": name}
    client.request(
        "PATCH",
        f"{name}?updateMask={urllib.parse.quote(update_mask)}",
        payload,
    )
    return f"updated {name}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Configura los controles de Cloud Monitoring de VPO Corp.")
    parser.add_argument("--project", default="vpo-corp-royalties")
    parser.add_argument("--api-url", default="https://vpo-corp-api-259971998447.us-central1.run.app")
    parser.add_argument("--service", default="vpo-corp-api")
    parser.add_argument("--job", default="vpo-royalty-report-job")
    parser.add_argument("--email", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    names = [
        "VPO API - disponibilidad",
        "VPO API - errores 5xx",
        "VPO API - latencia p95",
        "VPO API - memoria",
        "VPO reportes - ejecucion fallida",
    ]
    if not args.apply:
        print(json.dumps({"mode": "dry-run", "email": args.email, "policies": names}, indent=2))
        return

    client = MonitoringClient(args.project)
    channel_name = ensure_channel(client, args.email)
    check_id = ensure_uptime_check(client, args.api_url)
    results = [
        upsert_policy(client, policy)
        for policy in desired_policies(
            service_name=args.service,
            job_name=args.job,
            check_id=check_id,
            channel_name=channel_name,
        )
    ]
    print(
        json.dumps(
            {
                "channel": channel_name,
                "uptime_check_id": check_id,
                "policies": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
