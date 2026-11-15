"""Compare the actual browser download with an independently generated legacy Excel."""

from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from openpyxl import load_workbook
import polars as pl
import psycopg
from pyarrow.parquet import ParquetFile

from app.royalty_reports.bigquery_backend.publication import file_sha, read_json, write_json
from scripts.qa.royalty_bigquery_app_preview import CONFIG, INGEST_SCENARIO, PGDATA, RUNTIME


def compare_native_movements(before, after, *, exclude=()):
    with ParquetFile(before) as native, ParquetFile(after) as ingested:
        if native.schema_arrow != ingested.schema_arrow:
            raise AssertionError("La ingesta cambió el esquema nativo.")
        columns = [name for name in native.schema_arrow.names if name not in exclude]
        rows = 0
        before_batches = native.iter_batches(batch_size=16_384, columns=columns)
        after_batches = ingested.iter_batches(batch_size=16_384, columns=columns)
        for a, b in zip(before_batches, after_batches, strict=True):
            if not pl.from_arrow(a).equals(pl.from_arrow(b)):
                raise AssertionError(f"La ingesta cambió valores nativos a partir del bloque de la fila {rows}.")
            rows += a.num_rows
        return {"rows": rows, "fields": len(columns), "strict_values_types_and_positions_equal": True}


def workbook_values(path):
    book = load_workbook(path, read_only=True, data_only=False)
    try:
        sheets = {}
        for sheet in book.worksheets:
            cells = iter(sheet.iter_rows())
            header = tuple(c.value for c in next(cells))
            ignored = {i for i, title in enumerate(header) if title == "Generado el"}
            data = [tuple((c.value, c.data_type, getattr(c, "number_format", None))
                          for i, c in enumerate(row) if i not in ignored) for row in cells]
            sheets[sheet.title] = (header, data)
        return sheets
    finally:
        book.close()


def layout(path, count):
    with ZipFile(path) as book:
        entries = []
        for i in range(1, count + 1):
            root = ET.fromstring(book.read(f"xl/worksheets/sheet{i}.xml"))
            entries.append({node.tag.rsplit("}", 1)[-1]: ET.tostring(node) for node in root
                            if not node.tag.endswith("}sheetData")})
        return book.read("xl/styles.xml"), entries


def changed_widths(before, after):
    old, new = ET.fromstring(before), ET.fromstring(after)
    result = {}
    for a, b in zip(old, new, strict=True):
        left, right = dict(a.attrib), dict(b.attrib)
        w1, w2 = left.pop("width"), right.pop("width")
        if a.tag != b.tag or left != right or left["min"] != left["max"]:
            raise AssertionError("Cambió un atributo de columna distinto del ancho.")
        if w1 != w2:
            result[int(left["min"])] = {"legacy": w1, "bigquery": w2}
    return result


def compare_workbooks(before, after, *, allow_rounded_units=False, allow_rounding_widths=False,
                      numeric_tolerance=Decimal("0.000000000001")):
    native, observed = (workbook_values(path) for path in (before, after))
    if list(native) != list(observed):
        raise AssertionError("Cambiaron las hojas del informe.")
    old_styles, old_layout = layout(before, len(native))
    new_styles, new_layout = layout(after, len(native))
    comparisons = {}
    for i, (name, (headers, rows)) in enumerate(native.items()):
        other_header, other_rows = observed[name]
        lhs, rhs = Counter(rows), Counter(other_rows)
        missing, extra = lhs - rhs, rhs - lhs
        changed_layout = sorted(k for k in set(old_layout[i]) | set(new_layout[i])
                                if old_layout[i].get(k) != new_layout[i].get(k))
        comparisons[name] = {"rows": len(rows), "other_rows": len(other_rows), "columns": len(headers),
                             "headers_equal": headers == other_header, "positions_equal": rows == other_rows,
                             "missing_occurrences": missing.total(), "extra_occurrences": extra.total(),
                             "layout_differences": changed_layout}
        compared_headers = [title for title in headers if title != "Generado el"]
        differences = []
        unit_differences = []
        rounding_columns = set()
        if name == "detalle":
            accepted = not (missing or extra)
        else:
            accepted = len(rows) == len(other_rows)
            for a, b in zip(rows, other_rows):
                if len(a) != len(b) or len(a) != len(compared_headers):
                    accepted = False
                    break
                for title, left, right in zip(compared_headers, a, b, strict=True):
                    if left == right:
                        continue
                    first, second = left[0], right[0]
                    currency = title == "Ingresos USD" and left[1:] == right[1:] == ("n", "$#,##0.00")
                    units = (allow_rounded_units and title == "Unidades"
                             and left[1:] == right[1:] == ("n", "#,##0"))
                    if (currency or units) and type(first) in (int, float) and type(second) in (int, float):
                        x, y = Decimal(str(first)), Decimal(str(second))
                        delta = abs(x - y)
                        scale = Decimal("0.01") if currency else Decimal("1")
                        if (delta <= numeric_tolerance
                                and x.quantize(scale, rounding=ROUND_HALF_UP) == y.quantize(scale, rounding=ROUND_HALF_UP)):
                            (differences if currency else unit_differences).append(delta)
                            rounding_columns.add(headers.index(title) + 1)
                            continue
                    accepted = False
        allowed_layout = not changed_layout or name == "detalle" and changed_layout == ["cols"]
        if allow_rounding_widths and name != "detalle" and changed_layout == ["cols"]:
            widths = changed_widths(old_layout[i]["cols"], new_layout[i]["cols"])
            allowed_layout = set(widths) <= rounding_columns
            comparisons[name]["column_width_changes"] = {headers[k - 1]: v for k, v in widths.items()}
        comparisons[name].update(
            data_match_at_excel_precision=accepted, rounding_cells=len(differences),
            max_rounding_delta_usd=str(max(differences, default=Decimal(0))),
            unit_rounding_cells=len(unit_differences),
            max_rounding_delta_units=str(max(unit_differences, default=Decimal(0))),
            layout_match_with_known_widths=allowed_layout,
        )
        if not accepted:
            comparisons[name].update(missing_examples=list(missing)[:2], extra_examples=list(extra)[:2])
    strict = all(r["headers_equal"] and r["missing_occurrences"] == r["extra_occurrences"] == 0
                 and (n == "detalle" or r["positions_equal"]) for n, r in comparisons.items())
    passed = old_styles == new_styles and all(
        r["headers_equal"] and r["data_match_at_excel_precision"] and r["layout_match_with_known_widths"]
        for r in comparisons.values())
    return {"passed": passed, "strict_data_equal": strict, "sheets": comparisons, "styles_equal": old_styles == new_styles,
            "generation_timestamp_excluded": True, "numeric_tolerance_usd": str(numeric_tolerance)}


