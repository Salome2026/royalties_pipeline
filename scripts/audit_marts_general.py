from pathlib import Path

import polars as pl


BASE = Path(r"C:\royalties_pipeline")
MARTS = BASE / "warehouse" / "marts"
REPORT_PATH = BASE / "reports" / "reporte_ingresos_digitales_por_mes_de_statement_marts.xlsx"


SOURCES = [
    "dashgo",
    "fuga",
    "onerpm",
    "orchard",
    "soundon",
]


def print_df(df: pl.DataFrame):
    pl.Config.set_tbl_formatting("ASCII_FULL")
    print(df)


def amount_col_expr(schema: dict[str, pl.DataType]) -> pl.Expr:
    cols = []

    for name in ["amount_usd", "net_amount_usd", "net_amount"]:
        if name in schema:
            cols.append(pl.col(name).cast(pl.Float64, strict=False))

    if not cols:
        return pl.lit(None).cast(pl.Float64)

    return pl.coalesce(cols)


def optional_col(schema: dict[str, pl.DataType], name: str, dtype=pl.Utf8) -> pl.Expr:
    if name in schema:
        return pl.col(name).cast(dtype, strict=False)
    return pl.lit(None).cast(dtype)


def summarize_parquet(path: Path, amount_name: str = "amount_usd") -> dict:
    if not path.exists():
        return {
            "file": path.name,
            "exists": False,
            "rows": 0,
            amount_name: None,
        }

    lf = pl.scan_parquet(path)
    schema = lf.collect_schema()
    amount = amount_col_expr(schema)

    result = (
        lf
        .select([
            pl.len().alias("rows"),
            amount.sum().alias(amount_name),
        ])
        .collect()
        .to_dicts()[0]
    )

    return {
        "file": path.name,
        "exists": True,
        **result,
    }


def standardized_summary() -> pl.DataFrame:
    rows = []

    for source in SOURCES:
        path = MARTS / f"standardized_raw_{source}.parquet"
        rows.append({
            "source": source,
            **summarize_parquet(path, "standardized_usd"),
        })

    return pl.DataFrame(rows)


def song_summary() -> pl.DataFrame:
    rows = []

    for source in SOURCES:
        path = MARTS / f"song_level_{source}.parquet"
        rows.append({
            "source": source,
            **summarize_parquet(path, "song_usd"),
        })

    return pl.DataFrame(rows)


def compare_standardized_vs_song() -> pl.DataFrame:
    std = standardized_summary().select([
        "source",
        pl.col("rows").alias("standardized_rows"),
        "standardized_usd",
    ])
    song = song_summary().select([
        "source",
        pl.col("rows").alias("song_rows"),
        "song_usd",
    ])

    compare = (
        std
        .join(song, on="source", how="full", coalesce=True)
        .with_columns((pl.col("song_usd") - pl.col("standardized_usd")).alias("song_minus_standardized"))
    )

    return compare


def statement_view_summary() -> pl.DataFrame:
    rows = []

    for source in SOURCES:
        path = MARTS / f"standardized_raw_{source}.parquet"
        if not path.exists():
            continue

        lf = pl.scan_parquet(path)
        schema = lf.collect_schema()
        amount = amount_col_expr(schema)

        base = lf.with_columns([
            amount.alias("_amount"),
            optional_col(schema, "source").alias("_source"),
            optional_col(schema, "account").alias("_account"),
            optional_col(schema, "source_sheet").alias("_source_sheet"),
            optional_col(schema, "include_in_statement_view", pl.Boolean).alias("_include_in_statement_view"),
        ])

        if source == "soundon":
            base = base.filter(pl.col("_source_sheet") == "my_royalty")
        elif "include_in_statement_view" in schema:
            base = base.filter(pl.col("_include_in_statement_view") == True)

        if source == "fuga":
            base = base.with_columns((pl.col("_amount") * 0.977832).alias("_statement_amount"))
        else:
            base = base.with_columns(pl.col("_amount").alias("_statement_amount"))

        summary = (
            base
            .group_by(["_source", "_account"])
            .agg([
                pl.sum("_statement_amount").alias("statement_view_usd"),
                pl.len().alias("statement_view_rows"),
            ])
            .rename({"_source": "source", "_account": "account"})
            .collect()
        )

        rows.extend(summary.to_dicts())

    return pl.DataFrame(rows).sort(["source", "account"])


