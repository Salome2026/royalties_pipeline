from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import polars as pl
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from ingest_standardized_ada import read_statement, select_statement_files, standardize
from lib.ada_identity import ada_catalog_key_expr, add_ada_artist_evidence
from app.master_contracts import _ada_artists
from lib.store_taxonomy import add_store_dimensions


def fixture(path: Path, changes: dict | None = None, account: str = "99500", period: str = "07/26 - 07/26", empty: bool = False) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Distribution Statement"
    sheet.append(["Royalties Statement for Period:", period])
    sheet.append(["Contract:", f"{account}-TEST"])
    row = {
        "Artist Name": "Artist & Guest", "Project Title": "Album", "Catalogue Number": "A123",
        "ISRC": None, "Catalogue Title": "Track", "Reported Month": "202605",
        "Territory": "Spotify", "Country Code": "AR", "Sales": 2,
        "Receipts Value": 0.21, "Distribution Fees": 0.021, "Mechanical Fees": 0,
        "Admin Fees": 0, "Upload Fees": 0, "Other Fees": 0, "Artist Royalties": 0,
        "Parent Product ID": "8718521191726", "UPC": None,
        "Price Name": "Streaming Full Price", "Revenue Type Desc": "Subscription",
    }
    row.update(changes or {})
    sheet.append(list(row))
    if not empty:
        sheet.append(list(row.values()))
    for label in ["Sub Totals:", "Previously Accounted Deductions:", "Totals:"]:
        sheet.append([None] * 10 + [label])
    workbook.save(path)


def rejected(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError("Invalid input was accepted")


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        excel = root / "99500_202607_202607_99500_DTL.xlsx"
        fixture(excel)
        frame = read_statement(excel)
        assert frame.height == 1
        assert frame["amount_usd"][0] == 0.189
        normalized = standardize(frame, excel, "indyana_records", "99500", {"revenue_basis": "generation", "cash_view": True, "catalog_view": True, "statement_view": True})
        assert normalized["transaction_month"][0] == "2026-05"
        assert normalized["statement_period"][0] == "2026-07"
        assert normalized["receipt_month"][0] is None
        assert normalized["product_upc"][0] == "8718521191726"
        assert normalized["product_upc_source"][0] == "Parent Product ID"
        assert normalized["store_name"][0] == "Spotify" and normalized["territory"][0] == "AR"
        assert normalized["units"][0] == 2 and normalized["Artist Name"][0] == "Artist & Guest"
        assert not {"GPID", "gpid", "Repdate Month ID", "Product Title"} & set(normalized.columns)
        assert normalized.select(ada_catalog_key_expr(set(normalized.columns)))[0, 0] == "ADA:99500:CATALOG:A123"
        dimensions = add_store_dimensions(normalized.lazy()).collect()
        assert dimensions["dsp_normalized"][0] == "Spotify"
        assert dimensions["monetization_normalized"][0] == "Premium"
        assert select_statement_files(root) == [excel]
        txt = root / "Statement_99500_5779_99500_20260731.txt"
        txt.touch()
        rejected(lambda: read_statement(txt))
        rejected(lambda: select_statement_files(root))
        txt.unlink()
        wrong_period = root / "99500_202608_202608_99500_DTL.xlsx"
        fixture(wrong_period)
        rejected(lambda: read_statement(wrong_period))
        wrong_period.unlink()
        duplicate = root / "99205_202607_202607_99205_DTL.xlsx"
        fixture(duplicate, account="99205")
        rejected(lambda: select_statement_files(root))
        duplicate.unlink()
        fixture(excel, account="99205")
        rejected(lambda: read_statement(excel))
        fixture(excel)
        rejected(lambda: standardize(read_statement(excel), excel, "mawz", "99205", {"revenue_basis": "generation"}))
        for field, value in [("Mechanical Fees", 0.01), ("Other Fees", "NaN"), ("Admin Fees", "invalid"), ("Artist Royalties", 1), ("Receipts Value", None), ("Sales", "invalid"), ("Reported Month", "202613")]:
            fixture(excel, {field: value})
            rejected(lambda: read_statement(excel))
        fixture(excel, {"Catalogue Number": None, "ISRC": None})
        rejected(lambda: standardize(read_statement(excel), excel, "indyana_records", "99500", {"revenue_basis": "generation"}))
        fixture(excel, {"ISRC": "bk-4da-26-58497", "Catalogue Title": "Totals"})
        valid = standardize(read_statement(excel), excel, "indyana_records", "99500", {"revenue_basis": "generation"})
        assert valid.height == 1 and valid["asset_isrc"][0] == "BK4DA2658497"
        fixture(excel, {"Parent Product ID": "0085365665804"})
        assert standardize(read_statement(excel), excel, "indyana_records", "99500", {"revenue_basis": "generation"})["product_upc"][0] == "0085365665804"
        fixture(excel, empty=True)
        assert read_statement(excel).is_empty()

    cut = "LA JUNTADA DE LOS ARTISTAS & S"
    assert len(cut) == 30
    full = "LA JUNTADA DE LOS ARTISTAS & SOFI B"
    evidence = pl.DataFrame({"asset_isrc": ["BK4DA2634549", "BK4DA2634549", "BK4DA2634550"],
                             "Artist Name": [cut, full, cut], "statement_file_name": ["old.xlsx", "new.xlsx", "other.xlsx"]})
    resolved = add_ada_artist_evidence(evidence)
    assert resolved["Artist Name"].to_list() == [cut, full, cut]
    assert resolved["artist_statement_original"].to_list() == [cut, full, cut]
    assert resolved["artist_statement_style"].to_list() == [full, full, cut]
    assert add_ada_artist_evidence(resolved).select(resolved.columns).equals(resolved), "Reprocessing changed the original credit"
    assert resolved["artist_catalog_style"][0] == full
    assert resolved["artist_credit_evidence_file"][0] == "new.xlsx"
    assert resolved["artist_catalog_style"][2] == cut, "Different ISRC completed a participant"
    ambiguous = pl.concat([evidence, pl.DataFrame({"asset_isrc": ["BK4DA2634549"], "Artist Name": ["LA JUNTADA DE LOS ARTISTAS & SILVIA"], "statement_file_name": ["conflict.xlsx"]})])
    conflict = add_ada_artist_evidence(ambiguous)
    assert conflict["artist_catalog_style"][0] == cut and conflict["artist_credit_status"][0] == "conflicting_prefix"
    assert conflict["artist_statement_style"][0] == cut
    for raw in ["La Juntada De Los Artistas & Cumbia rocha", full, "La Juntada De Los Artistas, Candu Dominguez & G Sony", "LIT KILLAH, PAULO LONDRA, KHEA"]:
        artists, warning = _ada_artists(raw, "Not evidence")
        assert len(artists) >= 2 and warning is None
    artists, warning = _ada_artists(cut, "SOFI B / Enganchado En Vivo en LA JUNTADA DE LOS ARTISTAS")
    assert warning and "Sofi B" not in artists, "Project title invented a participant"
    print("PASSED: Excel-only ADA, identity, money, periods, taxonomy and evidence-based participants")


if __name__ == "__main__":
    main()
