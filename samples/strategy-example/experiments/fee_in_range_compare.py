"""
QUAN-1213: v3.2 with fee_in_range_liquidity off vs on (ENGINE-FEE-IN-RANGE-2026-10-29.md). Prints fees, end value,
LP value, max DD (demeter's and UTC-0 daily %) and fees per year for reinvest off / on.

    python experiments/fee_in_range_compare.py <result dir> [folder suffix, e.g. -rawdepth] [cost tag, default slipdepth]

Cost tag "swap10bp" compares the FLAT_SWAP_COST=1 runs (the validation setting).
"""
import glob
import sys

import pandas as pd

root = sys.argv[1]
suffix = sys.argv[2] if len(sys.argv) > 2 else ""
cost = sys.argv[3] if len(sys.argv) > 3 else "slipdepth"
off = glob.glob(f"{root}/gamma*{cost}{suffix}-100000-*")[0]
on = glob.glob(f"{root}/gamma*{cost}-feeinrange{suffix}-100000-*")[0]


def summary(d):
    s = pd.read_csv(f"{d}/apr_remix_100000_results.csv").set_index("Strategy")
    s.index = ["reinvest" if x.endswith("_reinvest") else "noreinvest" for x in s.index]
    return s


def yearly_fees(d, mode):
    f = pd.read_csv(glob.glob(f"{d}/fees_*_{mode}.csv")[0], parse_dates=["date"]).set_index("date")
    earned = f.collected_quote + f.pending_quote
    ye = earned.groupby(earned.index.year).last()
    return ye.diff().fillna(ye)


def daily_dd(d, mode):
    nv = pd.read_csv(glob.glob(f"{d}/netvalue_*_{mode}.csv")[0], index_col=0, parse_dates=True).net_value.astype(float)
    nv = nv[(nv.index.hour == 0) & (nv.index.minute == 0)]
    return (nv / nv.cummax() - 1).min()


so, sn = summary(off), summary(on)
for mode in ("noreinvest", "reinvest"):
    print(f"== {mode}")
    for col in ("Total Fee", "Total Net Value", "LP Net Value", "Max Draw Down", "Rebalance/Rescale Count"):
        a, b = so.loc[mode, col], sn.loc[mode, col]
        print(f"{col:24s} off {a:14,.2f}  on {b:14,.2f}  diff {b - a:+12,.2f}  ({(b / a - 1) * 100:+.2f}%)")
    print(f"{'daily % max DD':24s} off {daily_dd(off, mode) * 100:.2f}%  on {daily_dd(on, mode) * 100:.2f}%")
    yo, yn = yearly_fees(off, mode), yearly_fees(on, mode)
    for y in yo.index:
        print(f"  fees {y}: off {yo[y]:12,.0f}  on {yn[y]:12,.0f}  ({(yn[y] / yo[y] - 1) * 100:+.2f}%)")
