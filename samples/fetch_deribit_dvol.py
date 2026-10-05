"""
Daily Deribit DVOL (30-day implied volatility index) for ETH and BTC, from the public API.

usage: python fetch_deribit_dvol.py <start YYYY-MM-DD> <end YYYY-MM-DD> <out.csv>
Writes date,ETH,BTC (daily close of the index, annualised %).
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone

import pandas as pd

URL = ("https://www.deribit.com/api/v2/public/get_volatility_index_data?currency={c}"
       "&start_timestamp={s}&end_timestamp={e}&resolution=1D")


def fetch(currency: str, start: datetime, end: datetime) -> pd.Series:
    rows, s, e = [], int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    while s < e:
        req = urllib.request.Request(URL.format(c=currency, s=s, e=e), headers={"user-agent": "fetch"})
        with urllib.request.urlopen(req, timeout=60) as r:
            res = json.load(r)["result"]
        data = res["data"]
        if not data:
            break
        rows += data
        cont = res.get("continuation")
        if not cont or cont <= s:
            break
        e = cont   # the API pages backwards from the end
        time.sleep(0.2)
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"]).drop_duplicates("ts")
    df["date"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_localize(None).dt.normalize()
    return df.set_index("date")["close"].sort_index()


def main():
    start = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(sys.argv[2]).replace(tzinfo=timezone.utc)
    out = pd.DataFrame({c: fetch(c, start, end) for c in ("ETH", "BTC")})
    out.index.name = "date"
    out.to_csv(sys.argv[3])
    print(out.index[0].date(), out.index[-1].date(), len(out), out.isna().sum().to_dict())


if __name__ == "__main__":
    main()
