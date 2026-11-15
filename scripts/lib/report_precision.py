"""Exact accumulation and deterministic metadata selection for royalty reports."""

import math
from fractions import Fraction

import polars as pl


def exact_sum(values):
    # Every finite binary64 is an integer / power-of-two. Accumulate these exact
    # integers, then convert once to binary64. This is independent of row order.
    total=0;shift=0;count=0
    for value in values:
        if value is None:continue
        value=float(value)
        if not math.isfinite(value):
            raise ValueError('Non-finite values require an explicit shared policy; no silent replacement')
        numerator,denominator=value.as_integer_ratio()
        exponent=denominator.bit_length()-1
        if exponent>shift:total<<=exponent-shift;shift=exponent
        total+=numerator<<(shift-exponent);count+=1
    return float(Fraction(total,1<<shift))


def stable_sum(column):
    return pl.col(column).map_batches(lambda s:exact_sum(s.drop_nulls().to_list()),return_dtype=pl.Float64,returns_scalar=True)


def stable_series_sum(series,min_count=0):
    values=series.drop_nulls().to_list() if isinstance(series,pl.Series) else series.dropna().tolist()
    return exact_sum(values) if len(values)>=min_count else float('nan')


def stable_pick(column):
    # Preserve largest-absolute-income priority. Only an exact tie selects the
    # smallest original text; no separator, code, title or credit is rewritten.
    return pl.col(column).sort_by([pl.col('amount_usd').abs(),pl.col(column)],descending=[True,False],nulls_last=True).drop_nulls().first()
