"""
Tests 6 and 7 of preregistration.py, with the cost model of cost_matrix.py:

  --d     D (ETH in the wstETH/WETH LP, BTC in the WBTC/cbBTC LP, idle USDC parked) against C, over SHORT and the
          2026 holdout, judged by preregistration.d_holdout_verdict on the holdout. Each LP sleeve pays gas like the
          parking sleeve: entering, leaving, growing, shrinking and every re-centre while it is held. In SHORT, BTC is
          held spot before CBBTC_CLEAN, but its gas is still charged as an LP there, so D at a capital with gas is a
          little too low in SHORT; the holdout is not affected.
  --park  C with the idle share split into a parking sleeve and plain USDC by the rules of PARK_RULES, judged by
          preregistration.park_verdict. "every change" is C as cost_matrix runs it and must reproduce its numbers.

Both need yield_layer.py --sleeves --holdout first (the sleeves on to 2026-09-30).

Run from samples/strategy-example:
  PYTHONPATH=../.. python holdout_extra.py --d
  PYTHONPATH=../.. python holdout_extra.py --park
"""
import argparse
import multiprocessing
import os

import pandas as pd

import cost_matrix as cm
import preregistration as prereg
import spot_robustness as sr
from ensemble_gate import ensemble_weights
from sleeve_sim import simulate
from spot_btc_eth_gate import load_prices
from yield_layer import CBBTC_CLEAN, FULL, HOLDOUT_TAG, SHORT, index_on, load_sleeve, wsteth_ratio

RESULT_DIR = "result/holdout-extra"
PERIODS = {"short": SHORT, "holdout": prereg.HOLDOUT}
G = cm.G  # cost_matrix.gas_fn reads the ETH price and the gwei from here


def capital_label(capital):
    return "no gas" if capital is None else f"${capital:,}"


