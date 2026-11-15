"""Read complete source occurrences from the report's pinned BigQuery tables."""

from pathlib import Path

import polars as pl
import pyarrow.parquet as pq
from google.cloud import bigquery

from app.royalty_scope import use_scope
from scripts.lib.product_income import ISRC
from scripts.lib.dashgo_video_identity import compile_video_groups
from . import projection as codec
from .archive_query import source_query
from .large_read import MIN_EXPORT_ROWS, parquet_batches
from .publication import LABELS, PublicationError, file_sha, read_json, write_json
from .transport import arrow_batches, use_storage_read_api


DASHGO_GROUP_FIELDS = frozenset({
    "source", "account", "Track Title", "track_statement_style", "asset_title_statement",
    "dsp_normalized", "store_name", "Store", "store", "asset_isrc", "ISRC", "Asset ISRC",
    "product_upc", "UPC", "Product UPC", "track_id", "label_track_id", "Label Track ID",
    "video_id", "Video ID", "VideoId", "YOUTUBE VIDEO ID", "YouTube Video ID",
    "channel_id", "Channel ID", "ChannelId", "YOUTUBE CHANNEL ID",
})


def read_dashgo_groups(publications, release, folder):
    """Use all DashGo identity evidence in the publication before any report filters."""
    folder.mkdir(parents=True, exist_ok=True)
    target, receipt = folder / "dashgo_groups.parquet", folder / "dashgo_groups.json"
    if receipt.exists():
        if read_json(receipt)["sha256"] != file_sha(target):
            raise PublicationError("Cambió la evidencia de video de la publicación.")
        return pl.read_parquet(target)
    manifest = release["components"]["raw"]["manifest"]
    fields = [field for field in manifest["fields"] if field["name"] in DASHGO_GROUP_FIELDS]
    source = next(field["column"] for field in fields if field["name"] == "source")
    names = [field["column"] for field in fields if field["column"]]
    if len(names) != len(fields):
        names.append("_source_extension_json")
    selected = ", ".join(f"`{name}`" for name in names)
    table = publications.component_table(release, "raw")
    query = publications.client.query(
        f"SELECT DISTINCT {selected} FROM `{table}` WHERE TRIM(`{source}`)='dashgo'",
        location="US", job_config=bigquery.QueryJobConfig(labels=LABELS, maximum_bytes_billed=100_000_000_000),
    )
    rows = pl.from_arrow(query.result(timeout=900).to_arrow(create_bqstorage_client=False))
    native = codec.restore(rows.with_row_index("_origin_position").lazy(), {"fields": fields})
    groups = compile_video_groups(native)
    groups.write_parquet(target)
    write_json(receipt, {"sha256": file_sha(target), "query_id": query.job_id, "table": table,
                         "groups": groups.height, "identity_occurrences": rows.height})
    return groups


def product_text_sql(fields,*names):
    values=[f"NULLIF(TRIM(CAST(`{fields[n]}` AS STRING)),'')" for n in names if fields.get(n)]
    return 'COALESCE('+','.join(values)+')' if len(values)>1 else values[0] if values else 'CAST(NULL AS STRING)'


def product_key_sql(fields):
    def text(*names):return product_text_sql(fields,*names)
    upc=text('product_upc','UPC Code','UPC','Product UPC','upc')
    native=text('catalog_number','Catalogue Number','Catalog Number')
    source=text('source');account=text('account')
    return (f"CASE WHEN REGEXP_CONTAINS({upc},r'^(?:[0-9]{{8}}|[0-9]{{12,14}})$') AND SAFE_CAST({upc} AS INT64)!=0 "
            f"THEN CONCAT('UPC:',LPAD({upc},14,'0')) WHEN {source}='ada' AND {native} IS NOT NULL "
            f"THEN CONCAT('ADA:',{account},':',{native}) END")


def product_extra_candidates_sql(fields,parameter='candidate_products'):
    isrc=product_text_sql(fields,'asset_isrc','isrc','ISRC')
    return ('('+product_key_sql(fields)+f') IN UNNEST(@{parameter}) AND '
            f"NOT REGEXP_CONTAINS(COALESCE({isrc},''),@candidate_isrc_pattern)")


def coalesced_batches(batches,size=16384):
    import pyarrow as pa
    pending=[];rows=0
    for batch in batches:
        pending.append(batch);rows+=len(batch)
        if rows>=size:
            table=pa.Table.from_batches(pending).combine_chunks();pending=[];rows=0
            yield from table.to_batches(max_chunksize=size)
    if pending:
        yield from pa.Table.from_batches(pending).combine_chunks().to_batches(max_chunksize=size)


