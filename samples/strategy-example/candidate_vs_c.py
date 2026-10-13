"""
H34 of reports/plan_2026-10-12_two_coin.md (registered 2026-10-13 in 1782fd3, before this code ran): the candidate
against version C, the whole book. Two halves from 2022-01-01 to 2026-09-30, no rebalancing between them; the ETH
half is the same in both versions, so the difference is all in the BTC half.

  C     ETH half: wstETH while on (11 bps, two swaps' gas), parked while off (cost_matrix.py's C costs)
        BTC half: WBTC while on (10 bps, one swap's gas), parked while off
  C+g   ETH half: as C
        BTC half: one continuous Demeter g_down_d1x per slice (H26: re-centred at 00 UTC only), reading the gate and
                  switching at the slice's hour, at 1/n of the half; costs as pool_lp_batch.py

Gate: 99ac's BTC EMA100 (pool_lp_batch.gate(hour=)) for both versions, so they switch at the same hours. n = 1 (00) or
3 (00 / 08 / 16): C's weight is the slices' mean; C+g's BTC half is the mean of n Demeter runs, each paying gas at
its own size. The parking index is 1 before 2022-08-26 (no data), the same as USDC; wstETH's causal ratio is
back-filled before its first value (a valuation, the same in both versions).
Verdict ($100k book, n = 3, each year's gas): (C+g - C) total > 0, > 0 in at least 4 of the 5 calendar years
2022 .. 2026, and C+g's max drawdown (hourly) no more than 2 pt worse than C's. Listed: n = 1, $10k, $1M, the years,
gas and trades, and the BTC halves alone.

Bars: the Demeter runs use hourly bars (pool_lp_batch.BAR = "1h"). The minute-bar runs needed 4 - 5 GB each and were
killed by the OOM killer on the 7.7 GB host (2026-10-13, 0 of 12 done). --check reruns two of H26's windows on hourly
bars first; the hourly runs go ahead only if both are within 2 pt of H26's minute-bar net (fixed before the check).

Run from samples/strategy-example (the spot price cache, yield_layer's park_usdc_to2026, 99ac in ../real-data):
  PYTHONPATH=../.. python candidate_vs_c.py --check                 # hourly against minute bars on H26's windows
  PYTHONPATH=../.. python candidate_vs_c.py --test                  # a 6-week check, into result/candidate-vs-c/test
  PYTHONPATH=../.. python candidate_vs_c.py --runs --workers 2      # the 12 Demeter runs, skips finished ones
  PYTHONPATH=../.. python candidate_vs_c.py --combine
"""
import argparse
import multiprocessing
import os
from datetime import date

import pandas as pd

import cost_matrix as cm
import pool_lp_batch as batch
import pool_lp_robust as robust
import spot_robustness as sr
import yield_layer as yl
from sleeve_sim import GAS_EVENT_UNITS, simulate
from spot_btc_eth_gate import load_prices

RESULT_DIR = "result/candidate-vs-c"
START, END = date(2022, 1, 1), date(2026, 9, 30)
LO, HI = "2022-01-01", "2026-10-01"
BOOKS = (10_000, 100_000, 1_000_000)
JUDGED = (100_000, 3)
SLICES = {1: (0,), 3: (0, 8, 16)}
TAGS = {10_000: "10k", 100_000: "100k", 1_000_000: "1m"}
SWAP = GAS_EVENT_UNITS["swap"]


def demeter_cfg(book: int, n: int, h: int):
    return robust.rcfg(f"gd1x_1h_c{TAGS[book]}_n{n}_h{h:02d}", initial=book / 2 / n, daily_check=True, gate_hour=h,
                       delay=h, **robust.LADDER)


def demeter_cfgs() -> list:
    return [demeter_cfg(b, n, h) for b in BOOKS for n, hours in SLICES.items() for h in hours]


def nav_file(c, start: date) -> str:
    return f"{batch.RESULT_DIR}/nav_99ac_{c.name}_ema{c.ema}_{start}.csv"