def gate(period, n, offset):
    lo, _ = PERIODS[period]
    hours = tuple((h + offset) % 24 for h in range(0, 24, 24 // n))
    return ensemble_weights(G["prices"], hours, (100,)).loc[lo:]  # sliced first: keeps the state at lo


def finish(nav, paid, period):
    lo, hi = PERIODS[period]
    nav = nav[nav.index < hi]
    st = sr.stats(nav, lo, hi)
    return {"total": st["total"], "maxDD": st["maxDD"], "gas $": paid["gas"], "swap $": paid["swap"]}


def run_d(job):
    period, n, offset, version, capital = job
    scale = 0.0 if capital is None else 100_000 / capital
    lp_gas = cm.gas_fn(scale, cm.PARK_UNITS) if scale else None
    if version == "C":
        values, cost, lp = G["C"], {"eth": 11, "btc": 10}, {"cash": G["park_events"]}
        gas = {"eth": cm.gas_fn(scale, 2 * cm.SWAP), "btc": cm.gas_fn(scale, cm.SWAP), "cash": lp_gas}
    else:
        values, events = G["D"][version]
        cost, lp = {"eth": 11, "btc": 11}, {"eth": events[0], "btc": events[1], "cash": G["park_events"]}
        gas = {"eth": lp_gas, "btc": lp_gas, "cash": lp_gas}
    nav, _, paid = simulate(cm.changes(gate(period, n, offset)), values, start=PERIODS[period][0], cost_bps=cost,
                            cash_cost_bps=0.5, gas=gas if scale else None, lp=lp, resize="split")
    return {"period": period, "version": version, "capital": capital_label(capital), "tranches": n,
            "offset": offset, **finish(nav, paid, period)}


def park_share(idle: pd.Series, rule: str) -> pd.Series:
    full = idle >= 1 - 1e-9
    if rule == "every change":
        return idle
    if rule == "fully out only":
        return full.astype(float)
    return full * 1.0 + (~full & (idle >= 0.5 - 1e-9)) * 0.5  # whole halves


def run_park(job):
    period, n, offset, rule, capital = job
    scale = 0.0 if capital is None else 100_000 / capital
    w = gate(period, n, offset)
    idle = (1 - w["eth"] - w["btc"]).round(9)
    w = w.assign(park=park_share(idle, rule))
    gas = {"eth": cm.gas_fn(scale, 2 * cm.SWAP), "btc": cm.gas_fn(scale, cm.SWAP),
           "park": cm.gas_fn(scale, cm.PARK_UNITS)} if scale else None
    nav, _, paid = simulate(cm.changes(w), G["P"], start=PERIODS[period][0],
                            cost_bps={"eth": 11, "btc": 10, "park": 0.5}, gas=gas, lp={"park": G["park_events"]},
                            resize="split")
    return {"period": period, "rule": rule, "capital": capital_label(capital), "tranches": n, "offset": offset,
            **finish(nav, paid, period)}


def gaps(table, key, ref, cols=("capital", "tranches")):
    """Median over offsets of each `key` value minus `ref`, in pt, per period and cols."""
    rows = []
    for (period, *rest), g in table.groupby(["period", *cols], sort=False):
        base = g[g[key] == ref].set_index("offset")
        for name, part in g[g[key] != ref].groupby(key, sort=False):
            d = 100 * (part.set_index("offset")["total"] - base["total"])
            dd = 100 * (part.set_index("offset")["maxDD"] - base["maxDD"])
            rows.append({"period": period, **dict(zip(cols, rest)), key: name, f"vs {ref} pt med": d.median(),
                         "min": d.min(), "max": d.max(), "maxDD pt med": dd.median(),
                         f"{key} total med": part["total"].median(), f"{ref} total med": base["total"].median()})
    return pd.DataFrame(rows)


def setup():
    prices, _, _ = load_prices()
    hours = prices.index
    park, park_events = load_sleeve("park_usdc", HOLDOUT_TAG)
    cash = index_on(park["nav"], hours, FULL[0])
    eth = prices["eth"] * wsteth_ratio(hours, "causal")
    G.update(gwei=None, btc_direct=False, prices=prices, eth=prices["eth"], park_events=park_events,
             C=pd.DataFrame({"eth": eth, "btc": prices["btc"], "cash": cash}, index=hours),
             P=pd.DataFrame({"eth": eth, "btc": prices["btc"], "park": cash, "cash": 1.0}, index=hours))
    return prices, hours, cash


def main_d():
    prices, hours, cash = setup()
    G["D"] = {}
    for width in prereg.D_WIDTHS:
        eth_lp, ev_eth = load_sleeve(f"wsteth_lp{width:g}", HOLDOUT_TAG)
        btc_lp, ev_btc = load_sleeve(f"cbbtc_lp{width:g}", HOLDOUT_TAG)
        values = pd.DataFrame({"eth": prices["eth"] * index_on(eth_lp["nav"], hours, SHORT[0]),
                               "btc": prices["btc"] * index_on(btc_lp["nav"], hours, CBBTC_CLEAN), "cash": cash},
                              index=hours)
        G["D"][f"D +/-{width:.1%}"] = (values, (ev_eth, ev_btc))
    jobs = [(p, n, o, v, c) for p in PERIODS for n in prereg.D_TRANCHES for o in range(24 // n)
            for v in ["C", *G["D"]] for c in prereg.D_CAPITALS]
    print(f"{len(jobs)} runs", flush=True)
    with multiprocessing.Pool(cm.WORKERS) as pool:
        table = pd.DataFrame(pool.map(run_d, jobs, chunksize=4))
    table.to_csv(f"{RESULT_DIR}/d_runs.csv", index=False)
    one = table[(table["period"] == "short") & (table["tranches"] == 1) & (table["offset"] == 0)
                & (table["capital"] == "no gas")]
    print("check, SHORT, one tranche, 00:00, no gas (yield_layer --combine: C +108.6%, D +/-0.5% +117.1%):")
    print(one[["version", "total", "maxDD"]].to_string(index=False))
    summary = gaps(table, "version", "C")
    summary.to_csv(f"{RESULT_DIR}/d_summary.csv", index=False)
    pd.set_option("display.width", 250)
    print(summary.round(3).to_string(index=False))
    holdout = table[table["period"] == "holdout"].drop(columns="period")
    print(f"\n== preregistered verdict, D +/-0.5% beats C in the holdout: {prereg.d_holdout_verdict(holdout)} ==")
    print("D_HOLDOUT_DONE")


def main_park():
    setup()
    jobs = [(p, n, o, r, c) for p in PERIODS for n in cm.TRANCHES for o in range(24 // n) for r in prereg.PARK_RULES
            for c in cm.CAPITALS]
    print(f"{len(jobs)} runs", flush=True)
    with multiprocessing.Pool(cm.WORKERS) as pool:
        table = pd.DataFrame(pool.map(run_park, jobs, chunksize=4))
    table.to_csv(f"{RESULT_DIR}/park_runs.csv", index=False)
    # "every change" must be C of cost_matrix, offset by offset
    for period, path in (("short", f"{cm.RESULT_DIR}/runs.csv"), ("holdout", f"{cm.RESULT_DIR}/runs_holdout.csv")):
        ref = pd.read_csv(path)
        ref = ref[(ref["version"] == "C on-chain") & ref["period"].str.startswith(PERIODS[period][0])]
        mine = table[(table["period"] == period) & (table["rule"] == "every change")]
        both = mine.merge(ref, on=["capital", "tranches", "offset"], suffixes=("", " ref"))
        gap = (both["total"] - both["total ref"]).abs().max()
        print(f"check {period}: {len(both)} runs matched, max |total gap| {gap:.2e}")
    summary = gaps(table, "rule", "every change")
    gas = table.groupby(["period", "rule", "capital", "tranches"], sort=False)["gas $"].median().rename("gas $ med")
    summary = summary.merge(gas.reset_index(), on=["period", "rule", "capital", "tranches"], how="left")
    summary.to_csv(f"{RESULT_DIR}/park_summary.csv", index=False)
    pd.set_option("display.width", 250)
    print(summary.round(3).to_string(index=False))
    short = table[table["period"] == "short"].drop(columns="period")
    holdout = table[table["period"] == "holdout"].drop(columns="period")
    print(f"\n== preregistered verdict, parking rule to use: {prereg.park_verdict(short, holdout)} ==")
    print("PARK_DONE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--d", action="store_true")
    parser.add_argument("--park", action="store_true")
    cli = parser.parse_args()
    os.makedirs(RESULT_DIR, exist_ok=True)
    if cli.d:
        main_d()
    if cli.park:
        main_park()
