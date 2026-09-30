"""
Hourly Ethereum gas price for LP cost modelling.

After London (block 12,965,000) the price paid is baseFeePerGas + a tip; before it, the median
gasPrice of the block's transactions. One block roughly every hour (300 blocks).

usage: python fetch_gas.py <start block> <end block> <out csv>
"""
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from fetch_uni_minute import rpc

LONDON = 12_965_000
TIP_GWEI = 1.0


def sample(n):
    full = n < LONDON
    b = rpc("eth_getBlockByNumber", [hex(n), full])
    ts = int(b["timestamp"], 16)
    if full:
        prices = [int(t["gasPrice"], 16) for t in b["transactions"] if t.get("gasPrice")]
        gwei = statistics.median(prices) / 1e9 if prices else float("nan")
    else:
        gwei = int(b["baseFeePerGas"], 16) / 1e9 + TIP_GWEI
    return ts, n, gwei


def main():
    a, b, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    blocks = list(range(a, b + 1, 300))
    with ThreadPoolExecutor(int(os.environ.get("THREADS", "12"))) as ex:
        rows = list(ex.map(sample, blocks))
    d = pd.DataFrame(rows, columns=["ts", "block", "gwei"])
    d["timestamp"] = pd.to_datetime(d["ts"], unit="s")
    d[["timestamp", "block", "gwei"]].to_csv(out, index=False)
    print("done", len(d), "samples, median gwei", round(d["gwei"].median(), 2))


if __name__ == "__main__":
    main()
