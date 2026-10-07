"""
Test 4 of preregistration.py: the same rule and parameters on Arbitrum, never re-picked there, over ARBITRUM_PERIOD,
with Ethereum run through the same cost model over the same period so the two compare item by item.

The preregistration fixed the pools, the period, the versions (A exchange, A on-chain, C on-chain), the tranches,
the capitals, swaps priced from the pool's own liquidity, and one bridge each way. These details it left open are
fixed here before the first run:
  * gate and valuation: the Ethereum-derived prices of spot_btc_eth_gate on both chains, so the chains differ only in
    execution (swap cost, gas, the wstETH ratio and the parking LP), never in the signal
  * a swap of notional N through a pool costs its fee plus N / (L * sqrt(P)) in raw token1 units: the average price
    impact inside one constant-liquidity v3 range, with L and P the pool's state after its last trade before the swap
  * routes: ETH is USDC -> WETH; wstETH is USDC -> WETH -> wstETH; BTC takes the cheapest of USDC -> WETH -> WBTC and
    the direct BTC/stablecoin routes of the chain; parking swaps half its notional through USDC/USDT
  * gas on Arbitrum: $0.05 a swap, $0.20 an LP action (enter, leave, grow, shrink, re-centre); "arbitrum gas x10" runs
    ten times that. Ethereum uses cost_matrix's gas units and yearly gwei (3 for 2026)
  * bridge, Arbitrum only: $10 in at the start and $10 out at the end, taken out of the net value
  * "no gas" means no gas and no bridge; its price impact is sized at $100k
A exchange keeps a flat 10 bps a trade and no gas on both chains. Verdict: preregistration.arbitrum_verdict.

Added after the first run, shown only: the linear impact breaks down when a pool has almost no liquidity at the
price (the Arbitrum wstETH/WETH pool had 22 hours where $100k would cost over 500 bps, up to 16,000), since a real
swap moves into the next range or an aggregator routes around it. --cap 100 caps each hop's impact at 100 bps.

Run from samples/strategy-example (the spot price cache and yield_layer.py --sleeves --holdout must exist):
  PYTHONPATH=../.. python arbitrum_check.py
  PYTHONPATH=../.. python arbitrum_check.py --cap 100
"""
import argparse
import glob
import multiprocessing
import os
from datetime import date

import numpy as np
import pandas as pd

import cost_matrix as cm
import preregistration as prereg
import spot_robustness as sr
from ensemble_gate import ensemble_weights
from sleeve_sim import simulate
from spot_btc_eth_gate import load_prices
from tri_btc_eth_gate import PARK_MAX_DEPEG, PARK_RANGE, usdc, usdt
from yield_layer import (DATA_DIR, HOLDOUT_END, HOLDOUT_TAG, Sleeve, index_on, load_sleeve, pool_dir, run_sleeve,
                         wsteth_ratio)

RESULT_DIR = "result/arbitrum"
PERIOD = prereg.ARBITRUM_PERIOD
ARB_SWAP_USD, ARB_LP_USD = 0.05, 0.20
BRIDGE_USD = 10.0
NO_GAS_SIZE = 100_000
HOP_CAP_BPS = None  # set by --cap before the pool forks


class Pool:
    def __init__(self, address: str, dec0: int, dec1: int, fee_bps: float, token1_weth: bool):
        self.address, self.dec0, self.dec1, self.fee, self.token1_weth = address, dec0, dec1, fee_bps, token1_weth


