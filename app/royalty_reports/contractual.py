"""Opt-in contractual reporting; never applies splits to existing reports."""
from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from typing import Any

from app.master_contracts import validate_split, _period_start, _period_end


def beneficiary_key(value: str) -> str:
    normalized = re.sub(r"[\u0300-\u036f]", "", unicodedata.normalize("NFD", value))
    return re.sub(r"\s+", " ", normalized.strip()).lower()


def round_money(value: float) -> float:
    return (-1 if value < 0 else 1) * math.floor(abs(value) * 100 + 0.50000001) / 100


def settle_amounts(values: list[float], target: float) -> list[float]:
    """Same consolidated largest-remainder rule as contractLogic.settleRows."""
    if not values:
        if abs(target) > 0.005:
            raise ValueError("No hay beneficiarios para conservar el reparto.")
        return []
    sign = -1 if target < 0 else 1
    cents = math.floor(abs(target) * 100 + 0.50000001)
    total = sum(values)
    exact = [cents * value / total for value in values] if abs(total) > 1e-10 else [value * 100 for value in values]
    floors = [math.floor(value + 1e-8) for value in exact]
    order = sorted(range(len(values)), key=lambda i: (-(exact[i] - floors[i]), i))
    remainder = cents - sum(floors)
    if not 0 <= remainder <= len(values):
        raise ValueError("No se pudo conciliar el redondeo del reparto.")
    for index in order[:remainder]:
        floors[index] += 1
    return [sign * value / 100 for value in floors]


def allocation_rows(agreement: dict, split: dict) -> list[dict]:
    """Percentages and provenance mirror the saved-contract preview, without money rounding."""
    allocation = agreement.get("allocation") or split
    owners = agreement.get("owners") or []
    rows: list[dict] = []

    def add(name: str, percent: float, label: str, partner: bool = False) -> None:
        rows.append({"artist": name.strip(), "percent": percent, "label": label, "partner": partner})

    def distribute(base: float, label: str) -> None:
        total = sum(float(owner.get("percent") or 0) for owner in owners)
        for owner in owners:
            fraction = 1 / len(owners) if agreement.get("owner_split_mode") == "equal" else float(owner.get("percent") or 0) / total
            add(owner["name"], base * fraction, label, True)

    if agreement.get("allocation_model") == "pools":
        pool = float(agreement.get("master_pool_percent") or 0)
        if agreement.get("commercialization") == "master":
            distribute(pool, "Titular del master")
        else:
            add(agreement.get("company_name") or "Indyana", pool, "Distribución", True)
        participants = [{"artist": allocation["principal"], "percent": allocation["principal_percent"], "rule": allocation.get("principal_rule")}, *(allocation.get("participants") or [])]
        for item in participants:
            base = float(item.get("percent") or 0)
            rule = item.get("rule") or {}
            if rule.get("treatment") == "project_owners":
                distribute(base, f"Participación de {item['artist']}")
            elif rule.get("treatment") == "artist_contract":
                retained = base * float(rule["retained_percent"]) / 100
                add(rule["retained_recipient"], retained, f"Contrato de {item['artist']}", True)
                add(item["artist"], base - retained, "Participación después de contrato")
            else:
                add(item["artist"], base, "Participación directa")
    else:
        if agreement.get("commercialization") == "master":
            for owner in owners:
                add(owner["name"], float(owner.get("percent") or 0), "Reparto guardado", True)
        else:
            add("Indyana", float(allocation.get("indyana_percent") or 0), "Reparto guardado", True)
        add(allocation["principal"], float(allocation.get("principal_percent") or 0), "Reparto guardado")
        for item in allocation.get("participants") or []:
            base = float(item.get("percent") or 0)
            retained = base * float(item.get("internal_contract_indyana_percent") or 0) / 100 if allocation.get("apply_guest_contracts") else 0
            if retained:
                add("Indyana", retained, "Reparto guardado", True)
            add(item["artist"], base - retained, "Reparto guardado")
    if not math.isclose(sum(row["percent"] for row in rows), 100, abs_tol=0.0001):
        raise ValueError("El contrato no conserva el 100% del ingreso.")
    return rows


