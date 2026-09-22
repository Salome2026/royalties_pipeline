from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl


BASE = Path(__file__).resolve().parents[2]
MARTS = BASE / "warehouse" / "marts"
REGISTRY = BASE / "warehouse" / "registry"
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from scripts.lib.distributor_policy_store import load_distributor_policy_document


SOURCE = "ada"
ACCOUNT = "indyana_records"
RAW_ACCOUNT = "99500"
INITIAL_STATEMENT_PERIOD = "2026-07"
INITIAL_NET_USD = 7161.66557022
TOLERANCE = 1e-8
VALENTINO_TITLES = {
    "BK4DA2659049": ("DÓNDE ESTÁS CORAZÓN", "A10302B0014196415A"),
    "BK4DA2659050": ("SI UN DÍA ESTÁS SOLA", "A10302B00141964168"),
    "BK4DA2659051": ("TU FOTO", "A10302B00141964176"),
    "BK4DA2659052": ("HOY", "A10302B00141964184"),
    "BK4DA2659053": ("ME VOY", "A10302B00141964192"),
}


def account_total(
    path: Path,
    amount_column: str,
    *,
    statement_period: str | None = INITIAL_STATEMENT_PERIOD,
) -> tuple[int, float]:
    schema = pl.read_parquet_schema(path)
    frame = pl.scan_parquet(path).filter(
        (pl.col("source") == SOURCE)
        & (pl.col("account") == ACCOUNT)
    )
    if statement_period is not None and "statement_period" in schema:
        frame = frame.filter(pl.col("statement_period") == statement_period)
    result = frame.select(
        pl.len().alias("rows"),
        pl.col(amount_column).cast(pl.Float64, strict=False).sum().alias("amount_usd"),
    ).collect().to_dicts()[0]
    return int(result["rows"]), float(result["amount_usd"] or 0.0)


def assert_close(actual: float, expected: float, label: str) -> None:
    if abs(actual - expected) > TOLERANCE:
        raise AssertionError(f"{label}: {actual:.12f} != {expected:.12f}")


