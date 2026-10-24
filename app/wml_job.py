"""Cloud-only production ingestion, reconciliation and atomic WML publication."""
from __future__ import annotations
import json
import os
import re
import tempfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
import polars as pl
from google.api_core.exceptions import NotFound,PreconditionFailed
from google.cloud import bigquery,storage
from app.operational_db import close_operational_db_pool
from app.royalty_scope import WML_FILES,WML_DATASET,wml_release_prefix
from app.royalty_workspace_store import settings,merge_config
from app.wml_cloud import input_manifest
from scripts.ingest_wml_workspace import ingest,sha256
from scripts import load_bigquery_release as loader

ROOT=Path(__file__).resolve().parents[1]
WML_CONTEXT={'wml_royalty_rate_pct':'FLOAT64','wml_reported_royalty_usd':'FLOAT64','wml_base100_usd':'FLOAT64',
    'statement_row_number':'INT64','movement_id':'STRING','statement_semester':'STRING','statement_start_period':'STRING',
    'receipt_month':'STRING','product_type':'STRING'}

def prepare_detail_batches(source: Path,target: Path,release_id: str,*,batch_size: int=50000) -> None:
    """Bound memory independently of the length and compression of the catalogue."""
    import pyarrow.parquet as pq
    writer=None
    try:
        with tempfile.TemporaryDirectory(prefix='wml-detail-batches-') as temporary:
            root=Path(temporary);raw=root/'raw.parquet';normalized=root/'normalized.parquet'
            for index,batch in enumerate(pq.ParquetFile(source).iter_batches(batch_size=batch_size)):
                pl.from_arrow(batch).write_parquet(raw,compression='zstd')
                overrides={name:pl.col(name) for name in [*WML_CONTEXT,'gpid','catalog_number','gross_royalty_usd','deductible_fees_usd']}
                loader.build_detail(raw,normalized,release_id,overrides=overrides)
                table=pq.read_table(normalized)
                if writer is None:writer=pq.ParquetWriter(target,table.schema,compression='zstd')
                writer.write_table(table)
                del table,batch
                if index%10==0:print(f'WML: bloque de detalle {index+1} preparado.',flush=True)
    finally:
        if writer is not None:writer.close()
    if writer is None:raise ValueError('El detalle WML está vacío.')

def immutable_upload(bucket,name: str,path: Path):
    blob=bucket.blob(name)
    digest=sha256(path)
    blob.metadata={'sha256':digest}
    try:blob.upload_from_filename(str(path),if_generation_match=0)
    except PreconditionFailed:pass
    blob.reload()
    if (blob.metadata or {}).get('sha256')!=digest or int(blob.size)!=path.stat().st_size:
        raise RuntimeError('Una versión WML inmutable tiene contenido diferente.')
    return blob

def publish_package(bucket,folder: Path,summary: dict) -> dict:
    prefix=wml_release_prefix(summary['release_id'])
    manifest_blob=bucket.blob(prefix+'/release_manifest.json')
    try:
        old=json.loads(manifest_blob.download_as_text());manifest_blob.reload()
        if old['release_id']!=summary['release_id']:raise RuntimeError('Paquete WML inconsistente.')
        return old | {'manifest_generation':str(manifest_blob.generation),'manifest_object_name':manifest_blob.name}
    except NotFound:pass
    entries={}
    for name in [*WML_FILES,'wml_manifest.json']:
        blob=immutable_upload(bucket,prefix+'/files/'+sha256(folder/name)+'/'+name,folder/name)
        entries[name]={'object_name':blob.name,'generation':str(blob.generation),'size_bytes':int(blob.size),
                       'md5_hash':blob.md5_hash,'crc32c':blob.crc32c}
    document={'schema_version':1,'release_id':summary['release_id'],'royalty_scope':'wml',
              'published_at':datetime.now(timezone.utc).isoformat(),'files':entries}
    try:manifest_blob.upload_from_string(json.dumps(document),content_type='application/json',if_generation_match=0)
    except PreconditionFailed:pass
    manifest_blob.reload()
    return json.loads(manifest_blob.download_as_text()) | {
        'manifest_generation':str(manifest_blob.generation),'manifest_object_name':manifest_blob.name}

