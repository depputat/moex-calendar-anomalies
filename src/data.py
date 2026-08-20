"""Загрузка и подготовка котировок MOEX."""

from pathlib import Path

import pandas as pd
import requests

BASE = "https://iss.moex.com/iss/history/engines/stock/markets/shares/boards/TQBR/securities"
START_DATE = "2014-01-01"
END_DATE = "2026-08-19"
SPLIT_THRESHOLD = 0.5

TICKERS = [
    "SBER", "GAZP", "LKOH", "GMKN", "NVTK", "ROSN", "TATN", "PLZL", "SNGSP",
    "X5", "MGNT", "CHMF", "NLMK", "ALRS", "AFLT", "IRAO", "RTKM", "MOEX",
    "PHOR", "VTBR", "SIBN", "SMLT", "POSI", "MAGN", "T",
]


def project_root():
    """Корень проекта независимо от того, откуда запущен код."""
    cwd = Path.cwd()
    return cwd.parent if cwd.name == "notebooks" else cwd


def load_history(ticker, start_date=START_DATE, end_date=END_DATE, retries=3):
    """Качает дневную историю по бумаге с MOEX ISS, обходя пагинацию.

    При сетевых сбоях повторяет запрос до retries раз
    с экспоненциально растущей паузой.
    """
    rows, columns, cursor = [], None, 0
    while True:
        for attempt in range(retries):
            try:
                response = requests.get(
                    f"{BASE}/{ticker}.json",
                    params={
                        "from": start_date,
                        "till": end_date,
                        "start": cursor,
                        "iss.meta": "off",
                    },
                    timeout=30,
                )
                response.raise_for_status()
                break
            except requests.exceptions.RequestException:
                if attempt == retries - 1:
                    raise
                time.sleep(2 ** attempt)

        block = response.json()["history"]
        if not block["data"]:
            break
        columns = block["columns"]
        rows.extend(block["data"])
        cursor += len(block["data"])

    df = pd.DataFrame(rows, columns=columns)
    df["TRADEDATE"] = pd.to_datetime(df["TRADEDATE"])
    return df


def load_prices():
    """Читает сохранённые котировки с диска."""
    path = project_root() / "data" / "raw" / "moex_prices.csv"
    return pd.read_csv(path, parse_dates=["TRADEDATE"])


def prepare(prices):
    """Чистит данные и считает дневные доходности.

    Удаляет строки без цены закрытия и рабочие субботы,
    помечает как неопределённые доходности при сплитах.
    """
    df = prices[prices["CLOSE"].notna()].copy()
    df = df[["TRADEDATE", "SECID", "CLOSE", "VOLUME"]]
    df = df.sort_values(["SECID", "TRADEDATE"]).reset_index(drop=True)

    df["RETURN"] = df.groupby("SECID")["CLOSE"].pct_change()
    df.loc[df["RETURN"].abs() > SPLIT_THRESHOLD, "RETURN"] = None

    df["DOW"] = df["TRADEDATE"].dt.dayofweek
    df["MONTH"] = df["TRADEDATE"].dt.month
    df["YEAR"] = df["TRADEDATE"].dt.year

    return df[df["DOW"] < 5].reset_index(drop=True)


def to_daily(prices):
    """Сворачивает к одному наблюдению на дату: среднее по бумагам."""
    daily = prices.groupby("TRADEDATE")["RETURN"].mean().reset_index()
    daily["DOW"] = daily["TRADEDATE"].dt.dayofweek
    daily["MONTH"] = daily["TRADEDATE"].dt.month
    daily["YEAR"] = daily["TRADEDATE"].dt.year
    return daily