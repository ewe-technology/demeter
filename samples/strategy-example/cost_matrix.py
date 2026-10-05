"""
A / C x 1 / 3 / 6 tranches, with every on-chain cost each trade really needs. The yield layer (yield_layer.py) and
the split close hours (ensemble_gate.py) each held up on their own, the second only with a flat 10 bps per trade;
this is whether they still pay together, and at what size.

Tranches: the base rule (BTC above its EMA100 -> 50% ETH + 50% BTC, otherwise USDC) at n close hours spaced 24/n
apart, the portfolio holding their average. Every hour set is shifted by 0 .. 24/n - 1 hours and all offsets are
kept, so a design is a range of outcomes, not one lucky hour. Tranches that change in the same hour are one trade.

Versions:
  A exchange  ETH, BTC, USDC, 10 bps a trade, no gas (the ensemble_gate numbers)
  A on-chain  the same in a wallet: every ETH or BTC buy or sell is one swap's gas
  C on-chain  ETH held as wstETH (11 bps, two swaps' gas), BTC as WBTC (one swap), idle USDC in the USDC/USDT
              parking LP (0.5 bps; entering 580k gas, leaving 400k, adding to it 580k, taking part out 400k, and
              every re-centre of the parking sleeve while it holds anything 850k), wstETH at the causal ratio

Gas: the yearly gwei of tri_btc_eth_gate and the ETH price; capital $10k / $100k / $1M, or none at all. "No gas" is
a low-cost case only, not an L2: an L2 has its own pools, volume and liquidity. Periods: FULL (the wstETH pool barely
traded before mid-2023, so C there is more a valuation than a trade that could have been done) and SHORT.

Run from samples/strategy-example after yield_layer.py --sleeves (the parking LP) and the spot price cache:
  PYTHONPATH=../.. python cost_matrix.py
  PYTHONPATH=../.. python cost_matrix.py --gwei 10   # one gas price for every year, writes *_gwei10.csv
"""
import argparse
import multiprocessing
import os

import pandas as pd

import spot_robustness as sr
from ensemble_gate import ensemble_weights
from sleeve_sim import GAS_EVENT_UNITS, simulate
from spot_btc_eth_gate import load_prices
from tri_btc_eth_gate import GAS_GWEI
from yield_layer import FULL, SHORT, index_on, load_sleeve, wsteth_ratio

RESULT_DIR = "result/cost-matrix"
TRANCHES = (1, 3, 6)
CAPITALS = (None, 10_000, 100_000, 1_000_000)
SWAP = GAS_EVENT_UNITS["swap"]
PARK_UNITS = {"enter": GAS_EVENT_UNITS["enter"], "exit": GAS_EVENT_UNITS["exit"], "grow": GAS_EVENT_UNITS["enter"],
              "shrink": GAS_EVENT_UNITS["exit"], "recentre": GAS_EVENT_UNITS["recentre"]}
WORKERS = 4

G = {}  # filled in main before the pool forks


def gas_fn(scale: float, units):
    """USD gas of one event: units is a number (every kind costs the same) or {kind: units}."""
    eth_usd = G["eth"]

    flat = G.get("gwei")

    def gas(kind: str, t: pd.Timestamp) -> float:
        u = units if isinstance(units, (int, float)) else units[kind]
        gwei = flat if flat is not None else GAS_GWEI.get(t.year, min(GAS_GWEI.values()))
        return scale * u * gwei * 1e-9 * float(eth_usd.asof(t))

    return gas


def changes(w: pd.DataFrame) -> pd.DataFrame:
    """Only the rows where the target moves: the same trades as the hourly frame, far fewer rows to loop over."""
    moved = w.diff().abs().sum(axis=1) > 0
    moved.iloc[0] = True
    return w[moved]