def prepare_bigquery(folder: Path,target: Path,release_id: str) -> dict[str,Path]:
    target.mkdir(parents=True,exist_ok=True)
    paths={key:target/(key+'.parquet') for key in loader.SOURCE_FILES}
    builders={'detail':loader.build_detail,'dashboard':loader.build_dashboard,'song':loader.build_song,
              'catalog':loader.build_catalog,'digital':loader.build_digital}
    for key,builder in builders.items():
        print('WML: preparando BigQuery '+key,flush=True)
        if key=='detail':prepare_detail_batches(folder/loader.SOURCE_FILES[key],paths[key],release_id)
        else:builder(folder/loader.SOURCE_FILES[key],paths[key],release_id)
    refs=target/'references.parquet'
    pl.scan_parquet(folder/'wml_isrc_references.parquet').with_columns(pl.lit(release_id).alias('release_id')).sink_parquet(refs)
    paths['references']=refs
    return paths

def reconcile_bigquery(client,project: str,dataset: str,release_id: str,paths: dict[str,Path],location: str) -> None:
    """Compare every semester, totals, units, ISRC coverage and aggregate amounts."""
    lf=pl.scan_parquet(paths['detail'])
    if 'statement_month' not in lf.collect_schema():
        lf=lf.with_columns(pl.col('statement_period').str.strptime(pl.Date,'%Y-%m').alias('statement_month'),
            pl.col('asset_isrc').str.strip_chars().replace('',None))
    expected=lf.group_by('statement_month').agg(pl.len().alias('rows'),pl.col('amount_usd').sum(),
        pl.col('units').sum(),pl.col('asset_isrc').drop_nulls().n_unique().alias('isrcs')).collect().to_dicts()
    actual=[dict(r) for r in client.query(f"""SELECT statement_month,COUNT(*) AS `rows`,SUM(amount_usd) AS amount_usd,
        SUM(units) AS units,COUNT(DISTINCT asset_isrc) AS isrcs FROM `{project}.{dataset}.royalty_statement_fact`
        WHERE release_id='{release_id}' GROUP BY statement_month""",location=location).result()]
    by_period={str(r['statement_month']):r for r in actual}
    if len(expected)!=len(actual):raise RuntimeError('BigQuery WML: cantidad de semestres diferente.')
    for row in expected:
        other=by_period.get(str(row['statement_month']))
        if (not other or row['rows']!=other['rows'] or row['isrcs']!=other['isrcs'] or
            abs(row['amount_usd']-other['amount_usd'])>0.0001 or abs(row['units']-other['units'])>0.001):
            raise RuntimeError(f"BigQuery WML: no concilia el semestre {row['statement_month']}.")
    total=sum(r['amount_usd'] for r in expected)
    for key,table,col in [('dashboard','royalty_dashboard_rankings','amount_usd'),('song','royalty_song_level','amount_usd'),
                         ('catalog','royalty_catalog','amount_usd'),('digital','digital_income_summary','total_usd')]:
        local=pl.scan_parquet(paths[key]).select(pl.len().alias('rows'),pl.col(col).sum().alias('amount')).collect().row(0,named=True)
        cloud=next(iter(client.query(f"SELECT COUNT(*) AS `rows`,SUM({col}) AS amount FROM `{project}.{dataset}.{table}` WHERE release_id='{release_id}'",location=location).result()))
        if local['rows']!=cloud['rows'] or abs(local['amount']-cloud['amount'])>0.0001 or abs(local['amount']-total)>0.0001:
            raise RuntimeError('No concilia el agregado WML '+key)

