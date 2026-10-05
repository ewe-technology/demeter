"""
Step 2A of reports/next_backtest_plan.md: is "each coin above its own SMA200" (report 12.3) robust, or one lucky
setting? The same checks as report section 12, on the existing BTC/ETH data, always next to the base rule
(BTC above its EMA100 -> 50% ETH + 50% BTC) varied the same way:

  hours      daily close taken at every UTC hour
  ma         SMA and EMA, spans 100-250
  bootstrap  paired stationary bootstrap of daily returns, each-coin rule minus the base rule, 2022-2025

Stop rule fixed in the plan before running: proposal 2 stops here if the rule only works near SMA200, or if the
bootstrap gives it less than a 60% chance of beating the base. 2026 is shown, never used to judge.

Run from samples/strategy-example after spot_btc_eth_gate.py has built the price cache:
  PYTHONPATH=../.. python each_gate_check.py
"""
import os

import numpy as np
import pandas as pd

import spot_robustness as sr
from spot_btc_eth_gate import IN_SAMPLE, load_prices

RESULT_DIR = "result/basket"
EACH = dict(span=200, ma="sma", each=True)
BASE = dict(span=100, ma="ema", each=False)
COLS = ["2022", "2023", "2024", "2025", "total", "maxDD", "calmar", "drop window", "2026", "trades"]


def run(prices, **kw) -> tuple[dict, pd.Series]:
    nav, trades = sr.simulate(sr.gate(prices, **kw), prices)
    return sr.summary("", nav, trades), nav


def hours(prices) -> pd.DataFrame:
    rows = []
    for hour in range(24):
        for rule, kw in (("each sma200", EACH), ("base", BASE)):
            s, _ = run(prices, hour=hour, **kw)
            rows.append({"rule": rule, "hour": hour, **{k: s[k] for k in COLS}})
    return pd.DataFrame(rows)


def ma_grid(prices) -> pd.DataFrame:
    rows = []
    for ma in ("sma", "ema"):
        for span in range(100, 260, 10):
            for rule, each in (("each", True), ("btc gate", False)):
                s, _ = run(prices, span=span, ma=ma, each=each)
                rows.append({"rule": rule, "ma": ma, "span": span, **{k: s[k] for k in COLS}})
    return pd.DataFrame(rows)


def bootstrap(prices, reps=2000, seed=11) -> pd.DataFrame:
    navs = {}
    for name, kw in (("each", EACH), ("base", BASE)):
        _, nav = run(prices, **kw)
        navs[name] = nav[nav.index < IN_SAMPLE[1]]
    daily = pd.DataFrame(navs)
    daily = daily[daily.index.hour == 0].pct_change().dropna().to_numpy()
    rng = np.random.default_rng(seed)
    n = len(daily)
    rows = []
    for block in (20, 60, 120):
        diffs = []
        for _ in range(reps):
            path = np.cumprod(1 + daily[sr.stationary_indices(n, block, rng)], axis=0)
            annual = path[-1] ** (365.25 / n) - 1
            dd = (path / np.maximum.accumulate(path, axis=0) - 1).min(axis=0)
            diffs.append((annual[0] - annual[1], dd[0] - dd[1], annual[0] / -dd[0] - annual[1] / -dd[1]))
        d = np.array(diffs)
        for k, label in enumerate(("annual return diff", "maxDD diff", "calmar diff")):
            q = np.quantile(d[:, k], [0.05, 0.5, 0.95])
            rows.append({"block days": block, "measure": label, "p5": q[0], "median": q[1], "p95": q[2],
                         "P(each better)": float((d[:, k] > 0).mean())})
    return pd.DataFrame(rows)


def pct(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for c in out.columns:
        if c in sr.PCT:
            out[c] = out[c].map(lambda v: f"{v:+.1%}" if pd.notna(v) else "")
    return out.round(2)


if __name__ == "__main__":
    os.makedirs(RESULT_DIR, exist_ok=True)
    prices, _, _ = load_prices()
    pd.set_option("display.width", 250)

    table = hours(prices)
    table.to_csv(f"{RESULT_DIR}/2a_hours.csv", index=False)
    print("\n== close hour 0-23: each sma200 vs base ==")
    print(pct(table).to_string(index=False))
    each = table[table.rule == "each sma200"].set_index("hour")
    base = table[table.rule == "base"].set_index("hour")
    print(f"hours where each beats base: calmar {(each.calmar > base.calmar).sum()}/24, "
          f"total {(each.total > base.total).sum()}/24, maxDD {(each.maxDD > base.maxDD).sum()}/24, "
          f"drop window {(each['drop window'] > base['drop window']).sum()}/24")
    base_calmar = base.loc[0, "calmar"]

    table = ma_grid(prices)
    table.to_csv(f"{RESULT_DIR}/2a_ma.csv", index=False)
    print("\n== MA type and span: each coin vs BTC gate with the same MA ==")
    print(pct(table).to_string(index=False))
    for ma in ("sma", "ema"):
        e = table[(table.rule == "each") & (table.ma == ma)].set_index("span")
        b = table[(table.rule == "btc gate") & (table.ma == ma)].set_index("span")
        print(f"{ma}: spans where each beats the BTC gate: calmar {(e.calmar > b.calmar).sum()}/{len(e)}, "
              f"maxDD {(e.maxDD > b.maxDD).sum()}/{len(e)}, total {(e.total > b.total).sum()}/{len(e)}")
        print(f"{ma}: spans where each has calmar >= the base rule ({base_calmar:.2f}): "
              f"{list(e.index[e.calmar >= base_calmar])}")

    table = bootstrap(prices)
    table.to_csv(f"{RESULT_DIR}/2a_bootstrap.csv", index=False)
    print("\n== paired stationary bootstrap, each sma200 minus base, 2022-2025 daily ==")
    shown = table.copy()
    for c in ("p5", "median", "p95"):
        shown[c] = [f"{v:+.2f}" if m == "calmar diff" else f"{v:+.1%}" for v, m in zip(shown[c], shown["measure"])]
    print(shown.to_string(index=False))
    print("EACH_DONE")
