from __future__ import annotations

from pathlib import Path
import sys

import polars as pl


BASE = Path(__file__).resolve().parents[2]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from scripts.lib.catalog_report_filter import apply_report_net_personalization
from scripts.lib.distributor_policy_store import load_distributor_policy_document


DASHBOARD_PATH = BASE / "warehouse" / "marts" / "royalties_dashboard_summary.parquet"
REMOVED_JSON_PATH = BASE / "warehouse" / "registry" / "distributor_account_policies.json"


def main() -> None:
    if REMOVED_JSON_PATH.exists():
        raise RuntimeError(f"Removed runtime policy JSON exists: {REMOVED_JSON_PATH}")
    if not DASHBOARD_PATH.exists():
        raise FileNotFoundError(DASHBOARD_PATH)

    policy = load_distributor_policy_document()
    if not policy.get("entries"):
        raise RuntimeError("Cloud SQL has no active distributor policies.")

    base = pl.scan_parquet(DASHBOARD_PATH)
    schema = set(base.collect_schema().names())
    baked_columns = sorted(column for column in schema if column.startswith("policy_"))
    if baked_columns:
        raise RuntimeError(f"Dashboard contains baked policy columns: {baked_columns}")

    adjusted = apply_report_net_personalization(base, schema, amount_col="amount_usd")
    totals = pl.concat([
        base.select(pl.lit("base").alias("kind"), pl.sum("amount_usd").alias("amount_usd")),
        adjusted.select(pl.lit("adjusted").alias("kind"), pl.sum("amount_usd").alias("amount_usd")),
    ]).collect().to_dicts()

    print({
        "ok": True,
        "policy_version": policy["policy_version"],
        "personalization": policy["report_personalization"],
        "accounts": len(policy["entries"]),
        "dashboard_totals": totals,
    })


if __name__ == "__main__":
    main()