def order_completed_files(target, positions, rows):
    ordinal=pl.read_parquet(positions,columns=["_origin_position"])["_origin_position"]
    assert len(ordinal)==ordinal.n_unique()==rows
    if ordinal.is_sorted():return
    # Sort a narrow index, then gather bounded batches of the wide source.
    import pyarrow as pa
    import pyarrow.dataset as ds
    physical=pl.DataFrame({"_origin_position":ordinal}).with_row_index("_physical").sort("_origin_position")["_physical"]
    dataset=ds.dataset(str(positions),format="parquet")
    sorted_path=positions.with_suffix(".ordered.parquet");source_path=target.with_suffix(".ordered.parquet")
    ordered_writer=source_writer=None
    try:
        for offset in range(0,rows,16384):
            table=dataset.take(pa.array(physical.slice(offset,16384).to_list(),type=pa.int64()),batch_size=16384,batch_readahead=1,fragment_readahead=1,use_threads=False)
            source_table=table.drop(["_origin_position"])
            if ordered_writer is None:
                ordered_writer=pq.ParquetWriter(sorted_path,table.schema,compression="zstd")
                source_writer=pq.ParquetWriter(source_path,source_table.schema,compression="zstd")
            ordered_writer.write_table(table);source_writer.write_table(source_table)
    finally:
        if ordered_writer is not None:ordered_writer.close();source_writer.close()
    sorted_path.replace(positions);source_path.replace(target)


def read_source(publications, release, kind, params, report, folder, *, export_bucket=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    manifest = release["components"][kind]["manifest"]
    target = folder / f"{kind}.parquet"
    positions = folder / f"{kind}_positions.parquet"
    receipt = folder / f"{kind}_read.json"
    if receipt.exists():
        saved = read_json(receipt)
        if file_sha(target) != saved["sha256"]:
            raise PublicationError("Cambió la lectura guardada del reporte.")
        return target
    paths = publications.paths(release)
    marts = {role.removeprefix("marts/"): path for role, path in paths.items() if role.startswith("marts/")}
    candidate = dict(params, mode="any")
    table = publications.component_table(release, kind)
    with use_scope(release["scope"], marts=marts, release_id=release["source_release_id"]):
        sql, arguments = source_query(table, kind, manifest, candidate, report)
    if kind == "raw" and candidate["keywords"]:
        products = list(read_json(marts["product_income_allocations.json"])["products"])
        if products:
            fields = {field["name"]: field["column"] for field in manifest["fields"] if field["column"]}
            selected = ", ".join(chr(96) + field["name"] + chr(96) for field in codec.bigquery_schema(manifest))
            marker = "SELECT " + selected + " FROM searchable WHERE "
            before, order = sql.rsplit(" ORDER BY _origin_position", 1)
            head, predicate = before.rsplit(marker, 1)
            sql = head + marker + "(" + predicate + ") OR (" + product_extra_candidates_sql(fields) + ") ORDER BY _origin_position" + order
            arguments.extend([
                bigquery.ArrayQueryParameter("candidate_products", "STRING", products),
                bigquery.ScalarQueryParameter("candidate_isrc_pattern", "STRING", ISRC.pattern),
            ])
    config = bigquery.QueryJobConfig(query_parameters=arguments, labels=LABELS, maximum_bytes_billed=100_000_000_000)
    query = publications.client.query(sql, job_config=config, location="US")
    result = query.result(timeout=1800)
    rows = 0
    use_export = export_bucket and result.total_rows >= MIN_EXPORT_ROWS
    if result.total_rows:
        source_writer = position_writer = None
        try:
            if use_export:
                batches = parquet_batches(publications.client, query.destination, export_bucket, folder)
            else:
                iterator = publications.client.list_rows(query.destination)
                batches = arrow_batches(iterator, publications.client._credentials)
            for batch in coalesced_batches(batches):
                frame = pl.from_arrow(batch).sort("_origin_position")
                restored = codec.restore(frame.lazy(), manifest).collect()
                ordinary = restored.to_arrow()
                positioned = restored.with_columns(frame["_origin_position"]).to_arrow()
                if source_writer is None:
                    source_writer = pq.ParquetWriter(target, ordinary.schema, compression="zstd")
                    position_writer = pq.ParquetWriter(positions, positioned.schema, compression="zstd")
                source_writer.write_table(ordinary)
                position_writer.write_table(positioned)
                rows += len(frame)
        finally:
            if source_writer is not None:
                source_writer.close()
                position_writer.close()
        if rows != result.total_rows:
            raise PublicationError("La lectura de BigQuery quedó incompleta.")
        order_completed_files(target, positions, rows)
    else:
        schema = {field["name"]: codec.SUPPORTED_TYPES[field["polars_type"]][0] for field in manifest["fields"]}
        pl.DataFrame(schema=schema).write_parquet(target)
    write_json(receipt, {"rows": rows, "query_id": query.job_id, "table": table, "sha256": file_sha(target),
                         "transport": "parquet_export" if use_export else "storage_api" if use_storage_read_api() else "rest"})
    return target
