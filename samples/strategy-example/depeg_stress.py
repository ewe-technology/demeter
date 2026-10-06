"""
Test 5 of preregistration.py: what a depeg of the sleeve asset costs the yield layer, for the shocks of DEPEG_SHOCKS
(wstETH -5%, cbBTC -3% against its peg, each held 7 or 30 days). No pass or fail: it sizes the risk.

Two details the preregistration left open, fixed here before the first run:
  * shape: the sleeve's value drops by the discount at 00:00 of the start day, stays there N days, then recovers
    linearly to the peg over another N days
  * when: every day of SHORT at 00:00 with the gate open (the sleeve held) is tried as a start, as long as the shock
    ends inside the period; the worst and the median are reported. A shock only costs money when the gate trades
    during it: an exit sells the sleeve at the discount, an entry buys it cheap.

Versions as in yield_layer.combine, one tranche at 00:00, no gas: C (ETH as wstETH, so only the wstETH shock applies;
BTC is WBTC spot) and D +/- 0.5% (ETH in the wstETH/WETH LP, BTC in the WBTC/cbBTC LP from CBBTC_CLEAN). A depegging
LP side is valued as if the position were all in the cheap asset, which a +/- 0.5% range is once the price leaves it.
The exit pays its usual swap cost only; a thin pool during a real depeg would cost more.

Run from samples/strategy-example after yield_layer.py --sleeves:
  PYTHONPATH=../.. python depeg_stress.py
"""
import multiprocessing
import os

import pandas as pd

import preregistration as prereg
import spot_robustness as sr
from cost_matrix import changes
from sleeve_sim import simulate
from spot_btc_eth_gate import load_prices
from yield_layer import CBBTC_CLEAN, SHORT, index_on, load_sleeve, wsteth_ratio

RESULT_DIR = "result/depeg"
WORKERS = 4
G = {}  # filled in main before the pool forks


def shock_path(index: pd.DatetimeIndex, start: pd.Timestamp, discount: float, days: int) -> pd.Series:
    """Multiplier on the sleeve's value: 1 - discount for `days`, then a linear way back to 1 over `days` more."""
    m = pd.Series(1.0, index=index)
    held_to, back_at = start + pd.Timedelta(days=days), start + pd.Timedelta(days=2 * days)
    m[(index >= start) & (index < held_to)] = 1 - discount
    ramp = (index >= held_to) & (index < back_at)
    m[ramp] = 1 - discount * (1 - (index[ramp] - held_to) / (back_at - held_to))
    return m


def run(job):
    version, sleeve, discount, days, start = job
    values, cost = G["versions"][version]
    column = "eth" if sleeve == "wsteth" else "btc"
    lo, hi = SHORT
    if start is not None:
        values = values.copy()
        values[column] = values[column] * shock_path(values.index, start, discount, days)
    nav, trades, _ = simulate(G["w"], values, start=lo, cost_bps=cost, cash_cost_bps=0.5)
    nav = nav[nav.index < hi]
    st = sr.stats(nav, lo, hi)
    return {"version": version, "sleeve": sleeve, "discount": discount, "days": days, "start": start,
            "total": st["total"], "maxDD": st["maxDD"], "trades": trades}


def main():
    os.makedirs(RESULT_DIR, exist_ok=True)
    prices, _, _ = load_prices()
    hours = prices.index
    w = sr.gate(prices)
    park, _ = load_sleeve("park_usdc")
    cash = index_on(park["nav"], hours, SHORT[0])
    eth_lp, _ = load_sleeve("wsteth_lp0.005")
    btc_lp, _ = load_sleeve("cbbtc_lp0.005")
    eth, btc = prices["eth"], prices["btc"]
    G.update(w=changes(w.loc[SHORT[0]:]), versions={
        "C": (pd.DataFrame({"eth": eth * wsteth_ratio(hours, "causal"), "btc": btc, "cash": cash}, index=hours),
              {"eth": 11, "btc": 10}),
        "D +/-0.5%": (pd.DataFrame({"eth": eth * index_on(eth_lp["nav"], hours, SHORT[0]),
                                    "btc": btc * index_on(btc_lp["nav"], hours, CBBTC_CLEAN), "cash": cash},
                                   index=hours), {"eth": 11, "btc": 11}),
    })
    held = w[(w.index.hour == 0) & (w["eth"] > 0)].index  # 00:00 with the sleeves held
    jobs = [(v, None, 0.0, 0, None) for v in G["versions"]]
    for sleeve, discount, days in prereg.DEPEG_SHOCKS:
        first = pd.Timestamp(SHORT[0] if sleeve == "wsteth" else CBBTC_CLEAN)
        starts = held[(held >= first) & (held + pd.Timedelta(days=2 * days) <= pd.Timestamp(SHORT[1]))]
        for version in G["versions"]:
            if sleeve == "cbbtc" and version == "C":
                continue  # C holds BTC as WBTC spot, no cbBTC
            jobs += [(version, sleeve, discount, days, s) for s in starts]
    print(f"{len(jobs)} runs", flush=True)
    with multiprocessing.Pool(WORKERS) as pool:
        rows = pool.map(run, jobs, chunksize=8)
    table = pd.DataFrame(rows)
    table.to_csv(f"{RESULT_DIR}/runs.csv", index=False)

    base = table[table["start"].isna()].set_index("version")
    shocked = table[table["start"].notna()].copy()
    shocked["pt lost"] = [100 * (base.at[r.version, "total"] - r.total) for r in shocked.itertuples()]
    shocked["maxDD pt worse"] = [100 * (base.at[r.version, "maxDD"] - r.maxDD) for r in shocked.itertuples()]
    out = []
    for (version, sleeve, discount, days), g in shocked.groupby(["version", "sleeve", "discount", "days"]):
        worst = g.loc[g["pt lost"].idxmax()]
        out.append({"version": version, "shock": f"{sleeve} -{discount:.0%} for {days}d", "starts": len(g),
                    "pt lost worst": worst["pt lost"], "worst start": worst["start"].date(),
                    "pt lost median": g["pt lost"].median(), "starts losing > 0.1 pt": (g["pt lost"] > 0.1).mean(),
                    "maxDD pt worse, worst": g["maxDD pt worse"].max()})
    summary = pd.DataFrame(out)
    summary.to_csv(f"{RESULT_DIR}/summary.csv", index=False)
    pd.set_option("display.width", 250)
    print("unshocked, SHORT:", {v: f"{base.at[v, 'total']:+.1%} / {base.at[v, 'maxDD']:+.1%}" for v in base.index})
    print(summary.to_string(index=False, float_format="{:.2f}".format))
    print("DEPEG_DONE")


if __name__ == "__main__":
    main()
