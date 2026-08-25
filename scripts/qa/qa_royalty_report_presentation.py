from __future__ import annotations

from pathlib import Path
import sys


BASE = Path(__file__).resolve().parents[2]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from scripts.build_keyword_royalty_report import (  # noqa: E402
    PRIVATE_REPORT_AMOUNT_COLUMNS,
    public_detail_columns,
)


def main() -> None:
    source_columns = {
        "source",
        "account",
        "statement_period",
        "transaction_month",
        "amount_usd",
        "net_amount",
        "net_amount_usd",
        "gross_amount",
        "currency_original",
        "fx_to_usd_rate",
        "units",
    }
    for include_statement_metadata in (False, True):
        selected = public_detail_columns(
            source_columns,
            include_statement_metadata=include_statement_metadata,
        )
        if "amount_usd" not in selected:
            raise AssertionError("El detalle publico debe incluir el neto reportable final")
        exposed = PRIVATE_REPORT_AMOUNT_COLUMNS.intersection(selected)
        if exposed:
            raise AssertionError(f"El detalle publico expone importes internos: {sorted(exposed)}")

    print("OK: el detalle de regalias expone un unico importe reportable.")


if __name__ == "__main__":
    main()