def run_demeter(workers: int, start: date = START, end: date = END):
    jobs = [(c, start, end) for c in demeter_cfgs() if not os.path.exists(nav_file(c, start))]
    print(f"{len(jobs)} Demeter runs", flush=True)
    with multiprocessing.Pool(workers, maxtasksperchild=1) as pool:
        rows = pool.starmap(batch.run, jobs, chunksize=1)
    os.makedirs(RESULT_DIR, exist_ok=True)
    pd.DataFrame(rows).to_csv(f"{RESULT_DIR}/demeter_runs{'' if start == START else '_test'}.csv", index=False)


def btc_half_g(book: int, n: int, hours_index: pd.DatetimeIndex, start: date) -> pd.Series:
    """Mean of the n slices' net values, each over its own capital (entry costs included), on hourly bars."""
    parts = []
    for h in SLICES[n]:
        c = demeter_cfg(book, n, h)
        net = pd.read_csv(nav_file(c, start), index_col=0, parse_dates=True)["net"]
        net = net.resample("1h").last().ffill() / c.initial
        parts.append(net.reindex(hours_index, method="ffill"))
    return pd.concat(parts, axis=1).mean(axis=1)


def gate_share(hours_index: pd.DatetimeIndex, n: int) -> pd.Series:
    """The slices' mean of the 99ac gate (1 = on), each slice switching at its own hour."""
    parts = [batch.gate("99ac", 100, h).astype(float).reindex(hours_index, method="ffill").fillna(0.0)
             for h in SLICES[n]]
    return pd.concat(parts, axis=1).mean(axis=1)


def half_sim(sleeve: str, w: pd.Series, values: pd.DataFrame, lo: str, hi: str, book: int, park_events):
    """One half of the book through sleeve_sim with C's costs; returns the net value over its capital."""
    scale = 100_000 / (book / 2)
    units = 2 * SWAP if sleeve == "eth" else SWAP
    gas = {sleeve: cm.gas_fn(scale, units), "cash": cm.gas_fn(scale, cm.PARK_UNITS)}
    weights = cm.changes(pd.DataFrame({sleeve: w}).loc[lo:])
    v = values[(values.index >= lo) & (values.index < hi)]
    nav, trades, paid = simulate(weights, v, start=lo, cost_bps={sleeve: 11 if sleeve == "eth" else 10},
                                 cash_cost_bps=0.5, gas=gas, lp={"cash": park_events}, resize="split")
    return nav / 100_000, trades, paid


def years(lo: str, hi: str) -> list[tuple[str, str]]:
    return [(f"{y}-01-01", min(f"{y + 1}-01-01", hi)) for y in range(int(lo[:4]), int(hi[:4]) + (hi[5:] != "01-01"))]


def row(nav: pd.Series, lo: str, hi: str) -> dict:
    nav = nav[nav.index < hi]
    st = sr.stats(nav, lo, hi)
    out = {"total": st["total"], "maxDD": st["maxDD"]}
    out.update({y0[:4]: sr.stats(nav, y0, y1)["total"] for y0, y1 in years(lo, hi)})
    return out


