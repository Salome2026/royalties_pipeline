from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import unicodedata
import uuid
from calendar import monthrange
from datetime import date
from datetime import datetime
from io import BytesIO
from time import time
from pathlib import Path
from typing import Any, Literal

import polars as pl
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from google.cloud import storage
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2 import service_account
from googleapiclient.discovery import build as google_build
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field

from app.operational_db import (
    db_bool,
    db_sql,
    is_postgres_connection,
    operational_connect,
    operational_db_healthcheck,
    operational_db_settings,
    operational_sqlite_compatible_connect,
)
from app.report_jobs import (
    claim_report_job,
    cloud_tasks_enabled,
    complete_report_job,
    create_or_reuse_report_job,
    enqueue_report_job,
    fail_report_job,
    get_report_job,
    get_report_job_artifact,
    list_report_jobs,
    set_report_job_stage,
    set_report_job_task,
)


BASE = Path(__file__).resolve().parents[1]
SCRIPTS = BASE / "scripts"
ENV_PATH = BASE / ".env"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_keyword_royalty_report import build_report, build_report_tables, normalize_keywords  # noqa: E402
from build_executive_royalty_pdf import build_executive_royalty_pdf  # noqa: E402
from build_statement_report_from_mart import build_statement_report_from_mart  # noqa: E402
from build_custom_title_royalty_report import (  # noqa: E402
    DEFAULT_LOS_ANORMALES_TERMS,
    build_custom_title_report,
)
from lib.catalog_report_filter import apply_report_net_personalization, filter_reportable_generation  # noqa: E402
from lib.text_search import contains_search_expr, normalize_search_text  # noqa: E402
from lib.distributor_policy_store import (  # noqa: E402
    load_distributor_policy_document,
    update_report_personalization,
)
from build_fuga_gusty_contract_report import build_fuga_gusty_contract_report  # noqa: E402
import build_la_nueva_sangre_report as la_nueva_sangre_report  # noqa: E402
import build_la_juntada_report as la_juntada_report  # noqa: E402

CUSTOM_REPORT_TEMPLATES = [
    {
        "key": "los_anormales",
        "title": "Regalias Los Anormales",
        "description": "Reporte validado por listado editable de temas/artistas, con summaries por fuente, titulo, statement, DSP, monetizacion, origen, pais y song matches.",
        "terms": DEFAULT_LOS_ANORMALES_TERMS,
        "enabled": True,
    },
    {
        "key": "gusty_fuga_contracts",
        "title": "Gusty Fuga contratos nuevo & viejo",
        "description": "Reporte FUGA Gusty con separacion contractual nuevo/viejo segun mapa ONErpm/Motorcito. Usa fecha de statement y aplica el resumen normalizado de DSP, monetizacion y origen.",
        "terms": ["Gusty"],
        "enabled": True,
    },
    {
        "key": "la_nueva_sangre",
        "title": "La Nueva Sangre",
        "description": "Reporte personalizado con capa de negocio: ingresos ONErpm, ingresos FUGA, exclusiones y detalle normalizado de DSP, monetizacion y origen.",
        "terms": [],
        "enabled": True,
        "requires_terms": False,
        "supports_sources": False,
        "supports_start_month": False,
        "options": [
            {
                "key": "hide_zero_amounts",
                "label": "Sacar filas que suman 0",
                "description": "Oculta grupos sin importe neto para que el Excel quede mas limpio.",
                "default": True,
            },
            {
                "key": "exclude_related_videos",
                "label": "Sacar videos relacionados a temas excluidos",
                "description": "Excluye videos aunque tengan fecha posterior si corresponden a un master excluido por corte/catalogo.",
                "default": True,
            },
        ],
    },
    {
        "key": "la_juntada_artistas",
        "title": "La juntada de los artistas",
        "description": "Reporte listo para presentar: ingresos consolidados por distribuidora, cuenta, mes, tema, pais/DSP y detalle.",
        "terms": [],
        "enabled": True,
        "requires_terms": False,
        "supports_sources": False,
        "supports_start_month": False,
        "default_end_month": "2026-05",
    },
    {
        "key": "especial_fin_de_ano",
        "title": "Script Especial Fin de Ano",
        "description": "Plantilla reservada para cierres especiales de periodo. Queda visible para ordenar el menu, pero sin ejecucion hasta definir la logica.",
        "terms": [],
        "enabled": False,
    },
]


def load_local_env(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env(ENV_PATH)

GCS_BUCKET = os.environ.get("GCS_BUCKET", "")
GCS_PREFIX = os.environ.get("GCS_PREFIX", "marts").strip("/")
GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
GCS_SERVICE_ACCOUNT_JSON = os.environ.get("GCS_SERVICE_ACCOUNT_JSON", "")
GOOGLE_OAUTH_TOKEN_JSON = os.environ.get("GOOGLE_OAUTH_TOKEN_JSON", "")
VPO_API_KEY = os.environ.get("VPO_API_KEY", "change-me")
VPO_LOCAL_MARTS_DIR_RAW = os.environ.get("VPO_LOCAL_MARTS_DIR", "").strip()
VPO_LOCAL_MARTS_DIR = Path(VPO_LOCAL_MARTS_DIR_RAW).expanduser() if VPO_LOCAL_MARTS_DIR_RAW else None
VPO_API_CACHE_DIR = Path(os.environ.get("VPO_API_CACHE_DIR", BASE / "cache" / "gcs_marts"))
VPO_API_REPORTS_DIR = Path(os.environ.get("VPO_API_REPORTS_DIR", BASE / "reports" / "api"))
BOOKING_ARTIST_REGISTRY_PATH = BASE / "warehouse" / "booking" / "registry" / "booking_artists.json"
SOURCE_MONITOR_CONFIG_PATH = BASE / "warehouse" / "registry" / "source_monitor_config.json"
GOOGLE_SHEETS_SHARE_EMAIL = os.environ.get("GOOGLE_SHEETS_SHARE_EMAIL", "").strip()
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
VPO_REPORT_RESULTS_PREFIX = os.environ.get("VPO_REPORT_RESULTS_PREFIX", "reports/jobs").strip("/")
VPO_REPORT_WORKER_BASE_URL = os.environ.get("VPO_REPORT_WORKER_BASE_URL", "").strip().rstrip("/")

SONG_FILE = "song_level_all_sources.parquet"
STANDARDIZED_FILE = "standardized_raw_all_sources.parquet"
STANDARDIZED_ONERPM_FILE = "standardized_raw_onerpm.parquet"
STANDARDIZED_FUGA_FILE = "standardized_raw_fuga.parquet"
CATALOG_MASTER_FILE = "catalog_master.parquet"
CATALOG_RELEASE_METADATA_FILE = "catalog_release_metadata.parquet"
STATEMENT_SUMMARY_FILE = "statement_summary_all_sources.parquet"
DIGITAL_INCOME_SUMMARY_FILE = "digital_income_statement_summary.parquet"
DIGITAL_INCOME_SUMMARY_PATH = BASE / "warehouse" / "marts" / "digital_income_statement_summary.parquet"
ROYALTIES_DASHBOARD_SUMMARY_FILE = "royalties_dashboard_summary.parquet"
ROYALTIES_DASHBOARD_SUMMARY_PATH = BASE / "warehouse" / "marts" / "royalties_dashboard_summary.parquet"
REQUIRED_MART_FILES = [
    STANDARDIZED_FILE,
    SONG_FILE,
    STATEMENT_SUMMARY_FILE,
    DIGITAL_INCOME_SUMMARY_FILE,
    ROYALTIES_DASHBOARD_SUMMARY_FILE,
    CATALOG_MASTER_FILE,
]
CATALOG_STATUS_PATH = BASE / "warehouse" / "registry" / "catalog_status.parquet"
CONFIG_REGISTRY_DIR = BASE / "warehouse" / "registry"
CONFIG_SEED_FILES = {
    "statement-source-dictionary": CONFIG_REGISTRY_DIR / "statement_source_dictionary.json",
    "contract-cutoffs": CONFIG_REGISTRY_DIR / "contract_cutoffs.json",
    "report-templates": CONFIG_REGISTRY_DIR / "report_templates.json",
}
VPO_CATALOG_STATUS_GCS_OBJECT = os.environ.get("VPO_CATALOG_STATUS_GCS_OBJECT", "").strip("/")
VPO_CATALOG_STATUS_SYNC_GCS = (
    os.environ.get("VPO_CATALOG_STATUS_SYNC_GCS", "1").strip().lower()
    in {"1", "true", "yes", "on"}
)
PUBLISH_JOBS: dict[str, dict] = {}
PUBLISH_JOBS_LOCK = threading.Lock()
LOCAL_REPORT_JOB_LOCK = threading.Lock()


class KeywordReportRequest(BaseModel):
    keywords: list[str] = Field(..., min_length=1)
    start_month: str | None = None
    end_month: str | None = None
    period_basis: Literal["transaction_month", "statement_period"] = "transaction_month"
    mode: Literal["any", "all"] = "any"
    raw_limit: int = Field(default=5000, ge=0, le=50000)
    refresh_cache: bool = False


class ExecutiveRoyaltyReportRequest(BaseModel):
    keywords: list[str] = Field(default_factory=list, max_length=100)
    start_month: str | None = None
    end_month: str | None = None
    period_basis: Literal["transaction_month", "statement_period"] = "transaction_month"
    mode: Literal["any", "all"] = "any"
    source: str | None = Field(default=None, max_length=80)
    account: str | None = Field(default=None, max_length=120)
    refresh_cache: bool = False


class RoyaltyReportJobRequest(BaseModel):
    output: Literal["excel", "executive_pdf", "google_sheet"] = "excel"
    keywords: list[str] = Field(default_factory=list, max_length=100)
    start_month: str | None = None
    end_month: str | None = None
    period_basis: Literal["transaction_month", "statement_period"] = "transaction_month"
    mode: Literal["any", "all"] = "any"
    raw_limit: int = Field(default=5000, ge=0, le=50000)
    source: str | None = Field(default=None, max_length=80)
    account: str | None = Field(default=None, max_length=120)
    refresh_cache: bool = False


class RefreshRequest(BaseModel):
    refresh_cache: bool = False


class StatementReportRequest(BaseModel):
    refresh_cache: bool = False
    min_artist_total_usd: float = Field(default=0.0, ge=0.0, le=1_000_000.0)
    include_zero_total_artists: bool = False
    report_version: Literal["legacy", "new"] = "legacy"


class CatalogStatusRequest(BaseModel):
    catalog_key: str = Field(..., min_length=1)
    active: bool
    include_in_reports: bool | None = None
    business_status: Literal["vpo_catalog", "artist_personal", "external_catalog", "pending_review", "inactive"] = "vpo_catalog"
    notes: str | None = Field(default=None, max_length=1000)
    label_normalized_override: str | None = Field(default=None, max_length=300)


class CustomRoyaltyReportRequest(BaseModel):
    template_key: str = Field(default="los_anormales", min_length=1, max_length=80)
    report_title: str = Field(default="Regalias Los Anormales", min_length=1, max_length=120)
    terms: list[str] = Field(default_factory=lambda: list(DEFAULT_LOS_ANORMALES_TERMS))
    start_month: str | None = None
    end_month: str | None = None
    sources: list[str] = Field(default_factory=list)
    source_accounts: list[dict[str, str]] = Field(default_factory=list)
    refresh_cache: bool = False
    hide_zero_amounts: bool = False
    exclude_related_videos: bool = False


class DistributorPersonalizationAccountRequest(BaseModel):
    policy_id: str = Field(..., min_length=1, max_length=160)
    report_net_adjustment_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class DistributorPersonalizationRequest(BaseModel):
    enabled: bool = False
    accounts: list[DistributorPersonalizationAccountRequest] = Field(default_factory=list, max_length=200)


class SourceMonitorUpdateRequest(BaseModel):
    monitoring_active: bool | None = None
    alert_silenced: bool | None = None
    last_manual_review_at: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=1000)
    portal_url: str | None = Field(default=None, max_length=500)
    max_age_months: int | None = Field(default=None, ge=0, le=24)


class BookingArtistRecordRequest(BaseModel):
    stage_name: str = Field(..., min_length=1, max_length=160)
    legal_name: str | None = Field(default=None, max_length=180)
    cuit: str | None = Field(default=None, max_length=40)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=180)
    address: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=2000)
    active: bool = True


class EmployeePermissionRequest(BaseModel):
    module_key: str = Field(..., min_length=1, max_length=80)
    can_access: bool = False
    can_create: bool = False
    can_view_history: bool = False
    can_edit: bool = False
    can_approve: bool = False
    scope: list[dict[str, str]] = Field(default_factory=list, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)


class EmployeeRecordRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=180)
    legal_name: str | None = Field(default=None, max_length=180)
    cuit: str | None = Field(default=None, max_length=40)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=180)
    address: str | None = Field(default=None, max_length=300)
    functions: list[str] = Field(default_factory=list, max_length=20)
    compensation_type: Literal[
        "none",
        "salary",
        "salary_plus_booking_commission",
        "booking_commission_only",
    ] = "none"
    salary_amount: float = Field(default=0.0, ge=0.0)
    salary_currency: Literal["ARS", "USD"] = "ARS"
    salary_frequency: Literal["monthly"] = "monthly"
    salary_notes: str | None = Field(default=None, max_length=1000)
    username: str | None = Field(default=None, max_length=80)
    password: str | None = Field(default=None, max_length=200)
    must_change_password: bool | None = None
    user_role: Literal["viewer", "editor", "admin"] = "viewer"
    user_active: bool = True
    permissions: list[EmployeePermissionRequest] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    active: bool = True


class AuthLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=200)


class AuthSessionRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)


class AuthChangePasswordRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=200)


class EmployeePasswordRequest(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=200)
    use_default: bool = False
    must_change_password: bool = True


class BookingCommissionRuleRequest(BaseModel):
    artist: str = Field(..., min_length=1, max_length=160)
    percent: float = Field(default=0.0, ge=0.0, le=100.0)
    base: Literal["commissionable", "total"] = "commissionable"
    include_booking_fee_paid_shows: bool = False
    priority_order: int | None = Field(default=None, ge=1, le=5)
    start_month: str | None = Field(default=None, max_length=7)
    end_month: str | None = Field(default=None, max_length=7)
    active: bool = True
    notes: str | None = Field(default=None, max_length=1000)


class BookingCommissionRulesRequest(BaseModel):
    employee_id: int = Field(..., gt=0)
    rules: list[BookingCommissionRuleRequest] = Field(default_factory=list, max_length=500)


class BookingArtistAdjustmentRequest(BaseModel):
    concept: str = Field(..., min_length=1, max_length=180)
    amount: float = Field(default=0.0, ge=0.0)
    applied_amount: float = Field(default=0.0, ge=0.0)
    adjustment_type: Literal["recupero", "adelanto", "inversion", "descuento_especial", "otro"] = "recupero"
    area: Literal["booking", "label", "general"] = "booking"
    impact: Literal["pago_artista", "ingreso_productora", "solo_cuenta_corriente"] = "pago_artista"
    recoverable: bool = True
    artist_percent: float = Field(default=70.0, ge=0.0, le=100.0)
    producer_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    notes: str | None = Field(default=None, max_length=1000)


class BookingShowExpenseRequest(BaseModel):
    concept: str | None = Field(default=None, max_length=180)
    category: str = Field(default="general", min_length=1, max_length=80)
    amount: float = Field(default=0.0, ge=0.0)
    notes: str | None = Field(default=None, max_length=1000)


class BookingPreSplitAdjustmentRequest(BaseModel):
    concept: str = Field(..., min_length=1, max_length=180)
    destination: Literal["artist", "producer"] = "producer"
    amount: float = Field(default=0.0, ge=0.0)
    recovery_auto_apply: bool = False
    notes: str | None = Field(default=None, max_length=1000)


class BookingDirectCommissionRequest(BaseModel):
    concept: str = Field(..., min_length=1, max_length=180)
    recipient: str | None = Field(default=None, max_length=160)
    destination: Literal["salida_directa", "incorpora_base"] = "salida_directa"
    amount: float = Field(default=0.0, ge=0.0)
    notes: str | None = Field(default=None, max_length=1000)


class BookingExternalShareRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    role: Literal["manager_externo", "socio_externo", "tercero", "otro"] = "tercero"
    percent: float | None = Field(default=None, ge=0.0, le=100.0)
    amount: float = Field(default=0.0, ge=0.0)
    cash_handled_by_vpo: bool = False
    notes: str | None = Field(default=None, max_length=1000)


class BookingCashMovementRequest(BaseModel):
    recipient: Literal["producer", "artist"] = "producer"
    concept: str = Field(..., min_length=1, max_length=180)
    amount: float = Field(default=0.0, ge=0.0)
    payment_method: Literal["transferencia", "efectivo", "seña", "sena", "se?a", "seÃ±a", "seÃƒÂ±a", "seÃƒÆ’Ã‚Â±a", "otro"] = "seña"
    paid_by: str | None = Field(default=None, max_length=180)
    notes: str | None = Field(default=None, max_length=1000)


class BookingAccountApplicationRequest(BaseModel):
    application_date: str = Field(..., min_length=10, max_length=10)
    target_balance: Literal["artist", "producer", "venue"] = "artist"
    application_type: Literal[
        "artist_payment",
        "artist_reimbursement",
        "producer_reimbursement",
        "venue_payment",
        "compensation",
        "adjustment",
    ] = "compensation"
    amount: float = Field(..., gt=0.0)
    payment_method: Literal["transferencia", "efectivo", "compensacion", "ajuste", "otro"] = "transferencia"
    counterparty: str | None = Field(default=None, max_length=180)
    linked_show_id: int | None = Field(default=None, ge=1)
    proof_refs: list[str] = Field(default_factory=list, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)


class BookingAccountParentApplicationRequest(BaseModel):
    show_id: int = Field(..., ge=1)
    target_balance: Literal["artist", "producer", "venue"]
    amount: float = Field(..., gt=0.0)


class BookingAccountParentMovementRequest(BaseModel):
    movement_date: str = Field(..., min_length=10, max_length=10)
    artist: str = Field(..., min_length=1, max_length=160)
    movement_type: Literal[
        "cobro_deuda_booking",
        "pago_saldo_artista",
        "compensacion_booking",
        "pago_deuda_boliche",
        "ajuste_booking",
    ]
    amount: float = Field(..., gt=0.0)
    payment_method: Literal["transferencia", "efectivo", "compensacion", "ajuste", "otro"] = "transferencia"
    counterparty: str | None = Field(default=None, max_length=180)
    proof_refs: list[str] = Field(default_factory=list, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)
    applications: list[BookingAccountParentApplicationRequest] = Field(..., min_length=1, max_length=200)


class BookingAccountBlockSettlementRequest(BaseModel):
    settlement_date: str = Field(..., min_length=10, max_length=10)
    artist: str = Field(..., min_length=1, max_length=160)
    amount: float = Field(..., gt=0.0)
    payment_method: Literal["transferencia", "efectivo", "compensacion", "ajuste", "otro"] = "transferencia"
    counterparty: str | None = Field(default=None, max_length=180)
    show_ids: list[int] = Field(..., min_length=1, max_length=200)
    proof_refs: list[str] = Field(default_factory=list, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)


class FinanceProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=180)
    artist: str | None = Field(default=None, max_length=160)
    business_area: Literal["booking", "label", "marketing", "digitales", "management", "administracion", "estructura", "general"] = "general"
    status: Literal["activo", "cerrado", "pausado"] = "activo"
    notes: str | None = Field(default=None, max_length=1000)


class FinanceMovementAllocationRequest(BaseModel):
    allocation_type: Literal[
        "indyana_cost",
        "third_party_receivable",
        "artist_current_account",
        "other",
    ] = "indyana_cost"
    target_name: str = Field(..., min_length=1, max_length=180)
    business_area: Literal["booking", "label", "marketing", "digitales", "management", "administracion", "estructura", "general"] | None = None
    amount: float = Field(..., ge=0.0)
    currency: Literal["ARS", "USD"] | None = None
    fx_rate: float | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=1000)


class FinanceAccountApplicationRequest(BaseModel):
    account_entry_id: int = Field(..., ge=1)
    amount_ars: float = Field(..., gt=0.0)


class FinanceDocumentDetailRequest(BaseModel):
    document_type: Literal["show_deposit_receipt", "payment_order", "collection_receipt"] = "show_deposit_receipt"
    issuer_company: Literal[
        "VPO Corp",
        "Indyana Records LLC",
        "Carolina Vanesa Alvarez",
        "Mawz SRL",
        "Mawz Records LLC",
        "Mawz Records SRL",
    ] = "VPO Corp"
    counterparty_name: str = Field(..., min_length=1, max_length=180)
    show_date: str | None = Field(default=None, max_length=10)
    venue: str | None = Field(default=None, max_length=180)
    artist_names: list[str] = Field(default_factory=list, max_length=12)
    booking_show_id: int | None = None
    vat_mode: Literal["no_aplica", "mas_iva", "iva_incluido"] = "no_aplica"
    notes: str | None = Field(default=None, max_length=2000)


class FinanceMovementRequest(BaseModel):
    movement_date: str = Field(..., min_length=10, max_length=10)
    artist: str = Field(..., min_length=1, max_length=160)
    business_area: Literal["booking", "label", "marketing", "digitales", "management", "administracion", "estructura", "general"] = "general"
    movement_type: Literal["gasto", "ingreso", "recupero", "adelanto", "prestamo", "ajuste", "pago", "salario"] = "gasto"
    category: str = Field(..., min_length=1, max_length=100)
    project_id: int | None = None
    project_name: str | None = Field(default=None, max_length=180)
    concept: str = Field(..., min_length=1, max_length=240)
    counterparty: str | None = Field(default=None, max_length=180)
    paid_by: Literal["indyana", "artista", "manager", "empleado", "tercero", "desconocido"] = "indyana"
    paid_by_employee_id: int | None = Field(default=None, ge=1)
    amount: float = Field(..., ge=0.0)
    paid_amount: float | None = Field(default=None, ge=0.0)
    due_date: str | None = Field(default=None, max_length=10)
    payment_status: Literal["pendiente", "parcial", "pagado"] | None = None
    currency: Literal["ARS", "USD"] = "ARS"
    fx_rate: float | None = Field(default=None, gt=0)
    recoverable: bool = False
    recoverable_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    recovery_method: Literal[
        "none",
        "before_split",
        "after_split",
        "direct_account",
        "royalties",
        "manual",
    ] = "none"
    artist_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    producer_percent: float = Field(default=100.0, ge=0.0, le=100.0)
    account_effect: Literal[
        "sin_impacto",
        "artista_debe_indyana",
        "indyana_debe_artista",
        "inversion_indyana",
    ] = "inversion_indyana"
    status: Literal["borrador", "pendiente_control", "aprobado", "aplicado", "anulado"] = "pendiente_control"
    source_type: Literal["manual", "legacy", "booking", "royalties", "import"] = "manual"
    source_id: str | None = Field(default=None, max_length=120)
    proof_refs: list[str] = Field(default_factory=list, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)
    allocation_lines: list[FinanceMovementAllocationRequest] = Field(default_factory=list, max_length=20)
    account_applications: list[FinanceAccountApplicationRequest] = Field(default_factory=list, max_length=50)
    document_detail: FinanceDocumentDetailRequest | None = None



def normalize_booking_cash_method(value: str) -> str:
    if value in {"seña", "seÃ±a", "sena", "se?a", "seÃƒÂ±a", "seÃƒÆ’Ã‚Â±a"}:
        return "seña"
    if value in {"transferencia", "efectivo", "otro"}:
        return value
    return "otro"


class BookingQuickShowRequest(BaseModel):
    booking_event_id: int | None = Field(default=None, ge=1)
    artist: str = Field(..., min_length=1, max_length=160)
    show_date: str = Field(..., min_length=10, max_length=10)
    venue: str = Field(..., min_length=1, max_length=180)
    city: str | None = Field(default=None, max_length=120)
    tour_manager: str | None = Field(default=None, max_length=120)
    seller: str | None = Field(default=None, max_length=120)
    status: Literal["pendiente", "realizado", "rendido", "aprobado", "cancelado", "no_cobrado"] = "realizado"
    currency: Literal["ARS", "USD"] = "ARS"
    fx_rate: float | None = Field(default=None, gt=0)
    contracted_cachet_amount: float | None = Field(default=None, ge=0.0)
    venue_collected_amount: float | None = Field(default=None, ge=0.0)
    venue_payment_status: Literal["cobrado", "parcial", "no_cobrado"] = "cobrado"
    venue_shortfall_policy: Literal["deuda_boliche", "ajustar_cachet"] = "deuda_boliche"
    venue_payment_notes: str | None = Field(default=None, max_length=1000)
    cachet_amount: float = Field(default=0.0, ge=0.0)
    expenses_amount: float = Field(default=0.0, ge=0.0)
    show_expenses: list[BookingShowExpenseRequest] = Field(default_factory=list, max_length=50)
    direct_commissions: list[BookingDirectCommissionRequest] = Field(default_factory=list, max_length=20)
    pre_split_adjustments: list[BookingPreSplitAdjustmentRequest] = Field(default_factory=list, max_length=30)
    external_shares: list[BookingExternalShareRequest] = Field(default_factory=list, max_length=20)
    cash_movements: list[BookingCashMovementRequest] = Field(default_factory=list, max_length=30)
    artist_paid_amount: float = Field(default=0.0, ge=0.0)
    producer_received_amount: float = Field(default=0.0, ge=0.0)
    artist_percent: float = Field(default=70.0, ge=0.0, le=100.0)
    producer_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    booking_commission_exempt: bool = False
    booking_commission_notes: str | None = Field(default=None, max_length=1000)
    artist_adjustments: list[BookingArtistAdjustmentRequest] = Field(default_factory=list, max_length=20)
    receipt_refs: list[str] = Field(default_factory=list, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)


class CaserioEventLineRequest(BaseModel):
    line_type: Literal["gasto_general", "artista_externo", "artista_vpo"] = "gasto_general"
    description: str = Field(..., min_length=1, max_length=180)
    amount: float = Field(default=0.0, ge=0.0)
    artist: str | None = Field(default=None, max_length=160)
    artist_percent: float = Field(default=70.0, ge=0.0, le=100.0)
    producer_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    show_expenses: list[BookingShowExpenseRequest] = Field(default_factory=list, max_length=30)
    notes: str | None = Field(default=None, max_length=1000)


class CaserioEventRequest(BaseModel):
    event_date: str = Field(..., min_length=10, max_length=10)
    venue: str = Field(..., min_length=1, max_length=180)
    city: str | None = Field(default=None, max_length=120)
    responsible: str | None = Field(default=None, max_length=160)
    gross_amount: float = Field(default=0.0, ge=0.0)
    currency: Literal["ARS", "USD"] = "ARS"
    fx_rate: float | None = Field(default=None, gt=0)
    status: Literal["borrador", "rendido", "observado", "cerrado"] = "borrador"
    received_amount: float = Field(default=0.0, ge=0.0)
    receipt_refs: list[str] = Field(default_factory=list, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[CaserioEventLineRequest] = Field(default_factory=list, max_length=80)


class BookingCompositeEventExpenseRequest(BaseModel):
    concept: str = Field(..., min_length=1, max_length=180)
    category: str = Field(default="general", min_length=1, max_length=80)
    amount: float = Field(default=0.0, ge=0.0)
    notes: str | None = Field(default=None, max_length=1000)


class BookingCompositeEventLineRequest(BaseModel):
    id: int | None = Field(default=None, ge=1)
    line_type: Literal["artista_vpo", "artista_externo", "comision_externa"] = "artista_vpo"
    description: str = Field(..., min_length=1, max_length=180)
    artist: str | None = Field(default=None, max_length=160)
    amount: float = Field(default=0.0, ge=0.0)
    artist_percent: float = Field(default=70.0, ge=0.0, le=100.0)
    producer_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    artist_paid_amount: float = Field(default=0.0, ge=0.0)
    producer_received_amount: float = Field(default=0.0, ge=0.0)
    show_expenses: list[BookingShowExpenseRequest] = Field(default_factory=list, max_length=30)
    external_shares: list[BookingExternalShareRequest] = Field(default_factory=list, max_length=20)
    booking_commission_exempt: bool = True
    booking_commission_notes: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=1000)


class BookingCompositeEventRequest(BaseModel):
    booking_event_id: int | None = Field(default=None, ge=1)
    event_date: str = Field(..., min_length=10, max_length=10)
    venue: str = Field(..., min_length=1, max_length=180)
    city: str | None = Field(default=None, max_length=120)
    responsible: str | None = Field(default=None, max_length=160)
    status: Literal["borrador", "rendido", "observado", "cerrado"] = "borrador"
    currency: Literal["ARS", "USD"] = "ARS"
    fx_rate: float | None = Field(default=None, gt=0)
    gross_amount: float = Field(default=0.0, ge=0.0)
    received_amount: float = Field(default=0.0, ge=0.0)
    receipt_refs: list[str] = Field(default_factory=list, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)
    expenses: list[BookingCompositeEventExpenseRequest] = Field(default_factory=list, max_length=80)
    lines: list[BookingCompositeEventLineRequest] = Field(default_factory=list, max_length=80)


class BookingAgendaDepositRequest(BaseModel):
    movement_date: str = Field(..., min_length=10, max_length=10)
    amount: float = Field(..., gt=0)
    currency: Literal["ARS", "USD"] = "ARS"
    fx_rate: float | None = Field(default=None, gt=0)
    received_by: Literal["indyana", "artista", "empleado", "tercero"] = "indyana"
    received_by_name: str | None = Field(default=None, max_length=160)
    payment_method: Literal["transferencia", "efectivo", "otro"] = "transferencia"
    counterparty: str | None = Field(default=None, max_length=180)
    proof_refs: list[str] = Field(default_factory=list, max_length=30)
    notes: str | None = Field(default=None, max_length=1000)


class BookingAgendaGroupChildRequest(BaseModel):
    id: int | None = Field(default=None, ge=1)
    event_date: str = Field(..., min_length=10, max_length=10)
    start_time: str | None = Field(default=None, max_length=5)
    venue: str = Field(..., min_length=1, max_length=180)
    city: str | None = Field(default=None, max_length=120)
    contracted_cachet_amount: float = Field(default=0.0, ge=0.0)
    notes: str | None = Field(default=None, max_length=2000)


class BookingAgendaEventRequest(BaseModel):
    event_type: Literal["show", "show_group", "availability_block", "logistics", "prospect"] = "show"
    event_date: str = Field(..., min_length=10, max_length=10)
    start_time: str | None = Field(default=None, max_length=5)
    venue: str = Field(..., min_length=1, max_length=180)
    city: str | None = Field(default=None, max_length=120)
    artists: list[str] = Field(..., min_length=1, max_length=20)
    contracted_cachet_amount: float = Field(default=0.0, ge=0.0)
    currency: Literal["ARS", "USD"] = "ARS"
    fx_rate: float | None = Field(default=None, gt=0)
    tour_manager: str | None = Field(default=None, max_length=160)
    seller: str | None = Field(default=None, max_length=160)
    deposit: BookingAgendaDepositRequest | None = None
    duplicate_override: bool = False
    duplicate_override_notes: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)
    group_children: list[BookingAgendaGroupChildRequest] = Field(default_factory=list, max_length=20)


ParticipationPreset = Literal["last_month", "last_3_months", "last_year", "all_history", "custom"]


app = FastAPI(title="VPO Corp Royalties API", version="0.1.0")

GOOGLE_API_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def require_api_key(x_vpo_api_key: str | None) -> None:
    if not VPO_API_KEY or VPO_API_KEY == "change-me":
        raise HTTPException(
            status_code=500,
            detail="VPO_API_KEY is not configured.",
        )

    if x_vpo_api_key != VPO_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key.")


def load_config_seed(config_name: str) -> dict:
    if config_name == "distributor-account-policies":
        return load_distributor_policy_document()
    path = CONFIG_SEED_FILES.get(config_name)
    if path is None:
        raise HTTPException(status_code=404, detail="Configuracion no soportada.")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No existe configuracion seed: {path.name}")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"JSON invalido en {path.name}: {exc}") from exc


def catalog_stats_by_account(refresh_cache: bool = False) -> dict[tuple[str, str], dict]:
    try:
        marts = ensure_marts(refresh_cache=refresh_cache, filenames=[CATALOG_MASTER_FILE])
        path = marts[CATALOG_MASTER_FILE]
        if not path.exists():
            return {}
        catalog = pl.read_parquet(path)
    except Exception:
        return {}

    if "external_label" not in catalog.columns:
        catalog = catalog.with_columns(pl.lit(None).cast(pl.Utf8).alias("external_label"))
    if "label_normalized_auto" not in catalog.columns:
        catalog = catalog.with_columns(
            normalized_label_expr(pl.col("external_label")).alias("label_normalized_auto")
        )
    if "label_normalized" not in catalog.columns:
        catalog = catalog.with_columns(
            pl.coalesce(["label_normalized_auto", "external_label"]).alias("label_normalized")
        )

    status_df = load_catalog_status()
    if status_df.is_empty():
        catalog = catalog.with_columns([
            pl.lit(True).alias("active"),
            pl.lit(True).alias("include_in_reports"),
            pl.lit(None).cast(pl.Utf8).alias("label_normalized_override"),
        ])
    else:
        catalog = (
            catalog
            .join(status_df.select(["catalog_key", "active", "include_in_reports", "label_normalized_override"]), on="catalog_key", how="left")
            .with_columns([
                pl.col("active").fill_null(True),
                pl.col("include_in_reports").fill_null(pl.col("active")).fill_null(True),
                pl.col("label_normalized_override").cast(pl.Utf8, strict=False),
            ])
        )
    catalog = catalog.with_columns([
        pl.when(pl.col("label_normalized_override").str.strip_chars() == "")
        .then(pl.lit(None).cast(pl.Utf8))
        .otherwise(pl.col("label_normalized_override").str.strip_chars())
        .alias("label_normalized_override"),
    ]).with_columns([
        pl.coalesce(["label_normalized_override", "label_normalized_auto", "external_label"]).alias("label_normalized"),
    ])

    result: dict[tuple[str, str], dict] = {}
    if "sources" not in catalog.columns or "accounts" not in catalog.columns:
        return result

    pairs: set[tuple[str, str]] = set()
    for row in catalog.select(["sources", "accounts"]).to_dicts():
        sources = [item.strip() for item in str(row.get("sources") or "").split(" | ") if item.strip()]
        accounts = [item.strip() for item in str(row.get("accounts") or "").split(" | ") if item.strip()]
        for source in sources:
            for account in accounts:
                pairs.add((source, account))

    for source, account in pairs:
        filtered = catalog.filter(
            pl.col("sources").fill_null("").str.contains(source, literal=True)
            & pl.col("accounts").fill_null("").str.contains(account, literal=True)
        )
        if filtered.is_empty():
            continue
        amount = filtered.get_column("amount_usd").sum() if "amount_usd" in filtered.columns else 0.0
        release_dates = (
            filtered.filter(pl.col("external_release_date").is_not_null()).height
            if "external_release_date" in filtered.columns
            else 0
        )
        labels = (
            filtered.filter(pl.col("label_normalized").is_not_null()).height
            if "label_normalized" in filtered.columns
            else 0
        )
        inactive = filtered.filter(pl.col("active") == False).height
        excluded = filtered.filter(pl.col("include_in_reports") == False).height
        result[(source, account)] = {
            "works": filtered.height,
            "active": filtered.height - inactive,
            "inactive": inactive,
            "excluded_from_reports": excluded,
            "release_dates": release_dates,
            "missing_release_dates": filtered.height - release_dates,
            "labels": labels,
            "missing_labels": filtered.height - labels,
            "amount_usd": round(float(amount or 0.0), 2),
            "first_transaction_month": filtered.get_column("first_transaction_month").drop_nulls().min() if "first_transaction_month" in filtered.columns else None,
            "last_transaction_month": filtered.get_column("last_transaction_month").drop_nulls().max() if "last_transaction_month" in filtered.columns else None,
        }
    return result


def account_impact_stats_by_account(refresh_cache: bool = False) -> dict[tuple[str, str], dict]:
    try:
        marts = ensure_marts(refresh_cache=refresh_cache, filenames=[SONG_FILE])
        path = marts[SONG_FILE]
        if not path.exists():
            return {}
        song = pl.read_parquet(path)
    except Exception:
        return {}

    required = {"source", "account", "amount_usd"}
    if not required.issubset(set(song.columns)):
        return {}

    if "source_sheet" not in song.columns:
        song = song.with_columns(pl.lit(None).cast(pl.Utf8).alias("source_sheet"))
    if "units" not in song.columns:
        song = song.with_columns(pl.lit(0.0).alias("units"))
    if "transaction_month" not in song.columns:
        song = song.with_columns(pl.lit(None).cast(pl.Utf8).alias("transaction_month"))
    if "asset_isrc" not in song.columns:
        song = song.with_columns(pl.lit(None).cast(pl.Utf8).alias("asset_isrc"))
    if "track_id" not in song.columns:
        song = song.with_columns(pl.lit(None).cast(pl.Utf8).alias("track_id"))
    if "track_statement_style" not in song.columns:
        song = song.with_columns(pl.lit(None).cast(pl.Utf8).alias("track_statement_style"))
    if "artist_statement_style" not in song.columns:
        song = song.with_columns(pl.lit(None).cast(pl.Utf8).alias("artist_statement_style"))

    song = song.with_columns(
        pl.when(pl.col("asset_isrc").is_not_null() & (pl.col("asset_isrc") != ""))
        .then(pl.concat_str([pl.lit("ISRC:"), pl.col("asset_isrc")]))
        .when(pl.col("track_id").is_not_null() & (pl.col("track_id") != ""))
        .then(pl.concat_str([pl.lit("TRACK:"), pl.col("track_id")]))
        .otherwise(pl.concat_str([
            pl.lit("TEXT:"),
            pl.col("artist_statement_style").fill_null(""),
            pl.lit("|"),
            pl.col("track_statement_style").fill_null(""),
        ]))
        .alias("_work_key")
    )

    result: dict[tuple[str, str], dict] = {}
    for row in (
        song
        .group_by(["source", "account"])
        .agg([
            pl.len().alias("rows"),
            pl.col("_work_key").n_unique().alias("works"),
            pl.sum("amount_usd").round(2).alias("amount_usd"),
            pl.sum("units").round(2).alias("units"),
            pl.min("transaction_month").alias("first_transaction_month"),
            pl.max("transaction_month").alias("last_transaction_month"),
        ])
        .to_dicts()
    ):
        source = str(row.get("source") or "")
        account = str(row.get("account") or "")
        result[(source, account)] = {
            "rows": int(row.get("rows") or 0),
            "works": int(row.get("works") or 0),
            "amount_usd": float(row.get("amount_usd") or 0.0),
            "units": float(row.get("units") or 0.0),
            "first_transaction_month": row.get("first_transaction_month"),
            "last_transaction_month": row.get("last_transaction_month"),
            "sheet_breakdown": [],
        }

    sheet_rows = (
        song
        .group_by(["source", "account", "source_sheet"])
        .agg([
            pl.len().alias("rows"),
            pl.col("_work_key").n_unique().alias("works"),
            pl.sum("amount_usd").round(2).alias("amount_usd"),
            pl.sum("units").round(2).alias("units"),
            pl.min("transaction_month").alias("first_transaction_month"),
            pl.max("transaction_month").alias("last_transaction_month"),
        ])
        .sort(["source", "account", "amount_usd"], descending=[False, False, True])
        .to_dicts()
    )
    for row in sheet_rows:
        key = (str(row.get("source") or ""), str(row.get("account") or ""))
        if key not in result:
            continue
        result[key]["sheet_breakdown"].append({
            "source_sheet": row.get("source_sheet") or "detalle",
            "rows": int(row.get("rows") or 0),
            "works": int(row.get("works") or 0),
            "amount_usd": float(row.get("amount_usd") or 0.0),
            "units": float(row.get("units") or 0.0),
            "first_transaction_month": row.get("first_transaction_month"),
            "last_transaction_month": row.get("last_transaction_month"),
        })

    return result


def account_rule_preview_by_account(cutoff_entries: list[dict], refresh_cache: bool = False) -> dict[tuple[str, str], dict]:
    if not cutoff_entries:
        return {}
    try:
        marts = ensure_marts(refresh_cache=refresh_cache, filenames=[SONG_FILE, CATALOG_MASTER_FILE])
        song_path = marts[SONG_FILE]
        catalog_path = marts[CATALOG_MASTER_FILE]
        if not song_path.exists() or not catalog_path.exists():
            return {}
        song = pl.read_parquet(song_path)
        catalog = pl.read_parquet(catalog_path)
    except Exception:
        return {}

    if not {"source", "account", "amount_usd"}.issubset(set(song.columns)):
        return {}
    for column in ["source_sheet", "transaction_month", "asset_isrc", "track_statement_style", "artist_statement_style"]:
        if column not in song.columns:
            song = song.with_columns(pl.lit(None).cast(pl.Utf8).alias(column))

    status_df = load_catalog_status()
    if status_df.is_empty():
        catalog = catalog.with_columns([
            pl.lit(True).alias("active"),
            pl.lit(True).alias("include_in_reports"),
            pl.lit(None).cast(pl.Utf8).alias("catalog_business_status"),
            pl.lit(None).cast(pl.Utf8).alias("status_notes"),
        ])
    else:
        catalog = (
            catalog
            .join(status_df.select(["catalog_key", "active", "include_in_reports", "catalog_business_status", "status_notes"]), on="catalog_key", how="left")
            .with_columns([
                pl.col("active").fill_null(True),
                pl.col("include_in_reports").fill_null(pl.col("active")).fill_null(True),
                pl.col("catalog_business_status").cast(pl.Utf8, strict=False),
                pl.col("status_notes").cast(pl.Utf8, strict=False),
            ])
        )

    def norm_text(value: object) -> str:
        return str(value or "").strip().casefold()

    catalog_lookup: dict[str, dict] = {}

    def add_catalog_key(key: str, payload: dict) -> None:
        clean = str(key or "").strip()
        if clean and clean not in catalog_lookup:
            catalog_lookup[clean] = payload

    for catalog_row in catalog.to_dicts():
        payload = {
            "catalog_key": catalog_row.get("catalog_key"),
            "catalog_active": bool(catalog_row.get("active", True)),
            "catalog_include_in_reports": bool(catalog_row.get("include_in_reports", catalog_row.get("active", True))),
            "catalog_business_status": catalog_row.get("catalog_business_status"),
            "catalog_status_notes": catalog_row.get("status_notes"),
            "external_release_date": catalog_row.get("external_release_date"),
            "external_label": catalog_row.get("external_label"),
        }
        add_catalog_key(str(catalog_row.get("catalog_key") or ""), payload)
        for raw_field in ["asset_isrc", "track_id", "identity_asset_isrc", "identity_video_id", "identity_track_id"]:
            raw_value = catalog_row.get(raw_field)
            if raw_value:
                add_catalog_key(str(raw_value), payload)
        for list_field in ["isrcs", "video_ids", "track_ids"]:
            for part in str(catalog_row.get(list_field) or "").split(" | "):
                add_catalog_key(part, payload)
        text_key = f"{norm_text(catalog_row.get('track_title'))}|{norm_text(catalog_row.get('artist_statement'))}"
        add_catalog_key(f"TEXT:{text_key}", payload)
        reverse_text_key = f"{norm_text(catalog_row.get('artist_statement'))}|{norm_text(catalog_row.get('track_title'))}"
        add_catalog_key(f"TEXT:{reverse_text_key}", payload)

    release_map = pl.DataFrame({
        "asset_isrc": pl.Series([], dtype=pl.Utf8),
        "external_release_date": pl.Series([], dtype=pl.Utf8),
        "external_label": pl.Series([], dtype=pl.Utf8),
    })
    if {"asset_isrc", "external_release_date"}.issubset(set(catalog.columns)):
        label_expr = (
            pl.col("external_label").first().alias("external_label")
            if "external_label" in catalog.columns
            else pl.lit(None).cast(pl.Utf8).alias("external_label")
        )
        release_map = (
            catalog
            .filter(pl.col("asset_isrc").is_not_null() & (pl.col("asset_isrc") != ""))
            .group_by("asset_isrc")
            .agg([
                pl.col("external_release_date").drop_nulls().min().alias("external_release_date"),
                label_expr,
            ])
        )

    result: dict[tuple[str, str], dict] = {}
    for cutoff in cutoff_entries:
        source = str(cutoff.get("source") or "")
        account = str(cutoff.get("account") or "")
        if not source or not account:
            continue
        cutoff_month = cutoff.get("contract_start_month")
        cutoff_date = cutoff.get("contract_start_date") or (f"{cutoff_month}-01" if cutoff_month else None)
        cutoff_basis = str(cutoff.get("cutoff_basis") or "")

        scoped = (
            song
            .filter((pl.col("source") == source) & (pl.col("account") == account))
            .with_columns(
                pl.when(pl.col("asset_isrc").is_not_null() & (pl.col("asset_isrc") != ""))
                .then(pl.concat_str([pl.lit("ISRC:"), pl.col("asset_isrc")]))
                .otherwise(pl.concat_str([
                    pl.lit("TEXT:"),
                    pl.col("artist_statement_style").fill_null(""),
                    pl.lit("|"),
                    pl.col("track_statement_style").fill_null(""),
                ]))
                .alias("_work_key")
            )
            .group_by(["_work_key", "asset_isrc", "track_statement_style", "artist_statement_style", "source_sheet"])
            .agg([
                pl.sum("amount_usd").round(2).alias("amount_usd"),
                pl.len().alias("rows"),
                pl.min("transaction_month").alias("first_transaction_month"),
                pl.max("transaction_month").alias("last_transaction_month"),
            ])
            .join(release_map, on="asset_isrc", how="left")
        )
        if scoped.is_empty():
            result[(source, account)] = {
                "enabled": False,
                "cutoff_id": cutoff.get("cutoff_id"),
                "summary": [],
                "items": [],
            }
            continue

        rows = []
        for row in scoped.to_dicts():
            release_date = row.get("external_release_date")
            external_label = row.get("external_label")
            first_tx = row.get("first_transaction_month")
            decision_basis = None
            rule_status = "manual_review"
            reason = "Sin fecha suficiente para decidir."

            if cutoff_basis == "transaction_month":
                decision_basis = first_tx
                if first_tx and cutoff_month:
                    if str(first_tx) >= str(cutoff_month):
                        rule_status = "included"
                        reason = "Primer transaction month desde el contrato."
                    else:
                        rule_status = "excluded"
                        reason = "Primer transaction month anterior al contrato."
            elif cutoff_basis == "release_date_preferred_transaction_month_fallback":
                if release_date and cutoff_date:
                    decision_basis = release_date
                    if str(release_date) >= str(cutoff_date):
                        rule_status = "included"
                        reason = "Release date desde el contrato."
                    else:
                        rule_status = "excluded"
                        reason = "Release date anterior al contrato."
                elif first_tx and cutoff_month:
                    decision_basis = first_tx
                    if str(first_tx) >= str(cutoff_month):
                        rule_status = "included"
                        reason = "Sin release date; fallback por primer transaction month desde contrato."
                    else:
                        rule_status = "excluded"
                        reason = "Sin release date; fallback por primer transaction month anterior al contrato."

            catalog_payload = None
            asset_id = row.get("asset_isrc")
            if asset_id:
                catalog_payload = (
                    catalog_lookup.get(str(asset_id))
                    or catalog_lookup.get(f"ISRC:{asset_id}")
                    or catalog_lookup.get(f"VIDEO:{asset_id}")
                )
            if catalog_payload is None:
                text_key = f"{norm_text(row.get('track_statement_style'))}|{norm_text(row.get('artist_statement_style'))}"
                reverse_text_key = f"{norm_text(row.get('artist_statement_style'))}|{norm_text(row.get('track_statement_style'))}"
                catalog_payload = catalog_lookup.get(f"TEXT:{text_key}") or catalog_lookup.get(f"TEXT:{reverse_text_key}")

            catalog_active = catalog_payload.get("catalog_active") if catalog_payload else None
            include_in_reports = catalog_payload.get("catalog_include_in_reports") if catalog_payload else None
            if catalog_payload and not release_date:
                release_date = catalog_payload.get("external_release_date")
            if catalog_payload and not external_label:
                external_label = catalog_payload.get("external_label")

            final_status = "manual_review"
            final_reason = reason
            attention_level = "none"
            if rule_status == "excluded":
                final_status = "excluded_by_rule"
                final_reason = reason
            elif rule_status == "manual_review":
                final_status = "manual_review"
                attention_level = "warning"
                final_reason = "La regla contractual no alcanza para decidir."
            elif catalog_payload is None:
                final_status = "manual_review"
                attention_level = "warning"
                final_reason = "Incluido por regla, pero sin match claro en catalogo."
            elif include_in_reports is False or catalog_active is False:
                final_status = "excluded_by_catalog"
                attention_level = "warning"
                final_reason = "Incluido por regla, pero el catalogo lo marca fuera de reportes."
            else:
                final_status = "reportable"
                final_reason = "Incluido por regla y activo/reportable en catalogo."

            rows.append({
                "status": rule_status,
                "rule_status": rule_status,
                "final_status": final_status,
                "decision_basis": decision_basis,
                "reason": reason,
                "final_reason": final_reason,
                "attention_level": attention_level,
                "catalog_key": catalog_payload.get("catalog_key") if catalog_payload else None,
                "catalog_active": catalog_active,
                "catalog_include_in_reports": include_in_reports,
                "catalog_business_status": catalog_payload.get("catalog_business_status") if catalog_payload else None,
                "catalog_status_notes": catalog_payload.get("catalog_status_notes") if catalog_payload else None,
                "source_sheet": row.get("source_sheet") or "detalle",
                "asset_isrc": row.get("asset_isrc"),
                "track_title": row.get("track_statement_style"),
                "artist": row.get("artist_statement_style"),
                "amount_usd": float(row.get("amount_usd") or 0.0),
                "rows": int(row.get("rows") or 0),
                "first_transaction_month": row.get("first_transaction_month"),
                "last_transaction_month": row.get("last_transaction_month"),
                "external_release_date": release_date,
                "external_label": external_label,
            })

        summary = []
        for status in ["included", "excluded", "manual_review"]:
            status_rows = [row for row in rows if row["rule_status"] == status]
            summary.append({
                "status": status,
                "works": len(status_rows),
                "amount_usd": round(sum(row["amount_usd"] for row in status_rows), 2),
                "rows": sum(row["rows"] for row in status_rows),
            })
        final_summary = []
        for status in ["reportable", "excluded_by_rule", "excluded_by_catalog", "manual_review"]:
            status_rows = [row for row in rows if row["final_status"] == status]
            final_summary.append({
                "status": status,
                "works": len(status_rows),
                "amount_usd": round(sum(row["amount_usd"] for row in status_rows), 2),
                "rows": sum(row["rows"] for row in status_rows),
            })
        alerts = [
            row for row in rows
            if row["final_status"] in {"excluded_by_catalog", "manual_review"}
        ]

        result[(source, account)] = {
            "enabled": True,
            "cutoff_id": cutoff.get("cutoff_id"),
            "cutoff_basis": cutoff_basis,
            "contract_start_date": cutoff.get("contract_start_date"),
            "contract_start_month": cutoff_month,
            "summary": summary,
            "final_summary": final_summary,
            "alerts": sorted(alerts, key=lambda item: abs(item["amount_usd"]), reverse=True)[:12],
            "items": sorted(rows, key=lambda item: abs(item["amount_usd"]), reverse=True)[:25],
        }
    return result


def report_signature_payload(
    keywords: str,
    start_month: str,
    end_month: str,
    period_basis: str,
    mode: str,
    raw_limit: int,
    refresh_cache: bool,
    expires: int,
) -> str:
    return "\n".join([
        keywords,
        start_month,
        end_month,
        period_basis,
        mode,
        str(raw_limit),
        "1" if refresh_cache else "0",
        str(expires),
    ])


def sign_report_payload(payload: str) -> str:
    if not VPO_API_KEY or VPO_API_KEY == "change-me":
        raise HTTPException(status_code=500, detail="VPO_API_KEY is not configured.")

    return hmac.new(
        VPO_API_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def require_valid_report_signature(
    keywords: str,
    start_month: str,
    end_month: str,
    period_basis: str,
    mode: str,
    raw_limit: int,
    refresh_cache: bool,
    expires: int,
    sig: str,
) -> None:
    if expires < int(time()):
        raise HTTPException(status_code=401, detail="Download link expired.")

    expected = sign_report_payload(report_signature_payload(
        keywords=keywords,
        start_month=start_month,
        end_month=end_month,
        period_basis=period_basis,
        mode=mode,
        raw_limit=raw_limit,
        refresh_cache=refresh_cache,
        expires=expires,
    ))

    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=401, detail="Invalid download signature.")


def gcs_client() -> storage.Client:
    if GCS_SERVICE_ACCOUNT_JSON:
        try:
            service_account_info = json.loads(GCS_SERVICE_ACCOUNT_JSON)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"GCS_SERVICE_ACCOUNT_JSON is invalid JSON: {exc}") from exc

        return storage.Client.from_service_account_info(service_account_info)

    if GOOGLE_APPLICATION_CREDENTIALS:
        credentials_path = Path(GOOGLE_APPLICATION_CREDENTIALS)
        if not credentials_path.exists():
            raise HTTPException(status_code=500, detail=f"Credentials file not found: {credentials_path}")

        return storage.Client.from_service_account_json(str(credentials_path))

    return storage.Client()


def google_credentials(scopes: list[str]):
    if GOOGLE_OAUTH_TOKEN_JSON:
        try:
            token_info = json.loads(GOOGLE_OAUTH_TOKEN_JSON)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"GOOGLE_OAUTH_TOKEN_JSON is invalid JSON: {exc}") from exc

        return UserCredentials.from_authorized_user_info(token_info, scopes=scopes)

    if GCS_SERVICE_ACCOUNT_JSON:
        try:
            service_account_info = json.loads(GCS_SERVICE_ACCOUNT_JSON)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"GCS_SERVICE_ACCOUNT_JSON is invalid JSON: {exc}") from exc

        return service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=scopes,
        )

    if GOOGLE_APPLICATION_CREDENTIALS:
        credentials_path = Path(GOOGLE_APPLICATION_CREDENTIALS)
        if not credentials_path.exists():
            raise HTTPException(status_code=500, detail=f"Credentials file not found: {credentials_path}")

        return service_account.Credentials.from_service_account_file(
            str(credentials_path),
            scopes=scopes,
        )

    raise HTTPException(
        status_code=500,
        detail="Configure GCS_SERVICE_ACCOUNT_JSON or GOOGLE_APPLICATION_CREDENTIALS.",
    )


def object_name(filename: str) -> str:
    return f"{GCS_PREFIX}/{filename}" if GCS_PREFIX else filename


def catalog_status_object_name() -> str:
    return VPO_CATALOG_STATUS_GCS_OBJECT or object_name("catalog_status.parquet")


def ensure_marts(refresh_cache: bool = False, filenames: list[str] | None = None) -> dict[str, Path]:
    requested_files = filenames or REQUIRED_MART_FILES

    if VPO_LOCAL_MARTS_DIR is not None and VPO_LOCAL_MARTS_DIR.exists():
        paths = {filename: VPO_LOCAL_MARTS_DIR / filename for filename in requested_files}
        missing = [str(path) for path in paths.values() if not path.exists()]
        if missing:
            raise HTTPException(
                status_code=500,
                detail=f"Local mart files not found: {', '.join(missing)}",
            )
        return paths

    if not GCS_BUCKET:
        raise HTTPException(status_code=500, detail="GCS_BUCKET is not configured.")

    VPO_API_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    client = gcs_client()
    bucket = client.bucket(GCS_BUCKET)

    paths: dict[str, Path] = {}

    for filename in requested_files:
        local_path = VPO_API_CACHE_DIR / filename
        paths[filename] = local_path

        if local_path.exists() and not refresh_cache:
            continue

        blob = bucket.blob(object_name(filename))
        if not blob.exists(client):
            raise HTTPException(status_code=500, detail=f"GCS object not found: gs://{GCS_BUCKET}/{blob.name}")

        blob.download_to_filename(str(local_path))

    return paths


def load_catalog_status() -> pl.DataFrame:
    if not CATALOG_STATUS_PATH.exists() and GCS_BUCKET and VPO_CATALOG_STATUS_SYNC_GCS:
        try:
            client = gcs_client()
            bucket = client.bucket(GCS_BUCKET)
            blob = bucket.blob(catalog_status_object_name())
            if blob.exists(client):
                CATALOG_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
                blob.download_to_filename(str(CATALOG_STATUS_PATH))
        except Exception:
            # Catalog status is a governance layer. If remote sync is unavailable,
            # the API can still operate with the local/default active status.
            pass

    if not CATALOG_STATUS_PATH.exists():
        return pl.DataFrame({
            "catalog_key": pl.Series([], dtype=pl.Utf8),
            "active": pl.Series([], dtype=pl.Boolean),
            "include_in_reports": pl.Series([], dtype=pl.Boolean),
            "catalog_business_status": pl.Series([], dtype=pl.Utf8),
            "status_notes": pl.Series([], dtype=pl.Utf8),
            "label_normalized_override": pl.Series([], dtype=pl.Utf8),
            "updated_at": pl.Series([], dtype=pl.Utf8),
        })
    status_df = pl.read_parquet(CATALOG_STATUS_PATH)
    if "label_normalized_override" not in status_df.columns:
        status_df = status_df.with_columns(pl.lit(None).cast(pl.Utf8).alias("label_normalized_override"))
    return status_df


def normalized_label_expr(expr: pl.Expr) -> pl.Expr:
    cleaned = (
        expr
        .fill_null("")
        .cast(pl.Utf8, strict=False)
        .str.strip_chars()
        .str.replace_all(r"(?i)^\s*(?:\([pc]\)|[℗©])\.?\s*", "")
        .str.replace_all(r"(?i)^\s*[pc]\.?\s+((?:19|20)\d{2}\b)", "$1")
        .str.replace_all(r"^\s*(?:19|20)\d{2}\s*", "")
        .str.replace_all(r"(?i)^\s*(?:\([pc]\)|[℗©])\.?\s*", "")
        .str.replace_all(r"(?i)^\s*[pc]\.?\s+((?:19|20)\d{2}\b)", "$1")
        .str.replace_all(r"^\s*(?:19|20)\d{2}\s*", "")
        .str.replace_all(r"\s+", " ")
        .str.strip_chars(" -–—")
    )
    return pl.when(cleaned == "").then(pl.lit(None).cast(pl.Utf8)).otherwise(cleaned)


def save_catalog_status(df: pl.DataFrame) -> None:
    CATALOG_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(CATALOG_STATUS_PATH)
    if GCS_BUCKET and VPO_CATALOG_STATUS_SYNC_GCS:
        client = gcs_client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(catalog_status_object_name())
        blob.upload_from_filename(str(CATALOG_STATUS_PATH))


def configure_catalog_report_env(marts: dict[str, Path] | None = None) -> None:
    if marts and CATALOG_MASTER_FILE in marts:
        os.environ["VPO_CATALOG_MASTER_PATH"] = str(marts[CATALOG_MASTER_FILE])
    os.environ["VPO_CATALOG_STATUS_PATH"] = str(CATALOG_STATUS_PATH)


def shift_month(month: str, delta: int) -> str:
    year, month_number = (int(part) for part in month.split("-", 1))
    month_index = year * 12 + month_number - 1 + delta
    shifted_year = month_index // 12
    shifted_month = month_index % 12 + 1
    return f"{shifted_year:04d}-{shifted_month:02d}"


def previous_calendar_month(today: date | None = None) -> str:
    current = today or date.today()
    return shift_month(f"{current.year:04d}-{current.month:02d}", -1)


def default_source_monitor_config() -> list[dict]:
    return [
        {
            "id": "ada_mawz",
            "source": "ada",
            "account": "mawz",
            "display_name": "ADA / Mawz",
            "input_path": "input_raw/ada/mawz",
            "expected_frequency": "monthly",
            "max_age_months": 2,
            "monitoring_active": True,
            "alert_silenced": False,
            "portal_url": "",
            "notes": "TXT mensual. Net Royalty Payable es el neto reportable; statements sin actividad son validos.",
        },
        {
            "id": "ada_indyana_records",
            "source": "ada",
            "account": "indyana_records",
            "display_name": "ADA / Indyana Records",
            "input_path": "input_raw/ada/Indyana Records",
            "expected_frequency": "monthly",
            "max_age_months": 2,
            "monitoring_active": True,
            "alert_silenced": False,
            "portal_url": "",
            "notes": "TXT mensual de la cuenta 99500 / Indyana Records LLC. Net Royalty Payable es el neto reportable.",
        },
        {
            "id": "dashgo_mawzrecords",
            "source": "dashgo",
            "account": "mawzrecords",
            "display_name": "DashGo / Mawz Records",
            "input_path": "input_raw/dashgo",
            "expected_frequency": "monthly",
            "max_age_months": 2,
            "monitoring_active": True,
            "alert_silenced": False,
            "portal_url": "",
            "notes": "",
        },
        {
            "id": "fuga_indyana_records",
            "source": "fuga",
            "account": "indyana_records",
            "display_name": "FUGA / Indyana Records",
            "input_path": "input_raw/fuga",
            "expected_frequency": "monthly",
            "max_age_months": 2,
            "monitoring_active": True,
            "alert_silenced": False,
            "portal_url": "",
            "notes": "",
        },
        {
            "id": "onerpm_gusty_dj",
            "source": "onerpm",
            "account": "gusty_dj",
            "display_name": "ONErpm / Gusty DJ",
            "input_path": "input_raw/onerpm/gusty_dj",
            "expected_frequency": "monthly",
            "max_age_months": 2,
            "monitoring_active": True,
            "alert_silenced": False,
            "portal_url": "",
            "notes": "",
        },
        {
            "id": "onerpm_henry_remix",
            "source": "onerpm",
            "account": "henry_remix",
            "display_name": "ONErpm / Henry Remix",
            "input_path": "input_raw/onerpm/henry_remix",
            "expected_frequency": "monthly",
            "max_age_months": 2,
            "monitoring_active": True,
            "alert_silenced": False,
            "portal_url": "",
            "notes": "",
        },
        {
            "id": "onerpm_la_nueva_sangre",
            "source": "onerpm",
            "account": "la_nueva_sangre",
            "display_name": "ONErpm / La Nueva Sangre",
            "input_path": "input_raw/onerpm/la_nueva_sangre",
            "expected_frequency": "monthly",
            "max_age_months": 2,
            "monitoring_active": True,
            "alert_silenced": False,
            "portal_url": "",
            "notes": "Cuenta externa tipo Gusty: Masters y Youtube Channels para catalogo; Shares solo como flags.",
        },
        {
            "id": "onerpm_mawzrecords",
            "source": "onerpm",
            "account": "mawzrecords",
            "display_name": "ONErpm / Mawz Records",
            "input_path": "input_raw/onerpm/mawzrecords",
            "expected_frequency": "monthly",
            "max_age_months": 2,
            "monitoring_active": True,
            "alert_silenced": False,
            "portal_url": "",
            "notes": "",
        },
        {
            "id": "orchard_mawzrecords",
            "source": "orchard",
            "account": "mawzrecords",
            "display_name": "Orchard / Mawz Records",
            "input_path": "input_raw/orchard",
            "expected_frequency": "monthly",
            "max_age_months": 2,
            "monitoring_active": True,
            "alert_silenced": False,
            "portal_url": "",
            "notes": "",
        },
        {
            "id": "soundon_soundon",
            "source": "soundon",
            "account": "soundon",
            "display_name": "SoundOn",
            "input_path": "input_raw/soundon",
            "expected_frequency": "monthly",
            "max_age_months": 2,
            "monitoring_active": True,
            "alert_silenced": False,
            "portal_url": "",
            "notes": "",
        },
        {
            "id": "altafonte_legacy",
            "source": "altafonte",
            "account": "legacy",
            "display_name": "Altafonte / Legacy",
            "input_path": "input_raw/altafonte",
            "expected_frequency": "legacy",
            "max_age_months": 24,
            "monitoring_active": False,
            "alert_silenced": True,
            "portal_url": "",
            "notes": "Legacy historico. No alertar, pero conservar datos en reportes.",
        },
    ]


def source_monitor_id(source: str, account: str) -> str:
    safe_source = "".join(ch if ch.isalnum() else "_" for ch in source.lower()).strip("_")
    safe_account = "".join(ch if ch.isalnum() else "_" for ch in account.lower()).strip("_")
    return f"{safe_source}_{safe_account}"


def load_source_monitor_config() -> list[dict]:
    defaults = default_source_monitor_config()
    if not SOURCE_MONITOR_CONFIG_PATH.exists():
        return defaults

    try:
        overrides = json.loads(SOURCE_MONITOR_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return defaults

    if not isinstance(overrides, list):
        return defaults

    by_id = {item["id"]: dict(item) for item in defaults}
    for item in overrides:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            continue
        base = by_id.get(item_id, {"id": item_id})
        base.update(item)
        by_id[item_id] = base
    return list(by_id.values())


def save_source_monitor_config(items: list[dict]) -> None:
    SOURCE_MONITOR_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_MONITOR_CONFIG_PATH.write_text(
        json.dumps(items, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def month_age(month: str | None, today: date | None = None) -> int | None:
    if not month:
        return None
    try:
        year, month_number = (int(part) for part in str(month)[:7].split("-", 1))
    except ValueError:
        return None
    current = today or date.today()
    return (current.year - year) * 12 + (current.month - month_number)


def latest_raw_file_info(input_path: str) -> dict:
    folder = (BASE / input_path).resolve()
    try:
        folder.relative_to(BASE.resolve())
    except ValueError:
        return {"raw_files": 0, "latest_raw_file": None, "latest_raw_modified": None, "raw_file_names": []}

    if not folder.exists():
        return {"raw_files": 0, "latest_raw_file": None, "latest_raw_modified": None, "raw_file_names": []}

    files = sorted([path for path in folder.iterdir() if path.is_file()], key=lambda path: path.name.lower())
    latest = max(files, key=lambda path: path.stat().st_mtime, default=None)
    return {
        "raw_files": len(files),
        "latest_raw_file": latest.name if latest else None,
        "latest_raw_modified": datetime.fromtimestamp(latest.stat().st_mtime).isoformat(timespec="seconds") if latest else None,
        "raw_file_names": [path.name for path in files],
    }


def count_csv_rows(path: Path) -> int | None:
    try:
        return pl.read_csv(
            path,
            infer_schema_length=100,
            ignore_errors=True,
            encoding="utf8-lossy",
        ).height
    except Exception:
        return None


def count_excel_sheet_rows(path: Path, sheet_name: str) -> int | None:
    try:
        return pl.read_excel(path, sheet_name=sheet_name).height
    except Exception:
        return None


def count_onerpm_monitor_rows(path: Path) -> dict:
    account = path.parent.name.lower()
    included_sheets = ["Masters", "Youtube Channels"]
    if account == "mawzrecords":
        included_sheets.append("Shares In & Out")

    rows_by_sheet = {
        sheet_name: count_excel_sheet_rows(path, sheet_name)
        for sheet_name in included_sheets
    }
    total_rows = sum(row_count or 0 for row_count in rows_by_sheet.values())
    return {
        "rows": total_rows,
        "rows_by_sheet": rows_by_sheet,
    }


def classify_raw_file(source: str, path: Path, mart_names: set[str]) -> dict:
    name = path.name
    lower_name = name.lower()

    if name in mart_names:
        return {"file_name": name, "status": "loaded_to_mart", "reason": "Cargado en mart nuevo."}

    if source == "altafonte":
        return {
            "file_name": name,
            "status": "legacy_manual",
            "reason": "Legacy historico cargado dentro del mart Orchard/Altafonte.",
        }

    if source == "soundon":
        if "_discovery mode.csv" in lower_name:
            return {
                "file_name": name,
                "status": "ignored_audit_detail",
                "reason": "Detalle de deduccion Discovery Mode ya incluido en My Royalty; se valida por auditoria.",
                "rows": count_csv_rows(path),
            }

        if "_summary.csv" in lower_name:
            return {
                "file_name": name,
                "status": "ignored_summary",
                "reason": "Summary de SoundOn se omite para no duplicar My Royalty.",
            }

        if "_share in.csv" in lower_name or "_share out.csv" in lower_name:
            row_count = count_csv_rows(path)
            if row_count == 0:
                return {
                    "file_name": name,
                    "status": "ignored_empty",
                    "reason": "Share in/out de SoundOn sin filas.",
                    "rows": row_count,
                }
            return {
                "file_name": name,
                "status": "pending_real",
                "reason": "Share in/out con filas; debe entrar al ingest nuevo.",
                "rows": row_count,
            }

    if source == "ada" and path.suffix.lower() == ".txt":
        try:
            content = path.read_text(encoding="utf-8-sig").strip()
        except UnicodeDecodeError:
            content = path.read_text(encoding="cp1252").strip()
        if content == "No Earning Activity for this Royalty Period":
            return {
                "file_name": name,
                "status": "ignored_empty",
                "reason": "Statement ADA valido sin actividad de regalias.",
                "rows": 0,
            }

    if source == "fuga" and path.suffix.lower() == ".csv":
        row_count = count_csv_rows(path)
        if row_count == 0:
            return {
                "file_name": name,
                "status": "ignored_empty",
                "reason": "Statement FUGA sin movimientos.",
                "rows": row_count,
            }

    if source == "onerpm" and path.suffix.lower() in {".xlsx", ".xlsm"}:
        monitor_rows = count_onerpm_monitor_rows(path)
        if monitor_rows["rows"] == 0:
            return {
                "file_name": name,
                "status": "ignored_no_included_rows",
                "reason": "Statement ONErpm sin filas en hojas cargables para esta cuenta.",
                **monitor_rows,
            }
        return {
            "file_name": name,
            "status": "pending_real",
            "reason": "Tiene filas en hojas cargables y no aparece en el mart nuevo.",
            **monitor_rows,
        }

    return {"file_name": name, "status": "pending_real", "reason": "No aparece en el mart nuevo."}


def build_raw_inventory(source: str, input_path: str, mart_names: set[str]) -> dict:
    folder = (BASE / input_path).resolve()
    try:
        folder.relative_to(BASE.resolve())
    except ValueError:
        return {"items": [], "summary": {}}

    if not folder.exists():
        return {"items": [], "summary": {}}

    items = [
        classify_raw_file(source, path, mart_names)
        for path in sorted([item for item in folder.iterdir() if item.is_file()], key=lambda item: item.name.lower())
    ]
    summary: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "unknown")
        summary[status] = summary.get(status, 0) + 1
    return {"items": items, "summary": summary}


def source_monitor_mart_summary(standardized_path: Path) -> dict[tuple[str, str], dict]:
    if not standardized_path.exists():
        return {}

    scan = pl.scan_parquet(standardized_path)
    schema = scan.collect_schema()
    required_columns = {"source", "account", "statement_period"}
    if not required_columns.issubset(set(schema.names())):
        return {}

    has_statement_file = "statement_file_name" in schema.names()
    selected_columns = ["source", "account", "statement_period"]
    if has_statement_file:
        selected_columns.append("statement_file_name")

    aggregations = [
        pl.max("statement_period").alias("last_statement_period"),
        pl.len().alias("rows_in_mart"),
    ]
    if has_statement_file:
        aggregations.extend([
            pl.n_unique("statement_file_name").alias("statement_files_in_mart"),
            pl.col("statement_file_name").unique().alias("mart_file_names"),
        ])

    frame = (
        scan
        .select(selected_columns)
        .filter(pl.col("source").is_not_null() & pl.col("account").is_not_null())
        .group_by(["source", "account"])
        .agg(aggregations)
        .collect()
    )

    return {
        (row["source"], row["account"]): {
            **dict(row),
            "statement_files_in_mart": int(row.get("statement_files_in_mart") or 0),
            "mart_file_names": row.get("mart_file_names") or [],
        }
        for row in frame.to_dicts()
    }


def latest_period(*periods: str | None) -> str | None:
    valid = [period for period in periods if period]
    if not valid:
        return None
    return sorted(valid)[-1]


def publish_required_marts_to_gcs() -> dict:
    if not GCS_BUCKET:
        raise HTTPException(status_code=500, detail="GCS_BUCKET no esta configurado.")

    preparation = prepare_analytics_package_for_publish()
    validation = validate_analytics_package_for_publish()

    client = gcs_client()
    bucket = client.bucket(GCS_BUCKET)
    prefix = GCS_PREFIX.strip("/")
    uploaded = []

    for filename in REQUIRED_MART_FILES:
        local_path = BASE / "warehouse" / "marts" / filename
        if not local_path.exists():
            raise HTTPException(status_code=500, detail=f"No existe mart requerido: {local_path}")

        object_name = f"{prefix}/{filename}" if prefix else filename
        blob = bucket.blob(object_name)
        blob.upload_from_filename(str(local_path))
        uploaded.append({
            "file_name": filename,
            "object_name": object_name,
            "size_bytes": local_path.stat().st_size,
            "size_mb": round(local_path.stat().st_size / 1024 / 1024, 2),
        })

    return {
        "ok": True,
        "published_at": datetime.now().isoformat(timespec="seconds"),
        "bucket": GCS_BUCKET,
        "prefix": prefix,
        "preparation": preparation,
        "validation": validation,
        "uploaded": uploaded,
    }


def public_publish_job(job: dict) -> dict:
    visible = dict(job)
    visible.pop("thread", None)
    return visible


def latest_running_publish_job() -> dict | None:
    with PUBLISH_JOBS_LOCK:
        running = [
            job for job in PUBLISH_JOBS.values()
            if job.get("status") in {"queued", "running"}
        ]
        if not running:
            return None
        return public_publish_job(sorted(running, key=lambda item: item.get("created_at") or "")[-1])


def update_publish_job(job_id: str, **updates: object) -> None:
    with PUBLISH_JOBS_LOCK:
        job = PUBLISH_JOBS.get(job_id)
        if not job:
            return
        job.update(updates)


def run_publish_job(job_id: str) -> None:
    update_publish_job(
        job_id,
        status="running",
        stage="cerrando_paquete",
        started_at=datetime.now().isoformat(timespec="seconds"),
    )
    try:
        result = publish_required_marts_to_gcs()
        update_publish_job(
            job_id,
            status="completed",
            stage="terminado",
            finished_at=datetime.now().isoformat(timespec="seconds"),
            result=result,
        )
    except HTTPException as exc:
        update_publish_job(
            job_id,
            status="failed",
            stage="error",
            finished_at=datetime.now().isoformat(timespec="seconds"),
            error=exc.detail,
        )
    except Exception as exc:
        update_publish_job(
            job_id,
            status="failed",
            stage="error",
            finished_at=datetime.now().isoformat(timespec="seconds"),
            error=str(exc),
        )


def start_publish_job() -> dict:
    running = latest_running_publish_job()
    if running:
        return running

    job_id = uuid.uuid4().hex
    now = datetime.now().isoformat(timespec="seconds")
    job = {
        "job_id": job_id,
        "status": "queued",
        "stage": "en_cola",
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
    }
    thread = threading.Thread(target=run_publish_job, args=(job_id,), daemon=True)
    job["thread"] = thread
    with PUBLISH_JOBS_LOCK:
        PUBLISH_JOBS[job_id] = job
    thread.start()
    return public_publish_job(job)


def get_publish_job(job_id: str) -> dict:
    with PUBLISH_JOBS_LOCK:
        job = PUBLISH_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Publish job not found.")
        return public_publish_job(job)


def mart_path(filename: str) -> Path:
    return BASE / "warehouse" / "marts" / filename


def parquet_summary(path: Path, period_columns: list[str]) -> dict:
    summary: dict[str, object] = {
        "path": str(path),
        "exists": path.exists(),
        "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds") if path.exists() else None,
        "size_mb": round(path.stat().st_size / 1024 / 1024, 2) if path.exists() else None,
    }
    if not path.exists():
        return summary
    try:
        frame = pl.scan_parquet(path)
        columns = set(frame.collect_schema().names())
        expressions: list[pl.Expr] = [pl.len().alias("rows")]
        for column in period_columns:
            if column in columns:
                expressions.extend([
                    pl.min(column).alias(f"first_{column}"),
                    pl.max(column).alias(f"last_{column}"),
                ])
        values = frame.select(expressions).collect().to_dicts()[0]
        summary.update(values)
    except Exception as exc:
        summary["error"] = str(exc)
    return summary


def run_publish_preparation_script(script_name: str) -> dict:
    result = run_pipeline_script(script_name)
    if result["returncode"] != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Fallo cierre analitico antes de publicar: {script_name}.",
                "script": result,
            },
        )
    return result


def prepare_analytics_package_for_publish() -> dict:
    standardized_path = mart_path(STANDARDIZED_FILE)
    song_path = mart_path(SONG_FILE)
    if not standardized_path.exists():
        raise HTTPException(status_code=500, detail=f"No existe mart requerido: {standardized_path}")
    if not song_path.exists():
        raise HTTPException(status_code=500, detail=f"No existe mart requerido: {song_path}")

    scripts = [
        run_publish_preparation_script("build_statement_summary_mart.py"),
        run_publish_preparation_script("build_catalog_master.py"),
    ]
    digital_summary_path = build_digital_income_summary_mart(standardized_path, refresh_cache=True)
    royalties_dashboard_summary_path = build_royalties_dashboard_summary_mart(standardized_path, refresh_cache=True)

    return {
        "closed_at": datetime.now().isoformat(timespec="seconds"),
        "scripts": scripts,
        "digital_income_summary": parquet_summary(digital_summary_path, ["statement_period"]),
        "royalties_dashboard_summary": parquet_summary(royalties_dashboard_summary_path, ["statement_period", "transaction_month"]),
    }


def validate_analytics_package_for_publish() -> dict:
    summaries = {
        SONG_FILE: parquet_summary(mart_path(SONG_FILE), ["transaction_month"]),
        STANDARDIZED_FILE: parquet_summary(mart_path(STANDARDIZED_FILE), ["statement_period", "transaction_month"]),
        CATALOG_MASTER_FILE: parquet_summary(mart_path(CATALOG_MASTER_FILE), ["first_transaction_month", "last_transaction_month"]),
        STATEMENT_SUMMARY_FILE: parquet_summary(mart_path(STATEMENT_SUMMARY_FILE), ["statement_period"]),
        DIGITAL_INCOME_SUMMARY_FILE: parquet_summary(mart_path(DIGITAL_INCOME_SUMMARY_FILE), ["statement_period"]),
        ROYALTIES_DASHBOARD_SUMMARY_FILE: parquet_summary(mart_path(ROYALTIES_DASHBOARD_SUMMARY_FILE), ["statement_period", "transaction_month"]),
    }
    missing = [filename for filename, summary in summaries.items() if not summary.get("exists")]
    if missing:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "No se puede publicar: faltan marts requeridos.",
                "missing": missing,
                "summaries": summaries,
            },
        )

    stale = []
    standardized_mtime = mart_path(STANDARDIZED_FILE).stat().st_mtime
    song_mtime = mart_path(SONG_FILE).stat().st_mtime
    dependency_mtime = max(standardized_mtime, song_mtime)
    for filename in [CATALOG_MASTER_FILE, STATEMENT_SUMMARY_FILE, DIGITAL_INCOME_SUMMARY_FILE, ROYALTIES_DASHBOARD_SUMMARY_FILE]:
        if mart_path(filename).stat().st_mtime + 0.001 < dependency_mtime:
            stale.append(filename)

    song_last_tx = summaries[SONG_FILE].get("last_transaction_month")
    catalog_last_tx = summaries[CATALOG_MASTER_FILE].get("last_last_transaction_month")
    if song_last_tx and catalog_last_tx and str(catalog_last_tx) < str(song_last_tx):
        stale.append(f"{CATALOG_MASTER_FILE}: activity {catalog_last_tx} < song_level {song_last_tx}")

    standardized_last_statement = summaries[STANDARDIZED_FILE].get("last_statement_period")
    statement_summary_last = summaries[STATEMENT_SUMMARY_FILE].get("last_statement_period")
    digital_summary_last = summaries[DIGITAL_INCOME_SUMMARY_FILE].get("last_statement_period")
    royalties_dashboard_last = summaries[ROYALTIES_DASHBOARD_SUMMARY_FILE].get("last_statement_period")
    if standardized_last_statement and statement_summary_last and str(statement_summary_last) < str(standardized_last_statement):
        stale.append(f"{STATEMENT_SUMMARY_FILE}: statement {statement_summary_last} < standardized {standardized_last_statement}")
    if standardized_last_statement and digital_summary_last and str(digital_summary_last) < str(standardized_last_statement):
        stale.append(f"{DIGITAL_INCOME_SUMMARY_FILE}: statement {digital_summary_last} < standardized {standardized_last_statement}")
    if standardized_last_statement and royalties_dashboard_last and str(royalties_dashboard_last) < str(standardized_last_statement):
        stale.append(f"{ROYALTIES_DASHBOARD_SUMMARY_FILE}: statement {royalties_dashboard_last} < standardized {standardized_last_statement}")

    if stale:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "No se puede publicar: el paquete analitico no esta cerrado.",
                "stale": stale,
                "summaries": summaries,
            },
        )

    return {
        "ok": True,
        "validated_at": datetime.now().isoformat(timespec="seconds"),
        "summaries": summaries,
    }


def source_monitor_pipeline_scripts(source: str) -> list[str]:
    source_scripts = {
        "dashgo": ["ingest_standardized_dashgo.py", "build_song_level_dashgo.py"],
        "fuga": ["ingest_standardized_fuga.py", "build_song_level_fuga.py"],
        "onerpm": ["ingest_standardized_onerpm.py", "build_song_level_onerpm.py"],
        "orchard": ["ingest_standardized_orchard.py", "build_song_level_orchard.py"],
        "soundon": ["ingest_standardized_soundon.py", "build_song_level_soundon.py"],
        "ada": ["ingest_standardized_ada.py", "build_song_level_ada.py"],
    }
    scripts = source_scripts.get(source, [])
    if not scripts:
        return []
    return [
        *scripts,
        "build_consolidated_marts.py",
        "build_statement_summary_mart.py",
        "build_catalog_master.py",
    ]


def run_pipeline_script(script_name: str) -> dict:
    script_path = SCRIPTS / script_name
    if not script_path.exists():
        raise HTTPException(status_code=500, detail=f"No existe script: {script_name}")

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(SCRIPTS),
        text=True,
        capture_output=True,
    )
    output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    lines = output.splitlines()
    return {
        "script": script_name,
        "returncode": result.returncode,
        "tail": lines[-40:],
    }


def statement_summary_for_files(standardized_path: Path, source: str, account: str, file_names: list[str]) -> list[dict]:
    if not file_names or not standardized_path.exists():
        return []

    frame = (
        pl.scan_parquet(standardized_path)
        .filter(
            (pl.col("source") == source)
            & (pl.col("account") == account)
            & pl.col("statement_file_name").is_in(file_names)
        )
        .group_by("statement_period")
        .agg([
            pl.len().alias("rows"),
            pl.sum("amount_usd").alias("amount_usd"),
            pl.n_unique("statement_file_name").alias("files"),
        ])
        .sort("statement_period")
        .collect()
    )

    return frame.to_dicts()


def get_source_monitor_item(monitor_id: str) -> dict | None:
    marts = ensure_marts(refresh_cache=False, filenames=[STANDARDIZED_FILE])
    mart_summary = source_monitor_mart_summary(marts[STANDARDIZED_FILE])
    for config in load_source_monitor_config():
        item_id = config.get("id") or source_monitor_id(str(config.get("source") or ""), str(config.get("account") or ""))
        if item_id != monitor_id:
            continue
        source = str(config.get("source") or "")
        account = str(config.get("account") or "")
        raw_info = latest_raw_file_info(str(config.get("input_path") or ""))
        mart_info = mart_summary.get((source, account), {})
        mart_names = set(mart_info.get("mart_file_names") or [])
        raw_inventory = build_raw_inventory(source, str(config.get("input_path") or ""), mart_names)
        pending_real_files = [
            str(item.get("file_name"))
            for item in raw_inventory["items"]
            if item.get("status") == "pending_real"
        ]
        return {
            "id": item_id,
            "source": source,
            "account": account,
            "display_name": config.get("display_name") or f"{source} / {account}",
            "last_statement_period": mart_info.get("last_statement_period"),
            "unprocessed_raw_files": pending_real_files,
        }
    return None


def first_business_day(month: str) -> str:
    year, month_number = (int(part) for part in month.split("-", 1))
    current = date(year, month_number, 1)
    while current.weekday() >= 5:
        current = current.replace(day=current.day + 1)
    return current.isoformat()


def last_business_day(month: str) -> str:
    year, month_number = (int(part) for part in month.split("-", 1))
    current = date(year, month_number, monthrange(year, month_number)[1])
    while current.weekday() >= 5:
        current = current.replace(day=current.day - 1)
    return current.isoformat()


def booking_connect():
    return operational_sqlite_compatible_connect()


def init_booking_db() -> None:
    if operational_db_settings().driver == "postgres":
        return
    with booking_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_artists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stage_name TEXT NOT NULL UNIQUE,
                legal_name TEXT,
                cuit TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                notes TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_name TEXT NOT NULL UNIQUE,
                legal_name TEXT,
                cuit TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                compensation_type TEXT NOT NULL DEFAULT 'none',
                salary_amount REAL NOT NULL DEFAULT 0,
                salary_currency TEXT NOT NULL DEFAULT 'ARS',
                salary_frequency TEXT NOT NULL DEFAULT 'monthly',
                salary_notes TEXT,
                notes TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        ensure_sqlite_column(conn, "employees", "compensation_type", "TEXT NOT NULL DEFAULT 'none'")
        ensure_sqlite_column(conn, "employees", "salary_amount", "REAL NOT NULL DEFAULT 0")
        ensure_sqlite_column(conn, "employees", "salary_currency", "TEXT NOT NULL DEFAULT 'ARS'")
        ensure_sqlite_column(conn, "employees", "salary_frequency", "TEXT NOT NULL DEFAULT 'monthly'")
        ensure_sqlite_column(conn, "employees", "salary_notes", "TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS employee_functions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                function_code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(employee_id, function_code)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                last_login_at TEXT,
                global_role TEXT NOT NULL DEFAULT 'viewer',
                active INTEGER NOT NULL DEFAULT 1,
                auth_source TEXT NOT NULL DEFAULT 'operational',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        ensure_sqlite_column(conn, "app_users", "password_hash", "TEXT")
        ensure_sqlite_column(conn, "app_users", "must_change_password", "INTEGER NOT NULL DEFAULT 0")
        ensure_sqlite_column(conn, "app_users", "last_login_at", "TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_key TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS module_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                module_key TEXT NOT NULL,
                can_access INTEGER NOT NULL DEFAULT 0,
                can_create INTEGER NOT NULL DEFAULT 0,
                can_view_history INTEGER NOT NULL DEFAULT 0,
                can_edit INTEGER NOT NULL DEFAULT 0,
                can_approve INTEGER NOT NULL DEFAULT 0,
                scope_json TEXT NOT NULL DEFAULT '[]',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(employee_id, module_key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at TEXT NOT NULL,
                actor_username TEXT,
                employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                module_key TEXT,
                action TEXT NOT NULL,
                entity_table TEXT,
                entity_id TEXT,
                before_json TEXT,
                after_json TEXT,
                source TEXT NOT NULL DEFAULT 'web',
                notes TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_shows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artist TEXT NOT NULL,
                show_date TEXT NOT NULL,
                venue TEXT NOT NULL,
                city TEXT,
                tour_manager TEXT,
                seller TEXT,
                status TEXT NOT NULL,
                currency TEXT NOT NULL,
                fx_rate REAL,
                contracted_cachet_amount REAL NOT NULL DEFAULT 0,
                venue_collected_amount REAL NOT NULL DEFAULT 0,
                venue_balance_amount REAL NOT NULL DEFAULT 0,
                venue_payment_status TEXT NOT NULL DEFAULT 'cobrado',
                venue_shortfall_policy TEXT NOT NULL DEFAULT 'deuda_boliche',
                venue_payment_notes TEXT,
                cachet_amount REAL NOT NULL DEFAULT 0,
                expenses_amount REAL NOT NULL DEFAULT 0,
                net_amount REAL NOT NULL DEFAULT 0,
                pre_split_adjustments_amount REAL NOT NULL DEFAULT 0,
                split_base_amount REAL NOT NULL DEFAULT 0,
                artist_percent REAL NOT NULL DEFAULT 0,
                producer_percent REAL NOT NULL DEFAULT 0,
                artist_share_amount REAL NOT NULL DEFAULT 0,
                producer_share_amount REAL NOT NULL DEFAULT 0,
                artist_cash_target_amount REAL NOT NULL DEFAULT 0,
                producer_cash_target_amount REAL NOT NULL DEFAULT 0,
                artist_paid_amount REAL NOT NULL DEFAULT 0,
                producer_received_amount REAL NOT NULL DEFAULT 0,
                balance_artist_amount REAL NOT NULL DEFAULT 0,
                balance_producer_amount REAL NOT NULL DEFAULT 0,
                receipt_refs_json TEXT NOT NULL DEFAULT '[]',
                settlement_status TEXT NOT NULL DEFAULT 'pendiente',
                settlement_group TEXT,
                settlement_closed_at TEXT,
                settlement_notes TEXT,
                origin_type TEXT,
                origin_id INTEGER,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS caserio_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                venue TEXT NOT NULL,
                city TEXT,
                responsible TEXT,
                status TEXT NOT NULL,
                currency TEXT NOT NULL,
                fx_rate REAL,
                gross_amount REAL NOT NULL DEFAULT 0,
                caserio_expected_amount REAL NOT NULL DEFAULT 0,
                producer_expected_amount REAL NOT NULL DEFAULT 0,
                total_expected_amount REAL NOT NULL DEFAULT 0,
                received_amount REAL NOT NULL DEFAULT 0,
                balance_amount REAL NOT NULL DEFAULT 0,
                receipt_refs_json TEXT NOT NULL DEFAULT '[]',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS caserio_event_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL REFERENCES caserio_events(id) ON DELETE CASCADE,
                line_type TEXT NOT NULL,
                description TEXT NOT NULL,
                artist TEXT,
                amount REAL NOT NULL DEFAULT 0,
                booking_show_id INTEGER REFERENCES booking_shows(id) ON DELETE SET NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_composite_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                venue TEXT NOT NULL,
                city TEXT,
                responsible TEXT,
                status TEXT NOT NULL,
                currency TEXT NOT NULL,
                fx_rate REAL,
                gross_amount REAL NOT NULL DEFAULT 0,
                general_expenses_amount REAL NOT NULL DEFAULT 0,
                allocated_amount REAL NOT NULL DEFAULT 0,
                producer_expected_amount REAL NOT NULL DEFAULT 0,
                received_amount REAL NOT NULL DEFAULT 0,
                balance_amount REAL NOT NULL DEFAULT 0,
                receipt_refs_json TEXT NOT NULL DEFAULT '[]',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_composite_event_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL REFERENCES booking_composite_events(id) ON DELETE CASCADE,
                concept TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_composite_event_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL REFERENCES booking_composite_events(id) ON DELETE CASCADE,
                line_type TEXT NOT NULL,
                description TEXT NOT NULL,
                artist TEXT,
                amount REAL NOT NULL DEFAULT 0,
                artist_percent REAL NOT NULL DEFAULT 0,
                producer_percent REAL NOT NULL DEFAULT 0,
                artist_paid_amount REAL NOT NULL DEFAULT 0,
                producer_received_amount REAL NOT NULL DEFAULT 0,
                booking_commission_exempt INTEGER NOT NULL DEFAULT 1,
                booking_commission_notes TEXT,
                booking_show_id INTEGER REFERENCES booking_shows(id) ON DELETE SET NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                show_id INTEGER NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
                movement_type TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                currency TEXT NOT NULL,
                fx_rate REAL,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_account_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                show_id INTEGER NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
                application_date TEXT NOT NULL,
                target_balance TEXT NOT NULL,
                application_type TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                effect_amount REAL NOT NULL DEFAULT 0,
                payment_method TEXT NOT NULL DEFAULT 'transferencia',
                counterparty TEXT,
                linked_show_id INTEGER REFERENCES booking_shows(id) ON DELETE SET NULL,
                proof_refs_json TEXT NOT NULL DEFAULT '[]',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_booking_account_app_show ON booking_account_applications(show_id, application_date)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_show_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                show_id INTEGER NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
                concept TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                currency TEXT NOT NULL,
                fx_rate REAL,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_pre_split_adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                show_id INTEGER NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
                concept TEXT NOT NULL,
                destination TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                currency TEXT NOT NULL,
                fx_rate REAL,
                recovery_auto_apply INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_direct_commissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                show_id INTEGER NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
                concept TEXT NOT NULL,
                recipient TEXT,
                destination TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                currency TEXT NOT NULL,
                fx_rate REAL,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_external_shares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                show_id INTEGER NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                percent REAL,
                amount REAL NOT NULL DEFAULT 0,
                currency TEXT NOT NULL,
                fx_rate REAL,
                cash_handled_by_vpo INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_artist_adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                show_id INTEGER NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
                concept TEXT NOT NULL,
                adjustment_type TEXT NOT NULL,
                area TEXT NOT NULL,
                impact TEXT NOT NULL,
                recoverable INTEGER NOT NULL DEFAULT 1,
                amount REAL NOT NULL DEFAULT 0,
                applied_amount REAL NOT NULL DEFAULT 0,
                currency TEXT NOT NULL,
                fx_rate REAL,
                artist_percent REAL NOT NULL DEFAULT 0,
                producer_percent REAL NOT NULL DEFAULT 0,
                artist_amount REAL NOT NULL DEFAULT 0,
                producer_amount REAL NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_artist_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artist TEXT NOT NULL,
                movement_date TEXT NOT NULL,
                movement_type TEXT NOT NULL,
                concept TEXT NOT NULL,
                category TEXT NOT NULL,
                project TEXT,
                amount REAL NOT NULL DEFAULT 0,
                original_amount REAL,
                recoverable INTEGER NOT NULL DEFAULT 1,
                artist_percent REAL NOT NULL DEFAULT 0,
                producer_percent REAL NOT NULL DEFAULT 0,
                show_id INTEGER REFERENCES booking_shows(id) ON DELETE SET NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS finance_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                artist TEXT,
                business_area TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'activo',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(name, artist, business_area)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS finance_staging_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                movement_date TEXT NOT NULL,
                artist TEXT NOT NULL,
                business_area TEXT NOT NULL,
                movement_type TEXT NOT NULL,
                category TEXT NOT NULL,
                project_id INTEGER REFERENCES finance_projects(id) ON DELETE SET NULL,
                project_name TEXT,
                concept TEXT NOT NULL,
                counterparty TEXT,
                paid_by TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'ARS',
                fx_rate REAL,
                amount_ars REAL NOT NULL DEFAULT 0,
                paid_amount REAL NOT NULL DEFAULT 0,
                paid_amount_ars REAL NOT NULL DEFAULT 0,
                pending_amount_ars REAL NOT NULL DEFAULT 0,
                payment_status TEXT NOT NULL DEFAULT 'pagado',
                due_date TEXT,
                recoverable INTEGER NOT NULL DEFAULT 0,
                recoverable_percent REAL NOT NULL DEFAULT 0,
                recovery_method TEXT NOT NULL DEFAULT 'none',
                artist_percent REAL NOT NULL DEFAULT 0,
                producer_percent REAL NOT NULL DEFAULT 100,
                account_effect TEXT NOT NULL DEFAULT 'inversion_indyana',
                status TEXT NOT NULL DEFAULT 'pendiente_control',
                source_type TEXT NOT NULL DEFAULT 'manual',
                source_id TEXT,
                proof_refs_json TEXT NOT NULL DEFAULT '[]',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS finance_recovery_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artist TEXT NOT NULL,
                application_date TEXT NOT NULL,
                finance_movement_id INTEGER NOT NULL REFERENCES finance_staging_movements(id) ON DELETE CASCADE,
                project_name TEXT,
                source_type TEXT NOT NULL DEFAULT 'booking',
                source_id TEXT,
                source_label TEXT,
                amount_ars REAL NOT NULL DEFAULT 0,
                recovery_method TEXT NOT NULL DEFAULT 'manual',
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS finance_movement_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                movement_id INTEGER NOT NULL REFERENCES finance_staging_movements(id) ON DELETE CASCADE,
                allocation_type TEXT NOT NULL DEFAULT 'indyana_cost',
                target_name TEXT NOT NULL,
                business_area TEXT,
                amount REAL NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'ARS',
                fx_rate REAL,
                amount_ars REAL NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        ensure_sqlite_column(conn, "finance_staging_movements", "paid_amount", "REAL NOT NULL DEFAULT 0")
        ensure_sqlite_column(conn, "finance_staging_movements", "paid_amount_ars", "REAL NOT NULL DEFAULT 0")
        ensure_sqlite_column(conn, "finance_staging_movements", "pending_amount_ars", "REAL NOT NULL DEFAULT 0")
        ensure_sqlite_column(conn, "finance_staging_movements", "payment_status", "TEXT NOT NULL DEFAULT 'pagado'")
        ensure_sqlite_column(conn, "finance_staging_movements", "due_date", "TEXT")
        ensure_sqlite_column(conn, "finance_staging_movements", "recovery_method", "TEXT NOT NULL DEFAULT 'none'")
        ensure_sqlite_column(conn, "booking_pre_split_adjustments", "recovery_auto_apply", "INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            """
            UPDATE finance_staging_movements
            SET paid_amount = amount,
                paid_amount_ars = amount_ars,
                pending_amount_ars = 0,
                payment_status = 'pagado'
            WHERE paid_amount = 0
              AND amount > 0
              AND amount_ars > 0
              AND payment_status = 'pagado'
            """
        )
        ensure_sqlite_column(conn, "booking_shows", "pre_split_adjustments_amount", "REAL NOT NULL DEFAULT 0")
        ensure_sqlite_column(conn, "booking_shows", "split_base_amount", "REAL NOT NULL DEFAULT 0")
        ensure_sqlite_column(conn, "booking_shows", "artist_cash_target_amount", "REAL NOT NULL DEFAULT 0")
        ensure_sqlite_column(conn, "booking_shows", "producer_cash_target_amount", "REAL NOT NULL DEFAULT 0")
        ensure_sqlite_column(conn, "booking_shows", "contracted_cachet_amount", "REAL NOT NULL DEFAULT 0")
        ensure_sqlite_column(conn, "booking_shows", "venue_collected_amount", "REAL NOT NULL DEFAULT 0")
        ensure_sqlite_column(conn, "booking_shows", "venue_balance_amount", "REAL NOT NULL DEFAULT 0")
        ensure_sqlite_column(conn, "booking_shows", "venue_payment_status", "TEXT NOT NULL DEFAULT 'cobrado'")
        ensure_sqlite_column(conn, "booking_shows", "venue_shortfall_policy", "TEXT NOT NULL DEFAULT 'deuda_boliche'")
        ensure_sqlite_column(conn, "booking_shows", "venue_payment_notes", "TEXT")
        ensure_sqlite_column(conn, "booking_shows", "booking_commission_exempt", "INTEGER NOT NULL DEFAULT 0")
        ensure_sqlite_column(conn, "booking_shows", "booking_commission_notes", "TEXT")
        ensure_sqlite_column(conn, "booking_shows", "settlement_status", "TEXT NOT NULL DEFAULT 'pendiente'")
        ensure_sqlite_column(conn, "booking_shows", "settlement_group", "TEXT")
        ensure_sqlite_column(conn, "booking_shows", "settlement_closed_at", "TEXT")
        ensure_sqlite_column(conn, "booking_shows", "settlement_notes", "TEXT")
        ensure_sqlite_column(conn, "booking_shows", "origin_type", "TEXT")
        ensure_sqlite_column(conn, "booking_shows", "origin_id", "INTEGER")
        ensure_sqlite_column(conn, "booking_artist_adjustments", "applied_amount", "REAL NOT NULL DEFAULT 0")
        ensure_sqlite_column(conn, "booking_artists", "active", "INTEGER NOT NULL DEFAULT 1")
        seed_app_modules(conn)
        seed_initial_employees(conn)
        conn.execute(
            """
            UPDATE booking_shows
            SET contracted_cachet_amount = cachet_amount
            WHERE contracted_cachet_amount = 0
              AND cachet_amount > 0
            """
        )
        conn.execute(
            """
            UPDATE booking_shows
            SET venue_collected_amount = cachet_amount
            WHERE venue_collected_amount = 0
              AND cachet_amount > 0
            """
        )
        conn.execute(
            """
            UPDATE booking_shows
            SET venue_payment_status = 'no_cobrado'
            WHERE cachet_amount = 0
              AND COALESCE(venue_payment_status, 'cobrado') = 'cobrado'
              AND status = 'no_cobrado'
            """
        )
        conn.execute(
            """
            UPDATE booking_shows
            SET venue_shortfall_policy = 'ajustar_cachet'
            WHERE venue_balance_amount > 0.01
              AND ABS(COALESCE(cachet_amount, 0) - COALESCE(venue_collected_amount, 0)) <= 0.01
              AND COALESCE(venue_shortfall_policy, 'deuda_boliche') = 'deuda_boliche'
            """
        )
        seed_booking_artist_registry(conn)


def ensure_sqlite_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


_EMPLOYEE_COMPENSATION_COLUMNS_READY = False


def ensure_employee_compensation_columns(conn: sqlite3.Connection) -> None:
    global _EMPLOYEE_COMPENSATION_COLUMNS_READY
    if is_postgres_connection(conn):
        if _EMPLOYEE_COMPENSATION_COLUMNS_READY:
            return
        conn.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS compensation_type text NOT NULL DEFAULT 'none'")
        conn.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS salary_amount numeric(18,6) NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS salary_currency text NOT NULL DEFAULT 'ARS'")
        conn.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS salary_frequency text NOT NULL DEFAULT 'monthly'")
        conn.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS salary_notes text")
        _EMPLOYEE_COMPENSATION_COLUMNS_READY = True
        return

    ensure_sqlite_column(conn, "employees", "compensation_type", "TEXT NOT NULL DEFAULT 'none'")
    ensure_sqlite_column(conn, "employees", "salary_amount", "REAL NOT NULL DEFAULT 0")
    ensure_sqlite_column(conn, "employees", "salary_currency", "TEXT NOT NULL DEFAULT 'ARS'")
    ensure_sqlite_column(conn, "employees", "salary_frequency", "TEXT NOT NULL DEFAULT 'monthly'")
    ensure_sqlite_column(conn, "employees", "salary_notes", "TEXT")


DEFAULT_WEB_PASSWORD = "Indyana2026!"


def base64url_no_padding(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def hash_web_password(password: str) -> str:
    salt = base64url_no_padding(secrets.token_bytes(16))
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=16384,
        r=8,
        p=1,
        dklen=32,
    )
    return f"scrypt${salt}${base64url_no_padding(digest)}"


def verify_web_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    parts = password_hash.split("$")
    if len(parts) != 3 or parts[0] != "scrypt":
        return False
    _scheme, salt, expected = parts
    try:
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt.encode("utf-8"),
            n=16384,
            r=8,
            p=1,
            dklen=32,
        )
        expected_bytes = base64url_decode(expected)
    except Exception:
        return False
    return hmac.compare_digest(actual, expected_bytes)


def generated_employee_username(display_name: str) -> str | None:
    cleaned = " ".join((display_name or "").strip().split())
    if not cleaned:
        return None
    parts = cleaned.split()
    if len(parts) == 1:
        base = parts[0]
    else:
        base = f"{parts[0]}{parts[-1][0]}"
    return "".join(ch for ch in base.lower() if ch.isalnum())


EMPLOYEE_FUNCTION_OPTIONS = [
    "Tour Manager",
    "Project Manager",
    "Label",
    "Digitales",
    "Administracion",
    "Presidente",
    "Vice Presidente",
    "Management",
    "Booking",
    "Otro",
]


APP_MODULES = [
    ("home", "Inicio"),
    ("statement_reports", "Reporte por statement"),
    ("royalty_reports", "Reporte de regalias"),
    ("custom_reports", "Reportes Personalizados"),
    ("participation", "Participacion en distribuidoras"),
    ("booking_agenda", "Agenda Booking"),
    ("booking", "Booking Indyana"),
    ("booking_lab", "Carga de Shows laboratorio"),
    ("booking_detail", "Detalle Booking"),
    ("booking_summary", "Resumen Booking"),
    ("booking_commissions", "Comisiones"),
    ("composite_booking", "Booking compartido"),
    ("caserio", "El Caserio"),
    ("finance_movements", "Movimientos financieros"),
    ("payroll_compensation", "Sueldos y compensaciones"),
    ("artist_finance", "Finanzas Artista"),
    ("artists", "ABM Artistas"),
    ("employees", "ABM Empleados"),
    ("catalog", "Catalogo General"),
    ("digital_income", "Ingresos Digitales"),
    ("royalties_dashboard", "Dashboard Regalias"),
    ("distributor_config", "Configuracion Distribuidoras"),
    ("source_monitor", "Control Distribuidoras"),
]


INITIAL_EMPLOYEES = [
    ("Ruben Elkowich", ["Administracion"]),
    ("Juan Manuel Fornasari", ["Presidente"]),
    ("Carolina Vanesa Alvarez", ["Vice Presidente"]),
    ("Salome Fornasari", ["Tour Manager", "Project Manager"]),
    ("Santiago Damonte", ["Tour Manager", "Project Manager"]),
    ("Santiago Mareco", ["Tour Manager", "Project Manager"]),
    ("Lautaro Alarcon", ["Tour Manager", "Project Manager"]),
    ("David Carbone", ["Tour Manager", "Project Manager"]),
    ("Walter Robales", ["Tour Manager"]),
]


def normalize_employee_function(value: str) -> str | None:
    cleaned = clean_optional_text(value)
    if not cleaned:
        return None

    lookup = {option.casefold(): option for option in EMPLOYEE_FUNCTION_OPTIONS}
    return lookup.get(cleaned.casefold(), cleaned)


def clean_employee_functions(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_employee_function(value)
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def seed_app_modules(conn: sqlite3.Connection) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    for module_key, label in APP_MODULES:
        conn.execute(
            db_sql(
                conn,
                """
            INSERT INTO app_modules (module_key, label, active, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(module_key) DO UPDATE SET
                label = excluded.label,
                active = excluded.active
            """,
            ),
            (module_key, label, db_bool(True), now),
        )


def upsert_employee_functions(conn: sqlite3.Connection, employee_id: int, functions: list[str]) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    cleaned_functions = clean_employee_functions(functions)
    conn.execute(db_sql(conn, "DELETE FROM employee_functions WHERE employee_id = ?"), (employee_id,))
    for function_code in cleaned_functions:
        if is_postgres_connection(conn):
            conn.execute(
                db_sql(
                    conn,
                    """
                INSERT INTO employee_functions (employee_id, function_code, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(employee_id, function_code) DO NOTHING
                """,
                ),
                (employee_id, function_code, now),
            )
        else:
            conn.execute(
                """
                INSERT OR IGNORE INTO employee_functions (employee_id, function_code, created_at)
                VALUES (?, ?, ?)
                """,
                (employee_id, function_code, now),
            )


def clean_username(value: str | None) -> str | None:
    cleaned = clean_optional_text(value)
    if not cleaned:
        return None
    return cleaned.strip().lower()


def upsert_employee_user(
    conn: sqlite3.Connection,
    employee_id: int,
    username: str | None,
    role: str = "viewer",
    active: bool = True,
    auth_source: str = "operational",
    password: str | None = None,
    must_change_password: bool | None = None,
) -> None:
    clean_user = clean_username(username)
    if not clean_user:
        return

    if role not in {"viewer", "editor", "admin"}:
        role = "viewer"

    now = datetime.now().isoformat(timespec="seconds")
    existing = conn.execute(
        db_sql(conn, "SELECT id, password_hash FROM app_users WHERE lower(username) = lower(?)"),
        (clean_user,),
    ).fetchone()
    password_hash = hash_web_password(password) if password else None
    if existing is None:
        conn.execute(
            db_sql(
                conn,
                """
            INSERT INTO app_users (
                employee_id, username, password_hash, must_change_password, global_role, active,
                auth_source, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ),
            (
                employee_id,
                clean_user,
                password_hash,
                db_bool(bool(must_change_password)),
                role,
                db_bool(active),
                auth_source,
                "Usuario operativo cloud/local.",
                now,
                now,
            ),
        )
    else:
        update_password_sql = ""
        params: list[object] = [
            employee_id,
            role,
            db_bool(active),
            auth_source,
        ]
        if password_hash:
            update_password_sql = """
                password_hash = ?,
                must_change_password = ?,
            """
            params.extend([password_hash, db_bool(bool(must_change_password))])
        conn.execute(
            db_sql(
                conn,
                f"""
            UPDATE app_users
            SET employee_id = ?,
                global_role = ?,
                active = ?,
                auth_source = ?,
                {update_password_sql}
                updated_at = ?
            WHERE id = ?
            """,
            ),
            (*params, now, existing["id"]),
        )


def ensure_booking_commission_rules_table(conn: sqlite3.Connection) -> None:
    if not is_postgres_connection(conn):
        raise HTTPException(
            status_code=500,
            detail="Las reglas de comisiones usan la base operacional Postgres. SQLite queda solo como historico.",
        )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS booking_commission_rules (
            id bigserial PRIMARY KEY,
            employee_id bigint NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            artist text NOT NULL,
            percentage numeric(9, 4) NOT NULL DEFAULT 0,
            calculation_base text NOT NULL DEFAULT 'commissionable',
            include_booking_fee_paid_shows boolean NOT NULL DEFAULT false,
            priority_order integer,
            active_from_month text,
            active_to_month text,
            active boolean NOT NULL DEFAULT true,
            notes text,
            created_by text,
            updated_by text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(employee_id, artist),
            CONSTRAINT booking_commission_rules_base_chk
                CHECK (calculation_base IN ('commissionable', 'total'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_booking_commission_rules_employee ON booking_commission_rules(employee_id)"
    )
    conn.execute(
        "ALTER TABLE booking_commission_rules ADD COLUMN IF NOT EXISTS include_booking_fee_paid_shows boolean NOT NULL DEFAULT false"
    )
    conn.execute(
        "ALTER TABLE booking_commission_rules ADD COLUMN IF NOT EXISTS priority_order integer"
    )
    conn.execute(
        "ALTER TABLE booking_commission_rules ALTER COLUMN priority_order DROP NOT NULL"
    )
    conn.execute(
        "ALTER TABLE booking_commission_rules ALTER COLUMN priority_order DROP DEFAULT"
    )
    conn.execute(
        "ALTER TABLE booking_commission_rules DROP CONSTRAINT IF EXISTS booking_commission_rules_priority_chk"
    )
    conn.execute(
        "ALTER TABLE booking_commission_rules ADD CONSTRAINT booking_commission_rules_priority_chk CHECK (priority_order BETWEEN 1 AND 5)"
    )


def clean_commission_rule_month(value: str | None) -> str | None:
    cleaned = clean_optional_text(value)
    if not cleaned:
        return None
    if len(cleaned) != 7 or cleaned[4] != "-":
        raise HTTPException(status_code=400, detail="Mes invalido. Usar YYYY-MM.")
    try:
        year = int(cleaned[:4])
        month = int(cleaned[5:])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Mes invalido. Usar YYYY-MM.") from exc
    if year < 2000 or month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Mes invalido. Usar YYYY-MM.")
    return cleaned


def row_to_booking_commission_rule(row) -> dict:
    return {
        "id": int(row["id"]),
        "employee_id": int(row["employee_id"]),
        "artist": row["artist"],
        "percent": float(row["percentage"] or 0),
        "base": row["calculation_base"] or "commissionable",
        "include_booking_fee_paid_shows": bool(row["include_booking_fee_paid_shows"]),
        "priority_order": int(row["priority_order"]) if row["priority_order"] is not None else None,
        "start_month": row["active_from_month"],
        "end_month": row["active_to_month"],
        "active": bool(row["active"]),
        "notes": row["notes"] or "",
        "created_by": row["created_by"],
        "updated_by": row["updated_by"],
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def upsert_employee_permissions(
    conn: sqlite3.Connection,
    employee_id: int,
    permissions: list[EmployeePermissionRequest],
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    valid_modules = {module_key for module_key, _label in APP_MODULES}
    existing_rows = conn.execute(
        db_sql(
            conn,
            """
        SELECT module_key, can_access, can_create, can_view_history,
               can_edit, can_approve, scope_json, notes
        FROM module_permissions
        WHERE employee_id = ?
        """,
        ),
        (employee_id,),
    ).fetchall()
    existing_by_module = {row["module_key"]: row for row in existing_rows}
    for permission in permissions:
        if permission.module_key not in valid_modules:
            continue
        existing = existing_by_module.get(permission.module_key)
        if existing is not None:
            existing_scope = parse_permission_scope(existing["scope_json"])
            requested_scope = parse_permission_scope(permission.scope)
            unchanged = (
                bool(existing["can_access"]) == bool(permission.can_access)
                and bool(existing["can_create"]) == bool(permission.can_create)
                and bool(existing["can_view_history"]) == bool(permission.can_view_history)
                and bool(existing["can_edit"]) == bool(permission.can_edit)
                and bool(existing["can_approve"]) == bool(permission.can_approve)
                and existing_scope == requested_scope
                and (existing["notes"] or None) == clean_optional_text(permission.notes)
            )
            if unchanged:
                continue
        if is_postgres_connection(conn):
            from psycopg.types.json import Jsonb

            scope_payload = Jsonb(permission.scope)
        else:
            scope_payload = json.dumps(permission.scope, ensure_ascii=False)
        conn.execute(
            db_sql(
                conn,
                """
            INSERT INTO module_permissions (
                employee_id, module_key, can_access, can_create, can_view_history,
                can_edit, can_approve, scope_json, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(employee_id, module_key) DO UPDATE SET
                can_access = excluded.can_access,
                can_create = excluded.can_create,
                can_view_history = excluded.can_view_history,
                can_edit = excluded.can_edit,
                can_approve = excluded.can_approve,
                scope_json = excluded.scope_json,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            ),
            (
                employee_id,
                permission.module_key,
                db_bool(permission.can_access),
                db_bool(permission.can_create),
                db_bool(permission.can_view_history),
                db_bool(permission.can_edit),
                db_bool(permission.can_approve),
                scope_payload,
                clean_optional_text(permission.notes),
                now,
                now,
            ),
        )


def parse_permission_scope(scope_json) -> list[dict[str, str]]:
    if isinstance(scope_json, list):
        raw_scope = scope_json
    elif isinstance(scope_json, dict):
        raw_scope = [scope_json]
    else:
        try:
            raw_scope = json.loads(scope_json or "[]")
        except (TypeError, json.JSONDecodeError):
            return []
    if not isinstance(raw_scope, list):
        return []
    scope: list[dict[str, str]] = []
    for item in raw_scope:
        if not isinstance(item, dict):
            continue
        scope_type = clean_optional_text(item.get("scope_type") or item.get("type"))
        scope_ref = clean_optional_text(item.get("scope_ref") or item.get("ref") or item.get("value"))
        if scope_type and scope_ref:
            scope.append({"scope_type": scope_type, "scope_ref": scope_ref})
    return scope


def user_module_permission(
    conn: sqlite3.Connection,
    username: str | None,
    module_key: str,
) -> dict:
    username = clean_username(username or "")
    if not username:
        return {
            "allowed": True,
            "is_admin": True,
            "can_access": True,
            "can_create": True,
            "can_view_history": True,
            "can_edit": True,
            "can_approve": True,
            "scope": None,
        }

    user = conn.execute(
        db_sql(
            conn,
            """
        SELECT u.*, e.id AS employee_ref
        FROM app_users u
        LEFT JOIN employees e ON e.id = u.employee_id
        WHERE lower(u.username) = lower(?)
          AND u.active = ?
        """,
        ),
        (username, db_bool(True)),
    ).fetchone()
    if user is None:
        return {"allowed": False, "is_admin": False, "scope": set()}

    if str(user["global_role"] or "").lower() == "admin":
        return {
            "allowed": True,
            "is_admin": True,
            "can_access": True,
            "can_create": True,
            "can_view_history": True,
            "can_edit": True,
            "can_approve": True,
            "scope": None,
        }

    employee_id = user["employee_ref"]
    if employee_id is None:
        return {"allowed": False, "is_admin": False, "scope": set()}

    permission = conn.execute(
        db_sql(
            conn,
            """
        SELECT can_access, can_create, can_view_history, can_edit, can_approve, scope_json
        FROM module_permissions
        WHERE employee_id = ?
          AND module_key = ?
        """,
        ),
        (employee_id, module_key),
    ).fetchone()
    if permission is None or not bool(permission["can_access"]):
        return {"allowed": False, "is_admin": False, "scope": set()}

    scope_items = parse_permission_scope(permission["scope_json"])
    scoped_artists: set[str] | None
    if not scope_items or any(item["scope_type"] == "all" and item["scope_ref"] == "*" for item in scope_items):
        scoped_artists = None
    else:
        scoped_artists = {
            cleaned.casefold()
            for item in scope_items
            if item["scope_type"] == "artist"
            for cleaned in [clean_booking_artist(item["scope_ref"])]
            if cleaned
        }
        if not scoped_artists:
            return {"allowed": False, "is_admin": False, "scope": set()}

    return {
        "allowed": True,
        "is_admin": False,
        "can_access": bool(permission["can_access"]),
        "can_create": bool(permission["can_create"]),
        "can_view_history": bool(permission["can_view_history"]),
        "can_edit": bool(permission["can_edit"]),
        "can_approve": bool(permission["can_approve"]),
        "scope": scoped_artists,
    }


def require_module_permission(
    conn: sqlite3.Connection,
    username: str | None,
    module_key: str,
    action: Literal["access", "create", "view_history", "edit", "approve"],
    *,
    artist: str | None = None,
    existing_artist: str | None = None,
) -> dict:
    permission = user_module_permission(conn, username, module_key)
    action_key = {
        "access": "can_access",
        "create": "can_create",
        "view_history": "can_view_history",
        "edit": "can_edit",
        "approve": "can_approve",
    }[action]
    if not permission.get("allowed") or not permission.get(action_key):
        raise HTTPException(status_code=403, detail="No tenes permiso para esta accion.")

    scoped_artists = permission.get("scope")
    if scoped_artists is not None:
        for value in (artist, existing_artist):
            cleaned = clean_booking_artist(value or "")
            if cleaned and cleaned.casefold() not in scoped_artists:
                raise HTTPException(status_code=403, detail="No tenes permiso para operar este artista.")
    return permission


def is_payroll_compensation_movement(
    business_area: str | None,
    category: str | None,
    movement_type: str | None = None,
) -> bool:
    normalized_area = (business_area or "").strip().lower()
    normalized_category = (category or "").strip().lower()
    normalized_type = (movement_type or "").strip().lower()
    return (
        normalized_area == "estructura"
        and (
            normalized_type == "salario"
            or normalized_category in {"salario", "comision_interna"}
        )
    )


def user_artist_scope_for_module(
    conn: sqlite3.Connection,
    username: str | None,
    module_key: str,
) -> tuple[bool, set[str] | None]:
    """Return (allowed, artist_set). artist_set None means all artists.

    Missing username means an internal/API-key maintenance call, so it keeps the
    previous unrestricted behavior. Empty scope also means all artists for
    backward compatibility with permissions created before artist scopes.
    """
    permission = user_module_permission(conn, username, module_key)
    return bool(permission.get("allowed")), permission.get("scope")


def apply_artist_scope_sql(
    conn: sqlite3.Connection,
    username: str | None,
    module_key: str,
    params: list,
    *,
    column: str = "artist",
) -> str:
    allowed, scoped_artists = user_artist_scope_for_module(conn, username, module_key)
    if not allowed:
        return " AND 1 = 0"
    if scoped_artists is None:
        return ""
    placeholders = ", ".join("?" for _ in scoped_artists)
    params.extend(sorted(scoped_artists))
    return f" AND lower({column}) IN ({placeholders})"


def filter_artists_by_scope(
    artists: list[str],
    conn: sqlite3.Connection,
    username: str | None,
    module_key: str,
) -> list[str]:
    allowed, scoped_artists = user_artist_scope_for_module(conn, username, module_key)
    if not allowed:
        return []
    if scoped_artists is None:
        return artists
    return [artist for artist in artists if artist.casefold() in scoped_artists]


def grant_employee_all_permissions(conn: sqlite3.Connection, employee_id: int) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    for module_key, _label in APP_MODULES:
        conn.execute(
            """
            INSERT INTO module_permissions (
                employee_id, module_key, can_access, can_create, can_view_history,
                can_edit, can_approve, scope_json, notes, created_at, updated_at
            )
            VALUES (?, ?, 1, 1, 1, 1, 1, ?, ?, ?, ?)
            ON CONFLICT(employee_id, module_key) DO UPDATE SET
                can_access = 1,
                can_create = 1,
                can_view_history = 1,
                can_edit = 1,
                can_approve = 1,
                scope_json = excluded.scope_json,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (
                employee_id,
                module_key,
                json.dumps([{"scope_type": "all", "scope_ref": "*"}], ensure_ascii=False),
                "Super-admin inicial. No bloquear a Ruben.",
                now,
                now,
            ),
        )


def grant_employee_view_permissions_if_empty(
    conn: sqlite3.Connection,
    employee_id: int,
    module_keys: list[str],
    notes: str,
) -> None:
    existing = conn.execute(
        "SELECT COUNT(*) AS count FROM module_permissions WHERE employee_id = ?",
        (employee_id,),
    ).fetchone()
    if existing and int(existing["count"] or 0) > 0:
        return

    now = datetime.now().isoformat(timespec="seconds")
    valid_modules = {module_key for module_key, _label in APP_MODULES}
    for module_key in module_keys:
        if module_key not in valid_modules:
            continue
        conn.execute(
            """
            INSERT INTO module_permissions (
                employee_id, module_key, can_access, can_create, can_view_history,
                can_edit, can_approve, scope_json, notes, created_at, updated_at
            )
            VALUES (?, ?, 1, 0, 1, 0, 0, ?, ?, ?, ?)
            ON CONFLICT(employee_id, module_key) DO NOTHING
            """,
            (
                employee_id,
                module_key,
                json.dumps([{"scope_type": "all", "scope_ref": "*"}], ensure_ascii=False),
                notes,
                now,
                now,
            ),
        )


def ensure_user_default_password(conn: sqlite3.Connection, username: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        db_sql(
            conn,
            """
        UPDATE app_users
        SET password_hash = ?,
            must_change_password = ?,
            updated_at = ?
        WHERE lower(username) = lower(?)
          AND (password_hash IS NULL OR password_hash = '')
        """,
        ),
        (hash_web_password(DEFAULT_WEB_PASSWORD), db_bool(True), now, username),
    )


def seed_initial_employees(conn: sqlite3.Connection) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    for display_name, functions in INITIAL_EMPLOYEES:
        existing = conn.execute(
            "SELECT id FROM employees WHERE lower(display_name) = lower(?)",
            (display_name,),
        ).fetchone()
        if existing is None:
            cursor = conn.execute(
                """
                INSERT INTO employees (
                    display_name, legal_name, active, notes, created_at, updated_at
                )
                VALUES (?, ?, 1, ?, ?, ?)
                """,
                (display_name, display_name, "Seed inicial de empleados VPO.", now, now),
            )
            employee_id = int(cursor.lastrowid)
        else:
            employee_id = int(existing["id"])

        existing_functions = conn.execute(
            "SELECT COUNT(*) AS count FROM employee_functions WHERE employee_id = ?",
            (employee_id,),
        ).fetchone()
        if not existing_functions or int(existing_functions["count"] or 0) == 0:
            upsert_employee_functions(conn, employee_id, functions)

        if display_name.casefold() == "ruben elkowich":
            grant_employee_all_permissions(conn, employee_id)
            upsert_employee_user(conn, employee_id, "rubene", "admin", True, "operational")
            conn.execute(
                """
                DELETE FROM app_users
                WHERE lower(username) IN ('ruben', 'admin')
                """,
            )
        elif display_name.casefold() == "juan manuel fornasari":
            upsert_employee_user(conn, employee_id, "juanf", "viewer", True, "operational")
            conn.execute(
                """
                DELETE FROM app_users
                WHERE lower(username) = lower('jfornasari')
                """,
            )
            grant_employee_view_permissions_if_empty(
                conn,
                employee_id,
                ["booking_detail", "catalog"],
                "Permisos operativos iniciales. Ajustar desde ABM empleados.",
            )
        else:
            generated_username = generated_employee_username(display_name)
            if generated_username:
                upsert_employee_user(conn, employee_id, generated_username, "viewer", True, "operational")

        for user_row in conn.execute(
            "SELECT username FROM app_users WHERE employee_id = ?",
            (employee_id,),
        ).fetchall():
            ensure_user_default_password(conn, user_row["username"])


def seed_booking_artist_registry(conn: sqlite3.Connection) -> None:
    if not BOOKING_ARTIST_REGISTRY_PATH.exists():
        return

    try:
        registry = json.loads(BOOKING_ARTIST_REGISTRY_PATH.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return

    if not isinstance(registry, list):
        return

    now = datetime.now().isoformat(timespec="seconds")
    for value in registry:
        cleaned = clean_booking_artist(value)
        if not cleaned:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO booking_artists (
                stage_name, active, created_at, updated_at
            )
            VALUES (?, 1, ?, ?)
            """,
            (cleaned, now, now),
        )


def validate_iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="show_date must be YYYY-MM-DD.") from exc


def clean_receipt_refs(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value and value.strip()]


def row_to_booking_show(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["receipt_refs"] = json.loads(data.pop("receipt_refs_json") or "[]")
    data["show_expenses"] = []
    data["cash_movements"] = []
    data["pre_split_adjustments"] = []
    data["direct_commissions"] = []
    data["external_shares"] = []
    data["artist_adjustments"] = []
    data["account_applications"] = []
    data["open_balance_artist_amount"] = float(data.get("balance_artist_amount") or 0)
    data["open_balance_producer_amount"] = float(data.get("balance_producer_amount") or 0)
    data["open_venue_balance_amount"] = float(data.get("venue_balance_amount") or 0)
    data["account_open_balance_amount"] = abs(
        booking_current_account_net(
            data["open_balance_producer_amount"],
            data["open_balance_artist_amount"],
        )
    ) + max(0.0, data["open_venue_balance_amount"])
    data["account_status"] = "settled" if data["account_open_balance_amount"] <= 0.01 else "open"
    return data


def row_to_booking_artist(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["active"] = bool(data.get("active", 1))
    return data


def parse_scope_payload(value) -> list[dict[str, str]]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    try:
        raw = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return raw if isinstance(raw, list) else []


def row_to_employee(conn, row) -> dict:
    data = dict(row)
    data["active"] = bool(data.get("active", 1))
    function_rows = conn.execute(
        db_sql(
            conn,
            """
        SELECT function_code
        FROM employee_functions
        WHERE employee_id = ?
        ORDER BY function_code
        """,
        ),
        (data["id"],),
    ).fetchall()
    data["functions"] = [item["function_code"] for item in function_rows]
    user_rows = conn.execute(
        db_sql(
            conn,
            """
        SELECT id, username, global_role, active, auth_source, notes, created_at, updated_at,
               password_hash, must_change_password, last_login_at
        FROM app_users
        WHERE employee_id = ?
        ORDER BY active DESC, username
        """,
        ),
        (data["id"],),
    ).fetchall()
    data["users"] = [
        {
            **{key: value for key, value in dict(item).items() if key != "password_hash"},
            "active": bool(item["active"]),
            "has_password": bool(item["password_hash"]),
            "must_change_password": bool(item["must_change_password"]),
        }
        for item in user_rows
    ]
    permission_rows = conn.execute(
        db_sql(
            conn,
            """
        SELECT module_key, can_access, can_create, can_view_history, can_edit, can_approve, scope_json, notes
        FROM module_permissions
        WHERE employee_id = ?
        ORDER BY module_key
        """,
        ),
        (data["id"],),
    ).fetchall()
    data["permissions"] = [
        {
            **dict(item),
            "can_access": bool(item["can_access"]),
            "can_create": bool(item["can_create"]),
            "can_view_history": bool(item["can_view_history"]),
            "can_edit": bool(item["can_edit"]),
            "can_approve": bool(item["can_approve"]),
            "scope": parse_scope_payload(item["scope_json"]),
        }
        for item in permission_rows
    ]
    return data


def row_to_session_user(row: sqlite3.Row) -> dict:
    role = row["global_role"] if row["global_role"] in {"viewer", "editor", "admin"} else "viewer"
    return {
        "username": row["username"],
        "role": role,
        "canEdit": role in {"editor", "admin"},
        "mustChangePassword": bool(row["must_change_password"]),
    }


def row_to_caserio_event(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["receipt_refs"] = json.loads(data.pop("receipt_refs_json") or "[]")
    data["lines"] = []
    return data


def row_to_booking_expense(row: sqlite3.Row) -> dict:
    return dict(row)


def row_to_booking_pre_split_adjustment(row: sqlite3.Row) -> dict:
    return dict(row)


def row_to_booking_direct_commission(row: sqlite3.Row) -> dict:
    return dict(row)


def row_to_booking_external_share(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["cash_handled_by_vpo"] = bool(data["cash_handled_by_vpo"])
    return data


def row_to_booking_adjustment(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["recoverable"] = bool(data["recoverable"])
    return data


def row_to_booking_cash_movement(row: sqlite3.Row) -> dict:
    data = dict(row)
    category = str(data.get("category") or "")
    parts = category.split(":", 2)
    if len(parts) == 3 and parts[0] == "cash_received":
        data["recipient"] = parts[1]
        data["payment_method"] = parts[2]
    else:
        data["recipient"] = "producer"
        data["payment_method"] = "otro"

    raw_notes = data.get("notes")
    metadata = {}
    if raw_notes:
        try:
            metadata = json.loads(raw_notes)
        except json.JSONDecodeError:
            metadata = {"notes": raw_notes}

    data["concept"] = metadata.get("concept") or "Movimiento de caja"
    data["paid_by"] = metadata.get("paid_by")
    data["notes"] = metadata.get("notes")
    return data


def parse_json_list(value) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def row_to_booking_account_application(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["proof_refs"] = parse_json_list(data.pop("proof_refs_json", "[]"))
    data["amount"] = float(data.get("amount") or 0)
    data["effect_amount"] = float(data.get("effect_amount") or 0)
    return data


def row_to_booking_account_movement(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["proof_refs"] = parse_json_list(data.pop("proof_refs_json", "[]"))
    data["amount"] = float(data.get("amount") or 0)
    data["applied_amount"] = float(data.get("applied_amount") or 0)
    data["unapplied_amount"] = float(data.get("unapplied_amount") or 0)
    return data


def ensure_booking_account_movements_table(conn: sqlite3.Connection) -> None:
    if is_postgres_connection(conn):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_account_movements (
                id bigserial PRIMARY KEY,
                movement_date date NOT NULL,
                artist text NOT NULL,
                movement_type text NOT NULL,
                amount numeric(18, 6) NOT NULL DEFAULT 0,
                applied_amount numeric(18, 6) NOT NULL DEFAULT 0,
                unapplied_amount numeric(18, 6) NOT NULL DEFAULT 0,
                payment_method text NOT NULL DEFAULT 'transferencia',
                counterparty text,
                proof_refs_json jsonb NOT NULL DEFAULT '[]'::jsonb,
                notes text,
                created_by text,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT booking_account_mov_type_chk CHECK (movement_type IN ('cobro_deuda_booking', 'pago_saldo_artista', 'compensacion_booking', 'pago_deuda_boliche', 'ajuste_booking')),
                CONSTRAINT booking_account_mov_method_chk CHECK (payment_method IN ('transferencia', 'efectivo', 'compensacion', 'ajuste', 'otro'))
            )
            """
        )
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_account_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                movement_date TEXT NOT NULL,
                artist TEXT NOT NULL,
                movement_type TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                applied_amount REAL NOT NULL DEFAULT 0,
                unapplied_amount REAL NOT NULL DEFAULT 0,
                payment_method TEXT NOT NULL DEFAULT 'transferencia',
                counterparty TEXT,
                proof_refs_json TEXT NOT NULL DEFAULT '[]',
                notes TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_booking_account_mov_artist ON booking_account_movements(artist, movement_date)"
    )


def ensure_booking_account_applications_table(conn: sqlite3.Connection) -> None:
    if is_postgres_connection(conn):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_account_applications (
                id bigserial PRIMARY KEY,
                show_id bigint NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
                application_date date NOT NULL,
                target_balance text NOT NULL,
                application_type text NOT NULL,
                amount numeric(18, 6) NOT NULL DEFAULT 0,
                effect_amount numeric(18, 6) NOT NULL DEFAULT 0,
                payment_method text NOT NULL DEFAULT 'transferencia',
                counterparty text,
                linked_show_id bigint REFERENCES booking_shows(id) ON DELETE SET NULL,
                movement_id bigint,
                proof_refs_json jsonb NOT NULL DEFAULT '[]'::jsonb,
                notes text,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT booking_account_app_target_chk CHECK (target_balance IN ('artist', 'producer', 'venue')),
                CONSTRAINT booking_account_app_type_chk CHECK (application_type IN ('artist_payment', 'artist_reimbursement', 'producer_reimbursement', 'venue_payment', 'compensation', 'adjustment')),
                CONSTRAINT booking_account_app_method_chk CHECK (payment_method IN ('transferencia', 'efectivo', 'compensacion', 'ajuste', 'otro'))
            )
            """
        )
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_account_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                show_id INTEGER NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
                application_date TEXT NOT NULL,
                target_balance TEXT NOT NULL,
                application_type TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                effect_amount REAL NOT NULL DEFAULT 0,
                payment_method TEXT NOT NULL DEFAULT 'transferencia',
                counterparty TEXT,
                linked_show_id INTEGER REFERENCES booking_shows(id) ON DELETE SET NULL,
                movement_id INTEGER,
                proof_refs_json TEXT NOT NULL DEFAULT '[]',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_booking_account_app_show ON booking_account_applications(show_id, application_date)"
    )
    ensure_booking_account_movements_table(conn)
    if is_postgres_connection(conn):
        conn.execute(
            """
            ALTER TABLE booking_account_applications
            ADD COLUMN IF NOT EXISTS movement_id bigint REFERENCES booking_account_movements(id) ON DELETE SET NULL
            """
        )
    else:
        ensure_sqlite_column(conn, "booking_account_applications", "movement_id", "INTEGER")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_booking_account_app_movement ON booking_account_applications(movement_id)"
    )


def booking_application_json_value(conn: sqlite3.Connection, values: list[str]):
    cleaned = clean_receipt_refs(values)
    if is_postgres_connection(conn):
        from psycopg.types.json import Jsonb

        return Jsonb(cleaned)
    return json.dumps(cleaned, ensure_ascii=False)


def booking_target_original_balance(show: dict, target_balance: str) -> float:
    if target_balance == "artist":
        return float(show.get("balance_artist_amount") or 0)
    if target_balance == "producer":
        return float(show.get("balance_producer_amount") or 0)
    if target_balance == "venue":
        return float(show.get("venue_balance_amount") or 0)
    raise HTTPException(status_code=400, detail="Saldo destino invalido.")


def booking_open_balance_for_target(show: dict, applications: list[dict], target_balance: str) -> float:
    value = booking_target_original_balance(show, target_balance)
    value += sum(
        float(application.get("effect_amount") or 0)
        for application in applications
        if application.get("target_balance") == target_balance
    )
    return 0.0 if abs(value) <= 0.01 else value


def apply_booking_account_fields(show: dict, applications: list[dict]) -> dict:
    show["account_applications"] = applications
    show["open_balance_artist_amount"] = booking_open_balance_for_target(show, applications, "artist")
    show["open_balance_producer_amount"] = booking_open_balance_for_target(show, applications, "producer")
    show["open_venue_balance_amount"] = booking_open_balance_for_target(show, applications, "venue")
    show["account_open_balance_amount"] = abs(
        booking_current_account_net(
            show["open_balance_producer_amount"],
            show["open_balance_artist_amount"],
        )
    ) + max(0.0, show["open_venue_balance_amount"])
    show["account_status"] = "settled" if show["account_open_balance_amount"] <= 0.01 else "open"
    return show


def attach_booking_account_applications(conn: sqlite3.Connection, shows: list[dict]) -> list[dict]:
    if not shows:
        return shows

    ensure_booking_account_applications_table(conn)
    show_ids = [show["id"] for show in shows]
    placeholders = ",".join("?" for _ in show_ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM booking_account_applications
        WHERE show_id IN ({placeholders})
        ORDER BY application_date, id
        """,
        show_ids,
    ).fetchall()

    by_show: dict[int, list[dict]] = {show_id: [] for show_id in show_ids}
    for row in rows:
        application = row_to_booking_account_application(row)
        by_show.setdefault(application["show_id"], []).append(application)

    for show in shows:
        apply_booking_account_fields(show, by_show.get(show["id"], []))
    return shows


def booking_application_effect(current_balance: float, amount: float, target_balance: str) -> float:
    if abs(current_balance) <= 0.01:
        raise HTTPException(status_code=400, detail="Ese saldo ya esta saldado.")
    if target_balance == "venue" and current_balance < -0.01:
        raise HTTPException(status_code=400, detail="La deuda de boliche no puede aplicarse con saldo negativo.")
    if amount > abs(current_balance) + 0.01:
        raise HTTPException(status_code=400, detail="El importe supera el saldo abierto del show.")
    if abs(abs(current_balance) - amount) <= 0.01:
        return -current_balance
    return -amount if current_balance > 0 else amount


def booking_same_show_counterpart_effect(
    show: dict,
    applications: list[dict],
    target_balance: str,
    effect_amount: float,
) -> tuple[str | None, float | None]:
    if target_balance not in {"artist", "producer"}:
        return None, None
    counterpart_target = "producer" if target_balance == "artist" else "artist"
    current_balance = booking_open_balance_for_target(show, applications, target_balance)
    counterpart_balance = booking_open_balance_for_target(show, applications, counterpart_target)
    if abs(counterpart_balance) <= 0.01 or current_balance * counterpart_balance >= 0:
        return None, None
    counterpart_effect = -effect_amount
    if abs(counterpart_effect) > abs(counterpart_balance) + 0.01:
        return None, None
    if abs(abs(counterpart_balance) - abs(counterpart_effect)) <= 0.01:
        counterpart_effect = -counterpart_balance
    return counterpart_target, counterpart_effect


def booking_parent_application_type(
    movement_type: str,
    target_balance: str,
    current_balance: float,
) -> str:
    if movement_type == "pago_deuda_boliche":
        if target_balance != "venue":
            raise HTTPException(status_code=400, detail="El pago de boliche solo puede aplicarse a deuda de boliche.")
        return "venue_payment"
    if movement_type == "pago_saldo_artista":
        return "artist_payment" if target_balance == "artist" else "adjustment"
    if movement_type == "cobro_deuda_booking":
        if target_balance == "artist":
            return "artist_reimbursement" if current_balance < -0.01 else "artist_payment"
        if target_balance == "producer":
            return "producer_reimbursement"
    if movement_type == "compensacion_booking":
        if target_balance == "venue":
            raise HTTPException(status_code=400, detail="La deuda de boliche se salda como pago, no como compensacion.")
        return "compensation"
    return "adjustment"


def booking_block_application_type(target_balance: str, current_balance: float, aggregate_net: float) -> str:
    if target_balance == "venue":
        return "venue_payment"
    if target_balance == "artist":
        if current_balance > 0.01:
            return "artist_payment" if aggregate_net < -0.01 else "compensation"
        return "artist_reimbursement" if aggregate_net > 0.01 else "compensation"
    if target_balance == "producer":
        if current_balance < -0.01:
            return "producer_reimbursement" if aggregate_net > 0.01 else "compensation"
        return "compensation"
    return "adjustment"


def sync_booking_event_from_show(conn: Any, show_id: int, item: dict, now: str) -> None:
    link = conn.execute(
        "SELECT booking_event_id FROM booking_shows WHERE id = ?",
        (show_id,),
    ).fetchone()
    if link is None or link["booking_event_id"] is None:
        return

    show_status = str(item.get("status") or "")
    settlement_status = str(item.get("settlement_status") or "")
    event_settlement_status = (
        "cerrada"
        if settlement_status in {"cerrado", "cerrado_compensado", "cerrado_con_pago_posterior"}
        else "pendiente"
    )
    event_operational_status = (
        "realizado"
        if show_status in {"realizado", "rendido", "aprobado", "no_cobrado"}
        else "programado"
    )
    event_commercial_status = "cancelado" if show_status == "cancelado" else "confirmado"
    event_id = int(link["booking_event_id"])
    conn.execute(
        """
        UPDATE booking_events
        SET event_date = ?,
            venue = ?,
            city = ?,
            commercial_status = ?,
            operational_status = ?,
            settlement_status = ?,
            contracted_cachet_amount = ?,
            currency = ?,
            fx_rate = ?,
            tour_manager = ?,
            seller = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            item.get("show_date"),
            item.get("venue"),
            item.get("city"),
            event_commercial_status,
            event_operational_status,
            event_settlement_status,
            item.get("contracted_cachet_amount") or 0,
            item.get("currency") or "ARS",
            item.get("fx_rate"),
            item.get("tour_manager"),
            item.get("seller"),
            now,
            event_id,
        ),
    )

    artist_name = clean_booking_artist(item.get("artist"))
    if not artist_name:
        return
    artist_row = conn.execute(
        "SELECT id, stage_name FROM artists WHERE active = TRUE AND lower(stage_name) = lower(?)",
        (artist_name,),
    ).fetchone()
    if artist_row is None:
        return
    current_artists = conn.execute(
        "SELECT artist_id, artist_name FROM booking_event_artists WHERE event_id = ? ORDER BY position",
        (event_id,),
    ).fetchall()
    if (
        len(current_artists) == 1
        and int(current_artists[0]["artist_id"]) == int(artist_row["id"])
        and str(current_artists[0]["artist_name"]) == str(artist_row["stage_name"])
    ):
        return
    conn.execute("DELETE FROM booking_event_artists WHERE event_id = ?", (event_id,))
    conn.execute(
        """
        INSERT INTO booking_event_artists (event_id, artist_id, artist_name, position)
        VALUES (?, ?, ?, 1)
        """,
        (event_id, artist_row["id"], artist_row["stage_name"]),
    )


def sync_booking_event_from_composite(conn: Any, composite_event_id: int, item: dict, now: str) -> None:
    link = conn.execute(
        "SELECT booking_event_id FROM booking_composite_events WHERE id = ?",
        (composite_event_id,),
    ).fetchone()
    if link is None or link["booking_event_id"] is None:
        return

    composite_status = str(item.get("status") or "")
    conn.execute(
        """
        UPDATE booking_events
        SET operational_status = ?,
            settlement_status = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            "realizado" if composite_status in {"rendido", "observado", "cerrado"} else "programado",
            "cerrada" if composite_status == "cerrado" else "pendiente",
            now,
            link["booking_event_id"],
        ),
    )


def update_booking_settlement_from_account(
    conn: sqlite3.Connection,
    show_id: int,
    item: dict,
    application_type: str,
    now: str,
) -> dict:
    if item.get("account_open_balance_amount", 0) > 0.01 or (item.get("settlement_status") or "") == "historico":
        sync_booking_event_from_show(conn, show_id, item, now)
        return item
    settled_status = "cerrado_compensado" if application_type == "compensation" else "cerrado_con_pago_posterior"
    conn.execute(
        """
        UPDATE booking_shows
        SET settlement_status = ?,
            settlement_closed_at = COALESCE(settlement_closed_at, ?),
            updated_at = ?
        WHERE id = ?
        """,
        (settled_status, now, now, show_id),
    )
    updated_item = fetch_booking_show_item(conn, show_id)
    sync_booking_event_from_show(conn, show_id, updated_item, now)
    return updated_item


def attach_booking_expenses(conn: sqlite3.Connection, shows: list[dict]) -> list[dict]:
    if not shows:
        return shows

    show_ids = [show["id"] for show in shows]
    placeholders = ",".join("?" for _ in show_ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM booking_show_expenses
        WHERE show_id IN ({placeholders})
        ORDER BY id
        """,
        show_ids,
    ).fetchall()

    by_show: dict[int, list[dict]] = {show_id: [] for show_id in show_ids}
    for row in rows:
        expense = row_to_booking_expense(row)
        by_show.setdefault(expense["show_id"], []).append(expense)

    for show in shows:
        show["show_expenses"] = by_show.get(show["id"], [])
    return shows


def attach_booking_pre_split_adjustments(conn: sqlite3.Connection, shows: list[dict]) -> list[dict]:
    if not shows:
        return shows

    show_ids = [show["id"] for show in shows]
    placeholders = ",".join("?" for _ in show_ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM booking_pre_split_adjustments
        WHERE show_id IN ({placeholders})
        ORDER BY id
        """,
        show_ids,
    ).fetchall()

    by_show: dict[int, list[dict]] = {show_id: [] for show_id in show_ids}
    for row in rows:
        adjustment = row_to_booking_pre_split_adjustment(row)
        by_show.setdefault(adjustment["show_id"], []).append(adjustment)

    for show in shows:
        show["pre_split_adjustments"] = by_show.get(show["id"], [])
    return shows


def attach_booking_direct_commissions(conn: sqlite3.Connection, shows: list[dict]) -> list[dict]:
    if not shows:
        return shows

    show_ids = [show["id"] for show in shows]
    placeholders = ",".join("?" for _ in show_ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM booking_direct_commissions
        WHERE show_id IN ({placeholders})
        ORDER BY id
        """,
        show_ids,
    ).fetchall()

    by_show: dict[int, list[dict]] = {show_id: [] for show_id in show_ids}
    for row in rows:
        commission = row_to_booking_direct_commission(row)
        by_show.setdefault(commission["show_id"], []).append(commission)

    for show in shows:
        show["direct_commissions"] = by_show.get(show["id"], [])
    return shows


def attach_booking_external_shares(conn: sqlite3.Connection, shows: list[dict]) -> list[dict]:
    if not shows:
        return shows

    show_ids = [show["id"] for show in shows]
    placeholders = ",".join("?" for _ in show_ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM booking_external_shares
        WHERE show_id IN ({placeholders})
        ORDER BY id
        """,
        show_ids,
    ).fetchall()

    by_show: dict[int, list[dict]] = {show_id: [] for show_id in show_ids}
    for row in rows:
        share = row_to_booking_external_share(row)
        by_show.setdefault(share["show_id"], []).append(share)

    for show in shows:
        show["external_shares"] = by_show.get(show["id"], [])
    return shows


def attach_booking_cash_movements(conn: sqlite3.Connection, shows: list[dict]) -> list[dict]:
    if not shows:
        return shows

    show_ids = [show["id"] for show in shows]
    placeholders = ",".join("?" for _ in show_ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM booking_movements
        WHERE show_id IN ({placeholders})
          AND category LIKE 'cash_received:%'
        ORDER BY id
        """,
        show_ids,
    ).fetchall()

    by_show: dict[int, list[dict]] = {show_id: [] for show_id in show_ids}
    for row in rows:
        movement = row_to_booking_cash_movement(row)
        by_show.setdefault(movement["show_id"], []).append(movement)

    for show in shows:
        show["cash_movements"] = by_show.get(show["id"], [])
    return shows


def attach_booking_adjustments(conn: sqlite3.Connection, shows: list[dict]) -> list[dict]:
    if not shows:
        return shows

    show_ids = [show["id"] for show in shows]
    placeholders = ",".join("?" for _ in show_ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM booking_artist_adjustments
        WHERE show_id IN ({placeholders})
        ORDER BY id
        """,
        show_ids,
    ).fetchall()

    by_show: dict[int, list[dict]] = {show_id: [] for show_id in show_ids}
    for row in rows:
        adjustment = row_to_booking_adjustment(row)
        by_show.setdefault(adjustment["show_id"], []).append(adjustment)

    for show in shows:
        show["artist_adjustments"] = by_show.get(show["id"], [])
    return shows


def prepare_booking_show_payload(request: BookingQuickShowRequest, *, validate_artist: bool = True) -> dict:
    show_date = validate_iso_date(request.show_date)
    artist = require_known_booking_artist(request.artist) if validate_artist else clean_booking_artist(request.artist)
    if not artist:
        raise HTTPException(status_code=400, detail="artist is required.")
    venue = request.venue.strip()
    city = (request.city or "").strip() or None
    tour_manager = (request.tour_manager or "").strip() or None
    seller = (request.seller or "").strip() or None
    notes = (request.notes or "").strip() or None
    venue_payment_notes = (request.venue_payment_notes or "").strip() or None
    booking_commission_notes = (request.booking_commission_notes or "").strip() or None
    receipt_refs = clean_receipt_refs(request.receipt_refs)
    contracted_cachet = request.contracted_cachet_amount
    if contracted_cachet is None:
        contracted_cachet = request.cachet_amount

    venue_collected = request.venue_collected_amount
    if venue_collected is None:
        venue_collected = request.cachet_amount

    if venue_collected > contracted_cachet + 0.01:
        raise HTTPException(status_code=400, detail="venue_collected_amount cannot exceed contracted_cachet_amount.")

    shortfall_policy = request.venue_shortfall_policy
    raw_venue_shortfall = max(0.0, contracted_cachet - venue_collected)
    venue_balance = raw_venue_shortfall if shortfall_policy == "deuda_boliche" else 0.0
    venue_payment_status = request.venue_payment_status
    if raw_venue_shortfall > 0.01 and venue_payment_status == "cobrado":
        venue_payment_status = "parcial"
    if venue_payment_status == "no_cobrado" and venue_collected > 0.01:
        venue_payment_status = "parcial"

    prepared_expenses = []
    for expense in request.show_expenses:
        category = expense.category.strip() or "general"
        concept = (expense.concept or "").strip() or category
        if expense.amount <= 0:
            continue

        prepared_expenses.append({
            "concept": concept,
            "category": category,
            "amount": expense.amount,
            "notes": (expense.notes or "").strip() or None,
        })

    expenses_amount = sum(expense["amount"] for expense in prepared_expenses)
    if not prepared_expenses:
        expenses_amount = request.expenses_amount

    prepared_direct_commissions = []
    for commission in request.direct_commissions:
        concept = commission.concept.strip()
        if not concept or commission.amount <= 0:
            continue

        prepared_direct_commissions.append({
            "concept": concept,
            "recipient": (commission.recipient or "").strip() or None,
            "destination": commission.destination,
            "amount": commission.amount,
            "notes": (commission.notes or "").strip() or None,
        })

    prepared_pre_split_adjustments = []
    for adjustment in request.pre_split_adjustments:
        concept = adjustment.concept.strip()
        if not concept or adjustment.amount <= 0:
            continue

        prepared_pre_split_adjustments.append({
            "concept": concept,
            "destination": adjustment.destination,
            "amount": adjustment.amount,
            "recovery_auto_apply": bool(adjustment.recovery_auto_apply),
            "notes": (adjustment.notes or "").strip() or None,
        })

    producer_percent = request.producer_percent
    if producer_percent is None:
        producer_percent = max(0.0, 100.0 - request.artist_percent)

    if round(request.artist_percent + producer_percent, 4) > 100.0:
        raise HTTPException(status_code=400, detail="artist_percent + producer_percent cannot exceed 100.")

    prepared_adjustments = []
    for adjustment in request.artist_adjustments:
        concept = adjustment.concept.strip()
        if not concept or adjustment.amount <= 0:
            continue

        adjustment_producer_percent = adjustment.producer_percent
        if adjustment_producer_percent is None:
            adjustment_producer_percent = max(0.0, 100.0 - adjustment.artist_percent)

        if round(adjustment.artist_percent + adjustment_producer_percent, 4) > 100.0:
            raise HTTPException(status_code=400, detail="Adjustment artist_percent + producer_percent cannot exceed 100.")

        artist_amount = adjustment.amount * adjustment.artist_percent / 100
        producer_amount = adjustment.amount * adjustment_producer_percent / 100
        if adjustment.applied_amount > artist_amount:
            raise HTTPException(status_code=400, detail="Adjustment applied_amount cannot exceed artist recoverable amount.")

        prepared_adjustments.append({
            "concept": concept,
            "adjustment_type": adjustment.adjustment_type,
            "area": adjustment.area,
            "impact": adjustment.impact,
            "recoverable": adjustment.recoverable,
            "amount": adjustment.amount,
            "applied_amount": adjustment.applied_amount,
            "artist_percent": adjustment.artist_percent,
            "producer_percent": adjustment_producer_percent,
            "artist_amount": artist_amount,
            "producer_amount": producer_amount,
            "notes": (adjustment.notes or "").strip() or None,
        })

    prepared_cash_movements = []
    for movement in request.cash_movements:
        concept = movement.concept.strip()
        if not concept or movement.amount <= 0:
            continue

        prepared_cash_movements.append({
            "recipient": movement.recipient,
            "concept": concept,
            "amount": movement.amount,
            "payment_method": normalize_booking_cash_method(movement.payment_method),
            "paid_by": (movement.paid_by or "").strip() or None,
            "notes": (movement.notes or "").strip() or None,
        })

    effective_cachet_amount = venue_collected if shortfall_policy == "ajustar_cachet" else contracted_cachet
    direct_commissions_amount = sum(commission["amount"] for commission in prepared_direct_commissions)
    direct_commissions_incorporated_amount = sum(
        commission["amount"]
        for commission in prepared_direct_commissions
        if commission["destination"] == "incorpora_base"
    )
    net_amount = effective_cachet_amount - expenses_amount - direct_commissions_amount + direct_commissions_incorporated_amount
    pre_split_adjustments_amount = sum(adjustment["amount"] for adjustment in prepared_pre_split_adjustments)
    pre_split_artist_amount = sum(
        adjustment["amount"]
        for adjustment in prepared_pre_split_adjustments
        if adjustment["destination"] == "artist"
    )
    pre_split_producer_amount = sum(
        adjustment["amount"]
        for adjustment in prepared_pre_split_adjustments
        if adjustment["destination"] == "producer"
    )
    split_base_amount = net_amount - pre_split_adjustments_amount
    if split_base_amount < 0:
        raise HTTPException(status_code=400, detail="Pre-split adjustments cannot exceed show net amount.")

    prepared_external_shares = []
    external_percent_total = 0.0
    external_amount_total = 0.0
    for share in request.external_shares:
        name = share.name.strip()
        if not name:
            continue

        amount = share.amount
        if amount <= 0 and share.percent is not None:
            amount = split_base_amount * share.percent / 100

        if amount <= 0:
            continue

        if share.percent is not None:
            external_percent_total += share.percent
        external_amount_total += amount
        prepared_external_shares.append({
            "name": name,
            "role": share.role,
            "percent": share.percent,
            "amount": amount,
            "cash_handled_by_vpo": share.cash_handled_by_vpo,
            "notes": (share.notes or "").strip() or None,
        })

    if round(request.artist_percent + producer_percent + external_percent_total, 4) > 100.0:
        raise HTTPException(
            status_code=400,
            detail="artist_percent + producer_percent + external share percent cannot exceed 100.",
        )

    if external_amount_total > split_base_amount + 0.01:
        raise HTTPException(status_code=400, detail="External shares cannot exceed split base amount.")

    artist_share = split_base_amount * request.artist_percent / 100
    producer_share = split_base_amount * producer_percent / 100
    post_split_applied_amount = sum(adjustment["applied_amount"] for adjustment in prepared_adjustments)
    artist_cash_target = artist_share + pre_split_artist_amount - post_split_applied_amount
    producer_cash_target = producer_share + pre_split_producer_amount + post_split_applied_amount
    cash_artist_received = sum(
        movement["amount"]
        for movement in prepared_cash_movements
        if movement["recipient"] == "artist"
    )
    cash_producer_received = sum(
        movement["amount"]
        for movement in prepared_cash_movements
        if movement["recipient"] == "producer"
    )
    effective_artist_paid = request.artist_paid_amount + cash_artist_received
    effective_producer_received = request.producer_received_amount + cash_producer_received
    balance_artist = artist_cash_target - effective_artist_paid
    balance_producer = producer_cash_target - effective_producer_received

    return {
        "show_date": show_date,
        "artist": artist,
        "venue": venue,
        "city": city,
        "tour_manager": tour_manager,
        "seller": seller,
        "notes": notes,
        "contracted_cachet": contracted_cachet,
        "venue_collected": venue_collected,
        "venue_balance": venue_balance,
        "venue_payment_status": venue_payment_status,
        "venue_shortfall_policy": shortfall_policy,
        "venue_payment_notes": venue_payment_notes,
        "effective_cachet_amount": effective_cachet_amount,
        "booking_commission_exempt": 1 if request.booking_commission_exempt else 0,
        "booking_commission_notes": booking_commission_notes,
        "receipt_refs": receipt_refs,
        "expenses": prepared_expenses,
        "direct_commissions": prepared_direct_commissions,
        "direct_commissions_amount": direct_commissions_amount,
        "direct_commissions_incorporated_amount": direct_commissions_incorporated_amount,
        "pre_split_adjustments": prepared_pre_split_adjustments,
        "external_shares": prepared_external_shares,
        "cash_movements": prepared_cash_movements,
        "adjustments": prepared_adjustments,
        "expenses_amount": expenses_amount,
        "pre_split_adjustments_amount": pre_split_adjustments_amount,
        "producer_percent": producer_percent,
        "net_amount": net_amount,
        "split_base_amount": split_base_amount,
        "artist_share": artist_share,
        "producer_share": producer_share,
        "artist_cash_target": artist_cash_target,
        "producer_cash_target": producer_cash_target,
        "artist_paid_amount": effective_artist_paid,
        "producer_received_amount": effective_producer_received,
        "balance_artist": balance_artist,
        "balance_producer": balance_producer,
    }


def derive_booking_settlement(
    request: BookingQuickShowRequest,
    payload: dict,
    now: str,
    *,
    previous_status: str | None = None,
    previous_closed_at: str | None = None,
) -> tuple[str, str | None]:
    if previous_status == "historico":
        return "historico", previous_closed_at

    can_close = (
        request.status == "aprobado"
        and abs(payload["balance_producer"]) <= 0.01
        and abs(payload["balance_artist"]) <= 0.01
        and abs(payload["venue_balance"]) <= 0.01
    )
    if can_close:
        return "cerrado", previous_closed_at or now

    return "pendiente", None


def amount_to_ars(amount: float, currency: str, fx_rate: float | None) -> float:
    if currency == "USD" and fx_rate and fx_rate > 0:
        return amount * fx_rate
    return amount


def apply_booking_pre_split_recoveries(
    conn: sqlite3.Connection,
    show_id: int,
    request: BookingQuickShowRequest,
    payload: dict,
    now: str,
) -> None:
    conn.execute(
        """
        DELETE FROM finance_recovery_applications
        WHERE source_type = 'booking_presplit_auto'
          AND source_id LIKE ?
        """,
        (f"{show_id}:pre_split_auto:%",),
    )

    auto_recoveries = [
        adjustment
        for adjustment in payload["pre_split_adjustments"]
        if adjustment.get("destination") == "producer"
        and adjustment.get("recovery_auto_apply")
        and float(adjustment.get("amount") or 0) > 0
    ]
    if not auto_recoveries:
        return

    recovered_rows = conn.execute(
        """
        SELECT finance_movement_id, SUM(COALESCE(amount_ars, 0)) AS recovered_ars
        FROM finance_recovery_applications
        WHERE artist = ?
        GROUP BY finance_movement_id
        """,
        (payload["artist"],),
    ).fetchall()
    recovered_by_movement = {
        int(row["finance_movement_id"]): float(row["recovered_ars"] or 0)
        for row in recovered_rows
    }

    movement_rows = conn.execute(
        """
        SELECT
            id, movement_date, project_name, concept,
            amount_ars, recoverable_percent, status
        FROM finance_staging_movements
        WHERE artist = ?
          AND recoverable = 1
          AND status NOT IN ('aplicado', 'anulado')
        ORDER BY movement_date ASC, id ASC
        """,
        (payload["artist"],),
    ).fetchall()

    open_recoverables: list[dict] = []
    for row in movement_rows:
        movement_id = int(row["id"])
        recoverable_amount = float(row["amount_ars"] or 0) * float(row["recoverable_percent"] or 0) / 100.0
        open_amount = max(recoverable_amount - recovered_by_movement.get(movement_id, 0.0), 0.0)
        if open_amount > 0.01:
            open_recoverables.append({
                "id": movement_id,
                "project_name": row["project_name"],
                "concept": row["concept"],
                "open_amount": open_amount,
            })

    requested_ars = sum(
        amount_to_ars(float(adjustment["amount"]), request.currency, request.fx_rate)
        for adjustment in auto_recoveries
    )
    available_ars = sum(item["open_amount"] for item in open_recoverables)
    if requested_ars > available_ars + 0.01:
        raise HTTPException(
            status_code=400,
            detail=(
                "El recupero pre-split marcado para imputar supera el saldo recuperable abierto "
                f"del artista. Pedido: {requested_ars:.2f}; abierto: {available_ars:.2f}."
            ),
        )

    if not open_recoverables:
        raise HTTPException(
            status_code=400,
            detail="No hay proyectos recuperables abiertos para imputar este recupero.",
        )

    source_base_label = f"{payload['show_date']} - {payload['venue']}"
    cursor_index = 0
    for adjustment_index, adjustment in enumerate(auto_recoveries, start=1):
        remaining = amount_to_ars(float(adjustment["amount"]), request.currency, request.fx_rate)
        source_id = f"{show_id}:pre_split_auto:{adjustment_index}"
        source_label = f"{source_base_label} - {adjustment['concept']}"
        while remaining > 0.01 and cursor_index < len(open_recoverables):
            current = open_recoverables[cursor_index]
            applied = min(remaining, current["open_amount"])
            if applied <= 0.01:
                cursor_index += 1
                continue

            conn.execute(
                """
                INSERT INTO finance_recovery_applications (
                    artist, application_date, finance_movement_id, project_name,
                    source_type, source_id, source_label, amount_ars,
                    recovery_method, notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["artist"],
                    payload["show_date"],
                    current["id"],
                    current["project_name"],
                    "booking_presplit_auto",
                    source_id,
                    source_label,
                    applied,
                    "before_split",
                    "Aplicacion automatica FIFO desde ajuste antes del split en booking.",
                    now,
                ),
            )
            current["open_amount"] -= applied
            remaining -= applied
            if current["open_amount"] <= 0.01:
                cursor_index += 1


def replace_booking_show_children(
    conn: sqlite3.Connection,
    show_id: int,
    request: BookingQuickShowRequest,
    payload: dict,
    now: str,
) -> None:
    conn.execute("DELETE FROM booking_movements WHERE show_id = ?", (show_id,))
    conn.execute("DELETE FROM booking_show_expenses WHERE show_id = ?", (show_id,))
    conn.execute("DELETE FROM booking_pre_split_adjustments WHERE show_id = ?", (show_id,))
    conn.execute("DELETE FROM booking_direct_commissions WHERE show_id = ?", (show_id,))
    conn.execute("DELETE FROM booking_external_shares WHERE show_id = ?", (show_id,))
    conn.execute("DELETE FROM booking_artist_adjustments WHERE show_id = ?", (show_id,))
    apply_booking_pre_split_recoveries(conn, show_id, request, payload, now)

    movement_rows = [
        ("income", "cachet", payload["effective_cachet_amount"]),
        ("expense", "artist_payment", payload["artist_paid_amount"]),
        ("income", "producer_settlement", payload["producer_received_amount"]),
    ]
    for expense in payload["expenses"]:
        movement_rows.append(("expense", f"show_expense:{expense['category']}", expense["amount"]))

    if not payload["expenses"]:
        movement_rows.append(("expense", "show_expenses", payload["expenses_amount"]))

    for commission in payload["direct_commissions"]:
        if commission["destination"] == "salida_directa":
            movement_rows.append(("expense", "direct_commission:salida_directa", commission["amount"]))

    for share in payload["external_shares"]:
        if share["cash_handled_by_vpo"]:
            movement_rows.append(("expense", f"external_share:{share['role']}", share["amount"]))

    for movement_type, category, amount in movement_rows:
        if amount <= 0:
            continue
        conn.execute(
            """
            INSERT INTO booking_movements (
                show_id, movement_type, category, amount, currency, fx_rate, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (show_id, movement_type, category, amount, request.currency, request.fx_rate, None, now),
        )

    for movement in payload["cash_movements"]:
        conn.execute(
            """
            INSERT INTO booking_movements (
                show_id, movement_type, category, amount, currency, fx_rate, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                show_id,
                "income",
                f"cash_received:{movement['recipient']}:{movement['payment_method']}",
                movement["amount"],
                request.currency,
                request.fx_rate,
                json.dumps({
                    "concept": movement["concept"],
                    "paid_by": movement["paid_by"],
                    "notes": movement["notes"],
                }, ensure_ascii=False),
                now,
            ),
        )

    for expense in payload["expenses"]:
        conn.execute(
            """
            INSERT INTO booking_show_expenses (
                show_id, concept, category, amount, currency, fx_rate, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                show_id,
                expense["concept"],
                expense["category"],
                expense["amount"],
                request.currency,
                request.fx_rate,
                expense["notes"],
                now,
            ),
        )

    for commission in payload["direct_commissions"]:
        conn.execute(
            """
            INSERT INTO booking_direct_commissions (
                show_id, concept, recipient, destination, amount, currency, fx_rate, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                show_id,
                commission["concept"],
                commission["recipient"],
                commission["destination"],
                commission["amount"],
                request.currency,
                request.fx_rate,
                commission["notes"],
                now,
            ),
        )

    for adjustment in payload["pre_split_adjustments"]:
        conn.execute(
            """
            INSERT INTO booking_pre_split_adjustments (
                show_id, concept, destination, amount, currency, fx_rate,
                recovery_auto_apply, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                show_id,
                adjustment["concept"],
                adjustment["destination"],
                adjustment["amount"],
                request.currency,
                request.fx_rate,
                1 if adjustment.get("recovery_auto_apply") else 0,
                adjustment["notes"],
                now,
            ),
        )

    for share in payload["external_shares"]:
        conn.execute(
            """
            INSERT INTO booking_external_shares (
                show_id, name, role, percent, amount, currency, fx_rate,
                cash_handled_by_vpo, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                show_id,
                share["name"],
                share["role"],
                share["percent"],
                share["amount"],
                request.currency,
                request.fx_rate,
                1 if share["cash_handled_by_vpo"] else 0,
                share["notes"],
                now,
            ),
        )

    for adjustment in payload["adjustments"]:
        conn.execute(
            """
            INSERT INTO booking_artist_adjustments (
                show_id, concept, adjustment_type, area, impact, recoverable,
                amount, applied_amount, currency, fx_rate, artist_percent, producer_percent,
                artist_amount, producer_amount, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                show_id,
                adjustment["concept"],
                adjustment["adjustment_type"],
                adjustment["area"],
                adjustment["impact"],
                1 if adjustment["recoverable"] else 0,
                adjustment["amount"],
                adjustment["applied_amount"],
                request.currency,
                request.fx_rate,
                adjustment["artist_percent"],
                adjustment["producer_percent"],
                adjustment["artist_amount"],
                adjustment["producer_amount"],
                adjustment["notes"],
                now,
            ),
        )


def fetch_booking_show_item(conn: sqlite3.Connection, show_id: int) -> dict:
    row = conn.execute("SELECT * FROM booking_shows WHERE id = ?", (show_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Booking show not found.")

    item = attach_booking_expenses(conn, [row_to_booking_show(row)])
    item = attach_booking_cash_movements(conn, item)
    item = attach_booking_pre_split_adjustments(conn, item)
    item = attach_booking_direct_commissions(conn, item)
    item = attach_booking_external_shares(conn, item)
    item = attach_booking_adjustments(conn, item)
    return attach_booking_account_applications(conn, item)[0]


def insert_booking_show_from_request(
    conn: sqlite3.Connection,
    request: BookingQuickShowRequest,
    now: str,
    *,
    origin_type: str | None = None,
    origin_id: int | None = None,
    settlement_group: str | None = None,
    validate_artist: bool = True,
) -> dict:
    payload = prepare_booking_show_payload(request, validate_artist=validate_artist)
    settlement_status, settlement_closed_at = derive_booking_settlement(request, payload, now)
    cursor = conn.execute(
        """
        INSERT INTO booking_shows (
            artist, show_date, venue, city, tour_manager, seller, status,
            currency, fx_rate, contracted_cachet_amount, venue_collected_amount,
            venue_balance_amount, venue_payment_status, venue_shortfall_policy,
            venue_payment_notes,
            cachet_amount, expenses_amount, net_amount,
            pre_split_adjustments_amount, split_base_amount,
            artist_percent, producer_percent, artist_share_amount, producer_share_amount,
            artist_cash_target_amount, producer_cash_target_amount,
            artist_paid_amount, producer_received_amount, balance_artist_amount,
            balance_producer_amount, receipt_refs_json, settlement_status,
            settlement_group, settlement_closed_at, settlement_notes,
            origin_type, origin_id, booking_commission_exempt, booking_commission_notes,
            notes, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["artist"],
            payload["show_date"],
            payload["venue"],
            payload["city"],
            payload["tour_manager"],
            payload["seller"],
            request.status,
            request.currency,
            request.fx_rate,
            payload["contracted_cachet"],
            payload["venue_collected"],
            payload["venue_balance"],
            payload["venue_payment_status"],
            payload["venue_shortfall_policy"],
            payload["venue_payment_notes"],
            payload["effective_cachet_amount"],
            payload["expenses_amount"],
            payload["net_amount"],
            payload["pre_split_adjustments_amount"],
            payload["split_base_amount"],
            request.artist_percent,
            payload["producer_percent"],
            payload["artist_share"],
            payload["producer_share"],
            payload["artist_cash_target"],
            payload["producer_cash_target"],
            payload["artist_paid_amount"],
            payload["producer_received_amount"],
            payload["balance_artist"],
            payload["balance_producer"],
            json.dumps(payload["receipt_refs"], ensure_ascii=False),
            settlement_status,
            settlement_group,
            settlement_closed_at,
            None,
            origin_type,
            origin_id,
            payload["booking_commission_exempt"],
            payload["booking_commission_notes"],
            payload["notes"],
            now,
            now,
        ),
    )
    show_id = int(cursor.lastrowid)
    replace_booking_show_children(conn, show_id, request, payload, now)
    return fetch_booking_show_item(conn, show_id)


def update_booking_show_from_request(
    conn: sqlite3.Connection,
    show_id: int,
    request: BookingQuickShowRequest,
    now: str,
    *,
    validate_artist: bool = True,
    preserve_origin: bool = True,
) -> dict:
    payload = prepare_booking_show_payload(request, validate_artist=validate_artist)
    existing = conn.execute(
        """
        SELECT id, settlement_status, settlement_closed_at, origin_type, origin_id, settlement_group
        FROM booking_shows
        WHERE id = ?
        """,
        (show_id,),
    ).fetchone()
    if existing is None:
        raise HTTPException(status_code=404, detail="Booking show not found.")

    settlement_status, settlement_closed_at = derive_booking_settlement(
        request,
        payload,
        now,
        previous_status=existing["settlement_status"],
        previous_closed_at=existing["settlement_closed_at"],
    )

    conn.execute(
        """
        UPDATE booking_shows
        SET artist = ?,
            show_date = ?,
            venue = ?,
            city = ?,
            tour_manager = ?,
            seller = ?,
            status = ?,
            currency = ?,
            fx_rate = ?,
            contracted_cachet_amount = ?,
            venue_collected_amount = ?,
            venue_balance_amount = ?,
            venue_payment_status = ?,
            venue_shortfall_policy = ?,
            venue_payment_notes = ?,
            cachet_amount = ?,
            expenses_amount = ?,
            net_amount = ?,
            pre_split_adjustments_amount = ?,
            split_base_amount = ?,
            artist_percent = ?,
            producer_percent = ?,
            artist_share_amount = ?,
            producer_share_amount = ?,
            artist_cash_target_amount = ?,
            producer_cash_target_amount = ?,
            artist_paid_amount = ?,
            producer_received_amount = ?,
            balance_artist_amount = ?,
            balance_producer_amount = ?,
            receipt_refs_json = ?,
            settlement_status = ?,
            settlement_group = ?,
            settlement_closed_at = ?,
            origin_type = ?,
            origin_id = ?,
            booking_commission_exempt = ?,
            booking_commission_notes = ?,
            notes = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            payload["artist"],
            payload["show_date"],
            payload["venue"],
            payload["city"],
            payload["tour_manager"],
            payload["seller"],
            request.status,
            request.currency,
            request.fx_rate,
            payload["contracted_cachet"],
            payload["venue_collected"],
            payload["venue_balance"],
            payload["venue_payment_status"],
            payload["venue_shortfall_policy"],
            payload["venue_payment_notes"],
            payload["effective_cachet_amount"],
            payload["expenses_amount"],
            payload["net_amount"],
            payload["pre_split_adjustments_amount"],
            payload["split_base_amount"],
            request.artist_percent,
            payload["producer_percent"],
            payload["artist_share"],
            payload["producer_share"],
            payload["artist_cash_target"],
            payload["producer_cash_target"],
            payload["artist_paid_amount"],
            payload["producer_received_amount"],
            payload["balance_artist"],
            payload["balance_producer"],
            json.dumps(payload["receipt_refs"], ensure_ascii=False),
            settlement_status,
            existing["settlement_group"] if preserve_origin else None,
            settlement_closed_at,
            existing["origin_type"] if preserve_origin else None,
            existing["origin_id"] if preserve_origin else None,
            payload["booking_commission_exempt"],
            payload["booking_commission_notes"],
            payload["notes"],
            now,
            show_id,
        ),
    )
    replace_booking_show_children(conn, show_id, request, payload, now)
    item = fetch_booking_show_item(conn, show_id)
    sync_booking_event_from_show(conn, show_id, item, now)
    return item


def clean_booking_artist(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    lowered = text.lower()
    if lowered in {"nan", "none", "null", "todos", "total", "artista", "nombre"}:
        return None

    return text


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def normalize_booking_identity(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(text.casefold().strip().split())


def validate_booking_start_time(value: str | None) -> str | None:
    cleaned = clean_optional_text(value)
    if not cleaned:
        return None
    try:
        return datetime.strptime(cleaned, "%H:%M").strftime("%H:%M")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="La hora debe tener formato HH:MM.") from exc


def require_booking_agenda_postgres() -> None:
    if operational_db_settings().driver != "postgres":
        raise HTTPException(
            status_code=503,
            detail="La Agenda de Booking opera exclusivamente sobre Cloud SQL Postgres.",
        )


def booking_permission_covers_artists(permission: dict, artists: list[str]) -> bool:
    if not permission.get("allowed"):
        return False
    scope = permission.get("scope")
    if scope is None:
        return True
    return all((clean_booking_artist(artist) or "").casefold() in scope for artist in artists)


def booking_event_deposit_amount_in_currency(deposit: dict, event_currency: str) -> float | None:
    amount = float(deposit.get("amount") or 0)
    deposit_currency = str(deposit.get("currency") or "ARS")
    if deposit_currency == event_currency:
        return amount
    fx_rate = float(deposit.get("fx_rate") or 0)
    if fx_rate <= 0:
        return None
    if deposit_currency == "USD" and event_currency == "ARS":
        return amount * fx_rate
    if deposit_currency == "ARS" and event_currency == "USD":
        return amount / fx_rate
    return None


def booking_event_deposit_status(cachet_amount: float, event_currency: str, deposits: list[dict]) -> str:
    if not deposits:
        return "sin_sena"
    converted = [booking_event_deposit_amount_in_currency(item, event_currency) for item in deposits]
    if cachet_amount > 0 and all(value is not None for value in converted):
        if sum(float(value or 0) for value in converted) + 0.01 >= cachet_amount:
            return "sena_recibida"
    return "sena_parcial"


def booking_agenda_event_item(conn: Any, event_id: int) -> dict:
    row = conn.execute(
        """
        SELECT e.*,
               s.id AS booking_show_id,
               c.id AS composite_event_id,
               ce.id AS caserio_event_id,
               (SELECT count(*) FROM booking_events child WHERE child.group_event_id = e.id) AS group_count,
               (
                   SELECT source.source_text
                   FROM booking_event_source_links source
                   WHERE source.event_id = e.id
                   ORDER BY source.id DESC
                   LIMIT 1
               ) AS source_text
        FROM booking_events e
        LEFT JOIN booking_shows s ON s.booking_event_id = e.id
        LEFT JOIN booking_composite_events c ON c.booking_event_id = e.id
        LEFT JOIN caserio_events ce ON ce.booking_event_id = e.id
        WHERE e.id = %s
        """,
        (event_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Evento de Booking no encontrado.")

    artist_rows = conn.execute(
        """
        SELECT artist_id, artist_name, position
        FROM booking_event_artists
        WHERE event_id = %s
        ORDER BY position
        """,
        (event_id,),
    ).fetchall()
    deposit_rows = conn.execute(
        """
        SELECT *
        FROM booking_event_deposits
        WHERE event_id = %s
        ORDER BY movement_date, id
        """,
        (event_id,),
    ).fetchall()

    item = dict(row)
    for key in ("contracted_cachet_amount", "fx_rate"):
        item[key] = float(item.get(key) or 0)
    if item.get("start_time") is not None:
        item["start_time"] = str(item["start_time"])[:5]
    item["event_date"] = item["event_date"].isoformat() if hasattr(item["event_date"], "isoformat") else str(item["event_date"])
    item["artists"] = [
        {
            "artist_id": int(artist["artist_id"]),
            "artist": artist["artist_name"],
            "position": int(artist["position"]),
        }
        for artist in artist_rows
    ]
    deposits: list[dict] = []
    for deposit_row in deposit_rows:
        deposit = dict(deposit_row)
        deposit["amount"] = float(deposit.get("amount") or 0)
        deposit["fx_rate"] = float(deposit.get("fx_rate") or 0)
        deposit["movement_date"] = deposit["movement_date"].isoformat() if hasattr(deposit["movement_date"], "isoformat") else str(deposit["movement_date"])
        deposit["proof_refs"] = parse_json_list(deposit.pop("proof_refs_json", []))
        deposits.append(deposit)
    item["deposits"] = deposits
    item["deposit_total"] = sum(float(deposit["amount"]) for deposit in deposits if deposit["currency"] == item["currency"])
    return item


def validate_booking_event_settlement_link(
    conn: Any,
    *,
    event_id: int,
    booking_mode: str,
    artists: list[str],
) -> dict:
    event = conn.execute(
        "SELECT * FROM booking_events WHERE id = ?",
        (event_id,),
    ).fetchone()
    if event is None:
        raise HTTPException(status_code=400, detail="La precarga de Agenda no existe.")
    if str(event["event_type"]) != "show":
        raise HTTPException(status_code=400, detail="Solo una entrada de tipo show puede iniciar una liquidacion.")
    if str(event["booking_mode"]) != booking_mode:
        expected = "individual" if booking_mode == "individual" else "compartido"
        raise HTTPException(status_code=400, detail=f"La precarga no corresponde a Booking {expected}.")
    if str(event["commercial_status"]) == "cancelado":
        raise HTTPException(status_code=400, detail="No se puede liquidar un show cancelado.")

    caserio_link = conn.execute(
        "SELECT id FROM caserio_events WHERE booking_event_id = ?",
        (event_id,),
    ).fetchone()
    if caserio_link is not None:
        raise HTTPException(status_code=409, detail="Esta precarga ya tiene una liquidacion Caserio vinculada.")

    participant_rows = conn.execute(
        "SELECT artist_name FROM booking_event_artists WHERE event_id = ? ORDER BY position",
        (event_id,),
    ).fetchall()
    expected_artists = {normalize_booking_identity(row["artist_name"]) for row in participant_rows}
    received_artists = {normalize_booking_identity(artist) for artist in artists if clean_booking_artist(artist)}
    if expected_artists != received_artists:
        raise HTTPException(status_code=400, detail="Los artistas de la liquidacion no coinciden con la precarga de Agenda.")

    if booking_mode == "individual":
        linked = conn.execute(
            "SELECT id FROM booking_shows WHERE booking_event_id = ?",
            (event_id,),
        ).fetchone()
    else:
        linked = conn.execute(
            "SELECT id FROM booking_composite_events WHERE booking_event_id = ?",
            (event_id,),
        ).fetchone()
    if linked is not None:
        raise HTTPException(status_code=409, detail="Esta precarga ya tiene una liquidacion vinculada.")
    return dict(event)


def booking_duplicate_candidates(
    conn: Any,
    *,
    event_date: str,
    artists: list[str],
    venue: str,
    city: str | None,
) -> list[dict]:
    expected_artists = {normalize_booking_identity(artist) for artist in artists}
    normalized_venue = normalize_booking_identity(venue)
    normalized_city = normalize_booking_identity(city)
    candidates: list[dict] = []

    event_rows = conn.execute(
        """
        SELECT e.id, e.event_type, e.event_date, e.venue, e.city, e.booking_mode, e.commercial_status,
               a.artist_name
        FROM booking_events e
        JOIN booking_event_artists a ON a.event_id = e.id
        WHERE e.event_date = %s
          AND e.commercial_status <> 'cancelado'
        ORDER BY e.id, a.position
        """,
        (event_date,),
    ).fetchall()
    grouped_events: dict[int, dict] = {}
    for row in event_rows:
        event = grouped_events.setdefault(
            int(row["id"]),
            {
                "source": "agenda",
                "id": int(row["id"]),
                "event_type": str(row["event_type"]),
                "date": str(row["event_date"]),
                "venue": row["venue"] or "",
                "city": row["city"] or "",
                "artists": [],
            },
        )
        event["artists"].append(row["artist_name"])

    for event in grouped_events.values():
        event_artists = {normalize_booking_identity(value) for value in event["artists"]}
        shared_artist = bool(expected_artists & event_artists)
        if not shared_artist:
            continue
        exact_location = (
            normalize_booking_identity(event["venue"]) == normalized_venue
            and normalize_booking_identity(event["city"]) == normalized_city
        )
        event["match"] = "duplicado" if exact_location and event_artists == expected_artists else "conflicto_agenda"
        candidates.append(event)

    show_rows = conn.execute(
        """
        SELECT id, show_date, venue, city, artist
        FROM booking_shows
        WHERE show_date = %s
          AND status <> 'cancelado'
          AND booking_event_id IS NULL
        ORDER BY id
        """,
        (event_date,),
    ).fetchall()
    for row in show_rows:
        artist_name = str(row["artist"] or "")
        if normalize_booking_identity(artist_name) not in expected_artists:
            continue
        exact_location = (
            normalize_booking_identity(row["venue"]) == normalized_venue
            and normalize_booking_identity(row["city"]) == normalized_city
        )
        candidates.append(
            {
                "source": "booking_individual",
                "id": int(row["id"]),
                "date": str(row["show_date"]),
                "venue": row["venue"] or "",
                "city": row["city"] or "",
                "artists": [artist_name],
                "match": "duplicado" if exact_location and len(expected_artists) == 1 else "conflicto_agenda",
            }
        )

    composite_rows = conn.execute(
        """
        SELECT e.id, e.event_date, e.venue, e.city, l.artist
        FROM booking_composite_events e
        JOIN booking_composite_event_lines l ON l.event_id = e.id
        WHERE e.event_date = %s
          AND e.booking_event_id IS NULL
          AND l.line_type = 'artista_vpo'
          AND l.artist IS NOT NULL
        ORDER BY e.id, l.id
        """,
        (event_date,),
    ).fetchall()
    grouped_composite: dict[int, dict] = {}
    for row in composite_rows:
        event = grouped_composite.setdefault(
            int(row["id"]),
            {
                "source": "booking_compartido",
                "id": int(row["id"]),
                "date": str(row["event_date"]),
                "venue": row["venue"] or "",
                "city": row["city"] or "",
                "artists": [],
            },
        )
        event["artists"].append(row["artist"])
    for event in grouped_composite.values():
        event_artists = {normalize_booking_identity(value) for value in event["artists"]}
        if not expected_artists & event_artists:
            continue
        exact_location = (
            normalize_booking_identity(event["venue"]) == normalized_venue
            and normalize_booking_identity(event["city"]) == normalized_city
        )
        event["match"] = "duplicado" if exact_location and event_artists == expected_artists else "conflicto_agenda"
        candidates.append(event)

    return candidates


def resolve_booking_event_for_new_settlement(
    conn: Any,
    *,
    requested_event_id: int | None,
    booking_mode: str,
    artists: list[str],
    event_date: str,
    venue: str,
    city: str | None,
    cachet_amount: float,
    currency: str,
    fx_rate: float | None,
    tour_manager: str | None,
    seller: str | None,
    settlement_status: str,
    actor_username: str | None,
) -> int:
    """Resolve the canonical Agenda header for every new settlement."""
    cleaned_artists = [clean_booking_artist(value) for value in artists]
    cleaned_artists = [value for value in cleaned_artists if value]
    if not cleaned_artists:
        raise HTTPException(status_code=400, detail="La liquidacion necesita al menos un artista VPO.")

    if requested_event_id is not None:
        validate_booking_event_settlement_link(
            conn,
            event_id=requested_event_id,
            booking_mode=booking_mode,
            artists=cleaned_artists,
        )
        return int(requested_event_id)

    candidates = booking_duplicate_candidates(
        conn,
        event_date=event_date,
        artists=cleaned_artists,
        venue=venue,
        city=city,
    )
    exact = [item for item in candidates if item["match"] == "duplicado"]
    exact_agenda = [
        item for item in exact
        if item["source"] == "agenda" and item.get("event_type") == "show"
    ]
    exact_liquidations = [item for item in exact if item["source"] != "agenda"]
    if exact_liquidations:
        item = exact_liquidations[0]
        raise HTTPException(
            status_code=409,
            detail=(
                f"Ya existe una liquidacion historica sin vinculo para {item['date']} · "
                f"{item['venue']}. Abrila y conciliala antes de crear otra."
            ),
        )
    if len(exact_agenda) > 1:
        raise HTTPException(
            status_code=409,
            detail="Hay mas de una entrada exacta en Agenda. Elegi explicitamente cual queres liquidar.",
        )
    if len(exact_agenda) == 1:
        event_id = int(exact_agenda[0]["id"])
        validate_booking_event_settlement_link(
            conn,
            event_id=event_id,
            booking_mode=booking_mode,
            artists=cleaned_artists,
        )
        return event_id

    artist_rows = conn.execute(
        "SELECT id, stage_name FROM artists WHERE active = TRUE ORDER BY lower(stage_name)"
    ).fetchall()
    artist_lookup = {str(row["stage_name"]).casefold(): row for row in artist_rows}
    missing = [artist for artist in cleaned_artists if artist.casefold() not in artist_lookup]
    if missing:
        raise HTTPException(status_code=400, detail=f"Artista no encontrado o inactivo: {', '.join(missing)}")

    unique_rows = []
    seen_artist_ids: set[str] = set()
    for artist in cleaned_artists:
        artist_row = artist_lookup[artist.casefold()]
        artist_id = str(artist_row["id"])
        if artist_id in seen_artist_ids:
            continue
        seen_artist_ids.add(artist_id)
        unique_rows.append(artist_row)

    actor = clean_username(actor_username or "") or "system"
    is_realized = event_date < date.today().isoformat() or settlement_status in {
        "realizado", "rendido", "aprobado", "no_cobrado", "observado", "cerrado"
    }
    row = conn.execute(
        """
        INSERT INTO booking_events (
            event_type, event_date, start_time, venue, city, booking_mode,
            commercial_status, operational_status, deposit_status, settlement_status,
            contracted_cachet_amount, currency, fx_rate, tour_manager, seller,
            duplicate_override, duplicate_override_notes, notes, created_by
        )
        VALUES ('show', %s, NULL, %s, %s, %s,
                'confirmado', %s, 'sin_sena', 'no_iniciada',
                %s, %s, %s, %s, %s,
                FALSE, NULL, %s, %s)
        RETURNING id
        """,
        (
            event_date,
            venue,
            city,
            booking_mode,
            "realizado" if is_realized else "programado",
            cachet_amount,
            currency,
            fx_rate,
            clean_optional_text(tour_manager),
            clean_optional_text(seller),
            "Cabecera creada al iniciar una liquidacion directa.",
            actor,
        ),
    ).fetchone()
    event_id = int(row["id"])
    for position, artist_row in enumerate(unique_rows, start=1):
        conn.execute(
            """
            INSERT INTO booking_event_artists (event_id, artist_id, artist_name, position)
            VALUES (%s, %s, %s, %s)
            """,
            (event_id, artist_row["id"], artist_row["stage_name"], position),
        )
    conn.execute(
        """
        INSERT INTO app_audit_log (
            actor_username, module_key, action, entity_table, entity_id, after_json, notes
        )
        VALUES (%s, %s, 'create', 'booking_events', %s, %s, %s)
        """,
        (
            actor,
            "booking" if booking_mode == "individual" else "composite_booking",
            str(event_id),
            json.dumps(
                {
                    "event_date": event_date,
                    "event_type": "show",
                    "venue": venue,
                    "city": city,
                    "artists": [str(row["stage_name"]) for row in unique_rows],
                    "booking_mode": booking_mode,
                },
                ensure_ascii=False,
            ),
            "Cabecera de Agenda creada desde Liquidaciones.",
        ),
    )
    return event_id


def finance_amount_ars(amount: float, currency: str, fx_rate: float | None) -> float:
    if currency == "USD":
        if not fx_rate:
            raise HTTPException(status_code=400, detail="Para cargar USD falta tipo de cambio.")
        return float(amount) * float(fx_rate)
    return float(amount)


def finance_payment_status(amount_ars: float, paid_amount_ars: float, explicit_status: str | None) -> str:
    if explicit_status:
        return explicit_status
    if paid_amount_ars <= 0.01 and amount_ars > 0.01:
        return "pendiente"
    if paid_amount_ars + 0.01 < amount_ars:
        return "parcial"
    return "pagado"


LOCKED_FINANCE_STATUSES = {"aprobado", "aplicado", "anulado"}


def finance_movement_is_locked(status: str | None) -> bool:
    return (status or "").strip().lower() in LOCKED_FINANCE_STATUSES


def resolve_finance_project(
    conn: sqlite3.Connection,
    request: FinanceMovementRequest,
    now: str,
) -> tuple[int | None, str | None]:
    project_id = request.project_id
    project_name = clean_optional_text(request.project_name)

    if project_id is not None:
        row = conn.execute(
            "SELECT id, name FROM finance_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Proyecto financiero no encontrado.")
        return int(row["id"]), row["name"]

    if not project_name:
        return None, None

    existing = conn.execute(
        """
        SELECT id, name
        FROM finance_projects
        WHERE name = ?
          AND COALESCE(artist, '') = COALESCE(?, '')
          AND business_area = ?
        """,
        (project_name, request.artist, request.business_area),
    ).fetchone()
    if existing:
        return int(existing["id"]), existing["name"]

    cursor = conn.execute(
        """
        INSERT INTO finance_projects (
            name, artist, business_area, status, notes, created_at, updated_at
        )
        VALUES (?, ?, ?, 'activo', ?, ?, ?)
        """,
        (
            project_name,
            request.artist,
            request.business_area,
            "Creado automaticamente desde movimiento financiero.",
            now,
            now,
        ),
    )
    return int(cursor.lastrowid), project_name


def finance_movement_item(row: sqlite3.Row) -> dict:
    item = dict(row)
    try:
        item["proof_refs"] = json.loads(item.pop("proof_refs_json") or "[]")
    except json.JSONDecodeError:
        item["proof_refs"] = []
    item["allocation_lines"] = item.get("allocation_lines", [])
    return item


def ensure_finance_movement_employee_columns(conn: sqlite3.Connection) -> None:
    if not is_postgres_connection(conn):
        raise HTTPException(
            status_code=500,
            detail="Los reintegros a empleados usan Cloud SQL Postgres.",
        )


def ensure_finance_account_entries_table(conn: sqlite3.Connection) -> None:
    if not is_postgres_connection(conn):
        raise HTTPException(
            status_code=500,
            detail="Las cuentas financieras usan Cloud SQL Postgres.",
        )


def ensure_finance_account_applications_table(conn: sqlite3.Connection) -> None:
    ensure_finance_account_entries_table(conn)


def finance_employee_option_from_id(conn: sqlite3.Connection, employee_id: int | None) -> dict | None:
    if not employee_id:
        return None
    row = conn.execute(
        """
        SELECT id, display_name, active
        FROM employees
        WHERE id = ?
        """,
        (employee_id,),
    ).fetchone()
    if row is None or not bool(row["active"]):
        return None
    return {"id": int(row["id"]), "display_name": row["display_name"]}


def replace_employee_reimbursement_account_entry(
    conn: sqlite3.Connection,
    movement_id: int,
    request: FinanceMovementRequest,
    amount_ars: float,
    paid_amount_ars: float,
    employee: dict | None,
    now: str,
) -> None:
    ensure_finance_account_applications_table(conn)
    existing_application = conn.execute(
        """
        SELECT COUNT(*) AS rows
        FROM finance_account_entries fae
        JOIN finance_account_applications faa
          ON faa.account_entry_id = fae.id
        WHERE fae.origin_type = 'finance_employee_reimbursement'
          AND fae.origin_id = ?
        """,
        (movement_id,),
    ).fetchone()
    if existing_application and int(existing_application["rows"] or 0) > 0:
        raise HTTPException(
            status_code=409,
            detail="Este gasto ya tiene reintegros aplicados. Corregilo con un nuevo movimiento.",
        )
    conn.execute(
        """
        DELETE FROM finance_account_entries
        WHERE origin_type = 'finance_employee_reimbursement'
          AND origin_id = ?
        """,
        (movement_id,),
    )
    if (
        request.paid_by != "empleado"
        or employee is None
        or request.movement_type != "gasto"
        or request.status == "anulado"
    ):
        return

    reimbursement_amount_ars = paid_amount_ars if paid_amount_ars > 0 else amount_ars
    if reimbursement_amount_ars <= 0.01:
        return

    notes = "Reintegro pendiente por gasto pagado por empleado."
    if request.notes:
        notes = f"{notes} {request.notes.strip()}"
    conn.execute(
        """
        INSERT INTO finance_account_entries (
            artist, counterparty, counterparty_employee_id, entry_date, origin_type, origin_id, concept,
            amount_ars, direction, status, notes, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 'finance_employee_reimbursement', ?, ?, ?, 'indyana_owes_third_party', 'open', ?, ?, ?)
        """,
        (
            request.artist.strip(),
            employee["display_name"],
            employee["id"],
            request.movement_date,
            movement_id,
            request.concept.strip(),
            reimbursement_amount_ars,
            notes,
            now,
            now,
        ),
    )


def finance_account_entry_balance(conn: sqlite3.Connection, entry_id: int) -> tuple[float, float] | None:
    row = conn.execute(
        """
        SELECT
            fae.amount_ars AS amount_ars,
            COALESCE(SUM(faa.amount_ars), 0) AS applied_amount_ars
        FROM finance_account_entries fae
        LEFT JOIN finance_account_applications faa
          ON faa.account_entry_id = fae.id
        WHERE fae.id = ?
        GROUP BY fae.id, fae.amount_ars
        """,
        (entry_id,),
    ).fetchone()
    if not row:
        return None
    return float(row["amount_ars"] or 0), float(row["applied_amount_ars"] or 0)


def refresh_finance_account_entry_status(conn: sqlite3.Connection, entry_id: int, now: str) -> None:
    balance = finance_account_entry_balance(conn, entry_id)
    if balance is None:
        return
    amount, applied = balance
    if applied <= 0.01:
        status = "open"
    elif applied + 0.01 < amount:
        status = "partial"
    else:
        status = "settled"
    conn.execute(
        """
        UPDATE finance_account_entries
        SET status = ?,
            updated_at = ?
        WHERE id = ?
          AND status != 'void'
        """,
        (status, now, entry_id),
    )


def replace_finance_account_applications(
    conn: sqlite3.Connection,
    movement_id: int,
    request: FinanceMovementRequest,
    amount_ars: float,
    now: str,
    username: str | None,
) -> None:
    ensure_finance_account_applications_table(conn)
    previous_rows = conn.execute(
        """
        SELECT DISTINCT account_entry_id
        FROM finance_account_applications
        WHERE payment_movement_id = ?
        """,
        (movement_id,),
    ).fetchall()
    previous_entry_ids = [int(row["account_entry_id"]) for row in previous_rows]
    conn.execute(
        """
        DELETE FROM finance_account_applications
        WHERE payment_movement_id = ?
        """,
        (movement_id,),
    )

    application_entry_ids: list[int] = []
    should_apply = (
        request.movement_type == "pago"
        and request.category == "employee_reimbursement"
        and request.status != "anulado"
        and bool(request.account_applications)
    )
    if should_apply:
        total_applications = sum(float(item.amount_ars or 0) for item in request.account_applications)
        if total_applications > amount_ars + 0.01:
            raise HTTPException(status_code=400, detail="La aplicacion supera el importe del pago.")
        employee_name = clean_optional_text(request.counterparty)
        for item in request.account_applications:
            entry = conn.execute(
                """
                SELECT id, counterparty, amount_ars, status
                FROM finance_account_entries
                WHERE id = ?
                  AND origin_type = 'finance_employee_reimbursement'
                  AND direction = 'indyana_owes_third_party'
                  AND status IN ('open', 'partial', 'observed')
                """,
                (item.account_entry_id,),
            ).fetchone()
            if not entry:
                raise HTTPException(status_code=400, detail="Uno de los reintegros elegidos no esta abierto.")
            if employee_name and entry["counterparty"] != employee_name:
                raise HTTPException(status_code=400, detail="El pago debe aplicarse a reintegros del mismo empleado.")
            current_balance = finance_account_entry_balance(conn, int(entry["id"]))
            if current_balance is None:
                raise HTTPException(status_code=400, detail="No se pudo calcular el saldo del reintegro.")
            entry_amount, applied_amount = current_balance
            available = max(entry_amount - applied_amount, 0.0)
            if item.amount_ars > available + 0.01:
                raise HTTPException(status_code=400, detail="La aplicacion supera el saldo pendiente de un reintegro.")
            conn.execute(
                """
                INSERT INTO finance_account_applications (
                    account_entry_id, payment_movement_id, application_date,
                    amount_ars, notes, created_by, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(entry["id"]),
                    movement_id,
                    request.movement_date,
                    float(item.amount_ars),
                    clean_optional_text(request.notes),
                    clean_username(username or "") or None,
                    now,
                ),
            )
            application_entry_ids.append(int(entry["id"]))

    for entry_id in sorted(set([*previous_entry_ids, *application_entry_ids])):
        refresh_finance_account_entry_status(conn, entry_id, now)


def ensure_finance_movement_allocations_table(conn: sqlite3.Connection) -> None:
    if is_postgres_connection(conn):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS finance_movement_allocations (
                id bigserial PRIMARY KEY,
                movement_id bigint NOT NULL REFERENCES finance_staging_movements(id) ON DELETE CASCADE,
                allocation_type text NOT NULL DEFAULT 'indyana_cost',
                target_name text NOT NULL,
                business_area text,
                amount numeric(18, 6) NOT NULL DEFAULT 0,
                currency text NOT NULL DEFAULT 'ARS',
                fx_rate numeric(18, 6),
                amount_ars numeric(18, 6) NOT NULL DEFAULT 0,
                notes text,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS finance_movement_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                movement_id INTEGER NOT NULL REFERENCES finance_staging_movements(id) ON DELETE CASCADE,
                allocation_type TEXT NOT NULL DEFAULT 'indyana_cost',
                target_name TEXT NOT NULL,
                business_area TEXT,
                amount REAL NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'ARS',
                fx_rate REAL,
                amount_ars REAL NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_finance_allocations_movement ON finance_movement_allocations(movement_id)"
    )


def finance_allocation_item(row: sqlite3.Row) -> dict:
    data = dict(row)
    for key in ("amount", "fx_rate", "amount_ars"):
        if key in data:
            data[key] = float(data.get(key) or 0)
    return data


def finance_allocation_rows_for_ids(conn: sqlite3.Connection, movement_ids: list[int]) -> dict[int, list[dict]]:
    if not movement_ids:
        return {}
    ensure_finance_movement_allocations_table(conn)
    placeholders = ",".join("?" for _ in movement_ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM finance_movement_allocations
        WHERE movement_id IN ({placeholders})
        ORDER BY movement_id, id
        """,
        movement_ids,
    ).fetchall()
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        item = finance_allocation_item(row)
        grouped.setdefault(int(item["movement_id"]), []).append(item)
    return grouped


def ensure_finance_documents_table(conn: Any) -> None:
    if not is_postgres_connection(conn):
        raise HTTPException(
            status_code=500,
            detail="Los documentos financieros operativos usan Cloud SQL Postgres. SQLite no es una base viva para emitir documentos.",
        )


def finance_document_item(row: sqlite3.Row) -> dict:
    item = dict(row)
    for key in ("amount", "fx_rate", "amount_ars"):
        if key in item:
            item[key] = float(item.get(key) or 0)
    raw_artists = item.pop("artist_names_json", "[]")
    if isinstance(raw_artists, list):
        item["artist_names"] = raw_artists
    else:
        try:
            item["artist_names"] = json.loads(raw_artists or "[]")
        except (TypeError, json.JSONDecodeError):
            item["artist_names"] = []
    return item


def finance_document_rows_for_ids(conn: Any, movement_ids: list[int]) -> dict[int, dict]:
    if not movement_ids:
        return {}
    ensure_finance_documents_table(conn)
    placeholders = ",".join("?" for _ in movement_ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM finance_documents
        WHERE movement_id IN ({placeholders})
        ORDER BY movement_id, id
        """,
        movement_ids,
    ).fetchall()
    return {int(row["movement_id"]): finance_document_item(row) for row in rows}


def validate_finance_document_request(request: FinanceMovementRequest) -> FinanceDocumentDetailRequest | None:
    document = request.document_detail
    if request.category == "sena_show" and not document:
        raise HTTPException(status_code=400, detail="Completa los datos del documento financiero.")
    if not document:
        return None
    if request.movement_type not in {"pago", "gasto"}:
        raise HTTPException(status_code=400, detail="Los documentos financieros se emiten desde Pago / cobro o desde Gasto / inversión.")
    if request.movement_type == "gasto" and document.document_type != "payment_order":
        raise HTTPException(status_code=400, detail="Un gasto/inversión solo puede emitir una orden de pago.")
    if request.category == "sena_show" and document.document_type != "show_deposit_receipt":
        raise HTTPException(status_code=400, detail="La categoría seña de show debe emitir un recibo por seña de show.")
    if document.document_type == "show_deposit_receipt" and request.business_area != "booking":
        raise HTTPException(status_code=400, detail="El recibo por seña de show debe cargarse en el área Booking.")
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="El documento financiero necesita un importe mayor a cero.")
    if request.currency == "USD" and not request.fx_rate:
        raise HTTPException(status_code=400, detail="Para emitir un documento en USD, completa el tipo de cambio.")
    artists = [clean_booking_artist(name) or name.strip() for name in document.artist_names if name.strip()]
    if request.artist.strip() and request.artist.strip() not in artists:
        artists.insert(0, request.artist.strip())
    if document.document_type == "show_deposit_receipt" and not artists:
        raise HTTPException(status_code=400, detail="Elegir al menos un artista del show para el recibo.")
    document.artist_names = list(dict.fromkeys(artists))
    return document


def next_finance_document_number(conn: Any) -> int:
    ensure_finance_documents_table(conn)
    row = conn.execute("SELECT nextval('finance_documents_document_number_seq') AS next_number").fetchone()
    return int(row["next_number"] or 1)


def replace_finance_document_detail(
    conn: Any,
    movement_id: int,
    request: FinanceMovementRequest,
    amount_ars: float,
    now: str,
    username: str | None,
) -> dict | None:
    document = validate_finance_document_request(request)
    ensure_finance_documents_table(conn)
    if not document:
        conn.execute("DELETE FROM finance_documents WHERE movement_id = ?", (movement_id,))
        return None

    existing = conn.execute(
        "SELECT id, document_number FROM finance_documents WHERE movement_id = ?",
        (movement_id,),
    ).fetchone()
    document_number = int(existing["document_number"]) if existing else next_finance_document_number(conn)
    artist_names_json = json.dumps(document.artist_names, ensure_ascii=False)
    if existing:
        conn.execute(
            """
            UPDATE finance_documents
            SET document_date = ?,
                document_type = ?,
                issuer_company = ?,
                counterparty_name = ?,
                amount = ?,
                currency = ?,
                fx_rate = ?,
                amount_ars = ?,
                vat_mode = ?,
                concept = ?,
                show_date = ?,
                venue = ?,
                artist_names_json = ?,
                booking_show_id = ?,
                status = 'emitido',
                notes = ?,
                updated_at = ?
            WHERE movement_id = ?
            """,
            (
                request.movement_date,
                document.document_type,
                document.issuer_company,
                document.counterparty_name.strip(),
                request.amount,
                request.currency,
                request.fx_rate,
                amount_ars,
                document.vat_mode,
                request.concept.strip(),
                clean_optional_text(document.show_date),
                clean_optional_text(document.venue),
                artist_names_json,
                document.booking_show_id,
                clean_optional_text(document.notes),
                now,
                movement_id,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO finance_documents (
                movement_id, document_number, document_date, document_type,
                issuer_company, counterparty_name, amount, currency, fx_rate, amount_ars,
                vat_mode, concept, show_date, venue, artist_names_json,
                booking_show_id, status, notes, created_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'emitido', ?, ?, ?, ?)
            """,
            (
                movement_id,
                document_number,
                request.movement_date,
                document.document_type,
                document.issuer_company,
                document.counterparty_name.strip(),
                request.amount,
                request.currency,
                request.fx_rate,
                amount_ars,
                document.vat_mode,
                request.concept.strip(),
                clean_optional_text(document.show_date),
                clean_optional_text(document.venue),
                artist_names_json,
                document.booking_show_id,
                clean_optional_text(document.notes),
                clean_optional_text(username),
                now,
                now,
            ),
        )
    row = conn.execute("SELECT * FROM finance_documents WHERE movement_id = ?", (movement_id,)).fetchone()
    return finance_document_item(row) if row else None


def finance_document_number_label(amount: float) -> str:
    value = f"{float(amount or 0):,.2f}"
    return value.replace(",", "X").replace(".", ",").replace("X", ".")


def finance_document_amount_label(currency: str, amount: float) -> str:
    if currency == "USD":
        return f"{finance_document_number_label(amount)} dólares americanos"
    return f"{finance_document_number_label(amount)} pesos argentinos"


def finance_document_title(document_type: str) -> str:
    if document_type == "payment_order":
        return "ORDEN DE PAGO"
    if document_type == "collection_receipt":
        return "COMPROBANTE DE COBRO"
    return "RECIBO"


def finance_document_subtitle(document_type: str) -> str:
    if document_type == "payment_order":
        return "Comprobante interno de pago emitido desde Movimientos financieros"
    if document_type == "collection_receipt":
        return "Comprobante interno de cobro emitido desde Movimientos financieros"
    return "Comprobante interno de recepción de dinero"


def finance_document_counterparty_label(document_type: str) -> str:
    if document_type == "payment_order":
        return "Pagado a"
    return "Recibimos de"


def finance_document_amount_row_label(document_type: str) -> str:
    if document_type == "payment_order":
        return "Importe pagado"
    return "Importe recibido"


def finance_document_pdf_bytes(document: dict, movement: dict) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="Falta reportlab para generar PDF de documentos financieros. Instalar dependencias y redeployar.",
        ) from exc

    buffer = BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 20 * mm
    issuer_company = str(document.get("issuer_company") or "VPO Corp").strip() or "VPO Corp"
    document_number = int(document["document_number"])
    document_type = str(document.get("document_type") or "show_deposit_receipt")
    title = finance_document_title(document_type)

    def draw_wrapped(text: str, x: float, y_pos: float, max_chars: int = 82, line_height: float = 5 * mm) -> float:
        cleaned = " ".join(str(text or "").split()) or "-"
        lines = [cleaned[i:i + max_chars] for i in range(0, len(cleaned), max_chars)]
        for line in lines[:4]:
            page.drawString(x, y_pos, line)
            y_pos -= line_height
        return y_pos

    page.setTitle(f"Documento financiero {document_number:06d}")
    page.setFillColor(colors.HexColor("#2f6f67"))
    page.rect(0, height - 34 * mm, width, 34 * mm, stroke=0, fill=1)
    page.setFillColor(colors.white)
    page.setFont("Helvetica-Bold", 18)
    page.drawString(margin, height - 18 * mm, issuer_company)
    page.setFont("Helvetica", 9)
    page.drawString(margin, height - 25 * mm, finance_document_subtitle(document_type))
    page.setFont("Helvetica-Bold", 22)
    page.drawRightString(width - margin, height - 17 * mm, title)
    page.setFont("Helvetica", 10)
    page.drawRightString(width - margin, height - 25 * mm, f"Nro. {document_number:06d}")

    y = height - 48 * mm
    page.setFillColor(colors.HexColor("#0f172a"))
    page.setFont("Helvetica-Bold", 12)
    page.drawString(margin, y, "Datos del documento")
    y -= 7 * mm

    box_x = margin
    box_w = width - (2 * margin)
    box_y = y - 55 * mm
    page.setStrokeColor(colors.HexColor("#d7dee8"))
    page.setFillColor(colors.HexColor("#f8fafc"))
    page.roundRect(box_x, box_y, box_w, 58 * mm, 4 * mm, stroke=1, fill=1)
    y -= 9 * mm

    rows = [
        ("Fecha", str(document.get("document_date") or "")),
        (finance_document_counterparty_label(document_type), str(document.get("counterparty_name") or "")),
        (finance_document_amount_row_label(document_type), finance_document_amount_label(str(document.get("currency") or "ARS"), float(document.get("amount") or 0))),
        ("Concepto", str(document.get("concept") or movement.get("concept") or "")),
        ("Area", str(movement.get("business_area") or "-")),
        ("Artista / unidad", ", ".join(document.get("artist_names") or [movement.get("artist") or ""])),
    ]
    if document_type == "show_deposit_receipt":
        rows.extend([
            ("Fecha del show", str(document.get("show_date") or "-")),
            ("Lugar", str(document.get("venue") or "-")),
        ])
    label_x = margin + 7 * mm
    value_x = margin + 50 * mm
    for label, value in rows:
        page.setFont("Helvetica-Bold", 10)
        page.setFillColor(colors.HexColor("#475569"))
        page.drawString(label_x, y, f"{label}:")
        page.setFont("Helvetica", 10)
        page.setFillColor(colors.HexColor("#0f172a"))
        y = draw_wrapped(value, value_x, y, max_chars=62)
        y -= 2 * mm

    notes = str(document.get("notes") or movement.get("notes") or "").strip()
    if notes:
        y -= 6 * mm
        page.setFont("Helvetica-Bold", 10)
        page.drawString(margin, y, "Notas:")
        y -= 6 * mm
        page.setFont("Helvetica", 10)
        for line in notes.splitlines()[:8]:
            y = draw_wrapped(line, margin, y, max_chars=105)

    y = 65 * mm
    page.setStrokeColor(colors.HexColor("#94a3b8"))
    page.line(margin, y, margin + 65 * mm, y)
    page.line(width - margin - 65 * mm, y, width - margin, y)
    y -= 5 * mm
    page.setFillColor(colors.HexColor("#334155"))
    page.setFont("Helvetica", 9)
    page.drawString(margin, y, "Firma / aclaración")
    page.drawString(width - margin - 65 * mm, y, f"Emitido por {issuer_company}"[:48])

    page.setFillColor(colors.HexColor("#64748b"))
    page.setFont("Helvetica", 8)
    page.drawString(margin, 18 * mm, "Documento generado desde Movimientos financieros.")
    page.drawRightString(width - margin, 18 * mm, datetime.now().isoformat(timespec="seconds"))
    page.showPage()
    page.save()
    return buffer.getvalue()

def finance_normalized_allocations(
    request: FinanceMovementRequest,
    movement_amount_ars: float,
) -> list[dict]:
    if not request.allocation_lines:
        return [
            {
                "allocation_type": "indyana_cost",
                "target_name": "Indyana",
                "business_area": request.business_area,
                "amount": request.amount,
                "currency": request.currency,
                "fx_rate": request.fx_rate,
                "amount_ars": movement_amount_ars,
                "notes": None,
            }
        ]

    normalized: list[dict] = []
    total_ars = 0.0
    for line in request.allocation_lines:
        currency = line.currency or request.currency
        fx_rate = line.fx_rate if currency == "USD" else None
        if currency == "USD" and not fx_rate:
            fx_rate = request.fx_rate
        amount_ars = finance_amount_ars(line.amount, currency, fx_rate)
        normalized.append(
            {
                "allocation_type": line.allocation_type,
                "target_name": line.target_name.strip(),
                "business_area": line.business_area or request.business_area,
                "amount": line.amount,
                "currency": currency,
                "fx_rate": fx_rate,
                "amount_ars": amount_ars,
                "notes": clean_optional_text(line.notes),
            }
        )
        total_ars += amount_ars

    if abs(total_ars - movement_amount_ars) > 0.05:
        raise HTTPException(
            status_code=400,
            detail=(
                "La distribucion economica debe cerrar con el compromiso total "
                f"del movimiento. Distribuido: {round(total_ars, 2)} / Movimiento: {round(movement_amount_ars, 2)}."
            ),
        )
    return normalized


def replace_finance_movement_allocations(
    conn: sqlite3.Connection,
    movement_id: int,
    request: FinanceMovementRequest,
    movement_amount_ars: float,
    now: str,
) -> None:
    ensure_finance_movement_allocations_table(conn)
    allocations = finance_normalized_allocations(request, movement_amount_ars)
    conn.execute("DELETE FROM finance_movement_allocations WHERE movement_id = ?", (movement_id,))
    for line in allocations:
        conn.execute(
            """
            INSERT INTO finance_movement_allocations (
                movement_id, allocation_type, target_name, business_area,
                amount, currency, fx_rate, amount_ars, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                movement_id,
                line["allocation_type"],
                line["target_name"],
                line["business_area"],
                line["amount"],
                line["currency"],
                line["fx_rate"],
                line["amount_ars"],
                line["notes"],
                now,
                now,
            ),
        )


def finance_ledger_entry(
    *,
    entry_id: str,
    ledger_date: str,
    artist: str,
    business_area: str,
    ledger_type: str,
    project_name: str | None,
    concept: str,
    source_module: str,
    source_table: str,
    source_id: str,
    source_label: str | None = None,
    amount_ars: float = 0.0,
    account_delta_ars: float = 0.0,
    venue_receivable_ars: float = 0.0,
    investment_ars: float = 0.0,
    recoverable_origin_ars: float = 0.0,
    recovered_amount_ars: float = 0.0,
    recoverable_open_ars: float = 0.0,
    status: str | None = None,
    notes: str | None = None,
) -> dict:
    return {
        "id": entry_id,
        "ledger_date": ledger_date,
        "artist": artist,
        "business_area": business_area,
        "ledger_type": ledger_type,
        "project_name": project_name,
        "concept": concept,
        "source_module": source_module,
        "source_table": source_table,
        "source_id": str(source_id),
        "source_label": source_label,
        "amount_ars": float(amount_ars or 0),
        "account_delta_ars": float(account_delta_ars or 0),
        "venue_receivable_ars": float(venue_receivable_ars or 0),
        "investment_ars": float(investment_ars or 0),
        "recoverable_origin_ars": float(recoverable_origin_ars or 0),
        "recovered_amount_ars": float(recovered_amount_ars or 0),
        "recoverable_open_ars": float(recoverable_open_ars or 0),
        "status": status,
        "notes": notes,
    }


def booking_current_account_net(indyana_balance: float, artist_balance: float) -> float:
    """Net booking account balance without double-counting mirrored show balances."""
    indyana = float(indyana_balance or 0)
    artist = float(artist_balance or 0)
    if abs(indyana) <= 0.01:
        return 0.0 if abs(artist) <= 0.01 else -artist
    if abs(artist) <= 0.01:
        return indyana
    if indyana * artist < 0:
        return indyana if abs(indyana) >= abs(artist) else -artist
    return indyana - artist


def build_artist_finance_ledger(
    conn: sqlite3.Connection,
    selected_artist: str | None,
    x_vpo_username: str | None = None,
    module_key: str = "artist_finance",
) -> dict:
    entries: list[dict] = []
    params: list = []
    where_artist = ""
    if selected_artist:
        where_artist = "AND artist = ?"
        params.append(selected_artist)
    artist_scope_sql = apply_artist_scope_sql(conn, x_vpo_username, module_key, params)
    ensure_booking_account_applications_table(conn)

    booking_rows = conn.execute(
        f"""
        WITH account_applications AS (
            SELECT
                show_id,
                SUM(CASE WHEN target_balance = 'producer' THEN effect_amount ELSE 0 END) AS producer_effect,
                SUM(CASE WHEN target_balance = 'artist' THEN effect_amount ELSE 0 END) AS artist_effect,
                SUM(CASE WHEN target_balance = 'venue' THEN effect_amount ELSE 0 END) AS venue_effect
            FROM booking_account_applications
            GROUP BY show_id
        )
        SELECT
            booking_shows.id,
            artist,
            show_date,
            venue,
            COALESCE(balance_producer_amount, 0) + COALESCE(account_applications.producer_effect, 0) AS indyana_balance,
            COALESCE(balance_artist_amount, 0) + COALESCE(account_applications.artist_effect, 0) AS artist_balance,
            COALESCE(venue_balance_amount, 0) + COALESCE(account_applications.venue_effect, 0) AS venue_balance,
            settlement_status, status, notes
        FROM booking_shows
        LEFT JOIN account_applications ON account_applications.show_id = booking_shows.id
        WHERE status <> 'cancelado'
          {where_artist}
          {artist_scope_sql}
          AND (
            ABS(COALESCE(balance_producer_amount, 0) + COALESCE(account_applications.producer_effect, 0)) > 0.01
            OR ABS(COALESCE(balance_artist_amount, 0) + COALESCE(account_applications.artist_effect, 0)) > 0.01
            OR ABS(COALESCE(venue_balance_amount, 0) + COALESCE(account_applications.venue_effect, 0)) > 0.01
          )
        ORDER BY show_date DESC, id DESC
        """,
        params,
    ).fetchall()

    for row in booking_rows:
        source_label = f"{row['show_date']} - {row['venue']} - Show #{row['id']}"
        indyana_balance = float(row["indyana_balance"] or 0)
        artist_balance = float(row["artist_balance"] or 0)
        venue_balance = float(row["venue_balance"] or 0)
        status = row["settlement_status"] or row["status"]
        account_balance = booking_current_account_net(indyana_balance, artist_balance)
        if abs(account_balance) > 0.01:
            account_concept = "saldo a favor de Indyana" if account_balance > 0 else "saldo a favor del artista"
            entries.append(
                finance_ledger_entry(
                    entry_id=f"booking-show-{row['id']}-account",
                    ledger_date=row["show_date"],
                    artist=row["artist"],
                    business_area="booking",
                    ledger_type="booking_account_current",
                    project_name=None,
                    concept=f"{row['venue']} - {account_concept}",
                    source_module="booking",
                    source_table="booking_shows",
                    source_id=str(row["id"]),
                    source_label=source_label,
                    amount_ars=account_balance,
                    account_delta_ars=account_balance,
                    status=status,
                    notes=row["notes"],
                )
            )
        if abs(venue_balance) > 0.01:
            entries.append(
                finance_ledger_entry(
                    entry_id=f"booking-show-{row['id']}-venue",
                    ledger_date=row["show_date"],
                    artist=row["artist"],
                    business_area="booking",
                    ledger_type="booking_venue_receivable",
                    project_name=None,
                    concept=f"{row['venue']} - deuda boliche/cliente",
                    source_module="booking",
                    source_table="booking_shows",
                    source_id=str(row["id"]),
                    source_label=source_label,
                    amount_ars=venue_balance,
                    venue_receivable_ars=venue_balance,
                    status=status,
                    notes=row["notes"],
                )
            )

    finance_params: list = []
    finance_where = "WHERE 1 = 1"
    if selected_artist:
        finance_where += " AND artist = ?"
        finance_params.append(selected_artist)
    finance_where += apply_artist_scope_sql(conn, x_vpo_username, module_key, finance_params)

    recovery_rows = conn.execute(
        f"""
        SELECT
            id, artist, application_date, finance_movement_id, project_name,
            source_type, source_id, source_label, amount_ars,
            recovery_method, notes, created_at
        FROM finance_recovery_applications
        {finance_where}
        ORDER BY application_date DESC, id DESC
        """,
        finance_params,
    ).fetchall()
    recovered_by_movement: dict[int, float] = {}
    for row in recovery_rows:
        movement_id = int(row["finance_movement_id"] or 0)
        recovered_by_movement[movement_id] = recovered_by_movement.get(movement_id, 0.0) + float(row["amount_ars"] or 0)

    finance_rows = conn.execute(
        f"""
        SELECT
            id, movement_date, artist, business_area, movement_type, category,
            project_name, concept, counterparty, paid_by,
            amount_ars, paid_amount_ars, pending_amount_ars,
            recoverable, recoverable_percent, recovery_method,
            artist_percent, producer_percent, account_effect,
            status, source_type, source_id, notes
        FROM finance_staging_movements
        {finance_where}
        ORDER BY movement_date DESC, id DESC
        """,
        finance_params,
    ).fetchall()

    for row in finance_rows:
        if row["status"] == "anulado":
            continue
        amount_ars = float(row["amount_ars"] or 0)
        paid_amount_ars = float(row["paid_amount_ars"] or 0)
        account_effect = row["account_effect"] or "sin_impacto"
        account_delta = 0.0
        if account_effect == "artista_debe_indyana":
            account_delta = amount_ars
        elif account_effect == "indyana_debe_artista":
            account_delta = -amount_ars

        is_investment = row["movement_type"] == "gasto" and account_effect in {"inversion_indyana", "sin_impacto"}
        recoverable_origin = (
            amount_ars * float(row["recoverable_percent"] or 0) / 100.0
            if row["recoverable"] and row["status"] not in {"aplicado", "anulado"}
            else 0.0
        )
        recovered_amount = recovered_by_movement.get(int(row["id"] or 0), 0.0)
        recoverable_open = max(recoverable_origin - recovered_amount, 0.0)
        ledger_type = "finance_account_current" if account_delta else "finance_investment"
        if row["movement_type"] == "ingreso":
            ledger_type = "finance_income"
        elif row["movement_type"] in {"recupero", "pago", "ajuste"} and not account_delta:
            ledger_type = "finance_movement"

        entries.append(
            finance_ledger_entry(
                entry_id=f"finance-movement-{row['id']}",
                ledger_date=row["movement_date"],
                artist=row["artist"],
                business_area=row["business_area"],
                ledger_type=ledger_type,
                project_name=row["project_name"],
                concept=row["concept"],
                source_module="finance",
                source_table="finance_staging_movements",
                source_id=str(row["id"]),
                source_label=f"Movimiento financiero #{row['id']}",
                amount_ars=amount_ars,
                account_delta_ars=account_delta,
                investment_ars=paid_amount_ars if is_investment else 0.0,
                recoverable_origin_ars=recoverable_origin,
                recovered_amount_ars=recovered_amount,
                recoverable_open_ars=recoverable_open,
                status=row["status"],
                notes=row["notes"],
            )
        )

    for row in recovery_rows:
        amount_ars = float(row["amount_ars"] or 0)
        entries.append(
            finance_ledger_entry(
                entry_id=f"recovery-application-{row['id']}",
                ledger_date=row["application_date"],
                artist=row["artist"],
                business_area="booking",
                ledger_type="recoverable_application",
                project_name=row["project_name"],
                concept=row["source_label"] or f"Recupero aplicado #{row['id']}",
                source_module="finance",
                source_table="finance_recovery_applications",
                source_id=str(row["id"]),
                source_label=row["source_label"],
                amount_ars=amount_ars,
                recovered_amount_ars=amount_ars,
                status="aplicado",
                notes=row["notes"],
            )
        )

    entries.sort(key=lambda item: (item["ledger_date"] or "", item["id"]), reverse=True)
    account_positive = sum(max(float(item["account_delta_ars"] or 0), 0.0) for item in entries)
    account_negative = sum(max(-float(item["account_delta_ars"] or 0), 0.0) for item in entries)
    recoverable_origin = sum(float(item["recoverable_origin_ars"] or 0) for item in entries if item["source_table"] == "finance_staging_movements")
    recovered_amount = sum(float(item["amount_ars"] or 0) for item in entries if item["ledger_type"] == "recoverable_application")
    return {
        "entries": entries[:500],
        "summary": {
            "account_current_net_ars": account_positive - account_negative,
            "artist_owes_indyana_ars": account_positive,
            "indyana_owes_artist_ars": account_negative,
            "venue_receivable_ars": sum(float(item["venue_receivable_ars"] or 0) for item in entries),
            "investment_ars": sum(float(item["investment_ars"] or 0) for item in entries),
            "recoverable_origin_ars": recoverable_origin,
            "recovered_amount_ars": recovered_amount,
            "recoverable_open_ars": max(recoverable_origin - recovered_amount, 0.0),
            "rows": len(entries),
            "official": True,
            "note": "Ledger v1 canonico de lectura: normaliza booking, movimientos financieros y aplicaciones de recupero sin duplicar la fuente.",
        },
    }


def booking_artist_options() -> list[str]:
    artists: dict[str, str] = {}
    init_booking_db()
    with booking_connect() as conn:
        artist_rows = conn.execute(
            """
            SELECT stage_name
            FROM booking_artists
            WHERE active = 1
            ORDER BY stage_name
            """
        ).fetchall()
        show_rows = conn.execute("SELECT DISTINCT artist FROM booking_shows").fetchall()

    for row in artist_rows:
        cleaned = clean_booking_artist(row["stage_name"])
        if cleaned:
            artists.setdefault(cleaned.casefold(), cleaned)
    for row in show_rows:
        cleaned = clean_booking_artist(row["artist"])
        if cleaned:
            artists.setdefault(cleaned.casefold(), cleaned)

    return sorted(artists.values(), key=lambda value: value.casefold())


def require_known_booking_artist(artist: str) -> str:
    cleaned = clean_booking_artist(artist)
    if not cleaned:
        raise HTTPException(status_code=400, detail="artist is required.")

    artists = {value.casefold(): value for value in booking_artist_options()}
    canonical = artists.get(cleaned.casefold())
    if canonical is None:
        raise HTTPException(status_code=400, detail="Artist must be selected from the booking artist list.")

    return canonical


def dataframe_values(dataframe) -> list[list[object]]:
    clean = dataframe.where(dataframe.notna(), "")
    values = [list(clean.columns)]

    for row in clean.astype(object).itertuples(index=False, name=None):
        values.append([value.item() if hasattr(value, "item") else value for value in row])

    return values


def sheet_title(keywords: list[str], start_month: str | None, end_month: str | None) -> str:
    keyword_part = " ".join(keywords)[:60] or "keyword"
    period_part = ""
    if start_month or end_month:
        period_part = f" {start_month or 'start'} to {end_month or 'end'}"
    return f"VPO Royalties - {keyword_part}{period_part}"


def column_width(column_name: str, dataframe) -> int:
    lower_name = column_name.lower()

    sample_values = [str(column_name)]
    if column_name in dataframe.columns:
        sample_values.extend(
            str(value)
            for value in dataframe[column_name].head(80).fillna("").tolist()
        )

    max_len = max((len(value) for value in sample_values), default=10)
    calculated = max_len * 7 + 24

    min_width = 90
    max_width = 220

    if "texto coincidente" in lower_name:
        max_width = 360
        min_width = 180
    elif "tema" in lower_name or "title" in lower_name or "artista" in lower_name or "artist" in lower_name:
        max_width = 260
        min_width = 140
    elif "archivo" in lower_name:
        max_width = 280
        min_width = 160
    elif "generado" in lower_name:
        max_width = 180
        min_width = 130
    elif lower_name in {"ingresos usd", "importe neto"}:
        max_width = 130
        min_width = 115
    elif lower_name in {"unidades", "filas", "filas song level", "filas raw"}:
        max_width = 120
        min_width = 95
    elif lower_name in {"desde", "hasta", "mes", "fuente", "cuenta", "tipo de contenido", "isrc"}:
        max_width = 150
        min_width = 100

    return int(min(max(calculated, min_width), max_width))


def create_google_sheet(
    tables,
    keywords: list[str],
    start_month: str | None,
    end_month: str | None,
) -> str:
    credentials = google_credentials(GOOGLE_API_SCOPES)
    sheets_service = google_build("sheets", "v4", credentials=credentials, cache_discovery=False)
    drive_service = google_build("drive", "v3", credentials=credentials, cache_discovery=False)

    sheet_names = list(tables.keys())
    title = sheet_title(keywords, start_month, end_month)

    if GOOGLE_DRIVE_FOLDER_ID:
        try:
            drive_file = drive_service.files().create(
                body={
                    "name": title,
                    "mimeType": "application/vnd.google-apps.spreadsheet",
                    "parents": [GOOGLE_DRIVE_FOLDER_ID],
                },
                fields="id,webViewLink",
                supportsAllDrives=True,
            ).execute()
        except HttpError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google Drive file create failed in folder {GOOGLE_DRIVE_FOLDER_ID}: {exc.reason}",
            ) from exc

        spreadsheet_id = drive_file["id"]
        spreadsheet_url = drive_file.get("webViewLink") or f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"

        try:
            metadata = sheets_service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets.properties(sheetId,title)",
            ).execute()
            first_sheet_id = metadata["sheets"][0]["properties"]["sheetId"]
            setup_requests = [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": first_sheet_id,
                            "title": sheet_names[0],
                        },
                        "fields": "title",
                    }
                }
            ]
            setup_requests.extend(
                {"addSheet": {"properties": {"title": name}}}
                for name in sheet_names[1:]
            )
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": setup_requests},
            ).execute()
        except HttpError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google Sheets setup failed: {exc.reason}",
            ) from exc
    else:
        try:
            spreadsheet = sheets_service.spreadsheets().create(
                body={
                    "properties": {"title": title},
                    "sheets": [{"properties": {"title": name}} for name in sheet_names],
                },
                fields="spreadsheetId,spreadsheetUrl,sheets.properties",
            ).execute()
        except HttpError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google Sheets create failed: {exc.reason}",
            ) from exc

        spreadsheet_id = spreadsheet["spreadsheetId"]
        spreadsheet_url = spreadsheet["spreadsheetUrl"]

    for sheet_name, dataframe in tables.items():
        values = dataframe_values(dataframe)
        if not values:
            continue

        try:
            sheets_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"'{sheet_name}'!A1",
                valueInputOption="USER_ENTERED",
                body={"values": values},
            ).execute()
        except HttpError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google Sheets write failed on {sheet_name}: {exc.reason}",
            ) from exc

    metadata = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties(sheetId,title)",
    ).execute()
    sheet_id_by_title = {
        sheet["properties"]["title"]: sheet["properties"]["sheetId"]
        for sheet in metadata["sheets"]
    }

    amount_headers = {
        "amount_usd",
        "song_level_amount_usd",
        "net_amount",
        "Ingresos USD",
        "Importe neto",
    }
    integer_headers = {
        "units",
        "rows",
        "song_level_rows",
        "raw_sample_rows",
        "Unidades",
        "Filas",
        "Filas song level",
        "Filas raw",
    }

    requests = []
    for sheet_name, dataframe in tables.items():
        sheet_id = sheet_id_by_title[sheet_name]
        column_count = max(1, len(dataframe.columns))
        row_count = max(1, len(dataframe.index) + 1)
        requests.extend([
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.12, "green": 0.31, "blue": 0.47},
                            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True},
                            "horizontalAlignment": "CENTER",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            },
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": column_count,
                    }
                }
            },
        ])

        requests.append({
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": column_count,
                    }
                }
            }
        })

        for idx, column_name in enumerate(dataframe.columns):
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": idx,
                        "endIndex": idx + 1,
                    },
                    "properties": {
                        "pixelSize": column_width(str(column_name), dataframe),
                    },
                    "fields": "pixelSize",
                }
            })

            if column_name in amount_headers:
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": row_count,
                            "startColumnIndex": idx,
                            "endColumnIndex": idx + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "CURRENCY",
                                    "pattern": "$#,##0.00",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                })
            elif column_name in integer_headers:
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": row_count,
                            "startColumnIndex": idx,
                            "endColumnIndex": idx + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "NUMBER",
                                    "pattern": "#,##0",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                })

    if requests:
        try:
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests},
            ).execute()
        except HttpError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google Sheets format failed: {exc.reason}",
            ) from exc

    if GOOGLE_SHEETS_SHARE_EMAIL:
        try:
            drive_service.permissions().create(
                fileId=spreadsheet_id,
                body={
                    "type": "user",
                    "role": "writer",
                    "emailAddress": GOOGLE_SHEETS_SHARE_EMAIL,
                },
                sendNotificationEmail=False,
            ).execute()
        except HttpError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google Drive share failed for {GOOGLE_SHEETS_SHARE_EMAIL}: {exc.reason}",
            ) from exc

    return spreadsheet_url


@app.get("/health")
def health() -> dict:
    sheets_auth_mode = "oauth_user" if GOOGLE_OAUTH_TOKEN_JSON else "service_account"
    return {
        "status": "ok",
        "bucket": GCS_BUCKET,
        "prefix": GCS_PREFIX,
        "marts_mode": "local" if VPO_LOCAL_MARTS_DIR is not None and VPO_LOCAL_MARTS_DIR.exists() else "gcs",
        "local_marts_dir": str(VPO_LOCAL_MARTS_DIR) if VPO_LOCAL_MARTS_DIR is not None else "",
        "sheets_auth_mode": sheets_auth_mode,
        "drive_folder_configured": "yes" if GOOGLE_DRIVE_FOLDER_ID else "no",
        "share_email_configured": "yes" if GOOGLE_SHEETS_SHARE_EMAIL else "no",
        "operational_db": operational_db_healthcheck(),
    }


@app.get("/source-monitor")
def source_monitor(x_vpo_api_key: str | None = Header(default=None)):
    require_api_key(x_vpo_api_key)
    local_marts_available = VPO_LOCAL_MARTS_DIR is not None and VPO_LOCAL_MARTS_DIR.exists()
    monitor_mart_file = STANDARDIZED_FILE if local_marts_available else STATEMENT_SUMMARY_FILE
    marts = ensure_marts(refresh_cache=False, filenames=[monitor_mart_file])
    mart_summary = source_monitor_mart_summary(marts[monitor_mart_file])
    config_items = load_source_monitor_config()

    configured_keys = {(item.get("source"), item.get("account")) for item in config_items}
    for source, account in sorted(mart_summary):
        if (source, account) in configured_keys:
            continue
        config_items.append({
            "id": source_monitor_id(source, account),
            "source": source,
            "account": account,
            "display_name": f"{source} / {account}",
            "input_path": "",
            "expected_frequency": "monthly",
            "max_age_months": 2,
            "monitoring_active": True,
            "alert_silenced": False,
            "portal_url": "",
            "notes": "",
        })

    items = []
    status_counts = {"ok": 0, "attention": 0, "alert": 0, "inactive": 0}
    today = date.today()

    for config in config_items:
        source = str(config.get("source") or "")
        account = str(config.get("account") or "")
        key = (source, account)
        raw_info = latest_raw_file_info(str(config.get("input_path") or ""))
        mart_info = mart_summary.get(key, {})

        last_statement = mart_info.get("last_statement_period")
        age = month_age(last_statement, today=today)
        max_age = int(config.get("max_age_months") or 2)
        monitoring_active = bool(config.get("monitoring_active", True))
        alert_silenced = bool(config.get("alert_silenced", False))
        mart_names = set(mart_info.get("mart_file_names") or [])
        raw_inventory = build_raw_inventory(source, str(config.get("input_path") or ""), mart_names)
        raw_inventory_summary = raw_inventory["summary"]
        unprocessed_raw_files = [
            str(item.get("file_name"))
            for item in raw_inventory["items"]
            if item.get("status") == "pending_real"
        ]

        if not monitoring_active:
            status = "inactive"
            alert = False
            reason = "Monitoreo inactivo: no genera alerta, pero los datos historicos siguen incluidos."
        elif age is None:
            status = "alert"
            alert = not alert_silenced
            reason = "No se detecto statement cargado."
        elif age > max_age:
            status = "alert"
            alert = not alert_silenced
            reason = f"Ultimo statement {last_statement}; supera tolerancia de {max_age} meses."
        elif unprocessed_raw_files:
            status = "attention"
            alert = not alert_silenced
            reason = "Hay archivos raw que no figuran en el mart nuevo."
        else:
            status = "ok"
            alert = False
            reason = "Dentro de tolerancia."

        if alert_silenced and status in {"alert", "attention"}:
            reason = f"Alerta silenciada. {reason}"

        status_counts[status] = status_counts.get(status, 0) + 1
        items.append({
            "id": config.get("id") or source_monitor_id(source, account),
            "source": source,
            "account": account,
            "display_name": config.get("display_name") or f"{source} / {account}",
            "input_path": config.get("input_path") or "",
            "expected_frequency": config.get("expected_frequency") or "monthly",
            "max_age_months": max_age,
            "monitoring_active": monitoring_active,
            "alert_silenced": alert_silenced,
            "portal_url": config.get("portal_url") or "",
            "notes": config.get("notes") or "",
            "last_manual_review_at": config.get("last_manual_review_at") or None,
            "last_statement_period": last_statement,
            "statement_age_months": age,
            "statement_files_in_mart": mart_info.get("statement_files_in_mart", 0),
            "rows_in_mart": mart_info.get("rows_in_mart", 0),
            "files_in_mart": len(mart_names),
            "raw_files": raw_info["raw_files"],
            "latest_raw_file": raw_info["latest_raw_file"],
            "latest_raw_modified": raw_info["latest_raw_modified"],
            "unprocessed_raw_files": unprocessed_raw_files[:20],
            "unprocessed_raw_count": len(unprocessed_raw_files),
            "raw_inventory_summary": raw_inventory_summary,
            "ignored_raw_count": sum(
                count
                for status, count in raw_inventory_summary.items()
                if status.startswith("ignored_")
            ),
            "ignored_raw_files": [
                item for item in raw_inventory["items"]
                if str(item.get("status") or "").startswith("ignored_")
            ][:20],
            "status": status,
            "alert": alert,
            "reason": reason,
        })

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "items": items,
        "summary": {
            "total": len(items),
            "alerts": sum(1 for item in items if item["alert"]),
            "status_counts": status_counts,
        },
    }


@app.post("/source-monitor/publish")
def publish_source_monitor_marts(x_vpo_api_key: str | None = Header(default=None)):
    require_api_key(x_vpo_api_key)
    return start_publish_job()


@app.get("/source-monitor/publish/{job_id}")
def source_monitor_publish_status(
    job_id: str,
    x_vpo_api_key: str | None = Header(default=None),
):
    require_api_key(x_vpo_api_key)
    return get_publish_job(job_id)


@app.patch("/source-monitor/{monitor_id}")
def update_source_monitor(
    monitor_id: str,
    request: SourceMonitorUpdateRequest,
    x_vpo_api_key: str | None = Header(default=None),
):
    require_api_key(x_vpo_api_key)
    items = load_source_monitor_config()
    found = False
    now = datetime.now().isoformat(timespec="seconds")

    for item in items:
        if item.get("id") != monitor_id:
            continue
        found = True
        update_data = request.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                item[key] = value
        item["updated_at"] = now
        break

    if not found:
        raise HTTPException(status_code=404, detail="Source monitor item not found.")

    save_source_monitor_config(items)
    return {"ok": True, "item": next(item for item in items if item.get("id") == monitor_id)}


@app.post("/source-monitor/{monitor_id}/process")
def process_source_monitor(
    monitor_id: str,
    x_vpo_api_key: str | None = Header(default=None),
):
    require_api_key(x_vpo_api_key)
    before = get_source_monitor_item(monitor_id)
    if not before:
        raise HTTPException(status_code=404, detail="Source monitor item not found.")

    source = before["source"]
    account = before["account"]
    pending_files = before["unprocessed_raw_files"]
    scripts = source_monitor_pipeline_scripts(source)
    if not scripts:
        raise HTTPException(status_code=400, detail=f"No hay pipeline nuevo configurado para {source}.")

    script_results = []
    for script_name in scripts:
        result = run_pipeline_script(script_name)
        script_results.append(result)
        if result["returncode"] != 0:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": f"Fallo {script_name}.",
                    "before": before,
                    "scripts": script_results,
                },
            )

    after = get_source_monitor_item(monitor_id)
    standardized_after_path = BASE / "warehouse" / "marts" / STANDARDIZED_FILE
    processed_summary = statement_summary_for_files(
        standardized_path=standardized_after_path,
        source=source,
        account=account,
        file_names=pending_files,
    )

    return {
        "ok": True,
        "processed_at": datetime.now().isoformat(timespec="seconds"),
        "display_name": before["display_name"],
        "source": source,
        "account": account,
        "pending_files_before": pending_files,
        "last_statement_before": before["last_statement_period"],
        "last_statement_after": after["last_statement_period"] if after else None,
        "pending_files_after": after["unprocessed_raw_files"] if after else [],
        "summary": processed_summary,
        "total_rows": sum(int(row.get("rows") or 0) for row in processed_summary),
        "total_amount_usd": sum(float(row.get("amount_usd") or 0) for row in processed_summary),
        "scripts": script_results,
    }


def royalty_report_scope_label(source: str | None, account: str | None) -> str:
    source = (source or "").strip().lower() or None
    account = (account or "").strip().lower() or None
    policy = load_distributor_policy_document()
    matching_policy = next(
        (
            entry
            for entry in policy.get("entries", [])
            if str(entry.get("source") or "").strip().lower() == source
            and str(entry.get("account") or "").strip().lower() == account
        ),
        None,
    )
    if source and account:
        return str((matching_policy or {}).get("display_name") or "").strip() or (
            f"{source.upper()} / {account.replace('_', ' ').title()}"
        )
    if source:
        return source.upper()
    return "Todas las distribuidoras"


def upload_report_job_artifact(job_id: int, output_path: Path, content_type: str) -> str:
    if not GCS_BUCKET:
        raise RuntimeError("GCS_BUCKET no esta configurado para guardar el reporte.")
    object_path = f"{VPO_REPORT_RESULTS_PREFIX}/{job_id}/{output_path.name}"
    client = gcs_client()
    blob = client.bucket(GCS_BUCKET).blob(object_path)
    blob.upload_from_filename(str(output_path), content_type=content_type)
    return f"gs://{GCS_BUCKET}/{object_path}"


def materialize_report_job_artifact(job_id: int) -> tuple[Path, str, str]:
    artifact = get_report_job_artifact(job_id)
    if artifact is None or artifact.get("status") != "completed":
        raise HTTPException(status_code=409, detail="El reporte todavia no esta listo.")
    output_uri = str(artifact.get("output_uri") or "")
    if not output_uri.startswith("gs://"):
        raise HTTPException(status_code=500, detail="El reporte no tiene un archivo persistido valido.")
    bucket_name, _, object_path = output_uri[5:].partition("/")
    if not bucket_name or not object_path:
        raise HTTPException(status_code=500, detail="La ubicacion del reporte es invalida.")
    filename = Path(str(artifact.get("result_filename") or Path(object_path).name)).name
    content_type = str(artifact.get("result_content_type") or "application/octet-stream")
    local_dir = VPO_API_REPORTS_DIR / "completed" / str(job_id)
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / filename
    if not local_path.exists():
        client = gcs_client()
        blob = client.bucket(bucket_name).blob(object_path)
        if not blob.exists(client):
            raise HTTPException(status_code=410, detail="El archivo del reporte ya no esta disponible.")
        blob.download_to_filename(str(local_path))
    return local_path, filename, content_type


def build_royalty_report_job(job: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    job_id = int(job["id"])
    output_format = str(job.get("output_format") or "excel")
    params = dict(job.get("params") or {})
    keywords = normalize_keywords(params.get("keywords") or [])
    start_month = params.get("start_month") or None
    end_month = params.get("end_month") or None
    period_basis = params.get("period_basis") or "transaction_month"
    mode = params.get("mode") or "any"
    raw_limit = max(0, min(int(params.get("raw_limit") or 0), 50000))
    refresh_cache = bool(params.get("refresh_cache"))
    source = (params.get("source") or "").strip().lower() or None
    account = (params.get("account") or "").strip().lower() or None

    if start_month and end_month and start_month > end_month:
        raise ValueError("El periodo desde no puede ser mayor que hasta.")
    if output_format in {"excel", "google_sheet"} and not keywords:
        raise ValueError("El reporte requiere al menos una palabra clave.")

    set_report_job_stage(job_id, "reading_data")
    marts = ensure_marts(
        refresh_cache=refresh_cache,
        filenames=[SONG_FILE, STANDARDIZED_FILE, CATALOG_MASTER_FILE],
    )
    configure_catalog_report_env(marts)
    set_report_job_stage(job_id, "building")

    if output_format == "excel":
        output_path = build_report(
            keywords=keywords,
            mode=mode,
            raw_limit=raw_limit,
            start_month=start_month,
            end_month=end_month,
            period_basis=period_basis,
            song_path=marts[SONG_FILE],
            standardized_path=marts[STANDARDIZED_FILE],
            output_dir=VPO_API_REPORTS_DIR,
        )
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        tables = build_report_tables(
            keywords=keywords,
            mode=mode,
            raw_limit=raw_limit if output_format == "google_sheet" else 0,
            start_month=start_month,
            end_month=end_month,
            period_basis=period_basis,
            song_path=marts[SONG_FILE],
            standardized_path=marts[STANDARDIZED_FILE],
            source=source if output_format == "executive_pdf" else None,
            account=account if output_format == "executive_pdf" else None,
        )
        if output_format == "google_sheet":
            spreadsheet_url = create_google_sheet(
                tables=tables,
                keywords=keywords,
                start_month=start_month,
                end_month=end_month,
            )
            return None, None, None, spreadsheet_url
        output_path = build_executive_royalty_pdf(
            tables=tables,
            output_dir=VPO_API_REPORTS_DIR,
            scope_label=royalty_report_scope_label(source, account),
            keywords=keywords,
            period_basis=period_basis,
            start_month=start_month,
            end_month=end_month,
        )
        content_type = "application/pdf"

    set_report_job_stage(job_id, "uploading")
    output_uri = upload_report_job_artifact(job_id, output_path, content_type)
    filename = output_path.name
    try:
        output_path.unlink(missing_ok=True)
    except OSError:
        pass
    return output_uri, filename, content_type, None


def execute_royalty_report_job(job_id: int) -> dict[str, Any] | None:
    job = claim_report_job(job_id)
    if job is None:
        return get_report_job(job_id)
    try:
        output_uri, filename, content_type, result_url = build_royalty_report_job(job)
        complete_report_job(
            job_id,
            output_uri=output_uri,
            filename=filename,
            content_type=content_type,
            result_url=result_url,
        )
    except Exception as exc:
        fail_report_job(job_id, str(exc))
    return get_report_job(job_id)


def execute_local_royalty_report_job(job_id: int) -> None:
    with LOCAL_REPORT_JOB_LOCK:
        execute_royalty_report_job(job_id)


def require_report_job_access(username: str, job: dict[str, Any], action: Literal["access", "create"] = "access") -> dict:
    with operational_connect() as conn:
        permission = require_module_permission(conn, username, "royalty_reports", action)
    if not permission.get("is_admin") and str(job.get("requested_by") or "").casefold() != username.casefold():
        raise HTTPException(status_code=403, detail="No tenes permiso para ver este reporte.")
    return permission


@app.post("/reports/jobs", status_code=202)
def create_royalty_report_job(
    request: RoyaltyReportJobRequest,
    http_request: Request,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    username = clean_username(x_vpo_username or "")
    if not username:
        raise HTTPException(status_code=401, detail="Usuario requerido.")
    with operational_connect() as conn:
        require_module_permission(conn, username, "royalty_reports", "create")

    params = request.model_dump(exclude={"output"})
    params["keywords"] = normalize_keywords(params.get("keywords") or [])
    if request.output in {"excel", "google_sheet"} and not params["keywords"]:
        raise HTTPException(status_code=400, detail="Ingresa al menos una palabra clave.")
    if request.start_month and request.end_month and request.start_month > request.end_month:
        raise HTTPException(status_code=400, detail="El periodo desde no puede ser mayor que hasta.")

    report_key = {
        "excel": "royalty_keyword",
        "executive_pdf": "royalty_executive",
        "google_sheet": "royalty_google_sheet",
    }[request.output]
    job, created = create_or_reuse_report_job(
        requested_by=username,
        report_key=report_key,
        output_format=request.output,
        params=params,
    )
    if created:
        try:
            if cloud_tasks_enabled():
                worker_base_url = VPO_REPORT_WORKER_BASE_URL or str(http_request.base_url).rstrip("/")
                worker_url = f"{worker_base_url}/reports/jobs/{job['id']}/execute"
                task_name = enqueue_report_job(int(job["id"]), worker_url)
                set_report_job_task(int(job["id"]), task_name)
            else:
                thread = threading.Thread(
                    target=execute_local_royalty_report_job,
                    args=(int(job["id"]),),
                    daemon=True,
                    name=f"royalty-report-{job['id']}",
                )
                thread.start()
                set_report_job_task(int(job["id"]), f"local:{thread.name}")
        except Exception as exc:
            fail_report_job(int(job["id"]), f"No se pudo encolar el reporte: {exc}")
            raise HTTPException(status_code=500, detail="No se pudo iniciar el reporte.") from exc
    return {"item": get_report_job(int(job["id"])), "reused": not created}


@app.get("/reports/jobs")
def recent_royalty_report_jobs(
    limit: int = 10,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    username = clean_username(x_vpo_username or "")
    if not username:
        raise HTTPException(status_code=401, detail="Usuario requerido.")
    with operational_connect() as conn:
        permission = require_module_permission(conn, username, "royalty_reports", "access")
    requested_by = None if permission.get("is_admin") else username
    return {"items": list_report_jobs(requested_by, limit=limit)}


@app.get("/reports/jobs/{job_id}")
def royalty_report_job_status(
    job_id: int,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    username = clean_username(x_vpo_username or "")
    if not username:
        raise HTTPException(status_code=401, detail="Usuario requerido.")
    job = get_report_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Reporte no encontrado.")
    require_report_job_access(username, job)
    return {"item": job}


@app.get("/reports/jobs/{job_id}/download")
def royalty_report_job_download(
    job_id: int,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> FileResponse:
    require_api_key(x_vpo_api_key)
    username = clean_username(x_vpo_username or "")
    if not username:
        raise HTTPException(status_code=401, detail="Usuario requerido.")
    job = get_report_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Reporte no encontrado.")
    require_report_job_access(username, job)
    local_path, filename, content_type = materialize_report_job_artifact(job_id)
    return FileResponse(path=local_path, media_type=content_type, filename=filename)


@app.post("/reports/jobs/{job_id}/execute")
def royalty_report_job_worker(
    job_id: int,
    x_vpo_worker_token: str | None = Header(default=None),
) -> dict:
    expected = os.environ.get("VPO_REPORT_WORKER_TOKEN", "").strip()
    supplied = (x_vpo_worker_token or "").strip()
    if not expected or not supplied or not secrets.compare_digest(expected, supplied):
        raise HTTPException(status_code=403, detail="Worker no autorizado.")
    item = execute_royalty_report_job(job_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Reporte no encontrado.")
    return {"item": item}


@app.post("/reports/keyword")
def keyword_report(
    request: KeywordReportRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> FileResponse:
    require_api_key(x_vpo_api_key)

    if request.start_month and request.end_month and request.start_month > request.end_month:
        raise HTTPException(status_code=400, detail="start_month cannot be greater than end_month.")

    keywords = normalize_keywords(request.keywords)
    if not keywords:
        raise HTTPException(status_code=400, detail="At least one keyword is required.")

    marts = ensure_marts(refresh_cache=request.refresh_cache, filenames=[SONG_FILE, STANDARDIZED_FILE, CATALOG_MASTER_FILE])
    configure_catalog_report_env(marts)

    output_path = build_report(
        keywords=keywords,
        mode=request.mode,
        raw_limit=request.raw_limit,
        start_month=request.start_month,
        end_month=request.end_month,
        period_basis=request.period_basis,
        song_path=marts[SONG_FILE],
        standardized_path=marts[STANDARDIZED_FILE],
        output_dir=VPO_API_REPORTS_DIR,
    )

    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=output_path.name,
    )


@app.get("/reports/royalty/options")
def royalty_report_options(
    refresh_cache: bool = False,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    marts = ensure_marts(refresh_cache=refresh_cache, filenames=[SONG_FILE])
    base = pl.scan_parquet(marts[SONG_FILE])
    available = (
        base
        .select(["source", "account"])
        .filter(
            pl.col("source").is_not_null()
            & (pl.col("source").cast(pl.Utf8).str.strip_chars() != "")
            & pl.col("account").is_not_null()
            & (pl.col("account").cast(pl.Utf8).str.strip_chars() != "")
        )
        .unique()
        .sort(["source", "account"])
        .collect()
        .to_dicts()
    )
    policy = load_distributor_policy_document()
    display_names = {
        (
            str(entry.get("source") or "").strip().lower(),
            str(entry.get("account") or "").strip().lower(),
        ): str(entry.get("display_name") or "").strip()
        for entry in policy.get("entries", [])
    }
    source_accounts = []
    for row in available:
        source = str(row.get("source") or "").strip()
        account = str(row.get("account") or "").strip()
        source_accounts.append({
            "source": source,
            "account": account,
            "display_name": display_names.get((source.lower(), account.lower()))
            or f"{source.upper()} / {account.replace('_', ' ').title()}",
        })
    return {
        "sources": sorted({item["source"] for item in source_accounts}),
        "source_accounts": source_accounts,
    }


@app.post("/reports/executive")
def executive_royalty_report(
    request: ExecutiveRoyaltyReportRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> FileResponse:
    require_api_key(x_vpo_api_key)
    if request.start_month and request.end_month and request.start_month > request.end_month:
        raise HTTPException(status_code=400, detail="start_month cannot be greater than end_month.")

    keywords = normalize_keywords(request.keywords)
    marts = ensure_marts(
        refresh_cache=request.refresh_cache,
        filenames=[SONG_FILE, STANDARDIZED_FILE, CATALOG_MASTER_FILE],
    )
    configure_catalog_report_env(marts)

    policy = load_distributor_policy_document()
    source = (request.source or "").strip().lower() or None
    account = (request.account or "").strip().lower() or None
    matching_policy = next(
        (
            entry
            for entry in policy.get("entries", [])
            if str(entry.get("source") or "").strip().lower() == source
            and str(entry.get("account") or "").strip().lower() == account
        ),
        None,
    )
    if source and account:
        scope_label = str((matching_policy or {}).get("display_name") or "").strip()
        if not scope_label:
            scope_label = f"{source.upper()} / {account.replace('_', ' ').title()}"
    elif source:
        scope_label = source.upper()
    else:
        scope_label = "Todas las distribuidoras"

    tables = build_report_tables(
        keywords=keywords,
        mode=request.mode,
        raw_limit=0,
        start_month=request.start_month,
        end_month=request.end_month,
        period_basis=request.period_basis,
        song_path=marts[SONG_FILE],
        standardized_path=marts[STANDARDIZED_FILE],
        source=source,
        account=account,
    )
    try:
        output_path = build_executive_royalty_pdf(
            tables=tables,
            output_dir=VPO_API_REPORTS_DIR,
            scope_label=scope_label,
            keywords=keywords,
            period_basis=request.period_basis,
            start_month=request.start_month,
            end_month=request.end_month,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileResponse(
        path=output_path,
        media_type="application/pdf",
        filename=output_path.name,
    )


@app.get("/reports/keyword-download")
def keyword_report_download(
    keywords: str,
    expires: int,
    sig: str,
    start_month: str = "",
    end_month: str = "",
    period_basis: Literal["transaction_month", "statement_period"] = "transaction_month",
    mode: Literal["any", "all"] = "any",
    raw_limit: int = 5000,
    refresh_cache: bool = False,
) -> FileResponse:
    require_valid_report_signature(
        keywords=keywords,
        start_month=start_month,
        end_month=end_month,
        period_basis=period_basis,
        mode=mode,
        raw_limit=raw_limit,
        refresh_cache=refresh_cache,
        expires=expires,
        sig=sig,
    )

    if start_month and end_month and start_month > end_month:
        raise HTTPException(status_code=400, detail="start_month cannot be greater than end_month.")

    normalized_keywords = normalize_keywords([keywords])
    if not normalized_keywords:
        raise HTTPException(status_code=400, detail="At least one keyword is required.")

    marts = ensure_marts(refresh_cache=refresh_cache, filenames=[SONG_FILE, STANDARDIZED_FILE, CATALOG_MASTER_FILE])
    configure_catalog_report_env(marts)

    output_path = build_report(
        keywords=normalized_keywords,
        mode=mode,
        raw_limit=raw_limit,
        start_month=start_month or None,
        end_month=end_month or None,
        period_basis=period_basis,
        song_path=marts[SONG_FILE],
        standardized_path=marts[STANDARDIZED_FILE],
        output_dir=VPO_API_REPORTS_DIR,
    )

    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=output_path.name,
    )


@app.post("/reports/statement")
def statement_report(
    request: StatementReportRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> FileResponse:
    require_api_key(x_vpo_api_key)
    marts = ensure_marts(refresh_cache=request.refresh_cache, filenames=[STATEMENT_SUMMARY_FILE, STANDARDIZED_FILE, CATALOG_MASTER_FILE])
    configure_catalog_report_env(marts)
    VPO_API_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    version_suffix = "nuevo" if request.report_version == "new" else "historico"
    output_path = VPO_API_REPORTS_DIR / f"reporte_ingresos_por_statement_marts_{version_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    output_path = build_statement_report_from_mart(
        standardized_path=marts[STANDARDIZED_FILE],
        output_path=output_path,
        min_artist_total_usd=request.min_artist_total_usd,
        include_zero_total_artists=request.include_zero_total_artists,
        report_version=request.report_version,
    )

    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=output_path.name,
    )


@app.get("/reports/custom/options")
def custom_report_options(
    refresh_cache: bool = False,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    marts = ensure_marts(refresh_cache=refresh_cache, filenames=[STANDARDIZED_FILE])
    try:
        source_accounts_df = (
            pl.scan_parquet(marts[STANDARDIZED_FILE])
            .select(
                [
                    pl.col("source").cast(pl.Utf8, strict=False).str.to_lowercase().alias("source"),
                    pl.col("account").cast(pl.Utf8, strict=False).str.to_lowercase().alias("account"),
                ]
            )
            .drop_nulls()
            .unique()
            .sort(["source", "account"])
            .collect()
        )
        source_accounts = source_accounts_df.to_dicts()
        sources = sorted({row["source"] for row in source_accounts})
    except Exception:
        sources = []
        source_accounts = []

    return {
        "templates": CUSTOM_REPORT_TEMPLATES,
        "sources": sources,
        "source_accounts": source_accounts,
    }


@app.post("/reports/custom/title-list")
def custom_title_report(
    request: CustomRoyaltyReportRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> FileResponse:
    require_api_key(x_vpo_api_key)

    if request.start_month and request.end_month and request.start_month > request.end_month:
        raise HTTPException(status_code=400, detail="start_month cannot be greater than end_month.")

    if request.template_key == "gusty_fuga_contracts":
        marts = ensure_marts(refresh_cache=request.refresh_cache, filenames=[STANDARDIZED_FILE, CATALOG_MASTER_FILE])
        configure_catalog_report_env(marts)
        output_path = build_fuga_gusty_contract_report(
            start_month=request.start_month,
            end_month=request.end_month,
            raw_path=marts[STANDARDIZED_FILE],
            output_dir=VPO_API_REPORTS_DIR,
        )
        return FileResponse(
            path=output_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=output_path.name,
        )

    if request.template_key == "la_nueva_sangre":
        end_month = request.end_month or "2026-03"
        marts = ensure_marts(
            refresh_cache=request.refresh_cache,
            filenames=[
                STANDARDIZED_ONERPM_FILE,
                STANDARDIZED_FUGA_FILE,
                CATALOG_RELEASE_METADATA_FILE,
                CATALOG_MASTER_FILE,
            ],
        )
        configure_catalog_report_env(marts)
        la_nueva_sangre_report.STANDARDIZED_ONERPM_PATH = marts[STANDARDIZED_ONERPM_FILE]
        la_nueva_sangre_report.STANDARDIZED_FUGA_PATH = marts[STANDARDIZED_FUGA_FILE]
        la_nueva_sangre_report.CATALOG_RELEASE_METADATA_PATH = marts[CATALOG_RELEASE_METADATA_FILE]
        la_nueva_sangre_report.CATALOG_MASTER_PATH = marts[CATALOG_MASTER_FILE]
        la_nueva_sangre_report.REPORTS_DIR = VPO_API_REPORTS_DIR
        rows = la_nueva_sangre_report.classified_rows(end_month)
        if request.exclude_related_videos:
            rows = la_nueva_sangre_report.apply_related_video_exclusions(rows)
        output_path = la_nueva_sangre_report.write_report(
            rows,
            end_month,
            hide_zero_amounts=request.hide_zero_amounts,
        )
        return FileResponse(
            path=output_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=output_path.name,
        )

    if request.template_key == "la_juntada_artistas":
        marts = ensure_marts(
            refresh_cache=request.refresh_cache,
            filenames=[STANDARDIZED_FILE, CATALOG_MASTER_FILE],
        )
        la_juntada_report.RAW_ALL_PATH = marts[STANDARDIZED_FILE]
        la_juntada_report.CATALOG_MASTER_PATH = marts[CATALOG_MASTER_FILE]
        output_path = la_juntada_report.build_report(
            output_dir=VPO_API_REPORTS_DIR,
            end_month=request.end_month or None,
        )
        return FileResponse(
            path=output_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=output_path.name,
        )

    terms = [term.strip() for term in request.terms if str(term or "").strip()]
    if not terms:
        raise HTTPException(status_code=400, detail="La lista de busqueda no puede estar vacia.")

    marts = ensure_marts(refresh_cache=request.refresh_cache, filenames=[SONG_FILE, STANDARDIZED_FILE, CATALOG_MASTER_FILE])
    configure_catalog_report_env(marts)
    output_path = build_custom_title_report(
        report_title=request.report_title,
        terms=terms,
        start_month=request.start_month,
        end_month=request.end_month,
        sources=request.sources or None,
        source_accounts=request.source_accounts or None,
        song_path=marts[SONG_FILE],
        raw_path=marts[STANDARDIZED_FILE],
        output_dir=VPO_API_REPORTS_DIR,
    )

    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=output_path.name,
    )


@app.post("/reports/google-sheet")
def keyword_google_sheet(
    request: KeywordReportRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict[str, str]:
    require_api_key(x_vpo_api_key)

    if request.start_month and request.end_month and request.start_month > request.end_month:
        raise HTTPException(status_code=400, detail="start_month cannot be greater than end_month.")

    keywords = normalize_keywords(request.keywords)
    if not keywords:
        raise HTTPException(status_code=400, detail="At least one keyword is required.")

    marts = ensure_marts(refresh_cache=request.refresh_cache, filenames=[SONG_FILE, STANDARDIZED_FILE, CATALOG_MASTER_FILE])
    configure_catalog_report_env(marts)

    tables = build_report_tables(
        keywords=keywords,
        mode=request.mode,
        raw_limit=request.raw_limit,
        start_month=request.start_month,
        end_month=request.end_month,
        period_basis=request.period_basis,
        song_path=marts[SONG_FILE],
        standardized_path=marts[STANDARDIZED_FILE],
    )

    try:
        spreadsheet_url = create_google_sheet(
            tables=tables,
            keywords=keywords,
            start_month=request.start_month,
            end_month=request.end_month,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Google Sheet generation failed: {exc}") from exc

    return {"url": spreadsheet_url}


@app.get("/participation/distributors")
def distributor_participation(
    refresh_cache: bool = False,
    preset: ParticipationPreset = "last_year",
    start_month: str | None = None,
    end_month: str | None = None,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    marts = ensure_marts(refresh_cache=refresh_cache, filenames=[SONG_FILE])
    base = pl.scan_parquet(marts[SONG_FILE]).filter(pl.col("transaction_month").is_not_null())
    schema = set(base.collect_schema().names())
    if "include_in_statement_view" in schema:
        base = base.filter(pl.col("include_in_statement_view").cast(pl.Boolean, strict=False).fill_null(True))

    month_bounds = (
        base
        .select([
            pl.min("transaction_month").alias("min_month"),
            pl.max("transaction_month").alias("max_month"),
        ])
        .collect()
    )

    available_start = month_bounds["min_month"][0]
    available_end = month_bounds["max_month"][0]

    if not available_end:
        return {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "preset": preset,
            "start_month": None,
            "end_month": None,
            "start_date": None,
            "end_date": None,
            "available_start_month": None,
            "available_end_month": None,
            "total_amount_usd": 0.0,
            "items": [],
            "account_items": [],
        }

    report_end_month = min(previous_calendar_month(), available_end)

    if preset == "custom":
        effective_start = start_month or available_start
        effective_end = end_month or report_end_month
    elif preset == "last_month":
        effective_start = report_end_month
        effective_end = report_end_month
    elif preset == "last_3_months":
        effective_start = shift_month(report_end_month, -2)
        effective_end = report_end_month
    elif preset == "all_history":
        effective_start = available_start
        effective_end = report_end_month
    else:
        effective_start = shift_month(report_end_month, -11)
        effective_end = report_end_month

    effective_start = max(effective_start, available_start)
    effective_end = min(effective_end, available_end)

    if effective_start > effective_end:
        raise HTTPException(status_code=400, detail="start_month cannot be greater than end_month.")

    period_base = (
        base
        .filter(pl.col("transaction_month") >= effective_start)
        .filter(pl.col("transaction_month") <= effective_end)
    )

    df = (
        period_base
        .group_by("source")
        .agg(pl.sum("amount_usd").alias("amount_usd"))
        .sort("amount_usd", descending=True)
        .collect()
    )

    account_df = (
        period_base
        .group_by(["source", "account"])
        .agg(pl.sum("amount_usd").alias("amount_usd"))
        .sort(["source", "amount_usd"], descending=[False, True])
        .collect()
    )

    total = float(df["amount_usd"].sum()) if df.height else 0.0

    items = []
    for row in df.iter_rows(named=True):
        amount = float(row["amount_usd"] or 0)
        items.append({
            "source": row["source"],
            "amount_usd": amount,
            "percentage": (amount / total * 100) if total else 0,
        })

    account_items = []
    for row in account_df.iter_rows(named=True):
        amount = float(row["amount_usd"] or 0)
        account_items.append({
            "source": row["source"],
            "account": row["account"],
            "amount_usd": amount,
            "percentage": (amount / total * 100) if total else 0,
        })

    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "preset": preset,
        "start_month": effective_start,
        "end_month": effective_end,
        "start_date": first_business_day(effective_start),
        "end_date": last_business_day(effective_end),
        "available_start_month": available_start,
        "available_end_month": available_end,
        "total_amount_usd": total,
        "items": items,
        "account_items": account_items,
    }


@app.get("/config/distributor-overview")
def distributor_config_overview(
    x_vpo_api_key: str | None = Header(default=None),
):
    require_api_key(x_vpo_api_key)
    policies = load_config_seed("distributor-account-policies")
    dictionary = load_config_seed("statement-source-dictionary")
    cutoffs = load_config_seed("contract-cutoffs")
    templates = load_config_seed("report-templates")
    catalog_stats = catalog_stats_by_account(refresh_cache=False)
    account_impact_stats = account_impact_stats_by_account(refresh_cache=False)
    rule_previews = account_rule_preview_by_account(cutoffs.get("entries", []), refresh_cache=False)

    dictionary_entries = dictionary.get("entries", [])
    cutoff_by_id = {
        item.get("cutoff_id"): item
        for item in cutoffs.get("entries", [])
        if item.get("cutoff_id")
    }

    accounts = []
    for policy in policies.get("entries", []):
        source = policy.get("source")
        account = policy.get("account")
        policy_with_defaults = {
            **policy,
            "report_net_adjustment_pct": float(policy.get("report_net_adjustment_pct") or 0.0),
        }
        related_dictionary = [
            item for item in dictionary_entries
            if item.get("source") == source and item.get("account") in {account, "*"}
        ]
        contract_cutoff_id = policy.get("contract_cutoff_id")
        accounts.append({
            **policy_with_defaults,
            "statement_dictionary": related_dictionary,
            "contract_cutoff": cutoff_by_id.get(contract_cutoff_id),
            "account_impact_stats": account_impact_stats.get((str(source), str(account)), {
                "rows": 0,
                "works": 0,
                "amount_usd": 0.0,
                "units": 0.0,
                "first_transaction_month": None,
                "last_transaction_month": None,
                "sheet_breakdown": [],
            }),
            "rule_preview": rule_previews.get((str(source), str(account)), {
                "enabled": False,
                "cutoff_id": contract_cutoff_id,
                "summary": [],
                "items": [],
            }),
            "catalog_stats": catalog_stats.get((str(source), str(account)), {
                "works": 0,
                "active": 0,
                "inactive": 0,
                "excluded_from_reports": 0,
                "release_dates": 0,
                "missing_release_dates": 0,
                "labels": 0,
                "missing_labels": 0,
                "amount_usd": 0.0,
                "first_transaction_month": None,
                "last_transaction_month": None,
            }),
        })

    source_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    for account in accounts:
        source_counts[str(account.get("source") or "unknown")] = source_counts.get(str(account.get("source") or "unknown"), 0) + 1
        type_counts[str(account.get("account_type") or "unknown")] = type_counts.get(str(account.get("account_type") or "unknown"), 0) + 1

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": policies.get("mode", "production_policy"),
        "policy_version": policies.get("policy_version"),
        "report_personalization": policies.get("report_personalization", {
            "enabled": False,
            "amount_basis": "net_amount_after_distributor",
        }),
        "accounts": accounts,
        "statement_dictionary": dictionary_entries,
        "contract_cutoffs": cutoffs.get("entries", []),
        "report_templates": templates.get("entries", []),
        "summary": {
            "accounts": len(accounts),
            "dictionary_entries": len(dictionary_entries),
            "contract_cutoffs": len(cutoffs.get("entries", [])),
            "report_templates": len(templates.get("entries", [])),
            "sources": source_counts,
            "account_types": type_counts,
            "catalog_works": sum(int(item.get("catalog_stats", {}).get("works", 0) or 0) for item in accounts),
        },
    }


@app.patch("/config/distributor-account-policies/personalization")
def update_distributor_personalization(
    request: DistributorPersonalizationRequest,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
):
    require_api_key(x_vpo_api_key)
    try:
        policies = update_report_personalization(
            enabled=bool(request.enabled),
            accounts=[account.model_dump() for account in request.accounts],
            updated_by=(x_vpo_username or "system").strip() or "system",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "ok": True,
        "report_personalization": policies["report_personalization"],
        "policy_version": policies["policy_version"],
        "updated_at": policies["updated_at"],
        "accounts_updated": len(request.accounts),
    }


@app.get("/config/{config_name}")
def config_seed(
    config_name: Literal[
        "distributor-account-policies",
        "statement-source-dictionary",
        "contract-cutoffs",
        "report-templates",
    ],
    x_vpo_api_key: str | None = Header(default=None),
):
    require_api_key(x_vpo_api_key)
    return load_config_seed(config_name)


@app.get("/catalog")
def catalog_items(
    source: str | None = None,
    account: str | None = None,
    artist: str | None = None,
    keyword: str | None = None,
    label: str | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
    status: Literal["active", "inactive", "all"] = "active",
    limit: int = 50,
    offset: int = 0,
    refresh_cache: bool = False,
    x_vpo_api_key: str | None = Header(default=None),
):
    require_api_key(x_vpo_api_key)
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))

    marts = ensure_marts(refresh_cache=refresh_cache, filenames=[CATALOG_MASTER_FILE])
    path = marts[CATALOG_MASTER_FILE]
    if not path.exists():
        raise HTTPException(status_code=500, detail=f"No existe catalog master: {path}")

    catalog = pl.read_parquet(path)
    if "external_label" not in catalog.columns:
        catalog = catalog.with_columns(pl.lit(None).cast(pl.Utf8).alias("external_label"))
    if "label_normalized_auto" not in catalog.columns:
        catalog = catalog.with_columns(
            normalized_label_expr(pl.col("external_label")).alias("label_normalized_auto")
        )
    if "label_normalized" not in catalog.columns:
        catalog = catalog.with_columns(
            pl.coalesce(["label_normalized_auto", "external_label"]).alias("label_normalized")
        )
    status_df = load_catalog_status()
    if status_df.is_empty():
        catalog = catalog.with_columns([
            pl.lit(True).alias("active"),
            pl.lit(True).alias("include_in_reports"),
            pl.lit("vpo_catalog").alias("catalog_business_status"),
            pl.lit(None).cast(pl.Utf8).alias("status_notes"),
            pl.lit(None).cast(pl.Utf8).alias("label_normalized_override"),
            pl.lit(None).cast(pl.Utf8).alias("status_updated_at"),
        ])
    else:
        catalog = (
            catalog
            .join(
                status_df.rename({"updated_at": "status_updated_at"}),
                on="catalog_key",
                how="left",
            )
            .with_columns([
                pl.col("active").fill_null(True),
                (
                    pl.col("include_in_reports").fill_null(pl.col("active")).fill_null(True)
                    if "include_in_reports" in status_df.columns
                    else pl.col("active").fill_null(True)
                ).alias("include_in_reports"),
                (
                    pl.col("catalog_business_status").fill_null("vpo_catalog")
                    if "catalog_business_status" in status_df.columns
                    else pl.lit("vpo_catalog")
                ).alias("catalog_business_status"),
                pl.col("status_notes").cast(pl.Utf8, strict=False),
                pl.col("label_normalized_override").cast(pl.Utf8, strict=False),
                pl.col("status_updated_at").cast(pl.Utf8, strict=False),
            ])
        )
    catalog = catalog.with_columns([
        pl.when(pl.col("label_normalized_override").str.strip_chars() == "")
        .then(pl.lit(None).cast(pl.Utf8))
        .otherwise(pl.col("label_normalized_override").str.strip_chars())
        .alias("label_normalized_override"),
    ]).with_columns([
        pl.coalesce(["label_normalized_override", "label_normalized_auto", "external_label"]).alias("label_normalized"),
    ])

    def split_values(series_name: str) -> list[str]:
        values: set[str] = set()
        if series_name not in catalog.columns:
            return []
        for raw in catalog.get_column(series_name).drop_nulls().to_list():
            for part in str(raw).split(" | "):
                value = part.strip()
                if value:
                    values.add(value)
        return sorted(values, key=lambda item: item.casefold())

    options = {
        "sources": split_values("sources"),
        "accounts": split_values("accounts"),
        "artists": sorted(
            [
                str(value)
                for value in catalog.get_column("artist_statement").drop_nulls().unique().to_list()
                if str(value).strip()
            ],
            key=lambda item: item.casefold(),
        ),
        "labels": sorted(
            [
                str(value)
                for value in catalog.get_column("label_normalized").drop_nulls().unique().to_list()
                if str(value).strip()
            ],
            key=lambda item: item.casefold(),
        ) if "label_normalized" in catalog.columns else [],
        "first_month": catalog.get_column("first_transaction_month").drop_nulls().min(),
        "last_month": catalog.get_column("last_transaction_month").drop_nulls().max(),
    }

    filtered = catalog.lazy()
    if source:
        filtered = filtered.filter(pl.col("sources").fill_null("").str.contains(source, literal=True))
    if account:
        filtered = filtered.filter(pl.col("accounts").fill_null("").str.contains(account, literal=True))
    if artist:
        needle = normalize_search_text(artist)
        filtered = filtered.filter(
            contains_search_expr(pl.col("artist_statement"), needle)
            | contains_search_expr(pl.col("artist_variants"), needle)
        )
    if keyword:
        needle = normalize_search_text(keyword)
        if needle:
            filtered = filtered.filter(
                contains_search_expr(pl.col("track_title"), needle)
                | contains_search_expr(pl.col("artist_statement"), needle)
                | contains_search_expr(pl.col("asset_isrc"), needle)
                | contains_search_expr(pl.col("title_variants"), needle)
                | contains_search_expr(pl.col("artist_variants"), needle)
            )
    if label:
        clean_label = label.strip()
        if clean_label == "__missing__":
            filtered = filtered.filter(
                pl.col("label_normalized").is_null()
                | (pl.col("label_normalized").cast(pl.Utf8, strict=False).str.strip_chars() == "")
            )
        elif clean_label:
            filtered = filtered.filter(
                pl.col("label_normalized").fill_null("").str.strip_chars() == clean_label
            )
    if start_month:
        filtered = filtered.filter(pl.col("last_transaction_month").fill_null("") >= start_month)
    if end_month:
        filtered = filtered.filter(pl.col("first_transaction_month").fill_null("") <= end_month)
    if status == "active":
        filtered = filtered.filter(pl.col("active") == True)
    elif status == "inactive":
        filtered = filtered.filter(pl.col("active") == False)

    total = filtered.select(pl.len().alias("total")).collect()["total"][0]
    totals = filtered.select([
        pl.sum("amount_usd").round(2).alias("amount_usd"),
        pl.sum("units").round(2).alias("units"),
    ]).collect().to_dicts()[0]
    items = (
        filtered
        .sort("amount_usd", descending=True)
        .slice(offset, limit)
        .collect()
        .to_dicts()
    )

    return {
        "items": items,
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "totals": totals,
        "options": options,
    }


@app.patch("/catalog/status")
def update_catalog_status(
    request: CatalogStatusRequest,
    x_vpo_api_key: str | None = Header(default=None),
):
    require_api_key(x_vpo_api_key)
    catalog_key = request.catalog_key.strip()
    if not catalog_key:
        raise HTTPException(status_code=400, detail="catalog_key vacio.")

    now = datetime.now().isoformat(timespec="seconds")
    status_df = load_catalog_status()
    existing_rows = [] if status_df.is_empty() else status_df.filter(pl.col("catalog_key") == catalog_key).to_dicts()
    existing_row = existing_rows[0] if existing_rows else {}
    request_fields = getattr(request, "model_fields_set", getattr(request, "__fields_set__", set()))
    label_override = existing_row.get("label_normalized_override")
    if "label_normalized_override" in request_fields:
        label_override = (request.label_normalized_override or "").strip() or None
    new_row = pl.DataFrame([{
        "catalog_key": catalog_key,
        "active": bool(request.active),
        "include_in_reports": bool(request.active if request.include_in_reports is None else request.include_in_reports),
        "catalog_business_status": request.business_status,
        "status_notes": (request.notes or "").strip() or None,
        "label_normalized_override": label_override,
        "updated_at": now,
    }])
    if status_df.is_empty():
        final = new_row
    else:
        final = pl.concat([
            status_df.filter(pl.col("catalog_key") != catalog_key),
            new_row,
        ], how="diagonal_relaxed")
    save_catalog_status(final)
    return {"ok": True, "catalog_key": catalog_key, "active": bool(request.active), "updated_at": now}


def build_royalties_dashboard_summary_mart(
    standardized_path: Path,
    refresh_cache: bool = False,
    *,
    output_path: Path | None = None,
    partition_large_input: bool = True,
) -> Path:
    target_path = output_path or ROYALTIES_DASHBOARD_SUMMARY_PATH
    if (
        not refresh_cache
        and target_path.exists()
        and target_path.stat().st_mtime >= standardized_path.stat().st_mtime
    ):
        return target_path

    if partition_large_input and standardized_path.stat().st_size > 256 * 1024 * 1024:
        return build_partitioned_royalties_dashboard_summary_mart(
            standardized_path=standardized_path,
            output_path=target_path,
        )

    lf = pl.scan_parquet(standardized_path)
    schema = lf.collect_schema()
    columns = set(schema.names())
    required_store_dimensions = {
        "dsp_normalized",
        "monetization_normalized",
        "content_origin_normalized",
        "classification_status",
        "store_report_label",
    }
    missing_store_dimensions = sorted(required_store_dimensions - columns)
    if missing_store_dimensions:
        raise ValueError(
            "El mart consolidado no cumple el contrato de Store/DSP normalizado. "
            f"Faltan: {', '.join(missing_store_dimensions)}"
        )
    needed_columns = {
        "source",
        "Fuente",
        "SOURCE",
        "account",
        "Cuenta",
        "ACCOUNT",
        "source_sheet",
        "sheet_name",
        "Sheet",
        "SHEET",
        "statement_type",
        "statement_kind",
        "statement_file_name",
        "mart_source_file",
        "source_file",
        "revenue_basis",
        "Base ingreso",
        "statement_period",
        "transaction_month",
        "amount_usd",
        "net_amount_usd",
        "net_amount",
        "units",
        "Units",
        "quantity",
        "Quantity",
        "Asset Quantity",
        "Product Quantity",
        "streams",
        "Streams",
        "views",
        "Views",
        "asset_isrc",
        "ISRC",
        "isrc",
        "Asset ISRC",
        "YouTube Asset ISRC",
        "product_upc",
        "UPC",
        "upc",
        "Product UPC",
        "DISPLAY UPC",
        "Display UPC",
        "MANUFACTURER UPC",
        "UPC Code",
        "video_id",
        "Video ID",
        "VideoId",
        "YOUTUBE VIDEO ID",
        "YouTube Video ID",
        "YouTube Asset ID",
        "ID",
        "Parent ID",
        "track_id",
        "artist_statement_style",
        "artist_best_available",
        "artist_name_statement",
        "track_artist_statement",
        "product_artist_statement",
        "asset_artist_statement",
        "Artist Name",
        "Artists",
        "Track Artists",
        "Track Artist",
        "TRACK ARTIST",
        "PRODUCT ARTIST",
        "Asset Artist",
        "Product Artist",
        "artists_raw",
        "payee",
        "Payee",
        "Channel Name",
        "track_statement_style",
        "asset_title_statement",
        "release_statement_style",
        "track_title",
        "Track Title",
        "TRACK",
        "Asset Title",
        "Product Title",
        "Title",
        "Video Title",
        "YouTube Video Title",
        "Album Title",
        "PRODUCT",
        "dsp",
        "DSP",
        "dsp_normalized",
        "monetization_normalized",
        "content_origin_normalized",
        "classification_status",
        "store_report_label",
        "store_name",
        "store_raw",
        "Store",
        "Sale Store Name",
        "STORE",
        "Shop",
        "Platform",
        "territory",
        "Territory",
        "COUNTRY",
        "Country",
        "Sale Country",
        "Region",
        "Sale Type",
        "use_type",
        "Use Type",
        "usage_type",
        "usage_raw",
        "Product Type",
        "label_normalized_statement_style",
        "label_normalized",
        "label_statement_style",
        "Label Name",
        "Product Label",
        "LABEL",
        "label",
    }
    selected_columns = [column for column in sorted(needed_columns) if column in columns]
    if selected_columns:
        lf = lf.select(selected_columns)
        columns = set(selected_columns)

    def text_expr(column_name: str) -> pl.Expr:
        if column_name not in columns:
            return pl.lit("")
        return pl.col(column_name).cast(pl.Utf8, strict=False).fill_null("").str.strip_chars()

    def non_empty_text_expr(column_name: str) -> pl.Expr:
        value = text_expr(column_name)
        return pl.when(value == "").then(None).otherwise(value)

    def coalesce_text_expr(column_names: list[str]) -> pl.Expr:
        choices = [non_empty_text_expr(column_name) for column_name in column_names if column_name in columns]
        return pl.coalesce(choices).fill_null("") if choices else pl.lit("")

    def numeric_expr(column_name: str) -> pl.Expr:
        if column_name not in columns:
            return pl.lit(None).cast(pl.Float64)
        return pl.col(column_name).cast(pl.Float64, strict=False)

    def coalesce_numeric_expr(column_names: list[str]) -> pl.Expr:
        choices = [numeric_expr(column_name) for column_name in column_names if column_name in columns]
        return pl.coalesce(choices).fill_null(0.0) if choices else pl.lit(0.0)

    amount_usd = coalesce_numeric_expr(["amount_usd", "net_amount_usd", "net_amount"])
    units = coalesce_numeric_expr([
        "units",
        "Units",
        "quantity",
        "Quantity",
        "Asset Quantity",
        "Product Quantity",
        "streams",
        "Streams",
        "views",
        "Views",
    ])
    artist = coalesce_text_expr([
        "artist_statement_style",
        "artist_best_available",
        "artist_name_statement",
        "track_artist_statement",
        "product_artist_statement",
        "asset_artist_statement",
        "Artist Name",
        "Track Artist",
        "TRACK ARTIST",
        "PRODUCT ARTIST",
        "Asset Artist",
        "Product Artist",
        "artists_raw",
        "payee",
        "Payee",
    ])
    title = coalesce_text_expr([
        "track_statement_style",
        "release_statement_style",
        "track_title",
        "Track Title",
        "TRACK",
        "Asset Title",
        "Product Title",
        "Title",
        "Video Title",
        "Album Title",
    ])
    isrc = coalesce_text_expr(["asset_isrc", "isrc", "ISRC", "Track ISRC", "Asset ISRC"])
    upc = coalesce_text_expr(["upc", "UPC", "Product UPC", "Release UPC"])
    dsp = text_expr("dsp_normalized")
    territory = coalesce_text_expr(["territory", "Territory", "COUNTRY", "Country", "Sale Country", "Region"])
    sale_type = coalesce_text_expr(["Sale Type", "use_type", "Use Type", "usage_type", "usage_raw", "Product Type"])
    label = coalesce_text_expr([
        "label_normalized_statement_style",
        "label_normalized",
        "label_statement_style",
        "Label Name",
        "Product Label",
        "LABEL",
        "label",
    ])
    search_variants = pl.concat_str([
        text_expr(column_name)
        for column_name in [
            "artist_statement_style",
            "artist_best_available",
            "artist_name_statement",
            "track_artist_statement",
            "product_artist_statement",
            "asset_artist_statement",
            "Artist Name",
            "Track Artist",
            "TRACK ARTIST",
            "PRODUCT ARTIST",
            "Asset Artist",
            "Product Artist",
            "artists_raw",
            "payee",
            "Payee",
            "track_statement_style",
            "release_statement_style",
            "track_title",
            "Track Title",
            "TRACK",
            "Asset Title",
            "Product Title",
            "Title",
            "Video Title",
            "Album Title",
        ]
        if column_name in columns
    ], separator=" ")
    source_sheet = coalesce_text_expr(["source_sheet", "sheet_name", "Sheet", "SHEET"])
    precompact = (
        lf
        .with_columns([
            text_expr("source").alias("source"),
            text_expr("account").alias("account"),
            text_expr("statement_period").alias("statement_period"),
            text_expr("transaction_month").alias("transaction_month"),
            source_sheet.alias("source_sheet"),
            coalesce_text_expr(["revenue_basis", "Base ingreso"]).alias("revenue_basis"),
            artist.alias("artist"),
            title.alias("title"),
            isrc.alias("asset_isrc"),
            upc.alias("UPC"),
            coalesce_text_expr(["video_id", "Video ID", "VideoId", "YOUTUBE VIDEO ID", "YouTube Video ID", "YouTube Asset ID", "ID", "Parent ID", "track_id"]).alias("video_id"),
            dsp.alias("dsp"),
            territory.alias("territory"),
            sale_type.alias("sale_type"),
            text_expr("monetization_normalized").alias("monetization_normalized"),
            text_expr("content_origin_normalized").alias("content_origin_normalized"),
            text_expr("classification_status").alias("classification_status"),
            label.alias("label"),
            search_variants.alias("_search_variants"),
            units.alias("units"),
            amount_usd.alias("_dashboard_amount_usd"),
        ])
        .with_columns([
            pl.when(pl.col("artist") == "").then(pl.lit("SIN ARTISTA")).otherwise(pl.col("artist")).alias("artist"),
            pl.when(pl.col("title") == "").then(pl.lit("SIN TITULO")).otherwise(pl.col("title")).alias("title"),
            pl.when(pl.col("dsp") == "").then(pl.lit("SIN DSP")).otherwise(pl.col("dsp")).alias("dsp"),
            pl.when(pl.col("territory") == "").then(pl.lit("SIN TERRITORIO")).otherwise(pl.col("territory")).alias("territory"),
            pl.when(pl.col("sale_type") == "").then(pl.lit("SIN TIPO")).otherwise(pl.col("sale_type")).alias("sale_type"),
            pl.when(pl.col("label") == "").then(pl.lit("SIN LABEL")).otherwise(pl.col("label")).alias("label"),
        ])
        .filter(
            (pl.col("source") != "")
            & (pl.col("account") != "")
            & (pl.col("statement_period") != "")
        )
        .group_by([
            "statement_period",
            "transaction_month",
            "source",
            "account",
            "source_sheet",
            "revenue_basis",
            "artist",
            "title",
            "asset_isrc",
            "UPC",
            "video_id",
            "dsp",
            "territory",
            "sale_type",
            "monetization_normalized",
            "content_origin_normalized",
            "classification_status",
            "label",
            "_search_variants",
        ])
        .agg([
            pl.sum("_dashboard_amount_usd").alias("_dashboard_amount_usd"),
            pl.sum("units").round(0).alias("units"),
            pl.len().alias("raw_rows"),
        ])
    )

    reportable = filter_reportable_generation(precompact, set(precompact.collect_schema().names()))
    compact = (
        reportable
        .select([
            "statement_period",
            "transaction_month",
            "source",
            "account",
            "source_sheet",
            "artist",
            "title",
            pl.col("asset_isrc").alias("isrc"),
            pl.col("UPC").alias("upc"),
            "dsp",
            "territory",
            "sale_type",
            "monetization_normalized",
            "content_origin_normalized",
            "classification_status",
            "label",
            pl.concat_str([
                pl.col("artist"),
                pl.col("title"),
                pl.col("asset_isrc"),
                pl.col("UPC"),
                pl.col("video_id"),
                pl.col("dsp"),
                pl.col("monetization_normalized"),
                pl.col("content_origin_normalized"),
                pl.col("label"),
                pl.col("sale_type"),
                pl.col("_search_variants"),
            ], separator=" ")
            .str.to_lowercase()
            .alias("search_text"),
            pl.col("_dashboard_amount_usd").alias("amount_usd"),
            "units",
            "raw_rows",
        ])
    )

    statement_periods = (
        lf
        .select(text_expr("statement_period").alias("statement_period"))
        .filter(pl.col("statement_period") != "")
        .unique()
        .sort("statement_period")
        .collect(engine="streaming")
        .get_column("statement_period")
        .to_list()
    )
    if not statement_periods:
        raise ValueError("No hay statement_period validos para construir el dashboard de regalias.")

    parts_dir = BASE / "staging" / f"{target_path.stem}_parts"
    if parts_dir.exists():
        shutil.rmtree(parts_dir)
    parts_dir.mkdir(parents=True, exist_ok=True)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = target_path.with_name(
        f"{target_path.name}.tmp"
    )
    if temporary_output.exists():
        temporary_output.unlink()
    try:
        for index, statement_period in enumerate(statement_periods):
            part_path = parts_dir / f"{index:03d}_{statement_period}.parquet"
            (
                compact
                .filter(pl.col("statement_period") == statement_period)
                .sink_parquet(part_path, compression="zstd", engine="streaming")
            )

        (
            pl.scan_parquet(parts_dir / "*.parquet")
            .sink_parquet(temporary_output, compression="zstd", engine="streaming")
        )
        temporary_output.replace(target_path)
    finally:
        shutil.rmtree(parts_dir, ignore_errors=True)
    return target_path


def build_partitioned_royalties_dashboard_summary_mart(
    standardized_path: Path,
    output_path: Path,
) -> Path:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    raw_parts_dir = BASE / "staging" / "royalties_dashboard_raw_periods"
    summary_parts_dir = BASE / "staging" / "royalties_dashboard_compact_periods"
    temporary_output = output_path.with_name(f"{output_path.name}.tmp")

    for path in [raw_parts_dir, summary_parts_dir]:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    if temporary_output.exists():
        temporary_output.unlink()

    parquet_file = pq.ParquetFile(standardized_path)
    statement_period_index = parquet_file.schema_arrow.get_field_index("statement_period")
    if statement_period_index < 0:
        raise ValueError("El mart consolidado no contiene statement_period.")

    writers: dict[str, pq.ParquetWriter] = {}
    try:
        for batch in parquet_file.iter_batches(batch_size=100_000):
            statement_periods = batch.column(statement_period_index)
            for scalar in pc.unique(statement_periods):
                if not scalar.is_valid:
                    continue
                statement_period = str(scalar.as_py()).strip()
                if not statement_period:
                    continue
                mask = pc.equal(
                    statement_periods,
                    pa.scalar(scalar.as_py(), type=statement_periods.type),
                )
                table = pa.Table.from_batches([batch]).filter(mask)
                writer = writers.get(statement_period)
                if writer is None:
                    part_path = raw_parts_dir / f"{statement_period}.parquet"
                    writer = pq.ParquetWriter(part_path, table.schema, compression="zstd")
                    writers[statement_period] = writer
                writer.write_table(table)
    finally:
        for writer in writers.values():
            writer.close()

    raw_parts = sorted(raw_parts_dir.rglob("*.parquet"))
    if not raw_parts:
        raise ValueError("No se generaron particiones mensuales para el dashboard de regalias.")

    try:
        for index, raw_part in enumerate(raw_parts):
            summary_part = summary_parts_dir / f"{index:03d}.parquet"
            build_royalties_dashboard_summary_mart(
                standardized_path=raw_part,
                refresh_cache=True,
                output_path=summary_part,
                partition_large_input=False,
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        (
            pl.scan_parquet(summary_parts_dir / "*.parquet")
            .sink_parquet(temporary_output, compression="zstd", engine="streaming")
        )
        temporary_output.replace(output_path)
    finally:
        shutil.rmtree(raw_parts_dir, ignore_errors=True)
        shutil.rmtree(summary_parts_dir, ignore_errors=True)
        if temporary_output.exists():
            temporary_output.unlink()

    return output_path


def build_digital_income_summary_mart(standardized_path: Path, refresh_cache: bool = False) -> Path:
    if (
        not refresh_cache
        and DIGITAL_INCOME_SUMMARY_PATH.exists()
        and DIGITAL_INCOME_SUMMARY_PATH.stat().st_mtime >= standardized_path.stat().st_mtime
    ):
        return DIGITAL_INCOME_SUMMARY_PATH

    lf = pl.scan_parquet(standardized_path)
    schema = lf.collect_schema()
    columns = set(schema.names())

    def text_expr(column_name: str) -> pl.Expr:
        if column_name not in columns:
            return pl.lit("")
        return pl.col(column_name).cast(pl.Utf8, strict=False).fill_null("").str.strip_chars()

    def non_empty_text_expr(column_name: str) -> pl.Expr:
        value = text_expr(column_name)
        return pl.when(value == "").then(None).otherwise(value)

    def numeric_expr(column_name: str) -> pl.Expr:
        if column_name not in columns:
            return pl.lit(None).cast(pl.Float64)
        return pl.col(column_name).cast(pl.Float64, strict=False)

    amount_candidates = [
        numeric_expr(column_name)
        for column_name in ["amount_usd", "net_amount_usd", "net_amount"]
        if column_name in columns
    ]
    amount_usd = pl.coalesce(amount_candidates).fill_null(0.0) if amount_candidates else pl.lit(0.0)

    artist_fields = [
        "artist_statement_style",
        "artist_best_available",
        "artist_name_statement",
        "track_artist_statement",
        "product_artist_statement",
        "asset_artist_statement",
        "Artist Name",
        "Track Artist",
        "TRACK ARTIST",
        "PRODUCT ARTIST",
        "Asset Artist",
        "Product Artist",
        "artists_raw",
        "payee",
        "Payee",
    ]
    title_fields = [
        "track_statement_style",
        "release_statement_style",
        "track_title",
        "Track Title",
        "TRACK",
        "Asset Title",
        "Product Title",
        "Title",
        "Video Title",
        "Album Title",
    ]
    search_fields = [field for field in artist_fields + title_fields if field in columns]

    base = lf.with_columns([
        text_expr("source").alias("source"),
        text_expr("account").alias("account"),
        text_expr("statement_period").alias("statement_period"),
        pl.coalesce([non_empty_text_expr(field) for field in artist_fields if field in columns] or [pl.lit("")]).fill_null("").alias("artist"),
        pl.coalesce([non_empty_text_expr(field) for field in title_fields if field in columns] or [pl.lit("")]).fill_null("").alias("title"),
        pl.concat_str([text_expr(field) for field in search_fields] or [pl.lit("")], separator=" ").str.to_lowercase().alias("search_text"),
        amount_usd.alias("total_usd"),
        numeric_expr("net_amount_eur").fill_null(0.0).alias("total_eur"),
        (
            pl.col("has_share_in_out").cast(pl.Boolean, strict=False).fill_null(False)
            if "has_share_in_out" in columns
            else pl.lit(False)
        ).alias("has_share_in_out"),
    ]).filter(
        (pl.col("statement_period") != "")
        & (pl.col("source") != "")
        & (pl.col("account") != "")
    )
    if "include_in_statement_view" in columns:
        base = base.filter(pl.col("include_in_statement_view").cast(pl.Boolean, strict=False).fill_null(True))

    compact = (
        base
        .with_columns([
            pl.when(pl.col("artist") == "").then(pl.lit("SIN ARTISTA")).otherwise(pl.col("artist")).alias("artist"),
            pl.when(pl.col("title") == "").then(pl.lit("SIN TITULO")).otherwise(pl.col("title")).alias("title"),
        ])
        .group_by(["statement_period", "source", "account", "artist", "title", "search_text"])
        .agg([
            pl.sum("total_usd").alias("total_usd"),
            pl.sum("total_eur").alias("total_eur"),
            pl.max("has_share_in_out").alias("has_share_in_out"),
            pl.len().alias("raw_rows"),
        ])
        .collect()
    )

    DIGITAL_INCOME_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    compact.write_parquet(DIGITAL_INCOME_SUMMARY_PATH)
    return DIGITAL_INCOME_SUMMARY_PATH


@app.get("/digital-income")
def digital_income(
    source: str | None = None,
    account: str | None = None,
    artist: str | None = None,
    artist_keyword: str | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
    period_mode: Literal["last_6_months", "last_12_months", "all", "single_month", "closed_range"] = "last_6_months",
    limit: int = 500,
    offset: int = 0,
    refresh_cache: bool = False,
    x_vpo_api_key: str | None = Header(default=None),
):
    require_api_key(x_vpo_api_key)
    limit = max(1, min(int(limit or 500), 5000))
    offset = max(0, int(offset or 0))

    if VPO_LOCAL_MARTS_DIR is not None and VPO_LOCAL_MARTS_DIR.exists():
        marts = ensure_marts(refresh_cache=refresh_cache, filenames=[STANDARDIZED_FILE])
        standardized_path = marts[STANDARDIZED_FILE]
        if not standardized_path.exists():
            raise HTTPException(status_code=500, detail=f"No existe standardized mart: {standardized_path}")
        summary_path = build_digital_income_summary_mart(standardized_path, refresh_cache=refresh_cache)
    else:
        try:
            summary_marts = ensure_marts(refresh_cache=refresh_cache, filenames=[DIGITAL_INCOME_SUMMARY_FILE])
            summary_path = summary_marts[DIGITAL_INCOME_SUMMARY_FILE]
        except HTTPException:
            marts = ensure_marts(refresh_cache=refresh_cache, filenames=[STANDARDIZED_FILE])
            standardized_path = marts[STANDARDIZED_FILE]
            if not standardized_path.exists():
                raise HTTPException(status_code=500, detail=f"No existe standardized mart: {standardized_path}")
            summary_path = build_digital_income_summary_mart(standardized_path, refresh_cache=refresh_cache)
    base = pl.scan_parquet(summary_path)

    source_account_options = (
        base
        .select(["source", "account"])
        .unique()
        .sort(["source", "account"])
        .collect()
    )
    options = {
        "sources": source_account_options.get_column("source").unique().sort().to_list(),
        "accounts": source_account_options.get_column("account").unique().sort().to_list(),
        "source_accounts": source_account_options.to_dicts(),
        "artists": [],
        "first_month": base.select(pl.min("statement_period").alias("first_month")).collect()["first_month"][0],
        "last_month": base.select(pl.max("statement_period").alias("last_month")).collect()["last_month"][0],
    }

    filtered = base
    if source:
        filtered = filtered.filter(pl.col("source") == source.strip())
    if account:
        filtered = filtered.filter(pl.col("account") == account.strip())

    keyword = normalize_search_text(artist_keyword or artist or "")
    if keyword:
        for token in [part for part in keyword.split() if part.strip()]:
            filtered = filtered.filter(contains_search_expr(pl.col("search_text"), token))

    month_scope = filtered
    if start_month:
        month_scope = month_scope.filter(pl.col("statement_period") >= start_month)
    if end_month:
        month_scope = month_scope.filter(pl.col("statement_period") <= end_month)

    available_months = (
        month_scope
        .select("statement_period")
        .unique()
        .sort("statement_period")
        .collect()
        .get_column("statement_period")
        .to_list()
    )
    if not available_months:
        return {
            "items": [],
            "monthly": [],
            "by_source": [],
            "matrix": [],
            "matrix_months": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "keyword": keyword,
            "totals": {
                "total_usd": 0.0,
                "total_eur": 0.0,
                "rows": 0,
                "months": 0,
                "sources": 0,
                "accounts": 0,
                "first_month": None,
                "last_month": None,
            },
            "options": options,
        }

    if start_month or end_month or period_mode in {"single_month", "closed_range", "all"}:
        matrix_months = available_months
    elif period_mode == "last_12_months":
        matrix_months = available_months[-12:]
    else:
        matrix_months = available_months[-6:]

    filtered = month_scope.filter(pl.col("statement_period").is_in(matrix_months))

    grouped = filtered

    total_rows = grouped.select(pl.len().alias("rows")).collect()["rows"][0]
    totals = (
        grouped
        .select([
            pl.sum("total_usd").round(2).alias("total_usd"),
            pl.sum("total_eur").round(2).alias("total_eur"),
            pl.len().alias("rows"),
            pl.col("statement_period").n_unique().alias("months"),
            pl.col("source").n_unique().alias("sources"),
            pl.col("account").n_unique().alias("accounts"),
            pl.min("statement_period").alias("first_month"),
            pl.max("statement_period").alias("last_month"),
        ])
        .collect()
        .to_dicts()[0]
    )
    monthly = (
        grouped
        .group_by("statement_period")
        .agg([
            pl.sum("total_usd").round(2).alias("total_usd"),
            pl.sum("total_eur").round(2).alias("total_eur"),
            pl.len().alias("rows"),
        ])
        .sort("statement_period")
        .collect()
        .to_dicts()
    )

    month_aggs = [
        (
            pl.when(pl.col("statement_period") == month)
            .then(pl.col("total_usd"))
            .otherwise(0.0)
            .sum()
            .round(2)
            .alias(month)
        )
        for month in matrix_months
    ]
    matrix_df = (
        grouped
        .group_by(["source", "account"])
        .agg([
            *month_aggs,
            pl.sum("total_usd").round(2).alias("total_usd"),
            pl.sum("total_eur").round(2).alias("total_eur"),
            pl.len().alias("rows"),
            pl.col("artist").n_unique().alias("artists"),
            pl.max("has_share_in_out").alias("has_share_in_out"),
        ])
        .sort("total_usd", descending=True)
        .collect()
    )
    matrix = []
    for row in matrix_df.to_dicts():
        matrix.append({
            "source": row["source"],
            "account": row["account"],
            "months": {month: float(row.get(month) or 0.0) for month in matrix_months},
            "total_usd": float(row.get("total_usd") or 0.0),
            "total_eur": float(row.get("total_eur") or 0.0),
            "rows": int(row.get("rows") or 0),
            "artists": int(row.get("artists") or 0),
            "has_share_in_out": bool(row.get("has_share_in_out")),
        })

    by_source = [
        {
            "source": row["source"],
            "account": row["account"],
            "total_usd": row["total_usd"],
            "total_eur": row["total_eur"],
            "rows": row["rows"],
            "artists": row["artists"],
        }
        for row in matrix
    ]

    items = (
        grouped
        .select([
            "statement_period",
            "source",
            "account",
            "artist",
            "title",
            "total_usd",
            "total_eur",
            "has_share_in_out",
            "raw_rows",
        ])
        .sort(["statement_period", "source", "account", "artist"])
        .slice(offset, limit)
        .collect()
        .to_dicts()
    )

    return {
        "items": items,
        "monthly": monthly,
        "by_source": by_source,
        "matrix": matrix,
        "matrix_months": matrix_months,
        "total": int(total_rows),
        "limit": limit,
        "offset": offset,
        "keyword": keyword,
        "totals": totals,
        "options": options,
    }


@app.get("/royalties-dashboard")
def royalties_dashboard(
    source: str | None = None,
    account: str | None = None,
    keyword: str | None = None,
    artist_keyword: str | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
    period_basis: Literal["statement_period", "transaction_month"] = "statement_period",
    period_mode: Literal["last_6_months", "last_12_months", "all", "single_month", "closed_range"] = "last_6_months",
    limit: int = 10,
    refresh_cache: bool = False,
    x_vpo_api_key: str | None = Header(default=None),
):
    require_api_key(x_vpo_api_key)
    safe_limit = max(3, min(int(limit or 10), 50))
    period_col = "transaction_month" if period_basis == "transaction_month" else "statement_period"

    if VPO_LOCAL_MARTS_DIR is not None and VPO_LOCAL_MARTS_DIR.exists():
        marts = ensure_marts(refresh_cache=refresh_cache, filenames=[STANDARDIZED_FILE])
        standardized_path = marts[STANDARDIZED_FILE]
        if not standardized_path.exists():
            raise HTTPException(status_code=500, detail=f"No existe standardized mart: {standardized_path}")
        summary_path = build_royalties_dashboard_summary_mart(standardized_path, refresh_cache=refresh_cache)
    else:
        try:
            summary_marts = ensure_marts(refresh_cache=refresh_cache, filenames=[ROYALTIES_DASHBOARD_SUMMARY_FILE])
            summary_path = summary_marts[ROYALTIES_DASHBOARD_SUMMARY_FILE]
        except HTTPException:
            marts = ensure_marts(refresh_cache=refresh_cache, filenames=[STANDARDIZED_FILE])
            standardized_path = marts[STANDARDIZED_FILE]
            if not standardized_path.exists():
                raise HTTPException(status_code=500, detail=f"No existe standardized mart: {standardized_path}")
            summary_path = build_royalties_dashboard_summary_mart(standardized_path, refresh_cache=refresh_cache)
    base = pl.scan_parquet(summary_path)
    policy_document = load_distributor_policy_document()
    base = apply_report_net_personalization(
        base,
        set(base.collect_schema().names()),
        amount_col="amount_usd",
    )
    personalization_state = {
        **policy_document["report_personalization"],
        "policy_version": policy_document["policy_version"],
        "updated_at": policy_document["updated_at"],
    }

    source_account_options = (
        base
        .select(["source", "account"])
        .unique()
        .sort(["source", "account"])
        .collect()
    )
    all_months = (
        base
        .filter(pl.col(period_col) != "")
        .select(period_col)
        .unique()
        .sort(period_col)
        .collect()
        .get_column(period_col)
        .to_list()
    )
    options = {
        "sources": source_account_options.get_column("source").unique().sort().to_list(),
        "accounts": source_account_options.get_column("account").unique().sort().to_list(),
        "source_accounts": source_account_options.to_dicts(),
        "first_month": all_months[0] if all_months else None,
        "last_month": all_months[-1] if all_months else None,
    }

    filtered = base.filter(pl.col(period_col) != "")
    if source:
        filtered = filtered.filter(pl.col("source") == source.strip())
    if account:
        filtered = filtered.filter(pl.col("account") == account.strip())

    search = normalize_search_text(keyword or artist_keyword or "")
    if search:
        for token in [part for part in search.split() if part.strip()]:
            filtered = filtered.filter(contains_search_expr(pl.col("search_text"), token))

    month_scope = filtered
    if start_month:
        month_scope = month_scope.filter(pl.col(period_col) >= start_month)
    if end_month:
        month_scope = month_scope.filter(pl.col(period_col) <= end_month)

    available_months = (
        month_scope
        .select(period_col)
        .unique()
        .sort(period_col)
        .collect()
        .get_column(period_col)
        .to_list()
    )
    if not available_months:
        empty_totals = {
            "amount_usd": 0.0,
            "units": 0.0,
            "rows": 0,
            "months": 0,
            "sources": 0,
            "accounts": 0,
            "titles": 0,
            "artists": 0,
            "first_month": None,
            "last_month": None,
        }
        return {
            "report_personalization": personalization_state,
            "period_basis": period_basis,
            "period_column": period_col,
            "period_months": [],
            "keyword": search,
            "totals": empty_totals,
            "monthly": [],
            "matrix": [],
            "rankings": {
                "sources": [],
                "dsp": [],
                "monetization": [],
                "content_origin": [],
                "territory": [],
                "sale_type": [],
                "artist": [],
                "title": [],
                "label": [],
            },
            "youtube": {
                "totals": empty_totals,
                "monetization": [],
                "content_origin": [],
                "title": [],
                "territory": [],
            },
            "options": options,
        }

    if start_month or end_month or period_mode in {"single_month", "closed_range", "all"}:
        months = available_months
    elif period_mode == "last_12_months":
        months = available_months[-12:]
    else:
        months = available_months[-6:]

    scoped = month_scope.filter(pl.col(period_col).is_in(months))

    totals = (
        scoped
        .select([
            pl.sum("amount_usd").round(2).alias("amount_usd"),
            pl.sum("units").round(0).alias("units"),
            pl.sum("raw_rows").alias("rows"),
            pl.col(period_col).n_unique().alias("months"),
            pl.col("source").n_unique().alias("sources"),
            pl.col("account").n_unique().alias("accounts"),
            pl.col("title").n_unique().alias("titles"),
            pl.col("artist").n_unique().alias("artists"),
            pl.min(period_col).alias("first_month"),
            pl.max(period_col).alias("last_month"),
        ])
        .collect()
        .to_dicts()[0]
    )
    total_amount = float(totals.get("amount_usd") or 0.0)

    def rank_by(field: str, name_key: str = "name", frame: pl.LazyFrame | None = None) -> list[dict]:
        source_frame = frame if frame is not None else scoped
        frame_total = (
            source_frame
            .select(pl.sum("amount_usd").round(2).alias("amount_usd"))
            .collect()
            .to_dicts()[0]
            .get("amount_usd")
        )
        df = (
            source_frame
            .filter(pl.col(field).is_not_null() & (pl.col(field) != ""))
            .group_by(field)
            .agg([
                pl.sum("amount_usd").round(2).alias("amount_usd"),
                pl.sum("units").round(0).alias("units"),
                pl.sum("raw_rows").alias("rows"),
            ])
            .sort("amount_usd", descending=True)
            .limit(safe_limit)
            .collect()
        )
        denominator = float(frame_total or 0.0)
        rows: list[dict] = []
        for row in df.to_dicts():
            amount = float(row.get("amount_usd") or 0.0)
            rows.append({
                name_key: row.get(field) or "-",
                "amount_usd": amount,
                "units": float(row.get("units") or 0.0),
                "rows": int(row.get("rows") or 0),
                "percentage": round((amount / denominator * 100), 2) if denominator else 0.0,
            })
        return rows

    monthly = (
        scoped
        .group_by(period_col)
        .agg([
            pl.sum("amount_usd").round(2).alias("amount_usd"),
            pl.sum("units").round(0).alias("units"),
            pl.sum("raw_rows").alias("rows"),
        ])
        .sort(period_col)
        .collect()
        .rename({period_col: "month"})
        .to_dicts()
    )

    month_aggs = [
        (
            pl.when(pl.col(period_col) == month)
            .then(pl.col("amount_usd"))
            .otherwise(0.0)
            .sum()
            .round(2)
            .alias(month)
        )
        for month in months
    ]
    matrix_df = (
        scoped
        .group_by(["source", "account"])
        .agg([
            *month_aggs,
            pl.sum("amount_usd").round(2).alias("amount_usd"),
            pl.sum("units").round(0).alias("units"),
            pl.sum("raw_rows").alias("rows"),
            pl.col("artist").n_unique().alias("artists"),
            pl.col("title").n_unique().alias("titles"),
        ])
        .sort("amount_usd", descending=True)
        .collect()
    )
    matrix = []
    for row in matrix_df.to_dicts():
        matrix.append({
            "source": row["source"],
            "account": row["account"],
            "months": {month: float(row.get(month) or 0.0) for month in months},
            "amount_usd": float(row.get("amount_usd") or 0.0),
            "units": float(row.get("units") or 0.0),
            "rows": int(row.get("rows") or 0),
            "artists": int(row.get("artists") or 0),
            "titles": int(row.get("titles") or 0),
        })

    youtube_scope = scoped.filter(pl.col("dsp") == "YouTube")
    youtube_totals = (
        youtube_scope
        .select([
            pl.sum("amount_usd").round(2).alias("amount_usd"),
            pl.sum("units").round(0).alias("units"),
            pl.sum("raw_rows").alias("rows"),
            pl.col("title").n_unique().alias("titles"),
            pl.col("artist").n_unique().alias("artists"),
        ])
        .collect()
        .to_dicts()[0]
    )

    return {
        "report_personalization": personalization_state,
        "period_basis": period_basis,
        "period_column": period_col,
        "period_months": months,
        "keyword": search,
        "totals": totals,
        "monthly": monthly,
        "matrix": matrix,
        "rankings": {
            "sources": rank_by("source"),
            "dsp": rank_by("dsp"),
            "monetization": rank_by("monetization_normalized"),
            "content_origin": rank_by("content_origin_normalized"),
            "territory": rank_by("territory"),
            "sale_type": rank_by("sale_type"),
            "artist": rank_by("artist"),
            "title": rank_by("title"),
            "label": rank_by("label"),
        },
        "youtube": {
            "totals": youtube_totals,
            "monetization": rank_by("monetization_normalized", frame=youtube_scope),
            "content_origin": rank_by("content_origin_normalized", frame=youtube_scope),
            "title": rank_by("title", frame=youtube_scope),
            "territory": rank_by("territory", frame=youtube_scope),
        },
        "options": options,
    }


@app.get("/booking/shows")
def booking_shows(
    limit: int = 50,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    safe_limit = min(max(limit, 1), 1000)

    with booking_connect() as conn:
        permission = user_module_permission(conn, x_vpo_username, "booking")
        if not permission.get("allowed"):
            raise HTTPException(status_code=403, detail="No tenes permiso para ver Booking Indyana.")
        if not (permission.get("can_view_history") or permission.get("can_edit") or permission.get("can_approve")):
            return {
                "db_driver": operational_db_settings().driver,
                "items": [],
            }
        params: list = []
        artist_scope_sql = apply_artist_scope_sql(conn, x_vpo_username, "booking", params)
        rows = conn.execute(
            f"""
            SELECT *
            FROM booking_shows
            WHERE 1 = 1
              {artist_scope_sql}
            ORDER BY show_date DESC, id DESC
            LIMIT ?
            """,
            (*params, safe_limit),
        ).fetchall()
        items = [row_to_booking_show(row) for row in rows]
        items = attach_booking_expenses(conn, items)
        items = attach_booking_cash_movements(conn, items)
        items = attach_booking_pre_split_adjustments(conn, items)
        items = attach_booking_direct_commissions(conn, items)
        items = attach_booking_external_shares(conn, items)
        items = attach_booking_adjustments(conn, items)
        items = attach_booking_account_applications(conn, items)

    return {
        "db_driver": operational_db_settings().driver,
        "items": items,
    }


@app.get("/booking/shows/{show_id}")
def booking_show(
    show_id: int,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    with booking_connect() as conn:
        row = conn.execute("SELECT artist FROM booking_shows WHERE id = ?", (show_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Show no encontrado.")
        require_module_permission(conn, x_vpo_username, "booking", "view_history", artist=row["artist"])
        item = fetch_booking_show_item(conn, show_id)
    return {"item": item}


def booking_summary_for_module(module_key: str, x_vpo_username: str | None) -> dict:
    with booking_connect() as conn:
        ensure_booking_commission_rules_table(conn)
        params: list = []
        artist_scope_sql = apply_artist_scope_sql(conn, x_vpo_username, module_key, params)
        rows = conn.execute(
            f"""
            SELECT
                artist,
                substr(show_date, 1, 7) AS month,
                COALESCE(producer_cash_target_amount, 0) AS indyana_total,
                COALESCE(booking_commission_exempt, 0) AS booking_commission_exempt,
                COALESCE(booking_commission_notes, '') AS commission_notes
            FROM booking_shows
            WHERE status <> 'cancelado'
              {artist_scope_sql}
            ORDER BY artist, month
            """,
            params,
        ).fetchall()
        rule_rows = conn.execute(
            """
            SELECT
                booking_commission_rules.artist,
                booking_commission_rules.percentage,
                booking_commission_rules.calculation_base,
                booking_commission_rules.include_booking_fee_paid_shows,
                booking_commission_rules.priority_order,
                booking_commission_rules.active_from_month,
                booking_commission_rules.active_to_month,
                booking_commission_rules.active,
                booking_commission_rules.employee_id,
                COALESCE(employees.display_name, '') AS employee_name
            FROM booking_commission_rules
            JOIN employees ON employees.id = booking_commission_rules.employee_id
            WHERE booking_commission_rules.active = true
              AND employees.active = true
            """
        ).fetchall()

    months = sorted({row["month"] for row in rows if row["month"]})
    rules_by_artist: dict[str, list[dict]] = {}
    for row in rule_rows:
        artist = clean_booking_artist(row["artist"])
        if not artist:
            continue
        rules_by_artist.setdefault(artist.casefold(), []).append(
            {
                "artist": artist,
                "employee_name": row["employee_name"] or "",
                "employee_id": int(row["employee_id"]),
                "percentage": float(row["percentage"] or 0),
                "calculation_base": row["calculation_base"] or "commissionable",
                "include_booking_fee_paid_shows": bool(row["include_booking_fee_paid_shows"]),
                "priority_order": int(row["priority_order"]) if row["priority_order"] is not None else 1,
                "stored_priority_order": int(row["priority_order"]) if row["priority_order"] is not None else None,
                "active_from_month": row["active_from_month"],
                "active_to_month": row["active_to_month"],
                "active": bool(row["active"]),
            }
        )

    by_artist: dict[str, dict] = {}
    for row in rows:
        artist = row["artist"]
        month = row["month"]
        if not artist or not month:
            continue

        item = by_artist.setdefault(
            artist,
            {
                "artist": artist,
                "shows": 0,
                "indyana_total": 0.0,
                "commissionable_total": 0.0,
                "non_commissionable_total": 0.0,
                "commission_total": 0.0,
                "indyana_net_total": 0.0,
                "commission_details": [],
                "months": {},
                "notes": [],
            },
        )
        indyana_total = float(row["indyana_total"] or 0)
        show_excludes_general = bool(row["booking_commission_exempt"])
        commissionable_total = 0.0 if show_excludes_general else indyana_total
        non_commissionable_total = indyana_total if show_excludes_general else 0.0
        commission_total = 0.0
        applied_excluded_rule = False
        applicable_rules = []
        for rule in rules_by_artist.get(clean_booking_artist(artist).casefold(), []):
            if not rule["active"] or rule["percentage"] <= 0:
                continue
            if rule["active_from_month"] and month < rule["active_from_month"]:
                continue
            if rule["active_to_month"] and month > rule["active_to_month"]:
                continue
            if show_excludes_general and not rule["include_booking_fee_paid_shows"]:
                continue
            applicable_rules.append(rule)

        cascade_base = indyana_total
        show_commission_details = []
        rules_by_priority: dict[int, list[dict]] = {}
        for rule in applicable_rules:
            rules_by_priority.setdefault(rule["priority_order"], []).append(rule)
        for priority_order in sorted(rules_by_priority):
            base_amount = max(cascade_base, 0.0)
            priority_commission_total = 0.0
            for rule in sorted(rules_by_priority[priority_order], key=lambda value: (value["employee_name"], value["employee_id"])):
                commission_amount = base_amount * rule["percentage"] / 100
                priority_commission_total += commission_amount
                commission_total += commission_amount
                show_commission_details.append(
                    {
                        "employee_id": rule["employee_id"],
                        "employee_name": rule["employee_name"],
                        "artist": artist,
                        "month": month,
                        "priority_order": rule["priority_order"],
                        "percent": rule["percentage"],
                        "base_amount": base_amount,
                        "commission_amount": commission_amount,
                        "show_excludes_general": show_excludes_general,
                        "include_booking_fee_paid_shows": rule["include_booking_fee_paid_shows"],
                    }
                )
                if show_excludes_general:
                    applied_excluded_rule = True
            cascade_base -= priority_commission_total

        item["shows"] += 1
        item["indyana_total"] += indyana_total
        item["commissionable_total"] += commissionable_total
        item["non_commissionable_total"] += non_commissionable_total
        item["commission_total"] += commission_total
        item["indyana_net_total"] += indyana_total - commission_total
        item["commission_details"].extend(show_commission_details)
        month_bucket = item["months"].setdefault(
            month,
            {
                "shows": 0,
                "indyana_total": 0.0,
                "commissionable_total": 0.0,
                "non_commissionable_total": 0.0,
                "commission_total": 0.0,
                "indyana_net_total": 0.0,
                "commission_details": [],
            },
        )
        month_bucket["shows"] += 1
        month_bucket["indyana_total"] += indyana_total
        month_bucket["commissionable_total"] += commissionable_total
        month_bucket["non_commissionable_total"] += non_commissionable_total
        month_bucket["commission_total"] += commission_total
        month_bucket["indyana_net_total"] += indyana_total - commission_total
        month_bucket["commission_details"].extend(show_commission_details)

        if show_excludes_general:
            note = clean_optional_text(row["commission_notes"]) or "Excluye comision general"
            if note not in item["notes"]:
                item["notes"].append(note)
            if applied_excluded_rule:
                applied_note = "Tiene comision particular sobre shows excluidos"
                if applied_note not in item["notes"]:
                    item["notes"].append(applied_note)

    items = sorted(by_artist.values(), key=lambda value: value["indyana_total"], reverse=True)
    totals = {
        "shows": sum(item["shows"] for item in items),
        "indyana_total": sum(item["indyana_total"] for item in items),
        "commissionable_total": sum(item["commissionable_total"] for item in items),
        "non_commissionable_total": sum(item["non_commissionable_total"] for item in items),
        "commission_total": sum(item["commission_total"] for item in items),
        "indyana_net_total": sum(item["indyana_net_total"] for item in items),
    }
    commission_rules = [
        {
            "employee_id": rule["employee_id"],
            "employee_name": rule["employee_name"],
            "artist": rule["artist"],
            "percent": rule["percentage"],
            "base": rule["calculation_base"],
            "include_booking_fee_paid_shows": rule["include_booking_fee_paid_shows"],
            "priority_order": rule["stored_priority_order"],
            "start_month": rule["active_from_month"],
            "end_month": rule["active_to_month"],
            "active": rule["active"],
        }
        for rules in rules_by_artist.values()
        for rule in rules
    ]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "months": months,
        "items": items,
        "totals": totals,
        "commission_rules": commission_rules,
        "db_driver": operational_db_settings().driver,
    }


@app.get("/booking/summary")
def booking_summary(
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    return booking_summary_for_module("booking_summary", x_vpo_username)


@app.get("/booking/commissions-summary")
def booking_commissions_summary(
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    return booking_summary_for_module("booking_commissions", x_vpo_username)


@app.get("/booking/commission-rules")
def booking_commission_rules(
    employee_id: int,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    with booking_connect() as conn:
        require_module_permission(conn, x_vpo_username, "booking_commissions", "access")
        ensure_booking_commission_rules_table(conn)
        employee = conn.execute("SELECT id, display_name FROM employees WHERE id = ?", (employee_id,)).fetchone()
        if employee is None:
            raise HTTPException(status_code=404, detail="Empleado no encontrado.")
        rows = conn.execute(
            """
            SELECT *
            FROM booking_commission_rules
            WHERE employee_id = ?
            ORDER BY artist
            """,
            (employee_id,),
        ).fetchall()
        return {
            "employee": {"id": int(employee["id"]), "display_name": employee["display_name"]},
            "rules": [row_to_booking_commission_rule(row) for row in rows],
        }


@app.put("/booking/commission-rules")
def save_booking_commission_rules(
    request: BookingCommissionRulesRequest,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    actor_username = clean_username(x_vpo_username or "")
    now = datetime.now().isoformat(timespec="seconds")
    with booking_connect() as conn:
        actor_permission = require_module_permission(conn, actor_username, "booking_commissions", "edit")
        ensure_booking_commission_rules_table(conn)
        employee = conn.execute(
            "SELECT id, display_name FROM employees WHERE id = ? AND active = 1",
            (request.employee_id,),
        ).fetchone()
        if employee is None:
            raise HTTPException(status_code=404, detail="Empleado no encontrado.")

        selected_permission = conn.execute(
            """
            SELECT can_access, scope_json
            FROM module_permissions
            WHERE employee_id = ?
              AND module_key = 'booking_commissions'
            """,
            (request.employee_id,),
        ).fetchone()
        if selected_permission is None or not bool(selected_permission["can_access"]):
            raise HTTPException(status_code=400, detail="El empleado no tiene activo el modulo Comisiones.")

        selected_scope_items = parse_permission_scope(selected_permission["scope_json"])
        if not selected_scope_items or any(item["scope_type"] == "all" and item["scope_ref"] == "*" for item in selected_scope_items):
            selected_scoped_artists: set[str] | None = None
        else:
            selected_scoped_artists = {
                cleaned.casefold()
                for item in selected_scope_items
                if item["scope_type"] == "artist"
                for cleaned in [clean_booking_artist(item["scope_ref"])]
                if cleaned
            }

        actor_scoped_artists = actor_permission.get("scope")
        prepared_rules: list[dict] = []
        seen_artists: set[str] = set()
        for rule in request.rules:
            artist = clean_booking_artist(rule.artist)
            if not artist:
                continue
            artist_key = artist.casefold()
            if artist_key in seen_artists:
                continue
            if selected_scoped_artists is not None and artist_key not in selected_scoped_artists:
                raise HTTPException(status_code=400, detail=f"{artist} no esta asignado al empleado seleccionado.")
            if actor_scoped_artists is not None and artist_key not in actor_scoped_artists:
                raise HTTPException(status_code=403, detail=f"No tenes permiso para configurar {artist}.")

            start_month = clean_commission_rule_month(rule.start_month)
            end_month = clean_commission_rule_month(rule.end_month)
            if start_month and end_month and start_month > end_month:
                raise HTTPException(status_code=400, detail=f"Rango de meses invalido para {artist}.")
            priority_order = int(rule.priority_order) if rule.priority_order is not None else None
            if rule.active and float(rule.percent) > 0 and priority_order is None:
                raise HTTPException(status_code=400, detail=f"Elegi orden de cobro para {artist}.")

            prepared_rules.append({
                "artist": artist,
                "percentage": float(rule.percent),
                "calculation_base": rule.base,
                "include_booking_fee_paid_shows": bool(rule.include_booking_fee_paid_shows),
                "priority_order": priority_order,
                "active_from_month": start_month,
                "active_to_month": end_month,
                "active": 1 if rule.active else 0,
                "notes": clean_optional_text(rule.notes),
            })
            seen_artists.add(artist_key)

        for rule in prepared_rules:
            if not rule["active"] or rule["percentage"] <= 0:
                continue
            conflict = conn.execute(
                """
                SELECT booking_commission_rules.artist, employees.display_name
                FROM booking_commission_rules
                JOIN employees ON employees.id = booking_commission_rules.employee_id
                WHERE lower(booking_commission_rules.artist) = lower(?)
                  AND booking_commission_rules.employee_id <> ?
                  AND booking_commission_rules.active = true
                  AND employees.active = true
                  AND COALESCE(booking_commission_rules.percentage, 0) > 0
                  AND booking_commission_rules.priority_order IS NOT NULL
                  AND booking_commission_rules.priority_order = ?
                LIMIT 1
                """,
                (rule["artist"], request.employee_id, rule["priority_order"]),
            ).fetchone()
            if conflict is not None:
                raise HTTPException(
                    status_code=400,
                    detail=f"El orden {rule['priority_order']} para {rule['artist']} ya lo usa {conflict['display_name']}.",
                )

        for rule in prepared_rules:
            conn.execute(
                """
                INSERT INTO booking_commission_rules (
                    employee_id, artist, percentage, calculation_base, include_booking_fee_paid_shows,
                    priority_order, active_from_month, active_to_month, active, notes, created_by, updated_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(employee_id, artist) DO UPDATE SET
                    percentage = excluded.percentage,
                    calculation_base = excluded.calculation_base,
                    include_booking_fee_paid_shows = excluded.include_booking_fee_paid_shows,
                    priority_order = excluded.priority_order,
                    active_from_month = excluded.active_from_month,
                    active_to_month = excluded.active_to_month,
                    active = excluded.active,
                    notes = excluded.notes,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (
                    request.employee_id,
                    rule["artist"],
                    rule["percentage"],
                    rule["calculation_base"],
                    rule["include_booking_fee_paid_shows"],
                    rule["priority_order"],
                    rule["active_from_month"],
                    rule["active_to_month"],
                    rule["active"],
                    rule["notes"],
                    actor_username or None,
                    actor_username or None,
                    now,
                    now,
                ),
            )

        rows = conn.execute(
            """
            SELECT *
            FROM booking_commission_rules
            WHERE employee_id = ?
            ORDER BY artist
            """,
            (request.employee_id,),
        ).fetchall()
        return {
            "ok": True,
            "employee": {"id": int(employee["id"]), "display_name": employee["display_name"]},
            "saved": len(prepared_rules),
            "rules": [row_to_booking_commission_rule(row) for row in rows],
        }


@app.get("/booking/artist-summary")
def booking_artist_summary(
    artist: str | None = None,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    selected_artist = clean_optional_text(artist)

    with booking_connect() as conn:
        artist_scope_params: list = []
        artist_scope_sql = apply_artist_scope_sql(conn, x_vpo_username, "booking_detail", artist_scope_params)
        artists = [
            row["artist"]
            for row in conn.execute(
                f"""
                SELECT DISTINCT artist
                FROM booking_shows
                WHERE status <> 'cancelado'
                  {artist_scope_sql}
                ORDER BY artist
                """,
                artist_scope_params,
            ).fetchall()
            if row["artist"]
        ]

        params: list = []
        where_artist = ""
        if selected_artist:
            where_artist = "AND artist = ?"
            params.append(selected_artist)
        artist_scope_sql = apply_artist_scope_sql(conn, x_vpo_username, "booking_detail", params)

        rows = conn.execute(
            f"""
            SELECT
                id,
                artist,
                show_date,
                venue,
                COALESCE(city, '') AS city,
                COALESCE(contracted_cachet_amount, cachet_amount, 0) AS cachet_total,
                artist_cash_target_amount AS artist_income,
                producer_cash_target_amount AS indyana_income,
                COALESCE(booking_commission_exempt, 0) AS booking_commission_exempt,
                CASE WHEN COALESCE(booking_commission_exempt, 0) = 1 THEN 0 ELSE producer_cash_target_amount END AS commissionable_income,
                CASE WHEN COALESCE(booking_commission_exempt, 0) = 1 THEN producer_cash_target_amount ELSE 0 END AS non_commissionable_income,
                COALESCE(booking_commission_notes, '') AS commission_notes,
                settlement_status,
                origin_type,
                origin_id
            FROM booking_shows
            WHERE status <> 'cancelado'
              {where_artist}
              {artist_scope_sql}
            ORDER BY show_date DESC, id DESC
            """,
            params,
        ).fetchall()

    items = []
    monthly: dict[str, dict] = {}
    for row in rows:
        month = str(row["show_date"] or "")[:7]
        cachet_total = float(row["cachet_total"] or 0)
        artist_income = float(row["artist_income"] or 0)
        indyana_income = float(row["indyana_income"] or 0)
        commissionable_income = float(row["commissionable_income"] or 0)
        non_commissionable_income = float(row["non_commissionable_income"] or 0)
        items.append(
            {
                "id": row["id"],
                "artist": row["artist"],
                "show_date": row["show_date"],
                "venue": row["venue"],
                "city": row["city"],
                "cachet_total": cachet_total,
                "artist_income": artist_income,
                "indyana_income": indyana_income,
                "is_commissionable": not bool(row["booking_commission_exempt"]),
                "commissionable_income": commissionable_income,
                "non_commissionable_income": non_commissionable_income,
                "commission_notes": row["commission_notes"],
                "settlement_status": row["settlement_status"],
                "origin_type": row["origin_type"],
                "origin_id": row["origin_id"],
            }
        )
        if month:
            bucket = monthly.setdefault(
                month,
                {
                    "month": month,
                    "shows": 0,
                    "cachet_total": 0.0,
                    "artist_income": 0.0,
                    "indyana_income": 0.0,
                    "commissionable_income": 0.0,
                    "non_commissionable_income": 0.0,
                },
            )
            bucket["shows"] += 1
            bucket["cachet_total"] += cachet_total
            bucket["artist_income"] += artist_income
            bucket["indyana_income"] += indyana_income
            bucket["commissionable_income"] += commissionable_income
            bucket["non_commissionable_income"] += non_commissionable_income

    totals = {
        "shows": len(items),
        "cachet_total": sum(item["cachet_total"] for item in items),
        "artist_income": sum(item["artist_income"] for item in items),
        "indyana_income": sum(item["indyana_income"] for item in items),
        "commissionable_income": sum(item["commissionable_income"] for item in items),
        "non_commissionable_income": sum(item["non_commissionable_income"] for item in items),
    }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "selected_artist": selected_artist,
        "artists": artists,
        "items": items,
        "months": [monthly[key] for key in sorted(monthly.keys(), reverse=True)],
        "totals": totals,
    }


@app.get("/artist-finance/summary")
def artist_finance_summary(
    artist: str | None = None,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    selected_artist = clean_optional_text(artist)

    with booking_connect() as conn:
        artist_scope_params: list = []
        artist_scope_sql = apply_artist_scope_sql(conn, x_vpo_username, "artist_finance", artist_scope_params)
        artists = [
            row["artist"]
            for row in conn.execute(
                f"""
                SELECT DISTINCT artist
                FROM booking_shows
                WHERE status <> 'cancelado'
                  {artist_scope_sql}
                ORDER BY artist
                """,
                artist_scope_params,
            ).fetchall()
            if row["artist"]
        ]

        params: list = []
        where_artist = ""
        if selected_artist:
            where_artist = "AND artist = ?"
            params.append(selected_artist)
        artist_scope_sql = apply_artist_scope_sql(conn, x_vpo_username, "artist_finance", params)
        ensure_booking_account_applications_table(conn)

        booking_totals = conn.execute(
            f"""
            WITH account_applications AS (
                SELECT
                    show_id,
                    SUM(CASE WHEN target_balance = 'producer' THEN effect_amount ELSE 0 END) AS producer_effect,
                    SUM(CASE WHEN target_balance = 'artist' THEN effect_amount ELSE 0 END) AS artist_effect,
                    SUM(CASE WHEN target_balance = 'venue' THEN effect_amount ELSE 0 END) AS venue_effect
                FROM booking_account_applications
                GROUP BY show_id
            )
            SELECT
                COUNT(*) AS shows,
                SUM(COALESCE(contracted_cachet_amount, cachet_amount, 0)) AS cachet_total,
                SUM(COALESCE(expenses_amount, 0)) AS show_expenses,
                SUM(COALESCE(artist_cash_target_amount, 0)) AS artist_target,
                SUM(COALESCE(producer_cash_target_amount, 0)) AS indyana_target,
                SUM(COALESCE(artist_paid_amount, 0)) AS artist_paid,
                SUM(COALESCE(producer_received_amount, 0)) AS indyana_received,
                SUM(COALESCE(balance_artist_amount, 0) + COALESCE(account_applications.artist_effect, 0)) AS artist_balance,
                SUM(COALESCE(balance_producer_amount, 0) + COALESCE(account_applications.producer_effect, 0)) AS indyana_balance,
                SUM(COALESCE(venue_balance_amount, 0) + COALESCE(account_applications.venue_effect, 0)) AS venue_balance,
                SUM(CASE WHEN COALESCE(booking_commission_exempt, 0) = 1 THEN 0 ELSE COALESCE(producer_cash_target_amount, 0) END) AS commissionable_indyana,
                SUM(CASE WHEN COALESCE(booking_commission_exempt, 0) = 1 THEN COALESCE(producer_cash_target_amount, 0) ELSE 0 END) AS non_commissionable_indyana
            FROM booking_shows
            LEFT JOIN account_applications ON account_applications.show_id = booking_shows.id
            WHERE status <> 'cancelado'
              {where_artist}
              {artist_scope_sql}
            """,
            params,
        ).fetchone()

        monthly_rows = conn.execute(
            f"""
            WITH account_applications AS (
                SELECT
                    show_id,
                    SUM(CASE WHEN target_balance = 'producer' THEN effect_amount ELSE 0 END) AS producer_effect,
                    SUM(CASE WHEN target_balance = 'artist' THEN effect_amount ELSE 0 END) AS artist_effect,
                    SUM(CASE WHEN target_balance = 'venue' THEN effect_amount ELSE 0 END) AS venue_effect
                FROM booking_account_applications
                GROUP BY show_id
            )
            SELECT
                substr(show_date, 1, 7) AS month,
                COUNT(*) AS shows,
                SUM(COALESCE(producer_cash_target_amount, 0)) AS indyana_target,
                SUM(COALESCE(balance_producer_amount, 0) + COALESCE(account_applications.producer_effect, 0)) AS indyana_balance,
                SUM(COALESCE(balance_artist_amount, 0) + COALESCE(account_applications.artist_effect, 0)) AS artist_balance,
                SUM(COALESCE(venue_balance_amount, 0) + COALESCE(account_applications.venue_effect, 0)) AS venue_balance
            FROM booking_shows
            LEFT JOIN account_applications ON account_applications.show_id = booking_shows.id
            WHERE status <> 'cancelado'
              {where_artist}
              {artist_scope_sql}
            GROUP BY month
            ORDER BY month DESC
            """,
            params,
        ).fetchall()

        open_show_rows = conn.execute(
            f"""
            WITH account_applications AS (
                SELECT
                    show_id,
                    SUM(CASE WHEN target_balance = 'producer' THEN effect_amount ELSE 0 END) AS producer_effect,
                    SUM(CASE WHEN target_balance = 'artist' THEN effect_amount ELSE 0 END) AS artist_effect,
                    SUM(CASE WHEN target_balance = 'venue' THEN effect_amount ELSE 0 END) AS venue_effect
                FROM booking_account_applications
                GROUP BY show_id
            )
            SELECT
                booking_shows.id,
                artist,
                show_date,
                venue,
                COALESCE(balance_producer_amount, 0) + COALESCE(account_applications.producer_effect, 0) AS indyana_balance,
                COALESCE(balance_artist_amount, 0) + COALESCE(account_applications.artist_effect, 0) AS artist_balance,
                COALESCE(venue_balance_amount, 0) + COALESCE(account_applications.venue_effect, 0) AS venue_balance,
                settlement_status,
                status,
                notes
            FROM booking_shows
            LEFT JOIN account_applications ON account_applications.show_id = booking_shows.id
            WHERE status <> 'cancelado'
              {where_artist}
              {artist_scope_sql}
              AND (
                ABS(COALESCE(balance_producer_amount, 0) + COALESCE(account_applications.producer_effect, 0)) > 0.01
                OR ABS(COALESCE(balance_artist_amount, 0) + COALESCE(account_applications.artist_effect, 0)) > 0.01
                OR ABS(COALESCE(venue_balance_amount, 0) + COALESCE(account_applications.venue_effect, 0)) > 0.01
              )
            ORDER BY show_date DESC, id DESC
            LIMIT 100
            """,
            params,
        ).fetchall()

        account_balance_rows = conn.execute(
            f"""
            WITH account_applications AS (
                SELECT
                    show_id,
                    SUM(CASE WHEN target_balance = 'producer' THEN effect_amount ELSE 0 END) AS producer_effect,
                    SUM(CASE WHEN target_balance = 'artist' THEN effect_amount ELSE 0 END) AS artist_effect,
                    SUM(CASE WHEN target_balance = 'venue' THEN effect_amount ELSE 0 END) AS venue_effect
                FROM booking_account_applications
                GROUP BY show_id
            )
            SELECT
                COALESCE(balance_producer_amount, 0) + COALESCE(account_applications.producer_effect, 0) AS indyana_balance,
                COALESCE(balance_artist_amount, 0) + COALESCE(account_applications.artist_effect, 0) AS artist_balance
            FROM booking_shows
            LEFT JOIN account_applications ON account_applications.show_id = booking_shows.id
            WHERE status <> 'cancelado'
              {where_artist}
              {artist_scope_sql}
              AND (
                ABS(COALESCE(balance_producer_amount, 0) + COALESCE(account_applications.producer_effect, 0)) > 0.01
                OR ABS(COALESCE(balance_artist_amount, 0) + COALESCE(account_applications.artist_effect, 0)) > 0.01
              )
            """,
            params,
        ).fetchall()

        ledger_params: list = []
        ledger_where = "WHERE 1 = 1"
        if selected_artist:
            ledger_where += " AND artist = ?"
            ledger_params.append(selected_artist)
        ledger_where += apply_artist_scope_sql(conn, x_vpo_username, "artist_finance", ledger_params)

        legacy_rows = conn.execute(
            f"""
            SELECT
                id,
                artist,
                movement_date,
                movement_type,
                concept,
                category,
                project,
                amount,
                recoverable,
                artist_percent,
                producer_percent,
                show_id,
                notes
            FROM booking_artist_ledger
            {ledger_where}
            ORDER BY movement_date DESC, id DESC
            LIMIT 100
            """,
            ledger_params,
        ).fetchall()

        finance_params: list = []
        finance_where = "WHERE 1 = 1"
        if selected_artist:
            finance_where += " AND artist = ?"
            finance_params.append(selected_artist)
        finance_where += apply_artist_scope_sql(conn, x_vpo_username, "artist_finance", finance_params)

        finance_rows = conn.execute(
            f"""
            SELECT
                id, movement_date, artist, business_area, movement_type, category,
                project_id, project_name, concept, counterparty, paid_by,
                amount, currency, fx_rate, amount_ars,
                paid_amount, paid_amount_ars, pending_amount_ars, payment_status, due_date,
                recoverable,
                recoverable_percent, recovery_method, artist_percent, producer_percent,
                account_effect, status, source_type, source_id,
                proof_refs_json, notes, created_at, updated_at
            FROM finance_staging_movements
            {finance_where}
            ORDER BY movement_date DESC, id DESC
            LIMIT 250
            """,
            finance_params,
        ).fetchall()

        recovery_application_rows = conn.execute(
            f"""
            SELECT
                id, artist, application_date, finance_movement_id, project_name,
                source_type, source_id, source_label, amount_ars,
                recovery_method, notes, created_at
            FROM finance_recovery_applications
            {finance_where}
            ORDER BY application_date DESC, id DESC
            """,
            finance_params,
        ).fetchall()

        finance_project_rows = conn.execute(
            f"""
            SELECT
                COALESCE(project_name, '(sin proyecto)') AS project_name,
                business_area,
                MIN(movement_date) AS first_date,
                MAX(movement_date) AS last_date,
                COUNT(*) AS rows,
                SUM(COALESCE(amount_ars, 0)) AS amount_ars,
                SUM(COALESCE(paid_amount_ars, 0)) AS paid_amount_ars,
                SUM(COALESCE(pending_amount_ars, 0)) AS pending_amount_ars,
                SUM(CASE WHEN recoverable = 1 AND status NOT IN ('aplicado', 'anulado') THEN COALESCE(amount_ars, 0) * COALESCE(recoverable_percent, 0) / 100.0 ELSE 0 END) AS recoverable_amount_ars,
                SUM(CASE WHEN recoverable = 1 AND status NOT IN ('aplicado', 'anulado') THEN COALESCE(paid_amount_ars, 0) * COALESCE(recoverable_percent, 0) / 100.0 ELSE 0 END) AS recoverable_paid_ars,
                SUM(CASE WHEN recoverable = 1 AND status NOT IN ('aplicado', 'anulado') AND COALESCE(recovery_method, 'none') = 'none' THEN COALESCE(amount_ars, 0) * COALESCE(recoverable_percent, 0) / 100.0 ELSE 0 END) AS recoverable_pending_criteria_ars,
                SUM(CASE WHEN recoverable = 1 AND status NOT IN ('aplicado', 'anulado') AND COALESCE(recovery_method, 'none') <> 'none' THEN COALESCE(amount_ars, 0) * COALESCE(recoverable_percent, 0) / 100.0 ELSE 0 END) AS recoverable_defined_ars
            FROM finance_staging_movements
            {finance_where}
            GROUP BY COALESCE(project_name, '(sin proyecto)'), business_area
            ORDER BY last_date DESC, project_name, business_area
            """,
            finance_params,
        ).fetchall()

        finance_status_rows = conn.execute(
            f"""
            SELECT
                status,
                COUNT(*) AS rows,
                SUM(COALESCE(amount_ars, 0)) AS amount_ars,
                SUM(COALESCE(paid_amount_ars, 0)) AS paid_amount_ars,
                SUM(COALESCE(pending_amount_ars, 0)) AS pending_amount_ars
            FROM finance_staging_movements
            {finance_where}
            GROUP BY status
            ORDER BY status
            """,
            finance_params,
        ).fetchall()
        finance_ledger = build_artist_finance_ledger(conn, selected_artist, x_vpo_username, "artist_finance")

    totals = dict(booking_totals) if booking_totals else {}
    for key in [
        "shows",
        "cachet_total",
        "show_expenses",
        "artist_target",
        "indyana_target",
        "artist_paid",
        "indyana_received",
        "artist_balance",
        "indyana_balance",
        "venue_balance",
        "commissionable_indyana",
        "non_commissionable_indyana",
    ]:
        totals[key] = float(totals.get(key) or 0)
    totals["shows"] = int(totals["shows"])
    totals["booking_current_balance_indyana"] = sum(
        booking_current_account_net(row["indyana_balance"], row["artist_balance"])
        for row in account_balance_rows
    )

    legacy_movements = [dict(row) for row in legacy_rows]
    legacy_total = sum(float(row.get("amount") or 0) for row in legacy_movements)
    recoverable_legacy_total = sum(float(row.get("amount") or 0) for row in legacy_movements if row.get("recoverable"))
    finance_movements = [finance_movement_item(row) for row in finance_rows]
    recovery_applications = [dict(row) for row in recovery_application_rows]
    recovered_by_movement: dict[int, float] = {}
    recovered_by_project: dict[tuple[str, str], float] = {}
    for row in recovery_applications:
        amount = float(row.get("amount_ars") or 0)
        movement_id = int(row.get("finance_movement_id") or 0)
        recovered_by_movement[movement_id] = recovered_by_movement.get(movement_id, 0.0) + amount
        project_key = (row.get("project_name") or "(sin proyecto)", "booking")
        recovered_by_project[project_key] = recovered_by_project.get(project_key, 0.0) + amount
    for row in finance_movements:
        recoverable_amount = (
            float(row.get("amount_ars") or 0)
            * float(row.get("recoverable_percent") or 0)
            / 100.0
            if row.get("recoverable") and row.get("status") not in {"aplicado", "anulado"}
            else 0.0
        )
        recovered_amount = recovered_by_movement.get(int(row.get("id") or 0), 0.0)
        row["recovered_amount_ars"] = recovered_amount
        row["recoverable_open_ars"] = max(recoverable_amount - recovered_amount, 0.0)
    finance_amount_total = sum(float(row.get("amount_ars") or 0) for row in finance_movements)
    finance_paid_total = sum(float(row.get("paid_amount_ars") or 0) for row in finance_movements)
    finance_pending_total = sum(float(row.get("pending_amount_ars") or 0) for row in finance_movements)
    finance_recoverable_total = sum(float(row.get("recoverable_open_ars") or 0) for row in finance_movements)
    finance_recovered_total = sum(float(row.get("amount_ars") or 0) for row in recovery_applications)
    finance_recoverable_paid = sum(
        float(row.get("paid_amount_ars") or 0) * float(row.get("recoverable_percent") or 0) / 100.0
        for row in finance_movements
        if row.get("recoverable") and row.get("status") not in {"aplicado", "anulado"}
    )
    finance_recoverable_pending_criteria = sum(
        float(row.get("recoverable_open_ars") or 0)
        for row in finance_movements
        if row.get("recoverable")
        and row.get("status") not in {"aplicado", "anulado"}
        and (row.get("recovery_method") or "none") == "none"
    )
    finance_recoverable_defined_open = sum(
        float(row.get("recoverable_open_ars") or 0)
        for row in finance_movements
        if row.get("recoverable")
        and row.get("status") not in {"aplicado", "anulado"}
        and (row.get("recovery_method") or "none") != "none"
    )
    finance_project_summary = []
    for row in finance_project_rows:
        item = dict(row)
        key = (item.get("project_name") or "(sin proyecto)", item.get("business_area") or "booking")
        recovered_amount = recovered_by_project.get(key, 0.0)
        item["recovered_amount_ars"] = recovered_amount
        item["recoverable_open_ars"] = max(float(item.get("recoverable_amount_ars") or 0) - recovered_amount, 0.0)
        item["recoverable_defined_open_ars"] = max(float(item.get("recoverable_defined_ars") or 0) - recovered_amount, 0.0)
        item["recoverable_pending_criteria_open_ars"] = float(item.get("recoverable_pending_criteria_ars") or 0)
        finance_project_summary.append(item)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "selected_artist": selected_artist,
        "artists": artists,
        "summary": {
            "booking": totals,
            "legacy_ledger": {
                "rows": len(legacy_movements),
                "amount_total": legacy_total,
                "recoverable_amount_total": recoverable_legacy_total,
                "official": False,
                "note": "Legacy de booking_artist_ledger: lectura de apoyo, todavia no es ledger financiero oficial.",
            },
            "recoverables": {
                "open_amount": finance_recoverable_total,
                "paid_basis_amount": finance_recoverable_paid,
                "recovered_amount": finance_recovered_total,
                "pending_amount": finance_recoverable_total,
                "official": True,
                "note": "Lectura desde ledger financiero v1: origenes recuperables menos aplicaciones trazadas.",
            },
            "finance_staging": {
                "rows": len(finance_movements),
                "amount_ars": finance_amount_total,
                "paid_amount_ars": finance_paid_total,
                "pending_amount_ars": finance_pending_total,
                "recoverable_amount_ars": sum(float(row.get("recoverable_amount_ars") or 0) for row in finance_project_summary),
                "recovered_amount_ars": finance_recovered_total,
                "recoverable_paid_basis_ars": finance_recoverable_paid,
                "recoverable_pending_basis_ars": finance_recoverable_total,
                "recoverable_defined_open_ars": finance_recoverable_defined_open,
                "recoverable_pending_criteria_ars": finance_recoverable_pending_criteria,
                "by_status": [dict(row) for row in finance_status_rows],
                "official": False,
                "note": "Movimientos financieros en staging: gastos, inversiones, recuperos, pagos y ajustes cargados para control.",
            },
        },
        "monthly_booking": [dict(row) for row in monthly_rows],
        "open_booking_balances": [dict(row) for row in open_show_rows],
        "finance_ledger": finance_ledger,
        "legacy_movements": legacy_movements,
        "finance_project_summary": finance_project_summary,
        "finance_movements": finance_movements,
        "recovery_applications": recovery_applications,
    }


@app.get("/finance/projects")
def finance_projects(
    artist: str | None = None,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    selected_artist = clean_optional_text(artist)
    params: list = []
    where = ""
    if selected_artist:
        where = "WHERE artist = ? OR artist IS NULL"
        params.append(selected_artist)

    with booking_connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, name, artist, business_area, status, notes, created_at, updated_at
            FROM finance_projects
            {where}
            ORDER BY COALESCE(artist, ''), business_area, name
            """,
            params,
        ).fetchall()

    return {
        "items": [dict(row) for row in rows],
    }


@app.post("/finance/projects")
def create_finance_project(
    request: FinanceProjectRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    now = datetime.now().isoformat(timespec="seconds")
    name = request.name.strip()
    artist = clean_optional_text(request.artist)

    with booking_connect() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM finance_projects
            WHERE name = ?
              AND COALESCE(artist, '') = COALESCE(?, '')
              AND business_area = ?
            """,
            (name, artist, request.business_area),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="El proyecto ya existe para ese artista/area.")

        cursor = conn.execute(
            """
            INSERT INTO finance_projects (
                name, artist, business_area, status, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                artist,
                request.business_area,
                request.status,
                clean_optional_text(request.notes),
                now,
                now,
            ),
        )
        item = conn.execute(
            """
            SELECT id, name, artist, business_area, status, notes, created_at, updated_at
            FROM finance_projects
            WHERE id = ?
            """,
            (int(cursor.lastrowid),),
        ).fetchone()

    return {"item": dict(item)}


@app.get("/finance/movements")
def finance_movements(
    artist: str | None = None,
    project: str | None = None,
    status: str | None = None,
    limit: int = 200,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    selected_artist = clean_optional_text(artist)
    selected_project = clean_optional_text(project)
    selected_status = clean_optional_text(status)
    safe_limit = max(1, min(int(limit or 200), 1000))

    where_parts: list[str] = []
    params: list = []
    option_where_parts: list[str] = []
    option_params: list = []
    if selected_artist:
        where_parts.append("artist = ?")
        params.append(selected_artist)
        option_where_parts.append("artist = ?")
        option_params.append(selected_artist)
    if selected_project:
        where_parts.append("project_name = ?")
        params.append(selected_project)
    if selected_status:
        where_parts.append("status = ?")
        params.append(selected_status)
        option_where_parts.append("status = ?")
        option_params.append(selected_status)
    with booking_connect() as conn:
        ensure_finance_movement_employee_columns(conn)
        ensure_finance_account_entries_table(conn)
        scope_sql = apply_artist_scope_sql(conn, x_vpo_username, "finance_movements", params)
        option_scope_sql = apply_artist_scope_sql(conn, x_vpo_username, "finance_movements", option_params)
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else "WHERE 1 = 1"
        where += scope_sql
        option_where = f"WHERE {' AND '.join(option_where_parts)}" if option_where_parts else "WHERE 1 = 1"
        option_where += option_scope_sql

        rows = conn.execute(
            f"""
            SELECT
                id, movement_date, artist, business_area, movement_type, category,
                project_id, project_name, concept, counterparty, paid_by,
                paid_by_employee_id, paid_by_employee_name,
                amount, currency, fx_rate, amount_ars,
                paid_amount, paid_amount_ars, pending_amount_ars, payment_status, due_date,
                recoverable,
                recoverable_percent, recovery_method, artist_percent, producer_percent,
                account_effect, status, source_type, source_id,
                proof_refs_json, created_by, notes, created_at, updated_at
            FROM finance_staging_movements
            {where}
            ORDER BY movement_date DESC, id DESC
            LIMIT ?
            """,
            [*params, safe_limit],
        ).fetchall()
        summary_rows = conn.execute(
            f"""
            SELECT
                status,
                COUNT(*) AS rows,
                SUM(COALESCE(amount_ars, 0)) AS amount_ars,
                SUM(COALESCE(paid_amount_ars, 0)) AS paid_amount_ars,
                SUM(COALESCE(pending_amount_ars, 0)) AS pending_amount_ars
            FROM finance_staging_movements
            {where}
            GROUP BY status
            ORDER BY status
            """,
            params,
        ).fetchall()
        project_options = conn.execute(
            f"""
            SELECT DISTINCT project_name AS name
            FROM finance_staging_movements
            {option_where}
            AND project_name IS NOT NULL
            AND TRIM(project_name) != ''
            ORDER BY project_name
            """,
            option_params,
        ).fetchall()
        project_params: list = []
        project_scope_sql = apply_artist_scope_sql(conn, x_vpo_username, "finance_movements", project_params)
        projects = conn.execute(
            f"""
            SELECT id, name, artist, business_area, status, notes, created_at, updated_at
            FROM finance_projects
            WHERE 1 = 1
              {project_scope_sql}
            ORDER BY COALESCE(artist, ''), business_area, name
            """,
            project_params,
        ).fetchall()
        distinct_artist_params: list = []
        distinct_artist_scope_sql = apply_artist_scope_sql(conn, x_vpo_username, "finance_movements", distinct_artist_params)
        distinct_artist_rows = conn.execute(
            f"""
            SELECT DISTINCT artist
            FROM finance_staging_movements
            WHERE artist IS NOT NULL
              AND TRIM(artist) != ''
              {distinct_artist_scope_sql}
            ORDER BY artist
            """,
            distinct_artist_params,
        ).fetchall()
        reimbursement_params: list = []
        reimbursement_where = "WHERE origin_type = 'finance_employee_reimbursement'"
        reimbursement_where += " AND status IN ('open', 'partial', 'observed')"
        if selected_artist:
            reimbursement_where += " AND artist = ?"
            reimbursement_params.append(selected_artist)
        reimbursement_where += apply_artist_scope_sql(conn, x_vpo_username, "finance_movements", reimbursement_params)
        reimbursement_rows = conn.execute(
            f"""
            WITH applied AS (
                SELECT account_entry_id, SUM(amount_ars) AS applied_amount_ars
                FROM finance_account_applications
                GROUP BY account_entry_id
            )
            SELECT
                counterparty AS employee_name,
                COUNT(*) AS rows,
                SUM(
                    CASE
                        WHEN COALESCE(fae.amount_ars, 0) - COALESCE(applied.applied_amount_ars, 0) > 0
                        THEN COALESCE(fae.amount_ars, 0) - COALESCE(applied.applied_amount_ars, 0)
                        ELSE 0
                    END
                ) AS amount_ars,
                MIN(entry_date) AS first_date,
                MAX(entry_date) AS last_date
            FROM finance_account_entries fae
            LEFT JOIN applied ON applied.account_entry_id = fae.id
            {reimbursement_where}
            GROUP BY counterparty
            ORDER BY counterparty
            """,
            reimbursement_params,
        ).fetchall()
        reimbursement_detail_rows = conn.execute(
            f"""
            WITH applied AS (
                SELECT account_entry_id, SUM(amount_ars) AS applied_amount_ars
                FROM finance_account_applications
                GROUP BY account_entry_id
            )
            SELECT
                fae.id, artist, counterparty AS employee_name, entry_date,
                origin_id AS movement_id, concept, fae.amount_ars, status, notes,
                COALESCE(applied.applied_amount_ars, 0) AS applied_amount_ars,
                CASE
                    WHEN COALESCE(fae.amount_ars, 0) - COALESCE(applied.applied_amount_ars, 0) > 0
                    THEN COALESCE(fae.amount_ars, 0) - COALESCE(applied.applied_amount_ars, 0)
                    ELSE 0
                END AS balance_ars
            FROM finance_account_entries fae
            LEFT JOIN applied ON applied.account_entry_id = fae.id
            {reimbursement_where}
            ORDER BY entry_date DESC, id DESC
            LIMIT 200
            """,
            reimbursement_params,
        ).fetchall()
        movement_ids = [int(row["id"]) for row in rows]
        allocation_map = finance_allocation_rows_for_ids(conn, movement_ids)
        document_map = finance_document_rows_for_ids(conn, movement_ids)
        movement_items = []
        for row in rows:
            item = finance_movement_item(row)
            item["allocation_lines"] = allocation_map.get(int(row["id"]), [])
            item["document_detail"] = document_map.get(int(row["id"]))
            movement_items.append(item)
        artists = sorted(set([
            *filter_artists_by_scope(booking_artist_options(), conn, x_vpo_username, "finance_movements"),
            *[row["artist"] for row in distinct_artist_rows if row["artist"]],
        ]), key=lambda value: value.casefold())

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "selected_artist": selected_artist,
        "selected_project": selected_project,
        "artists": artists,
        "items": movement_items,
        "projects": [dict(row) for row in projects],
        "project_options": [row["name"] for row in project_options],
        "employee_reimbursements": {
            "summary": [
                {
                    "employee_name": row["employee_name"],
                    "rows": int(row["rows"] or 0),
                    "amount_ars": float(row["amount_ars"] or 0),
                    "first_date": row["first_date"],
                    "last_date": row["last_date"],
                }
                for row in reimbursement_rows
            ],
            "items": [
                {
                    "id": int(row["id"]),
                    "artist": row["artist"],
                    "employee_name": row["employee_name"],
                    "entry_date": row["entry_date"],
                    "movement_id": int(row["movement_id"] or 0),
                    "concept": row["concept"],
                    "amount_ars": float(row["amount_ars"] or 0),
                    "applied_amount_ars": float(row["applied_amount_ars"] or 0),
                    "balance_ars": float(row["balance_ars"] or 0),
                    "status": row["status"],
                    "notes": row["notes"],
                }
                for row in reimbursement_detail_rows
            ],
        },
        "summary": {
            "rows": sum(int(row["rows"] or 0) for row in summary_rows),
            "amount_ars": sum(float(row["amount_ars"] or 0) for row in summary_rows),
            "paid_amount_ars": sum(float(row["paid_amount_ars"] or 0) for row in summary_rows),
            "pending_amount_ars": sum(float(row["pending_amount_ars"] or 0) for row in summary_rows),
            "by_status": [dict(row) for row in summary_rows],
            "official": False,
            "note": "Staging financiero: carga y control. Todavia no impacta automaticamente el ledger oficial.",
        },
    }


@app.post("/finance/movements")
def create_finance_movement(
    request: FinanceMovementRequest,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    now = datetime.now().isoformat(timespec="seconds")
    amount_ars = finance_amount_ars(request.amount, request.currency, request.fx_rate)
    validate_finance_document_request(request)
    paid_amount = request.amount if request.paid_amount is None else request.paid_amount
    paid_amount_ars = finance_amount_ars(paid_amount, request.currency, request.fx_rate)
    pending_amount_ars = max(amount_ars - paid_amount_ars, 0.0)
    payment_status = finance_payment_status(amount_ars, paid_amount_ars, request.payment_status)

    with booking_connect() as conn:
        ensure_finance_movement_employee_columns(conn)
        ensure_finance_account_entries_table(conn)
        movement_artist = clean_booking_artist(request.artist) or request.artist.strip()
        require_module_permission(
            conn,
            x_vpo_username,
            "finance_movements",
            "create",
            artist=movement_artist,
        )
        if is_payroll_compensation_movement(request.business_area, request.category, request.movement_type):
            require_module_permission(
                conn,
                x_vpo_username,
                "payroll_compensation",
                "create",
            )
        paid_by_employee = None
        if request.paid_by == "empleado":
            paid_by_employee = finance_employee_option_from_id(conn, request.paid_by_employee_id)
            if paid_by_employee is None:
                raise HTTPException(status_code=400, detail="Elegí el empleado que pagó el gasto.")
        project_id, project_name = resolve_finance_project(conn, request, now)
        cursor = conn.execute(
            """
            INSERT INTO finance_staging_movements (
                movement_date, artist, business_area, movement_type, category,
                project_id, project_name, concept, counterparty, paid_by,
                paid_by_employee_id, paid_by_employee_name,
                amount, currency, fx_rate, amount_ars,
                paid_amount, paid_amount_ars, pending_amount_ars, payment_status, due_date,
                recoverable,
                recoverable_percent, recovery_method, artist_percent, producer_percent,
                account_effect, status, source_type, source_id,
                proof_refs_json, created_by, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.movement_date,
                request.artist.strip(),
                request.business_area,
                request.movement_type,
                request.category.strip(),
                project_id,
                project_name,
                request.concept.strip(),
                clean_optional_text(request.counterparty),
                request.paid_by,
                paid_by_employee["id"] if paid_by_employee else None,
                paid_by_employee["display_name"] if paid_by_employee else None,
                request.amount,
                request.currency,
                request.fx_rate,
                amount_ars,
                paid_amount,
                paid_amount_ars,
                pending_amount_ars,
                payment_status,
                clean_optional_text(request.due_date),
                1 if request.recoverable else 0,
                request.recoverable_percent,
                request.recovery_method if request.recoverable else "none",
                request.artist_percent,
                request.producer_percent,
                request.account_effect,
                request.status,
                request.source_type,
                clean_optional_text(request.source_id),
                json.dumps(request.proof_refs, ensure_ascii=False),
                clean_username(x_vpo_username or "") or None,
                clean_optional_text(request.notes),
                now,
                now,
            ),
        )
        movement_id = int(cursor.lastrowid)
        replace_finance_movement_allocations(conn, movement_id, request, amount_ars, now)
        replace_employee_reimbursement_account_entry(
            conn,
            movement_id,
            request,
            amount_ars,
            paid_amount_ars,
            paid_by_employee,
            now,
        )
        replace_finance_account_applications(conn, movement_id, request, amount_ars, now, x_vpo_username)
        document_detail = replace_finance_document_detail(conn, movement_id, request, amount_ars, now, x_vpo_username)
        row = conn.execute(
            """
            SELECT *
            FROM finance_staging_movements
            WHERE id = ?
            """,
            (movement_id,),
        ).fetchone()
        item = finance_movement_item(row)
        item["allocation_lines"] = finance_allocation_rows_for_ids(conn, [movement_id]).get(movement_id, [])
        item["document_detail"] = document_detail

    return {
        "item": item,
    }


@app.put("/finance/movements/{movement_id}")
def update_finance_movement(
    movement_id: int,
    request: FinanceMovementRequest,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    now = datetime.now().isoformat(timespec="seconds")
    amount_ars = finance_amount_ars(request.amount, request.currency, request.fx_rate)
    validate_finance_document_request(request)
    paid_amount = request.amount if request.paid_amount is None else request.paid_amount
    paid_amount_ars = finance_amount_ars(paid_amount, request.currency, request.fx_rate)
    pending_amount_ars = max(amount_ars - paid_amount_ars, 0.0)
    payment_status = finance_payment_status(amount_ars, paid_amount_ars, request.payment_status)

    with booking_connect() as conn:
        ensure_finance_movement_employee_columns(conn)
        ensure_finance_account_entries_table(conn)
        ensure_finance_account_applications_table(conn)
        existing = conn.execute(
            "SELECT id, artist, status FROM finance_staging_movements WHERE id = ?",
            (movement_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Movimiento financiero no encontrado.")
        if finance_movement_is_locked(existing["status"]):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Movimiento financiero bloqueado. "
                    "Los movimientos aprobados, aplicados o anulados no se editan: "
                    "se corrigen con un nuevo movimiento."
                ),
            )

        movement_artist = clean_booking_artist(request.artist) or request.artist.strip()
        existing_artist = clean_booking_artist(existing["artist"]) if existing else ""
        require_module_permission(
            conn,
            x_vpo_username,
            "finance_movements",
            "edit",
            artist=movement_artist,
            existing_artist=existing_artist,
        )
        if is_payroll_compensation_movement(request.business_area, request.category, request.movement_type):
            require_module_permission(
                conn,
                x_vpo_username,
                "payroll_compensation",
                "edit",
            )
        paid_by_employee = None
        if request.paid_by == "empleado":
            paid_by_employee = finance_employee_option_from_id(conn, request.paid_by_employee_id)
            if paid_by_employee is None:
                raise HTTPException(status_code=400, detail="Elegí el empleado que pagó el gasto.")

        project_id, project_name = resolve_finance_project(conn, request, now)
        conn.execute(
            """
            UPDATE finance_staging_movements
            SET movement_date = ?,
                artist = ?,
                business_area = ?,
                movement_type = ?,
                category = ?,
                project_id = ?,
                project_name = ?,
                concept = ?,
                counterparty = ?,
                paid_by = ?,
                paid_by_employee_id = ?,
                paid_by_employee_name = ?,
                amount = ?,
                currency = ?,
                fx_rate = ?,
                amount_ars = ?,
                paid_amount = ?,
                paid_amount_ars = ?,
                pending_amount_ars = ?,
                payment_status = ?,
                due_date = ?,
                recoverable = ?,
                recoverable_percent = ?,
                recovery_method = ?,
                artist_percent = ?,
                producer_percent = ?,
                account_effect = ?,
                status = ?,
                source_type = ?,
                source_id = ?,
                proof_refs_json = ?,
                notes = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                request.movement_date,
                request.artist.strip(),
                request.business_area,
                request.movement_type,
                request.category.strip(),
                project_id,
                project_name,
                request.concept.strip(),
                clean_optional_text(request.counterparty),
                request.paid_by,
                paid_by_employee["id"] if paid_by_employee else None,
                paid_by_employee["display_name"] if paid_by_employee else None,
                request.amount,
                request.currency,
                request.fx_rate,
                amount_ars,
                paid_amount,
                paid_amount_ars,
                pending_amount_ars,
                payment_status,
                clean_optional_text(request.due_date),
                1 if request.recoverable else 0,
                request.recoverable_percent,
                request.recovery_method if request.recoverable else "none",
                request.artist_percent,
                request.producer_percent,
                request.account_effect,
                request.status,
                request.source_type,
                clean_optional_text(request.source_id),
                json.dumps(request.proof_refs, ensure_ascii=False),
                clean_optional_text(request.notes),
                now,
                movement_id,
            ),
        )
        replace_finance_movement_allocations(conn, movement_id, request, amount_ars, now)
        replace_employee_reimbursement_account_entry(
            conn,
            movement_id,
            request,
            amount_ars,
            paid_amount_ars,
            paid_by_employee,
            now,
        )
        replace_finance_account_applications(conn, movement_id, request, amount_ars, now, x_vpo_username)
        document_detail = replace_finance_document_detail(conn, movement_id, request, amount_ars, now, x_vpo_username)
        row = conn.execute(
            "SELECT * FROM finance_staging_movements WHERE id = ?",
            (movement_id,),
        ).fetchone()
        item = finance_movement_item(row)
        item["allocation_lines"] = finance_allocation_rows_for_ids(conn, [movement_id]).get(movement_id, [])
        item["document_detail"] = document_detail

    return {
        "item": item,
    }


@app.get("/finance/documents/{document_id}/pdf")
def finance_document_pdf(
    document_id: int,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> Response:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    with booking_connect() as conn:
        ensure_finance_documents_table(conn)
        row = conn.execute(
            """
            SELECT
                r.*,
                m.artist AS movement_artist,
                m.business_area,
                m.movement_type,
                m.category,
                m.concept AS movement_concept,
                m.notes AS movement_notes
            FROM finance_documents r
            JOIN finance_staging_movements m ON m.id = r.movement_id
            WHERE r.id = ?
            """,
            (document_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Documento financiero no encontrado.")
        document = finance_document_item(row)
        movement = {
            "artist": row["movement_artist"],
            "business_area": row["business_area"],
            "movement_type": row["movement_type"],
            "category": row["category"],
            "concept": row["movement_concept"],
            "notes": row["movement_notes"],
        }
        require_module_permission(
            conn,
            x_vpo_username,
            "finance_movements",
            "access",
            artist=clean_booking_artist(row["movement_artist"]) or row["movement_artist"],
        )

    pdf_bytes = finance_document_pdf_bytes(document, movement)
    filename = f"documento_financiero_{int(document['document_number']):06d}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.get("/booking/artists")
def booking_artists(
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    artists = booking_artist_options()
    with booking_connect() as conn:
        artists = filter_artists_by_scope(artists, conn, x_vpo_username, "booking")
    return {
        "items": artists,
    }


@app.get("/booking/artist-records")
def booking_artist_records(
    include_inactive: bool = False,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    where = "" if include_inactive else "WHERE active = 1"
    with booking_connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM booking_artists
            {where}
            ORDER BY active DESC, stage_name
            """
        ).fetchall()

    return {
        "items": [row_to_booking_artist(row) for row in rows],
    }


@app.post("/booking/artist-records")
def create_booking_artist_record(
    request: BookingArtistRecordRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    stage_name = clean_booking_artist(request.stage_name)
    if not stage_name:
        raise HTTPException(status_code=400, detail="stage_name is required.")

    now = datetime.now().isoformat(timespec="seconds")
    with booking_connect() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO booking_artists (
                    stage_name, legal_name, cuit, phone, email, address,
                    notes, active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stage_name,
                    clean_optional_text(request.legal_name),
                    clean_optional_text(request.cuit),
                    clean_optional_text(request.phone),
                    clean_optional_text(request.email),
                    clean_optional_text(request.address),
                    clean_optional_text(request.notes),
                    1 if request.active else 0,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Artist already exists.") from exc

        row = conn.execute("SELECT * FROM booking_artists WHERE id = ?", (cursor.lastrowid,)).fetchone()

    return {
        "item": row_to_booking_artist(row),
    }


@app.put("/booking/artist-records/{artist_id}")
def update_booking_artist_record(
    artist_id: int,
    request: BookingArtistRecordRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    stage_name = clean_booking_artist(request.stage_name)
    if not stage_name:
        raise HTTPException(status_code=400, detail="stage_name is required.")

    now = datetime.now().isoformat(timespec="seconds")
    with booking_connect() as conn:
        existing = conn.execute("SELECT id FROM booking_artists WHERE id = ?", (artist_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Artist not found.")

        try:
            conn.execute(
                """
                UPDATE booking_artists
                SET stage_name = ?,
                    legal_name = ?,
                    cuit = ?,
                    phone = ?,
                    email = ?,
                    address = ?,
                    notes = ?,
                    active = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    stage_name,
                    clean_optional_text(request.legal_name),
                    clean_optional_text(request.cuit),
                    clean_optional_text(request.phone),
                    clean_optional_text(request.email),
                    clean_optional_text(request.address),
                    clean_optional_text(request.notes),
                    1 if request.active else 0,
                    now,
                    artist_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Artist already exists.") from exc

        row = conn.execute("SELECT * FROM booking_artists WHERE id = ?", (artist_id,)).fetchone()

    return {
        "item": row_to_booking_artist(row),
    }


@app.delete("/booking/artist-records/{artist_id}")
def deactivate_booking_artist_record(
    artist_id: int,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    now = datetime.now().isoformat(timespec="seconds")
    with booking_connect() as conn:
        existing = conn.execute("SELECT id FROM booking_artists WHERE id = ?", (artist_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Artist not found.")

        conn.execute(
            """
            UPDATE booking_artists
            SET active = 0,
                updated_at = ?
            WHERE id = ?
            """,
            (now, artist_id),
        )
        row = conn.execute("SELECT * FROM booking_artists WHERE id = ?", (artist_id,)).fetchone()

    return {
        "item": row_to_booking_artist(row),
    }


@app.get("/employees")
def employee_records(
    include_inactive: bool = False,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    if operational_db_settings().driver == "sqlite":
        init_booking_db()

    where = "" if include_inactive else "WHERE active = ?"
    params = () if include_inactive else (db_bool(True),)
    with operational_connect() as conn:
        ensure_employee_compensation_columns(conn)
        employees_permission = require_module_permission(conn, x_vpo_username, "employees", "access")
        payroll_permission = user_module_permission(conn, x_vpo_username, "payroll_compensation")
        can_manage_employees = bool(
            employees_permission.get("is_admin")
            or employees_permission.get("can_edit")
            or employees_permission.get("can_approve")
        )
        can_view_compensation = bool(
            payroll_permission.get("allowed")
            and payroll_permission.get("can_access")
        )
        rows = conn.execute(
            db_sql(
                conn,
                f"""
            SELECT *
            FROM employees
            {where}
            ORDER BY active DESC, display_name
            """,
            ),
            params,
        ).fetchall()
        items = []
        for row in rows:
            item = row_to_employee(conn, row)
            if not can_view_compensation:
                item["compensation_type"] = "none"
                item["salary_amount"] = 0.0
                item["salary_currency"] = "ARS"
                item["salary_frequency"] = "monthly"
                item["salary_notes"] = None
            if not can_manage_employees:
                item["users"] = []
                item["permissions"] = []
            items.append(item)

        return {
            "items": items,
            "function_options": EMPLOYEE_FUNCTION_OPTIONS,
            "modules": [{"module_key": key, "label": label} for key, label in APP_MODULES],
            "db_driver": operational_db_settings().driver,
        }


@app.get("/employees/finance-options")
def employee_finance_options(
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    if operational_db_settings().driver == "sqlite":
        init_booking_db()

    with operational_connect() as conn:
        ensure_employee_compensation_columns(conn)
        require_module_permission(conn, x_vpo_username, "finance_movements", "access")
        payroll_permission = user_module_permission(conn, x_vpo_username, "payroll_compensation")
        can_view_compensation = bool(
            payroll_permission.get("allowed")
            and payroll_permission.get("can_access")
        )
        rows = conn.execute(
            db_sql(
                conn,
                """
            SELECT id, display_name, compensation_type, salary_amount,
                   salary_currency, salary_frequency, active, created_at, updated_at
            FROM employees
            WHERE active = ?
            ORDER BY display_name
            """,
            ),
            (db_bool(True),),
        ).fetchall()

        items = []
        for row in rows:
            functions = conn.execute(
                db_sql(
                    conn,
                    """
                SELECT function_code
                FROM employee_functions
                WHERE employee_id = ?
                ORDER BY function_code
                """,
                ),
                (row["id"],),
            ).fetchall()
            items.append({
                "id": row["id"],
                "display_name": row["display_name"],
                "compensation_type": (row["compensation_type"] or "none") if can_view_compensation else "none",
                "salary_amount": float(row["salary_amount"] or 0) if can_view_compensation else 0.0,
                "salary_currency": (row["salary_currency"] or "ARS") if can_view_compensation else "ARS",
                "salary_frequency": (row["salary_frequency"] or "monthly") if can_view_compensation else "monthly",
                "active": bool(row["active"]),
                "functions": [item["function_code"] for item in functions],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })

        return {
            "items": items,
            "db_driver": operational_db_settings().driver,
        }


@app.get("/employees/commission-options")
def employee_commission_options(
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    with booking_connect() as conn:
        ensure_employee_compensation_columns(conn)
        permission = require_module_permission(conn, x_vpo_username, "booking_commissions", "access")
        employee_filter_sql = ""
        params: list = []
        if not (permission.get("is_admin") or permission.get("can_edit") or permission.get("can_approve")):
            username = clean_username(x_vpo_username or "")
            user = conn.execute(
                """
                SELECT employee_id
                FROM app_users
                WHERE lower(username) = lower(?)
                  AND active = 1
                """,
                (username,),
            ).fetchone()
            if user is None or user["employee_id"] is None:
                return {"items": [], "db_driver": operational_db_settings().driver}
            employee_filter_sql = " AND id = ?"
            params.append(user["employee_id"])
        rows = conn.execute(
            f"""
            SELECT id, display_name, active, created_at, updated_at
            FROM employees
            WHERE active = 1
              {employee_filter_sql}
            ORDER BY display_name
            """,
            params,
        ).fetchall()
        items = []
        for row in rows:
            functions = conn.execute(
                """
                SELECT function_code
                FROM employee_functions
                WHERE employee_id = ?
                ORDER BY function_code
                """,
                (row["id"],),
            ).fetchall()
            permission = conn.execute(
                """
                SELECT module_key, can_access, can_create, can_view_history,
                       can_edit, can_approve, scope_json, notes
                FROM module_permissions
                WHERE employee_id = ?
                  AND module_key = 'booking_commissions'
                """,
                (row["id"],),
            ).fetchone()
            permissions = []
            if permission is not None:
                permissions.append({
                    "module_key": permission["module_key"],
                    "can_access": bool(permission["can_access"]),
                    "can_create": bool(permission["can_create"]),
                    "can_view_history": bool(permission["can_view_history"]),
                    "can_edit": bool(permission["can_edit"]),
                    "can_approve": bool(permission["can_approve"]),
                    "scope": parse_scope_payload(permission["scope_json"]),
                    "notes": permission["notes"],
                })
            items.append({
                "id": int(row["id"]),
                "display_name": row["display_name"],
                "active": bool(row["active"]),
                "functions": [item["function_code"] for item in functions],
                "permissions": permissions,
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            })

        return {
            "items": items,
            "db_driver": operational_db_settings().driver,
        }


@app.get("/me/permissions")
def current_user_permissions(
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    if operational_db_settings().driver == "sqlite":
        init_booking_db()

    username = clean_username(x_vpo_username or "")
    if not username:
        raise HTTPException(status_code=401, detail="Usuario requerido.")

    with operational_connect() as conn:
        user = conn.execute(
            db_sql(
                conn,
                """
            SELECT u.*, e.id AS employee_ref, e.display_name
            FROM app_users u
            LEFT JOIN employees e ON e.id = u.employee_id
            WHERE lower(u.username) = lower(?)
              AND u.active = ?
            """,
            ),
            (username, db_bool(True)),
        ).fetchone()
        if user is None:
            raise HTTPException(status_code=401, detail="Usuario no autorizado.")

        if str(user["global_role"] or "").lower() == "admin":
            permissions = [
                {
                    "module_key": key,
                    "can_access": True,
                    "can_create": True,
                    "can_view_history": True,
                    "can_edit": True,
                    "can_approve": True,
                    "scope": [{"scope_type": "all", "scope_ref": "*"}],
                    "notes": None,
                }
                for key, _label in APP_MODULES
                if key != "home"
            ]
        else:
            employee_id = user["employee_ref"]
            if employee_id is None:
                permissions = []
            else:
                rows = conn.execute(
                    db_sql(
                        conn,
                        """
                    SELECT module_key, can_access, can_create, can_view_history,
                           can_edit, can_approve, scope_json, notes
                    FROM module_permissions
                    WHERE employee_id = ?
                    ORDER BY module_key
                    """,
                    ),
                    (employee_id,),
                ).fetchall()
                permissions = [
                    {
                        "module_key": row["module_key"],
                        "can_access": bool(row["can_access"]),
                        "can_create": bool(row["can_create"]),
                        "can_view_history": bool(row["can_view_history"]),
                        "can_edit": bool(row["can_edit"]),
                        "can_approve": bool(row["can_approve"]),
                        "scope": parse_scope_payload(row["scope_json"]),
                        "notes": row["notes"],
                    }
                    for row in rows
                    if bool(row["can_access"])
                ]

        return {
            "user": row_to_session_user(user),
            "employee": {
                "id": user["employee_ref"],
                "display_name": user["display_name"],
            },
            "permissions": permissions,
            "modules": [{"module_key": key, "label": label} for key, label in APP_MODULES if key != "home"],
            "db_driver": operational_db_settings().driver,
        }


@app.post("/auth/login")
def operational_login(
    request: AuthLoginRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    if operational_db_settings().driver == "sqlite":
        init_booking_db()
    username = clean_username(request.username)
    if not username:
        raise HTTPException(status_code=401, detail="Usuario o contrasena incorrectos.")

    with operational_connect() as conn:
        row = conn.execute(
            db_sql(
                conn,
                """
            SELECT *
            FROM app_users
            WHERE lower(username) = lower(?)
              AND active = ?
            """,
            ),
            (username, db_bool(True)),
        ).fetchone()
        if row is None or not verify_web_password(request.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Usuario o contrasena incorrectos.")

        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            db_sql(conn, "UPDATE app_users SET last_login_at = ?, updated_at = ? WHERE id = ?"),
            (now, now, row["id"]),
        )
        updated = conn.execute(db_sql(conn, "SELECT * FROM app_users WHERE id = ?"), (row["id"],)).fetchone()
        return {"ok": True, "user": row_to_session_user(updated)}


@app.post("/auth/session")
def operational_session(
    request: AuthSessionRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    if operational_db_settings().driver == "sqlite":
        init_booking_db()
    username = clean_username(request.username)
    if not username:
        raise HTTPException(status_code=401, detail="Sesion invalida.")

    with operational_connect() as conn:
        row = conn.execute(
            db_sql(
                conn,
                """
            SELECT *
            FROM app_users
            WHERE lower(username) = lower(?)
              AND active = ?
            """,
            ),
            (username, db_bool(True)),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="Sesion invalida.")
        return {"ok": True, "user": row_to_session_user(row)}


@app.post("/auth/change-password")
def operational_change_password(
    request: AuthChangePasswordRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    if operational_db_settings().driver == "sqlite":
        init_booking_db()
    username = clean_username(request.username)
    if not username:
        raise HTTPException(status_code=400, detail="Usuario invalido.")
    if request.new_password == DEFAULT_WEB_PASSWORD:
        raise HTTPException(status_code=400, detail="La nueva contrasena no puede ser la clave default.")

    with operational_connect() as conn:
        row = conn.execute(
            db_sql(
                conn,
                """
            SELECT *
            FROM app_users
            WHERE lower(username) = lower(?)
              AND active = ?
            """,
            ),
            (username, db_bool(True)),
        ).fetchone()
        if row is None or not verify_web_password(request.current_password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Contrasena actual incorrecta.")

        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            db_sql(
                conn,
                """
            UPDATE app_users
            SET password_hash = ?,
                must_change_password = ?,
                updated_at = ?
            WHERE id = ?
            """,
            ),
            (hash_web_password(request.new_password), db_bool(False), now, row["id"]),
        )
        updated = conn.execute(db_sql(conn, "SELECT * FROM app_users WHERE id = ?"), (row["id"],)).fetchone()
        return {"ok": True, "user": row_to_session_user(updated)}


@app.post("/employees")
def create_employee_record(
    request: EmployeeRecordRequest,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    display_name = clean_optional_text(request.display_name)
    if not display_name:
        raise HTTPException(status_code=400, detail="display_name is required.")

    now = datetime.now().isoformat(timespec="seconds")
    with booking_connect() as conn:
        ensure_employee_compensation_columns(conn)
        require_module_permission(conn, x_vpo_username, "employees", "create")
        try:
            cursor = conn.execute(
                db_sql(
                    conn,
                    """
                INSERT INTO employees (
                    display_name, legal_name, cuit, phone, email, address,
                    compensation_type, salary_amount, salary_currency, salary_frequency,
                    salary_notes, notes, active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                ),
                (
                    display_name,
                    clean_optional_text(request.legal_name) or display_name,
                    clean_optional_text(request.cuit),
                    clean_optional_text(request.phone),
                    clean_optional_text(request.email),
                    clean_optional_text(request.address),
                    request.compensation_type,
                    request.salary_amount,
                    request.salary_currency,
                    request.salary_frequency,
                    clean_optional_text(request.salary_notes),
                    clean_optional_text(request.notes),
                    db_bool(request.active),
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Employee already exists.") from exc

        returned = cursor.fetchone()
        employee_id = int(returned["id"] if returned else cursor.lastrowid)
        upsert_employee_functions(conn, employee_id, request.functions)
        upsert_employee_user(conn, employee_id, request.username, request.user_role, request.user_active)
        if request.permissions is not None:
            upsert_employee_permissions(conn, employee_id, request.permissions)
        if not request.permissions or not any(
            permission.module_key == "booking_agenda" for permission in request.permissions
        ):
            upsert_employee_permissions(
                conn,
                employee_id,
                [
                    EmployeePermissionRequest(
                        module_key="booking_agenda",
                        can_access=True,
                        can_view_history=True,
                        scope=[{"scope_type": "all", "scope_ref": "*"}],
                        notes="Acceso inicial de lectura a la Agenda Booking.",
                    )
                ],
            )
        if display_name.casefold() == "ruben elkowich":
            grant_employee_all_permissions(conn, employee_id)
            upsert_employee_user(
                conn,
                employee_id,
                request.username or generated_employee_username(display_name) or "rubene",
                "admin",
                True,
                "operational",
                request.password,
                request.must_change_password,
            )
        elif request.username:
            upsert_employee_user(
                conn,
                employee_id,
                request.username,
                request.user_role,
                request.user_active,
                "operational",
                request.password,
                request.must_change_password,
            )
        row = conn.execute(db_sql(conn, "SELECT * FROM employees WHERE id = ?"), (employee_id,)).fetchone()

        return {
            "item": row_to_employee(conn, row),
        }


@app.put("/employees/{employee_id}")
def update_employee_record(
    employee_id: int,
    request: EmployeeRecordRequest,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    display_name = clean_optional_text(request.display_name)
    if not display_name:
        raise HTTPException(status_code=400, detail="display_name is required.")

    now = datetime.now().isoformat(timespec="seconds")
    with booking_connect() as conn:
        ensure_employee_compensation_columns(conn)
        require_module_permission(conn, x_vpo_username, "employees", "edit")
        existing = conn.execute(db_sql(conn, "SELECT id FROM employees WHERE id = ?"), (employee_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Employee not found.")

        try:
            conn.execute(
                db_sql(
                    conn,
                    """
                UPDATE employees
                SET display_name = ?,
                    legal_name = ?,
                    cuit = ?,
                    phone = ?,
                    email = ?,
                    address = ?,
                    compensation_type = ?,
                    salary_amount = ?,
                    salary_currency = ?,
                    salary_frequency = ?,
                    salary_notes = ?,
                    notes = ?,
                    active = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                ),
                (
                    display_name,
                    clean_optional_text(request.legal_name) or display_name,
                    clean_optional_text(request.cuit),
                    clean_optional_text(request.phone),
                    clean_optional_text(request.email),
                    clean_optional_text(request.address),
                    request.compensation_type,
                    request.salary_amount,
                    request.salary_currency,
                    request.salary_frequency,
                    clean_optional_text(request.salary_notes),
                    clean_optional_text(request.notes),
                    db_bool(request.active),
                    now,
                    employee_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Employee already exists.") from exc

        upsert_employee_functions(conn, employee_id, request.functions)
        upsert_employee_user(conn, employee_id, request.username, request.user_role, request.user_active)
        if request.permissions is not None:
            upsert_employee_permissions(conn, employee_id, request.permissions)
        if display_name.casefold() == "ruben elkowich":
            grant_employee_all_permissions(conn, employee_id)
            upsert_employee_user(
                conn,
                employee_id,
                request.username or generated_employee_username(display_name) or "rubene",
                "admin",
                True,
                "operational",
                request.password,
                request.must_change_password,
            )
        elif request.username:
            upsert_employee_user(
                conn,
                employee_id,
                request.username,
                request.user_role,
                request.user_active,
                "operational",
                request.password,
                request.must_change_password,
            )
        row = conn.execute(db_sql(conn, "SELECT * FROM employees WHERE id = ?"), (employee_id,)).fetchone()

        return {
            "item": row_to_employee(conn, row),
        }


@app.post("/employees/{employee_id}/password")
def set_employee_password(
    employee_id: int,
    request: EmployeePasswordRequest,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    password = DEFAULT_WEB_PASSWORD if request.use_default else request.password
    if not password:
        raise HTTPException(status_code=400, detail="Password is required.")
    init_booking_db()
    now = datetime.now().isoformat(timespec="seconds")
    with booking_connect() as conn:
        ensure_employee_compensation_columns(conn)
        require_module_permission(conn, x_vpo_username, "employees", "edit")
        employee = conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
        if employee is None:
            raise HTTPException(status_code=404, detail="Employee not found.")
        user = conn.execute(
            """
            SELECT *
            FROM app_users
            WHERE employee_id = ?
              AND active = 1
            ORDER BY username
            LIMIT 1
            """,
            (employee_id,),
        ).fetchone()
        if user is None:
            username = generated_employee_username(employee["display_name"])
            if not username:
                raise HTTPException(status_code=400, detail="El empleado no tiene usuario web.")
            upsert_employee_user(
                conn,
                employee_id,
                username,
                "admin" if str(employee["display_name"] or "").casefold() == "ruben elkowich" else "viewer",
                True,
                "operational",
                password,
                request.must_change_password,
            )
        else:
            conn.execute(
                """
                UPDATE app_users
                SET password_hash = ?,
                    must_change_password = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    hash_web_password(password),
                    db_bool(request.must_change_password),
                    now,
                    user["id"],
                ),
            )
        row = conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
        return {
            "item": row_to_employee(conn, row),
        }


@app.delete("/employees/{employee_id}")
def deactivate_employee_record(
    employee_id: int,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    now = datetime.now().isoformat(timespec="seconds")
    with booking_connect() as conn:
        ensure_employee_compensation_columns(conn)
        require_module_permission(conn, x_vpo_username, "employees", "edit")
        existing = conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Employee not found.")
        if str(existing["display_name"] or "").casefold() == "ruben elkowich":
            raise HTTPException(status_code=400, detail="Ruben Elkowich no puede desactivarse.")

        conn.execute(
            """
            UPDATE employees
            SET active = 0,
                updated_at = ?
            WHERE id = ?
            """,
            (now, employee_id),
        )
        row = conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()

        return {
            "item": row_to_employee(conn, row),
        }


def fetch_caserio_event_item(conn: sqlite3.Connection, event_id: int) -> dict:
    row = conn.execute("SELECT * FROM caserio_events WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Caserio event not found.")

    item = row_to_caserio_event(row)
    lines = conn.execute(
        """
        SELECT *
        FROM caserio_event_lines
        WHERE event_id = ?
        ORDER BY id
        """,
        (event_id,),
    ).fetchall()
    item["lines"] = [dict(line) for line in lines]
    return item


def row_to_booking_composite_event(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["receipt_refs"] = json.loads(item.pop("receipt_refs_json") or "[]")
    return item


def fetch_booking_composite_event_item(conn: sqlite3.Connection, event_id: int) -> dict:
    row = conn.execute("SELECT * FROM booking_composite_events WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Composite booking event not found.")

    item = row_to_booking_composite_event(row)
    expense_rows = conn.execute(
        """
        SELECT *
        FROM booking_composite_event_expenses
        WHERE event_id = ?
        ORDER BY id
        """,
        (event_id,),
    ).fetchall()
    line_rows = conn.execute(
        """
        SELECT *
        FROM booking_composite_event_lines
        WHERE event_id = ?
        ORDER BY id
        """,
        (event_id,),
    ).fetchall()
    item["expenses"] = [dict(expense) for expense in expense_rows]
    item["operational_expenses_amount"] = sum(
        float(expense["amount"] or 0)
        for expense in expense_rows
        if not str(expense["category"] or "").startswith("comision")
    )
    item["direct_commissions_amount"] = sum(
        float(expense["amount"] or 0)
        for expense in expense_rows
        if str(expense["category"] or "").startswith("comision")
    )
    item["artist_base_amount"] = (
        float(item.get("gross_amount") or 0)
        - item["operational_expenses_amount"]
        - item["direct_commissions_amount"]
    )
    lines = [dict(line) for line in line_rows]
    child_show_ids = [
        int(line["booking_show_id"])
        for line in lines
        if line.get("booking_show_id")
    ]
    if child_show_ids:
        placeholders = ",".join("?" for _ in child_show_ids)

        expense_rows = conn.execute(
            f"""
            SELECT *
            FROM booking_show_expenses
            WHERE show_id IN ({placeholders})
            ORDER BY id
            """,
            child_show_ids,
        ).fetchall()
        expenses_by_show: dict[int, list[dict]] = {show_id: [] for show_id in child_show_ids}
        for expense in expense_rows:
            expense_data = row_to_booking_expense(expense)
            expenses_by_show.setdefault(expense_data["show_id"], []).append(expense_data)

        share_rows = conn.execute(
            f"""
            SELECT *
            FROM booking_external_shares
            WHERE show_id IN ({placeholders})
            ORDER BY id
            """,
            child_show_ids,
        ).fetchall()
        shares_by_show: dict[int, list[dict]] = {show_id: [] for show_id in child_show_ids}
        for share in share_rows:
            share_data = row_to_booking_external_share(share)
            shares_by_show.setdefault(share_data["show_id"], []).append(share_data)

        for line in lines:
            booking_show_id = line.get("booking_show_id")
            if booking_show_id:
                line["show_expenses"] = expenses_by_show.get(int(booking_show_id), [])
                line["external_shares"] = shares_by_show.get(int(booking_show_id), [])
            else:
                line["show_expenses"] = []
                line["external_shares"] = []
    else:
        for line in lines:
            line["show_expenses"] = []
            line["external_shares"] = []

    item["lines"] = lines
    return item


@app.get("/booking/events/options")
def booking_event_options(
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    require_booking_agenda_postgres()
    with operational_connect() as conn:
        agenda_permission = require_module_permission(
            conn, x_vpo_username, "booking_agenda", "view_history"
        )
        individual_permission = user_module_permission(conn, x_vpo_username, "booking")
        shared_permission = user_module_permission(conn, x_vpo_username, "composite_booking")
        artist_rows = conn.execute(
            "SELECT id, stage_name FROM artists WHERE active = TRUE ORDER BY lower(stage_name)"
        ).fetchall()

    artists = []
    for row in artist_rows:
        artist = str(row["stage_name"])
        can_individual = booking_permission_covers_artists(individual_permission, [artist])
        can_shared = booking_permission_covers_artists(shared_permission, [artist])
        artists.append(
            {
                "id": int(row["id"]),
                "artist": artist,
                "can_individual": can_individual,
                "can_shared": can_shared,
            }
        )

    return {
        "artists": artists,
        "permissions": {
            "agenda": {
                "access": bool(agenda_permission.get("allowed")),
                "create": bool(agenda_permission.get("can_create")),
                "view_history": bool(agenda_permission.get("can_view_history")),
                "edit": bool(agenda_permission.get("can_edit")),
            },
            "individual": {
                "access": bool(individual_permission.get("allowed")),
                "create": bool(individual_permission.get("can_create")),
                "view_history": bool(individual_permission.get("can_view_history")),
                "edit": bool(individual_permission.get("can_edit")),
            },
            "shared": {
                "access": bool(shared_permission.get("allowed")),
                "create": bool(shared_permission.get("can_create")),
                "view_history": bool(shared_permission.get("can_view_history")),
                "edit": bool(shared_permission.get("can_edit")),
            },
        },
    }


@app.get("/booking/events")
def booking_events(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    require_booking_agenda_postgres()
    safe_limit = min(max(limit, 1), 1000)
    if start_date:
        start_date = validate_iso_date(start_date)
    if end_date:
        end_date = validate_iso_date(end_date)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="La fecha desde no puede ser posterior a la fecha hasta.")

    with operational_connect() as conn:
        require_module_permission(conn, x_vpo_username, "booking_agenda", "view_history")

        where = []
        params: list[Any] = []
        if start_date:
            where.append("e.event_date >= %s")
            params.append(start_date)
        if end_date:
            where.append("e.event_date <= %s")
            params.append(end_date)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(safe_limit)
        rows = conn.execute(
            f"""
            SELECT e.*,
                   s.id AS booking_show_id,
                   c.id AS composite_event_id,
                   ce.id AS caserio_event_id,
                   (SELECT count(*) FROM booking_events child WHERE child.group_event_id = e.id) AS group_count,
                   (
                       SELECT source.source_text
                       FROM booking_event_source_links source
                       WHERE source.event_id = e.id
                       ORDER BY source.id DESC
                       LIMIT 1
                   ) AS source_text,
                   COALESCE((
                       SELECT jsonb_agg(
                           jsonb_build_object(
                               'artist_id', a.artist_id,
                               'artist', a.artist_name,
                               'position', a.position
                           ) ORDER BY a.position
                       )
                       FROM booking_event_artists a
                       WHERE a.event_id = e.id
                   ), '[]'::jsonb) AS artists,
                   COALESCE((
                       SELECT jsonb_agg(
                           jsonb_build_object(
                               'id', d.id,
                               'movement_date', d.movement_date,
                               'amount', d.amount,
                               'currency', d.currency,
                               'fx_rate', d.fx_rate,
                               'received_by', d.received_by,
                               'received_by_name', d.received_by_name,
                               'payment_method', d.payment_method,
                               'counterparty', d.counterparty,
                               'proof_refs', d.proof_refs_json,
                               'notes', d.notes
                           ) ORDER BY d.movement_date, d.id
                       )
                       FROM booking_event_deposits d
                       WHERE d.event_id = e.id
                   ), '[]'::jsonb) AS deposits
            FROM booking_events e
            LEFT JOIN booking_shows s ON s.booking_event_id = e.id
            LEFT JOIN booking_composite_events c ON c.booking_event_id = e.id
            LEFT JOIN caserio_events ce ON ce.booking_event_id = e.id
            {where_sql}
            ORDER BY e.event_date DESC, e.start_time DESC NULLS LAST, e.id DESC
            LIMIT %s
            """,
            tuple(params),
        ).fetchall()

    visible_items: list[dict] = []
    for raw_row in rows:
        item = dict(raw_row)
        item["event_date"] = item["event_date"].isoformat() if hasattr(item["event_date"], "isoformat") else str(item["event_date"])
        if item.get("start_time") is not None:
            item["start_time"] = str(item["start_time"])[:5]
        item["contracted_cachet_amount"] = float(item.get("contracted_cachet_amount") or 0)
        item["fx_rate"] = float(item.get("fx_rate") or 0)
        item["group_count"] = int(item.get("group_count") or 0)
        item["deposit_total"] = sum(
            float(deposit.get("amount") or 0)
            for deposit in (item.get("deposits") or [])
            if deposit.get("currency") == item.get("currency")
        )
        visible_items.append(item)

    today = date.today().isoformat()
    active_items = [
        item
        for item in visible_items
        if item["event_type"] == "show" and item["commercial_status"] != "cancelado"
    ]
    return {
        "items": visible_items,
        "summary": {
            "total": len(active_items),
            "upcoming": sum(item["event_date"] >= today and item["operational_status"] == "programado" for item in active_items),
            "with_deposit": sum(item["deposit_status"] in {"sena_parcial", "sena_recibida"} for item in active_items),
            "pending_settlement": sum(item["settlement_status"] in {"pendiente", "rendida", "observada"} for item in active_items),
            "not_started": sum(item["settlement_status"] == "no_iniciada" for item in active_items),
        },
    }


@app.post("/booking/events")
def create_booking_event(
    request: BookingAgendaEventRequest,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    require_booking_agenda_postgres()
    username = clean_username(x_vpo_username or "")
    if not username:
        raise HTTPException(status_code=401, detail="Falta el usuario que realiza la carga.")

    event_date = validate_iso_date(request.event_date)
    start_time = validate_booking_start_time(request.start_time)
    venue = request.venue.strip()
    city = clean_optional_text(request.city)
    group_children: list[dict] = []
    if request.event_type == "show_group":
        if len(request.group_children) < 2:
            raise HTTPException(status_code=400, detail="Un grupo necesita al menos dos shows.")
        for child in request.group_children:
            group_children.append({
                "id": child.id,
                "event_date": validate_iso_date(child.event_date),
                "start_time": validate_booking_start_time(child.start_time),
                "venue": child.venue.strip(),
                "city": clean_optional_text(child.city),
                "contracted_cachet_amount": float(child.contracted_cachet_amount),
                "notes": clean_optional_text(child.notes),
            })
        event_date = min(child["event_date"] for child in group_children)
        start_time = None
    elif request.group_children:
        raise HTTPException(status_code=400, detail="Los shows internos solo corresponden a un grupo.")
    requested_artists = [clean_booking_artist(value) for value in request.artists]
    requested_artists = [value for value in requested_artists if value]
    unique_artist_keys = []
    for artist in requested_artists:
        key = artist.casefold()
        if key not in unique_artist_keys:
            unique_artist_keys.append(key)
    if not unique_artist_keys:
        raise HTTPException(status_code=400, detail="Elegí al menos un artista.")
    if request.duplicate_override and not clean_optional_text(request.duplicate_override_notes):
        raise HTTPException(status_code=400, detail="Explicá por qué la coincidencia corresponde a otro show.")
    event_cachet = (
        sum(child["contracted_cachet_amount"] for child in group_children)
        if request.event_type == "show_group"
        else float(request.contracted_cachet_amount)
    )
    if request.currency == "USD" and event_cachet > 0 and not request.fx_rate:
        raise HTTPException(status_code=400, detail="Para un caché en USD falta el tipo de cambio.")
    if request.event_type != "show" and request.deposit is not None:
        raise HTTPException(status_code=400, detail="Solo un show puede registrar una seña.")

    with operational_connect() as conn:
        require_module_permission(conn, username, "booking_agenda", "create")
        artist_rows = conn.execute(
            "SELECT id, stage_name FROM artists WHERE active = TRUE ORDER BY lower(stage_name)"
        ).fetchall()
        artist_lookup = {str(row["stage_name"]).casefold(): row for row in artist_rows}
        missing = [artist for artist in requested_artists if artist.casefold() not in artist_lookup]
        if missing:
            raise HTTPException(status_code=400, detail=f"Artista no encontrado o inactivo: {', '.join(missing)}")
        selected_rows = [artist_lookup[key] for key in unique_artist_keys]
        selected_names = [str(row["stage_name"]) for row in selected_rows]
        booking_mode = "individual" if len(selected_names) == 1 else "shared"
        module_key = "booking_agenda"

        duplicate_candidates: list[dict] = []
        duplicate_targets = group_children if request.event_type == "show_group" else [{
            "event_date": event_date,
            "venue": venue,
            "city": city,
        }]
        if request.event_type in {"show", "show_group"}:
            for target in duplicate_targets:
                duplicate_candidates.extend(booking_duplicate_candidates(
                    conn,
                    event_date=target["event_date"],
                    artists=selected_names,
                    venue=target["venue"],
                    city=target["city"],
                ))
        hard_duplicates = [item for item in duplicate_candidates if item["match"] == "duplicado"]
        if hard_duplicates and not request.duplicate_override:
            first = hard_duplicates[0]
            artists_text = ", ".join(first["artists"])
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "booking_duplicate",
                    "message": (
                        f"Posible show duplicado: {first['date']} · {artists_text} · "
                        f"{first['venue']} {first['city']}. Abrí el existente o confirmá que es otro show."
                    ),
                    "candidates": hard_duplicates,
                },
            )

        deposit_payload = None
        deposits_for_status: list[dict] = []
        if request.deposit:
            deposit_date = validate_iso_date(request.deposit.movement_date)
            if request.deposit.currency == "USD" and not request.deposit.fx_rate:
                raise HTTPException(status_code=400, detail="Para una seña en USD falta el tipo de cambio.")
            deposit_payload = {
                "movement_date": deposit_date,
                "amount": float(request.deposit.amount),
                "currency": request.deposit.currency,
                "fx_rate": request.deposit.fx_rate,
                "received_by": request.deposit.received_by,
                "received_by_name": clean_optional_text(request.deposit.received_by_name),
                "payment_method": request.deposit.payment_method,
                "counterparty": clean_optional_text(request.deposit.counterparty),
                "proof_refs": clean_receipt_refs(request.deposit.proof_refs),
                "notes": clean_optional_text(request.deposit.notes),
            }
            deposits_for_status.append(deposit_payload)

        deposit_status = booking_event_deposit_status(
            event_cachet,
            request.currency,
            deposits_for_status,
        )
        status_by_type = {
            "show": ("confirmado", "programado", "no_iniciada"),
            "show_group": ("no_aplica", "programado", "no_aplica"),
            "availability_block": ("no_aplica", "bloqueado", "no_aplica"),
            "logistics": ("no_aplica", "informativo", "no_aplica"),
            "prospect": ("prospecto", "programado", "no_aplica"),
        }
        commercial_status, operational_status, settlement_status = status_by_type[request.event_type]
        if request.event_type != "show":
            deposit_status = "no_informada"
        row = conn.execute(
            """
            INSERT INTO booking_events (
                event_type, event_date, start_time, venue, city, booking_mode,
                commercial_status, operational_status, deposit_status, settlement_status,
                contracted_cachet_amount, currency, fx_rate, tour_manager, seller,
                duplicate_override, duplicate_override_notes, notes, created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                request.event_type,
                event_date,
                start_time,
                venue,
                city,
                booking_mode,
                commercial_status,
                operational_status,
                deposit_status,
                settlement_status,
                event_cachet,
                request.currency,
                request.fx_rate,
                clean_optional_text(request.tour_manager),
                clean_optional_text(request.seller),
                request.duplicate_override,
                clean_optional_text(request.duplicate_override_notes),
                clean_optional_text(request.notes),
                username,
            ),
        ).fetchone()
        event_id = int(row["id"])
        for position, artist_row in enumerate(selected_rows, start=1):
            conn.execute(
                """
                INSERT INTO booking_event_artists (event_id, artist_id, artist_name, position)
                VALUES (%s, %s, %s, %s)
                """,
                (event_id, artist_row["id"], artist_row["stage_name"], position),
            )
        child_ids: list[int] = []
        if request.event_type == "show_group":
            for group_position, child in enumerate(group_children, start=1):
                child_row = conn.execute(
                    """
                    INSERT INTO booking_events (
                        event_type, event_date, start_time, venue, city, booking_mode,
                        commercial_status, operational_status, deposit_status, settlement_status,
                        contracted_cachet_amount, currency, fx_rate, tour_manager, seller,
                        group_event_id, group_position, notes, created_by
                    )
                    VALUES ('show', %s, %s, %s, %s, %s,
                            'confirmado', 'programado', 'sin_sena', 'no_iniciada',
                            %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        child["event_date"],
                        child["start_time"],
                        child["venue"],
                        child["city"],
                        booking_mode,
                        child["contracted_cachet_amount"],
                        request.currency,
                        request.fx_rate,
                        clean_optional_text(request.tour_manager),
                        clean_optional_text(request.seller),
                        event_id,
                        group_position,
                        child["notes"],
                        username,
                    ),
                ).fetchone()
                child_id = int(child_row["id"])
                child_ids.append(child_id)
                for position, artist_row in enumerate(selected_rows, start=1):
                    conn.execute(
                        """
                        INSERT INTO booking_event_artists (event_id, artist_id, artist_name, position)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (child_id, artist_row["id"], artist_row["stage_name"], position),
                    )
        if deposit_payload:
            conn.execute(
                """
                INSERT INTO booking_event_deposits (
                    event_id, movement_date, amount, currency, fx_rate,
                    received_by, received_by_name, payment_method, counterparty,
                    proof_refs_json, notes, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    event_id,
                    deposit_payload["movement_date"],
                    deposit_payload["amount"],
                    deposit_payload["currency"],
                    deposit_payload["fx_rate"],
                    deposit_payload["received_by"],
                    deposit_payload["received_by_name"],
                    deposit_payload["payment_method"],
                    deposit_payload["counterparty"],
                    json.dumps(deposit_payload["proof_refs"], ensure_ascii=False),
                    deposit_payload["notes"],
                    username,
                ),
            )
        conn.execute(
            """
            INSERT INTO app_audit_log (
                actor_username, module_key, action, entity_table, entity_id, after_json, notes
            )
            VALUES (%s, %s, 'create', 'booking_events', %s, %s, %s)
            """,
            (
                username,
                module_key,
                str(event_id),
                json.dumps(
                    {
                        "event_date": event_date,
                        "event_type": request.event_type,
                        "venue": venue,
                        "city": city,
                        "artists": selected_names,
                        "booking_mode": booking_mode,
                        "deposit_status": deposit_status,
                        "group_children": child_ids,
                    },
                    ensure_ascii=False,
                ),
                "Alta desde Agenda de Booking.",
            ),
        )
        item = booking_agenda_event_item(conn, event_id)

    return {"item": item, "warnings": [item for item in duplicate_candidates if item["match"] == "conflicto_agenda"]}


@app.put("/booking/events/{event_id}")
def update_booking_event(
    event_id: int,
    request: BookingAgendaEventRequest,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    require_booking_agenda_postgres()
    username = clean_username(x_vpo_username or "")
    if not username:
        raise HTTPException(status_code=401, detail="Falta el usuario que realiza la edición.")

    with operational_connect() as conn:
        require_module_permission(conn, username, "booking_agenda", "edit")
        existing = conn.execute(
            """
            SELECT e.*,
                   EXISTS(SELECT 1 FROM booking_shows s WHERE s.booking_event_id = e.id) AS has_individual,
                   EXISTS(SELECT 1 FROM booking_composite_events c WHERE c.booking_event_id = e.id) AS has_composite,
                   EXISTS(SELECT 1 FROM caserio_events c WHERE c.booking_event_id = e.id) AS has_caserio
            FROM booking_events e
            WHERE e.id = %s
            FOR UPDATE
            """,
            (event_id,),
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="La entrada de Agenda no existe.")
        existing_data = dict(existing)
        if existing_data["has_individual"] or existing_data["has_composite"] or existing_data["has_caserio"]:
            raise HTTPException(
                status_code=409,
                detail="Este show ya tiene liquidación. Editalo desde Liquidaciones para mantener una sola verdad.",
            )

        requested_artists = [clean_booking_artist(value) for value in request.artists]
        requested_artists = [value for value in requested_artists if value]
        unique_artist_keys: list[str] = []
        for artist in requested_artists:
            key = artist.casefold()
            if key not in unique_artist_keys:
                unique_artist_keys.append(key)
        if not unique_artist_keys:
            raise HTTPException(status_code=400, detail="Elegí al menos un artista.")
        artist_rows = conn.execute(
            "SELECT id, stage_name FROM artists WHERE active = TRUE ORDER BY lower(stage_name)"
        ).fetchall()
        artist_lookup = {str(row["stage_name"]).casefold(): row for row in artist_rows}
        missing = [artist for artist in requested_artists if artist.casefold() not in artist_lookup]
        if missing:
            raise HTTPException(status_code=400, detail=f"Artista no encontrado o inactivo: {', '.join(missing)}")
        selected_rows = [artist_lookup[key] for key in unique_artist_keys]
        selected_names = [str(row["stage_name"]) for row in selected_rows]
        booking_mode = "individual" if len(selected_names) == 1 else "shared"
        module_key = "booking_agenda"

        existing_type = str(existing_data["event_type"])
        if existing_type == "show_group" and request.event_type not in {"show_group", "show"}:
            raise HTTPException(status_code=400, detail="Un grupo solo puede mantenerse como grupo o quedar como un show.")
        if request.deposit is not None:
            raise HTTPException(status_code=400, detail="Las señas existentes se administran desde su documento financiero.")

        venue = request.venue.strip()
        city = clean_optional_text(request.city)
        event_date = validate_iso_date(request.event_date)
        start_time = validate_booking_start_time(request.start_time)
        event_cachet = float(request.contracted_cachet_amount)
        group_children: list[dict] = []
        child_ids: list[int] = []
        collapsed_children: list[dict] = []

        if existing_type == "show_group" and request.event_type == "show":
            current_children = conn.execute(
                """
                SELECT child.*,
                       EXISTS(SELECT 1 FROM booking_shows s WHERE s.booking_event_id = child.id) AS has_individual,
                       EXISTS(SELECT 1 FROM booking_composite_events c WHERE c.booking_event_id = child.id) AS has_composite,
                       EXISTS(SELECT 1 FROM caserio_events c WHERE c.booking_event_id = child.id) AS has_caserio,
                       EXISTS(SELECT 1 FROM booking_event_deposits d WHERE d.event_id = child.id) AS has_deposit
                FROM booking_events child
                WHERE child.group_event_id = %s
                ORDER BY child.group_position
                FOR UPDATE
                """,
                (event_id,),
            ).fetchall()
            collapsed_children = [dict(row) for row in current_children]
            if any(
                row["has_individual"] or row["has_composite"] or row["has_caserio"] or row["has_deposit"]
                for row in collapsed_children
            ):
                raise HTTPException(
                    status_code=409,
                    detail="El grupo tiene shows con liquidación o seña y no puede reducirse desde Agenda.",
                )
            collapsed_child_ids = [int(row["id"]) for row in collapsed_children]
            if collapsed_child_ids:
                conn.execute(
                    """
                    INSERT INTO booking_event_source_links (
                        event_id, source_system, source_reference, source_role,
                        source_text, source_payload_json, created_by, created_at
                    )
                    SELECT %s, source_system, source_reference, source_role,
                           source_text, source_payload_json, created_by, created_at
                    FROM booking_event_source_links
                    WHERE event_id = ANY(%s)
                    ON CONFLICT (event_id, source_system, source_reference) DO NOTHING
                    """,
                    (event_id, collapsed_child_ids),
                )
                conn.execute("DELETE FROM booking_events WHERE id = ANY(%s)", (collapsed_child_ids,))

        if request.event_type == "show_group":
            if len(request.group_children) < 2:
                raise HTTPException(status_code=400, detail="Un grupo necesita al menos dos shows.")
            current_children = conn.execute(
                """
                SELECT child.*,
                       EXISTS(SELECT 1 FROM booking_shows s WHERE s.booking_event_id = child.id) AS has_individual,
                       EXISTS(SELECT 1 FROM booking_composite_events c WHERE c.booking_event_id = child.id) AS has_composite,
                       EXISTS(SELECT 1 FROM caserio_events c WHERE c.booking_event_id = child.id) AS has_caserio
                FROM booking_events child
                WHERE child.group_event_id = %s
                ORDER BY child.group_position
                FOR UPDATE
                """,
                (event_id,),
            ).fetchall()
            current_by_id = {int(row["id"]): dict(row) for row in current_children}
            if any(row["has_individual"] or row["has_composite"] or row["has_caserio"] for row in current_by_id.values()):
                raise HTTPException(
                    status_code=409,
                    detail="El grupo tiene shows liquidados. Editá esos shows desde Liquidaciones.",
                )
            for child in request.group_children:
                if child.id is not None and child.id not in current_by_id:
                    raise HTTPException(status_code=400, detail="Uno de los shows no pertenece a este grupo.")
                group_children.append({
                    "id": child.id,
                    "event_date": validate_iso_date(child.event_date),
                    "start_time": validate_booking_start_time(child.start_time),
                    "venue": child.venue.strip(),
                    "city": clean_optional_text(child.city),
                    "contracted_cachet_amount": float(child.contracted_cachet_amount),
                    "notes": clean_optional_text(child.notes),
                })
            event_date = min(child["event_date"] for child in group_children)
            start_time = None
            event_cachet = sum(child["contracted_cachet_amount"] for child in group_children)

            submitted_ids = {int(child["id"]) for child in group_children if child["id"] is not None}
            removed_ids = set(current_by_id) - submitted_ids
            if removed_ids:
                conn.execute("DELETE FROM booking_events WHERE id = ANY(%s)", (list(removed_ids),))
            for group_position, child in enumerate(group_children, start=1):
                if child["id"] is None:
                    inserted = conn.execute(
                        """
                        INSERT INTO booking_events (
                            event_type, event_date, start_time, venue, city, booking_mode,
                            commercial_status, operational_status, deposit_status, settlement_status,
                            contracted_cachet_amount, currency, fx_rate, tour_manager, seller,
                            group_event_id, group_position, notes, created_by
                        )
                        VALUES ('show', %s, %s, %s, %s, %s,
                                'confirmado', 'programado', 'sin_sena', 'no_iniciada',
                                %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            child["event_date"], child["start_time"], child["venue"], child["city"], booking_mode,
                            child["contracted_cachet_amount"], request.currency, request.fx_rate,
                            clean_optional_text(request.tour_manager), clean_optional_text(request.seller),
                            event_id, group_position, child["notes"], username,
                        ),
                    ).fetchone()
                    child_id = int(inserted["id"])
                else:
                    child_id = int(child["id"])
                    conn.execute(
                        """
                        UPDATE booking_events
                        SET event_date = %s, start_time = %s, venue = %s, city = %s,
                            booking_mode = %s, contracted_cachet_amount = %s,
                            currency = %s, fx_rate = %s, tour_manager = %s, seller = %s,
                            group_position = %s, notes = %s, updated_at = now()
                        WHERE id = %s
                        """,
                        (
                            child["event_date"], child["start_time"], child["venue"], child["city"], booking_mode,
                            child["contracted_cachet_amount"], request.currency, request.fx_rate,
                            clean_optional_text(request.tour_manager), clean_optional_text(request.seller),
                            group_position, child["notes"], child_id,
                        ),
                    )
                child_ids.append(child_id)
                conn.execute("DELETE FROM booking_event_artists WHERE event_id = %s", (child_id,))
                for position, artist_row in enumerate(selected_rows, start=1):
                    conn.execute(
                        """INSERT INTO booking_event_artists (event_id, artist_id, artist_name, position)
                           VALUES (%s, %s, %s, %s)""",
                        (child_id, artist_row["id"], artist_row["stage_name"], position),
                    )
        elif request.group_children:
            raise HTTPException(status_code=400, detail="Los shows internos solo corresponden a un grupo.")

        if request.currency == "USD" and event_cachet > 0 and not request.fx_rate:
            raise HTTPException(status_code=400, detail="Para un caché en USD falta el tipo de cambio.")
        if request.event_type != "show" and existing_data.get("deposit_status") not in {"no_informada", "sin_sena"}:
            raise HTTPException(status_code=409, detail="No se puede cambiar el tipo porque la entrada tiene una seña.")

        status_by_type = {
            "show": ("confirmado", "programado", "no_iniciada"),
            "show_group": ("no_aplica", "programado", "no_aplica"),
            "availability_block": ("no_aplica", "bloqueado", "no_aplica"),
            "logistics": ("no_aplica", "informativo", "no_aplica"),
            "prospect": ("prospecto", "programado", "no_aplica"),
        }
        if request.event_type == existing_type:
            commercial_status = existing_data["commercial_status"]
            operational_status = existing_data["operational_status"]
            settlement_status = existing_data["settlement_status"]
        else:
            commercial_status, operational_status, settlement_status = status_by_type[request.event_type]
        deposit_status = existing_data["deposit_status"] if request.event_type == "show" else "no_informada"

        audit_before = dict(existing_data)
        if collapsed_children:
            audit_before["group_children"] = collapsed_children
        before_json = json.dumps(audit_before, ensure_ascii=False, default=str)
        conn.execute(
            """
            UPDATE booking_events
            SET event_type = %s, event_date = %s, start_time = %s, venue = %s, city = %s,
                booking_mode = %s, commercial_status = %s, operational_status = %s,
                deposit_status = %s, settlement_status = %s,
                contracted_cachet_amount = %s, currency = %s, fx_rate = %s,
                tour_manager = %s, seller = %s, notes = %s, updated_at = now()
            WHERE id = %s
            """,
            (
                request.event_type, event_date, start_time, venue, city, booking_mode,
                commercial_status, operational_status, deposit_status, settlement_status,
                event_cachet, request.currency, request.fx_rate,
                clean_optional_text(request.tour_manager), clean_optional_text(request.seller),
                clean_optional_text(request.notes), event_id,
            ),
        )
        conn.execute("DELETE FROM booking_event_artists WHERE event_id = %s", (event_id,))
        for position, artist_row in enumerate(selected_rows, start=1):
            conn.execute(
                """INSERT INTO booking_event_artists (event_id, artist_id, artist_name, position)
                   VALUES (%s, %s, %s, %s)""",
                (event_id, artist_row["id"], artist_row["stage_name"], position),
            )
        conn.execute(
            """
            INSERT INTO app_audit_log (
                actor_username, module_key, action, entity_table, entity_id,
                before_json, after_json, notes
            )
            VALUES (%s, %s, 'update', 'booking_events', %s, %s, %s, %s)
            """,
            (
                username, module_key, str(event_id), before_json,
                json.dumps({
                    "event_type": request.event_type,
                    "event_date": event_date,
                    "venue": venue,
                    "artists": selected_names,
                    "group_children": child_ids,
                }, ensure_ascii=False),
                "Grupo reducido a un show desde Agenda." if collapsed_children else "Edición desde Agenda de Booking.",
            ),
        )
        item = booking_agenda_event_item(conn, event_id)

    return {"item": item}


@app.delete("/booking/events/{event_id}")
def delete_booking_event(
    event_id: int,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    require_booking_agenda_postgres()
    username = clean_username(x_vpo_username or "")
    if not username:
        raise HTTPException(status_code=401, detail="Falta el usuario que realiza la eliminación.")
    with operational_connect() as conn:
        require_module_permission(conn, username, "booking_agenda", "edit")
        existing = conn.execute(
            """
            SELECT e.*,
                   EXISTS(SELECT 1 FROM booking_shows s WHERE s.booking_event_id = e.id) AS has_individual,
                   EXISTS(SELECT 1 FROM booking_composite_events c WHERE c.booking_event_id = e.id) AS has_composite,
                   EXISTS(SELECT 1 FROM caserio_events c WHERE c.booking_event_id = e.id) AS has_caserio
            FROM booking_events e WHERE e.id = %s FOR UPDATE
            """,
            (event_id,),
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="La entrada de Agenda no existe.")
        data = dict(existing)
        if data["has_individual"] or data["has_composite"] or data["has_caserio"]:
            raise HTTPException(status_code=409, detail="El show tiene liquidación y no se puede eliminar desde Agenda.")
        module_key = "booking_agenda"
        child_links = conn.execute(
            """
            SELECT count(*) AS total
            FROM booking_events child
            WHERE child.group_event_id = %s
              AND (
                  EXISTS(SELECT 1 FROM booking_shows s WHERE s.booking_event_id = child.id)
                  OR EXISTS(SELECT 1 FROM booking_composite_events c WHERE c.booking_event_id = child.id)
                  OR EXISTS(SELECT 1 FROM caserio_events c WHERE c.booking_event_id = child.id)
              )
            """,
            (event_id,),
        ).fetchone()
        if int(child_links["total"] or 0):
            raise HTTPException(status_code=409, detail="El grupo contiene shows liquidados y no se puede eliminar.")
        conn.execute(
            """
            INSERT INTO app_audit_log (
                actor_username, module_key, action, entity_table, entity_id,
                before_json, notes
            )
            VALUES (%s, %s, 'delete', 'booking_events', %s, %s, %s)
            """,
            (
                username, module_key, str(event_id),
                json.dumps(data, ensure_ascii=False, default=str),
                "Eliminación desde Agenda de Booking.",
            ),
        )
        if data["event_type"] == "show_group":
            conn.execute("DELETE FROM booking_events WHERE group_event_id = %s", (event_id,))
        conn.execute("DELETE FROM booking_events WHERE id = %s", (event_id,))

    return {"deleted": True, "event_id": event_id}


@app.get("/booking/composite-events")
def booking_composite_events(
    limit: int = 100,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    safe_limit = min(max(limit, 1), 500)

    with booking_connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM booking_composite_events
            ORDER BY event_date DESC, id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        items = [fetch_booking_composite_event_item(conn, row["id"]) for row in rows]

    return {
        "items": items,
    }


@app.get("/booking/composite-events/{event_id}")
def booking_composite_event(
    event_id: int,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    with booking_connect() as conn:
        item = fetch_booking_composite_event_item(conn, event_id)
        artists = [
            clean_booking_artist(line.get("artist"))
            for line in item.get("lines", [])
            if line.get("line_type") == "artista_vpo" and clean_booking_artist(line.get("artist"))
        ]
        for artist in artists:
            require_module_permission(conn, x_vpo_username, "composite_booking", "view_history", artist=artist)
    return {"item": item}


@app.post("/booking/composite-events")
def create_booking_composite_event(
    request: BookingCompositeEventRequest,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    event_date = validate_iso_date(request.event_date)
    venue = request.venue.strip()
    city = clean_optional_text(request.city)
    responsible = clean_optional_text(request.responsible)
    notes = clean_optional_text(request.notes)
    receipt_refs = clean_receipt_refs(request.receipt_refs)
    now = datetime.now().isoformat(timespec="seconds")

    prepared_expenses = [
        {
            "concept": expense.concept.strip(),
            "category": expense.category.strip() or "general",
            "amount": expense.amount,
            "notes": clean_optional_text(expense.notes),
        }
        for expense in request.expenses
        if expense.amount > 0 and expense.concept.strip()
    ]
    general_expenses = sum(expense["amount"] for expense in prepared_expenses)
    allocated_amount = sum(line.amount for line in request.lines)
    if allocated_amount > request.gross_amount + 0.01:
        raise HTTPException(status_code=400, detail="Composite event lines cannot exceed gross amount.")

    with booking_connect() as conn:
        vpo_artists = [
            clean_booking_artist(line.artist)
            for line in request.lines
            if line.line_type == "artista_vpo" and clean_booking_artist(line.artist)
        ]
        for artist in vpo_artists:
            require_module_permission(conn, x_vpo_username, "composite_booking", "create", artist=artist)
        booking_event_id = resolve_booking_event_for_new_settlement(
            conn,
            requested_event_id=request.booking_event_id,
            booking_mode="shared",
            artists=vpo_artists,
            event_date=event_date,
            venue=venue,
            city=city,
            cachet_amount=float(request.gross_amount),
            currency=request.currency,
            fx_rate=request.fx_rate,
            tour_manager=responsible,
            seller=None,
            settlement_status=request.status,
            actor_username=x_vpo_username,
        )
        cursor = conn.execute(
            """
            INSERT INTO booking_composite_events (
                booking_event_id, event_date, venue, city, responsible, status, currency, fx_rate,
                gross_amount, general_expenses_amount, allocated_amount,
                producer_expected_amount, received_amount, balance_amount,
                receipt_refs_json, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0, ?, ?, ?, ?)
            """,
            (
                booking_event_id,
                event_date,
                venue,
                city,
                responsible,
                request.status,
                request.currency,
                request.fx_rate,
                request.gross_amount,
                general_expenses,
                allocated_amount,
                request.received_amount,
                json.dumps(receipt_refs, ensure_ascii=False),
                notes,
                now,
                now,
            ),
        )
        event_id = int(cursor.lastrowid)
        settlement_group = f"booking_composite_{event_id}_{event_date}"
        producer_expected = 0.0

        for expense in prepared_expenses:
            conn.execute(
                """
                INSERT INTO booking_composite_event_expenses (
                    event_id, concept, category, amount, notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, expense["concept"], expense["category"], expense["amount"], expense["notes"], now),
            )

        for line in request.lines:
            line_artist = clean_optional_text(line.artist)
            line_notes = clean_optional_text(line.notes)
            commission_notes = clean_optional_text(line.booking_commission_notes)
            producer_percent = line.producer_percent
            if producer_percent is None:
                producer_percent = max(0.0, 100.0 - line.artist_percent)

            booking_show_id = None
            if line.line_type == "artista_vpo":
                if not line_artist:
                    raise HTTPException(status_code=400, detail="artist is required for artista_vpo lines.")

                show_request = BookingQuickShowRequest(
                    artist=line_artist,
                    show_date=event_date,
                    venue=venue,
                    city=city,
                    tour_manager=responsible,
                    status="realizado",
                    currency=request.currency,
                    fx_rate=request.fx_rate,
                    cachet_amount=line.amount,
                    show_expenses=line.show_expenses,
                    external_shares=line.external_shares,
                    artist_paid_amount=line.artist_paid_amount,
                    producer_received_amount=line.producer_received_amount,
                    artist_percent=line.artist_percent,
                    producer_percent=producer_percent,
                    booking_commission_exempt=line.booking_commission_exempt,
                    booking_commission_notes=commission_notes,
                    notes=f"Liquidacion hija de show madre #{event_id}: {line.description}. {line_notes or ''}".strip(),
                )
                show = insert_booking_show_from_request(
                    conn,
                    show_request,
                    now,
                    origin_type="booking_composite",
                    origin_id=event_id,
                    settlement_group=settlement_group,
                    validate_artist=False,
                )
                booking_show_id = show["id"]
                producer_expected += float(show["producer_cash_target_amount"] or 0)

            conn.execute(
                """
                INSERT INTO booking_composite_event_lines (
                    event_id, line_type, description, artist, amount,
                    artist_percent, producer_percent, artist_paid_amount,
                    producer_received_amount, booking_commission_exempt,
                    booking_commission_notes, booking_show_id, notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    line.line_type,
                    line.description.strip(),
                    line_artist,
                    line.amount,
                    line.artist_percent,
                    producer_percent,
                    line.artist_paid_amount,
                    line.producer_received_amount,
                    1 if line.booking_commission_exempt else 0,
                    commission_notes,
                    booking_show_id,
                    line_notes,
                    now,
                ),
            )

        balance = producer_expected - request.received_amount
        conn.execute(
            """
            UPDATE booking_composite_events
            SET producer_expected_amount = ?,
                balance_amount = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (producer_expected, balance, now, event_id),
        )
        conn.execute(
            """
            UPDATE booking_events
            SET settlement_status = ?,
                operational_status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                "cerrada" if request.status == "cerrado" and abs(balance) <= 0.01 else "pendiente",
                "realizado" if request.status in {"rendido", "observado", "cerrado"} or event_date < date.today().isoformat() else "programado",
                now,
                booking_event_id,
            ),
        )
        item = fetch_booking_composite_event_item(conn, event_id)

    return {
        "item": item,
        "db_driver": operational_db_settings().driver,
    }


@app.put("/booking/composite-events/{event_id}")
def update_booking_composite_event(
    event_id: int,
    request: BookingCompositeEventRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    event_date = validate_iso_date(request.event_date)
    venue = request.venue.strip()
    city = clean_optional_text(request.city)
    responsible = clean_optional_text(request.responsible)
    notes = clean_optional_text(request.notes)
    receipt_refs = clean_receipt_refs(request.receipt_refs)
    now = datetime.now().isoformat(timespec="seconds")

    prepared_expenses = [
        {
            "concept": expense.concept.strip(),
            "category": expense.category.strip() or "general",
            "amount": expense.amount,
            "notes": clean_optional_text(expense.notes),
        }
        for expense in request.expenses
        if expense.amount > 0 and expense.concept.strip()
    ]
    general_expenses = sum(expense["amount"] for expense in prepared_expenses)
    allocated_amount = sum(line.amount for line in request.lines)
    if allocated_amount > request.gross_amount + 0.01:
        raise HTTPException(status_code=400, detail="Composite event lines cannot exceed gross amount.")

    with booking_connect() as conn:
        existing = conn.execute(
            "SELECT id FROM booking_composite_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Composite booking event not found.")

        old_line_show_ids = {
            int(row["id"]): row["booking_show_id"]
            for row in conn.execute(
                """
                SELECT id, booking_show_id
                FROM booking_composite_event_lines
                WHERE event_id = ?
                """,
                (event_id,),
            ).fetchall()
        }

        conn.execute(
            """
            UPDATE booking_composite_events
            SET event_date = ?,
                venue = ?,
                city = ?,
                responsible = ?,
                status = ?,
                currency = ?,
                fx_rate = ?,
                gross_amount = ?,
                general_expenses_amount = ?,
                allocated_amount = ?,
                received_amount = ?,
                receipt_refs_json = ?,
                notes = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                event_date,
                venue,
                city,
                responsible,
                request.status,
                request.currency,
                request.fx_rate,
                request.gross_amount,
                general_expenses,
                allocated_amount,
                request.received_amount,
                json.dumps(receipt_refs, ensure_ascii=False),
                notes,
                now,
                event_id,
            ),
        )

        conn.execute("DELETE FROM booking_composite_event_expenses WHERE event_id = ?", (event_id,))
        conn.execute("DELETE FROM booking_composite_event_lines WHERE event_id = ?", (event_id,))

        for expense in prepared_expenses:
            conn.execute(
                """
                INSERT INTO booking_composite_event_expenses (
                    event_id, concept, category, amount, notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, expense["concept"], expense["category"], expense["amount"], expense["notes"], now),
            )

        producer_expected = 0.0
        for line in request.lines:
            line_artist = clean_optional_text(line.artist)
            line_notes = clean_optional_text(line.notes)
            commission_notes = clean_optional_text(line.booking_commission_notes)
            producer_percent = line.producer_percent
            if producer_percent is None:
                producer_percent = max(0.0, 100.0 - line.artist_percent)

            booking_show_id = old_line_show_ids.get(line.id) if line.id else None
            if line.line_type == "artista_vpo":
                if not line_artist:
                    raise HTTPException(status_code=400, detail="artist is required for artista_vpo lines.")
                if booking_show_id:
                    show_row = conn.execute(
                        """
                        SELECT settlement_status, settlement_closed_at, receipt_refs_json
                        FROM booking_shows
                        WHERE id = ?
                        """,
                        (booking_show_id,),
                    ).fetchone()
                    if show_row is not None:
                        if str(show_row["settlement_status"] or "") in {"historico", "cerrado"}:
                            existing_target = conn.execute(
                                "SELECT producer_cash_target_amount FROM booking_shows WHERE id = ?",
                                (booking_show_id,),
                            ).fetchone()
                            producer_expected += float(existing_target["producer_cash_target_amount"] or 0)
                        else:
                            show_receipts = json.loads(show_row["receipt_refs_json"] or "[]")
                            show_request = BookingQuickShowRequest(
                                artist=line_artist,
                                show_date=event_date,
                                venue=venue,
                                city=city,
                                tour_manager=responsible,
                                status="aprobado" if request.status == "cerrado" else "realizado",
                                currency=request.currency,
                                fx_rate=request.fx_rate,
                                contracted_cachet_amount=line.amount,
                                venue_collected_amount=line.amount,
                                cachet_amount=line.amount,
                                show_expenses=line.show_expenses,
                                external_shares=line.external_shares,
                                artist_paid_amount=line.artist_paid_amount,
                                producer_received_amount=line.producer_received_amount,
                                artist_percent=line.artist_percent,
                                producer_percent=producer_percent,
                                receipt_refs=show_receipts,
                                booking_commission_exempt=line.booking_commission_exempt,
                                booking_commission_notes=commission_notes,
                                notes=f"Sincronizado desde liquidacion madre #{event_id}: {line.description}. {line_notes or ''}".strip(),
                            )
                            synced_show = update_booking_show_from_request(
                                conn,
                                int(booking_show_id),
                                show_request,
                                now,
                                validate_artist=False,
                            )
                            producer_expected += float(synced_show["producer_cash_target_amount"] or 0)
                    else:
                        booking_show_id = None
                if not booking_show_id:
                    line_expenses = sum(expense.amount for expense in line.show_expenses)
                    producer_expected += max(0.0, line.amount - line_expenses) * producer_percent / 100

            conn.execute(
                """
                INSERT INTO booking_composite_event_lines (
                    event_id, line_type, description, artist, amount,
                    artist_percent, producer_percent, artist_paid_amount,
                    producer_received_amount, booking_commission_exempt,
                    booking_commission_notes, booking_show_id, notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    line.line_type,
                    line.description.strip(),
                    line_artist,
                    line.amount,
                    line.artist_percent,
                    producer_percent,
                    line.artist_paid_amount,
                    line.producer_received_amount,
                    1 if line.booking_commission_exempt else 0,
                    commission_notes,
                    booking_show_id,
                    line_notes,
                    now,
                ),
            )

        balance = producer_expected - request.received_amount
        conn.execute(
            """
            UPDATE booking_composite_events
            SET producer_expected_amount = ?,
                balance_amount = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (producer_expected, balance, now, event_id),
        )
        item = fetch_booking_composite_event_item(conn, event_id)
        sync_booking_event_from_composite(conn, event_id, item, now)

    return {
        "item": item,
        "db_driver": operational_db_settings().driver,
    }


@app.get("/caserio/events")
def caserio_events(
    limit: int = 100,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    safe_limit = min(max(limit, 1), 500)

    with booking_connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM caserio_events
            ORDER BY event_date DESC, id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        items = [fetch_caserio_event_item(conn, row["id"]) for row in rows]

    return {
        "items": items,
    }


@app.post("/caserio/events")
def create_caserio_event(
    request: CaserioEventRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    event_date = validate_iso_date(request.event_date)
    venue = request.venue.strip()
    city = clean_optional_text(request.city)
    responsible = clean_optional_text(request.responsible)
    notes = clean_optional_text(request.notes)
    receipt_refs = clean_receipt_refs(request.receipt_refs)
    now = datetime.now().isoformat(timespec="seconds")

    caserio_lines_amount = sum(line.amount for line in request.lines)
    caserio_expected = request.gross_amount - caserio_lines_amount
    producer_expected = 0.0
    if caserio_expected < 0:
        raise HTTPException(status_code=400, detail="Caserio lines cannot exceed gross amount.")

    with booking_connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO caserio_events (
                event_date, venue, city, responsible, status, currency, fx_rate,
                gross_amount, caserio_expected_amount, producer_expected_amount,
                total_expected_amount, received_amount, balance_amount,
                receipt_refs_json, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, 0, ?, ?, ?, ?)
            """,
            (
                event_date,
                venue,
                city,
                responsible,
                request.status,
                request.currency,
                request.fx_rate,
                request.gross_amount,
                caserio_expected,
                request.received_amount,
                json.dumps(receipt_refs, ensure_ascii=False),
                notes,
                now,
                now,
            ),
        )
        event_id = int(cursor.lastrowid)
        settlement_group = f"caserio_{event_id}_{event_date}"

        for line in request.lines:
            line_artist = clean_optional_text(line.artist)
            booking_show_id = None
            line_notes = clean_optional_text(line.notes)

            if line.line_type == "artista_vpo":
                if not line_artist:
                    raise HTTPException(status_code=400, detail="artist is required for artista_vpo lines.")

                producer_percent = line.producer_percent
                if producer_percent is None:
                    producer_percent = max(0.0, 100.0 - line.artist_percent)

                show_request = BookingQuickShowRequest(
                    artist=line_artist,
                    show_date=event_date,
                    venue=venue,
                    city=city,
                    tour_manager=responsible,
                    status="realizado",
                    currency=request.currency,
                    fx_rate=request.fx_rate,
                    cachet_amount=line.amount,
                    show_expenses=line.show_expenses,
                    artist_percent=line.artist_percent,
                    producer_percent=producer_percent,
                    notes=f"Show interno generado desde evento Caserio #{event_id}. {line_notes or ''}".strip(),
                )
                show = insert_booking_show_from_request(
                    conn,
                    show_request,
                    now,
                    origin_type="caserio",
                    origin_id=event_id,
                    settlement_group=settlement_group,
                    validate_artist=False,
                )
                booking_show_id = show["id"]
                producer_expected += float(show["producer_cash_target_amount"] or 0)

            conn.execute(
                """
                INSERT INTO caserio_event_lines (
                    event_id, line_type, description, artist, amount,
                    booking_show_id, notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    line.line_type,
                    line.description.strip(),
                    line_artist,
                    line.amount,
                    booking_show_id,
                    line_notes,
                    now,
                ),
            )

        total_expected = caserio_expected + producer_expected
        balance = total_expected - request.received_amount
        conn.execute(
            """
            UPDATE caserio_events
            SET producer_expected_amount = ?,
                total_expected_amount = ?,
                balance_amount = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (producer_expected, total_expected, balance, now, event_id),
        )
        item = fetch_caserio_event_item(conn, event_id)

    return {
        "item": item,
    }


@app.post("/booking/shows")
def create_booking_show(
    request: BookingQuickShowRequest,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    payload = prepare_booking_show_payload(request)
    now = datetime.now().isoformat(timespec="seconds")
    settlement_status, settlement_closed_at = derive_booking_settlement(request, payload, now)

    with booking_connect() as conn:
        require_module_permission(conn, x_vpo_username, "booking", "create", artist=payload["artist"])
        booking_event_id = resolve_booking_event_for_new_settlement(
            conn,
            requested_event_id=request.booking_event_id,
            booking_mode="individual",
            artists=[payload["artist"]],
            event_date=payload["show_date"],
            venue=payload["venue"],
            city=payload["city"],
            cachet_amount=float(payload["contracted_cachet"]),
            currency=request.currency,
            fx_rate=request.fx_rate,
            tour_manager=payload["tour_manager"],
            seller=payload["seller"],
            settlement_status=request.status,
            actor_username=x_vpo_username,
        )
        cursor = conn.execute(
            """
            INSERT INTO booking_shows (
                booking_event_id, artist, show_date, venue, city, tour_manager, seller, status,
                currency, fx_rate, contracted_cachet_amount, venue_collected_amount,
                venue_balance_amount, venue_payment_status, venue_shortfall_policy,
                venue_payment_notes,
                cachet_amount, expenses_amount, net_amount,
                pre_split_adjustments_amount, split_base_amount,
                artist_percent, producer_percent, artist_share_amount, producer_share_amount,
                artist_cash_target_amount, producer_cash_target_amount,
                artist_paid_amount, producer_received_amount, balance_artist_amount,
                balance_producer_amount, receipt_refs_json, settlement_status,
                settlement_closed_at, booking_commission_exempt, booking_commission_notes,
                notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                booking_event_id,
                payload["artist"],
                payload["show_date"],
                payload["venue"],
                payload["city"],
                payload["tour_manager"],
                payload["seller"],
                request.status,
                request.currency,
                request.fx_rate,
                payload["contracted_cachet"],
                payload["venue_collected"],
                payload["venue_balance"],
                payload["venue_payment_status"],
                payload["venue_shortfall_policy"],
                payload["venue_payment_notes"],
                payload["effective_cachet_amount"],
                payload["expenses_amount"],
                payload["net_amount"],
                payload["pre_split_adjustments_amount"],
                payload["split_base_amount"],
                request.artist_percent,
                payload["producer_percent"],
                payload["artist_share"],
                payload["producer_share"],
                payload["artist_cash_target"],
                payload["producer_cash_target"],
                payload["artist_paid_amount"],
                payload["producer_received_amount"],
                payload["balance_artist"],
                payload["balance_producer"],
                json.dumps(payload["receipt_refs"], ensure_ascii=False),
                settlement_status,
                settlement_closed_at,
                payload["booking_commission_exempt"],
                payload["booking_commission_notes"],
                payload["notes"],
                now,
                now,
            ),
        )
        show_id = int(cursor.lastrowid)
        replace_booking_show_children(conn, show_id, request, payload, now)
        conn.execute(
            """
            UPDATE booking_events
            SET settlement_status = ?,
                operational_status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                "cerrada" if settlement_status == "cerrado" else "pendiente",
                "realizado" if request.status in {"realizado", "rendido", "aprobado", "no_cobrado"} or payload["show_date"] < date.today().isoformat() else "programado",
                now,
                booking_event_id,
            ),
        )
        item = fetch_booking_show_item(conn, show_id)

    return {
        "item": item,
    }


@app.put("/booking/shows/{show_id}")
def update_booking_show(
    show_id: int,
    request: BookingQuickShowRequest,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    now = datetime.now().isoformat(timespec="seconds")

    with booking_connect() as conn:
        existing = conn.execute("SELECT artist FROM booking_shows WHERE id = ?", (show_id,)).fetchone()
        requested_artist = clean_booking_artist(request.artist) or ""
        existing_artist = clean_booking_artist(existing["artist"]) if existing else ""
        require_module_permission(
            conn,
            x_vpo_username,
            "booking",
            "edit",
            artist=requested_artist,
            existing_artist=existing_artist,
        )
        item = update_booking_show_from_request(conn, show_id, request, now)

    return {
        "item": item,
    }


@app.get("/booking/shows/{show_id}/account")
def booking_show_account(
    show_id: int,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    with booking_connect() as conn:
        existing = conn.execute("SELECT id, artist FROM booking_shows WHERE id = ?", (show_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Show no encontrado.")
        require_module_permission(
            conn,
            x_vpo_username,
            "booking",
            "access",
            existing_artist=clean_booking_artist(existing["artist"]),
        )
        item = fetch_booking_show_item(conn, show_id)

    return {
        "item": item,
        "applications": item.get("account_applications", []),
        "open_balances": {
            "artist": item.get("open_balance_artist_amount", 0),
            "producer": item.get("open_balance_producer_amount", 0),
            "venue": item.get("open_venue_balance_amount", 0),
            "total": item.get("account_open_balance_amount", 0),
        },
        "db_driver": operational_db_settings().driver,
    }


@app.post("/booking/shows/{show_id}/account/applications")
def create_booking_show_account_application(
    show_id: int,
    request: BookingAccountApplicationRequest,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    application_date = validate_iso_date(request.application_date)
    now = datetime.now().isoformat(timespec="seconds")

    with booking_connect() as conn:
        existing = conn.execute("SELECT * FROM booking_shows WHERE id = ?", (show_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Show no encontrado.")
        require_module_permission(
            conn,
            x_vpo_username,
            "booking",
            "edit",
            existing_artist=clean_booking_artist(existing["artist"]),
        )
        linked_existing = None
        if request.linked_show_id is not None:
            linked_existing = conn.execute("SELECT * FROM booking_shows WHERE id = ?", (request.linked_show_id,)).fetchone()
            if linked_existing is None:
                raise HTTPException(status_code=400, detail="El show vinculado no existe.")
            require_module_permission(
                conn,
                x_vpo_username,
                "booking",
                "edit",
                existing_artist=clean_booking_artist(linked_existing["artist"]),
            )

        ensure_booking_account_applications_table(conn)
        show = row_to_booking_show(existing)
        previous_rows = conn.execute(
            """
            SELECT *
            FROM booking_account_applications
            WHERE show_id = ?
            ORDER BY application_date, id
            """,
            (show_id,),
        ).fetchall()
        previous_applications = [row_to_booking_account_application(row) for row in previous_rows]
        current_balance = booking_open_balance_for_target(show, previous_applications, request.target_balance)
        effect_amount = booking_application_effect(current_balance, request.amount, request.target_balance)
        applied_amount = abs(effect_amount)
        counterpart_target, counterpart_effect = booking_same_show_counterpart_effect(
            show,
            previous_applications,
            request.target_balance,
            effect_amount,
        )
        linked_effect_amount = None
        linked_counterpart_target = None
        linked_counterpart_effect = None
        if request.application_type == "compensation" and linked_existing is not None:
            if request.target_balance == "venue":
                raise HTTPException(status_code=400, detail="La deuda de boliche se salda como pago, no como compensacion entre shows.")
            linked_show = row_to_booking_show(linked_existing)
            linked_rows = conn.execute(
                """
                SELECT *
                FROM booking_account_applications
                WHERE show_id = ?
                ORDER BY application_date, id
                """,
                (request.linked_show_id,),
            ).fetchall()
            linked_applications = [row_to_booking_account_application(row) for row in linked_rows]
            linked_balance = booking_open_balance_for_target(linked_show, linked_applications, request.target_balance)
            if abs(linked_balance) <= 0.01 or current_balance * linked_balance >= 0:
                raise HTTPException(
                    status_code=400,
                    detail="El show vinculado debe tener saldo abierto del mismo tipo y signo contrario.",
                )
            linked_effect_amount = -effect_amount
            if abs(linked_effect_amount) > abs(linked_balance) + 0.01:
                raise HTTPException(status_code=400, detail="La compensacion supera el saldo abierto del show vinculado.")
            if abs(abs(linked_balance) - abs(linked_effect_amount)) <= 0.01:
                linked_effect_amount = -linked_balance
            linked_counterpart_target, linked_counterpart_effect = booking_same_show_counterpart_effect(
                linked_show,
                linked_applications,
                request.target_balance,
                linked_effect_amount,
            )
        notes = (request.notes or "").strip() or None
        counterparty = (request.counterparty or "").strip() or None
        conn.execute(
            """
            INSERT INTO booking_account_applications (
                show_id, application_date, target_balance, application_type,
                amount, effect_amount, payment_method, counterparty, linked_show_id,
                proof_refs_json, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                show_id,
                application_date,
                request.target_balance,
                request.application_type,
                applied_amount,
                effect_amount,
                request.payment_method,
                counterparty,
                request.linked_show_id,
                booking_application_json_value(conn, request.proof_refs),
                notes,
                now,
                now,
            ),
        )
        if counterpart_target is not None and counterpart_effect is not None:
            counterpart_notes_parts = [f"Contrapartida contable automatica de aplicacion en {request.target_balance}"]
            if notes:
                counterpart_notes_parts.append(notes)
            conn.execute(
                """
                INSERT INTO booking_account_applications (
                    show_id, application_date, target_balance, application_type,
                    amount, effect_amount, payment_method, counterparty, linked_show_id,
                    proof_refs_json, notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    show_id,
                    application_date,
                    counterpart_target,
                    "adjustment",
                    abs(counterpart_effect),
                    counterpart_effect,
                    "ajuste",
                    counterparty,
                    request.linked_show_id,
                    booking_application_json_value(conn, request.proof_refs),
                    " | ".join(counterpart_notes_parts),
                    now,
                    now,
                ),
            )
        item = fetch_booking_show_item(conn, show_id)
        item = update_booking_settlement_from_account(conn, show_id, item, request.application_type, now)
        linked_item = None
        if linked_existing is not None and linked_effect_amount is not None:
            mirror_notes_parts = [f"Compensacion espejo desde show #{show_id}"]
            if notes:
                mirror_notes_parts.append(notes)
            conn.execute(
                """
                INSERT INTO booking_account_applications (
                    show_id, application_date, target_balance, application_type,
                    amount, effect_amount, payment_method, counterparty, linked_show_id,
                    proof_refs_json, notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.linked_show_id,
                    application_date,
                    request.target_balance,
                    "compensation",
                    abs(linked_effect_amount),
                    linked_effect_amount,
                    "compensacion",
                    counterparty,
                    show_id,
                    booking_application_json_value(conn, request.proof_refs),
                    " | ".join(mirror_notes_parts),
                    now,
                    now,
                ),
            )
            if linked_counterpart_target is not None and linked_counterpart_effect is not None:
                linked_counterpart_notes_parts = [f"Contrapartida contable automatica de compensacion desde show #{show_id}"]
                if notes:
                    linked_counterpart_notes_parts.append(notes)
                conn.execute(
                    """
                    INSERT INTO booking_account_applications (
                        show_id, application_date, target_balance, application_type,
                        amount, effect_amount, payment_method, counterparty, linked_show_id,
                        proof_refs_json, notes, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.linked_show_id,
                        application_date,
                        linked_counterpart_target,
                        "adjustment",
                        abs(linked_counterpart_effect),
                        linked_counterpart_effect,
                        "ajuste",
                        counterparty,
                        show_id,
                        booking_application_json_value(conn, request.proof_refs),
                        " | ".join(linked_counterpart_notes_parts),
                        now,
                        now,
                    ),
                )
            linked_item = fetch_booking_show_item(conn, request.linked_show_id)
            linked_item = update_booking_settlement_from_account(
                conn,
                request.linked_show_id,
                linked_item,
                "compensation",
                now,
            )

    return {
        "item": item,
        "linked_item": linked_item,
    }


@app.post("/booking/account-movements")
def create_booking_account_parent_movement(
    request: BookingAccountParentMovementRequest,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    movement_date = validate_iso_date(request.movement_date)
    artist = clean_booking_artist(request.artist)
    if not artist:
        raise HTTPException(status_code=400, detail="Elegir un artista para el movimiento.")
    amount = float(request.amount or 0)
    if amount <= 0.01:
        raise HTTPException(status_code=400, detail="El importe del movimiento debe ser mayor a cero.")
    now = datetime.now().isoformat(timespec="seconds")
    notes = (request.notes or "").strip() or None
    counterparty = (request.counterparty or "").strip() or None
    proof_refs = clean_receipt_refs(request.proof_refs)

    seen_shows: set[int] = set()
    if not request.applications:
        raise HTTPException(status_code=400, detail="Seleccionar al menos un show para aplicar.")
    for application in request.applications:
        if application.show_id in seen_shows:
            raise HTTPException(status_code=400, detail="Un movimiento padre no puede repetir el mismo show.")
        seen_shows.add(application.show_id)

    with booking_connect() as conn:
        require_module_permission(conn, x_vpo_username, "booking", "edit", artist=artist)
        ensure_booking_account_applications_table(conn)

        prepared_applications: list[dict] = []
        applied_amount = 0.0
        for application in request.applications:
            existing = conn.execute("SELECT * FROM booking_shows WHERE id = ?", (application.show_id,)).fetchone()
            if existing is None:
                raise HTTPException(status_code=404, detail=f"Show #{application.show_id} no encontrado.")
            show_artist = clean_booking_artist(existing["artist"])
            if (show_artist or "").casefold() != artist.casefold():
                raise HTTPException(
                    status_code=400,
                    detail=f"Show #{application.show_id} pertenece a {show_artist}, no a {artist}.",
                )
            require_module_permission(
                conn,
                x_vpo_username,
                "booking",
                "edit",
                existing_artist=show_artist,
            )
            show = row_to_booking_show(existing)
            previous_rows = conn.execute(
                """
                SELECT *
                FROM booking_account_applications
                WHERE show_id = ?
                ORDER BY application_date, id
                """,
                (application.show_id,),
            ).fetchall()
            previous_applications = [row_to_booking_account_application(row) for row in previous_rows]
            current_balance = booking_open_balance_for_target(show, previous_applications, application.target_balance)
            effect_amount = booking_application_effect(current_balance, application.amount, application.target_balance)
            counterpart_target, counterpart_effect = booking_same_show_counterpart_effect(
                show,
                previous_applications,
                application.target_balance,
                effect_amount,
            )
            application_type = booking_parent_application_type(
                request.movement_type,
                application.target_balance,
                current_balance,
            )
            prepared_applications.append(
                {
                    "show_id": application.show_id,
                    "target_balance": application.target_balance,
                    "application_type": application_type,
                    "amount": abs(effect_amount),
                    "effect_amount": effect_amount,
                    "counterpart_target": counterpart_target,
                    "counterpart_effect": counterpart_effect,
                }
            )
            applied_amount += abs(effect_amount)

        if applied_amount <= 0.01:
            raise HTTPException(status_code=400, detail="No hay importe aplicado a shows.")
        if applied_amount > amount + 0.01:
            raise HTTPException(status_code=400, detail="La suma aplicada supera el importe del movimiento.")

        cursor = conn.execute(
            """
            INSERT INTO booking_account_movements (
                movement_date, artist, movement_type, amount, applied_amount, unapplied_amount,
                payment_method, counterparty, proof_refs_json, notes, created_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                movement_date,
                artist,
                request.movement_type,
                amount,
                applied_amount,
                max(0.0, amount - applied_amount),
                request.payment_method,
                counterparty,
                booking_application_json_value(conn, proof_refs),
                notes,
                x_vpo_username,
                now,
                now,
            ),
        )
        movement_id = int(cursor.lastrowid)

        affected_show_ids: set[int] = set()
        for application in prepared_applications:
            conn.execute(
                """
                INSERT INTO booking_account_applications (
                    show_id, application_date, target_balance, application_type,
                    amount, effect_amount, payment_method, counterparty, linked_show_id, movement_id,
                    proof_refs_json, notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application["show_id"],
                    movement_date,
                    application["target_balance"],
                    application["application_type"],
                    application["amount"],
                    application["effect_amount"],
                    request.payment_method,
                    counterparty,
                    None,
                    movement_id,
                    booking_application_json_value(conn, proof_refs),
                    notes,
                    now,
                    now,
                ),
            )
            affected_show_ids.add(application["show_id"])
            if application["counterpart_target"] is not None and application["counterpart_effect"] is not None:
                counterpart_notes_parts = [f"Contrapartida contable automatica de movimiento padre #{movement_id}"]
                if notes:
                    counterpart_notes_parts.append(notes)
                conn.execute(
                    """
                    INSERT INTO booking_account_applications (
                        show_id, application_date, target_balance, application_type,
                        amount, effect_amount, payment_method, counterparty, linked_show_id, movement_id,
                        proof_refs_json, notes, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        application["show_id"],
                        movement_date,
                        application["counterpart_target"],
                        "adjustment",
                        abs(application["counterpart_effect"]),
                        application["counterpart_effect"],
                        "ajuste",
                        counterparty,
                        None,
                        movement_id,
                        booking_application_json_value(conn, proof_refs),
                        " | ".join(counterpart_notes_parts),
                        now,
                        now,
                    ),
                )

        updated_shows = []
        for affected_show_id in sorted(affected_show_ids):
            item = fetch_booking_show_item(conn, affected_show_id)
            first_application = next(
                (application for application in prepared_applications if application["show_id"] == affected_show_id),
                None,
            )
            application_type = first_application["application_type"] if first_application else "adjustment"
            updated_shows.append(
                update_booking_settlement_from_account(conn, affected_show_id, item, application_type, now)
            )

        movement_row = conn.execute(
            "SELECT * FROM booking_account_movements WHERE id = ?",
            (movement_id,),
        ).fetchone()

    return {
        "item": row_to_booking_account_movement(movement_row),
        "updated_shows": updated_shows,
        "db_driver": operational_db_settings().driver,
    }


@app.post("/booking/account-block-settlements")
def create_booking_account_block_settlement(
    request: BookingAccountBlockSettlementRequest,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()
    settlement_date = validate_iso_date(request.settlement_date)
    artist = clean_booking_artist(request.artist)
    if not artist:
        raise HTTPException(status_code=400, detail="Elegir un artista para cerrar el bloque.")
    show_ids = list(dict.fromkeys(int(show_id) for show_id in request.show_ids))
    if not show_ids:
        raise HTTPException(status_code=400, detail="Seleccionar al menos un show.")
    amount = float(request.amount or 0)
    if amount <= 0.01:
        raise HTTPException(status_code=400, detail="El importe pagado/cobrado debe ser mayor a cero.")
    now = datetime.now().isoformat(timespec="seconds")
    notes = (request.notes or "").strip() or None
    counterparty = (request.counterparty or "").strip() or None
    proof_refs = clean_receipt_refs(request.proof_refs)

    with booking_connect() as conn:
        require_module_permission(conn, x_vpo_username, "booking", "edit", artist=artist)
        ensure_booking_account_applications_table(conn)
        placeholders = ",".join("?" for _ in show_ids)
        rows = conn.execute(
            f"""
            SELECT *
            FROM booking_shows
            WHERE id IN ({placeholders})
            ORDER BY show_date, id
            """,
            show_ids,
        ).fetchall()
        if len(rows) != len(show_ids):
            raise HTTPException(status_code=404, detail="Alguno de los shows seleccionados no existe.")

        selected: list[dict] = []
        aggregate_artist = 0.0
        aggregate_producer = 0.0
        aggregate_venue = 0.0
        for row in rows:
            show_artist = clean_booking_artist(row["artist"])
            if (show_artist or "").casefold() != artist.casefold():
                raise HTTPException(
                    status_code=400,
                    detail=f"Show #{row['id']} pertenece a {show_artist}, no a {artist}.",
                )
            require_module_permission(conn, x_vpo_username, "booking", "edit", existing_artist=show_artist)
            show = row_to_booking_show(row)
            previous_rows = conn.execute(
                """
                SELECT *
                FROM booking_account_applications
                WHERE show_id = ?
                ORDER BY application_date, id
                """,
                (show["id"],),
            ).fetchall()
            previous_applications = [row_to_booking_account_application(item) for item in previous_rows]
            open_artist = booking_open_balance_for_target(show, previous_applications, "artist")
            open_producer = booking_open_balance_for_target(show, previous_applications, "producer")
            open_venue = booking_open_balance_for_target(show, previous_applications, "venue")
            aggregate_artist += open_artist
            aggregate_producer += open_producer
            aggregate_venue += open_venue
            selected.append({
                "show": show,
                "open_artist": open_artist,
                "open_producer": open_producer,
                "open_venue": open_venue,
            })

        if abs(aggregate_venue) > 0.01:
            raise HTTPException(
                status_code=400,
                detail="El cierre de bloque no salda deuda de boliche. Primero resolver esa deuda por separado.",
            )
        aggregate_net = booking_current_account_net(aggregate_producer, aggregate_artist)
        required_amount = abs(aggregate_net)
        if required_amount <= 0.01:
            raise HTTPException(status_code=400, detail="El bloque seleccionado ya esta saldado.")
        if abs(amount - required_amount) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=(
                    "El importe no coincide con el saldo neto del bloque. "
                    f"Saldo esperado: {required_amount:.2f}."
                ),
            )

        movement_type = "pago_saldo_artista" if aggregate_net < -0.01 else "cobro_deuda_booking"
        cursor = conn.execute(
            """
            INSERT INTO booking_account_movements (
                movement_date, artist, movement_type, amount, applied_amount, unapplied_amount,
                payment_method, counterparty, proof_refs_json, notes, created_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                settlement_date,
                artist,
                movement_type,
                amount,
                required_amount,
                0.0,
                request.payment_method,
                counterparty,
                booking_application_json_value(conn, proof_refs),
                notes,
                x_vpo_username,
                now,
                now,
            ),
        )
        movement_id = int(cursor.lastrowid)

        affected_show_ids: set[int] = set()
        for item in selected:
            show_id = item["show"]["id"]
            for target_balance, current_balance in (
                ("artist", item["open_artist"]),
                ("producer", item["open_producer"]),
            ):
                if abs(current_balance) <= 0.01:
                    continue
                effect_amount = -current_balance
                application_type = booking_block_application_type(target_balance, current_balance, aggregate_net)
                conn.execute(
                    """
                    INSERT INTO booking_account_applications (
                        show_id, application_date, target_balance, application_type,
                        amount, effect_amount, payment_method, counterparty, linked_show_id, movement_id,
                        proof_refs_json, notes, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        show_id,
                        settlement_date,
                        target_balance,
                        application_type,
                        abs(effect_amount),
                        effect_amount,
                        request.payment_method
                        if application_type in {"artist_payment", "artist_reimbursement", "producer_reimbursement"}
                        else "compensacion",
                        counterparty,
                        None,
                        movement_id,
                        booking_application_json_value(conn, proof_refs),
                        notes,
                        now,
                        now,
                    ),
                )
                affected_show_ids.add(show_id)

        updated_shows = []
        for show_id in sorted(affected_show_ids):
            item = fetch_booking_show_item(conn, show_id)
            updated_shows.append(update_booking_settlement_from_account(conn, show_id, item, "artist_payment", now))

        movement_row = conn.execute(
            "SELECT * FROM booking_account_movements WHERE id = ?",
            (movement_id,),
        ).fetchone()

    return {
        "item": row_to_booking_account_movement(movement_row),
        "updated_shows": updated_shows,
        "net_balance": aggregate_net,
        "db_driver": operational_db_settings().driver,
    }


@app.delete("/booking/shows/{show_id}")
def delete_booking_show(
    show_id: int,
    x_vpo_api_key: str | None = Header(default=None),
    x_vpo_username: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    init_booking_db()

    with booking_connect() as conn:
        existing = conn.execute("SELECT id, artist FROM booking_shows WHERE id = ?", (show_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Show no encontrado.")
        require_module_permission(
            conn,
            x_vpo_username,
            "booking",
            "approve",
            existing_artist=clean_booking_artist(existing["artist"]),
        )
        conn.execute("DELETE FROM finance_recovery_applications WHERE source_id LIKE ?", (f"{show_id}:pre_split_auto:%",))
        ensure_booking_account_applications_table(conn)
        conn.execute("DELETE FROM booking_account_applications WHERE show_id = ?", (show_id,))
        conn.execute("DELETE FROM booking_movements WHERE show_id = ?", (show_id,))
        conn.execute("DELETE FROM booking_show_expenses WHERE show_id = ?", (show_id,))
        conn.execute("DELETE FROM booking_pre_split_adjustments WHERE show_id = ?", (show_id,))
        conn.execute("DELETE FROM booking_direct_commissions WHERE show_id = ?", (show_id,))
        conn.execute("DELETE FROM booking_external_shares WHERE show_id = ?", (show_id,))
        conn.execute("DELETE FROM booking_artist_adjustments WHERE show_id = ?", (show_id,))
        conn.execute("DELETE FROM booking_shows WHERE id = ?", (show_id,))

    return {"ok": True, "deleted_id": show_id, "db_driver": operational_db_settings().driver}
