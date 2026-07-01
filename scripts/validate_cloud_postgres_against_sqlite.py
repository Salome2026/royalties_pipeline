from __future__ import annotations

import argparse
import json
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import quote

import psycopg


ROOT = Path(r"C:\royalties_pipeline")
DEFAULT_SQLITE = ROOT / "warehouse" / "booking" / "live" / "booking_live.sqlite"
DEFAULT_SECRET = ROOT / ".secrets" / "cloudsql_operational.env"


BOOKING_ARTISTS = [
    "Virrshi Dj",
    "Aneley",
    "Candu Dominguez",
    "G Sony",
    "Gusty DJ",
    "Laalo DJ",
]

FINANCE_ARTISTS = [
    "Virrshi Dj",
    "Aneley",
    "Bianca Lif",
]


def money(value) -> str:
    if value is None:
        value = 0
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def load_secret(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    return data


def pg_dsn(secret_path: Path, host: str) -> str:
    secret = load_secret(secret_path)
    password = quote(secret["CLOUDSQL_PASSWORD"], safe="")
    database = secret.get("CLOUDSQL_DATABASE", "vpo_corp")
    user = secret.get("CLOUDSQL_USER", "postgres")
    return f"postgresql://{user}:{password}@{host}:5432/{database}"


def sqlite_query(con: sqlite3.Connection, sql: str, params=()):
    cur = con.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def pg_query(con: psycopg.Connection, sql: str, params=()):
    with con.cursor() as cur:
        cur.execute(sql, params)
        cols = [desc.name for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def normalize_rows(rows):
    out = []
    for row in rows:
        normalized = {}
        for key, value in row.items():
            if isinstance(value, Decimal):
                normalized[key] = money(value)
            elif isinstance(value, float):
                normalized[key] = money(value)
            else:
                normalized[key] = value
        out.append(normalized)
    return out


def compare_section(name: str, sqlite_rows, pg_rows):
    left = normalize_rows(sqlite_rows)
    right = normalize_rows(pg_rows)
    return {
        "name": name,
        "ok": left == right,
        "sqlite": left,
        "postgres": right,
    }


def run(args: argparse.Namespace) -> dict:
    sqlite_con = sqlite3.connect(args.sqlite)
    sqlite_con.row_factory = sqlite3.Row
    dsn = pg_dsn(Path(args.secret), args.host)

    sections = []
    with psycopg.connect(dsn) as pg_con:
        count_tables = [
            ("booking_shows", "booking_shows"),
            ("booking_show_expenses", "booking_show_expenses"),
            ("booking_movements", "booking_movements"),
            ("booking_artist_ledger", "booking_artist_ledger"),
            ("booking_composite_events", "booking_composite_events"),
            ("booking_composite_event_lines", "booking_composite_event_lines"),
            ("finance_staging_movements", "finance_movements"),
            ("finance_projects", "finance_projects"),
            ("finance_recovery_applications", "finance_recovery_applications"),
            ("app_users", "app_users"),
            ("module_permissions", "module_permissions"),
        ]
        for sqlite_table, pg_table in count_tables:
            sqlite_sql = f'SELECT COUNT(*) AS rows FROM "{sqlite_table}"'
            pg_sql = f'SELECT COUNT(*) AS rows FROM "{pg_table}"'
            sections.append(
                compare_section(
                    f"count:{sqlite_table}->{pg_table}",
                    sqlite_query(sqlite_con, sqlite_sql),
                    pg_query(pg_con, pg_sql),
                )
            )

        booking_sql = """
            SELECT
                artist,
                COUNT(*) AS shows,
                COALESCE(SUM(cachet_amount), 0) AS cachet_amount,
                COALESCE(SUM(expenses_amount), 0) AS expenses_amount,
                COALESCE(SUM(artist_share_amount), 0) AS artist_share_amount,
                COALESCE(SUM(producer_share_amount), 0) AS producer_share_amount,
                COALESCE(SUM(artist_paid_amount), 0) AS artist_paid_amount,
                COALESCE(SUM(producer_received_amount), 0) AS producer_received_amount,
                COALESCE(SUM(balance_artist_amount), 0) AS balance_artist_amount,
                COALESCE(SUM(balance_producer_amount), 0) AS balance_producer_amount,
                COALESCE(SUM(venue_balance_amount), 0) AS venue_balance_amount
            FROM booking_shows
            WHERE artist = ?
            GROUP BY artist
        """
        pg_booking_sql = booking_sql.replace("?", "%s")
        for artist in BOOKING_ARTISTS:
            sections.append(
                compare_section(
                    f"booking_artist:{artist}",
                    sqlite_query(sqlite_con, booking_sql, (artist,)),
                    pg_query(pg_con, pg_booking_sql, (artist,)),
                )
            )

        finance_sql = """
            SELECT
                artist,
                COUNT(*) AS movements,
                COALESCE(SUM(amount_ars), 0) AS amount_ars,
                COALESCE(SUM(paid_amount_ars), 0) AS paid_amount_ars,
                COALESCE(SUM(pending_amount_ars), 0) AS pending_amount_ars
            FROM finance_staging_movements
            WHERE artist = ?
            GROUP BY artist
        """
        pg_finance_sql = finance_sql.replace("finance_staging_movements", "finance_movements").replace("?", "%s")
        for artist in FINANCE_ARTISTS:
            sections.append(
                compare_section(
                    f"finance_artist:{artist}",
                    sqlite_query(sqlite_con, finance_sql, (artist,)),
                    pg_query(pg_con, pg_finance_sql, (artist,)),
                )
            )

        composite_sql = """
            SELECT
                COUNT(*) AS events,
                COALESCE(SUM(gross_amount), 0) AS gross_amount,
                COALESCE(SUM(general_expenses_amount), 0) AS general_expenses_amount,
                COALESCE(SUM(producer_expected_amount), 0) AS producer_expected_amount,
                COALESCE(SUM(received_amount), 0) AS received_amount,
                COALESCE(SUM(balance_amount), 0) AS balance_amount
            FROM booking_composite_events
        """
        sections.append(
            compare_section(
                "composite_events_summary",
                sqlite_query(sqlite_con, composite_sql),
                pg_query(pg_con, composite_sql),
            )
        )

    failed = [section for section in sections if not section["ok"]]
    return {
        "ok": not failed,
        "sections_checked": len(sections),
        "failed_sections": [section["name"] for section in failed],
        "sections": sections,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Cloud SQL data against production local SQLite.")
    parser.add_argument("--sqlite", default=str(DEFAULT_SQLITE))
    parser.add_argument("--secret", default=str(DEFAULT_SECRET))
    parser.add_argument("--host", default="34.66.30.151")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    result = run(args)
    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
