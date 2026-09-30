"""
Daily Aave USDC supply APR (currentLiquidityRate, ray -> float APR) at ~12:00 UTC, from an archive RPC.

Mainnet: Aave v2 until the v3 USDC market opened (2023-01-27), v3 after. Base: Aave v3.
Blocks are estimated from the slot time (mainnet 12 s post-merge, Base 2 s) and corrected once per day.

usage: python fetch_aave_rates.py <ethereum|base> <start YYYY-MM-DD> <end YYYY-MM-DD> <out.csv>
"""
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import pandas as pd

MARKETS = {
    # chain: [(first day, pool, usdc, layout)]; layout "v2": rate is word 3, "v3": word 2 of getReserveData
    "ethereum": [(date(2020, 12, 1), "0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9",
                  "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "v2"),
                 (date(2023, 1, 27), "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
                  "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "v3")],
    "base": [(date(2023, 9, 1), "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
              "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "v3")],
}
RPCS = {"ethereum": os.environ.get("ETH_RPC", "https://gateway.tenderly.co/public/mainnet"),
        "base": os.environ.get("BASE_RPC", "https://base.gateway.tenderly.co")}
SLOT = {"ethereum": 12, "base": 2}


def rpc(url, method, params, retries=8):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for i in range(retries):
        try:
            req = urllib.request.Request(url, body, {"content-type": "application/json", "user-agent": "fetch"})
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.load(r)
            if "error" in d:
                raise RuntimeError(d["error"])
            return d["result"]
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)


def block_near(url, slot, ts, ref):
    """Block at or just before ts, starting from a (block, time) reference; two slot-time corrections."""
    b = ref[0] + (ts - ref[1]) // slot
    for _ in range(3):
        t = int(rpc(url, "eth_getBlockByNumber", [hex(b), False])["timestamp"], 16)
        if abs(t - ts) <= slot * 5:
            return b
        b += (ts - t) // slot
    return b


def rate_on(chain, day):
    url, slot = RPCS[chain], SLOT[chain]
    market = [m for m in MARKETS[chain] if m[0] <= day][-1]
    ts = int(datetime.combine(day, datetime.min.time(), timezone.utc).timestamp()) + 12 * 3600
    b = block_near(url, slot, ts, REF[chain])
    data = "0x35ea6a75" + market[2][2:].lower().rjust(64, "0")
    out = rpc(url, "eth_call", [{"to": market[1], "data": data}, hex(b)])[2:]
    word = 3 if market[3] == "v2" else 2
    return day, int(out[64 * word:64 * (word + 1)], 16) / 1e27, market[3]


def main():
    global REF
    chain, start, end, out = sys.argv[1], date.fromisoformat(sys.argv[2]), date.fromisoformat(sys.argv[3]), sys.argv[4]
    url = RPCS[chain]
    head = int(rpc(url, "eth_blockNumber", []), 16)
    REF = {chain: (head, int(rpc(url, "eth_getBlockByNumber", [hex(head), False])["timestamp"], 16))}
    days = [start + timedelta(d) for d in range((end - start).days + 1)]
    with ThreadPoolExecutor(int(os.environ.get("THREADS", "6"))) as ex:
        rows = list(ex.map(lambda d: rate_on(chain, d), days))
    df = pd.DataFrame(rows, columns=["date", "apr", "market"])
    df.to_csv(out, index=False)
    print(df.groupby(pd.to_datetime(df["date"]).dt.year)["apr"].mean().round(4).to_string())


if __name__ == "__main__":
    main()