def analyze_contractual_income(snapshot: dict, income: list[dict]) -> dict[str, Any]:
    catalog = {row["isrc"]: row for row in snapshot["catalog"]}
    contracts = {row["isrc"]: row for row in snapshot["contracts"]}
    monthly: dict[str, float] = defaultdict(float)
    by_isrc: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    pending: dict[tuple, dict] = {}
    total = 0.0
    units = raw_rows = 0
    sources = set()

    def unassigned(code: str, title: str, month: str, amount: float, reason: str) -> None:
        key = (code, reason)
        row = pending.setdefault(key, {"code": code, "title": title, "months": set(), "amount_usd": 0.0, "reason": reason})
        row["months"].add(month)
        row["amount_usd"] += amount

    for row in income:
        month = row.get("statement_month")
        if not month:
            raise ValueError("Hay ingresos sin fecha de statement; no se genera un reparto incompleto.")
        amount = float(row["amount_usd"] or 0)
        total += amount
        monthly[month] += amount
        units += float(row.get("units") or 0)
        raw_rows += int(row.get("raw_rows") or 0)
        sources.add(row.get("source"))
        if row.get("isrc") in catalog:
            by_isrc[row["isrc"]][month] += amount
        else:
            unassigned(row.get("isrc") or row.get("upc") or f"TEXT:{row.get('title') or ''}", row.get("title") or "Sin título", month, amount, "Sin contrato de ISRC asociado")

    beneficiaries: dict[str, dict] = {}
    allocations = []
    covered = 0.0
    for isrc, track in catalog.items():
        saved = contracts.get(isrc) or {}
        split = saved.get("split") or {}
        agreements = split.get("agreements") or []
        error = "Sin contrato cerrado con vigencia definida"
        if saved.get("is_closed") and agreements:
            try:
                validate_split(split, True, False)
                shares_by_agreement = [allocation_rows(agreement, split) for agreement in agreements]
                error = ""
            except (ValueError, TypeError, KeyError, ZeroDivisionError):
                error = "Contrato inválido; requiere revisión"
        if error:
            for month, amount in by_isrc[isrc].items():
                unassigned(isrc, track["title"], month, amount, error)
            continue
        for agreement, shares in zip(agreements, shares_by_agreement):
            start = _period_start(agreement["effective_from"])
            end = _period_end(agreement["effective_until"]) if agreement.get("effective_until") else _period_start(snapshot["as_of"])
            amount = sum(value for month, value in by_isrc[isrc].items() if start <= _period_start(month) <= end)
            covered += amount
            allocations.append({"isrc": isrc, "amount_usd": amount, "shares": shares, "version": saved["version"]})
            for share in shares:
                key = beneficiary_key(share["artist"])
                recipient = beneficiaries.setdefault(key, {"artist": share["artist"], "raw_amount_usd": 0.0, "partner": False, "components": [0.0, 0.0, 0.0]})
                contribution = amount * share["percent"] / 100
                recipient["raw_amount_usd"] += contribution
                recipient["partner"] |= share["partner"]
                label = share["label"]
                bucket = 0 if label in {"Titular del master", "Distribución", "Reparto guardado"} else 2 if label.startswith("Contrato de") else 1
                recipient["components"][bucket] += contribution
        for month, amount in by_isrc[isrc].items():
            day = _period_start(month)
            if not any(_period_start(a["effective_from"]) <= day <= (_period_end(a["effective_until"]) if a.get("effective_until") else _period_start(snapshot["as_of"])) for a in agreements):
                unassigned(isrc, track["title"], month, amount, "Fuera de la vigencia guardada")

    raw_pending = sum(row["amount_usd"] for row in pending.values())
    if not math.isclose(total, covered + raw_pending, abs_tol=0.00001):
        raise ValueError("No se conservan los ingresos del reporte.")
    recipients = list(beneficiaries.values())
    for row, amount in zip(recipients, settle_amounts([row["raw_amount_usd"] for row in recipients], covered)):
        row["amount"] = amount
        row["components"] = settle_amounts(row["components"], amount)
    pending_total = round_money(total) - round_money(covered)
    extras = sorted(pending.values(), key=lambda row: -row["amount_usd"])
    for row, amount in zip(extras, settle_amounts([row["amount_usd"] for row in extras], pending_total)):
        row["months"] = sorted(row["months"])
        row["display_amount"] = amount
    return {"total": round_money(total), "covered": round_money(covered), "pending": round_money(pending_total),
            "recipients": recipients, "extra_codes": extras, "monthly": sorted(monthly.items()),
            "units": units, "raw_rows": raw_rows, "sources": len(sources), "catalog_count": len(catalog),
            "income_isrc_count": len(by_isrc), "allocations": allocations,
            "tracks": sorted([{**track, "amount_usd": sum(by_isrc[isrc].values())} for isrc, track in catalog.items()], key=lambda row: -row["amount_usd"])}
