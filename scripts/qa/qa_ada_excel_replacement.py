from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from decimal import Decimal
from pathlib import Path

import polars as pl
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from ingest_standardized_ada import read_statement, select_statement_files, standardize, NO_ACTIVITY_MESSAGE
from lib.ada_identity import ada_catalog_key_expr
from lib.catalog_report_filter import row_catalog_key_expr
from build_keyword_royalty_report import add_report_code, contains_expr
from app.master_contracts import _ada_artists


ECONOMIC_FIELDS = [
    "ISRC", "Catalog Number", "Repdate Month ID", "Digital Service Provider(DSP)",
    "Country", "Price Desc", "Dist Chan Desc", "Sale Units", "Royalty Payable",
    "Deductible Fees", "Net Royalty Payable",
]
NUMERIC_FIELDS = set(ECONOMIC_FIELDS[-4:])


def economic_rows(frame: pl.DataFrame) -> Counter:
    return Counter(
        tuple(
            Decimal(str(row.get(name) or 0)) if name in NUMERIC_FIELDS
            else str(row.get(name) or "").strip()
            for name in ECONOMIC_FIELDS
        )
        for row in frame.iter_rows(named=True)
    )


def fixture(path: Path, account: str = "99500", fee: float = 0) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Distribution Statement"
    sheet.append(["Royalties Statement for Period:", "07/26 - 07/26"])
    sheet.append(["Contract:", f"{account}-TEST"])
    sheet.append([
        "Artist Name", "Project Title", "Catalogue Number", "ISRC", "Catalogue Title",
        "Reported Month", "Territory", "Country Code", "Sales", "Receipts Value",
        "Distribution Fees", "Mechanical Fees", "Artist Royalties", "Parent Product ID",
    ])
    sheet.append(["Artist & Guest", "Album", "A123", None, "Track", "202605", "Spotify", "AR", 2, 0.21, 0.021, fee, 0, "8718521191726"])
    for label in ["Sub Totals:", "Previously Accounted Deductions:", "Totals:"]:
        sheet.append([None] * 10 + [label])
    workbook.save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        excel = root / "99500_202607_202607_99500_DTL.xlsx"
        fixture(excel)
        frame = read_statement(excel)
        assert frame.height == 1
        assert frame["Net Royalty Payable"][0] == 0.189
        assert frame["Repdate Month ID"][0] == "2026-05"
        assert frame["parent_product_id"][0] == "8718521191726"
        assert frame["ada_explicit_upc"][0] is None
        normalized = standardize(frame, excel, "indyana_records", "99500", {"revenue_basis": "generation", "cash_view": True, "catalog_view": True, "statement_view": True})
        assert normalized["product_upc"][0] == "8718521191726"
        assert normalized["product_upc_source"][0] == "Parent Product ID"
        assert normalized["amount_usd"][0] == 0.189 and normalized["units"][0] == 2
        assert normalized["transaction_month"][0] == "2026-05"
        assert normalized["statement_period"][0] == "2026-07"
        assert normalized.select(ada_catalog_key_expr(set(normalized.columns)).alias("key"))["key"][0] == "ADA:99500:CATALOG:A123"
        wrong_period = root / "99500_202608_202608_99500_DTL.xlsx"
        fixture(wrong_period)
        try:
            read_statement(wrong_period)
            raise AssertionError("Wrong statement period was accepted")
        except ValueError:
            pass
        wrong_period.unlink()
        txt = root / "Statement_99500_5779_99500_20260731.txt"
        txt.write_text(NO_ACTIVITY_MESSAGE, encoding="utf-8")
        assert read_statement(txt) is None
        pl.DataFrame({
            "Account": ["99500"], "Start Period": ["2026-07"], "End Period": ["2026-07"],
            "Repdate Month ID": ["2026-05"], "Recdate Month ID": ["2026-07"],
            "ISRC": [None], "Catalog Number": ["A-FUTURE"], "GPID": ["0085365665804"],
            "Product Title": ["New Album"], "Project Title": ["New Album"],
            "Artist Name": ["New Artist"], "Digital Service Provider(DSP)": ["i-Tunes"],
            "Sale Units": [2], "Royalty Payable": [2.1], "Deductible Fees": [0.21],
            "Net Royalty Payable": [1.89],
        }).write_csv(txt, separator="\t")
        future_txt = read_statement(txt)
        assert future_txt["GPID"][0] == "0085365665804", "Numeric-only TXT lost leading zeros"
        future_normalized = standardize(future_txt, txt, "indyana_records", "99500", {"revenue_basis": "generation"})
        assert future_normalized["product_upc"][0] == "0085365665804"
        assert future_normalized["product_upc_source"][0] == "GPID"
        assert future_normalized["asset_isrc"][0] is None and future_normalized["amount_usd"][0] == 1.89
        assert future_normalized["transaction_month"][0] == "2026-05" and future_normalized["statement_period"][0] == "2026-07"
        for broken in [
            future_txt.with_columns(pl.lit(1.88).alias("Net Royalty Payable")),
            future_txt.with_columns(pl.lit("not money").alias("Net Royalty Payable")),
            future_txt.with_columns(pl.lit("2026-13").alias("Repdate Month ID")),
        ]:
            try:
                standardize(broken, txt, "indyana_records", "99500", {"revenue_basis": "generation"})
                raise AssertionError("Invalid future statement was accepted")
            except ValueError:
                pass
        assert select_statement_files(root) == [excel]
        duplicate = root / "Statement_99500_9999_99500_20260731.txt"
        duplicate.touch()
        try:
            select_statement_files(root)
            raise AssertionError("Duplicate statements were accepted")
        except ValueError:
            pass
        fixture(excel, account="99205")
        try:
            read_statement(excel)
            raise AssertionError("Wrong account was accepted")
        except ValueError:
            pass
        fixture(excel, fee=0.01)
        try:
            read_statement(excel)
            raise AssertionError("Unreviewed fees were accepted")
        except ValueError:
            pass

    identities = pl.DataFrame({
        "source": ["ada", "ada", "ada", "ada", "fuga"],
        "account": ["indyana_records", "indyana_records", "mawz", "mawz", "indyana_records"],
        "asset_isrc": ["BK4DA2658497", None, None, "BK4DA2658493", None],
        "catalog_number": ["A1", "A2", "A2", "A3", "A2"],
        "gpid": [None, "8718521191726", "1234567890123", None, None],
        "track_id": ["A1", "8718521191726", "1234567890123", "A3", "abcdefghijk"],
        "track_statement_style": ["Song"] * 5,
        "artist_statement_style": ["Artist"] * 5,
    })
    schema = set(identities.columns)
    keys = identities.select(ada_catalog_key_expr(schema).alias("key"))["key"].to_list()
    assert keys == ["ISRC:BK4DA2658497", "ADA:99500:CATALOG:A2", "ADA:99205:CATALOG:A2", "ISRC:BK4DA2658493", None]
    assert identities.select(row_catalog_key_expr(schema).alias("key"))["key"].to_list()[-1] == "VIDEO:abcdefghijk"
    changed_title = identities.with_columns(pl.lit("Different title").alias("track_statement_style"))
    assert changed_title.select(ada_catalog_key_expr(schema).alias("key"))["key"].to_list() == keys
    report = add_report_code(identities.lazy(), schema).collect()
    assert report["report_code"][1] == "A2"
    assert report["report_code_source"][1] == "ADA Catalog Number"
    assert identities.filter(contains_expr(schema, [], "A2")).height == 2
    assert identities.filter(contains_expr(schema, [], "8718521191726")).height == 1
    for raw, expected in [
        ("La Juntada De Los Artistas & Cumbia rocha", ["La Juntada de los Artistas", "Cumbia rocha"]),
        ("La Juntada De Los Artistas & Sofi B", ["La Juntada de los Artistas", "Sofi B"]),
        ("La Juntada De Los Artistas, Candu Dominguez & G Sony", ["La Juntada de los Artistas", "Candu Dominguez", "G Sony"]),
    ]:
        artists, warning = _ada_artists(raw, "Release")
        assert [name.casefold() for name in artists] == [name.casefold() for name in expected]
        assert warning is None

    result = []
    if args.input:
        files = list(args.input.glob("*.txt"))
        for excel in sorted(args.input.glob("*.xlsx")):
            month = excel.name.split("_")[1]
            txt = next(path for path in files if f"_{month}" in path.name)
            old, new = read_statement(txt), read_statement(excel)
            before, after = economic_rows(old), economic_rows(new)
            assert before == after, {
                "file": excel.name, "missing": list((before - after).items())[:2],
                "added": list((after - before).items())[:2],
            }
            result.append({"file": excel.name, "rows": new.height, "net_usd": new["Net Royalty Payable"].sum()})
    print(json.dumps({"status": "passed", "excel_txt_economic_equivalence": result}, ensure_ascii=True))


if __name__ == "__main__":
    main()