def load_bigquery(bucket,folder: Path,summary: dict,package: dict,*,project: str,dataset: str,location: str,client=None) -> None:
    regular=os.environ.get('VPO_BIGQUERY_DATASET','royalties_analytics')
    if dataset==regular or dataset!=WML_DATASET:
        raise ValueError('La publicación WML requiere su dataset exclusivo royalties_wml.')
    if not re.fullmatch(r'[a-z][a-z0-9-]{4,62}',project):raise ValueError('Proyecto WML inválido.')
    if not re.fullmatch(r'[A-Za-z0-9-]+',location):raise ValueError('Región BigQuery inválida.')
    client=client or bigquery.Client(project=project,location=location)
    query=lambda sql:client.query(sql,location=location).result()
    client.get_dataset(f'{project}.{dataset}')
    schema=(ROOT/'sql/bigquery/analytics_schema.sql').read_text()
    # The Job can write only WML; dataset creation belongs to administrative provisioning.
    query(schema[schema.index('CREATE TABLE'):].format(project=project,dataset=dataset,location=location))
    query(loader.detail_context_schema_sql(project,dataset));query(loader.catalog_artist_schema_sql(project,dataset))
    for table in ['royalty_statement_fact','royalty_transaction_fact']:
        query(f"ALTER TABLE `{project}.{dataset}.{table}` "+', '.join(f'ADD COLUMN IF NOT EXISTS {c} {t}' for c,t in WML_CONTEXT.items()))
    release=summary['release_id']
    def finish_reconciliation(paths):
        reconcile_bigquery(client,project,dataset,release,paths,location)
        expected_refs=pl.scan_parquet(folder/'wml_isrc_references.parquet').select(pl.len()).collect().item()
        refs=next(iter(query(f"SELECT COUNT(*) AS n,COUNT(DISTINCT reference_id) AS ids,COUNTIF(applies_automatically) AS automatic FROM `{project}.{dataset}.wml_isrc_references` WHERE release_id='{release}'")))
        if refs['n']!=expected_refs or refs['ids']!=expected_refs or refs['automatic']:
            raise RuntimeError('No concilian las referencias informativas WML.')
        query(f"UPDATE `{project}.{dataset}.analytics_releases` SET status='ready',notes='WML 91230: detalle y agregados conciliados; base contractual al 100%' WHERE release_id='{release}'")
    existing=list(query(f"SELECT status,manifest_generation FROM `{project}.{dataset}.analytics_releases` WHERE release_id='{release}'"))
    if existing and str(existing[0]['manifest_generation'])==str(package['manifest_generation']):
        if existing[0]['status']=='ready':return
        if existing[0]['status']=='loaded':
            print('WML: conciliando la carga existente sin reconstruirla.',flush=True)
            finish_reconciliation({key:folder/name for key,name in loader.SOURCE_FILES.items()})
            for key in [*loader.SOURCE_FILES,'references']:
                client.delete_table(f'{project}.{dataset}._wml_stage_{release.replace("-","_")}_{key}',not_found_ok=True)
            return
    with tempfile.TemporaryDirectory(prefix='wml-bq-') as temporary:
        paths=prepare_bigquery(folder,Path(temporary),release)
        # A retry of an already reconciled immutable release needs no rewriting.
        ready=list(query(f"SELECT release_id FROM `{project}.{dataset}.analytics_releases` WHERE release_id='{release}' AND status='ready'"))
        if ready:return
        stages={}
        for key,path in paths.items():
            print('WML: cargando BigQuery '+key,flush=True)
            blob=immutable_upload(bucket,wml_release_prefix(release)+'/bigquery/'+sha256(path)+'/'+path.name,path)
            table=f'_wml_stage_{release.replace("-","_")}_{key}'
            config=bigquery.LoadJobConfig(source_format=bigquery.SourceFormat.PARQUET,write_disposition='WRITE_TRUNCATE')
            parquet_options=bigquery.ParquetOptions()
            parquet_options.enable_list_inference=True
            config.parquet_options=parquet_options
            client.load_table_from_uri(f'gs://{bucket.name}/{blob.name}',f'{project}.{dataset}.{table}',job_config=config,location=location).result()
            table_obj=client.get_table(f'{project}.{dataset}.{table}');table_obj.expires=datetime.now(timezone.utc)+timedelta(days=1)
            arrays={'catalog':['video_isrcs','catalog_aliases','catalog_artists'],'references':['source_files','statement_periods']}.get(key,[])
            fields={field.name:field for field in table_obj.schema}
            if any(fields[name].mode!='REPEATED' or fields[name].field_type!='STRING' for name in arrays):
                raise RuntimeError('BigQuery WML no interpretó correctamente las listas de '+key)
            client.update_table(table_obj,['expires']);stages[key]=table
        query(loader.insert_sql(project=project,dataset=dataset,release_id=release,
            manifest_generation=package['manifest_generation'],published_at=package['published_at'],
            manifest_uri=f"gs://{bucket.name}/{package['manifest_object_name']}",source_files=len(WML_FILES),
            stages=stages,detail_fields=list(dict.fromkeys([*loader.DETAIL_FIELDS,*WML_CONTEXT]))))
        query(f"CREATE TABLE IF NOT EXISTS `{project}.{dataset}.wml_isrc_references` LIKE `{project}.{dataset}.{stages['references']}`;")
        query(f"ALTER TABLE `{project}.{dataset}.wml_isrc_references` SET OPTIONS(expiration_timestamp=NULL)")
        query(f"BEGIN TRANSACTION; DELETE FROM `{project}.{dataset}.wml_isrc_references` WHERE release_id='{release}'; INSERT INTO `{project}.{dataset}.wml_isrc_references` SELECT * FROM `{project}.{dataset}.{stages['references']}`; COMMIT TRANSACTION;")
        finish_reconciliation(paths)
        for table in stages.values():client.delete_table(f'{project}.{dataset}.{table}',not_found_ok=True)

