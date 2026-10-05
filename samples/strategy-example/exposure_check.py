"""
Is the volatility cap of report section 12.5 better than simply holding less? The cap lowered the drawdown from
-36% to -26% / -28%, but it also keeps less in ETH and BTC on average, and less exposure alone lowers drawdowns.

Every cap is paired with a fixed cut that holds the same time-average share of the net value in ETH and BTC over
2022-2025, measured on what is actually held (drift included), not on the target shares:

  cap X%, eth only     ETH share x min(1, X / ETH 30-day vol), traded when a share drifts 10% (section 12.5)
  cap X%, both coins   the same on both coins
  fixed, eth only      the base gate with the ETH share cut by a constant, the rest in USDC
  fixed, both coins    the base gate with both shares cut by the same constant

The constant is found by bisection on the 2022-2025 hourly run and is a diagnostic only, never a parameter to trade
with. Drawdowns are read on minute prices (spot_robustness --minute), the rest on both. 2026 is shown, not used.

Run from samples/strategy-example after spot_btc_eth_gate.py has built the price cache:
  PYTHONPATH=../.. python exposure_check.py
"""
import os

import pandas as pd

import spot_robustness as sr
from spot_btc_eth_gate import HOLDOUT, IN_SAMPLE, load_prices, stats

RESULT_DIR = "result/exposure"
TARGETS = (0.4, 0.6)
COINS = {"eth only": ("eth",), "both coins": ("eth", "btc")}


def in_sample(series: pd.Series) -> pd.Series:
    return series[(series.index >= IN_SAMPLE[0]) & (series.index < IN_SAMPLE[1])]


def mean_exposure(weights, prices, threshold) -> float:
    _, _, share = sr.simulate(weights, prices, threshold=threshold, exposure=True)
    return float(in_sample(share).mean())


def fixed(base: pd.DataFrame, cut: float, coins) -> pd.DataFrame:
    out = base.copy()
    for coin in coins:
        out[coin] = base[coin] * cut
    return out


def match(base, prices, coins, target: float) -> float:
    """The constant cut of `coins` whose run holds `target` of the net value in crypto on average."""
    lo, hi = 0.0, 1.0
    for _ in range(30):
        mid = (lo + hi) / 2
        if mean_exposure(fixed(base, mid, coins), prices, None) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def underwater_days(nav: pd.Series) -> float:
    """The longest stretch, in days, from a peak of the daily net value to the first day back at or above it."""
    daily = nav.resample("D").last().dropna()
    peak = daily.cummax()
    longest, since = 0.0, None
    for t, v, p in zip(daily.index, daily.to_numpy(), peak.to_numpy()):
        if v < p:
            since = since or t
        elif since is not None:
            longest, since = max(longest, (t - since).days + 1), None
    if since is not None:  # still under at the end
        longest = max(longest, (daily.index[-1] - since).days + 1)
    return float(longest)


def measures(nav: pd.Series) -> dict:
    ins = in_sample(nav)
    s = stats(nav, *IN_SAMPLE)
    hold = stats(nav, HOLDOUT, "2100-01-01")
    month = ins.resample("ME").last().pct_change().dropna()
    quarter = ins.resample("QE").last().pct_change().dropna()
    drop = nav.loc[sr.DROP[0]:sr.DROP[1]]
    return {"total": s["total"], "annual": s["annual"], "maxDD": s["maxDD"], "calmar": s["calmar"],
            "worst month": month.min(), "worst quarter": quarter.min(), "underwater days": underwater_days(ins),
            "drop window": drop.iloc[-1] / drop.iloc[0] - 1, "2026": hold["total"], "2026 maxDD": hold["maxDD"]}


def main():
    os.makedirs(RESULT_DIR, exist_ok=True)
    prices, _, _ = load_prices()
    minute = sr.load_minute_prices(prices)
    base = sr.gate(prices)
    rules = {"base": (base, None, "")}
    for target in TARGETS:
        for label, coins in COINS.items():
            cap = sr.vol_scale_each(prices, base, target, coins)
            name = f"cap {target:.0%}, {label}"
            rules[name] = (cap, 0.10, name)
            cut = match(base, prices, coins, mean_exposure(cap, prices, 0.10))
            rules[f"fixed {cut:.3f}, {label} (= {name})"] = (fixed(base, cut, coins), None, name)
    rows = []
    for name, (w, thr, pair) in rules.items():
        for bar, p in (("1h", prices), ("1min", minute)):
            nav, trades, share = sr.simulate(w, p, threshold=thr, exposure=True)
            ins = in_sample(share)
            on = ins[ins > 0.01]
            rows.append({"run": name, "pair": pair, "bar": bar, "mean exposure": ins.mean(),
                         "exposure while in": on.mean(), **measures(nav), "trades": trades})
            print(f"{name} [{bar}] done", flush=True)
    table = pd.DataFrame(rows)
    table.to_csv(f"{RESULT_DIR}/exposure.csv", index=False)

    pct = ["mean exposure", "exposure while in", "total", "annual", "maxDD", "worst month", "worst quarter",
           "drop window", "2026", "2026 maxDD"]
    shown = table.copy()
    for c in pct:
        shown[c] = shown[c].map(lambda v: f"{v:+.1%}")
    shown["calmar"] = shown["calmar"].round(2)
    pd.set_option("display.width", 300)
    for bar in ("1h", "1min"):
        print(f"\n== {bar} bars, 2022-2025 (2026 shown only) ==")
        print(shown[shown["bar"] == bar].drop(columns=["bar"]).to_string(index=False))
    # each cap minus its matched fixed cut, minute bars
    m = table[table["bar"] == "1min"].set_index("run")
    diff = []
    for name in [r for r in rules if r.startswith("cap")]:
        ctrl = next(r for r in rules if r.startswith("fixed") and rules[r][2] == name)
        a, b = m.loc[name], m.loc[ctrl]
        diff.append({"cap": name, "control": ctrl, "total pt": 100 * (a["total"] - b["total"]),
                     "maxDD pt": 100 * (a["maxDD"] - b["maxDD"]), "calmar": a["calmar"] - b["calmar"],
                     "worst month pt": 100 * (a["worst month"] - b["worst month"]),
                     "worst quarter pt": 100 * (a["worst quarter"] - b["worst quarter"]),
                     "underwater days": a["underwater days"] - b["underwater days"],
                     "drop window pt": 100 * (a["drop window"] - b["drop window"]),
                     "2026 pt": 100 * (a["2026"] - b["2026"])})
    diff = pd.DataFrame(diff)
    diff.to_csv(f"{RESULT_DIR}/exposure_diff.csv", index=False)
    print("\n== cap minus its exposure-matched fixed cut, minute bars (positive = cap better, except underwater) ==")
    print(diff.round(2).to_string(index=False))
    print("EXPOSURE_DONE")


if __name__ == "__main__":
    main()
