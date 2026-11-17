"""Compare the live published figures using an isolated Cloud Run job and policy copy."""
from contextlib import contextmanager
from json import dumps
from math import isclose
import os
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import polars as pl

from app import operational_db
from app.bigquery_dashboard import royalties_dashboard_bigquery
from app.catalog_refresh import dashboard_state
from app.royalty_reports.bigquery_backend.deployment import publications
from app.royalty_reports.bigquery_backend.reader import read_source
from app.royalty_reports.bigquery_backend.runtime import BigQueryReportBackend, report
from scripts.build_executive_royalty_pdf import build_executive_royalty_pdf
from scripts.lib import distributor_policy_store as store


OCT, NOV = "2026-10", "2026-11"
SOURCE = {"source": "fuga", "account": "indyana_records"}
ACCOUNT = {"policy_id": "fuga_indyana_records", "schedule_additions": [{"from_statement": NOV, "percent": 18}]}


def trial_policy(baseline):
    with operational_db.operational_connect() as conn:
        conn.execute("SET LOCAL search_path TO pg_temp, public")
        for table in ("distributor_account_policies", "distributor_policy_settings", "distributor_policy_audit"):
            suffix = " WHERE false" if table == "distributor_policy_audit" else ""
            conn.execute(f"CREATE TEMP TABLE {table} ON COMMIT DROP AS SELECT * FROM public.{table}{suffix}")
            assert conn.execute("SELECT to_regclass(%s) = to_regclass(%s) AS isolated", (table, f"pg_temp.{table}")).fetchone()["isolated"]
        assert store.read_distributor_policy_document(conn) == baseline, "Published policy changed"

        @contextmanager
        def isolated_connection():
            yield conn

        with patch.object(store, "operational_connect", isolated_connection):
            candidate = store.update_report_personalization(enabled=True, accounts=[ACCOUNT], updated_by="management-cloud-trial")
            entry = next(item for item in candidate["entries"] if item["policy_id"] == ACCOUNT["policy_id"])
            assert entry["report_net_adjustment_pct"] == 10 and entry["report_adjustment_schedule"] == ACCOUNT["schedule_additions"]
            try:
                store.update_report_personalization(enabled=True, accounts=[{"policy_id": ACCOUNT["policy_id"],
                    "report_net_adjustment_pct": 18}], updated_by="management-cloud-trial")
            except ValueError:
                pass
            else:
                raise AssertionError("The historical base could be overwritten")
            assert store.read_distributor_policy_document(conn) == candidate
            assert conn.execute("SELECT COUNT(*) AS n FROM pg_temp.distributor_policy_audit").fetchone()["n"] == 1
        conn.rollback()
    return candidate


def near(left, right):
    assert isclose(left, right, abs_tol=.011, rel_tol=0), (left, right)


def main():
    if os.getenv("CLOUD_RUN_JOB") != "vpo-management-preview-20261117":
        raise RuntimeError("Esta prueba requiere el Job cloud dedicado.")
    pub = publications()
    backend = BigQueryReportBackend(pub, watch_inbox=False)
    pin, release, paths, baseline = backend.capture("regular")
    candidate = trial_policy(baseline)
    print(dumps({"check": "isolated_policy", "before": baseline["policy_version"], "after": candidate["policy_version"]}), flush=True)
    manifest = {"release_id": release["source_release_id"], "royalty_scope": "regular", "report_publication": pin}
    state = dashboard_state(pub.state.bucket.client)
    assert state["ready"]["base_release_id"] == release["source_release_id"], "Published dashboard and report inputs are not aligned"
    read_params = dict(**SOURCE, keywords=[], mode="any", period_basis="statement_period", start_month=OCT, end_month=NOV)
    root = Path("/tmp/management-trial")
    raw = read_source(pub, release, "raw", read_params, report, root)
    with backend.context(release, paths, manifest, baseline):
        prepared = report.prepare_keyword_source(raw, root / "selected.parquet", [], "any", batch_size=16384)
    for start, end in ((OCT, OCT), (NOV, NOV), (OCT, NOV)):
        results = []
        for policy in (baseline, candidate):
            t0 = perf_counter()
            visible = royalties_dashboard_bigquery(policy_document=policy, catalog_state=state,
                period_mode="single_month" if start == end else "closed_range", start_month=start, end_month=end,
                period_basis="statement_period", client=pub.client, **SOURCE)["totals"]
            dashboard_s = perf_counter() - t0
            t0 = perf_counter()
            with backend.context(release, paths, manifest, policy):
                tables = report.build_report_tables(keywords=[], mode="any", raw_limit=0, standardized_path=prepared,
                    start_month=start, end_month=end, period_basis="statement_period", _dashgo_video_groups=pl.DataFrame(), **SOURCE)
            report_s = perf_counter() - t0
            total = float(tables["resumen general"]["Ingresos USD"].iloc[0])
            near(visible["amount_usd"], total)
            results.append({"usd": total, "units": visible["units"], "rows": visible["rows"],
                            "dashboard_seconds": round(dashboard_s, 2), "report_compute_seconds": round(report_s, 2)})
        if start == end == OCT:
            near(results[0]["usd"], results[1]["usd"])
            october = results[1]["usd"]
        elif start == end == NOV:
            near(results[0]["usd"] / .90 * .82, results[1]["usd"])
            november = results[1]["usd"]
        else:
            near(results[0]["usd"] - results[1]["usd"], november / .82 * (.90 - .82))
            near(october + november, results[1]["usd"])
            pdf = build_executive_royalty_pdf(tables=tables, output_dir=root, scope_label="FUGA Indyana",
                keywords=[], period_basis="statement_period", start_month=start, end_month=end)
            assert pdf.is_file() and pdf.stat().st_size > 1024
        assert results[0]["units"] == results[1]["units"] and results[0]["rows"] == results[1]["rows"]
        print(dumps({"check": "management_report_parity", "range": [start, end], "baseline": results[0], "candidate": results[1]}), flush=True)
    assert backend.capture("regular")[0] == pin and baseline == store.load_distributor_policy_document()


if __name__ == "__main__":
    main()
