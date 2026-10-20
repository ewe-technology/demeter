"""
Yearly ledger of H46 - H52 (reports/plan_2026-10-19_gate_lp_options.md) for the PnL page and the report: each
continuous book cut into calendar years (a year's return is its last NAV over the NAV just before it; a book that
starts inside a year starts from its $100k), the year's max drawdown, 移倉 (re-centres) and 換邊 (gate switches,
the first placement not counted), and for the single-slice books in a stablecoin-quoted pool the attribution of
.claude/skills/backtest-report/scripts/lp_attribution.py (decompose: gate-on price, gate-off price, fees, costs).

A book of n slices is the sum of its slices' USD NAVs (each started with 1/n of $100k, never rebalanced).
Books in WBTC / WETH quoted pools (A1, A2, B1) are USD books with a conversion at each switch (gate_lp_options.to_usd),
so they get returns only; the page splits A1 and A2 by differences (control, wstETH itself, the LP layer).

Run from samples/strategy-example on the strategy host, with lp_attribution.py copied next to it:
  PYTHONPATH=../.. python gate_lp_pnl.py            # writes result/gate-lp-options/pnl_ledger.json
"""
import json
import os
from datetime import date

import numpy as np
import pandas as pd

import gate_lp_options as g
from lp_attribution import decompose, fee_check, segments

R = g.RESULT_DIR
YEARS = ["2022", "2023", "2024", "2025", "2026"]
H51 = "H51C1"
D22 = date(2022, 1, 1)

# key: (option, pool, [version names], start, modes for the attribution or None)
SERIES = {
    "c1_ctl": (H51, "99ac", ["ctl_n1_h00_100k"], D22, {"on": ["spot", 1.0], "off": ["cash"]}),
    "c1_ctl3": (H51, "99ac", [f"ctl_n3_h{h:02d}_100k" for h in (0, 8, 16)], D22, None),
    "c1_ladder": (H51, "99ac", ["ladder_n1_h00_100k"], D22, {"on": ["spot", 1.0], "off": ["range", 1.40, 1.01]}),
    "c1_ladder3": (H51, "99ac", [f"ladder_n3_h{h:02d}_100k" for h in (0, 8, 16)], D22, None),
    "c1_sd": (H51, "99ac", ["sd_33_10_n1_h00_100k"], D22, {"on": ["spot", 1.0], "off": ["range", 1.33, 1.10]}),
    "c1_half": (H51, "99ac", ["half_n1_h00_100k"], D22, None),
    "c1_half3": (H51, "99ac", [f"half_n3_h{h:02d}_100k" for h in (0, 8, 16)], D22, None),
    "a1_ctl": ("A1", "e8f7", ["ctl"], date(2024, 10, 13), None),
    "a1_lp": ("A1", "e8f7", ["w0.25"], date(2024, 10, 13), None),
    "a2_ctl": ("A2", "1098", ["ctl"], date(2024, 1, 1), None),
    "a2_wst": ("A2", "1098", ["hold_wsteth"], date(2024, 1, 1), None),
    "a2_lp": ("A2", "1098", ["up_02_08"], date(2024, 1, 1), None),
    "b1_ctl": ("B1", "4585", ["ctl"], D22, None),
    "b1_lp": ("B1", "4585", ["w20"], D22, None),
    "c2_ctl": ("C2", "99ac", ["ctl50"], D22, {"on": ["spot", 0.5], "off": ["cash"]}),
    "c2_lp": ("C2", "99ac", ["w20"], D22, {"on": ["range", 1.20, 1.20], "off": ["cash"]}),
    "c3_ctl": ("C3", "8ad5", ["ctl"], D22, {"on": ["spot", 1.0], "off": ["cash"]}),
    "c3_lp": ("C3", "8ad5", ["w10"], D22, {"on": ["spot", 1.0], "off": ["range", 1.10, 1.10]}),
    "c4_ctl": ("C4", "8ad5", ["ctl50"], D22, {"on": ["spot", 0.5], "off": ["cash"]}),
    "c4_lp": ("C4", "8ad5", ["w30"], D22, {"on": ["range", 1.30, 1.30], "off": ["cash"]}),
}


def nav_path(opt, pool, v, start):
    return f"{R}/nav/{opt}_{pool}_{v}_continuous_{start}.parquet"


def ensure(opt, pool, v, start):
    """H48's B1 - C4 continuous NAVs were written before the file names carried the run kind; rerun those."""
    if os.path.exists(nav_path(opt, pool, v, start)):
        return
    with open(f"{R}/h46_choice.json") as f:
        ch = json.load(f)
    c = next(c for c in g.h48_configs(ch["btc"], ch["eth"]) if (c.option, c.pool_key, c.name) == (opt, pool, v))
    g.run(c, start, g.LAST_DAY, "1h", "continuous")
    print(f"reran {opt} {pool} {v} continuous", flush=True)