def combine(lo: str = LO, hi: str = HI, start: date = START, rdir: str = RESULT_DIR):
    os.makedirs(rdir, exist_ok=True)
    prices, _, _ = load_prices()
    park, park_events = yl.load_sleeve("park_usdc", yl.HOLDOUT_TAG)
    cash = yl.index_on(park["nav"], prices.index, yl.FULL[0])
    ratio = yl.wsteth_ratio(prices.index, "causal").bfill()
    cm.G.update(eth=prices["eth"], gwei=None)  # read by cost_matrix.gas_fn
    eth_values = pd.DataFrame({"eth": prices["eth"] * ratio, "cash": cash})
    btc_values = pd.DataFrame({"btc": prices["btc"], "cash": cash})
    rows = []
    for book in BOOKS:
        for n in SLICES:
            w = gate_share(prices.index, n)
            eth_nav, eth_tr, eth_paid = half_sim("eth", w, eth_values, lo, hi, book, park_events)
            btc_c, btc_tr, btc_paid = half_sim("btc", w, btc_values, lo, hi, book, park_events)
            btc_g = btc_half_g(book, n, eth_nav.index, start)
            books = {"C": 0.5 * eth_nav + 0.5 * btc_c, "C+g": 0.5 * eth_nav + 0.5 * btc_g,
                     "BTC half C": btc_c, "BTC half g": btc_g, "ETH half": eth_nav}
            for name, nav in books.items():
                r = {"book_capital": book, "n": n, "version": name, **row(nav, lo, hi)}
                if name == "C":  # gas in USD: each half's paid gas is in units of a $100k book
                    r.update(trades=eth_tr + btc_tr,
                             gas_usd=(eth_paid["gas"] + btc_paid["gas"]) * (book / 2) / 100_000)
                rows.append(r)
    t = pd.DataFrame(rows)
    t.to_csv(f"{rdir}/combine_h34.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(t.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    yrs = [y0[:4] for y0, _ in years(lo, hi)]
    for book in BOOKS:
        for n in SLICES:
            p = t[(t["book_capital"] == book) & (t["n"] == n)].set_index("version")
            a, b = p.loc["C+g"], p.loc["C"]
            diff = {y: a[y] - b[y] for y in yrs}
            need = min(4, len(yrs))
            ok = a["total"] - b["total"] > 0 and sum(v > 0 for v in diff.values()) >= need \
                and a["maxDD"] >= b["maxDD"] - 0.02
            judged = (book, n) == JUDGED
            print(f"H34 ${book:,} n={n}: C+g - C total {a['total'] - b['total']:+.4f}, by year "
                  + " ".join(f"{y} {v:+.3f}" for y, v in diff.items())
                  + f", maxDD C+g {a['maxDD']:+.3f} C {b['maxDD']:+.3f}"
                  + (f" -> {'PASS' if ok else 'fail'}" if judged else " (listed)"))


def check() -> bool:
    """Two of H26's windows (g_down_d1x, $100k) on hourly bars against their minute-bar net values."""
    t = pd.read_csv(f"{batch.RESULT_DIR}/windows_h26.csv")
    ok = True
    for s in (date(2022, 1, 1), date(2024, 7, 1)):
        c = robust.rcfg("g_down_d1x_1hcheck", daily_check=True, **robust.LADDER)
        hourly = batch.run(c, s, batch.window_end(s))["net"]
        minute = float(t[(t["version"] == "g_down_d1x") & (t["start"] == str(s))]["net"].iloc[0])
        gap = hourly - minute
        ok &= abs(gap) < 0.02
        print(f"check {s}: hourly {hourly:+.4f}, minute {minute:+.4f}, gap {gap:+.4f}", flush=True)
    print("CHECK", "OK: within 2 pt" if ok else "FAILED: a gap of 2 pt or more")
    return ok


def test():
    """A 6-week check of the plumbing (2023-01-01 .. 02-15, gate on and off), into result/candidate-vs-c/test."""
    s, e = date(2023, 1, 1), date(2023, 2, 15)
    run_demeter(1, s, e)
    combine("2023-01-01", "2023-02-16", s, f"{RESULT_DIR}/test")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--test", action="store_true")
    a.add_argument("--check", action="store_true")
    a.add_argument("--runs", action="store_true")
    a.add_argument("--combine", action="store_true")
    a.add_argument("--workers", type=int, default=3)
    a = a.parse_args()
    os.makedirs(batch.RESULT_DIR, exist_ok=True)
    batch.BAR = "1h"  # read by pool_lp_batch.run; the workers fork after
    batch.eth_daily()  # fill the caches before the workers read them
    for h in (0, 8, 16):
        batch.gate("99ac", 100, h)
    if a.test:
        test()
        return
    if a.check:
        check()
        return
    if a.runs:
        run_demeter(a.workers)
    if a.combine:
        combine()


if __name__ == "__main__":
    main()
