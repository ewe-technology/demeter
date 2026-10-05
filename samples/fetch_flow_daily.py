"""
Daily market-flow series for EXP-092.. (round 2, batch 3), written to samples/flow_daily.csv:

- stable_mcap: total stablecoin market cap, USD (DefiLlama /stablecoincharts/all, pegged USD).
- cb_eth, cb_btc: Coinbase ETH-USD / BTC-USD daily close (00:00 UTC candle, 300-day pages).

usage (from samples/): python fetch_flow_daily.py
"""
import time
from datetime import datetime, timedelta, timezone

import json
import urllib.parse
import urllib.request

import pandas as pd

START = datetime(2020, 6, 1, tzinfo=timezone.utc)


def get(url: str, params: dict | None = None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"user-agent": "demeter-research"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def stablecoins() -> pd.Series:
    r = get("https://stablecoins.llama.fi/stablecoincharts/all")
    s = pd.Series({pd.Timestamp(int(x["date"]), unit="s"): float(x["totalCirculatingUSD"]["peggedUSD"]) for x in r})
    return s.sort_index()


def coinbase(product: str) -> pd.Series:
    out, t = {}, START
    end = datetime.now(timezone.utc)
    while t < end:
        t2 = min(t + timedelta(days=299), end)
        r = get(f"https://api.exchange.coinbase.com/products/{product}/candles",
                {"granularity": 86400, "start": t.isoformat(), "end": t2.isoformat()})
        for ts, lo, hi, op, cl, vol in r:
            out[pd.Timestamp(ts, unit="s")] = float(cl)
        t = t2 + timedelta(days=1)
        time.sleep(0.4)
    return pd.Series(out).sort_index()


if __name__ == "__main__":
    df = pd.DataFrame({"stable_mcap": stablecoins(), "cb_eth": coinbase("ETH-USD"), "cb_btc": coinbase("BTC-USD")})
    df = df.loc[pd.Timestamp(START.date()):]
    df.index.name = "date"
    df.to_csv("flow_daily.csv", float_format="%.6f")
    print(df.describe().T[["count", "min", "max"]])
    print(df.index.min(), df.index.max())
