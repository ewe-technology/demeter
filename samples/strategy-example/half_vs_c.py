"""
H37 of reports/plan_2026-10-14_strategy_exchange.md (registered in ea8fc90, before this code ran): version C with a
half-size g_down in the BTC half, against C, the whole book. Everything else is H34 (candidate_vs_c.py): two halves
from 2022-01-01 to 2026-09-30 with no rebalancing between them, $100k, three slices (00 / 08 / 16 UTC), the gate of
99ac's BTC EMA100 read at each slice's hour, hourly bars, each slice paying gas at its own size.

  C           ETH half: wstETH while on, parked while off; BTC half: WBTC while on, parked while off (as H34)
  C+g-half    BTC half: one continuous Demeter run per slice; while off, half the slice in the ladder
              [p/1.40, p x 1.01], the other half in USDC; every off placement (the switch and each re-centre) first
              sells any WBTC, then places half of what the slice holds (pool_lp_gdown.HalfGated, H13's gd_half)
  C+g-full    H34's candidate, rerun here as the reference

The half ladder is re-centred once a day at the slice's hour (H26), not hourly as in H13.
Verdict (fixed in the plan): (C+g-half - C) total > 0, > 0 in at least 4 of the 5 calendar years 2022 .. 2026 (2026 to
9/30), and C+g-half's max drawdown (hourly) no more than 2 pt worse than C's. C+g-full is listed only.

--check runs the half ladder on two of H26's windows (2022-01, 2024-07, $100k, one slice at 00) on minute and on
hourly bars and reports the gap; it does not gate the main runs (plan section 3.3).

Run from samples/strategy-example:
  PYTHONPATH=../.. python half_vs_c.py --test               # 6 weeks, into result/candidate-vs-c/test_h37
  PYTHONPATH=../.. python half_vs_c.py --runs --workers 1   # the 6 Demeter runs, skips finished ones
  PYTHONPATH=../.. python half_vs_c.py --combine
  PYTHONPATH=../.. python half_vs_c.py --check
"""
import argparse
import multiprocessing
import os
from datetime import date

import pandas as pd

import candidate_vs_c as cvc
import cost_matrix as cm
import pool_lp_batch as batch
import pool_lp_robust as robust
import yield_layer as yl
from pool_lp_gdown import HalfGated
from pool_lp_robust import RobustGated
from spot_btc_eth_gate import load_prices

BOOK, N = 100_000, 3
HALF = dict(off="half", off_width=0.40, off_up=0.01)


class HalfRobust(HalfGated, RobustGated):
    """RobustGated's daily re-centre at the slice's hour, with HalfGated's half-size ladder when off == "half".
    With off == "range" it is RobustGated (H34's candidate)."""


batch.GatedPool = HalfRobust  # pool_lp_batch.run builds the gated strategy from this name; the workers fork after


def cfg(version: str, h: int, initial: float = BOOK / 2 / N):
    if version == "full":
        return cvc.demeter_cfg(BOOK, N, h)
    return robust.rcfg(f"gdh1x_1h_c100k_n{N}_h{h:02d}", initial=initial, daily_check=True, gate_hour=h, delay=h,
                       **HALF)


def nav_file(c, start: date) -> str:
    return f"{batch.RESULT_DIR}/nav_99ac_{c.name}_ema{c.ema}_{start}.csv"


def run_demeter(workers: int, start: date = cvc.START, end: date = cvc.END):
    cfgs = [cfg(v, h) for v in ("half", "full") for h in cvc.SLICES[N]]
    jobs = [(c, start, end) for c in cfgs if not os.path.exists(nav_file(c, start))]
    print(f"{len(jobs)} Demeter runs", flush=True)
    with multiprocessing.Pool(workers, maxtasksperchild=1) as pool:
        rows = pool.starmap(batch.run, jobs, chunksize=1)
    os.makedirs(cvc.RESULT_DIR, exist_ok=True)
    pd.DataFrame(rows).to_csv(f"{cvc.RESULT_DIR}/demeter_runs_h37{'' if start == cvc.START else '_test'}.csv",
                              index=False)


def btc_half(version: str, hours_index: pd.DatetimeIndex, start: date) -> pd.Series:
    """Mean of the slices' net values, each over its own capital (entry costs included), on hourly bars."""
    parts = []
    for h in cvc.SLICES[N]:
        c = cfg(version, h)
        net = pd.read_csv(nav_file(c, start), index_col=0, parse_dates=True)["net"]
        net = net.resample("1h").last().ffill() / c.initial
        parts.append(net.reindex(hours_index, method="ffill"))
    return pd.concat(parts, axis=1).mean(axis=1)


