"""Explicit royalty workspaces. A missing scope always means ordinary royalties."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator

SCOPE: ContextVar[str] = ContextVar('royalty_scope', default='regular')
MARTS: ContextVar[dict[str, Path]] = ContextVar('royalty_scope_marts', default={})
STATUS: ContextVar[list[dict] | None] = ContextVar('royalty_scope_status', default=None)
RELEASE: ContextVar[str | None] = ContextVar('royalty_scope_release', default=None)
WML_ACCOUNT = '91230'
WML_LABEL = 'WML — base contractual al 100%'
WML_PREFIX = 'marts/wml'
WML_DATASET = 'royalties_wml'
WML_FILES = (
    'standardized_raw_all_sources.parquet', 'song_level_all_sources.parquet',
    'catalog_master.parquet', 'statement_summary_all_sources.parquet',
    'digital_income_statement_summary.parquet', 'royalties_dashboard_summary.parquet',
    'catalog_status.parquet', 'wml_isrc_references.parquet',
)

def is_wml() -> bool:
    return SCOPE.get() == 'wml'

def wml_release_prefix(release_id: str | None = None) -> str:
    import re
    release_id = release_id or RELEASE.get()
    if not release_id or not re.fullmatch(r'wml-[a-f0-9]{24}',release_id):
        raise RuntimeError('WML no tiene una versión publicada válida.')
    return f'{WML_PREFIX}/versions/{release_id}'

def validate_scope(value: str | None) -> str:
    result = value or 'regular'
    if result not in {'regular', 'wml'}:
        raise ValueError('Ámbito de regalías inválido.')
    return result

@contextmanager
def use_scope(value: str, *, marts: dict[str, Path] | None = None,
              catalog_status: list[dict] | None = None, release_id: str | None = None) -> Iterator[None]:
    token = SCOPE.set(validate_scope(value))
    paths_token = MARTS.set(marts or {})
    status_token = STATUS.set(catalog_status)
    release_token = RELEASE.set(release_id)
    try:
        yield
    finally:
        RELEASE.reset(release_token)
        STATUS.reset(status_token)
        MARTS.reset(paths_token)
        SCOPE.reset(token)

def wml_policy() -> dict[str, Any]:
    # Analytical interpretation, not an editable operational-policy fallback.
    return {
        'schema_version': 1, 'policy_version': 1, 'mode': 'isolated_wml_100',
        'updated_at': None, 'updated_by': 'wml-91230-base100-v1',
        'scope': 'wml', 'amount_basis': 'wml_contractual_base_100',
        'report_personalization': {'enabled': False, 'amount_basis': 'wml_contractual_base_100', 'scope': 'wml'},
        'entries': [{'policy_id': 'wml_91230', 'source': 'wml', 'account': WML_ACCOUNT,
            'display_name': WML_LABEL, 'report_net_adjustment_pct': 0,
            'sheet_rules': {'royalty_detail': {'catalog_view': True, 'statement_view': True,
                'cash_view': False, 'audit_view': True, 'revenue_basis': 'generation'}}}],
    }
