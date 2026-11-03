"""Identity and statement dates for editing contracts, without calculating income."""
from functools import lru_cache
from pathlib import Path
import polars as pl

@lru_cache(maxsize=4)
def statement_dates(path: str, modified: int, wml: bool = False) -> pl.DataFrame:
    del modified  # cache invalidation uses the immutable mart path and mtime
    scan = pl.scan_parquet(path)
    return scan.select(pl.col("isrc").alias("asset_isrc"), "statement_period").filter(
        pl.col("asset_isrc").is_not_null() & pl.col("statement_period").is_not_null()
    ).group_by("asset_isrc").agg(
        pl.col("statement_period").min().alias("_contract_first_statement_month"),
        pl.col("statement_period").max().alias("_contract_last_statement_month"),
    ).collect(engine="streaming")

def metadata_catalog(catalog: pl.DataFrame, dates: pl.DataFrame) -> pl.DataFrame:
    valid = catalog.filter(pl.col("asset_isrc").fill_null("").str.contains(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$"))
    if "amount_usd" in valid.columns:
        valid = valid.sort(["amount_usd", "asset_isrc"], descending=[True, False])
    valid = valid.unique(subset=["asset_isrc"], keep="first", maintain_order=True)
    return valid.drop([c for c in dates.columns if c != "asset_isrc" and c in valid.columns]).join(
        dates, on="asset_isrc", how="left").with_columns(
        *[pl.lit(0.0).alias(c) for c in ["amount_usd", "isrc_amount_usd", "associated_amount_usd"]])