def view_summary() -> pl.DataFrame:
    rows = []

    for source in SOURCES:
        path = MARTS / f"standardized_raw_{source}.parquet"
        if not path.exists():
            continue

        lf = pl.scan_parquet(path)
        schema = lf.collect_schema()

        if "include_in_cash_view" not in schema and "include_in_catalog_view" not in schema:
            continue

        amount = amount_col_expr(schema)
        base = lf.with_columns(amount.alias("_amount"))

        exprs = []
        for view in ["include_in_cash_view", "include_in_catalog_view", "include_in_statement_view"]:
            if view in schema:
                exprs.extend([
                    pl.when(pl.col(view) == True)
                    .then(pl.col("_amount"))
                    .otherwise(0.0)
                    .sum()
                    .alias(view.replace("include_in_", "").replace("_view", "_usd")),
                    pl.when(pl.col(view) == True)
                    .then(1)
                    .otherwise(0)
                    .sum()
                    .alias(view.replace("include_in_", "").replace("_view", "_rows")),
                ])

        summary = base.select(exprs).collect().to_dicts()[0]
        rows.append({"source": source, **summary})

    return pl.DataFrame(rows)


def known_deltas() -> pl.DataFrame:
    rows = []

    onerpm = MARTS / "standardized_raw_onerpm.parquet"
    if onerpm.exists():
        df = pl.scan_parquet(onerpm)

        mawz_2024_02 = (
            df
            .filter(
                (pl.col("account") == "mawzrecords")
                & (pl.col("source_sheet") == "Masters")
                & (pl.col("statement_period") == "2024-02")
            )
            .select([
                pl.len().alias("rows"),
                pl.sum("amount_usd").alias("amount_usd"),
                pl.sum("net_amount").alias("net_amount"),
            ])
            .collect()
            .to_dicts()[0]
        )

        rows.append({
            "delta": "ONErpm MAWZ 2024-02 Masters recovered via RUR->RUB",
            **mawz_2024_02,
        })

        henry = (
            df
            .filter(pl.col("account") == "henry_remix")
            .select([
                pl.len().alias("rows"),
                pl.sum("amount_usd").alias("amount_usd"),
                pl.sum("net_amount").alias("net_amount"),
                (pl.sum("amount_usd") - pl.sum("net_amount")).alias("amount_minus_net"),
            ])
            .collect()
            .to_dicts()[0]
        )

        rows.append({
            "delta": "ONErpm Henry uses FX in marts; legacy report used net_amount",
            **henry,
        })

    return pl.DataFrame(rows)


def main():
    print("Audit general de marts")

    print("\n=== STANDARDIZED ===")
    print_df(standardized_summary())

    print("\n=== SONG LEVEL ===")
    print_df(song_summary())

    print("\n=== STANDARDIZED VS SONG ===")
    print_df(compare_standardized_vs_song())

    print("\n=== STATEMENT VIEW BY SOURCE/ACCOUNT ===")
    print_df(statement_view_summary())

    print("\n=== VIEW TOTALS ===")
    views = view_summary()
    if views.height > 0:
        print_df(views)
    else:
        print("No view flags found.")

    print("\n=== KNOWN DELTAS / NOTES ===")
    deltas = known_deltas()
    if deltas.height > 0:
        print_df(deltas)
    else:
        print("No known deltas registered.")

    print("\nNota: SoundOn Summary no se carga al standardized principal; audit_soundon lo lee desde input_raw.")

    print("\nReporte marts esperado:")
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
