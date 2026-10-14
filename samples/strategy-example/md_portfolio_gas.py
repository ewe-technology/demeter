"""
md_portfolio.py's books with one gas price for every year (default 3 gwei, the GAS_GWEI of 2025 and 2026) instead of
GAS_GWEI's 40 / 30 / 15 / 3 for 2022 / 2023 / 2024 / 2025+. Asked for on 2026-10-14, descriptive. The ETH price of
each action stays the one at the time.

  maker-defense  gas is subtracted afterwards from the recorded actions, so it is recomputed from actions_<run>.csv:
                 net(flat) = net + gas(yearly) - gas(flat). gas(yearly) must match the run's own gas.
  BTC half g     its nav files keep no action log, so the three slices (00 / 08 / 16 UTC, $50k / 3) are rerun with
                 the flat gas price into their own folder (the gate cache is copied there). Since 2025 both prices
                 are 3 gwei, so net(flat) - net(yearly) must stay flat from 2025-01-01 on.
  C, C+g, C+g+def (H45, references)  defensive_eth.py's books with cost_matrix's flat gwei, and the BTC half above.
                 The same books at yearly gwei must equal nav_h45.csv.

Run from samples/strategy-example on the strategy host, after md_portfolio.py:
  PYTHONPATH=../.. python md_portfolio_gas.py --runs --workers 2
  PYTHONPATH=../.. python md_portfolio_gas.py --combine
"""
import argparse
import glob
import json
import multiprocessing
import os
import shutil

import pandas as pd

import candidate_vs_c as cvc
import cost_matrix as cm
import defensive_eth as de
import md_portfolio as mp
import pool_lp_batch as batch
import yield_layer as yl
from spot_btc_eth_gate import load_prices, stats
from tri_btc_eth_gate import GAS_GWEI, GAS_UNITS

YEARLY = dict(GAS_GWEI)
OUT = f"{mp.RESULT_DIR}/gwei-flat"


def btc_dir(gwei: float) -> str:
    return f"{OUT}/btc-g-gwei{gwei:g}"


def run_btc(gwei: float, workers: int):
    rdir = btc_dir(gwei)
    os.makedirs(rdir, exist_ok=True)
    for f in glob.glob(f"{batch.RESULT_DIR}/gate_99ac_ema100*.csv"):
        shutil.copy(f, rdir)
    for y in range(2018, 2031):
        GAS_GWEI[y] = gwei  # the dict pool_lp_batch.run reads; the workers fork after
    batch.RESULT_DIR = rdir
    batch.BAR = "1h"
    batch.eth_daily()
    for h in cvc.SLICES[3]:
        batch.gate("99ac", 100, h)
    jobs = [(cvc.demeter_cfg(100_000, 3, h), cvc.START, cvc.END) for h in cvc.SLICES[3]]
    jobs = [j for j in jobs if not os.path.exists(cvc.nav_file(j[0], cvc.START))]
    print(f"{len(jobs)} BTC slices at {gwei:g} gwei", flush=True)
    with multiprocessing.get_context("fork").Pool(workers, maxtasksperchild=1) as pool:
        rows = pool.starmap(batch.run, jobs, chunksize=1)
    pd.DataFrame(rows).to_csv(f"{rdir}/runs.csv", index=False)
    print(pd.DataFrame(rows)[["version", "net", "gas", "maxDD", "secs"]].to_string(), flush=True)


def btc_half(rdir: str, index: pd.DatetimeIndex) -> pd.Series:
    saved, batch.RESULT_DIR = batch.RESULT_DIR, rdir
    try:
        return cvc.btc_half_g(100_000, 3, index, cvc.START)
    finally:
        batch.RESULT_DIR = saved


def md_gas(actions: pd.DataFrame, eth_usd: pd.Series, gwei_of) -> pd.Series:
    """Cumulative gas in USDC per action timestamp, as maker_defense_h38.gas_usd on 0x88e6."""
    units = actions["action"].map(GAS_UNITS).fillna(0.0).to_numpy()
    px = eth_usd.reindex(actions["t"].dt.normalize(), method="ffill").to_numpy()
    usd = units * actions["t"].dt.year.map(gwei_of).to_numpy() * 1e-9 * px
    return pd.Series(usd, index=actions["t"]).groupby(level=0).sum().cumsum()


def md_flat(version: str, book: int, gwei: float, eth_usd: pd.Series) -> tuple[pd.Series, dict]:
    name = mp.run_name(version, book)
    nav = pd.read_csv(f"{mp.RESULT_DIR}/nav_{name}.csv", index_col=0, parse_dates=True)["net"]
    act = pd.read_csv(f"{mp.RESULT_DIR}/actions_{name}.csv", parse_dates=["t"])
    run = pd.read_csv(f"{mp.RESULT_DIR}/run_{name}.csv").iloc[0]
    old = md_gas(act, eth_usd, lambda y: YEARLY.get(y, YEARLY[2025]))
    new = md_gas(act, eth_usd, lambda y: gwei)
    assert abs(old.iloc[-1] / book - run["gas"]) < 1e-9, (name, old.iloc[-1] / book, run["gas"])
    diff = (old - new).reindex(nav.index, method="ffill").fillna(0.0)
    return (nav + diff) / book, {"gas_yearly": old.iloc[-1] / book, "gas_flat": new.iloc[-1] / book}


