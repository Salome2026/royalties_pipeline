"""Stage selected immutable WML inputs and launch the same cloud job everywhere."""
from __future__ import annotations
import json
import os
import re
import uuid
from datetime import datetime,timezone
from pathlib import Path
from google.api_core.exceptions import NotFound,PreconditionFailed
from app.royalty_workspace_store import settings,merge_config
from scripts.ingest_wml_workspace import discover,sha256,input_fingerprint

INPUT_PREFIX='raw/wml/91230'

def stage_inputs(input_root: Path, *, client_factory, bucket_name: str) -> dict:
    files,_=discover(input_root)
    evidence=[{'file':p.name,'path':str(p),'sha256':sha256(p),'bytes':p.stat().st_size}
              for p in sorted(input_root.glob('Statement_91355_*.txt'))]
    bucket=client_factory().bucket(bucket_name)
    staged=[]
    for item in [*files,*evidence]:
        name=f"{INPUT_PREFIX}/objects/{item['sha256']}/{item['file']}"
        blob=bucket.blob(name)
        try:
            blob.reload()
            if (blob.metadata or {}).get('sha256') != item['sha256'] or int(blob.size)!=item['bytes']:
                raise RuntimeError('El objeto WML existente no coincide con su contenido.')
        except NotFound:
            blob.metadata={'sha256':item['sha256']}
            try:blob.upload_from_filename(item['path'],if_generation_match=0)
            except PreconditionFailed:pass
            blob.reload()
            if (blob.metadata or {}).get('sha256')!=item['sha256'] or int(blob.size)!=item['bytes']:
                raise RuntimeError('No se pudo verificar el objeto WML subido.')
        staged.append({k:v for k,v in item.items() if k!='path'} | {'object_name':name,'generation':str(blob.generation),
            'role':'economic' if item in files else 'reference_only'})
    fingerprint=input_fingerprint(files,evidence)
    document={'schema_version':1,'scope':'wml','account':'91230','fingerprint':fingerprint,
              'files':staged,'created_at':datetime.now(timezone.utc).isoformat()}
    manifest=bucket.blob(f'{INPUT_PREFIX}/manifests/{fingerprint}.json')
    try:manifest.upload_from_string(json.dumps(document),content_type='application/json',if_generation_match=0)
    except PreconditionFailed:pass
    manifest.reload()
    pointer={'object_name':manifest.name,'generation':str(manifest.generation),'fingerprint':fingerprint}
    bucket.blob(f'{INPUT_PREFIX}/latest.json').upload_from_string(json.dumps(pointer),content_type='application/json')
    return pointer

def input_manifest(bucket, pointer: dict) -> dict:
    name=pointer.get('object_name','')
    if not re.fullmatch(re.escape(INPUT_PREFIX)+r'/manifests/[a-f0-9]{64}\.json',name):
        raise ValueError('Manifiesto de entrada WML inválido.')
    document=json.loads(bucket.blob(name,generation=int(pointer['generation'])).download_as_text())
    if document.get('scope')!='wml' or document.get('account')!='91230':raise ValueError('Cuenta de entrada WML inválida.')
    if not document.get('files'):raise ValueError('La entrada WML está vacía.')
    names=set();periods=set()
    for entry in document['files']:
        filename=entry['file'];digest=entry['sha256'];role=entry['role']
        if not re.fullmatch(r'[a-f0-9]{64}',digest):raise ValueError('Hash WML inválido.')
        account='91230' if role=='economic' else '91355' if role=='reference_only' else None
        if not account or not re.fullmatch(rf'Statement_{account}_\d+_{account}_\d{{8}}\.txt',filename):
            raise ValueError('Archivo fuera del alcance WML autorizado.')
        if entry['object_name']!=f'{INPUT_PREFIX}/objects/{digest}/{filename}' or int(entry['generation'])<=0:
            raise ValueError('Objeto WML inválido.')
        if filename in names:raise ValueError('Archivo WML duplicado.')
        names.add(filename)
        if role=='economic':
            period=filename[-12:-4]
            if period in periods:raise ValueError('Dos versiones WML del mismo semestre.')
            periods.add(period)
    actual=input_fingerprint([x for x in document['files'] if x['role']=='economic'],
                             [x for x in document['files'] if x['role']=='reference_only'])
    if document['fingerprint']!=actual or pointer['fingerprint']!=actual:
        raise ValueError('La versión de transformación o la entrada WML cambió. Volvé a preparar los TXT.')
    return document

def launch_processing(*,client_factory,bucket_name: str,actor: str) -> dict:
    from google.auth import default
    from google.auth.transport.requests import AuthorizedSession
    project=os.environ.get('VPO_WML_JOB_PROJECT') or os.environ.get('VPO_REPORT_JOB_PROJECT','')
    location=os.environ.get('VPO_WML_JOB_LOCATION') or os.environ.get('VPO_REPORT_JOB_LOCATION','')
    job=os.environ.get('VPO_WML_JOB_NAME','').strip()
    if not project or not location or not job:raise RuntimeError('El Cloud Run Job de WML no está configurado.')
    state=settings()
    if not state['installed']:raise RuntimeError('Primero instalá la migración WML en Cloud SQL.')
    if state['config'].get('processing_status') in {'queued','running'}:
        started=state['config'].get('processing_started_at')
        if started and (datetime.now(timezone.utc)-datetime.fromisoformat(started)).total_seconds()>7200:
            # Jobs have a one-hour execution limit. Revoke a lost execution before retrying.
            merge_config({'processing_status':'failed','processing_error':'La ejecución anterior superó el tiempo máximo.'},actor=actor)
    bucket=client_factory().bucket(bucket_name)
    local=Path(__file__).resolve().parents[1]/'input_raw/wml'
    pointer=stage_inputs(local,client_factory=client_factory,bucket_name=bucket_name) if local.exists() else json.loads(
        bucket.blob(f'{INPUT_PREFIX}/latest.json').download_as_text())
    document=input_manifest(bucket,pointer)
    release_id='wml-'+document['fingerprint'][:24]
    if state['config'].get('published_release_id')==release_id:
        return {'reused':True,'release_id':release_id,'data_rebuilt':False}
    token=uuid.uuid4().hex
    merge_config({'processing_status':'queued','run_token':token,'processing_started_at':datetime.now(timezone.utc).isoformat(),
        'processing_error':None,'pending_release_id':release_id,'input_manifest':pointer},actor=actor,claim=token)
    try:
        credentials,_=default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        response=AuthorizedSession(credentials).post(
            f'https://run.googleapis.com/v2/projects/{project}/locations/{location}/jobs/{job}:run',
            json={'overrides':{'containerOverrides':[{'env':[
                {'name':'VPO_WML_RUN_TOKEN','value':token},{'name':'VPO_WML_BUCKET','value':bucket_name}]}]}},timeout=30)
        response.raise_for_status()
        operation=response.json().get('name')
        if not operation:raise RuntimeError('Cloud Run no devolvió una ejecución WML.')
        merge_config({'processing_operation':operation},actor=actor,run_token=token)
        return {'reused':False,'release_id':release_id,'operation':operation,'data_rebuilt':True}
    except Exception:
        # A timeout after dispatch is ambiguous; retain the token so a started Job can finish.
        confirmed_rejection=bool('response' in locals() and response.status_code>=400)
        merge_config({'processing_status':'failed' if confirmed_rejection else 'queued',
            'processing_error':'Cloud Run rechazó el inicio.' if confirmed_rejection else 'No se pudo confirmar el inicio. La ejecución conservará su identificador hasta resolver el estado.'},actor=actor,run_token=token)
        raise
