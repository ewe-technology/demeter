"""Section 7 of reports/c1_drawdown_2026-10-21_report.md. Exploration, listed only: a book with share f in C1 (or the live gate, or dd30) and the rest in stablecoin,
from the saved hourly continuous books (linear in f: the impact of a smaller C1 book would be lower)."""
import numpy as np
import pandas as pd
R = "result/gate-lp-options/nav"  # run from samples/strategy-example on the strategy host: python c1_scale_explore.py
def nav(tag):
    return pd.read_parquet(f"{R}/{tag}_continuous_2022-01-01.parquet")["usd"]
def mix(s, f, rebal, bps=50e-4):
    r = (s / s.shift(1)).fillna(1.0).to_numpy()
    idx = s.index
    month = idx.to_period("M")
    newm = np.r_[True, month[1:] != month[:-1]]
    a, c = f, 1 - f
    out = np.empty(len(r))
    for i in range(len(r)):
        a *= r[i]
        if rebal and newm[i] and i > 0 and idx[i].hour == 0:
            tot = a + c
            tr = abs(a - f * tot)
            tot -= tr * bps
            a, c = f * tot, (1 - f) * tot
        out[i] = a + c
    o = pd.Series(out, index=idx)
    return float(o.iloc[-1] - 1), float((o / o.cummax() - 1).min())
for pk in ("99ac", "9db9"):
    c1, ctl, dd30 = nav(f"H51C1_{pk}_ladder_n1_h00_100k"), nav(f"H51C1_{pk}_ctl_n1_h00_100k"), nav(f"H59_{pk}_dd30")
    c1, ctl, dd30 = (x / x.iloc[0] for x in (c1, ctl, dd30))
    base_ctl = mix(ctl, 1.0, False)
    base_dd30 = mix(dd30, 1.0, False)
    print(f"\n{pk}: live gate 100% {base_ctl[0]:+.1%} / {base_ctl[1]:.1%}; dd30 100% {base_dd30[0]:+.1%} / {base_dd30[1]:.1%}")
    for rebal in (False, True):
        print(f"  {'monthly rebalance (50 bps)' if rebal else 'split once, no rebalance'}:")
        for f in (0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 1.0):
            a = mix(c1, f, rebal); b = mix(ctl, f, rebal); d = mix(dd30, f, rebal)
            ok = a[1] >= base_ctl[1] - 0.02 and a[0] > base_dd30[0]
            print(f"    f {f:.2f}  C1 {a[0]:+7.1%} {a[1]:6.1%} (gap {100*(a[1]-base_ctl[1]):+5.1f} pt)  | live gate x f {b[0]:+7.1%} {b[1]:6.1%}  | dd30 x f {d[0]:+7.1%} {d[1]:6.1%}  {'<- within 2 pt and above dd30' if ok else ''}")
