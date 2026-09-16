from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
API_URL = os.environ.get(
    "VPO_DASHBOARD_QA_URL",
    "https://vpo-corp-api-32v4t5iawa-uc.a.run.app",
).rstrip("/")
CASES = [
    ("A_6m", {"period_basis": "statement_period", "period_mode": "last_6_months", "limit": 10}),
    (
        "B_2026_09",
        {
            "period_basis": "statement_period",
            "period_mode": "single_month",
            "start_month": "2026-09",
            "end_month": "2026-09",
            "limit": 10,
        },
    ),
    (
        "C_fuga_6m",
        {"period_basis": "statement_period", "period_mode": "last_6_months", "source": "fuga", "limit": 10},
    ),
    (
        "D_empty",
        {
            "period_basis": "statement_period",
            "period_mode": "closed_range",
            "start_month": "2027-01",
            "end_month": "2027-01",
            "limit": 3,
        },
    ),
    (
        "E_transaction_2026_07",
        {
            "period_basis": "transaction_month",
            "period_mode": "single_month",
            "start_month": "2026-07",
            "end_month": "2026-07",
            "limit": 3,
        },
    ),
    (
        "F_ada_2026_06",
        {
            "period_basis": "statement_period",
            "period_mode": "single_month",
            "start_month": "2026-06",
            "end_month": "2026-06",
            "source": "ada",
            "limit": 3,
        },
    ),
    (
        "G_isrc_search",
        {
            "period_basis": "statement_period",
            "period_mode": "all",
            "keyword": "ARDL12600043",
            "limit": 10,
        },
    ),
    (
        "H_ada_indyana_2026_06",
        {
            "period_basis": "statement_period",
            "period_mode": "single_month",
            "start_month": "2026-06",
            "end_month": "2026-06",
            "source": "ada",
            "account": "indyana_records",
            "limit": 10,
        },
    ),
]


def api_key() -> str:
    for line in (ROOT / "web" / ".env.local").read_text(encoding="utf-8").splitlines():
        if line.startswith("VPO_API_KEY="):
            return line.partition("=")[2].strip().strip('"')
    raise RuntimeError("VPO_API_KEY is not configured in web/.env.local")


def first_difference(left: object, right: object, path: str = "") -> str | None:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return None if left == right else f"{path}: {left!r} != {right!r}"
    if type(left) is not type(right):
        return f"{path}: type {type(left).__name__} != {type(right).__name__}"
    if isinstance(left, dict):
        if left.keys() != right.keys():
            return f"{path}: keys {sorted(left.keys())} != {sorted(right.keys())}"
        for key in left:
            difference = first_difference(left[key], right[key], f"{path}.{key}")
            if difference:
                return difference
    elif isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: length {len(left)} != {len(right)}"
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            difference = first_difference(left_item, right_item, f"{path}[{index}]")
            if difference:
                return difference
    elif left != right:
        return f"{path}: {left!r} != {right!r}"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Compara el dashboard Parquet con BigQuery.")
    parser.add_argument("--shadow-endpoint", action="store_true")
    parser.add_argument("--reference-url", default=API_URL)
    parser.add_argument("--candidate-url")
    parser.add_argument("--evidence-path")
    args = parser.parse_args()
    from scripts.load_bigquery_release import ENV_PATH, load_local_env

    load_local_env(ENV_PATH)
    from app.bigquery_dashboard import royalties_dashboard_bigquery

    session = requests.Session()
    session.headers.update({"x-vpo-api-key": api_key()})
    reference_url = args.reference_url.rstrip("/")
    candidate_url = args.candidate_url.rstrip("/") if args.candidate_url else None
    policy = None
    if candidate_url is None and not args.shadow_endpoint:
        policy_response = session.get(f"{reference_url}/config/distributor-account-policies", timeout=30)
        policy_response.raise_for_status()
        policy = policy_response.json()

    selected = set(filter(None, os.environ.get("VPO_DASHBOARD_QA_CASES", "").split(",")))
    use_shadow_endpoint = args.shadow_endpoint or os.environ.get("VPO_DASHBOARD_QA_USE_SHADOW_ENDPOINT", "0") == "1"
    evidence = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "reference_url": reference_url,
        "candidate_url": candidate_url,
        "cases": [],
    }
    for name, params in CASES:
        if selected and name not in selected:
            continue
        reference_started = time.perf_counter()
        expected_response = session.get(f"{reference_url}/royalties-dashboard", params=params, timeout=180)
        expected_response.raise_for_status()
        expected = expected_response.json()
        reference_seconds = time.perf_counter() - reference_started
        started = time.perf_counter()
        candidate_backend = "local-bigquery"
        if candidate_url:
            actual_response = session.get(
                f"{candidate_url}/royalties-dashboard",
                params=params,
                timeout=180,
            )
            actual_response.raise_for_status()
            actual = actual_response.json()
            candidate_backend = actual_response.headers.get("X-VPO-Dashboard-Backend", "missing")
            if candidate_backend != "bigquery":
                raise AssertionError(f"{name}: backend canario inesperado: {candidate_backend}")
        elif use_shadow_endpoint:
            actual_response = session.get(
                f"{reference_url}/royalties-dashboard/bigquery-shadow",
                params=params,
                timeout=180,
            )
            actual_response.raise_for_status()
            actual = actual_response.json()
            candidate_backend = "bigquery-shadow"
        else:
            assert policy is not None
            actual = royalties_dashboard_bigquery(policy_document=policy, **params)
        seconds = time.perf_counter() - started
        difference = first_difference(expected, actual)
        if difference:
            raise AssertionError(f"{name}: {difference}")
        evidence["cases"].append(
            {
                "case": name,
                "equivalent": True,
                "reference_seconds": round(reference_seconds, 3),
                "candidate_seconds": round(seconds, 3),
                "candidate_backend": candidate_backend,
                "amount_usd": actual["totals"]["amount_usd"],
            }
        )
        print(
            f"CASE={name} EQUIVALENT=1 REFERENCE_SECONDS={reference_seconds:.2f} "
            f"BIGQUERY_SECONDS={seconds:.2f} BACKEND={candidate_backend} "
            f"USD={actual['totals']['amount_usd']}",
            flush=True,
        )
    if args.evidence_path:
        evidence_path = Path(args.evidence_path)
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
        print(f"EVIDENCE={evidence_path}", flush=True)


if __name__ == "__main__":
    main()
