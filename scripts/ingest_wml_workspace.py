"""Ingest ONLY 91230 into an isolated immutable release, never ordinary marts."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
import polars as pl

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.royalty_scope import WML_FILES
from scripts.lib.store_taxonomy import add_store_dimensions
from scripts.lib.wml_references import build_references, REFERENCE_VERSION

INGEST_VERSION='wml-91230-base100-v1'
DEFAULT_ROOT=ROOT/'warehouse/isolated/wml'

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def write_json(path: Path,value: dict) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)

def semester(start: str,end: str) -> str:
    if not re.fullmatch(r'\d{4}-(06|12)',end):raise ValueError('Cierre semestral WML inválido.')
    expected=end[:4]+('-01' if end.endswith('06') else '-07')
    if start!=expected:raise ValueError('El statement WML no cubre un semestre completo.')
    return end[:4]+('-H1' if end.endswith('06') else '-H2')

def discover(input_root: Path) -> tuple[list[dict],list[dict]]:
    files=[];ignored=[];periods={}
    for path in sorted(input_root.iterdir()):
        if not path.is_file():continue
        match=re.fullmatch(r'Statement_91230_\d+_91230_(\d{4})(06|12)(\d{2})\.txt',path.name,re.I)
        if not match:
            ignored.append({'file':path.name,'reason':'support_document_or_other_account'})
            continue
        end=f'{match[1]}-{match[2]}'
        if match[3]!=('30' if match[2]=='06' else '31'):raise ValueError(f'Fecha inválida: {path.name}')
        digest=sha256(path)
        entry={'file':path.name,'path':str(path),'sha256':digest,'end_period':end,'bytes':path.stat().st_size}
        if end in periods:
            if periods[end]['sha256']==digest:
                ignored.append({'file':path.name,'reason':'identical_duplicate'});continue
            raise ValueError(f'Dos versiones distintas del semestre {end}. Conservar una versión vigente antes de procesar.')
        periods[end]=entry;files.append(entry)
    if not files:raise ValueError('No se encontraron TXT de la cuenta 91230.')
    return files,ignored

def standardize(path: Path,file_hash: str) -> tuple[pl.DataFrame,dict]:
    frame=pl.read_csv(path,separator='\t',quote_char=None,infer_schema=False,encoding='utf8',null_values='',
                      row_index_name='statement_row_number',row_index_offset=2)
    required={'Account','Start Period','End Period','Royalty Payable','Royalty Base','Sale Units','Royalty Rate','Share Tracks','Share Total Tracks','Product Title','Artist Name','ISRC','Product Type','Repdate Month ID','Recdate Month ID','Catalog Number'}
    if required-set(frame.columns):raise ValueError(f'Faltan columnas WML: {sorted(required-set(frame.columns))}')
    for name in ['Revenue Rate','Receipts','Tune Title','GPID','Country','Config','Dist Chan Desc','Digital Service Provider(DSP)']:
        if name not in frame.columns:frame=frame.with_columns(pl.lit(None,dtype=pl.String).alias(name))
    accounts=frame['Account'].unique().to_list()
    if accounts!=['91230']:raise ValueError(f'{path.name}: esperaba cuenta 91230, encontré {accounts}')
    starts=frame['Start Period'].unique().to_list();ends=frame['End Period'].unique().to_list()
    if len(starts)!=1 or len(ends)!=1:raise ValueError('El TXT mezcla períodos de liquidación.')
    start,end=starts[0],ends[0]
    label=semester(start,end)
    filename_end=re.search(r'(\d{4})(\d{2})\d{2}\.txt$',path.name,re.I)
    if not filename_end or end!=filename_end[1]+'-'+filename_end[2]:raise ValueError('El cierre no coincide con el nombre del archivo.')
    num=lambda name:pl.col(name).cast(pl.Float64,strict=True)
    frame=frame.with_columns([
        pl.coalesce(num('Royalty Rate'),num('Revenue Rate')).alias('wml_royalty_rate_pct'),
        num('Royalty Payable').alias('wml_reported_royalty_usd'),num('Sale Units').alias('units'),
    ]).with_columns([
        pl.when(pl.col('Royalty Base').is_not_null())
        .then(num('Royalty Base')*num('Sale Units')*num('Share Tracks')/num('Share Total Tracks'))
        .otherwise(num('Receipts')).alias('wml_base100_usd')
    ])
    bad=frame.filter(
        pl.col('wml_base100_usd').is_null()|(~pl.col('wml_base100_usd').is_finite())|
        pl.col('units').is_null()|pl.col('wml_reported_royalty_usd').is_null()|
        (~pl.col('units').is_finite())|(~pl.col('wml_reported_royalty_usd').is_finite())|(~pl.col('wml_royalty_rate_pct').is_finite())|
        pl.col('wml_royalty_rate_pct').is_null()|(pl.col('wml_royalty_rate_pct')<=0)|(pl.col('wml_royalty_rate_pct')>100)|
        (pl.col('Royalty Rate').is_not_null()&pl.col('Revenue Rate').is_not_null())|
        (pl.col('Royalty Base').is_not_null()&pl.col('Receipts').is_not_null())|
        ((pl.col('wml_base100_usd')*pl.col('wml_royalty_rate_pct')/100-pl.col('wml_reported_royalty_usd')).abs()>0.000001)
    )
    if bad.height:raise ValueError(f'{path.name}: {bad.height} líneas no reproducen la regalía de Warner.')
    frame=frame.with_columns([
        pl.lit('wml').alias('royalty_scope'),pl.lit('wml').alias('source'),pl.lit('91230').alias('account'),
        pl.lit('royalty_detail').alias('source_sheet'),pl.lit('wml_royalty_detail').alias('statement_type'),
        pl.lit('generation').alias('revenue_basis'),pl.lit('USD').alias('currency_original'),
        pl.lit(end).alias('statement_period'),pl.lit(start).alias('statement_start_period'),
        pl.lit(label).alias('statement_semester'),pl.lit('columns_validated_against_filename').alias('statement_period_source'),
        pl.lit('Semestre completo Start Period–End Period. Base contractual al 100%, antes de participaciones.').alias('statement_period_note'),
        pl.col('Repdate Month ID').alias('transaction_month'),pl.col('Recdate Month ID').alias('receipt_month'),
        pl.col('ISRC').alias('asset_isrc'),pl.col('Product Title').alias('track_statement_style'),
        pl.col('Product Title').alias('asset_title_statement'),pl.col('Product Title').alias('release_statement_style'),
        pl.col('Artist Name').alias('artist_statement_style'),pl.col('Artist Name').alias('asset_artist_statement'),
        pl.col('Product Type').alias('product_type'),pl.col('GPID').alias('gpid'),pl.col('GPID').alias('track_id'),
        pl.col('Catalog Number').alias('catalog_number'),pl.col('Country').alias('territory'),
        pl.col('Digital Service Provider(DSP)').alias('dsp'),pl.col('Digital Service Provider(DSP)').alias('store_name'),
        pl.col('Dist Chan Desc').alias('sale_type'),pl.col('Dist Chan Desc').alias('use_type'),
        pl.lit('Warner Music Latina').alias('label_statement_style'),
        pl.col('wml_base100_usd').alias('amount_usd'),pl.col('wml_base100_usd').alias('net_amount'),
        pl.col('wml_base100_usd').alias('net_amount_usd'),pl.col('wml_base100_usd').alias('gross_royalty_usd'),
        pl.lit(0.0).alias('deductible_fees_usd'),
        pl.when(pl.col('GPID').str.contains(r'^\d{12,14}$')).then(pl.col('GPID')).otherwise(None).alias('product_upc'),
        pl.lit(True).alias('include_in_catalog_view'),pl.lit(True).alias('include_in_statement_view'),
        pl.lit(False).alias('include_in_cash_view'),pl.lit(False).alias('possible_internal_transfer'),
        pl.lit(False).alias('has_share_in_out'),
        pl.when(pl.col('Product Type').str.contains('Video')).then(pl.lit('video')).otherwise(pl.lit('catalog')).alias('content_type'),
        pl.lit(path.name).alias('statement_file_name'),pl.lit(file_hash).alias('statement_file_hash'),
        pl.concat_str([pl.lit(file_hash),pl.col('statement_row_number').cast(pl.String)],separator=':').alias('movement_id'),
    ])
    frame=frame.with_columns(pl.concat_str([
        pl.when(pl.col('asset_isrc').is_not_null()).then(pl.lit('ISRC:')).otherwise(pl.lit('PRODUCT:')),
        pl.coalesce('asset_isrc','gpid','catalog_number')],separator='').alias('catalog_key'))
    frame=add_store_dimensions(frame.lazy(),set(frame.columns)).collect()
    return frame,{'file':path.name,'statement_period':end,'statement_semester':label,'rows':frame.height,
         'amount_usd':frame['amount_usd'].sum(),'warner_royalty_usd':frame['wml_reported_royalty_usd'].sum()}

def write_summaries(detail: Path,out: Path) -> None:
    lf=pl.scan_parquet(detail)
    song_keys=['source','account','source_sheet','revenue_basis','asset_isrc','track_id','gpid','catalog_number',
       'catalog_key','track_statement_style','asset_title_statement','release_statement_style','artist_statement_style',
       'asset_artist_statement','transaction_month','statement_period','statement_semester','product_upc','content_type',
       'include_in_cash_view','include_in_catalog_view','include_in_statement_view','possible_internal_transfer','statement_type']
    song=lf.group_by(song_keys).agg(pl.col('amount_usd').sum(),pl.col('units').sum(),pl.len().alias('raw_rows'))
    song.sink_parquet(out/'song_level_all_sources.parquet',compression='zstd')
    join=lambda name:pl.col(name).drop_nulls().unique().sort().str.join(' | ')
    cat=lf.group_by('catalog_key').agg([
        pl.col('asset_isrc').drop_nulls().first(),pl.col('track_id').drop_nulls().first(),
        pl.col('track_statement_style').first().alias('track_title'),pl.col('artist_statement_style').first().alias('artist_statement'),
        pl.col('transaction_month').min().alias('first_transaction_month'),pl.col('transaction_month').max().alias('last_transaction_month'),
        pl.col('amount_usd').sum(),pl.col('units').sum(),pl.len().alias('song_level_rows'),
        join('track_statement_style').alias('title_variants'),join('artist_statement_style').alias('artist_variants'),
        join('asset_isrc').alias('isrcs'),join('product_upc').alias('upcs'),join('track_id').alias('track_ids'),
        join('content_type').alias('content_types'),pl.col('product_upc').drop_nulls().first().alias('primary_upc'),
    ]).with_columns([
        pl.lit('wml').alias('sources'),pl.lit('91230').alias('accounts'),pl.lit(1).alias('source_count'),pl.lit(1).alias('account_count'),
        pl.lit('royalty_detail').alias('source_sheets'),pl.lit(None,dtype=pl.String).alias('external_release_date'),
        pl.lit('Warner Music Latina').alias('external_label'),pl.lit('Warner Music Latina').alias('label_normalized'),
        pl.lit(None,dtype=pl.String).alias('video_ids'),pl.lit([],dtype=pl.List(pl.String)).alias('video_isrcs'),
        pl.concat_list('catalog_key').alias('catalog_aliases'),pl.lit('[]').alias('video_relationships_json'),
    ])
    cat.sink_parquet(out/'catalog_master.parquet',compression='zstd')
    pl.DataFrame(schema={'catalog_key':pl.String,'active':pl.Boolean,'include_in_reports':pl.Boolean,
       'catalog_business_status':pl.String,'status_notes':pl.String,'label_normalized_override':pl.String,'updated_at':pl.String}).write_parquet(out/'catalog_status.parquet')
    lf.group_by(['source','account','artist_statement_style','statement_period']).agg([
        pl.col('amount_usd').sum().alias('total'),pl.lit(False).alias('has_share_in_out')
    ]).rename({'artist_statement_style':'artist'}).with_columns(pl.lit('artist_total').alias('row_type'),pl.lit(None,dtype=pl.Float64).alias('total_eur')).sink_parquet(out/'statement_summary_all_sources.parquet')
    base=lf.with_columns([
        pl.col('artist_statement_style').alias('artist'),pl.col('track_statement_style').alias('title'),
        pl.concat_str(['artist_statement_style','track_statement_style','asset_isrc'],separator=' ',ignore_nulls=True).str.to_lowercase().alias('search_text'),
    ])
    base.group_by(['statement_period','source','account','artist','title','search_text']).agg([
        pl.col('amount_usd').sum().alias('total_usd'),pl.lit(0.0).alias('total_eur'),pl.lit(False).alias('has_share_in_out'),pl.len().alias('raw_rows')
    ]).sink_parquet(out/'digital_income_statement_summary.parquet')
    base.with_columns([
        pl.col('asset_isrc').alias('isrc'),pl.col('product_upc').alias('upc'),pl.col('dsp_normalized').alias('dsp'),
        pl.lit('Warner Music Latina').alias('label'),
    ]).group_by(['statement_period','transaction_month','source','account','source_sheet','artist','title','isrc','upc',
        'dsp','territory','sale_type','monetization_normalized','content_origin_normalized','classification_status','label','search_text']).agg([
        pl.col('amount_usd').sum(),pl.col('units').sum(),pl.len().alias('raw_rows')
    ]).sink_parquet(out/'royalties_dashboard_summary.parquet',compression='zstd')

def ingest(input_root: Path,output_root: Path) -> dict:
    files,ignored=discover(input_root)
    evidence=[{'file':p.name,'sha256':sha256(p)} for p in sorted(input_root.glob('Statement_91355_*.txt'))]
    fingerprint=input_fingerprint(files,evidence)
    release='wml-'+fingerprint[:24]
    output=output_root/'releases'/release
    manifest_file=output/'wml_manifest.json'
    if manifest_file.exists() and all((output/name).exists() for name in WML_FILES):
        manifest=json.loads(manifest_file.read_text(encoding='utf-8'));manifest['reused']=True
        write_json(output_root/'active_release.json',{'release_id':release,'path':str(output),'fingerprint':fingerprint})
        return manifest
    output.mkdir(parents=True,exist_ok=True)
    parts=[];summaries=[]
    for file in files:
        cache=output_root/'parts'/INGEST_VERSION/file['sha256']
        part=cache/'detail.parquet';summary_file=cache/'summary.json'
        if not part.exists() or not summary_file.exists():
            cache.mkdir(parents=True,exist_ok=True)
            frame,summary=standardize(Path(file['path']),file['sha256'])
            frame.write_parquet(part,compression='zstd');write_json(summary_file,summary)
        summary=json.loads(summary_file.read_text(encoding='utf-8'))
        summaries.append(summary);parts.append(part)
        print(f"Validated {file['file']}: {summary['rows']} rows",flush=True)
    detail=output/'standardized_raw_all_sources.parquet'
    pl.concat([pl.scan_parquet(p) for p in parts],how='diagonal_relaxed').sink_parquet(detail,compression='zstd')
    write_summaries(detail,output)
    build_references(detail,input_root,output/'wml_isrc_references.parquet')
    manifest={'scope':'wml','account':'91230','enabled_by_default':False,'release_id':release,'fingerprint':fingerprint,
        'ingest_version':INGEST_VERSION,'reference_version':REFERENCE_VERSION,'created_at':datetime.now(timezone.utc).isoformat(),
        'files':files,'ignored':ignored,'evidence_only':evidence,'semesters':summaries,
        'rows':sum(s['rows'] for s in summaries),'amount_usd':sum(s['amount_usd'] for s in summaries),
        'warner_royalty_usd':sum(s['warner_royalty_usd'] for s in summaries),'reused':False}
    for name in WML_FILES:
        if not (output/name).exists():raise RuntimeError('El paquete WML está incompleto: '+name)
    write_json(manifest_file,manifest)
    write_json(output_root/'active_release.json',{'release_id':release,'path':str(output),'fingerprint':fingerprint})
    return manifest

def input_fingerprint(files: list[dict],evidence: list[dict]) -> str:
    return hashlib.sha256(json.dumps({'version':INGEST_VERSION,'references':REFERENCE_VERSION,
        'files':[(x['file'],x['sha256']) for x in sorted(files,key=lambda x:x['file'])],
        'evidence':[{'file':x['file'],'sha256':x['sha256']} for x in sorted(evidence,key=lambda x:x['file'])]},sort_keys=True).encode()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,default=ROOT/'input_raw/wml');p.add_argument('--output',type=Path,default=DEFAULT_ROOT)
    args=p.parse_args();result=ingest(args.input,args.output)
    print(json.dumps({k:result[k] for k in ['release_id','rows','amount_usd','warner_royalty_usd','reused']},indent=2))

if __name__=='__main__':main()