def main() -> None:
    token=os.environ.get('VPO_WML_RUN_TOKEN','')
    if not re.fullmatch(r'[a-f0-9]{32}',token):raise ValueError('Falta la ejecución WML autorizada.')
    state=settings();config=state['config']
    if token!=config.get('run_token'):raise ValueError('Esta ejecución WML ya no es vigente.')
    actor='wml-cloud-job'
    if config.get('processing_status')=='completed' and config.get('published_release_id')==config.get('pending_release_id'):
        print('WML: ejecución ya completada; no se reconstruyen datos.');return
    merge_config({'processing_status':'running','processing_execution':os.environ.get('CLOUD_RUN_EXECUTION')},actor=actor,run_token=token)
    try:
        bucket_name=os.environ['VPO_WML_BUCKET'];bucket=storage.Client().bucket(bucket_name)
        document=input_manifest(bucket,config['input_manifest'])
        with tempfile.TemporaryDirectory(prefix='wml-ingest-') as temporary:
            root=Path(temporary);inputs=root/'inputs';inputs.mkdir()
            release='wml-'+document['fingerprint'][:24]
            package_blob=bucket.blob(wml_release_prefix(release)+'/release_manifest.json')
            try:existing=json.loads(package_blob.download_as_text())
            except NotFound:existing=None
            if existing:
                from scripts.lib.mart_release import validate_release_manifest
                validate_release_manifest(existing,[*WML_FILES,'wml_manifest.json'])
                folder=root/'published';folder.mkdir()
                for name in [*WML_FILES,'wml_manifest.json']:
                    entry=existing['files'][name]
                    bucket.blob(entry['object_name'],generation=int(entry['generation'])).download_to_filename(str(folder/name))
                summary=json.loads((folder/'wml_manifest.json').read_text())
                print('WML: reutilizando paquete inmutable validado.',flush=True)
            else:
                for entry in document['files']:
                    path=inputs/entry['file']
                    bucket.blob(entry['object_name'],generation=int(entry['generation'])).download_to_filename(str(path))
                    if sha256(path)!=entry['sha256']:raise RuntimeError('El TXT WML no coincide con el hash de entrada.')
                summary=ingest(inputs,root/'output');folder=root/'output/releases'/summary['release_id']
            if summary['fingerprint']!=document['fingerprint']:raise RuntimeError('La ingesta WML cambió de versión.')
            package=publish_package(bucket,folder,summary)
            load_bigquery(bucket,folder,summary,package,project=os.environ.get('VPO_BIGQUERY_PROJECT','vpo-corp-royalties'),
                dataset=WML_DATASET,location=os.environ.get('VPO_BIGQUERY_LOCATION','US'))
            # This single Postgres commit switches all readers to the same validated BQ/GCS release.
            merge_config({'published_release_id':summary['release_id'],'published_at':datetime.now(timezone.utc).isoformat(),
                'processing_status':'completed','processing_error':None,'semesters':summary['semesters'],
                'rows':summary['rows'],'amount_usd':summary['amount_usd'],'warner_royalty_usd':summary['warner_royalty_usd']},
                actor=actor,run_token=token)
            print(json.dumps({'release_id':summary['release_id'],'rows':summary['rows'],'amount_usd':summary['amount_usd']}),flush=True)
    except Exception:
        merge_config({'processing_status':'failed','processing_error':'No se pudo completar y conciliar la carga WML. Revisá el Job.'},actor=actor,run_token=token)
        raise

if __name__=='__main__':
    try:main()
    finally:close_operational_db_pool()
