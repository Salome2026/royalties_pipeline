"""Documented evidence only. These percentages never enter amount calculations."""
from __future__ import annotations
import hashlib
import re
import unicodedata
from pathlib import Path
import polars as pl

REFERENCE_VERSION = 'wml-references-v1'
PARTICIPATIONS = (
    ('MALA MIA','Duki','91381',10.0,'deduced','Seis cargos consecutivos desde 2023-H2 cierran a centavos; incluye 1/14 del álbum MAWZ. Vigencia anterior y alcance por versión pendientes.'),
    ('FLEXIN','Bizarrap','91621',4.0,'deduced','Cuatro cargos desde 2024-H2 coinciden con el modelo del tema. Alcance histórico y por versión pendientes.'),
    ('KILLER BOMBON','Los Palmeras','91709',10.0,'deduced','Coinciden el cargo acumulado inicial de 2025-H1 y los dos posteriores. Deducción para el conjunto del tema.'),
    ('DEJAME TRANKI','Khea / UMG','91889',12.5,'deduced','Coinciden el cargo acumulado inicial de 2025-H2 y el siguiente. Deducción para el conjunto del tema.'),
    ('BIPOLAR','Lil Mosey / UMG','91890',8.333,'deduced','8,333% es compatible con los dos cargos; no es una lectura de su TXT propio ni un tercio exacto de la bolsa del 25%.'),
)
LDE = [('Tiago PZK','91910'),('Emilia','91911'),('FMK','91912'),('BigOne','91913'),('Rusherking','91914'),('Duki','91915'),('María Becerra','91916')]

def normalized(value: str) -> str:
    s=''.join(c for c in unicodedata.normalize('NFKD',value) if not unicodedata.combining(c))
    return re.sub('[^A-Z0-9]+',' ',s.upper()).strip()

def build_references(detail: Path, input_root: Path, target: Path) -> None:
    columns=['asset_isrc','track_statement_style','product_type','statement_period','wml_royalty_rate_pct','statement_file_name']
    groups=pl.scan_parquet(detail).select(columns).unique().collect().to_dicts()
    refs={}
    def add(isrc,kind,person,rate,status,scope,product,period,file,notes,account):
        if not isrc:return
        key=hashlib.sha256(f'{isrc}|{kind}|{person}|{rate}|{product}|{scope}'.encode()).hexdigest()[:24]
        row=refs.setdefault(key,{'reference_id':key,'scope':'wml','source':'wml','account':'91230','isrc':isrc,
            'reference_type':kind,'participant':person,'percent':rate,'basis':'contractual_base_100',
            'evidence_status':status,'reference_scope':scope,'product_type':product,
            'effective_from':None,'effective_until':None,'applies_automatically':False,
            'evidence_account':account,'statement_periods':set(),'source_files':set(),'notes':notes})
        row['statement_periods'].add(period);row['source_files'].add(file)
    for r in groups:
        title=normalized(r['track_statement_style'] or '')
        add(r['asset_isrc'],'account_rate','Contrato 91230',r['wml_royalty_rate_pct'],'informed','exact_isrc_and_usage',r['product_type'],r['statement_period'],r['statement_file_name'],
            'Tasa informada por línea. El período observado no establece la vigencia contractual. Sale de la base al 100%; puede contener participaciones.','91230')
        for prefix,person,account,rate,status,note in PARTICIPATIONS:
            if title.startswith(prefix):
                add(r['asset_isrc'],'participation',person,rate,status,'song_family_pending_asset_confirmation','group_of_versions',r['statement_period'],r['statement_file_name'],note,account)
        if title.startswith('LOS DEL ESPACIO'):
            for person,account in LDE:
                add(r['asset_isrc'],'participation',person,6.0,'hypothesis','song_family_pending_asset_confirmation','group_of_versions',r['statement_period'],r['statement_file_name'],
                    'Hipótesis de ocho partes iguales del 48%. No cierra exactamente los cargos; versiones, pagos y períodos sin confirmar. No se extrapola al 25% ni a sincronizaciones.',account)
    # The participant account supplies documentary evidence, never extra income.
    for path in sorted(input_root.glob('Statement_91355_*.txt')):
        frame=pl.read_csv(path,separator='\t',quote_char=None,infer_schema=False,encoding='utf8',null_values='')
        if 'Revenue Rate' not in frame.columns:frame=frame.with_columns(pl.lit(None,dtype=pl.String).alias('Revenue Rate'))
        for r in frame.select(['Account','ISRC','Product Type','End Period','Royalty Rate','Revenue Rate']).unique().to_dicts():
            if r['Account']!='91355':raise ValueError(f'Cuenta inesperada en evidencia: {path.name}')
            rate=float(r['Royalty Rate'] or r['Revenue Rate'])
            add(r['ISRC'],'participation','Tiago PZK',rate,'informed','exact_isrc_and_usage',r['Product Type'],r['End Period'],path.name,
                'Porcentaje escrito en el TXT propio de la 91355. Esa cuenta se usa como evidencia, no se suma al ingreso WML.','91355')
    rows=[]
    for r in refs.values():
        r['statement_periods']=sorted(r['statement_periods']);r['source_files']=sorted(r['source_files'])
        rows.append(r)
    pl.DataFrame(rows,infer_schema_length=None).with_columns(
        pl.col('effective_from').cast(pl.String),pl.col('effective_until').cast(pl.String)
    ).write_parquet(target,compression='zstd')
