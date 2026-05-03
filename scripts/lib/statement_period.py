import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StatementPeriodInfo:
    period: str
    source: str
    note: str


MONTHS = {
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
}


def from_dashgo_filename(file_name: str) -> StatementPeriodInfo:
    name = Path(file_name).stem
    match = re.search(r"-(\d{2})-(\d{2})$", name)

    if not match:
        return StatementPeriodInfo(
            period="unknown",
            source="filename",
            note="DashGo filename did not match expected pattern '...-MM-YY'.",
        )

    month = match.group(1)
    year = match.group(2)
    return StatementPeriodInfo(
        period=f"20{year}-{month}",
        source="filename",
        note="DashGo statement period inferred from filename suffix MM-YY.",
    )


def from_fuga_filename(file_name: str) -> StatementPeriodInfo:
    name = file_name.lower()

    for month_name, month_num in MONTHS.items():
        if month_name in name:
            pos = name.find(month_name)
            after_month = name[pos + len(month_name):]
            year = after_month[:4]

            if year.isdigit():
                return StatementPeriodInfo(
                    period=f"{year}-{month_num}",
                    source="filename",
                    note="FUGA regular statement period inferred from month/year in filename.",
                )

    return StatementPeriodInfo(
        period="unknown",
        source="filename",
        note="FUGA filename did not contain a parseable English month and 4-digit year.",
    )


def fuga_correction(period: str) -> StatementPeriodInfo:
    return StatementPeriodInfo(
        period=period,
        source="correction_policy",
        note=(
            "FUGA correction file has no statement month in filename; "
            "assigned to settlement period when correction is recognized."
        ),
    )


def from_onerpm_filename(file_name: str) -> StatementPeriodInfo:
    base = Path(file_name).stem
    if len(base) >= 7 and base[4] == "-" and base[7] == "-":
        return StatementPeriodInfo(
            period=base[:7],
            source="filename",
            note="ONErpm statement period inferred from filename prefix YYYY-MM.",
        )

    return StatementPeriodInfo(
        period="unknown",
        source="filename",
        note="ONErpm filename did not match expected prefix YYYY-MM.",
    )


def from_soundon_filename(file_name: str) -> StatementPeriodInfo:
    match = re.search(
        r"SoundOn_royalty_monthly_statement_(\d{4})_(\d{2})_(.+)\.csv$",
        file_name,
        flags=re.IGNORECASE,
    )

    if not match:
        return StatementPeriodInfo(
            period="unknown",
            source="filename",
            note="SoundOn filename did not match expected monthly statement pattern.",
        )

    return StatementPeriodInfo(
        period=f"{match.group(1)}-{match.group(2)}",
        source="filename",
        note="SoundOn statement period inferred from filename YYYY_MM.",
    )


def from_column(column_name: str, detail: str = "") -> tuple[str, str]:
    note = f"Statement period sourced from column '{column_name}'."
    if detail:
        note = f"{note} {detail}"
    return "column", note


def legacy_manual(detail: str) -> tuple[str, str]:
    return "legacy_manual", detail
