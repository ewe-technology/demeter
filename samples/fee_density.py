"""Fee income per unit of in-range liquidity for one Uniswap v3 WETH/USDC pool, one day at 3, 60 and 200 days ago.

usage: RPC=<url> BPD=<blocks per day> STEP=<log range> NAME=<label> POOL=<address> WETH0=<1 if token0 is WETH> \
       python fee_density.py

fee growth per unit L for a swap = amount_in x fee / L_active (in token terms); valued in USDC and summed per day.
A position's daily fee yield is proportional to this x its own L per dollar, which depends only on its range,
so the ratio between pools at the same range is the ratio of these numbers.
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone

import os
R = os.environ["RPC"]
BLOCKS_PER_DAY = int(os.environ["BPD"])
SWAP = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
POOLS = {os.environ["NAME"]: (os.environ["POOL"], 0.0005)}
WETH_IS_0 = os.environ["WETH0"] == "1"
STEP = int(os.environ.get("STEP", "2000"))


def rpc(m, p, tries=8):
    import time
    for i in range(tries):
        try:
            return _rpc(m, p)
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)


def _rpc(m, p):
    req = urllib.request.Request(R, json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                 {"content-type": "application/json", "user-agent": "fetch"})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    if "error" in d:
        raise RuntimeError(d["error"])
    return d["result"]


def s256(h):
    v = int(h, 16)
    return v - (1 << 256) if v >= 1 << 255 else v


def check_tokens(addr):
    t0 = rpc("eth_call", [{"to": addr, "data": "0x0dfe1681"}, "latest"])[-40:]
    t1 = rpc("eth_call", [{"to": addr, "data": "0xd21220a7"}, "latest"])[-40:]
    fee = int(rpc("eth_call", [{"to": addr, "data": "0xddca3f43"}, "latest"]), 16)
    return t0, t1, fee


head = int(rpc("eth_blockNumber", []), 16)
head_ts = int(rpc("eth_getBlockByNumber", [hex(head), False])["timestamp"], 16)
for days_ago in [3, 60, 200]:
    import datetime as _d
    b1 = head - days_ago * BLOCKS_PER_DAY
    b0 = b1 - BLOCKS_PER_DAY
    row = []
    for name, (addr, fee) in POOLS.items():
        growth_usd, vol_usd, n = 0.0, 0.0, 0
        for a in range(b0, b1, STEP):
            logs = rpc("eth_getLogs", [{"address": addr, "topics": [SWAP], "fromBlock": hex(a), "toBlock": hex(min(a + STEP - 1, b1))}])
            for lg in logs:
                d = lg["data"][2:]
                w = [d[i:i + 64] for i in range(0, len(d), 64)]
                a0, a1 = s256(w[0]), s256(w[1])
                sqrtp = int(w[2], 16) / 2 ** 96
                liq = int(w[3], 16)
                if not WETH_IS_0:                      # token0 USDC: swap roles so a0 is WETH
                    a0, a1 = a1, a0
                price = (sqrtp ** 2) * 1e12 if WETH_IS_0 else 1e12 / (sqrtp ** 2)
                if liq == 0:
                    continue
                in_usd = a0 / 1e18 * price if a0 > 0 else a1 / 1e6
                vol_usd += in_usd
                # fee growth per unit of L, in USD per 1e12 L (scaled for readability)
                growth_usd += in_usd * fee / liq * 1e12
                n += 1
        row.append((name, n, round(vol_usd / 1e6, 2), round(growth_usd, 4)))
    ts = datetime.fromtimestamp(head_ts - days_ago * 86400, timezone.utc).date()
    print(ts, row)
