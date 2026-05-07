from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import polars as pl


BASE = Path(r"C:\royalties_pipeline")
HISTORICAL_CSV = BASE / "reports" / "booking" / "booking_shows_report_base.csv"
STANDARDIZED_PATH = BASE / "warehouse" / "booking" / "standardized" / "standardized_booking_movements.parquet"
LIVE_DB = BASE / "warehouse" / "booking" / "live" / "booking_live.sqlite"
BACKUP_DIR = BASE / "warehouse" / "booking" / "live" / "backups"


def normalize_text(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def category_from_concept(concept: object) -> str:
    text = normalize_text(concept)
    if "tour" in text and "manager" in text:
        return "tour_manager"
    if "comision" in text or "comisión" in text:
        return "comision"
    if "film" in text or "video" in text:
        return "produccion"
    if "recupero" in text:
        return "recupero"
    if "viatico" in text or "viático" in text:
        return "viaticos"
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_") or "general"


def rebuild_historical_base() -> None:
    import subprocess
    import sys

    subprocess.run(
        [sys.executable, str(BASE / "scripts" / "build_booking_shows_report.py")],
        cwd=str(BASE),
        check=True,
    )


def ensure_live_db() -> None:
    if not LIVE_DB.exists():
        raise FileNotFoundError(f"No existe la base viva: {LIVE_DB}")


def backup_live_db() -> Path:
    ensure_live_db()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"booking_live_before_historical_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite"
    shutil.copy2(LIVE_DB, backup_path)
    return backup_path


def existing_live_keys(conn: sqlite3.Connection) -> set[tuple[str, str, str]]:
    rows = conn.execute(
        """
        SELECT artist, show_date, venue
        FROM booking_shows
        """
    ).fetchall()
    return {
        (normalize_text(row["artist"]), str(row["show_date"] or ""), normalize_text(row["venue"]))
        for row in rows
    }


def load_historical(keyword: str) -> pl.DataFrame:
    if not HISTORICAL_CSV.exists():
        rebuild_historical_base()

    return (
        pl.read_csv(HISTORICAL_CSV)
        .filter(pl.col("artista").cast(pl.Utf8).str.to_lowercase().str.contains(keyword))
        .with_columns([
            pl.col("artista").cast(pl.Utf8).str.strip_chars(),
            pl.col("fecha").cast(pl.Utf8),
            pl.col("venue_evento").cast(pl.Utf8).str.strip_chars(),
            pl.col("cachet_show").cast(pl.Float64, strict=False).fill_null(0),
            pl.col("gastos").cast(pl.Float64, strict=False).fill_null(0),
            pl.col("neto_show").cast(pl.Float64, strict=False).fill_null(0),
            pl.col("se_lleva_artista").cast(pl.Float64, strict=False).fill_null(0),
            pl.col("se_lleva_indyana").cast(pl.Float64, strict=False).fill_null(0),
        ])
        .sort(["fecha", "venue_evento", "archivo_origen"])
    )


def load_expense_details(keyword: str) -> dict[tuple[str, str, str, str], list[dict]]:
    movements = pl.read_parquet(STANDARDIZED_PATH)
    filtered = (
        movements
        .filter(
            (pl.col("business_area") == "booking")
            & (pl.col("movement_subcategory").str.to_lowercase() == "show")
            & (pl.col("movement_type") == "expense")
            & pl.col("artist_statement").cast(pl.Utf8).str.to_lowercase().str.contains(keyword)
            & pl.col("movement_date").is_not_null()
            & pl.col("amount_ars").is_not_null()
            & (pl.col("amount_ars") > 0)
            & (pl.col("concept").cast(pl.Utf8).str.to_lowercase().str.strip_chars() != "cachet")
        )
        .select([
            pl.col("source_file_name").cast(pl.Utf8),
            pl.col("artist_statement").cast(pl.Utf8),
            pl.col("movement_date").cast(pl.Utf8),
            pl.col("event_detail").cast(pl.Utf8),
            pl.col("concept").cast(pl.Utf8),
            pl.col("amount_ars").cast(pl.Float64),
            pl.col("fx_rate").cast(pl.Float64, strict=False),
            pl.col("payment_status").cast(pl.Utf8),
            pl.col("source_sheet").cast(pl.Utf8),
            pl.col("source_row").cast(pl.UInt32, strict=False),
        ])
        .sort(["movement_date", "event_detail", "source_row"])
    )

    by_key: dict[tuple[str, str, str, str], list[dict]] = {}
    for row in filtered.to_dicts():
        key = (
            normalize_text(row["source_file_name"]),
            normalize_text(row["artist_statement"]),
            str(row["movement_date"] or ""),
            normalize_text(row["event_detail"]),
        )
        by_key.setdefault(key, []).append(row)
    return by_key


def load_show_fx_rates(keyword: str) -> dict[tuple[str, str, str, str], float]:
    movements = pl.read_parquet(STANDARDIZED_PATH)
    filtered = (
        movements
        .filter(
            (pl.col("business_area") == "booking")
            & (pl.col("movement_subcategory").str.to_lowercase() == "show")
            & pl.col("artist_statement").cast(pl.Utf8).str.to_lowercase().str.contains(keyword)
            & pl.col("movement_date").is_not_null()
            & pl.col("fx_rate").is_not_null()
            & (pl.col("fx_rate") > 0)
        )
        .select([
            pl.col("source_file_name").cast(pl.Utf8),
            pl.col("artist_statement").cast(pl.Utf8),
            pl.col("movement_date").cast(pl.Utf8),
            pl.col("event_detail").cast(pl.Utf8),
            pl.col("movement_type").cast(pl.Utf8),
            pl.col("fx_rate").cast(pl.Float64),
        ])
    )

    grouped = (
        filtered
        .group_by(["source_file_name", "artist_statement", "movement_date", "event_detail"])
        .agg([
            pl.col("fx_rate").filter(pl.col("movement_type") == "income").first().alias("income_fx"),
            pl.col("fx_rate").filter(pl.col("movement_type") == "expense").first().alias("expense_fx"),
        ])
        .with_columns(pl.coalesce(["income_fx", "expense_fx"]).alias("fx_rate"))
    )

    out: dict[tuple[str, str, str, str], float] = {}
    for row in grouped.to_dicts():
        key = (
            normalize_text(row["source_file_name"]),
            normalize_text(row["artist_statement"]),
            str(row["movement_date"] or ""),
            normalize_text(row["event_detail"]),
        )
        if row["fx_rate"]:
            out[key] = float(row["fx_rate"])
    return out


def show_payload(row: dict, canonical_artist: str, fx_rate: float | None) -> dict:
    cachet = float(row["cachet_show"] or 0)
    expenses = float(row["gastos"] or 0)
    net = float(row["neto_show"] or 0)
    artist_cash = float(row["se_lleva_artista"] or 0)
    producer_cash = float(row["se_lleva_indyana"] or 0)

    if net > 0:
        artist_percent = artist_cash / net * 100
        producer_percent = producer_cash / net * 100
    else:
        artist_percent = 0.0
        producer_percent = 0.0

    return {
        "artist": canonical_artist,
        "show_date": row["fecha"],
        "venue": row["venue_evento"],
        "status": "no_cobrado" if row["control"] == "cachet_cero" else "realizado",
        "currency": "ARS",
        "fx_rate": fx_rate,
        "cachet_amount": cachet,
        "expenses_amount": expenses,
        "net_amount": net,
        "pre_split_adjustments_amount": 0.0,
        "split_base_amount": net,
        "artist_percent": artist_percent,
        "producer_percent": producer_percent,
        "artist_share_amount": artist_cash,
        "producer_share_amount": producer_cash,
        "artist_cash_target_amount": artist_cash,
        "producer_cash_target_amount": producer_cash,
        "artist_paid_amount": artist_cash,
        "producer_received_amount": producer_cash,
        "balance_artist_amount": 0.0,
        "balance_producer_amount": 0.0,
        "receipt_refs_json": "[]",
        "notes": (
            f"Import historico booking. Origen={row['archivo_origen']}; "
            f"control={row['control']}; lineas_ingreso={row['lineas_ingreso']}; "
            f"lineas_gasto={row['lineas_gasto']}."
        ),
    }


def insert_show(
    conn: sqlite3.Connection,
    row: dict,
    canonical_artist: str,
    expense_details: list[dict],
    now: str,
    fx_rate: float | None,
) -> int:
    payload = show_payload(row, canonical_artist, fx_rate)
    cursor = conn.execute(
        """
        INSERT INTO booking_shows (
            artist, show_date, venue, city, tour_manager, seller, status,
            currency, fx_rate, cachet_amount, expenses_amount, net_amount,
            pre_split_adjustments_amount, split_base_amount,
            artist_percent, producer_percent, artist_share_amount, producer_share_amount,
            artist_cash_target_amount, producer_cash_target_amount,
            artist_paid_amount, producer_received_amount, balance_artist_amount,
            balance_producer_amount, receipt_refs_json, notes, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["artist"],
            payload["show_date"],
            payload["venue"],
            None,
            None,
            None,
            payload["status"],
            payload["currency"],
            payload["fx_rate"],
            payload["cachet_amount"],
            payload["expenses_amount"],
            payload["net_amount"],
            payload["pre_split_adjustments_amount"],
            payload["split_base_amount"],
            payload["artist_percent"],
            payload["producer_percent"],
            payload["artist_share_amount"],
            payload["producer_share_amount"],
            payload["artist_cash_target_amount"],
            payload["producer_cash_target_amount"],
            payload["artist_paid_amount"],
            payload["producer_received_amount"],
            payload["balance_artist_amount"],
            payload["balance_producer_amount"],
            payload["receipt_refs_json"],
            payload["notes"],
            now,
            now,
        ),
    )
    show_id = int(cursor.lastrowid)

    movement_rows = [
        ("income", "cachet", payload["cachet_amount"], None),
        ("expense", "artist_payment", payload["artist_paid_amount"], None),
        ("income", "producer_settlement", payload["producer_received_amount"], None),
    ]

    if expense_details:
        for expense in expense_details:
            concept = str(expense.get("concept") or "gasto").strip() or "gasto"
            category = category_from_concept(concept)
            amount = float(expense.get("amount_ars") or 0)
            notes = json.dumps({
                "payment_status": expense.get("payment_status"),
                "source_sheet": expense.get("source_sheet"),
                "source_row": expense.get("source_row"),
            }, ensure_ascii=False)
            movement_rows.append(("expense", f"show_expense:{category}", amount, notes))
            conn.execute(
                """
                INSERT INTO booking_show_expenses (
                    show_id, concept, category, amount, currency, fx_rate, notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    show_id,
                    concept,
                    category,
                    amount,
                    payload["currency"],
                    expense.get("fx_rate"),
                    notes,
                    now,
                ),
            )
    elif payload["expenses_amount"] > 0:
        movement_rows.append(("expense", "show_expenses", payload["expenses_amount"], "Sin detalle de egresos en origen."))
        conn.execute(
            """
            INSERT INTO booking_show_expenses (
                show_id, concept, category, amount, currency, fx_rate, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                show_id,
                "Gastos historicos sin detalle",
                "general",
                payload["expenses_amount"],
                payload["currency"],
                None,
                "Sin detalle de egresos en origen.",
                now,
            ),
        )

    for movement_type, category, amount, notes in movement_rows:
        if amount <= 0:
            continue
        conn.execute(
            """
            INSERT INTO booking_movements (
                show_id, movement_type, category, amount, currency, fx_rate, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (show_id, movement_type, category, amount, payload["currency"], payload["fx_rate"], notes, now),
        )

    return show_id


def import_artist(keyword: str, canonical_artist: str, dry_run: bool) -> dict:
    historical = load_historical(keyword)
    expense_lookup = load_expense_details(keyword)
    fx_lookup = load_show_fx_rates(keyword)

    with sqlite3.connect(LIVE_DB) as conn:
        conn.row_factory = sqlite3.Row
        live_keys = existing_live_keys(conn)

        pending = []
        for row in historical.to_dicts():
            key = (normalize_text(canonical_artist), str(row["fecha"] or ""), normalize_text(row["venue_evento"]))
            if key not in live_keys:
                pending.append(row)

        totals = {
            "pending": len(pending),
            "cachet": sum(float(row["cachet_show"] or 0) for row in pending),
            "expenses": sum(float(row["gastos"] or 0) for row in pending),
            "artist": sum(float(row["se_lleva_artista"] or 0) for row in pending),
            "producer": sum(float(row["se_lleva_indyana"] or 0) for row in pending),
            "inserted": 0,
            "expense_rows": 0,
            "with_fx": 0,
        }

        if dry_run:
            return totals

        now = datetime.now().isoformat(timespec="seconds")
        for row in pending:
            expense_key = (
                normalize_text(row["archivo_origen"]),
                normalize_text(row["artista"]),
                str(row["fecha"] or ""),
                normalize_text(row["venue_evento"]),
            )
            expense_details = expense_lookup.get(expense_key, [])
            fx_rate = fx_lookup.get(expense_key)
            insert_show(conn, row, canonical_artist, expense_details, now, fx_rate)
            totals["inserted"] += 1
            totals["expense_rows"] += len(expense_details)
            if fx_rate:
                totals["with_fx"] += 1

        conn.commit()
        return totals


def update_existing_fx(keyword: str, canonical_artist: str) -> dict:
    historical = load_historical(keyword)
    fx_lookup = load_show_fx_rates(keyword)
    by_show_key: dict[tuple[str, str], float] = {}

    for row in historical.to_dicts():
        source_key = (
            normalize_text(row["archivo_origen"]),
            normalize_text(row["artista"]),
            str(row["fecha"] or ""),
            normalize_text(row["venue_evento"]),
        )
        fx_rate = fx_lookup.get(source_key)
        if fx_rate:
            by_show_key[(str(row["fecha"] or ""), normalize_text(row["venue_evento"]))] = fx_rate

    updated = 0
    with sqlite3.connect(LIVE_DB) as conn:
        conn.row_factory = sqlite3.Row
        shows = conn.execute(
            """
            SELECT id, show_date, venue
            FROM booking_shows
            WHERE lower(artist) = lower(?)
              AND notes LIKE 'Import historico booking.%'
            """,
            (canonical_artist,),
        ).fetchall()

        for show in shows:
            fx_rate = by_show_key.get((str(show["show_date"] or ""), normalize_text(show["venue"])))
            if not fx_rate:
                continue

            conn.execute("UPDATE booking_shows SET fx_rate = ? WHERE id = ?", (fx_rate, show["id"]))
            conn.execute(
                "UPDATE booking_movements SET fx_rate = ? WHERE show_id = ? AND fx_rate IS NULL",
                (fx_rate, show["id"]),
            )
            updated += 1

        conn.commit()

    return {"updated_shows": updated, "fx_available": len(by_show_key)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", default="virr|virs|virsh")
    parser.add_argument("--artist", default="Virrshi Dj")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--update-fx-only", action="store_true")
    args = parser.parse_args()

    if args.rebuild:
        rebuild_historical_base()

    if args.dry_run:
        totals = import_artist(args.keyword, args.artist, dry_run=True)
        print(json.dumps(totals, ensure_ascii=False, indent=2))
        return

    if args.update_fx_only:
        backup = backup_live_db()
        totals = update_existing_fx(args.keyword, args.artist)
        print(json.dumps({"backup": str(backup), **totals}, ensure_ascii=False, indent=2))
        return

    backup = backup_live_db()
    totals = import_artist(args.keyword, args.artist, dry_run=False)
    print(json.dumps({"backup": str(backup), **totals}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
