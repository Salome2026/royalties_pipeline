"""Prepare a pinned, reconciled video-context repair in Cloud Run; never activate it.

The publisher identity only writes immutable GCS candidates. The ordinary BigQuery
release operator validates and activates a candidate separately, without granting
the API or its workers write access to financial BigQuery tables.
"""
from __future__ import annotations

from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import polars as pl
from google.cloud import storage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from scripts.lib.mart_release import new_release_id, validate_release_manifest
from scripts.lib.video_context import preserve_video_context
from lib.distributor_policy_store import load_distributor_policy_document, use_distributor_policy_snapshot
from scripts.load_bigquery_release import (
    SOURCE_FILES, build_detail, build_song, build_catalog, build_dashboard, build_digital,
)
from scripts.reconcile_bigquery_release import aggregate_local


def event(name: str, **values):
    print(json.dumps({'event': name, **values}, default=str), flush=True)


def totals(path: Path, amount: str = 'amount_usd') -> dict:
    lf = pl.scan_parquet(path)
    return lf.select(pl.len().alias('rows'), pl.col(amount).sum().alias('amount_usd')).collect().to_dicts()[0]


def rewrite_identity_batches(source: Path, target: Path, batch_size=25000):
    """Bound wide native rows in memory independently of the historical size."""
    import pyarrow.parquet as pq
    from scripts.lib.catalog_identity_corrections import correct_recording_identity
    writer = None
    try:
        for number, batch in enumerate(pq.ParquetFile(source).iter_batches(batch_size=batch_size, use_threads=False), 1):
            frame = preserve_video_context(correct_recording_identity(pl.from_arrow(batch)))
            table = frame.to_arrow()
            if writer is None:
                writer = pq.ParquetWriter(target, table.schema, compression='zstd')
            writer.write_table(table)
            if number % 100 == 0:
                event('identity_raw_batch', batch=number)
    finally:
        if writer is not None:
            writer.close()


def assert_money_preserved(before: Path, after: Path) -> None:
    def grouped(path):
        return pl.scan_parquet(path).group_by(['source', 'account', 'transaction_month']).agg(
            pl.col('amount_usd').sum(), pl.col('units').sum()).collect()
    diff = grouped(before).join(grouped(after), on=['source', 'account', 'transaction_month'],
                                how='full', coalesce=True, nulls_equal=True, suffix='_new')
    if diff.filter((pl.col('amount_usd') - pl.col('amount_usd_new')).abs().fill_null(float('inf')) > .01).height:
        raise RuntimeError('El reproceso cambia importes por cuenta y mes.')
    if diff.filter((pl.col('units') - pl.col('units_new')).abs().fill_null(float('inf')) > .0001).height:
        raise RuntimeError('El reproceso cambia unidades por cuenta y mes.')


def assert_dashboard_preserved(before: Path, after: Path) -> None:
    keys = ['source', 'account', 'statement_period', 'transaction_month', 'dsp',
            'monetization_normalized', 'content_origin_normalized', 'classification_status']
    def grouped(path):
        return pl.scan_parquet(path).group_by(keys).agg(
            pl.col('amount_usd').sum(), pl.col('units').sum(), pl.col('raw_rows').sum()).collect()
    diff = grouped(before).join(grouped(after), on=keys, how='full', coalesce=True,
                                nulls_equal=True, suffix='_new')
    for field, tolerance in [('amount_usd', .01), ('units', .0001), ('raw_rows', 0)]:
        delta = (pl.col(field).cast(pl.Float64) - pl.col(field + '_new').cast(pl.Float64)).abs()
        if diff.filter(delta.fill_null(float('inf')) > tolerance).height:
            raise RuntimeError(f'El reproceso cambia {field} del dashboard por origen, fuente y mes.')


