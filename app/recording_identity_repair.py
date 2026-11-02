"""Rebuild only confirmed recordings, preserving the rest of the published catalog."""
from pathlib import Path
import polars as pl

from scripts.lib.catalog_identity_corrections import video_corrections


def rebuild_catalog(original: Path, raw: Path, song: Path, output: Path, work: Path):
    from scripts import build_catalog_master as builder
    from scripts.lib.catalog_video_metadata import load_decisions
    rules = video_corrections()
    codes = sorted({code for r in rules for code in [r['canonical_isrc'], *r['reported_isrcs']]})
    videos = [r['video_id'] for r in rules]
    work.mkdir()
    scoped_raw, scoped_song = work/'standardized_raw_all_sources.parquet', work/'song_level_all_sources.parquet'
    pl.scan_parquet(raw).filter(pl.col('asset_isrc').is_in(codes) | pl.col('video_id').is_in(videos)).sink_parquet(scoped_raw)
    pl.scan_parquet(song).filter(pl.col('asset_isrc').is_in(codes) | pl.col('video_id').is_in(videos)).sink_parquet(scoped_song)
    names = ['MARTS_DIR', 'SONG_LEVEL_PATH', 'STANDARDIZED_PATHS']
    previous = {name: getattr(builder, name) for name in names}
    try:
        builder.MARTS_DIR, builder.SONG_LEVEL_PATH, builder.STANDARDIZED_PATHS = work, scoped_song, [scoped_raw]
        from scripts.lib.product_income import use_product_income
        from lib.product_income import use_product_income as use_native_product_income
        with use_product_income(None), use_native_product_income(None):
            native = builder.build_catalog_master(native_only=True)
    finally:
        for name, value in previous.items():
            setattr(builder, name, value)
    before = pl.read_parquet(original)
    by_key = {r['catalog_key']: r for r in before.to_dicts()}
    native_by_key = {r['catalog_key']: r for r in native.to_dicts()}
    # Display names, participants, manual metadata and external validations stay
    # as published. Recompute native money and identifiers from admitted rows.
    preserve = {'catalog_key', 'asset_isrc', 'track_title', 'artist_statement',
        'track_title_normalized', 'artist_statement_normalized', 'catalog_built_at'}
    for code in codes:
        key = 'ISRC:' + code
        if key not in native_by_key or key not in by_key:
            raise ValueError('Missing original or rebuilt recording in identity repair')
        for name, value in native_by_key[key].items():
            if name in before.columns and name not in preserve:
                by_key[key][name] = value
    decisions = load_decisions()
    for rule in rules:
        target = 'ISRC:' + rule['canonical_isrc']
        alias = 'VIDEO:' + rule['video_id']
        for code in codes:
            key = 'ISRC:' + code
            row = by_key[key]
            def replace_pipe(field, value):
                if field not in row: return
                values = set((row.get(field) or '').split(' | ')) - {'', value}
                if key == target: values.add(value)
                row[field] = ' | '.join(sorted(values)) or None
            replace_pipe('video_ids', rule['video_id'])
            for field, value in [('catalog_aliases', alias), ('video_isrcs', rule['video_isrc'])]:
                values = set(row.get(field) or []) - {value}
                if key == target: values.add(value)
                row[field] = sorted(values)
            import json
            relationships = [r for r in json.loads(row.get('video_relationships_json') or '[]')
                if r['video_isrc'] != rule['video_isrc']]
            if key == target:
                relationships.append(next(r for r in decisions['entries'] if r['video_isrc'] == rule['video_isrc']))
            row['video_relationships_json'] = json.dumps(sorted(relationships, key=lambda r:r['video_isrc']), ensure_ascii=False, sort_keys=True)
    after = pl.DataFrame(list(by_key.values()), schema=before.schema)
    if before.height != after.height:
        raise ValueError('Identity repair changed catalog membership')
    unchanged_before = before.filter(~pl.col('asset_isrc').is_in(codes)).sort('catalog_key')
    unchanged_after = after.filter(~pl.col('asset_isrc').is_in(codes)).sort('catalog_key')
    if not unchanged_before.equals(unchanged_after):
        raise ValueError('Unrelated catalog entries changed')
    after.write_parquet(output)
    return {'recordings': codes, 'unrelated_rows_preserved': unchanged_after.height}
