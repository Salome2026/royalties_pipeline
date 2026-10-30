"""Independent checks against native source fields, before a BigQuery load."""
from pathlib import Path
import polars as pl


def validate_detail_source(source: Path, prepared: Path) -> dict:
    raw = pl.scan_parquet(source)
    cols = set(raw.collect_schema().names())

    def text(name):
        return pl.col(name).cast(pl.String, strict=False).str.strip_chars() if name in cols else pl.lit(None, dtype=pl.String)

    def num(*names):
        return pl.coalesce([pl.col(n).cast(pl.Float64, strict=False) for n in names if n in cols]) if any(n in cols for n in names) else pl.lit(None, dtype=pl.Float64)

    def valid(name):
        value = text(name)
        return pl.when(value.str.contains(r"^[A-Za-z0-9_-]{11}$")).then(value)

    src = text("source")
    asset = num("Asset Quantity", "asset_quantity_num")
    product = num("Product Quantity", "product_quantity_num")
    fuga_units = pl.when(pl.coalesce([text("Asset/Product"), text("asset_product_type")]) == "Product").then(product).otherwise(asset)
    units = (
        pl.when(src == "fuga").then(fuga_units)
        .when(src == "onerpm").then(num("Quantity"))
        .when(src == "dashgo").then(num("Units"))
        .when(src == "orchard").then(num("QUANTITY"))
        .when(src == "soundon").then(num("Units of Sold"))
        .when(src.is_in(["ada", "wml"])).then(num("Sales", "Sale Units"))
    )
    units = pl.when(src == "fuga").then(pl.coalesce([units, num("units", "streams")])).otherwise(
        pl.coalesce([num("units", "streams"), units])).fill_null(0.0)
    reference = pl.coalesce([text("Product Reference"), text("product_reference")]).str.extract(r"^YT-V-([A-Za-z0-9_-]{11})$", 1)
    native_video = (
        pl.when(src == "fuga").then(pl.coalesce([valid("DSP Container ID"), reference]))
        .when(src == "orchard").then(valid("YOUTUBE VIDEO ID"))
        .when(src == "dashgo").then(valid("VideoId"))
        .when(src == "onerpm").then(pl.coalesce([valid("Video ID"), valid("VideoId")]))
    )
    video = pl.coalesce([native_video, valid("video_id")])
    expected = raw.select(
        text("source").fill_null("").alias("source"), text("account").fill_null("").alias("account"),
        text("statement_period").str.slice(0, 7).fill_null("").alias("period"),
        video.fill_null("").alias("video"), num("amount_usd").fill_null(0).alias("amount"), units.alias("units"),
    )
    actual = pl.scan_parquet(prepared).select(
        pl.col("source").fill_null(""), pl.col("account").fill_null(""),
        pl.col("statement_month").cast(pl.String).str.slice(0, 7).fill_null("").alias("period"),
        pl.col("video_id").fill_null("").alias("video"), pl.col("amount_usd").fill_null(0).alias("amount"),
        pl.col("units").fill_null(0),
    )
    keys = ["source", "account", "period", "video"]
    def aggregate(frame):
        return frame.group_by(keys).agg(pl.len().alias("count"), pl.sum("amount"), pl.sum("units")).collect(engine="streaming")
    a, b = aggregate(expected), aggregate(actual)
    diff = a.join(b, on=keys, how="full", coalesce=True, suffix="_actual").filter(
        (pl.col("count").fill_null(-1) != pl.col("count_actual").fill_null(-1))
        | ((pl.col("amount") - pl.col("amount_actual")).abs().fill_null(float("inf")) > 0.01)
        | ((pl.col("units") - pl.col("units_actual")).abs().fill_null(float("inf")) > 0.0001)
    )
    if diff.height:
        raise ValueError("La carga BigQuery pierde identidad o cantidades de la fuente: " + str(diff.head(5).to_dicts()))
    return {"groups": a.height, "rows": int(a["count"].sum()), "video_groups": a.filter(pl.col("video") != "").height,
            "amount_usd": float(a["amount"].sum()), "units": float(a["units"].sum())}
