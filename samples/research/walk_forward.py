"""
Walk-forward check of the tri-pool grid (expanding window, one test year at a time).

  train 2022           -> pick a config -> test 2023
  train 2022-2023      -> pick a config -> test 2024
  train 2022-2024      -> pick a config -> test 2025

The picked config's test-year returns are chained into one out-of-sample curve and compared with
what you would get without choosing (median config), with hindsight (best config each year),
and with fixed configs / buy-and-hold.

Input: samples/strategy-example/result/tri-gate/nav_grid.csv, made by
  cd samples/strategy-example && PYTHONPATH=../.. python tri_btc_eth_gate.py --grid

Switching config at a year boundary would cost one extra rebuild in practice, which is not charged here.

Run from samples/research:  python walk_forward.py
"""
import os
import re

import numpy as np
import pandas as pd

RESULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "strategy-example", "result", "tri-gate")
TEST_YEARS = (2023, 2024, 2025)
HOLDS = ["hold_usdc", "hold_eth", "hold_btc", "hold_50eth_50btc"]
FIXED = ["none_none", "btc100_none", "btc100_follow", "btc150_none", "both150_none"]


def window(nav: pd.Series, start: str, end: str) -> pd.Series:
    return nav.loc[start:end].dropna()


def ret(nav: pd.Series, start: str, end: str) -> float:
    seg = window(nav, start, end)
    return seg.iloc[-1] / seg.iloc[0] - 1


def max_dd(seg: pd.Series) -> float:
    return (seg / seg.cummax() - 1).min()


def parse(name: str) -> tuple[str, str, str]:
    """'btc100_follow' -> ('btc', '100', 'follow'); 'none_fade' -> ('none', '-', 'fade')"""
    m = re.match(r"(btc|eth|both)(\d+)_(\w+)", name)
    return (m.group(1), m.group(2), m.group(3)) if m else ("none", "-", name.split("_")[1])


navs = pd.read_csv(os.path.join(RESULT_DIR, "nav_grid.csv"), index_col=0, parse_dates=True)
configs = [c for c in navs.columns if c not in HOLDS]
print(f"{len(configs)} configs, NAV {navs.index[0].date()} ~ {navs.index[-1].date()}")

year_ret = pd.DataFrame({y: {c: ret(navs[c], f"{y}-01-01", f"{y + 1}-01-01") for c in navs.columns}
                         for y in (2022, *TEST_YEARS)})

# ---------------------------------------------------------------- selection
rows = []
for y in TEST_YEARS:
    train_start, train_end = "2022-01-01", f"{y}-01-01"
    train = pd.DataFrame({c: {"ret": ret(navs[c], train_start, train_end),
                              "dd": max_dd(window(navs[c], train_start, train_end))} for c in configs}).T
    train["calmar"] = train["ret"] / train["dd"].abs().replace(0, np.nan)
    test = year_ret[y].loc[configs]
    for rule in ("ret", "calmar"):
        pick = train[rule].idxmax()
        rows.append({"test year": y, "rule": rule, "pick": pick, "train ret": train.loc[pick, "ret"],
                     "train maxDD": train.loc[pick, "dd"], "test ret": test[pick],
                     "test rank": f"{int((test > test[pick]).sum()) + 1}/{len(test)}",
                     "median config": test.median(), "best config": test.max(), "best is": test.idxmax()})
picks = pd.DataFrame(rows)


def stitched(names_by_year: dict) -> pd.Series:
    """Hourly OOS curve: each test year's segment of the chosen config, rescaled to continue the last one."""
    parts, level = [], 1.0
    for y in TEST_YEARS:
        seg = window(navs[names_by_year[y]], f"{y}-01-01", f"{y + 1}-01-01")
        seg = seg / seg.iloc[0] * level
        level = seg.iloc[-1]
        parts.append(seg)
    return pd.concat(parts)


summary = []
for rule in ("ret", "calmar"):
    chosen = dict(zip(picks[picks.rule == rule]["test year"], picks[picks.rule == rule]["pick"]))
    curve = stitched(chosen)
    summary.append({"strategy": f"walk-forward ({rule})", **{str(y): year_ret.loc[chosen[y], y] for y in TEST_YEARS},
                    "2023-25": curve.iloc[-1] - 1, "maxDD": max_dd(curve)})
for label, pick_year in (("median config (no skill)", lambda y: year_ret[y].loc[configs].median()),
                         ("best config (hindsight)", lambda y: year_ret[y].loc[configs].max())):
    r = {str(y): pick_year(y) for y in TEST_YEARS}
    summary.append({"strategy": label, **r, "2023-25": np.prod([1 + v for v in r.values()]) - 1, "maxDD": np.nan})
for name in FIXED + HOLDS[1:]:
    seg = window(navs[name], "2023-01-01", "2026-01-01")
    summary.append({"strategy": f"fixed {name}" if name in FIXED else name,
                    **{str(y): year_ret.loc[name, y] for y in TEST_YEARS},
                    "2023-25": seg.iloc[-1] / seg.iloc[0] - 1, "maxDD": max_dd(seg)})
summary = pd.DataFrame(summary).set_index("strategy")

# ---------------------------------------------------------------- family consistency
# for every gate x span pair: does follow (or fade) beat the fixed 50/50 in that year?
fam = pd.DataFrame([{"config": c, "gate": parse(c)[0], "span": parse(c)[1], "tilt": parse(c)[2]} for c in configs])
consistency = []
for tilt in ("follow", "fade"):
    for y in (2022, *TEST_YEARS):
        wins = total = 0
        for (gate, span), g in fam.groupby(["gate", "span"]):
            base = g[g.tilt == "none"].config.iloc[0]
            other = g[g.tilt == tilt].config.iloc[0]
            wins += year_ret.loc[other, y] > year_ret.loc[base, y]
            total += 1
        consistency.append({"tilt": tilt, "year": y, "beats 50/50": f"{wins}/{total}"})
gate_by_year = pd.DataFrame({y: fam.assign(r=year_ret[y].loc[fam.config].values).groupby("gate")["r"].median()
                             for y in (2022, *TEST_YEARS)})


def pct(df: pd.DataFrame, cols) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        out[c] = out[c].map(lambda v: f"{v:+.1%}" if pd.notna(v) else "")
    return out


print("\n=== picks per test year ===")
print(pct(picks, ["train ret", "train maxDD", "test ret", "median config", "best config"]).to_string(index=False))
print("\n=== out-of-sample 2023-2025 ===")
print(pct(summary, ["2023", "2024", "2025", "2023-25", "maxDD"]).to_string())
print("\n=== does the tilt beat fixed 50/50 within each gate x span pair? ===")
print(pd.DataFrame(consistency).pivot(index="tilt", columns="year", values="beats 50/50").to_string())
print("\n=== median yearly return by gate (over spans and tilts) ===")
print(pct(gate_by_year, gate_by_year.columns).to_string())

picks.to_csv(os.path.join(RESULT_DIR, "walk_forward_picks.csv"), index=False)
summary.to_csv(os.path.join(RESULT_DIR, "walk_forward_summary.csv"))
