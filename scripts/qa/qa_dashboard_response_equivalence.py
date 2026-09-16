from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys
import time

import requests
from fastapi import Response

from app import vpo_corp_api as api
from lib.distributor_policy_store import use_distributor_policy_snapshot


BASE = Path(__file__).resolve().parents[2]
SUMMARY = BASE / "warehouse" / "marts" / "royalties_dashboard_summary.parquet"
API_URL = os.environ.get(
    "VPO_DASHBOARD_QA_URL",
    "https://vpo-corp-api-32v4t5iawa-uc.a.run.app",
).rstrip("/")
CASES = [
    ("A_6m", {"period_basis": "statement_period", "period_mode": "last_6_months", "limit": 10}),
    ("B_2026_09", {
        "period_basis": "statement_period",
        "period_mode": "single_month",
        "start_month": "2026-09",
        "end_month": "2026-09",
        "limit": 10,
    }),
    ("C_fuga_6m", {
        "period_basis": "statement_period",
        "period_mode": "last_6_months",
        "source": "fuga",
        "limit": 10,
    }),
    ("D_empty", {
        "period_basis": "statement_period",
        "period_mode": "closed_range",
        "start_month": "2027-01",
        "end_month": "2027-01",
        "limit": 3,
    }),
    ("E_transaction_2026_07", {
        "period_basis": "transaction_month",
        "period_mode": "single_month",
        "start_month": "2026-07",
        "end_month": "2026-07",
        "limit": 3,
    }),
    ("F_ada_2026_06", {
        "period_basis": "statement_period",
        "period_mode": "single_month",
        "start_month": "2026-06",
        "end_month": "2026-06",
        "source": "ada",
        "limit": 3,
    }),
]


class ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("page_fault_count", ctypes.c_ulong),
        ("peak_working_set_size", ctypes.c_size_t),
        ("working_set_size", ctypes.c_size_t),
        ("quota_peak_paged_pool_usage", ctypes.c_size_t),
        ("quota_paged_pool_usage", ctypes.c_size_t),
        ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
        ("quota_non_paged_pool_usage", ctypes.c_size_t),
        ("pagefile_usage", ctypes.c_size_t),
        ("peak_pagefile_usage", ctypes.c_size_t),
    ]


def peak_working_set_mb() -> float:
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    if not psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        raise OSError(ctypes.get_last_error())
    return counters.peak_working_set_size / 1024 / 1024


def api_key() -> str:
    for line in (BASE / "web" / ".env.local").read_text(encoding="utf-8").splitlines():
        if line.startswith("VPO_API_KEY="):
            return line.partition("=")[2].strip().strip('"')
    raise RuntimeError("VPO_API_KEY is not configured in web/.env.local")


def first_difference(left: object, right: object, path: str = "") -> str | None:
    if type(left) is not type(right):
        if isinstance(left, (float, int)) and isinstance(right, (float, int)) and left == right:
            return None
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
    if not SUMMARY.exists():
        raise FileNotFoundError(SUMMARY)
    key = api_key()
    session = requests.Session()
    session.headers.update({"x-vpo-api-key": key})
    policy_response = session.get(
        f"{API_URL}/config/distributor-account-policies", timeout=30
    )
    policy_response.raise_for_status()
    policy = policy_response.json()

    previous_key = api.VPO_API_KEY
    previous_marts = api.VPO_LOCAL_MARTS_DIR
    previous_ensure = api.ensure_marts
    api.VPO_API_KEY = key
    api.VPO_LOCAL_MARTS_DIR = None
    api.ensure_marts = lambda **_: {api.ROYALTIES_DASHBOARD_SUMMARY_FILE: SUMMARY}
    try:
        with use_distributor_policy_snapshot(policy):
            for name, params in CASES:
                selected = os.environ.get("VPO_DASHBOARD_QA_CASES")
                if selected and name not in selected.split(","):
                    continue
                compare = os.environ.get("VPO_DASHBOARD_QA_COMPARE", "1") == "1"
                if compare:
                    response = session.get(
                        f"{API_URL}/royalties-dashboard", params=params, timeout=180
                    )
                    response.raise_for_status()
                    expected = response.json()
                started = time.perf_counter()
                actual = api.royalties_dashboard(response=Response(), x_vpo_api_key=key, **params)
                seconds = time.perf_counter() - started
                if compare:
                    difference = first_difference(expected, actual)
                    if difference:
                        raise AssertionError(f"{name}: {difference}")
                peak_mb = peak_working_set_mb() if sys.platform == "win32" else None
                print(
                    f"CASE={name} EQUIVALENT={int(compare)} LOCAL_SECONDS={seconds:.1f} "
                    f"USD={actual['totals']['amount_usd']} PEAK_MB={peak_mb}",
                    flush=True,
                )
    finally:
        api.VPO_API_KEY = previous_key
        api.VPO_LOCAL_MARTS_DIR = previous_marts
        api.ensure_marts = previous_ensure


if __name__ == "__main__":
    main()
