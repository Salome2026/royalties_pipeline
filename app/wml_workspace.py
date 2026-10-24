from __future__ import annotations
import calendar
import json
import os
from datetime import date,datetime,timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable
import polars as pl
from app.royalty_scope import WML_FILES, WML_LABEL, MARTS, RELEASE, wml_release_prefix
from scripts.lib.mart_release_cache import MartReleaseCache

ROOT=Path(__file__).resolve().parents[1]

def local_release(root: Path | None = None) -> tuple[dict,Path] | None:
    root=root or Path(os.environ.get('VPO_WML_LOCAL_ROOT') or ROOT/'warehouse/isolated/wml')
    pointer=root/'active_release.json'
    if not pointer.exists():return None
    document=json.loads(pointer.read_text(encoding='utf-8'))
    release_id=document['release_id']
    if not __import__('re').fullmatch(r'wml-[a-f0-9]{24}',release_id):raise ValueError('Versión WML inválida.')
    path=root/'releases'/release_id
    manifest=json.loads((path/'wml_manifest.json').read_text(encoding='utf-8'))
    return manifest,path

@lru_cache(maxsize=4)
def release_cache(bucket: str,prefix: str,cache_dir: str,client_factory: Callable):
    def validate(path):pl.read_parquet_schema(path)
    return MartReleaseCache(cache_dir=Path(cache_dir),bucket_name=bucket,prefix=prefix,
        required_files=WML_FILES,client_factory=client_factory,validator=validate)

def resolve_marts(filenames: list[str],*,bucket: str,client_factory: Callable,cache_dir: Path,
                  local_mode: bool=False,refresh: bool=False) -> dict[str,Path]:
    if set(filenames)-set(WML_FILES):raise ValueError('WML solicitó un archivo fuera de su ámbito.')
    local_root=os.environ.get('VPO_WML_LOCAL_ROOT')
    # Ordinary local marts never select a different WML release. Offline QA is explicit.
    if local_root:
        local=local_release(Path(local_root) if local_root else None)
        if local is None:raise RuntimeError('WML todavía no tiene una carga local validada.')
        if RELEASE.get() and local[0]['release_id'] != RELEASE.get():
            raise RuntimeError('La carga WML local difiere de la versión publicada. Actualizá WML.')
        paths={name:local[1]/name for name in filenames}
    else:
        prefix=wml_release_prefix()
        paths=release_cache(bucket,prefix,str(cache_dir/'wml'),client_factory).ensure(filenames,refresh=refresh)
    MARTS.set({**MARTS.get(),**paths})
    return paths

def semester_deadline(end: str,lag: int) -> date:
    year,month=map(int,end.split('-'));total=year*12+month-1+lag
    y,m=divmod(total,12);m+=1
    return date(y,m,calendar.monthrange(y,m)[1])

def expected_semester(today: date,lag: int=3) -> str:
    eligible=[f'{year}-{month:02}' for year in range(today.year-2,today.year+1) for month in (6,12)
              if semester_deadline(f'{year}-{month:02}',lag)<=today]
    return max(eligible)

def monitor_item(state: dict,summary: dict | None=None,*,today: date | None=None) -> dict:
    today=today or date.today();summary=summary or {}
    if state['config'].get('published_release_id'):
        summary={'semesters':state['config'].get('semesters') or [],'rows':state['config'].get('rows',0)}
    rows=summary.get('semesters') or state['config'].get('semesters') or []
    periods=sorted({r.get('statement_period') for r in rows if r.get('statement_period')})
    lag=int(state['config'].get('delivery_lag_months',3));expected=expected_semester(today,lag)
    latest=max(periods) if periods else None
    gaps=[]
    if periods:
        for year in range(int(periods[0][:4]),int(expected[:4])+1):
            for month in (6,12):
                p=f'{year}-{month:02}'
                if periods[0]<=p<=expected and p not in periods:gaps.append(p)
    status='inactive' if not state['enabled'] else 'alert' if not latest or latest<expected or gaps else 'ok'
    reason='WML desactivada; conservamos datos e historial.' if not state['enabled'] else (
        f'Falta el semestre esperado {expected} o hay discontinuidades.' if status=='alert' else 'Statements semestrales al día.')
    processing=state['config'].get('processing_status','completed')
    started=state['config'].get('processing_started_at')
    if processing in {'queued','running'} and started and (datetime.now(timezone.utc)-datetime.fromisoformat(started)).total_seconds()>7200:
        processing='failed'
    return {'id':'wml_91230','source':'wml','account':'91230','display_name':WML_LABEL,
        'input_path':'input_raw/wml','expected_frequency':'semiannual','max_age_months':6,
        'monitoring_active':state['enabled'],'alert_silenced':False,'workspace_enabled':state['enabled'],
        'workspace_version':state['version'],'workspace_installed':state['installed'],
        'workspace_ready':bool(state['config'].get('published_release_id')),
        'processing_status':processing,
        'processing_error':state['config'].get('processing_error'),
        'delivery_lag_months':lag,'expected_statement_period':expected,'missing_semesters':gaps,
        'portal_url':'https://artistroyalties.wmg.com',
        'notes':'Cuenta 91230 solamente. Base contractual al 100%; referencias informativas sin aplicación automática.',
        'last_manual_review_at':None,'last_statement_period':latest,'statement_age_months':None,
        'statement_files_in_mart':len(periods),'rows_in_mart':summary.get('rows',sum(r.get('rows',0) for r in rows)),
        'files_in_mart':len(periods),'raw_files':len(summary.get('files') or []),
        'latest_raw_file':None,'latest_raw_modified':None,'unprocessed_raw_files':[],'unprocessed_raw_count':0,
        'raw_inventory_summary':{},'supplementary_audits':[],'supplementary_audit_error':None,
        'ignored_raw_count':len(summary.get('ignored') or []),'ignored_raw_files':(summary.get('ignored') or [])[:20],
        'status':status,'alert':status=='alert','reason':reason}

def references_for_isrc(isrc: str,paths: dict[str,Path]) -> list[dict]:
    path=paths.get('wml_isrc_references.parquet')
    if path is None:return []
    return pl.scan_parquet(path).filter(pl.col('isrc')==isrc).collect().to_dicts()