CHAINS = {
    "ethereum": {
        "eth": Pool("0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", 6, 18, 5, True),  # USDC / WETH
        "ratio": Pool("0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0", 8, 18, 5, True),  # WBTC / WETH
        "park": Pool("0x3416cF6C708Da44DB2624D63ea0AAef7113527C6", 6, 6, 1, False),  # USDC / USDT
        "wsteth": Pool("0x109830a1AAaD605BbF02a9dFA7B0B92EC2FB7dAa", 18, 18, 1, True),  # wstETH / WETH
        "btc_direct": [["wbtc_usdc_30"], ["park", "wbtc_usdt_5"]],
        "wbtc_usdc_30": Pool("0x99ac8cA7087fA4A2A1FB6357269965A2014ABc35", 8, 6, 30, False),
        "wbtc_usdt_5": Pool("0x56534741CD8B152df6d48AdF7ac51f75169A83b2", 8, 6, 5, False),
    },
    "arbitrum": {
        "eth": Pool(prereg.ARBITRUM_POOLS["eth"], 18, 6, 5, False),  # WETH / USDC
        "ratio": Pool(prereg.ARBITRUM_POOLS["ratio"], 8, 18, 5, True),  # WBTC / WETH
        "park": Pool(prereg.ARBITRUM_POOLS["park"], 6, 6, 1, False),  # USDC / USDT
        "wsteth": Pool(prereg.ARBITRUM_POOLS["wsteth"], 18, 18, 1, True),  # wstETH / WETH
        "btc_direct": [["wbtc_usdc_5"]],
        "wbtc_usdc_5": Pool(prereg.LP_TESTS[1].pool, 8, 6, 5, False),  # WBTC / USDC 0.05%
    },
}
G = cm.G  # cost_matrix.gas_fn reads the ETH price and the gwei from here