def combine(lo: str = cvc.LO, hi: str = cvc.HI, start: date = cvc.START, rdir: str = cvc.RESULT_DIR):
    os.makedirs(rdir, exist_ok=True)
    prices, _, _ = load_prices()
    park, park_events = yl.load_sleeve("park_usdc", yl.HOLDOUT_TAG)
    cash = yl.index_on(park["nav"], prices.index, yl.FULL[0])
    ratio = yl.wsteth_ratio(prices.index, "causal").bfill()
    cm.G.update(eth=prices["eth"], gwei=None)  # read by cost_matrix.gas_fn
    eth_values = pd.DataFrame({"eth": prices["eth"] * ratio, "cash": cash})
    btc_values = pd.DataFrame({"btc": prices["btc"], "cash": cash})
    w = cvc.gate_share(prices.index, N)
    eth_nav, eth_tr, eth_paid = cvc.half_sim("eth", w, eth_values, lo, hi, BOOK, park_events)
    btc_c, btc_tr, btc_paid = cvc.half_sim("btc", w, btc_values, lo, hi, BOOK, park_events)
    g_half, g_full = btc_half("half", eth_nav.index, start), btc_half("full", eth_nav.index, start)
    books = {"C": 0.5 * eth_nav + 0.5 * btc_c, "C+g-half": 0.5 * eth_nav + 0.5 * g_half,
             "C+g-full": 0.5 * eth_nav + 0.5 * g_full, "BTC half C": btc_c, "BTC half g-half": g_half,
             "BTC half g-full": g_full, "ETH half": eth_nav}
    rows = []
    for name, nav in books.items():
        r = {"version": name, **cvc.row(nav, lo, hi)}
        if name == "C":
            r.update(trades=eth_tr + btc_tr, gas_usd=(eth_paid["gas"] + btc_paid["gas"]) * (BOOK / 2) / 100_000)
        rows.append(r)
    t = pd.DataFrame(rows)
    t.to_csv(f"{rdir}/combine_h37.csv", index=False)
    pd.DataFrame(books).to_csv(f"{rdir}/nav_h37.csv")
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(t.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    yrs = [y0[:4] for y0, _ in cvc.years(lo, hi)]
    p = t.set_index("version")
    for cand, judged in (("C+g-half", True), ("C+g-full", False)):
        a, b = p.loc[cand], p.loc["C"]
        diff = {y: a[y] - b[y] for y in yrs}
        ok = a["total"] - b["total"] > 0 and sum(v > 0 for v in diff.values()) >= min(4, len(yrs)) \
            and a["maxDD"] >= b["maxDD"] - 0.02
        print(f"H37 {cand} - C: total {a['total'] - b['total']:+.4f}, by year "
              + " ".join(f"{y} {v:+.3f}" for y, v in diff.items())
              + f", maxDD {cand} {a['maxDD']:+.3f} C {b['maxDD']:+.3f} (gap {a['maxDD'] - b['maxDD']:+.3f})"
              + (f" -> {'PASS' if ok else 'fail'}" if judged else " (listed)"))


def check():
    """The half ladder on two of H26's windows, minute against hourly bars (one slice at 00, $100k)."""
    rows = []
    for s in (date(2022, 1, 1), date(2024, 7, 1)):
        out = {"start": str(s)}
        for bar in (None, "1h"):
            batch.BAR = bar
            c = robust.rcfg(f"gdh1x_check_{'1h' if bar else '1m'}", daily_check=True, **HALF)
            out["hourly" if bar else "minute"] = batch.run(c, s, batch.window_end(s))["net"]
        out["gap"] = out["hourly"] - out["minute"]
        rows.append(out)
        print(f"check {s}: hourly {out['hourly']:+.4f}, minute {out['minute']:+.4f}, gap {out['gap']:+.4f}",
              flush=True)
    pd.DataFrame(rows).to_csv(f"{cvc.RESULT_DIR}/check_h37.csv", index=False)


def test():
    """A 6-week check of the plumbing (2023-01-01 .. 02-15, gate on and off), into result/candidate-vs-c/test_h37."""
    s, e = date(2023, 1, 1), date(2023, 2, 15)
    run_demeter(1, s, e)
    combine("2023-01-01", "2023-02-16", s, f"{cvc.RESULT_DIR}/test_h37")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--test", action="store_true")
    a.add_argument("--check", action="store_true")
    a.add_argument("--runs", action="store_true")
    a.add_argument("--combine", action="store_true")
    a.add_argument("--workers", type=int, default=1)
    a = a.parse_args()
    os.makedirs(batch.RESULT_DIR, exist_ok=True)
    os.makedirs(cvc.RESULT_DIR, exist_ok=True)
    if a.check:
        check()
        return
    batch.BAR = "1h"  # read by pool_lp_batch.run; the workers fork after
    batch.eth_daily()  # fill the caches before the workers read them
    for h in cvc.SLICES[N]:
        batch.gate("99ac", 100, h)
    if a.test:
        test()
        return
    if a.runs:
        run_demeter(a.workers)
    if a.combine:
        combine()


if __name__ == "__main__":
    main()
