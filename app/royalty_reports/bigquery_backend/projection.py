"""Local, reversible source projection prepared for a separate BigQuery test table."""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

import polars as pl


SUPPORTED_TYPES = {
    "UInt32": (pl.UInt32, "INT64"),
    "String": (pl.String, "STRING"),
    "Int64": (pl.Int64, "INT64"),
    "Float64": (pl.Float64, "FLOAT64"),
    "Boolean": (pl.Boolean, "BOOL"),
}


def referenced_fields(repo: Path) -> set[str]:
    """Promote named fields used by report code, retaining every other field as well."""
    paths = list((repo / "app/royalty_reports").glob("*.py"))
    paths += list((repo / "scripts").glob("build_*report*.py"))
    paths += list((repo / "scripts/lib").glob("*.py"))
    result = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        result.update(node.value for node in ast.walk(tree)
                      if isinstance(node, ast.Constant) and isinstance(node.value, str))
    return result


def field_alias(name: str, dtype: str) -> str:
    readable = re.sub("[^a-z0-9]+", "_", name.lower()).strip("_")[:90]
    suffix = hashlib.sha256((name + "|" + dtype).encode()).hexdigest()[:10]
    return f"raw_{readable}_{dtype.lower()}_{suffix}"


def prepare_manifest(schema: pl.Schema, *, repo: Path, source: dict,
                     release_id: str, selection: dict) -> dict:
    promoted = referenced_fields(repo)
    fields = []
    for name, dtype in schema.items():
        if str(dtype) not in SUPPORTED_TYPES:
            raise ValueError(f"Tipo de origen sin soporte comprobado: {name} {dtype}")
        native = name in promoted
        fields.append({"name": name, "polars_type": str(dtype),
                       "bigquery_type": SUPPORTED_TYPES[str(dtype)][1],
                       "column": field_alias(name, str(dtype)) if native else None})
    schema_json = json.dumps(fields, ensure_ascii=False, sort_keys=True)
    schema_id = hashlib.sha256(schema_json.encode()).hexdigest()
    source_id = source["uri"] + "#" + str(source["generation"])
    return {"projection_version": 2, "release_id": release_id,
            "schema_id": schema_id, "source_id": source_id,
            "source": source, "selection": selection, "fields": fields}


def project(frame: pl.LazyFrame, manifest: dict) -> pl.LazyFrame:
    """Call with row positions assigned before any filter or row multiplication."""
    fields = manifest["fields"]
    names = {f["name"] for f in fields}
    extension = [f["name"] for f in fields if f["column"] is None]
    position = pl.col("_origin_position").cast(pl.Int64)
    expressions = [
        pl.lit(manifest["release_id"]).alias("_release_id"),
        pl.lit(manifest["schema_id"]).alias("_schema_id"),
        pl.lit(manifest["source_id"]).alias("_source_id"),
        position.alias("_origin_position"),
        pl.concat_str([pl.lit(manifest["source_id"] + ":"), position.cast(pl.String)])
        .alias("_source_record_key"),
    ]
    for original, target in [("statement_period", "_statement_month"),
                             ("transaction_month", "_transaction_month")]:
        value = (pl.col(original).cast(pl.String).str.slice(0, 7)
                 if original in names else pl.lit(None, dtype=pl.String))
        expressions.append(value.alias(target))
    expressions += [pl.col(f["name"]).alias(f["column"]) for f in fields if f["column"]]
    payload = pl.struct(extension).struct.json_encode() if extension else pl.lit("{}")
    expressions.append(payload.alias("_source_extension_json"))
    return frame.select(expressions)


def restore(frame: pl.LazyFrame, manifest: dict) -> pl.LazyFrame:
    fields = manifest["fields"]
    extension = [f for f in fields if f["column"] is None]
    # Restore source positions explicitly after a BigQuery SELECT with no natural order.
    frame = frame.sort("_origin_position")
    if extension:
        schema = pl.Struct([pl.Field(f["name"], SUPPORTED_TYPES[f["polars_type"]][0])
                            for f in extension])
        frame = frame.with_columns(
            pl.col("_source_extension_json").str.json_decode(schema).alias("_extension")
        ).unnest("_extension")
    return frame.select([
        pl.col(f["column"] or f["name"])
        .cast(SUPPORTED_TYPES[f["polars_type"]][0]).alias(f["name"])
        for f in fields
    ])


def bigquery_schema(manifest: dict) -> list[dict]:
    fields = [{"name": name, "type": dtype, "mode": "REQUIRED"}
              for name, dtype in [("_release_id", "STRING"), ("_schema_id", "STRING"),
                                  ("_source_id", "STRING"), ("_origin_position", "INT64"),
                                  ("_source_record_key", "STRING")]]
    fields += [{"name": name, "type": "STRING", "mode": "NULLABLE"}
               for name in ["_statement_month", "_transaction_month"]]
    fields += [{"name": f["column"], "type": f["bigquery_type"], "mode": "NULLABLE"}
               for f in manifest["fields"] if f["column"]]
    fields.append({"name": "_source_extension_json", "type": "STRING", "mode": "REQUIRED"})
    return fields
