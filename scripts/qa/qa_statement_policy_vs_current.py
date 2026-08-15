from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

BASE = Path(r"C:\royalties_pipeline")
ENV_PATH = BASE / ".env"
SCRIPTS_DIR = BASE / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_local_env(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env(ENV_PATH)

from build_statement_report_from_mart import (
    NEW_REPORT_ONERPM_ACCOUNTS,
    STANDARDIZED_ALL_PATH,
    aggregate_statement_data,
    build_post_reference_totals,
    build_release_metadata_totals,
    build_source_sheet_totals,
    build_statement_report_new_variants,
)
from lib.distributor_policy_store import load_distributor_policy_document


REGISTRY_DIR = BASE / "warehouse" / "registry"
REPORTS_QA_DIR = BASE / "reports" / "qa"

CUTOFFS_PATH = REGISTRY_DIR / "contract_cutoffs.json"

KEY_COLUMNS = ["source", "account", "artist", "statement_period"]
VALUE_COLUMNS = KEY_COLUMNS + ["total", "has_share_in_out"]


def read_json_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError(f"{path} no tiene una lista entries valida")
    return entries


def normalize_totals(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=VALUE_COLUMNS)

    out = df.copy()
    for col in KEY_COLUMNS:
        out[col] = out[col].fillna("").astype(str)
    out["total"] = pd.to_numeric(out["total"], errors="coerce").fillna(0.0)
    if "has_share_in_out" not in out.columns:
        out["has_share_in_out"] = 0
    out["has_share_in_out"] = pd.to_numeric(
        out["has_share_in_out"],
        errors="coerce",
    ).fillna(0).astype(int)

    grouped = (
        out
        .groupby(KEY_COLUMNS, dropna=False, as_index=False)
        .agg(
            total=("total", "sum"),
            has_share_in_out=("has_share_in_out", "max"),
        )
    )
    grouped["total"] = grouped["total"].round(2)
    return grouped[VALUE_COLUMNS]


def current_new_statement_totals(standardized_path: Path = STANDARDIZED_ALL_PATH) -> pd.DataFrame:
    base, _ = aggregate_statement_data(standardized_path)
    current = base.loc[
        (base["source"] != "onerpm")
        | (base["account"].isin(NEW_REPORT_ONERPM_ACCOUNTS))
    ].copy()

    variants = build_statement_report_new_variants(standardized_path)
    if not variants.empty:
        current = pd.concat([current, variants], ignore_index=True)

    return normalize_totals(current)


def policy_statement_totals(standardized_path: Path = STANDARDIZED_ALL_PATH) -> pd.DataFrame:
    policies = load_distributor_policy_document().get("entries", [])
    cutoffs = {
        entry.get("cutoff_id"): entry
        for entry in read_json_entries(CUTOFFS_PATH)
        if entry.get("cutoff_id")
    }
    base, _ = aggregate_statement_data(standardized_path)

    pieces: list[pd.DataFrame] = []

    for policy in policies:
        source = str(policy.get("source") or "")
        account = str(policy.get("account") or "")
        if not source or not account:
            continue
        if policy.get("statement_view_enabled") is not True:
            continue

        cutoff_id = policy.get("contract_cutoff_id")
        if cutoff_id:
            cutoff = cutoffs.get(cutoff_id, {})
            evidence_terms = cutoff.get("evidence_terms") or []
            cutoff_basis = str(cutoff.get("cutoff_basis") or "transaction_month")

            if account == "la_nueva_sangre":
                release_based = build_release_metadata_totals(
                    standardized_path=standardized_path,
                    source=source,
                    account=account,
                    output_account=account,
                )
                if not release_based.empty:
                    pieces.append(release_based)
                    continue

            reference_source = None
            reference_account = None
            observed_source = str(cutoff.get("evidence_observed_source") or "")
            if "/" in observed_source:
                reference_source, reference_account = observed_source.split("/", 1)

            fallback_month = cutoff.get("contract_start_month")
            pieces.append(
                build_post_reference_totals(
                    standardized_path=standardized_path,
                    source=source,
                    base_account=account,
                    output_account=account,
                    reference_terms=[str(term) for term in evidence_terms],
                    fallback_cutoff_month=str(fallback_month) if fallback_month else None,
                    reference_source=reference_source,
                    reference_account=reference_account,
                    cutoff_basis="transaction_month"
                    if "transaction_month" in cutoff_basis
                    else "statement_period",
                )
            )
            continue

        if source == "onerpm":
            sheet_rules = policy.get("sheet_rules") or {}
            for source_sheet, rule in sheet_rules.items():
                if isinstance(rule, dict) and rule.get("statement_view") is True:
                    pieces.append(
                        build_source_sheet_totals(
                            standardized_path=standardized_path,
                            source=source,
                            account=account,
                            source_sheet=str(source_sheet),
                        )
                    )
            continue

        pieces.append(
            base.loc[
                (base["source"] == source)
                & (base["account"] == account)
            ].copy()
        )

    if not pieces:
        return pd.DataFrame(columns=VALUE_COLUMNS)

    return normalize_totals(pd.concat(pieces, ignore_index=True))


def compare_totals(current: pd.DataFrame, policy: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    compare = current.merge(
        policy,
        on=KEY_COLUMNS,
        how="outer",
        suffixes=("_current", "_policy"),
    )
    for col in ["total_current", "total_policy", "has_share_in_out_current", "has_share_in_out_policy"]:
        compare[col] = pd.to_numeric(compare[col], errors="coerce").fillna(0.0)

    compare["diff"] = (compare["total_policy"] - compare["total_current"]).round(2)
    compare["abs_diff"] = compare["diff"].abs()
    compare = compare.sort_values("abs_diff", ascending=False)

    summary = (
        compare
        .groupby(["source", "account"], dropna=False, as_index=False)
        .agg(
            total_current=("total_current", "sum"),
            total_policy=("total_policy", "sum"),
            diff=("diff", "sum"),
            max_abs_row_diff=("abs_diff", "max"),
            rows=("diff", "size"),
        )
    )
    summary["total_current"] = summary["total_current"].round(2)
    summary["total_policy"] = summary["total_policy"].round(2)
    summary["diff"] = summary["diff"].round(2)
    summary["status"] = summary["diff"].abs().le(0.01).map({True: "OK", False: "REVISAR"})
    summary = summary.sort_values(["status", "source", "account"])
    return summary, compare


def main() -> None:
    REPORTS_QA_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    current = current_new_statement_totals()
    policy = policy_statement_totals()
    summary, compare = compare_totals(current, policy)

    summary_path = REPORTS_QA_DIR / f"statement_policy_vs_current_summary_{stamp}.csv"
    diff_path = REPORTS_QA_DIR / f"statement_policy_vs_current_diffs_{stamp}.csv"
    top_path = REPORTS_QA_DIR / f"statement_policy_vs_current_top_diffs_{stamp}.csv"

    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    compare.to_csv(diff_path, index=False, encoding="utf-8-sig")
    compare.head(200).to_csv(top_path, index=False, encoding="utf-8-sig")

    print("=== QA STATEMENT POLICY VS CURRENT ===")
    print(f"Current rows: {len(current)} total={current['total'].sum():.2f}")
    print(f"Policy rows: {len(policy)} total={policy['total'].sum():.2f}")
    print(f"Diff total: {(policy['total'].sum() - current['total'].sum()):.2f}")
    print()
    print(summary.to_string(index=False))
    print()
    print("Archivos:")
    print(summary_path)
    print(diff_path)
    print(top_path)


if __name__ == "__main__":
    main()
