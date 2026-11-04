"""Recognize DashGo's native sales, footer controls and empty CSV records.

This changes admission only: no rows, cells, identities or measures are rewritten.
The legacy standardized output still preserves the complete native receipt.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

import polars as pl

from .ingestion_controls import IngestionControlError


CONTROL_LABELS = (
    "Gross Deal Revenue:", "Split Pay Revenue:",
    "Total Payable (US):", "Total Payable (NON-US):", "Total Payable:",
)
FOOTER = (None, CONTROL_LABELS[0], CONTROL_LABELS[1], None,
          CONTROL_LABELS[2], CONTROL_LABELS[3], None, CONTROL_LABELS[4])
CONTROL_NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?\Z", re.ASCII)


@dataclass(frozen=True)
class DashGoRowClasses:
    classes: tuple[str, ...]

    def sale_mask(self) -> pl.Series:
        return pl.Series("dashgo_sale", [kind == "sale" for kind in self.classes])


def classify_dashgo_rows(frame: pl.DataFrame, path: Path) -> DashGoRowClasses:
    """Require the certified physical footer before excluding any row from money validation.

    CSV record width matters: Polars pads the native 13-cell footer to the
    header width. Read the physical structure independently, then verify its
    complete positional correspondence with the frame being admitted.
    Decoding follows the existing reader; changing that reader is out of scope.
    """
    def reject(reason: str, row: int | None = None):
        raise IngestionControlError(
            "DASHGO_ROW_STRUCTURE", f"DashGo: {reason}, {path.name}. No se actualiza el lote.",
            file=path.name, csv_data_row=row,
        )

    try:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, None)
            records = list(reader)
    except csv.Error as error:
        reject(f"estructura CSV invalida ({error})")
    if not header or [name.strip() for name in header] != frame.columns:
        reject("cabecera original y lectura no coinciden")
    if len(records) != frame.height:
        reject("cantidad de registros original y lectura no coinciden")
    width = len(header)
    for position, (native, parsed) in enumerate(zip(records, frame.iter_rows()), start=1):
        if len(native) > width:
            reject("registro mas ancho que la cabecera", position)
        padded = native + [""] * (width - len(native))
        if any((actual if actual is not None else "") != expected
               for expected, actual in zip(padded, parsed)):
            reject("el registro leido no coincide con el original", position)

    if len(records) < len(FOOTER):
        reject("falta el pie completo certificado")
    start = len(records) - len(FOOTER)
    classes = []
    for position, record in enumerate(records[:start], start=1):
        if not record:
            classes.append("separator")
        elif len(record) != width:
            reject("registro corto fuera del pie certificado", position)
        elif any(value in CONTROL_LABELS for value in record):
            reject("control de pie fuera de su posicion certificada", position)
        else:
            # An absent/invalid Payable remains a sale, so validate_amounts rejects it.
            classes.append("sale")

    for offset, (record, label) in enumerate(zip(records[start:], FOOTER)):
        position = start + offset + 1
        if label is None:
            if record:
                reject("separador del pie no reconocido", position)
            classes.append("separator")
            continue
        if len(record) != 13 or any(record[:11]) or record[11] != label:
            reject("estructura, secuencia o etiqueta de control no reconocida", position)
        try:
            valid = bool(CONTROL_NUMBER.fullmatch(record[12])) and Decimal(record[12]).is_finite()
        except InvalidOperation:
            valid = False
        if not valid:
            reject("importe de control invalido", position)
        classes.append("control")
    return DashGoRowClasses(tuple(classes))
