"""Read native cells before interpretation; identifiers must never be inferred as numbers."""
from pathlib import Path
import polars as pl


def read_native_csv(path: Path, *, encoding: str = "utf8") -> pl.DataFrame:
    # A numeric prefix is not evidence that the rest of an identifier column is
    # numeric. Keep every lexical cell; source-specific parsers cast measures.
    return pl.read_csv(path, separator=",", quote_char='"', infer_schema=False,
                       ignore_errors=False, encoding=encoding)


def clean_native_headers(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.rename({name: name.replace("\ufeff", "").strip().strip('"')
                         for name in frame.columns})