def h45_books(gwei: float | None, btc_g: pd.Series) -> dict:
    """defensive_eth.books() with one gas price (None = yearly) and the given BTC half."""
    prices, _, _ = load_prices()
    park, park_events = yl.load_sleeve("park_usdc", yl.HOLDOUT_TAG)
    cash = yl.index_on(park["nav"], prices.index, yl.FULL[0])
    ratio = yl.wsteth_ratio(prices.index, "causal").bfill()
    cm.G.update(eth=prices["eth"], gwei=gwei)
    eth_values = pd.DataFrame({"eth": prices["eth"] * ratio, "cash": cash})
    btc_values = pd.DataFrame({"btc": prices["btc"], "cash": cash})
    gate = cvc.gate_share(prices.index, 3)
    w_def = 0.5 * gate + 0.5 * de.fp_share(prices.index)
    eth_c = cvc.half_sim("eth", gate, eth_values, de.LO, de.HI, de.BOOK, park_events)[0]
    eth_d = cvc.half_sim("eth", w_def, eth_values, de.LO, de.HI, de.BOOK, park_events)[0]
    btc_c = cvc.half_sim("btc", gate, btc_values, de.LO, de.HI, de.BOOK, park_events)[0]
    g = btc_g.reindex(eth_c.index)
    return {"C": 0.5 * eth_c + 0.5 * btc_c, "C+g": 0.5 * eth_c + 0.5 * g, "C+g+def": 0.5 * eth_d + 0.5 * g}


def combine(gwei: float):
    navs = pd.read_csv(f"{mp.RESULT_DIR}/navs.csv", index_col=0, parse_dates=True)
    idx = navs.index
    eth_usd = batch.eth_daily()
    btc_old = btc_half(batch.RESULT_DIR, idx)
    assert float((btc_old - navs["BTC half g ($50k)"]).abs().max()) < 1e-12
    btc_new = btc_half(btc_dir(gwei), idx)
    gap = btc_new - btc_old
    after = gap.loc["2025-01-01":]
    print(f"BTC half: gap at 2025-01-01 {after.iloc[0]:.6f}, range after {after.max() - after.min():.2e}")
    ref = pd.read_csv(mp.H45_NAV, index_col=0, parse_dates=True)
    check = h45_books(None, btc_old)
    for k in check:
        print(f"H45 {k} at yearly gwei vs nav_h45: max abs diff "
              f"{float((check[k] - ref[k].reindex(check[k].index)).abs().max()):.2e}")
    out, gas = {"BTC half g ($50k)": btc_new}, {}
    for v in mp.VERSIONS:
        for b in mp.BOOKS:
            nav, g = md_flat(v, b, gwei, eth_usd)
            out[f"md {v} (${b // 1000}k)"] = nav.reindex(idx).ffill()
            gas[mp.run_name(v, b)] = g
    for i, v in enumerate(mp.VERSIONS, 1):
        out[f"P{i} = BTC g + md {v}"] = 0.5 * btc_new + 0.5 * out[f"md {v} ($50k)"]
    for k, s in h45_books(gwei, btc_new).items():
        out[f"{k} (H45)"] = s.reindex(idx)
    out["hold ETH"] = navs["hold ETH"]
    flat = pd.DataFrame(out)
    assert not flat.isna().any().any(), flat.isna().sum()
    years = [y0[:4] for y0, _ in cvc.years(mp.LO, mp.HI)]
    rows = []
    for k, s in flat.items():
        st = stats(s, mp.LO, mp.HI)
        per = {y: stats(s, f"{y}-01-01", min(f"{int(y) + 1}-01-01", mp.HI)) for y in years}
        rows.append({"book": k, "total": st["total"], "maxDD": st["maxDD"],
                     **{y: per[y]["total"] for y in years}, **{f"dd{y}": per[y]["maxDD"] for y in years}})
    t = pd.DataFrame(rows)
    tag = f"gwei{gwei:g}"
    flat.to_csv(f"{OUT}/navs_{tag}.csv")
    t.to_csv(f"{OUT}/combine_{tag}.csv", index=False)
    with open(f"{OUT}/gas_{tag}.json", "w") as fh:
        json.dump({"md": gas, "btc_gap_end": float(gap.iloc[-1])}, fh, indent=1)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(t[["book", "total", "maxDD", *years]].to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print(pd.DataFrame(gas).T.to_string(float_format=lambda x: f"{x:.4f}"))
    print(f"BTC half: flat gas adds {gap.iloc[-1]:+.4f} of its $50k by the end")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--runs", action="store_true")
    a.add_argument("--combine", action="store_true")
    a.add_argument("--gwei", type=float, default=3.0)
    a.add_argument("--workers", type=int, default=2)
    a = a.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.runs:
        run_btc(a.gwei, a.workers)
    if a.combine:
        combine(a.gwei)


if __name__ == "__main__":
    main()
