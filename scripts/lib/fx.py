# C:\royalties_pipeline\scripts\lib\fx.py

import calendar
from datetime import datetime, date
from pathlib import Path

import polars as pl
import requests

FX_PATH = Path(r"C:\royalties_pipeline\warehouse\registry\exchange_rates.parquet")


# -----------------------------
# LOAD / SAVE
# -----------------------------

def load_fx_table() -> pl.DataFrame:
    if FX_PATH.exists():
        return pl.read_parquet(FX_PATH)

    return pl.DataFrame(
        schema={
            "fx_month": pl.Utf8,
            "from_currency": pl.Utf8,
            "to_currency": pl.Utf8,
            "rate_type": pl.Utf8,
            "rate": pl.Float64,
            "source": pl.Utf8,
            "fetched_at": pl.Utf8,
        }
    )


def save_fx_table(df: pl.DataFrame):
    FX_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(FX_PATH)


# -----------------------------
# FETCH (igual a tu lógica)
# -----------------------------

def fetch_monthly_avg_rate(fx_month: str, from_currency: str, to_currency: str) -> float:
    from_currency = normalize_currency(from_currency)
    to_currency = normalize_currency(to_currency)

    print(f"  - Buscando FX promedio {from_currency}/{to_currency} para {fx_month}...")

    year, month = map(int, fx_month.split("-"))
    last_day = calendar.monthrange(year, month)[1]

    rates = []

    for day in range(1, last_day + 1):
        rate_date = date(year, month, day).isoformat()

        url = f"https://api.frankfurter.dev/v2/rates?date={rate_date}&base={from_currency}&quotes={to_currency}"

        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()

            rate = None

            if isinstance(data, dict):
                rate = data.get("rates", {}).get(to_currency)
            elif isinstance(data, list) and len(data) > 0:
                rate = data[0].get("rate")

            if rate is not None:
                rates.append(float(rate))

        except Exception:
            continue

    if not rates:
        raise ValueError(f"No se encontraron tasas {from_currency}/{to_currency} para {fx_month}")

    avg_rate = sum(rates) / len(rates)

    print(f"  - FX promedio {fx_month}: {avg_rate}")

    return avg_rate


# -----------------------------
# MAIN API
# -----------------------------

def normalize_currency(currency: str) -> str:
    currency = str(currency).upper().strip()
    return {"RUR": "RUB"}.get(currency, currency)


def get_monthly_fx(
    fx_month: str,
    from_currency: str,
    to_currency: str,
    rate_type: str = "monthly_avg",
) -> float:
    from_currency = normalize_currency(from_currency)
    to_currency = normalize_currency(to_currency)

    if from_currency == to_currency:
        return 1.0

    fx_table = load_fx_table()

    existing = fx_table.filter(
        (pl.col("fx_month") == fx_month) &
        (pl.col("from_currency") == from_currency) &
        (pl.col("to_currency") == to_currency) &
        (pl.col("rate_type") == rate_type)
    )

    if existing.height > 0:
        rate = float(existing.select("rate").item())
        print(f"  - FX cacheado {fx_month}: {rate}")
        return rate

    rate = fetch_monthly_avg_rate(fx_month, from_currency, to_currency)

    new_row = pl.DataFrame([{
        "fx_month": fx_month,
        "from_currency": from_currency,
        "to_currency": to_currency,
        "rate_type": rate_type,
        "rate": rate,
        "source": "frankfurter",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }])

    fx_table = pl.concat([fx_table, new_row], how="diagonal_relaxed")
    save_fx_table(fx_table)

    return rate
