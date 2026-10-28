"""Binance spot UTC daily closes for the signal engines, from samples/real-data/binance/{SYMBOL}-1d.csv
(written by demeter-fetch binance_klines.py: date,open,high,low,close,volume, date = the candle's UTC day)."""
from datetime import date
from pathlib import Path

import pandas as pd

BINANCE_DIR = Path(__file__).resolve().parent.parent / "real-data" / "binance"
# token name -> Binance USDT pair; wrapped / bridged tokens follow their underlying
SYMBOL = {"eth": "ETHUSDT", "weth": "ETHUSDT", "btc": "BTCUSDT", "wbtc": "BTCUSDT", "cbbtc": "BTCUSDT"}
STABLE = {"usdc", "usdt", "dai"}  # priced at 1 USDT, as the spec's ETHUSDT signal does


def usdt_close(token: str, end: date) -> pd.Series:
    """Daily close of `token` in USDT, indexed by UTC day (00:00), from the first Binance day through `end`."""
    sym = SYMBOL.get(token.lower())
    if sym is None:
        raise KeyError(f"no Binance pair for token {token!r}, add it to binance_data.SYMBOL")
    path = BINANCE_DIR / f"{sym}-1d.csv"
    close = pd.read_csv(path, usecols=["date", "close"], index_col="date", parse_dates=True)["close"].astype(float)
    if close.index[-1] < pd.Timestamp(end):
        raise ValueError(f"{path} ends {close.index[-1].date()}, before {end}: rerun demeter-fetch binance_klines.py {sym}")
    return close.loc[:pd.Timestamp(end)].rename(sym)


def close_in(base: str, quote: str, end: date) -> pd.Series:
    """Daily close of `base` priced in `quote` (a stable quote counts as USDT), through `end`."""
    b = usdt_close(base, end)
    return b if quote.lower() in STABLE else (b / usdt_close(quote, end)).dropna()
