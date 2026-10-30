"""Activate a Cloud Run repair candidate using remote GCS/BQ operations only."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
import re
import sys
from pathlib import Path

from google.cloud import bigquery, storage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from scripts.load_bigquery_release import (DETAIL_FIELDS, SONG_FIELDS, CATALOG_FIELDS, DASHBOARD_FIELDS,
    DIGITAL_FIELDS, insert_sql, detail_context_schema_sql, video_context_schema_sql, catalog_artist_schema_sql)
from scripts.reconcile_bigquery_release import aggregate_bigquery_sql, reconcile_rows
from scripts.lib.mart_release import validate_release_manifest
from lib.distributor_policy_store import load_distributor_policy_document


def activate(candidate_uri: str, *, project='vpo-corp-royalties', dataset='royalties_analytics') -> dict:
    match = re.fullmatch(r'gs://([^/]+)/(.+)', candidate_uri)
    if not match:
        raise ValueError('Se requiere el URI del candidato preparado en Cloud Run.')
    client, bq = storage.Client(project=project), bigquery.Client(project=project)
    bucket = client.bucket(match[1])
    candidate = json.loads(bucket.blob(match[2]).download_as_text())
    manifest = validate_release_manifest(candidate['manifest'], [])
    release = manifest['release_id']
    if not re.fullmatch(r'[A-Za-z0-9_-]+', dataset):
        raise ValueError('Dataset invalido.')
    prefix = match[2].split('/video_context_candidates/')[0]
    pointer = bucket.blob(f'{prefix}/release_manifest.json')
    base = candidate['base_manifest_generation']
    def check_base():
        pointer.reload()
        if str(pointer.generation) != base:
            raise RuntimeError('Cambio el release activo; debe prepararse nuevamente sobre la ultima version.')
        status = bucket.blob(f'{prefix}/catalog_status.parquet')
        generation = '0'
        if status.exists():
            status.reload()
            generation = str(status.generation)
        if generation != candidate['catalog_generation']:
            raise RuntimeError('Cambio la gobernanza del catalogo; debe prepararse nuevamente.')
        if load_distributor_policy_document()['policy_version'] != candidate['policy_version']:
            raise RuntimeError('Cambio la politica de distribuidoras; debe prepararse nuevamente.')
    check_base()
    def query(sql):
        return list(bq.query(sql, location='US', job_config=bigquery.QueryJobConfig(
            maximum_bytes_billed=20_000_000_000)).result())
    for ddl in [detail_context_schema_sql(project, dataset), video_context_schema_sql(project, dataset), catalog_artist_schema_sql(project, dataset)]:
        query(ddl)
    suffix = re.sub('[^a-zA-Z0-9]', '', release)[-20:].lower()
    stages = {key: f'_stage_video_{key}_{suffix}' for key in candidate['prepared']}
    fields = {'detail': DETAIL_FIELDS, 'song': SONG_FIELDS, 'catalog': CATALOG_FIELDS,
              'dashboard': DASHBOARD_FIELDS, 'digital': DIGITAL_FIELDS}
    for key, entry in candidate['prepared'].items():
        blob = bucket.blob(entry['object_name'])
        blob.reload()
        if str(blob.generation) != entry['generation']:
            raise RuntimeError('El candidato preparado no es inmutable.')
        uri = f'gs://{bucket.name}/{blob.name}'
        stage = f'{project}.{dataset}.{stages[key]}'
        bq.load_table_from_uri(uri, stage, location='US', job_config=bigquery.LoadJobConfig(
            source_format='PARQUET', write_disposition='WRITE_TRUNCATE')).result()
        amount = 'total_usd' if key == 'digital' else 'amount_usd'
        checked = query(f'SELECT COUNT(*) n, COALESCE(SUM({amount}),0) amount FROM `{stage}`')[0]
        expected = candidate['expected'][key]
        if checked['n'] != expected['rows'] or abs(checked['amount'] - expected['amount_usd']) > .01:
            raise RuntimeError(f'La etapa {key} no coincide con el candidato.')
    query(insert_sql(project=project, dataset=dataset, release_id=release,
                     manifest_generation=base, published_at=manifest['published_at'],
                     manifest_uri=f'gs://{bucket.name}/{pointer.name}', source_files=len(manifest['files']), stages=stages))
    # Exact bidirectional content comparison includes the native video ID/provenance.
    targets = {'detail': ['royalty_statement_fact', 'royalty_transaction_fact'],
               'song': ['royalty_song_level'], 'catalog': ['royalty_catalog'],
               'dashboard': ['royalty_dashboard_rankings'], 'digital': ['digital_income_summary']}
    for key, tables in targets.items():
        selected = ', '.join(f'`{f}`' for f in fields[key])
        for table in tables:
            # Validate the loaded facts against the immutable prepared artifact.
            a = f'SELECT {selected} FROM `{project}.{dataset}.{table}` WHERE release_id="{release}"'
            b = f'SELECT {selected} FROM `{project}.{dataset}.{stages[key]}`'
            changed = query(f'SELECT COUNT(*) n FROM (({a} EXCEPT DISTINCT {b}) UNION ALL ({b} EXCEPT DISTINCT {a}))')[0]['n']
            if changed:
                raise RuntimeError(f'{table} pierde datos del candidato preparado.')
    remote = []
    for column, basis in [('statement_month', 'statement_period'), ('transaction_month', 'transaction_month')]:
        remote.extend(dict(row) for row in query(aggregate_bigquery_sql(project=project, dataset=dataset,
            release_id=release, period_column=column, period_basis=basis)))
    local = candidate['reconciliation']
    for row in local:
        row['period_month'] = date.fromisoformat(row['period_month'])
    run_id = f'video-context-{release}'
    results = reconcile_rows(local_rows=local, bigquery_rows=remote, release_id=release,
                            run_id=run_id, amount_tolerance=.01, units_tolerance=.0001)
    if any(row['status'] != 'match' for row in results):
        raise RuntimeError('La conciliacion por fuente, cuenta y mes no coincide.')
    # Recheck concurrency before activation; preserve all catalog/participant plan objects.
    check_base()
    result_name = f'{prefix}/analytics/reconciliation/{run_id}.json'
    bucket.blob(result_name).upload_from_string(json.dumps({'native_check': candidate['native_check'],
        'results': results}, default=str), content_type='application/json', if_generation_match=0)
    # Readers use immutable files from the manifest; canonical aliases remain for older clients.
    for filename, entry in manifest['files'].items():
        bucket.copy_blob(bucket.blob(entry['object_name'], generation=int(entry['generation'])), bucket,
                         new_name=f'{prefix}/{filename}')
    check_base()
    pointer.upload_from_string(json.dumps(manifest), content_type='application/json', if_generation_match=int(base))
    pointer.reload()
    generation = str(pointer.generation)
    # No data-dependent operation remains between the GCS switch and ready status.
    query(f"UPDATE `{project}.{dataset}.analytics_releases` SET status='ready', manifest_generation='{generation}', "
          f"notes='Native video/quantity reconciliation passed ({len(results)} account/month groups)' WHERE release_id='{release}'")
    for stage in stages.values():
        bq.delete_table(f'{project}.{dataset}.{stage}', not_found_ok=True)
    return {'release_id': release, 'manifest_generation': generation, 'groups': len(results),
            'native_check': candidate['native_check'], 'audit_uri': f'gs://{bucket.name}/{result_name}'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate')
    args = parser.parse_args()
    print(json.dumps(activate(args.candidate), default=str))
