"""Section 9 of reports/c1_drawdown_2026-10-21_report.md. Run from samples/strategy-example on the strategy host,
with lp_attribution.py next to it: python c1_feeiso_explore.py
Exploration, listed only: C1 with a share q of every hour's LP fees moved into a stablecoin reserve that never
re-enters (not bought into WBTC on gate-on, not placed in ladders). Linear on the saved hourly books: the active book
keeps C1's hourly return, minus the fees it hands over; fees from lp_attribution.decompose (the real fee residual)."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, ".")
from lp_attribution import decompose, segments
R = "result/gate-lp-options/nav"
MODES = {"on": ["spot", 1.0], "off": ["range", 1.40, 1.01]}
def load(tag, modes=None):
    df = pd.read_parquet(f"{R}/{tag}_continuous_2022-01-01.parquet")
    nav = df["usd"].to_numpy()
    if modes is None:
        return df.index, nav, None
    ev = pd.read_csv(f"{R}/events_{tag}_continuous_2022-01-01.csv")
    price = df["price"].astype(float).ffill().to_numpy()
    _, fe, _, _, _ = decompose(nav, price, segments(df.index, nav, price, ev, modes))
    return df.index, nav, fe
def stats(x):
    x = np.asarray(x)
    return float(x[-1] / x[0] - 1), float((x / np.maximum.accumulate(x) - 1).min())
for pk in ("99ac", "9db9"):
    idx, nav, fe = load(f"H51C1_{pk}_ladder_n1_h00_100k", MODES)
    _, ctl, _ = load(f"H51C1_{pk}_ctl_n1_h00_100k")
    _, dd30, _ = load(f"H59_{pk}_dd30")
    c, d = stats(ctl), stats(dd30)
    print(f"\n{pk}: live gate {c[0]:+.1%} / {c[1]:.1%}; dd30 {d[0]:+.1%} / {d[1]:.1%}; C1 {stats(nav)[0]:+.1%} / {stats(nav)[1]:.1%}")
    for q in (0.25, 0.5, 0.75, 1.0):
        a, res = nav[0], 0.0
        tot = np.empty(len(nav)); reserve = np.empty(len(nav))
        tot[0], reserve[0] = a, 0.0
        for i in range(1, len(nav)):
            scale = a / nav[i - 1]
            take = q * max(fe[i], 0.0) * scale
            a = a * nav[i] / nav[i - 1] - take
            res += take
            tot[i], reserve[i] = a + res, res
        t_, m_ = stats(tot)
        i_peak = int(np.argmax(tot[: int(np.argmin(tot / np.maximum.accumulate(tot)))+1]))
        print(f"  q {q:.2f}: {t_:+7.1%} / {m_:6.1%} (gap {100*(m_-c[1]):+5.1f} pt, vs dd30 {100*(t_-d[0]):+6.1f} pt); "
              f"reserve at end {reserve[-1]/tot[-1]:.0%} of book, at the MDD peak {idx[i_peak].date()} {reserve[i_peak]/tot[i_peak]:.0%}")
