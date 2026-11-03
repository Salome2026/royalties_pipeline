"""Pinned, exact distribution-contract membership for every income report table."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import json

import polars as pl

CURRENT = ContextVar('royalty_contract_filter', default=None)


def normalize_numbers(values):
    if not isinstance(values, (list, tuple)) or len(values) > 100:
        raise ValueError('Ingresá hasta 100 números de contrato.')
    if any(type(value) is not int or value < 10010 for value in values):
        raise ValueError('Ingresá solo números de contrato válidos, separados por comas.')
    return sorted(set(values))


def freeze_filter(numbers, templates, snapshot):
    numbers = normalize_numbers(numbers)
    known = {row['number']: row for row in templates}
    missing = set(numbers) - known.keys()
    if missing:
        raise ValueError('No existen los contratos: ' + ', '.join(map(str, sorted(missing))))
    selected = sorted({row['isrc'] for row in snapshot['contracts']
        if any(a.get('distribution_contract_number') in numbers
               for a in row['split'].get('agreements') or [])})
    if not selected:
        raise ValueError('Los contratos seleccionados no tienen temas vinculados.')
    return {'schema_version': 1, 'release_id': snapshot['release_id'],
            'numbers': numbers, 'isrcs': selected,
            'templates': deepcopy([known[n] for n in numbers]),
            'associations': deepcopy(snapshot['associations'])}


def require_filter(snapshot, numbers, release):
    if (not snapshot or snapshot.get('schema_version') != 1
            or snapshot.get('numbers') != normalize_numbers(numbers)
            or snapshot.get('release_id') != release or not snapshot.get('isrcs')
            or any(not isinstance((snapshot.get('associations') or {}).get(k), dict)
                   for k in ('included', 'excluded'))):
        raise ValueError('Falta la selección de contratos de la versión publicada del reporte.')
    return snapshot


@contextmanager
def use_filter(snapshot):
    token = CURRENT.set(snapshot)
    try:
        yield
    finally:
        CURRENT.reset(token)


def filter_income(frame):
    snapshot = CURRENT.get()
    if snapshot is None:
        return frame
    columns = set(frame.collect_schema().names())
    frame = frame.with_columns([pl.col(name).cast(pl.String, strict=False) for name in
        ('product_upc', 'video_id', 'track_id', 'source', 'account') if name in columns])
    selected = snapshot['isrcs']
    # Native ISRCs are authoritative. Never capture another song via a shared UPC.
    native = pl.col('asset_isrc').fill_null('').str.contains(r'^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$') if 'asset_isrc' in columns else pl.lit(False)
    included, excluded = [], []
    temporary = []
    for kind, field in [('UPC', 'product_upc'), ('VIDEO', 'video_id'), ('TRACK', 'track_id')]:
        if field not in columns or not {'source', 'account'} <= columns:
            continue
        for mode, expressions in [('included', included), ('excluded', excluded)]:
            records = []
            for key, roots in snapshot['associations'][mode].items():
                code_kind, code, source, account = json.loads(key)
                if code_kind == kind:
                    records.append({field: code, 'source': source, 'account': account, '_roots': roots})
            if not records:
                continue
            name = f'_contract_{mode}_{kind}'
            lookup = pl.DataFrame(records, schema={field: pl.String, 'source': pl.String, 'account': pl.String, '_roots': pl.List(pl.String)}).rename({'_roots': name})
            frame = frame.join(lookup.lazy(), on=[field, 'source', 'account'], how='left', maintain_order='left')
            roots = pl.col(name).fill_null(pl.lit([], dtype=pl.List(pl.String)))
            if kind == 'UPC' and '_income_upc_pending' in columns:
                roots = pl.when(pl.col('_income_upc_pending').fill_null(False)).then(pl.lit([], dtype=pl.List(pl.String))).otherwise(roots)
            expressions.append(roots)
            temporary.append(name)
    empty = pl.lit([], dtype=pl.List(pl.String))
    candidates = pl.concat_list(included).list.unique() if included else empty
    denied = pl.concat_list(excluded).list.unique() if excluded else empty
    candidates = candidates.list.set_difference(denied)
    associated = (candidates.list.len() == 1) & candidates.list.first().is_in(selected)
    if '_income_product_pending' in columns:
        associated &= ~pl.col('_income_product_pending').fill_null(False)
    if 'catalog_number' in columns:
        associated &= ~((pl.col('source') == 'ada') & (pl.col('catalog_number').fill_null('') != ''))
    primary = pl.col('catalog_key').is_in(['ISRC:' + code for code in selected])
    return frame.filter(pl.when(native).then(primary).otherwise(associated).fill_null(False)).drop(temporary)