def book(opt, pool, names, start) -> pd.DataFrame:
    parts = [pd.read_parquet(nav_path(opt, pool, v, start)) for v in names]
    usd = pd.concat([p["usd"] for p in parts], axis=1).ffill().sum(axis=1)
    return pd.DataFrame({"net": usd, "price": parts[0]["price"]})


def events(opt, pool, v, start) -> pd.DataFrame:
    return pd.read_csv(f"{R}/nav/events_{opt}_{pool}_{v}_continuous_{start}.csv")


def yearly(nav: pd.Series, initial: float) -> dict:
    out = {}
    for y in YEARS:
        cur = nav[nav.index.year == int(y)]
        if not len(cur):
            continue
        before = nav[nav.index < pd.Timestamp(f"{y}-01-01")]
        base = float(before.iloc[-1]) if len(before) else initial
        x = np.concatenate([[base], cur.to_numpy()])
        out[y] = {"ret": float(x[-1] / base - 1), "mdd": float((x / np.maximum.accumulate(x) - 1).min())}
    return out


def counts(evs: list[pd.DataFrame]) -> dict:
    out = {}
    for y in YEARS:
        m = r = 0
        for ev in evs:
            t = pd.to_datetime(ev["t"])
            later = ev.index > ev.index[0]  # the first row is the placement at the start, not a switch
            m += int(((t.dt.year == int(y)) & (ev["kind"] == "recentre")).sum())
            r += int(((t.dt.year == int(y)) & ev["kind"].isin(["on", "off"]) & later).sum())
        out[y] = {"移倉": m, "換邊": r}
    return out


def attribution(df: pd.DataFrame, ev: pd.DataFrame, modes: dict, initial: float) -> dict:
    nav, price = df["net"].to_numpy(), df["price"].astype(float).ffill().to_numpy()
    pe, fe, co, on, _ = decompose(nav, price, segments(df.index, nav, price, ev, modes))
    co[0] += nav[0] - initial  # the buy-in from cash at the first bar
    out = {}
    for y in YEARS:
        idx = np.nonzero(df.index.year == int(y))[0]
        if not len(idx):
            continue
        base = nav[idx[0] - 1] if idx[0] > 0 else initial
        ret = nav[idx[-1]] / base - 1
        a = {"on": float(pe[idx][on[idx]].sum() / base), "off": float(pe[idx][~on[idx]].sum() / base),
             "fees": float(fe[idx].sum() / base), "costs": float(co[idx].sum() / base)}
        a["other"] = float(ret - sum(a.values()))
        out[y] = a
    return out


def bench() -> dict:
    out = {}
    btc = g.hourly_close("99ac").ffill().loc["2021-12-31 23:00":g.IN_TO]
    eth = g.hourly_close("88e6").ffill().loc["2021-12-31 23:00":g.IN_TO]
    b, e = btc / btc.iloc[0], eth / eth.iloc[0]
    for key, nav in (("hold_btc", b), ("hold_eth", e), ("hold_5050", 0.5 * b + 0.5 * e)):
        out[key] = {"years": yearly(nav.iloc[1:], 1.0), "total": float(nav.iloc[-1] - 1),
                    "mdd": float((nav / nav.cummax() - 1).min())}
    return out


def row_info(opt, pool, names, start) -> dict:
    rs = [json.load(open(f"{R}/rows/{opt}_{pool}_{v}_continuous_{start}.json")) for v in names]
    return {"gas": float(np.mean([r["gas"] for r in rs])), "impact": float(np.mean([r["impact"] for r in rs])),
            "swap_fee": float(np.mean([r["swap_fee"] for r in rs]))}


def main():
    out = {"bench": bench(), "series": {}, "fee_check": {}}
    for key, (opt, pool, names, start, modes) in SERIES.items():
        for v in names:
            ensure(opt, pool, v, start)
        df = book(opt, pool, names, start)
        evs = [events(opt, pool, v, start) for v in names]
        cnt = counts(evs)
        nav0 = pd.concat([pd.Series([float(g.USD)], index=[df.index[0] - pd.Timedelta(hours=1)]), df["net"]])
        s = {"years": yearly(df["net"], g.USD), "info": cnt, "total": float(df["net"].iloc[-1] / g.USD - 1),
             "cagr": g.cagr(nav0), "mdd": float((nav0 / nav0.cummax() - 1).min()), "start": str(start),
             "moves": sum(v["移倉"] for v in cnt.values()), "switches": sum(v["換邊"] for v in cnt.values())}
        try:
            s.update(row_info(opt, pool, names, start))  # cost shares of capital, the mean over slices
        except FileNotFoundError:
            pass
        if modes:
            s["attr"] = attribution(df, evs[0], modes, g.USD)
            if key in ("c1_ladder", "c2_lp", "c3_lp"):
                out["fee_check"][key] = fee_check(df, evs[0], modes)
        out["series"][key] = s
        print(key, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items()
                    if k in ("total", "cagr", "mdd", "moves", "switches", "gas")}, flush=True)
    with open(f"{R}/pnl_ledger.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(json.dumps(out["fee_check"], indent=1))


if __name__ == "__main__":
    main()
