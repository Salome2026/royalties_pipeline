"""Rules for the management adjustment on the distributor's net amount."""
from __future__ import annotations

import math
import re


def adjustment_percent(value: object) -> float:
    percent = float(value)
    if not math.isfinite(percent) or not 0 <= percent <= 100:
        raise ValueError("El porcentaje de management debe estar entre 0 y 100.")
    return percent


def adjustment_schedule(changes: list[dict]) -> list[dict]:
    result = {}
    for item in changes:
        month = str(item["from_statement"])
        if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month) or month.startswith("0000"):
            raise ValueError("La vigencia debe ser un mes de statement valido (AAAA-MM).")
        if month in result:
            raise ValueError(f"Ya hay una vigencia de management desde {month}.")
        result[month] = adjustment_percent(item["percent"])
    return [{"from_statement": month, "percent": percent} for month, percent in sorted(result.items())]


def adjustment_rules(policy: dict):
    if not (policy.get("report_personalization") or {}).get("enabled"):
        return
    for entry in policy.get("entries", []):
        source = str(entry.get("source") or "").strip().lower().replace(" ", "_")
        account = str(entry.get("account") or "").strip().lower().replace(" ", "_")
        base = adjustment_percent(entry.get("report_net_adjustment_pct") or 0)
        schedule = adjustment_schedule(entry.get("report_adjustment_schedule") or [])
        if source and account and (base or schedule):
            yield source, account, base, schedule