def run(job):
    period, n, offset, version, capital = job
    lo, hi = period
    hours = tuple((h + offset) % 24 for h in range(0, 24, 24 // n))
    w = changes(ensemble_weights(G["prices"], hours, (100,)).loc[lo:])  # sliced first: keeps the state at lo
    scale = 0.0 if capital is None else 100_000 / capital
    if version == "A exchange":
        values, cost, cash_bps, gas, lp = G["A"], 10, 0.0, None, None
    elif version == "A on-chain":
        values, cost, cash_bps, lp = G["A"], 10, 0.0, None
        gas = {"eth": gas_fn(scale, SWAP), "btc": gas_fn(scale, SWAP)} if scale else None
    else:
        values, cost, cash_bps, lp = G["C"], {"eth": 11, "btc": 10}, 0.5, {"cash": G["park_events"]}
        gas = {"eth": gas_fn(scale, 2 * SWAP), "btc": gas_fn(scale, SWAP), "cash": gas_fn(scale, PARK_UNITS)} \
            if scale else None
    nav, trades, paid = simulate(w, values, start=lo, cost_bps=cost, cash_cost_bps=cash_bps, gas=gas, lp=lp,
                                 resize="split")
    nav = nav[nav.index < hi]
    st = sr.stats(nav, lo, hi)
    return {"period": f"{lo}~{hi}", "tranches": n, "offset": offset, "version": version,
            "capital": "no gas" if capital is None else f"${capital:,}", "total": st["total"], "annual": st["annual"],
            "maxDD": st["maxDD"], "calmar": st["calmar"], "trades": trades, "swap $": paid["swap"],
            "gas $": paid["gas"]}


def main(gwei: float | None = None):
    os.makedirs(RESULT_DIR, exist_ok=True)
    tag = "" if gwei is None else f"_gwei{gwei:g}"
    prices, _, _ = load_prices()
    hours = prices.index
    park, park_events = load_sleeve("park_usdc")
    G.update(gwei=gwei, prices=prices, eth=prices["eth"], park_events=park_events,
             A=pd.DataFrame({"eth": prices["eth"], "btc": prices["btc"], "cash": 1.0}, index=hours),
             C=pd.DataFrame({"eth": prices["eth"] * wsteth_ratio(hours, "causal"), "btc": prices["btc"],
                             "cash": index_on(park["nav"], hours, FULL[0])}, index=hours))
    jobs = []
    for period in (FULL, SHORT):
        for n in TRANCHES:
            for offset in range(24 // n):
                jobs.append((period, n, offset, "A exchange", None))
                for capital in CAPITALS:
                    if capital is not None:
                        jobs.append((period, n, offset, "A on-chain", capital))
                    jobs.append((period, n, offset, "C on-chain", capital))
    print(f"{len(jobs)} runs", flush=True)
    with multiprocessing.Pool(WORKERS) as pool:
        rows = pool.map(run, jobs, chunksize=4)
    table = pd.DataFrame(rows)
    table.to_csv(f"{RESULT_DIR}/runs{tag}.csv", index=False)

    # check: one tranche at offset 0 must give the yield_layer --combine numbers for A and for C without gas
    one = table[(table["tranches"] == 1) & (table["offset"] == 0) & (table["capital"] == "no gas")]
    print("\none tranche, offset 0, no gas (A must match yield_layer 'A base', C its 'C wstETH + park'):")
    print(one[["period", "version", "total", "maxDD", "trades"]].to_string(index=False))

    key = ["period", "capital", "tranches", "offset"]
    a_chain = table[table["version"] == "A on-chain"].set_index(key)
    a_exch = table[table["version"] == "A exchange"].set_index(["period", "tranches", "offset"])
    out = []
    for (period, capital, version, n), g in table.groupby(["period", "capital", "version", "tranches"], sort=False):
        row = {"period": period, "capital": capital, "version": version, "tranches": n, "offsets": len(g)}
        for c in ("total", "maxDD", "calmar"):
            q = g[c].quantile([0, 0.5, 1]).to_numpy()
            row[f"{c} min"], row[f"{c} med"], row[f"{c} max"] = q
        row["trades med"] = g["trades"].median()
        row["gas $ med"] = g["gas $"].median()
        row["swap $ med"] = g["swap $"].median()
        # paired by offset: C against A on-chain at the same capital (A exchange when there is no gas),
        # A on-chain against A exchange
        if version != "A exchange":
            if version == "A on-chain" or capital == "no gas":
                ref = a_exch.loc[[(period, n, o) for o in g["offset"]], "total"].to_numpy()
            else:
                ref = a_chain.loc[[(period, capital, n, o) for o in g["offset"]], "total"].to_numpy()
            d = pd.Series(100 * (g["total"].to_numpy() - ref))
            row["vs A pt min"], row["vs A pt med"], row["vs A pt max"] = d.min(), d.median(), d.max()
        out.append(row)
    summary = pd.DataFrame(out)
    summary.to_csv(f"{RESULT_DIR}/summary{tag}.csv", index=False)

    shown = summary.copy()
    for c in [c for c in shown.columns if c.split(" ")[0] in ("total", "maxDD")]:
        shown[c] = shown[c].map(lambda v: f"{v:+.0%}")
    for c in [c for c in shown.columns if c.startswith("calmar")]:
        shown[c] = shown[c].round(2)
    for c in [c for c in shown.columns if c.startswith("vs A")]:
        shown[c] = shown[c].map(lambda v: "" if pd.isna(v) else f"{v:+.1f}")
    for c in ("gas $ med", "swap $ med"):
        shown[c] = shown[c].round(0).astype(int)
    pd.set_option("display.width", 320)
    for (period, capital), part in shown.groupby(["period", "capital"], sort=False):
        print(f"\n== {period}, {capital} (A on-chain vs A exchange; C vs A on-chain, or A exchange without gas) ==")
        print(part.drop(columns=["period", "capital"]).to_string(index=False))
    print("MATRIX_DONE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gwei", type=float, default=None,
                        help="one gas price for every year instead of GAS_GWEI, for the sensitivity runs")
    main(parser.parse_args().gwei)