def pool_state(pool: Pool, hours: pd.DatetimeIndex) -> pd.DataFrame:
    """sqrt(price) and active liquidity after the last trade before each hour, both in raw units."""
    files = sorted(glob.glob(f"{DATA_DIR}/{pool_dir(pool.address)}/*.minute.csv"))
    cols = ["timestamp", "closeTick", "currentLiquidity"]
    df = pd.concat((pd.read_csv(f, usecols=cols) for f in files), ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"]) + pd.Timedelta(minutes=1)  # known from the next minute on
    for c in cols[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    df = df.dropna().set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    state = df.reindex(hours.union(df.index)).ffill().reindex(hours)
    return pd.DataFrame({"sqrtp": 1.0001 ** (state["closeTick"] / 2), "L": state["currentLiquidity"]}, index=hours)


def hop_bps(chain: str, name: str, t: pd.Timestamp, usd: float) -> float:
    pool, (sqrtp, liq) = CHAINS[chain][name], G["state"][(chain, name)][t]
    if not liq > 0:
        return np.inf
    raw1 = usd / (G["eth_px"][t] if pool.token1_weth else 1.0) * 10 ** pool.dec1
    impact = 1e4 * raw1 / (liq * sqrtp)
    return pool.fee + (impact if HOP_CAP_BPS is None else min(impact, HOP_CAP_BPS))


def size_of(capital) -> float:
    """Real dollars per simulated dollar: simulate runs on $100k."""
    return (NO_GAS_SIZE if capital is None else capital) / 100_000


def costs(chain: str, capital):
    size = size_of(capital)

    def eth(t, m):
        return hop_bps(chain, "eth", t, m * size)

    def wst(t, m):
        return hop_bps(chain, "eth", t, m * size) + hop_bps(chain, "wsteth", t, m * size)

    def btc(t, m):
        routes = [["eth", "ratio"], *CHAINS[chain]["btc_direct"]]
        return min(sum(hop_bps(chain, p, t, m * size) for p in r) for r in routes)

    def cash(t, m):
        return hop_bps(chain, "park", t, m * size / 2) / 2  # half the parked notional is swapped

    return eth, wst, btc, cash


def arb_gas(scale: float, usd: float):
    return lambda kind, t: scale * usd


def run(job):
    chain_label, n, offset, version, capital = job
    chain = "arbitrum" if chain_label.startswith("arbitrum") else "ethereum"
    gas_mult = 10 if chain_label.endswith("x10") else 1
    lo, hi = PERIOD
    hours = tuple((h + offset) % 24 for h in range(0, 24, 24 // n))
    w = cm.changes(ensemble_weights(G["prices"], hours, (100,)).loc[lo:])
    scale = 0.0 if capital is None else 100_000 / capital
    eth, wst, btc, cash = costs(chain, capital)
    gas = None
    if version == "A exchange":
        values, cost, cash_cost, lp = G["A"], 10, 0.0, None
    elif version == "A on-chain":
        values, cost, cash_cost, lp = G["A"], {"eth": eth, "btc": btc}, 0.0, None
        if scale and chain == "ethereum":
            gas = {"eth": cm.gas_fn(scale, cm.SWAP), "btc": cm.gas_fn(scale, cm.SWAP)}
        elif scale:
            gas = {"eth": arb_gas(scale, ARB_SWAP_USD * gas_mult), "btc": arb_gas(scale, ARB_SWAP_USD * gas_mult)}
    else:
        values, cost, cash_cost = G["C"][chain], {"eth": wst, "btc": btc}, cash
        lp = {"cash": G["park_events"][chain]}
        if scale and chain == "ethereum":
            gas = {"eth": cm.gas_fn(scale, 2 * cm.SWAP), "btc": cm.gas_fn(scale, cm.SWAP),
                   "cash": cm.gas_fn(scale, cm.PARK_UNITS)}
        elif scale:
            gas = {"eth": arb_gas(scale, 2 * ARB_SWAP_USD * gas_mult), "btc": arb_gas(scale, ARB_SWAP_USD * gas_mult),
                   "cash": arb_gas(scale, ARB_LP_USD * gas_mult)}
    nav, trades, paid = simulate(w, values, start=lo, cost_bps=cost, cash_cost_bps=cash_cost, gas=gas, lp=lp,
                                 resize="split")
    nav = nav[nav.index < hi]
    bridge = BRIDGE_USD * scale if chain == "arbitrum" and version != "A exchange" else 0.0
    if bridge:
        nav = nav - bridge
        nav.iloc[-1] -= bridge
    st = sr.stats(nav, lo, hi)
    size = size_of(capital)
    return {"chain": chain_label, "version": version, "capital": "no gas" if capital is None else f"${capital:,}",
            "tranches": n, "offset": offset, "total": st["total"], "maxDD": st["maxDD"], "trades": trades,
            "swap $": paid["swap"] * size, "gas $": paid["gas"] * size, "bridge $": 2 * BRIDGE_USD if bridge else 0.0}


def main():
    os.makedirs(RESULT_DIR, exist_ok=True)
    tag = "" if HOP_CAP_BPS is None else f"_cap{HOP_CAP_BPS:g}"
    prices, _, _ = load_prices()
    hours = prices.index
    lo, hi = PERIOD
    # the Arbitrum parking LP, run like the Ethereum one (same range and depeg guard), from three weeks before
    arb_park = Sleeve("park_usdc_arb", pool_dir(prereg.ARBITRUM_POOLS["park"]), usdc, usdt, usdc, date(2024, 11, 1),
                      HOLDOUT_END, PARK_RANGE, 100_000, PARK_MAX_DEPEG, chain="arbitrum")
    name, out, events, secs = run_sleeve(arb_park, "1h", arb_park.start, arb_park.end)
    out.to_csv(f"{RESULT_DIR}/sleeve_{name}.csv")
    print(f"Arbitrum parking LP: {out['nav'].iloc[-1] - 1:+.2%} from {out.index[0]} to {out.index[-1]}, "
          f"{len(events)} re-centres, {secs:.0f}s")
    eth_park, eth_events = load_sleeve("park_usdc", HOLDOUT_TAG)
    parks = {"ethereum": (eth_park, eth_events), "arbitrum": (out, pd.DatetimeIndex(events))}

    period_hours = hours[(hours >= lo) & (hours < hi)]
    state = {}
    for chain, pools in CHAINS.items():
        for key, pool in pools.items():
            if isinstance(pool, Pool):
                s = pool_state(pool, period_hours)
                state[(chain, key)] = dict(zip(period_hours, zip(s["sqrtp"].to_numpy(), s["L"].to_numpy())))
    ratios = {"ethereum": wsteth_ratio(hours, "causal"),
              "arbitrum": wsteth_ratio(hours, "causal", prereg.ARBITRUM_POOLS["wsteth"])}
    G.update(gwei=None, btc_direct=False, prices=prices, eth=prices["eth"], state=state,
             eth_px=dict(zip(hours, prices["eth"].to_numpy())),
             park_events={c: ev for c, (_, ev) in parks.items()},
             A=pd.DataFrame({"eth": prices["eth"], "btc": prices["btc"], "cash": 1.0}, index=hours),
             C={c: pd.DataFrame({"eth": prices["eth"] * ratios[c], "btc": prices["btc"],
                                 "cash": index_on(parks[c][0]["nav"], hours, lo)}, index=hours) for c in CHAINS})

    # what one $100k swap costs through each pool, sampled daily over the period
    rows = []
    for (chain, key) in state:
        bps = pd.Series([hop_bps(chain, key, t, 100_000) for t in period_hours[::24]])
        rows.append({"chain": chain, "pool": key, "fee bps": CHAINS[chain][key].fee, "$100k median bps": bps.median(),
                     "p90": bps.quantile(0.9)})
    impact = pd.DataFrame(rows)
    impact.to_csv(f"{RESULT_DIR}/impact{tag}.csv", index=False)
    print("\n== cost of one $100k swap (fee + price impact) ==")
    print(impact.round(2).to_string(index=False))
    for chain in CHAINS:
        r = ratios[chain][(hours >= lo) & (hours < hi)]
        c = G["C"][chain]["cash"][(hours >= lo) & (hours < hi)]
        print(f"{chain}: wstETH ratio {r.iloc[-1] / r.iloc[0] - 1:+.2%}, parking {c.iloc[-1] / c.iloc[0] - 1:+.2%} "
              f"over the period")

    jobs = []
    for chain in ("ethereum", "arbitrum", "arbitrum gas x10"):
        for n in cm.TRANCHES:
            for offset in range(24 // n):
                jobs.append((chain, n, offset, "A exchange", None))
                for capital in cm.CAPITALS:
                    if capital is not None:
                        jobs.append((chain, n, offset, "A on-chain", capital))
                    jobs.append((chain, n, offset, "C on-chain", capital))
    print(f"\n{len(jobs)} runs", flush=True)
    with multiprocessing.Pool(cm.WORKERS) as pool:
        table = pd.DataFrame(pool.map(run, jobs, chunksize=4))
    table.to_csv(f"{RESULT_DIR}/runs{tag}.csv", index=False)

    out_rows = []
    for (chain, capital, version, n), g in table.groupby(["chain", "capital", "version", "tranches"], sort=False):
        ref = table[(table["chain"] == chain) & (table["version"] == "A exchange") & (table["tranches"] == n)]
        d = 100 * (g.set_index("offset")["total"] - ref.set_index("offset")["total"])
        out_rows.append({"chain": chain, "capital": capital, "version": version, "tranches": n,
                         "total med": g["total"].median(), "total min": g["total"].min(),
                         "total max": g["total"].max(), "maxDD med": g["maxDD"].median(),
                         "vs A exchange pt med": d.median(), "swap $ med": g["swap $"].median(),
                         "gas $ med": g["gas $"].median(), "bridge $": g["bridge $"].max()})
    summary = pd.DataFrame(out_rows)
    summary.to_csv(f"{RESULT_DIR}/summary{tag}.csv", index=False)
    pd.set_option("display.width", 250)
    print(summary.round(3).to_string(index=False))
    arb = table[table["chain"] == "arbitrum"].drop(columns="chain")
    label = "preregistered verdict" if HOP_CAP_BPS is None else "shown only, impact capped"
    print(f"\n== {label}, {prereg.ARBITRUM_CLAIM}: {prereg.arbitrum_verdict(arb)} ==")
    print("ARBITRUM_DONE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cap", type=float, default=None, help="cap each hop's price impact at this many bps")
    HOP_CAP_BPS = parser.parse_args().cap
    main()
