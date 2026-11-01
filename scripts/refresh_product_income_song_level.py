"""Rebuild product context in historical song summaries from admitted raw, without reingestion."""
from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path
import tempfile

os.environ.setdefault('POLARS_MAX_THREADS','4')
import polars as pl
import pyarrow.compute as pc
import pyarrow.parquet as pq

SOURCES=('fuga','onerpm','dashgo')
BASE=Path(os.environ.get('VPO_PROJECT_ROOT',r'C:\royalties_pipeline'))


def refresh(marts: Path) -> Path:
    raw=marts/'standardized_raw_all_sources.parquet'
    song=marts/'song_level_all_sources.parquet'
    signature=(raw.stat().st_mtime_ns,raw.stat().st_size)
    from build_consolidated_marts import consolidate
    with tempfile.TemporaryDirectory(prefix='product-song-') as temporary:
        folder=Path(temporary)
        writers={}
        schemas={}
        inputs={}
        raw_names=set(pq.read_schema(raw).names)
        context={'video_id','video_id_source','channel_id','units','dsp_normalized','monetization_normalized',
            'content_origin_normalized','classification_status','product_upc','asset_product_type','product_type'}
        for source in SOURCES:
            native=BASE/'warehouse/marts'/f'standardized_raw_{source}.parquet'
            schemas[source]=[n for n in pq.read_schema(native).names if n in raw_names]
            schemas[source]+=sorted((context&raw_names)-set(schemas[source]))
            # Reuse a native input only when its admitted movements reconcile,
            # including an order-independent hash of their identity and money.
            from lib.catalog_identity_corrections import correct_recording_identity
            left=correct_recording_identity(pl.scan_parquet(native))
            right=pl.scan_parquet(raw).filter(pl.col('source')==source)
            common=set(left.collect_schema().names())&raw_names
            identity=[n for n in ['source','account','statement_file_name','statement_file_hash','asset_isrc',
                'product_upc','catalog_number','video_id','track_id','transaction_month','amount_usd'] if n in common]
            metrics=[pl.len(),pl.col('amount_usd').sum(),pl.struct(identity).hash(seed=42).sum().alias('identity')]
            if left.select(metrics).collect(engine='streaming').equals(right.select(metrics).collect(engine='streaming')):
                inputs[source]=native
        missing=set(SOURCES)-set(inputs)
        try:
            # Read a bounded batch of the immutable admitted source, once.
            for batch in (pq.ParquetFile(raw).iter_batches(batch_size=65536,use_threads=False) if missing else []):
                values=batch.column(batch.schema.get_field_index('source'))
                for source in missing:
                    part=batch.filter(pc.equal(values,source)).select(schemas[source])
                    if not part.num_rows:continue
                    if source not in writers:
                        writers[source]=pq.ParquetWriter(folder/f'standardized_raw_{source}.parquet',part.schema,compression='zstd')
                    writers[source].write_batch(part)
        finally:
            for writer in writers.values():writer.close()
        parts=[]
        print('Crudo histórico leído; reconstruyendo resúmenes por distribuidora.',flush=True)
        for source in SOURCES:
            if source not in writers and source not in inputs:continue
            builder=importlib.import_module('build_song_level_'+source)
            builder.INPUT_PATH=inputs.get(source,folder/f'standardized_raw_{source}.parquet')
            builder.OUTPUT_PATH=folder/f'song_level_{source}.parquet'
            builder.main();parts.append(builder.OUTPUT_PATH)
        other=folder/'song_level_other.parquet'
        pl.scan_parquet(song).filter(~pl.col('source').is_in(SOURCES)).sink_parquet(other,compression='zstd')
        target=folder/song.name
        consolidate([*parts,other],target)
        keys=['source','account']
        old=pl.scan_parquet(song).group_by(keys).agg(pl.col('amount_usd').sum().alias('old')).collect()
        new=pl.scan_parquet(target).group_by(keys).agg(pl.col('amount_usd').sum().alias('new')).collect()
        diff=old.join(new,on=keys,how='full',coalesce=True,nulls_equal=True)
        if diff.filter(pl.col('old').is_null()|pl.col('new').is_null()|((pl.col('old')-pl.col('new')).abs()>0.000001)).height:
            raise ValueError('El resumen histórico no concilia por distribuidora/cuenta. No se reemplazó ningún archivo.')
        if signature!=(raw.stat().st_mtime_ns,raw.stat().st_size):raise ValueError('Cambió el crudo admitido durante la reconstrucción.')
        # TemporaryDirectory can be on another drive, so copy before atomic replacement.
        import shutil
        pending=marts/(song.name+'.product-income.tmp')
        shutil.copyfile(target,pending);pending.replace(song)
    return song


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--marts',type=Path,default=BASE/'warehouse/marts')
    print(refresh(parser.parse_args().marts))


if __name__=='__main__':main()
