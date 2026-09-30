"""
Minimal replacement for demeter-fetch's uniswap `minute` output, using a public archive RPC.

Only Swap events are needed (same as demeter_fetch/processor_uniswap/minute.py). Logs from
tenderly/mevblocker/nodereal carry `blockTimestamp`, so no per-block timestamp lookups are needed.

usage: python fetch_uni_minute.py <pool_address> <start YYYY-MM-DD> <end YYYY-MM-DD> <out_dir>
"""
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pandas as pd

RPC = os.environ.get("ETH_RPC", "https://gateway.tenderly.co/public/mainnet")
SWAP = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
STEP = int(os.environ.get("STEP", "10000"))  # blocks per eth_getLogs; tenderly's public Base gateway caps at 1000
COLUMNS = ["timestamp", "netAmount0", "netAmount1", "closeTick", "openTick", "lowestTick", "highestTick",
           "inAmount0", "inAmount1", "currentLiquidity"]


def rpc(method, params, retries=8):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for i in range(retries):
        try:
            req = urllib.request.Request(RPC, body, {"content-type": "application/json", "user-agent": "fetch"})
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.load(r)
            if "error" in d:
                raise RuntimeError(d["error"])
            return d["result"]
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)


def block_ts(n):
    return int(rpc("eth_getBlockByNumber", [hex(n), False])["timestamp"], 16)


def first_block_at_or_after(ts):
    lo, hi = 1, int(rpc("eth_blockNumber", []), 16)
    while lo < hi:
        mid = (lo + hi) // 2
        if block_ts(mid) < ts:
            lo = mid + 1
        else:
            hi = mid
    return lo


def s256(h):
    v = int(h, 16)
    return v - (1 << 256) if v >= 1 << 255 else v


def decode(log):
    d = log["data"][2:]
    w = [d[i:i + 64] for i in range(0, len(d), 64)]
    a0, a1 = s256(w[0]), s256(w[1])
    return (int(log["blockTimestamp"], 16), int(log["blockNumber"], 16), int(log["logIndex"], 16),
            a0, a1, int(w[3], 16), s256(w[4]))


def get_range(pool, a, b):
    out = []
    stack = [(a, b)]
    while stack:
        x, y = stack.pop()
        try:
            logs = rpc("eth_getLogs", [{"address": pool, "topics": [SWAP], "fromBlock": hex(x), "toBlock": hex(y)}],
                       retries=3)
            out.extend(decode(l) for l in logs)
        except Exception:
            if y - x < 50:
                logs = rpc("eth_getLogs",
                           [{"address": pool, "topics": [SWAP], "fromBlock": hex(x), "toBlock": hex(y)}])
                out.extend(decode(l) for l in logs)
            else:
                m = (x + y) // 2
                stack += [(x, m), (m + 1, y)]
    return out


def to_minute(rows, day, prev_close):
    idx = pd.date_range(day, periods=1440, freq="1min")
    if rows:
        df = pd.DataFrame(rows, columns=["ts", "bn", "li", "a0", "a1", "liq", "tick"]).sort_values(["bn", "li"])
        df.index = pd.to_datetime(df["ts"], unit="s")
        df["in0"] = df["a0"].clip(lower=0)
        df["in1"] = df["a1"].clip(lower=0)
        g = df.resample("1min")
        m = pd.DataFrame({
            "netAmount0": g["a0"].sum(), "netAmount1": g["a1"].sum(),
            "inAmount0": g["in0"].sum(), "inAmount1": g["in1"].sum(),
            "currentLiquidity": g["liq"].last(),
            "openTick": g["tick"].first(), "highestTick": g["tick"].max(),
            "lowestTick": g["tick"].min(), "closeTick": g["tick"].last(),
        }).reindex(idx)
    else:
        m = pd.DataFrame(index=idx, columns=["netAmount0", "netAmount1", "inAmount0", "inAmount1",
                                             "currentLiquidity", "openTick", "highestTick", "lowestTick",
                                             "closeTick"], dtype=object)
    if prev_close is not None:
        if pd.isna(m["closeTick"].iloc[0]):
            m.loc[m.index[0], ["closeTick", "currentLiquidity"]] = prev_close
    m[["closeTick", "currentLiquidity"]] = m[["closeTick", "currentLiquidity"]].ffill().bfill()
    for c in ["netAmount0", "netAmount1", "inAmount0", "inAmount1"]:
        m[c] = m[c].fillna(0)
    for c in ["openTick", "highestTick", "lowestTick"]:
        m[c] = m[c].fillna(m["closeTick"])
    for c in m.columns:
        m[c] = m[c].map(lambda v: int(v))
    m["timestamp"] = m.index
    return m[COLUMNS], (int(m["closeTick"].iloc[-1]), int(m["currentLiquidity"].iloc[-1]))


def main():
    pool, start, end, out = sys.argv[1].lower(), sys.argv[2], sys.argv[3], sys.argv[4]
    os.makedirs(out, exist_ok=True)
    d0 = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    d1 = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    b0 = first_block_at_or_after(int(d0.timestamp()))
    b1 = first_block_at_or_after(int(d1.timestamp())) - 1
    print(f"blocks {b0}..{b1}", flush=True)
    chunks = [(a, min(a + STEP - 1, b1)) for a in range(b0, b1 + 1, STEP)]
    rows = []
    done = 0
    with ThreadPoolExecutor(int(os.environ.get("THREADS", "4"))) as ex:
        for r in ex.map(lambda c: get_range(pool, *c), chunks):
            rows.extend(r)
            done += 1
            if done % 20 == 0:
                print(f"{datetime.now():%H:%M:%S} chunks {done}/{len(chunks)} swaps {len(rows)}", flush=True)
    by_day = {}
    for r in rows:
        by_day.setdefault(datetime.fromtimestamp(r[0], timezone.utc).date(), []).append(r)
    prev = None
    day = d0.date()
    while day < d1.date():
        m, prev = to_minute(by_day.get(day, []), pd.Timestamp(day), prev)
        m.to_csv(os.path.join(out, f"ethereum-{pool}-{day:%Y-%m-%d}.minute.csv"), index=False)
        day += timedelta(days=1)
    print("done", len(rows), "swaps", flush=True)


if __name__ == "__main__":
    main()
