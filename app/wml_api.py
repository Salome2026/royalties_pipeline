"""WML feature gate and request-local isolation; ordinary endpoints stay ordinary."""
from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Any
from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from app.royalty_scope import use_scope, validate_scope, WML_LABEL
from app.royalty_workspace_store import settings, update_settings
from app.wml_workspace import local_release, references_for_isrc

class WorkspaceUpdate(BaseModel):
    enabled: bool
    expected_version: int = Field(ge=1)
    delivery_lag_months: int | None = Field(default=None,ge=0,le=6)

def install(api: Any) -> None:
    def allowed_artist(permission):
        artists=permission.get('scope')
        return artists is None or any(re.sub(r'[^a-z]','',str(s).lower())=='litkillah' for s in artists)

    def authorize(username,module,action='access'):
        if not username:raise HTTPException(401,'Se requiere una sesión de usuario.')
        with api.operational_connect() as conn:
            permission=api.require_module_permission(conn,username,module,action)
        if module=='source_monitor' and action=='edit' and not allowed_artist(permission):
            raise HTTPException(403,'No tenés permiso para operar WML.')
        return permission

    def request_context(path,key,username):
        api.require_api_key(key)
        module=('catalog' if path.startswith('/catalog') or path.startswith('/wml/references') else
                'master_contracts' if path.startswith('/master-contracts') else
                'royalties_dashboard' if path.startswith('/royalties-dashboard') else 'royalty_reports')
        if path.startswith('/wml/references'):
            try:
                permission=authorize(username,'catalog')
                if not allowed_artist(permission):raise HTTPException(403,'Sin acceso al catálogo WML.')
            except HTTPException as exc:
                if exc.status_code != 403:raise
                permission=authorize(username,'master_contracts')
        else:permission=authorize(username,module)
        if not allowed_artist(permission):
            raise HTTPException(403,'No tenés permiso para el catálogo de Lit Killah.')
        state=settings()
        historical=bool(re.fullmatch(r'/reports/jobs/\d+(?:/download)?',path))
        if not state['enabled'] and not historical:raise HTTPException(409,'WML está desactivada en Control de distribuidoras.')
        return state

    @api.app.middleware('http')
    async def scoped_request(request: Request,call_next):
        raw=request.headers.get('x-vpo-royalty-scope','regular')
        try:scope=validate_scope(raw)
        except ValueError as exc:return JSONResponse({'detail':str(exc)},status_code=400)
        if scope=='regular':return await call_next(request)
        path=request.url.path
        allowed=(path=='/catalog' or path=='/catalog/status' or path.startswith('/master-contracts') or
            path=='/royalties-dashboard' or path.startswith('/reports/jobs') or path.startswith('/reports/royalty/') or
            path.startswith('/wml/references'))
        if not allowed:return JSONResponse({'detail':'Esta operación no pertenece al ámbito WML.'},status_code=400)
        try:
            state=await run_in_threadpool(request_context,path,request.headers.get('x-vpo-api-key'),request.headers.get('x-vpo-username'))
            with use_scope('wml',release_id=state['config'].get('published_release_id')):
                # These small, isolated files also anchor report/catalog identity.
                paths=await run_in_threadpool(api.ensure_marts,False,['catalog_master.parquet','catalog_status.parquet','wml_isrc_references.parquet'])
                from app.royalty_scope import MARTS,STATUS
                from app.royalty_workspace_store import records
                MARTS.set(paths)
                status_records=await run_in_threadpool(records,'catalog_status')
                STATUS.set([row['payload'] for row in status_records.values()])
                response=await call_next(request)
                response.headers['X-VPO-Royalty-Scope']='wml'
                response.headers['X-VPO-Amount-Basis']='wml_contractual_base_100'
                return response
        except HTTPException as exc:return JSONResponse({'detail':exc.detail},status_code=exc.status_code)
        except (RuntimeError,ValueError) as exc:return JSONResponse({'detail':str(exc)},status_code=503)

    @api.app.get('/wml/workspace')
    def workspace(x_vpo_api_key: str|None=Header(default=None),x_vpo_username: str|None=Header(default=None)):
        api.require_api_key(x_vpo_api_key)
        if not x_vpo_username:raise HTTPException(401,'Se requiere una sesión de usuario.')
        # Visibility is available to users of any royalty module; edits use source-monitor permissions.
        allowed=False
        with api.operational_connect() as conn:
            for module in ('source_monitor','catalog','master_contracts','royalties_dashboard','royalty_reports'):
                permission=api.user_module_permission(conn,x_vpo_username,module)
                if permission.get('allowed') and allowed_artist(permission):allowed=True;break
        if not allowed:raise HTTPException(403,'Sin acceso a los módulos de regalías.')
        state=settings()
        local=local_release() if (api.BASE/'input_raw/wml').exists() else None
        visible_config={key:state['config'][key] for key in ('frequency','delivery_lag_months','processing_status','processing_error','published_at') if key in state['config']}
        return {**state,'config':visible_config,'label':WML_LABEL,'amount_basis':'wml_contractual_base_100','applies_references_automatically':False,
            'ready':bool(state['config'].get('published_release_id')),
            'prepared_local_release':local[0]['release_id'] if local else None}

    @api.app.patch('/wml/workspace')
    def update_workspace(request: WorkspaceUpdate,x_vpo_api_key: str|None=Header(default=None),x_vpo_username: str|None=Header(default=None)):
        api.require_api_key(x_vpo_api_key);authorize(x_vpo_username,'source_monitor','edit')
        state=settings()
        if request.enabled and not state['config'].get('published_release_id'):
            raise HTTPException(409,'Primero debe procesarse y publicarse la carga WML validada.')
        try:
            updated=update_settings(enabled=request.enabled,actor=x_vpo_username,expected_version=request.expected_version,
                delivery_lag_months=request.delivery_lag_months)
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc
        return {**updated,'data_rebuilt':False}

    @api.app.post('/wml/workspace/process',status_code=202)
    def process_workspace(x_vpo_api_key: str|None=Header(default=None),x_vpo_username: str|None=Header(default=None)):
        api.require_api_key(x_vpo_api_key);authorize(x_vpo_username,'source_monitor','edit')
        from app.wml_cloud import launch_processing
        try:return launch_processing(client_factory=api.gcs_client,bucket_name=api.GCS_BUCKET,actor=x_vpo_username)
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc
        except RuntimeError as exc:raise HTTPException(503,str(exc)) from exc

    @api.app.get('/wml/references/{isrc}')
    def references(isrc: str,x_vpo_api_key: str|None=Header(default=None),x_vpo_username: str|None=Header(default=None)):
        # Explicit scope is mandatory; silently using ordinary contracts would mix sources.
        from app.royalty_scope import is_wml
        if not is_wml():raise HTTPException(400,'Seleccioná el ámbito WML para ver sus referencias.')
        paths=api.ensure_marts(filenames=['wml_isrc_references.parquet'])
        return {'scope':'wml','isrc':isrc,'applies_automatically':False,'items':references_for_isrc(isrc,paths)}