def main():
    if not INGEST_SCENARIO:
        raise RuntimeError("La comparación requiere la copia de ingesta.")
    legacy = read_json(RUNTIME / "legacy_excel.json")
    ingested = read_json(RUNTIME / "ingest_to_bigquery.json")
    staged = read_json(RUNTIME / "staged_statement.json")
    release = ingested["release_id"]
    publication_id = ingested["publication_id"]
    assert release == legacy["release_id"]
    assert staged["pointer"]["fingerprint"] == ingested["input_fingerprint"]
    assert read_json(RUNTIME / "before_activation.json")["report_publication_active"] is False
    assert read_json(RUNTIME / "active/wml.json")["id"] == publication_id
    accepted = read_json(RUNTIME / "publication_status" / (publication_id + ".json"))
    assert accepted["status"] == "ready"
    assert accepted["tables"]["raw"]["binding"]["rows"] == ingested["native_rows"]
    folder = RUNTIME / "browser/wml-new-statement"
    browser = read_json(folder / "acceptance.json")
    terminal = read_json(folder / "terminal.json")
    assert terminal["engine_version"] == "bigquery" and terminal["status"] == "completed"
    assert all(terminal["params"][key] == value for key, value in legacy["params"].items()
               if key != "keywords")
    assert [k.casefold() for k in terminal["params"]["keywords"]] == [k.casefold() for k in legacy["params"]["keywords"]]
    config = read_json(CONFIG)
    with psycopg.connect(host="127.0.0.1", port=config["pg_port"], user="report_preview",
                         password=config["pg_password"], dbname="postgres") as db:
        assert Path(db.execute("SHOW data_directory").fetchone()[0]).resolve() == PGDATA.resolve()
        pin = db.execute("SELECT input_manifest_json #>> '{report_publication,publication_id}' FROM report_runs WHERE id=%s",
                         (browser["job"],)).fetchone()[0]
    assert pin == publication_id
    table = "standardized_raw_all_sources.parquet"
    native_before = RUNTIME / "system_current_data/releases" / release / table
    native_after = RUNTIME / "contexts" / release / table
    native = compare_native_movements(native_before, native_after)
    assert native["rows"] == ingested["native_rows"]
    actual, = browser["automatic_downloads"]
    previous, current = Path(legacy["xlsx"]), Path(actual["path"])
    result = compare_workbooks(previous, current)
    receipt = {"comparison": result, "native_ingest": native, "report_job": browser["job"],
               "native_release": release, "report_publication": pin,
               "current_system_xlsx": {"path": str(previous), "sha256": file_sha(previous)},
               "browser_xlsx": {"path": str(current), "sha256": file_sha(current)},
               "native_commit": legacy["commit"], "params": terminal["params"],
               "input_sha256": staged["input"]["files"][0]["sha256"]}
    write_json(RUNTIME / "statement_report_comparison.json", receipt)
    assert result["passed"], "Hay diferencias en el Excel. Revisar el recibo por hoja."
    print("Excel y movimientos nativos comparados", result["sheets"]["detalle"]["rows"], flush=True)


if __name__ == "__main__":
    main()