def song_input_columns(source: str, available: set[str]) -> list[str]:
    """Do not materialize hundreds of other distributors' null columns in RAM."""
    common = {
        'source', 'account', 'statement_type', 'statement_period', 'transaction_month',
        'source_sheet', 'revenue_basis', 'include_in_cash_view', 'include_in_catalog_view',
        'include_in_statement_view', 'possible_internal_transfer', 'asset_isrc', 'product_upc',
        'track_statement_style', 'artist_statement_style', 'amount_usd', 'units', 'streams',
        'track_id', 'video_id', 'video_id_source', 'channel_id', 'dsp_normalized',
        'monetization_normalized', 'content_origin_normalized', 'classification_status',
    }
    extra = {
        'fuga': {'asset_product_type', 'product_title_statement', 'product_artist_statement',
                 'net_amount_eur', 'asset_quantity_num', 'asset_title_statement', 'asset_artist_statement'},
        'dashgo': {'ISRC', 'VideoId'},
        'orchard': set(),
        'soundon': {'artist_catalog_style', 'net_amount', 'gross_revenue_usd', 'artist_share_usd'},
        'ada': {'asset_title_statement', 'release_statement_style', 'catalog_number', 'ada_account_id',
                'parent_product_id', 'product_upc_source', 'product_upc_status', 'artist_statement_original',
                'artist_catalog_style', 'artist_credit_status', 'artist_credit_evidence_file',
                'net_amount', 'gross_royalty_usd', 'deductible_fees_usd'},
        'onerpm': {'ISRC', 'ID', 'Parent ID', 'Video ID', 'Channel ID', 'Track Title', 'Title',
                   'Video Title', 'Album Title', 'UPC', 'Store', 'Territory', 'Sale Type', 'Label',
                   'Product Type', 'Quantity', 'net_amount'},
    }
    return sorted(available & (common | extra[source]))


