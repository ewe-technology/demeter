"""
Binance USDT-M perpetual funding history (8h settlements) as a CSV, for EXP-014's perp hedge.

usage: python fetch_binance_funding.py <SYMBOL e.g. ETHUSDT> <start YYYY-MM-DD> <end YYYY-MM-DD> <out.csv>
Columns: timestamp (UTC settlement time), rate (fraction per 8h, positive = longs pay shorts), mark_price (when given).
Public endpoint, no key: GET https://fapi.binance.com/fapi/v1/fundingRate (max 1000 rows per call).
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone

import pandas as pd

URL = "https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&startTime={start}&endTime={end}&limit=1000"


def fetch(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    rows, t = [], int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    while t < end_ms:
        req = urllib.request.Request(URL.format(sym=symbol, start=t, end=end_ms), headers={"user-agent": "fetch"})
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    batch = json.loads(r.read())
                break
            except Exception as e:  # noqa: BLE001 - retry on any transport error
                if attempt == 5:
                    raise
                time.sleep(2 ** attempt)
        if not batch:
            break
        rows += batch
        t = batch[-1]["fundingTime"] + 1
        time.sleep(0.2)
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True).dt.tz_localize(None).dt.round("min")
    df["rate"] = df["fundingRate"].astype(float)
    df["mark_price"] = pd.to_numeric(df.get("markPrice"), errors="coerce")
    return df[["timestamp", "rate", "mark_price"]].drop_duplicates("timestamp").sort_values("timestamp")


if __name__ == "__main__":
    sym, s, e, out = sys.argv[1:5]
    start = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(e).replace(tzinfo=timezone.utc)
    df = fetch(sym, start, end)
    df.to_csv(out, index=False)
    print(f"{sym}: {len(df)} settlements {df.timestamp.iloc[0]}..{df.timestamp.iloc[-1]}, "
          f"mean 8h rate {df.rate.mean():.5%}, annualised {df.rate.mean() * 3 * 365:.1%}, share negative {(df.rate < 0).mean():.1%}")
