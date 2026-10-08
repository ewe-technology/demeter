"""
H15 and H16 of reports/single_pool_loop.md (registered 2026-10-08, after H13). 0x99ac, BTC gate EMA100 from
pool_lp_batch.gate (EMA started on the pool's first day, 2021-05-05), costs as pool_lp_batch.py.

H15  g_down in 2021, the one stretch no test has used. g_down, gd_half and g_spot100 at $100k (2021 gas: 50 gwei).
       primary    2021-08-16 .. 2021-12-31 (the EMA has about 100 days behind it from here)
       secondary  2021-06-01 .. 2021-12-31 (the EMA is still warming up in June-July), listed only
     Verdict: g_down - g_spot100 > 0 over the primary window agrees with H4b; <= 0 contradicts it. One short window,
     so it can only agree or contradict, not confirm.
H16  $10k at today's gas: g_down and g_spot100 at $10k with 3 gwei in every year, the 16 windows of H12.
     Verdict: g_down passes if (g_down - g_spot100) meets H2's 1-3 (median > 0, >= 75% of windows > 0, median > 0 in
     both halves).

Run from samples/strategy-example:
  PYTHONPATH=../.. python pool_lp_unseen.py h15
  PYTHONPATH=../.. python pool_lp_unseen.py h16
"""
import glob
import multiprocessing
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

import pool_lp_batch as batch
import pool_lp_gdown  # noqa: F401  registers HalfGated (gd_half) on pool_lp_batch

g = dict(gated=True, on="spot")
LADDER = dict(off="range", off_width=0.40, off_up=0.01)
H15 = [batch.cfg("99ac", "g_down", **LADDER, **g),
       batch.cfg("99ac", "gd_half", off="half", off_width=0.40, off_up=0.01, **g),
       batch.cfg("99ac", "g_spot100", **g)]
H15_WINDOWS = [(date(2021, 8, 16), date(2021, 12, 31)), (date(2021, 6, 1), date(2021, 12, 31))]
H16 = [batch.cfg("99ac", "g_down_10k_3gw", initial=10_000, **LADDER, **g),
       batch.cfg("99ac", "g_spot100_10k_3gw", initial=10_000, **g)]


def eth_daily_from_2021() -> pd.Series:
    """88e6 daily ETH close from the pool's first day: the shared cache starts in 2022, which left 2021 gas unpriced."""
    path = f"{batch.RESULT_DIR}/eth_usd_daily_2021.csv"
    if not os.path.exists(path):
        p = batch.POOLS["88e6"]
        files = sorted(glob.glob(f"../real-data/{p.address}/*.minute.csv"))
        df = pd.concat((pd.read_csv(f, usecols=["timestamp", "closeTick"]) for f in files), ignore_index=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        tick = pd.to_numeric(df.set_index("timestamp").sort_index()["closeTick"], errors="coerce").dropna()
        (1e12 / np.power(1.0001, tick)).resample("1D").last().ffill().rename("eth_usd").to_csv(path)
    return pd.read_csv(path, index_col=0, parse_dates=True)["eth_usd"]


def main():
    which = sys.argv[1]
    os.makedirs(batch.RESULT_DIR, exist_ok=True)
    eth_daily_from_2021()
    batch.eth_daily = eth_daily_from_2021  # read by pool_lp_batch.run; the workers fork after
    batch.gate("99ac", 100)
    if which == "h15":
        tasks = [(c, s, e) for c in H15 for s, e in H15_WINDOWS]
    else:
        batch.GAS_GWEI = {y: 3 for y in range(2021, 2027)}  # read by pool_lp_batch.run; the workers fork after
        tasks = [(c, s, batch.window_end(s)) for c in H16 for s in batch.window_starts("99ac")]
    with multiprocessing.Pool(3, maxtasksperchild=1) as pool:
        rows = pool.starmap(batch.run, tasks, chunksize=1)
    t = pd.DataFrame(rows)
    t.to_csv(f"{batch.RESULT_DIR}/windows_{which}.csv", index=False)
    n = t.pivot(index="start", columns="version", values="net").sort_index()
    pd.set_option("display.width", 250)
    print(t.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    if which == "h15":
        for v in ("g_down", "gd_half"):
            print(v, "- g_spot100:", (n[v] - n["g_spot100"]).round(4).to_dict())
    else:
        x = n["g_down_10k_3gw"] - n["g_spot100_10k_3gw"]
        c = batch.checks(x)
        print("g_down_10k_3gw - control: median %.4f, positive %d/16, %s" % (
            x.median(), (x > 0).sum(), "PASS" if all(c.values()) else c))


if __name__ == "__main__":
    main()