def run() -> None:
    client = storage.Client()
    bucket = client.bucket(os.environ.get('GCS_BUCKET', 'vpo-corp-royalties-marts'))
    prefix = os.environ.get('GCS_PREFIX', 'marts').strip('/')
    pointer = bucket.blob(f'{prefix}/release_manifest.json')
    pointer.reload()
    base_generation = str(pointer.generation)
    manifest = validate_release_manifest(json.loads(pointer.download_as_text()), SOURCE_FILES.values())
    status = bucket.blob(f'{prefix}/catalog_status.parquet')
    status_generation = '0'
    if status.exists():
        status.reload()
        status_generation = str(status.generation)
    policy = load_distributor_policy_document()
    release = new_release_id()
    event('repair_start', base_release=manifest['release_id'], release_id=release)

    with TemporaryDirectory(prefix='video-context-') as d:
        root = Path(d)
        original, updated, prepared = root/'original', root/'updated', root/'prepared'
        for folder in [original, updated, prepared]:
            folder.mkdir()
        for filename in SOURCE_FILES.values():
            item = manifest['files'][filename]
            bucket.blob(item['object_name'], generation=int(item['generation'])).download_to_filename(str(original/filename))
        # Keep every other immutable manifest entry and every catalog field verbatim.
        raw_name, song_name = SOURCE_FILES['detail'], SOURCE_FILES['song']
        raw_frame = pl.scan_parquet(original/raw_name)
        identity_repair = os.environ.get('VPO_RECORDING_IDENTITY_REPAIR') == '1'
        if identity_repair:
            rewrite_identity_batches(original/raw_name, updated/raw_name)
        else:
            preserve_video_context(raw_frame).sink_parquet(updated/raw_name, compression='zstd')
        if totals(original/raw_name)['rows'] != totals(updated/raw_name)['rows']:
            raise RuntimeError('El reproceso cambia la cantidad de filas originales.')
        assert_money_preserved(original/raw_name, updated/raw_name)
        if identity_repair and 'product_income_allocations.json' in manifest['files']:
            entry = manifest['files']['product_income_allocations.json']
            allocation = json.loads(bucket.blob(entry['object_name'], generation=int(entry['generation'])).download_as_text())
            from scripts.lib.catalog_identity_corrections import video_corrections
            corrected_codes = {code for r in video_corrections() for code in [r['canonical_isrc'], *r['reported_isrcs']]}
            if any(t.get('isrc') in corrected_codes for p in allocation['products'].values() for t in p.get('tracks', [])):
                raise RuntimeError('La grabacion corregida participa en un producto; revisar su asignacion antes de reconstruir.')
            allocation['source_size_bytes'] = (updated/raw_name).stat().st_size
            (updated/'product_income_allocations.json').write_text(json.dumps(allocation, sort_keys=True), encoding='utf-8')
            os.environ['VPO_PRODUCT_INCOME_PATH'] = str(updated/'product_income_allocations.json')
        event('raw_context_preserved', **totals(updated/raw_name))
        song_paths = []
        for source in (['fuga'] if identity_repair else ['ada', 'dashgo', 'fuga', 'onerpm', 'orchard', 'soundon']):
            module = importlib.import_module(f'scripts.build_song_level_{source}')
            module.INPUT_PATH = root/f'raw_{source}.parquet'
            module.OUTPUT_PATH = root/f'song_level_{source}.parquet'
            source_lf = pl.scan_parquet(updated/raw_name).filter(pl.col('source') == source)
            source_lf.select(song_input_columns(source, set(source_lf.collect_schema().names()))).sink_parquet(module.INPUT_PATH)
            module.main()
            song_paths.append(module.OUTPUT_PATH)
            module.INPUT_PATH.unlink()
        from scripts.build_consolidated_marts import consolidate
        if identity_repair:
            from scripts.lib.catalog_identity_corrections import correct_recording_identity
            fuga_song = pl.scan_parquet(song_paths[0])
            if 'mart_source_file' in pl.scan_parquet(original/song_name).collect_schema().names():
                fuga_song = fuga_song.with_columns(pl.lit('song_level_fuga.parquet').alias('mart_source_file'))
            corrected = correct_recording_identity(fuga_song)
            pl.concat([pl.scan_parquet(original/song_name).filter(pl.col('source') != 'fuga'), corrected],
                how='diagonal_relaxed').sink_parquet(updated/song_name, compression='zstd')
        else:
            consolidate(song_paths, updated/song_name)
        assert_money_preserved(original/song_name, updated/song_name)
        for path in song_paths:
            path.unlink()
        if identity_repair:
            from app.recording_identity_repair import rebuild_catalog
            with use_distributor_policy_snapshot(policy):
                result = rebuild_catalog(original/SOURCE_FILES['catalog'], updated/raw_name,
                    updated/song_name, updated/SOURCE_FILES['catalog'], root/'identity_catalog')
            event('recording_identity_rebuilt', **result)
        # Catalog metadata, approved relationships and monetary admission stay pinned.
        os.environ['VPO_CATALOG_MASTER_PATH'] = str((updated if identity_repair else original)/SOURCE_FILES['catalog'])
        os.environ['VPO_CATALOG_STATUS_PATH'] = str(root/'catalog_status.parquet')
        if status_generation != '0':
            bucket.blob(status.name, generation=int(status_generation)).download_to_filename(os.environ['VPO_CATALOG_STATUS_PATH'])
        from app import vpo_corp_api as api
        with use_distributor_policy_snapshot(policy):
            api.build_royalties_dashboard_summary_mart(updated/raw_name, refresh_cache=True,
                output_path=updated/SOURCE_FILES['dashboard'], partition_large_input=True)
        assert_dashboard_preserved(original/SOURCE_FILES['dashboard'], updated/SOURCE_FILES['dashboard'])
        builders = {'detail': build_detail, 'song': build_song, 'catalog': build_catalog,
                    'dashboard': build_dashboard, 'digital': build_digital}
        expected = {}
        for key, builder in builders.items():
            filename = SOURCE_FILES[key]
            source_path = updated/filename if (updated/filename).exists() else original/filename
            target = prepared/f'{key}.parquet'
            # build_detail independently reconciles native source quantities and IDs.
            builder(source_path, target, release)
            expected[key] = totals(target, 'total_usd' if key == 'digital' else 'amount_usd')
            event('prepared', table=key, **expected[key])
        from scripts.lib.bigquery_source_integrity import validate_detail_source
        # Check against the pre-repair published source too, not just our normalized copy.
        native_check = validate_detail_source(original/raw_name, prepared/'detail.parquet')
        reconciliation = []
        for column, basis in [('statement_month', 'statement_period'), ('transaction_month', 'transaction_month')]:
            reconciliation.extend(aggregate_local(prepared/'detail.parquet', column, basis))
        entries = dict(manifest['files'])
        def upload(path: Path, name: str) -> dict:
            blob = bucket.blob(name)
            blob.upload_from_filename(str(path), if_generation_match=0)
            blob.reload()
            return {'object_name': name, 'generation': str(blob.generation), 'size_bytes': blob.size,
                    'md5_hash': blob.md5_hash, 'crc32c': blob.crc32c}
        for path in updated.iterdir():
            entries[path.name] = upload(path, f'{prefix}/releases/{release}/{path.name}')
        prepared_entries = {key: upload(prepared/f'{key}.parquet', f'{prefix}/analytics/releases/{release}/{key}.parquet')
                            for key in builders}
        candidate = {
            'manifest': {'schema_version': 1, 'release_id': release,
                         'published_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'files': entries},
            'base_release_id': manifest['release_id'], 'base_manifest_generation': base_generation,
            'catalog_generation': status_generation, 'policy_version': policy['policy_version'],
            'prepared': prepared_entries, 'expected': expected, 'native_check': native_check,
            'reconciliation': reconciliation,
        }
        pointer.reload()
        if str(pointer.generation) != base_generation:
            raise RuntimeError('Cambio el release publicado durante la preparacion; no se activa el candidato.')
        name = f'{prefix}/video_context_candidates/{release}.json'
        bucket.blob(name).upload_from_string(json.dumps(candidate, default=str), content_type='application/json', if_generation_match=0)
        event('repair_candidate_ready', candidate=f'gs://{bucket.name}/{name}', native_check=native_check)


if __name__ == '__main__':
    run()
