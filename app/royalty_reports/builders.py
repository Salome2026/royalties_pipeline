from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from app.royalty_reports.contracts import BuiltReport, ReportInputs, ReportRequest


BASE = Path(__file__).resolve().parents[2]
SCRIPTS = BASE / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_executive_royalty_pdf import build_executive_royalty_pdf  # noqa: E402
from build_keyword_royalty_report import (  # noqa: E402
    build_report,
    build_report_tables,
    normalize_keywords,
)
from lib.distributor_policy_store import load_distributor_policy_document  # noqa: E402


GoogleSheetBuilder = Callable[[object, list[str], str | None, str | None], str]


def royalty_report_scope_label(source: str | None, account: str | None) -> str:
    source = (source or "").strip().lower() or None
    account = (account or "").strip().lower() or None
    policy = load_distributor_policy_document()
    matching_policy = next(
        (
            entry
            for entry in policy.get("entries", [])
            if str(entry.get("source") or "").strip().lower() == source
            and str(entry.get("account") or "").strip().lower() == account
        ),
        None,
    )
    if source and account:
        return str((matching_policy or {}).get("display_name") or "").strip() or (
            f"{source.upper()} / {account.replace('_', ' ').title()}"
        )
    if source:
        return source.upper()
    return "Todas las distribuidoras"


def build_keyword_excel(request: ReportRequest, inputs: ReportInputs) -> BuiltReport:
    output_path = build_report(
        keywords=list(request.keywords),
        mode=request.mode,
        raw_limit=request.raw_limit,
        start_month=request.start_month,
        end_month=request.end_month,
        period_basis=request.period_basis,
        song_path=inputs.song_path,
        standardized_path=inputs.standardized_path,
        output_dir=inputs.output_dir,
    )
    return BuiltReport(
        output_path=Path(output_path),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def build_executive_pdf(request: ReportRequest, inputs: ReportInputs) -> BuiltReport:
    tables = build_report_tables(
        keywords=list(request.keywords),
        mode=request.mode,
        raw_limit=0,
        start_month=request.start_month,
        end_month=request.end_month,
        period_basis=request.period_basis,
        song_path=inputs.song_path,
        standardized_path=inputs.standardized_path,
        source=request.source,
        account=request.account,
    )
    output_path = build_executive_royalty_pdf(
        tables=tables,
        output_dir=inputs.output_dir,
        scope_label=royalty_report_scope_label(request.source, request.account),
        keywords=list(request.keywords),
        period_basis=request.period_basis,
        start_month=request.start_month,
        end_month=request.end_month,
    )
    return BuiltReport(output_path=Path(output_path), content_type="application/pdf")


def build_google_sheet(
    request: ReportRequest,
    inputs: ReportInputs,
    create_google_sheet: GoogleSheetBuilder,
) -> BuiltReport:
    tables = build_report_tables(
        keywords=list(request.keywords),
        mode=request.mode,
        raw_limit=request.raw_limit,
        start_month=request.start_month,
        end_month=request.end_month,
        period_basis=request.period_basis,
        song_path=inputs.song_path,
        standardized_path=inputs.standardized_path,
    )
    result_url = create_google_sheet(
        tables,
        list(request.keywords),
        request.start_month,
        request.end_month,
    )
    return BuiltReport(result_url=result_url)


def build_registered_report(
    request: ReportRequest,
    inputs: ReportInputs,
    *,
    create_google_sheet: GoogleSheetBuilder,
) -> BuiltReport:
    if request.report_key == "royalty_keyword":
        return build_keyword_excel(request, inputs)
    if request.report_key == "royalty_executive":
        return build_executive_pdf(request, inputs)
    if request.report_key == "royalty_google_sheet":
        return build_google_sheet(request, inputs, create_google_sheet)
    raise ValueError(f"Tipo de reporte no soportado: {request.report_key}.")
