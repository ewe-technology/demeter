"""Listed only (after the fact): half A2 (wstETH/WETH up-skew, ETH TS30), half C1 (99ac ladder, BTC EMA100), each $50k
from 2024-01-01, never rebalanced; against the same mix of their spot controls and against holding."""
import json
from datetime import date
import numpy as np
import pandas as pd
import gate_lp_options as g
import gate_lp_pnl as p

R = g.RESULT_DIR
S = date(2024, 1, 1)
ch = json.load(open(f"{R}/h46_choice.json"))
cf = {(c.option, c.pool_key, c.name): c for c in g.h48_configs(ch["btc"], ch["eth"])}
for v in ("ladder", "ctl"):  # C1 from 2024-01-01, its own continuous run
    c = cf[("C1", "99ac", v)]
    path = f"{R}/nav/C1_99ac_{v}_continuous_{S}.parquet"
    import os
    if not os.path.exists(path):
        g.run(c, S, g.LAST_DAY, "1h", "continuous")

def nav(opt, pool, v):
    return pd.read_parquet(f"{R}/nav/{opt}_{pool}_{v}_continuous_{S}.parquet")["usd"]

def ev(opt, pool, v):
    return pd.read_csv(f"{R}/nav/events_{opt}_{pool}_{v}_continuous_{S}.csv")

books = {"a2_lp": nav("A2", "1098", "up_02_08"), "a2_ctl": nav("A2", "1098", "ctl"),
         "c1_lp": nav("C1", "99ac", "ladder"), "c1_ctl": nav("C1", "99ac", "ctl")}
idx = books["a2_lp"].index.union(books["c1_lp"].index)
b = {k: v.reindex(idx).ffill() for k, v in books.items()}
combo = {"mix": 0.5 * b["a2_lp"] + 0.5 * b["c1_lp"], "mix_ctl": 0.5 * b["a2_ctl"] + 0.5 * b["c1_ctl"]}
btc = g.hourly_close("99ac").ffill().reindex(idx, method="ffill")
eth = g.hourly_close("88e6").ffill().reindex(idx, method="ffill")
p0b, p0e = float(g.hourly_close("99ac").ffill().loc[:"2023-12-31 23:00"].iloc[-1]), float(g.hourly_close("88e6").ffill().loc[:"2023-12-31 23:00"].iloc[-1])
hold = {"hold_btc": 1e5 * btc / p0b, "hold_eth": 1e5 * eth / p0e, "hold_5050": 5e4 * btc / p0b + 5e4 * eth / p0e}
out = {}
for k, n in {**combo, **{k: v for k, v in b.items()}, **hold}.items():
    nav0 = pd.concat([pd.Series([1e5], index=[idx[0] - pd.Timedelta(hours=1)]), n])
    out[k] = {"total": float(n.iloc[-1] / 1e5 - 1), "cagr": g.cagr(nav0), "mdd": float((nav0 / nav0.cummax() - 1).min()),
              "years": p.yearly(n, 1e5)}
cnt = {k: p.counts([ev(*a)]) for k, a in {"a2_lp": ("A2", "1098", "up_02_08"), "c1_lp": ("C1", "99ac", "ladder"),
                                           "c1_ctl": ("C1", "99ac", "ctl"), "a2_ctl": ("A2", "1098", "ctl")}.items()}
out["counts"] = cnt
# drawdown overlap: when does each half hit its worst
for k in ("a2_lp", "c1_lp", "mix"):
    n = combo["mix"] if k == "mix" else b[k]
    dd = n / n.cummax() - 1
    out[k]["mdd_at"] = str(dd.idxmin())
out["corr_daily"] = float(b["a2_lp"].resample("1D").last().pct_change().corr(b["c1_lp"].resample("1D").last().pct_change()))
json.dump(out, open(f"{R}/combo_a2_c1.json", "w"), indent=1, default=str)
for k in ("mix", "mix_ctl", "a2_lp", "a2_ctl", "c1_lp", "c1_ctl", "hold_btc", "hold_eth", "hold_5050"):
    o = out[k]
    print(k, f"total {o['total']:+.4f} cagr {o['cagr']:+.4f} mdd {o['mdd']:+.4f}",
          {y: (round(v['ret'], 4), round(v['mdd'], 4)) for y, v in o["years"].items()}, o.get("mdd_at", ""))
print("counts", {k: {y: (c["移倉"], c["換邊"]) for y, c in v.items() if y >= "2024"} for k, v in cnt.items()})
print("corr", out["corr_daily"])
