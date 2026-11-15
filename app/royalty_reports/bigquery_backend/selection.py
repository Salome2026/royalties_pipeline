"""Bounded projection of the native summary selection and public detail."""

from dataclasses import dataclass
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from .delivery import DetailRows


@dataclass(frozen=True)
class SpooledSelection:
    summary: Path
    detail: DetailRows


def write_selection(report, prepared: Path, params: dict, directory: Path) -> SpooledSelection | None:
    source = pq.ParquetFile(prepared)
    if source.metadata.num_rows == 0:
        return None
    if "_income_allocated" not in source.schema.names:
        raise ValueError("El detalle debe usar la selección original con el reparto ya aplicado.")
    directory.mkdir(parents=True, exist_ok=True)
    summary_path = directory / "summary.parquet"
    detail_path = directory / "detail.parquet"
    summary_writer = detail_writer = None
    headers = None
    detail_count = summary_count = 0
    period = params["period_basis"]
    selection = {key: params[key] for key in ("keywords", "mode", "start_month", "end_month", "source", "account")}
    try:
        for batch in source.iter_batches(batch_size=8192, use_threads=False):
            raw = pl.from_arrow(batch).lazy()
            summary = report.build_summary_selection(
                raw, set(raw.collect_schema().names()), period_column=period, excluded_isrcs=[], **selection
            ).collect(engine="streaming")
            summary_arrow = summary.to_arrow()
            if summary_writer is None:
                summary_writer = pq.ParquetWriter(summary_path, summary_arrow.schema, compression="zstd")
            summary_writer.write_table(summary_arrow)
            summary_count += summary.height

            detail, columns = report.build_filtered_raw_detail_lf(
                standardized_path=prepared, period_basis=period, raw=raw, **selection
            )
            public_columns = report.public_detail_columns(columns, include_statement_metadata=period == "statement_period")
            native = detail.select(public_columns).collect(engine="streaming")
            display = report.display_dataframe(native.to_pandas())
            if headers is None:
                headers = tuple(display.columns)
                schema = pa.schema([
                    pa.field(f"c{index}", pa.string() if pa.types.is_large_string(field.type) else field.type)
                    for index, field in enumerate(native.to_arrow().schema)
                ])
                detail_writer = pq.ParquetWriter(detail_path, schema, compression="zstd")
            elif headers != tuple(display.columns):
                raise ValueError("Las columnas del detalle cambiaron durante la generación.")
            display.columns = schema.names
            detail_writer.write_table(pa.Table.from_pandas(display, schema=schema, preserve_index=False))
            detail_count += len(display)
    finally:
        if summary_writer is not None:
            summary_writer.close()
        if detail_writer is not None:
            detail_writer.close()
    if detail_count != summary_count:
        raise ValueError("El resumen y el detalle completo tienen distintas cantidades.")
    return SpooledSelection(summary_path, DetailRows.from_parquet(detail_path, headers, detail_count))
