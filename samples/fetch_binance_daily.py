"""Binance spot daily closes (UTC day close) of ETHUSDT and BTCUSDT from 2019 -> binance_daily_closes.csv.
EXP-018 reads the 12-month return from it (the pools' minute data starts too late)."""
import json
import os
import urllib.request

import pandas as pd


def get(sym):
    out, start = [], 1546300800000   # 2019-01-01
    while True:
        u = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1d&startTime={start}&limit=1000"
        d = json.load(urllib.request.urlopen(u, timeout=30))
        if not d:
            break
        out += d
        start = d[-1][0] + 86400000
        if len(d) < 1000:
            break
    df = pd.DataFrame(out).iloc[:, [0, 4]]
    df.columns = ["date", "close"]
    df["date"] = pd.to_datetime(df["date"], unit="ms")
    df["close"] = df["close"].astype(float)
    return df.set_index("date")["close"]


if __name__ == "__main__":
    pd.DataFrame({s: get(s) for s in ["ETHUSDT", "BTCUSDT"]}).to_csv(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "binance_daily_closes.csv"))
