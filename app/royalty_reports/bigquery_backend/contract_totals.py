"""Exact aggregation of eligible contractual movements."""

import math
from fractions import Fraction

from .transport import arrow_batches


class BinaryTotal:
    __slots__=('integer','shift')
    def __init__(self):self.integer=0;self.shift=0
    def add(self,value):
        value=float(value)
        if not math.isfinite(value):raise ValueError('La base contractual contiene un valor no finito.')
        numerator,denominator=value.as_integer_ratio();power=denominator.bit_length()-1
        if power>self.shift:self.integer<<=power-self.shift;self.shift=power
        self.integer+=numerator<<(self.shift-power)
    def value(self):return float(Fraction(self.integer,1<<self.shift))


def group_columns(version):
    fields=['isrc','upc','artist','title','source','account']
    if version>=2:fields+=['source_sheet','search_text','normalized_search']
    if version>=3:fields+=['channel_id']
    return fields+['statement_month']


def aggregate(rows, version):
    fields=group_columns(version);metrics=['amount_usd','units']+(['gross_amount_usd'] if version>=2 else [])
    groups = {}
    for row in rows:
        key=tuple(row[k] for k in fields)
        if key not in groups:groups[key]=[0,*[BinaryTotal() for _ in metrics]]
        target=groups[key];target[0]+=int(row['raw_rows'])
        for i,name in enumerate(metrics,1):
            target[i].add(row[name])
    result=[]
    for key,totals in groups.items():
        item=dict(zip(fields,key,strict=True));item['raw_rows']=totals[0]
        item.update({name:value.value() for name,value in zip(metrics,totals[1:],strict=True)})
        result.append(item)
    order=['statement_month','isrc','upc','title','artist','source','account',*fields]
    result.sort(key=lambda row:tuple((row[k] is not None,str(row[k] or '')) for k in order))
    return result

def read_exact_groups(result, version, credentials):
    seen = 0

    def rows():
        nonlocal seen
        for batch in arrow_batches(result, credentials):
            seen += batch.num_rows
            yield from batch.to_pylist()

    grouped = aggregate(rows(), version)
    if seen != result.total_rows:
        raise ValueError("La lectura contractual de BigQuery quedó incompleta.")
    return grouped