def main() -> None:
    policy = load_distributor_policy_document()
    entry = next(
        (
            item
            for item in policy.get("entries", [])
            if item.get("source") == SOURCE and item.get("account") == ACCOUNT
        ),
        None,
    )
    if entry is None:
        raise AssertionError("Cloud SQL no contiene la politica ADA / Indyana Records.")
    if not all(entry.get(field) for field in [
        "catalog_view_enabled",
        "statement_view_enabled",
        "cash_view_enabled",
    ]):
        raise AssertionError(f"La politica ADA / Indyana Records esta incompleta: {entry}")

    dictionary = json.loads(
        (REGISTRY / "statement_source_dictionary.json").read_text(encoding="utf-8")
    )
    dictionary_entry = next(
        (
            item
            for item in dictionary.get("entries", [])
            if item.get("source") == SOURCE and item.get("account") == ACCOUNT
        ),
        None,
    )
    if dictionary_entry is None:
        raise AssertionError("Falta ADA / Indyana Records en statement_source_dictionary.json.")

    ada_path = MARTS / "standardized_raw_ada.parquet"
    raw_accounts = set(
        pl.scan_parquet(ada_path)
        .filter((pl.col("source") == SOURCE) & (pl.col("account") == ACCOUNT))
        .select(pl.col("Account").cast(pl.Utf8).unique())
        .collect()
        .get_column("Account")
        .to_list()
    )
    if raw_accounts != {RAW_ACCOUNT}:
        raise AssertionError(
            f"La identidad cruda ADA no coincide: {sorted(raw_accounts)} != {[RAW_ACCOUNT]}"
        )

    title_semantic_violations = (
        pl.scan_parquet(ada_path)
        .filter(
            pl.col("track_statement_style").fill_null("").str.strip_chars()
            != pl.col("Product Title").fill_null("").str.strip_chars()
        )
        .select(pl.len())
        .collect()
        .item()
    )
    release_semantic_violations = (
        pl.scan_parquet(ada_path)
        .filter(
            pl.col("release_statement_style").fill_null("").str.strip_chars()
            != pl.col("Project Title").fill_null("").str.strip_chars()
        )
        .select(pl.len())
        .collect()
        .item()
    )
    if title_semantic_violations or release_semantic_violations:
        raise AssertionError(
            "ADA no conserva Product Title como tema y Project Title como lanzamiento: "
            f"title={title_semantic_violations}, release={release_semantic_violations}"
        )

    song_ada = pl.read_parquet(MARTS / "song_level_ada.parquet")
    required_song_columns = {
        "asset_title_statement",
        "release_statement_style",
        "gpid",
        "catalog_number",
        "source_asset_id",
        "track_id",
    }
    missing_song_columns = sorted(required_song_columns - set(song_ada.columns))
    if missing_song_columns:
        raise AssertionError(f"song_level_ada no conserva campos ADA: {missing_song_columns}")

    expected_isrcs = set(VALENTINO_TITLES)
    valentino_song = (
        song_ada
        .filter(pl.col("asset_isrc").is_in(sorted(expected_isrcs)))
        .select(["asset_isrc", "track_statement_style", "release_statement_style", "source_asset_id"])
        .unique()
    )
    if set(valentino_song.get_column("asset_isrc").to_list()) != expected_isrcs:
        raise AssertionError("Faltan pistas de Valentino Merlo en song_level_ada.")
    for row in valentino_song.to_dicts():
        expected_title, expected_source_id = VALENTINO_TITLES[row["asset_isrc"]]
        if row["track_statement_style"] != expected_title:
            raise AssertionError(f"Titulo ADA incorrecto: {row}")
        if row["source_asset_id"] != expected_source_id:
            raise AssertionError(f"GPID ADA incorrecto: {row}")
        if "VALENTINO MERLO" not in str(row["release_statement_style"] or "").upper():
            raise AssertionError(f"Proyecto ADA incorrecto: {row}")

    all_period_net_usd = account_total(
        ada_path,
        "amount_usd",
        statement_period=None,
    )[1]
    checks = [
        ("standardized_raw_ada.parquet", "amount_usd", INITIAL_NET_USD, INITIAL_STATEMENT_PERIOD),
        ("song_level_ada.parquet", "amount_usd", all_period_net_usd, None),
        ("standardized_raw_all_sources.parquet", "amount_usd", INITIAL_NET_USD, INITIAL_STATEMENT_PERIOD),
        ("song_level_all_sources.parquet", "amount_usd", all_period_net_usd, None),
        ("digital_income_statement_summary.parquet", "total_usd", INITIAL_NET_USD, INITIAL_STATEMENT_PERIOD),
        ("royalties_dashboard_summary.parquet", "amount_usd", INITIAL_NET_USD, INITIAL_STATEMENT_PERIOD),
    ]
    results = {}
    for filename, amount_column, expected_amount, statement_period in checks:
        rows, amount_usd = account_total(
            MARTS / filename,
            amount_column,
            statement_period=statement_period,
        )
        if rows <= 0:
            raise AssertionError(f"{filename} no contiene ADA / Indyana Records.")
        assert_close(amount_usd, expected_amount, filename)
        results[filename] = {"rows": rows, "amount_usd": amount_usd}

    statement_rows, statement_amount = account_total(
        MARTS / "statement_summary_all_sources.parquet",
        "total",
    )
    expected_statement_amount = round(
        pl.scan_parquet(MARTS / "standardized_raw_all_sources.parquet")
        .filter(
            (pl.col("source") == SOURCE)
            & (pl.col("account") == ACCOUNT)
            & (pl.col("statement_period") == INITIAL_STATEMENT_PERIOD)
        )
        .with_columns(
            pl.when(
                pl.col("artist_statement_style").is_null()
                | (pl.col("artist_statement_style").str.strip_chars() == "")
            )
            .then(pl.lit("SIN ARTISTA"))
            .otherwise(pl.col("artist_statement_style").str.strip_chars())
            .alias("artist")
        )
        .group_by("artist")
        .agg(pl.sum("amount_usd").round(2).alias("artist_total"))
        .select(pl.sum("artist_total"))
        .collect()
        .item(),
        2,
    )
    assert_close(statement_amount, expected_statement_amount, "statement_summary_all_sources.parquet")
    results["statement_summary_all_sources.parquet"] = {
        "rows": statement_rows,
        "amount_usd": statement_amount,
        "rounding_contract": "artist totals rounded to cents",
    }

    catalog_matches = (
        pl.scan_parquet(MARTS / "catalog_master.parquet")
        .filter(pl.col("accounts").fill_null("").str.contains(ACCOUNT, literal=True))
        .select(pl.len().alias("rows"))
        .collect()
        .item()
    )
    if catalog_matches <= 0:
        raise AssertionError("El catalogo no contiene obras observadas en ADA / Indyana Records.")

    catalog = pl.read_parquet(MARTS / "catalog_master.parquet")
    valentino_catalog = (
        catalog
        .filter(pl.col("asset_isrc").is_in(sorted(expected_isrcs)))
        .select(["asset_isrc", "track_title", "track_id"])
    )
    if valentino_catalog.height != len(expected_isrcs):
        raise AssertionError("El catalogo no conserva las cinco pistas de Valentino Merlo.")
    for row in valentino_catalog.to_dicts():
        expected_title, expected_source_id = VALENTINO_TITLES[row["asset_isrc"]]
        if row["track_title"] != expected_title or row["track_id"] != expected_source_id:
            raise AssertionError(f"Catalogo ADA incorrecto: {row}")

    print({
        "ok": True,
        "policy_version": policy.get("policy_version"),
        "source": SOURCE,
        "account": ACCOUNT,
        "raw_account": RAW_ACCOUNT,
        "statement_period": INITIAL_STATEMENT_PERIOD,
        "net_usd": INITIAL_NET_USD,
        "catalog_rows_related": catalog_matches,
        "checks": results,
    })


if __name__ == "__main__":
    main()
