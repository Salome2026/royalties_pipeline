from __future__ import annotations

import sys
from pathlib import Path

import polars as pl


BASE = Path(__file__).resolve().parents[2]
SCRIPTS = BASE / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_keyword_royalty_report as report  # noqa: E402


def detail_frame() -> pl.LazyFrame:
    rows: list[dict[str, object]] = []

    def add(country: str, dsp: str, amount: float, index: int) -> None:
        rows.append(
            {
                "statement_period": "2026-08",
                "transaction_month": "2026-07",
                "artist_statement_style": "Artista",
                "track_statement_style": f"Tema {index}",
                "report_code": f"CODE{index}",
                "report_code_source": "ISRC",
                "asset_isrc": f"ISRC{index}",
                "report_territory": country,
                "dsp_normalized": dsp,
                "monetization_normalized": "Premium",
                "content_origin_normalized": "Audio / Master",
                "classification_status": "exact",
                "store_raw": dsp,
                "usage_type": "Audio / Master",
                "amount_usd": amount,
                "currency_original": "USD",
                "fx_to_usd_rate": 1.0,
                "units": 1.0,
                "territory": country,
                "statement_file_name": "test.csv",
                "match_text": "artista",
                "source": "test",
                "account": "test",
            }
        )

    add("AR", "Spotify", 100, 1)
    add("AR", "Apple Music", 10, 2)
    add("ES", "YouTube", 80, 3)
    add("US", "Spotify", 70, 4)
    add("CL", "Spotify", 60, 5)
    add("UY", "Spotify", 50, 6)
    for index in range(7, 17):
        add("MX", "Spotify", 1, index)
    return pl.DataFrame(rows).lazy()


def check_limited_modes() -> None:
    frame = detail_frame()
    columns = set(frame.collect_schema().names())

    empty = report.build_report_detail(
        frame,
        columns,
        keywords=["artista"],
        detail_mode="limited",
        raw_limit=0,
    )
    assert empty.empty

    limited = report.build_report_detail(
        frame,
        columns,
        keywords=["artista"],
        detail_mode="limited",
        raw_limit=5,
    )
    assert len(limited) == 5


def check_top_countries_use_income() -> None:
    frame = detail_frame()
    columns = set(frame.collect_schema().names())
    detail = report.build_report_detail(
        frame,
        columns,
        keywords=["artista"],
        detail_mode="top_countries",
        raw_limit=5,
    )

    countries = list(dict.fromkeys(detail["País consolidado"].tolist()))
    assert countries == [
        "Argentina",
        "España",
        "Estados Unidos",
        "Chile",
        "Uruguay",
        "Resto del mundo",
    ]
    assert "México" not in countries
    assert int(detail["Filas representadas"].sum()) == 16
    assert abs(float(detail["Ingresos USD"].sum()) - 380.0) < 0.000001


def check_full_detail_limit() -> None:
    frame = detail_frame()
    columns = set(frame.collect_schema().names())
    original_limit = report.EXCEL_MAX_DATA_ROWS
    report.EXCEL_MAX_DATA_ROWS = 2
    try:
        try:
            report.build_report_detail(
                frame,
                columns,
                keywords=["artista"],
                detail_mode="full",
                raw_limit=0,
            )
        except ValueError as exc:
            assert "supera el máximo permitido" in str(exc)
        else:
            raise AssertionError("El detalle completo debe respetar el límite de Excel.")
    finally:
        report.EXCEL_MAX_DATA_ROWS = original_limit


def main() -> None:
    check_limited_modes()
    check_top_countries_use_income()
    check_full_detail_limit()
    print("OK: modos de detalle, ranking por ingresos y límite de Excel.")


if __name__ == "__main__":
    main()
