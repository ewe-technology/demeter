"""
H17 - H19 of reports/single_pool_loop.md (registered 2026-10-08, after H16): each coin on its own gate, an LP on its
own kind while the gate is on, a buy ladder in its stablecoin pool while it is off, and the two coins as one book.

H18-A  ETH on its own gate. 0x88e6 (ETH/USDC 0.05%), gate = ETH's 88e6 close above its EMA100 (pool_lp_batch.gate,
       from the pool's first day), $100k, the 16 windows and costs of pool_lp_batch.py:
         e_down     on: 100% WETH spot   off: [p/1.40, p 1.01] in 88e6, re-centred hourly (H4b's g_down, no tuning)
         e_spot100  on: 100% WETH spot   off: USDC (the control)
       Verdict: e_down passes if (e_down - e_spot100) meets H2's 1-3 (median > 0, >= 12/16 > 0, median > 0 in both
       halves).
H18-C  Listed only: e_spot100 against H7's 88e6 g_spot100 (the same book on the BTC gate).

H17    BTC sleeve while on: WBTC/cbBTC 0.01% +/- 0.5% (0xe8f7) instead of WBTC.
H18-B  ETH sleeve while on: wstETH/WETH 0.01% +/- 0.5% (0x1098) instead of WETH; holding wstETH listed beside it.
       Both are overlays on the sleeve's on-hours, not Demeter runs of the whole book. The LP is yield_layer.py's
       `_to2026` value index (one position always open, re-centred at 00:00 when out, in the base coin), so the
       sleeve's value is multiplied by the index's hourly change while the gate is on and by 1 otherwise. wstETH is
       yield_layer.wsteth_ratio (causal). Each on-period pays, as a share of the sleeve's capital:
         LP     enter 580k gas, exit 400k, every index re-centre inside the on-hours 850k (sleeve_sim.GAS_EVENT_UNITS),
                plus 1 bp per conversion in and out (yield_layer's extra hop)
         wstETH 130k gas in and out, plus 1 bp each way
       No exit is charged at a window's end. The LP is only used from its clean data (cbBTC 2024-10-13, wstETH
       2024-01-01); before that the sleeve stays in spot.
       Windows: 6 months from each quarter start with clean data, the last ending 2026-09-30 (cbBTC 2024-10-13 and
       2025-01 .. 2026-04, 7 windows; wstETH 2024-01 .. 2026-04, 10 windows). Gates: BTC EMA100 for H17, ETH EMA100
       for H18-B.
       Verdict at $100k a sleeve and 3 gwei: the overlay's excess (its value multiple - 1) has a median > 0 and is
       > 0 in more than half the windows. $10k and 20 gwei are listed. For H18-B, the LP is judged against holding
       wstETH (the LP multiple / the wstETH multiple - 1); wstETH against WETH is listed.

H19    The book: half the capital in a BTC sleeve, half in an ETH sleeve, each from cash at the window's start, no
       rebalancing inside the window (each sleeve's net value from its own $100k run, normalised to 1). The 16 windows
       of H4b, 2022-01 .. 2025-10:
         P0  BTC: g_spot100 (BTC gate)      ETH: 88e6 g_spot100 (BTC gate, H7)     the live gate, spot
         P1  BTC: g_down (BTC gate, H4b)    ETH: 88e6 g_spot100 (BTC gate)
         P2  BTC: g_down                    ETH: e_spot100 (ETH gate)
         P3  BTC: g_down                    ETH: e_down (ETH gate)
       Verdict: P3 passes if (P3 - P0) meets H2's 1-3 and the median max drawdown of P3 (hourly) is no more than
       2 pt worse than P0's. P1 - P0, P2 - P1 and P3 - P2 split the gain and are listed only, as are the same books
       rebalanced to 50/50 at every quarter start (no cost charged for the rebalance) and P3 with the H17 / H18-B
       overlays at $100k and 3 gwei.

Inputs on the backtest host, read if present and run otherwise: H4b's result/pool-lp-windows/nav_g_down_<start>.csv,
H13's and H7's result/pool-lp-batch/nav_{99ac,88e6}_g_spot100_ema100_<start>.csv, yield_layer.py's
result/yield-layer/sleeve_{cbbtc,wsteth}_lp0.005_to2026.csv with their events files.

Run from samples/strategy-example:
  PYTHONPATH=../.. python pool_lp_combo.py --test               # e_down and e_spot100 over 2022-05-01 .. 05-31
  PYTHONPATH=../.. python pool_lp_combo.py --runs --workers 3   # H18-A, the 32 Demeter runs
  PYTHONPATH=../.. python pool_lp_combo.py --combine            # H18-C, H17, H18-B, H19 from the files
"""
import argparse
import multiprocessing
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

import pool_lp_batch as batch
import yield_layer as yl
from sleeve_sim import GAS_EVENT_UNITS

LADDER = dict(off="range", off_width=0.40, off_up=0.01)
g = dict(gated=True, on="spot")
H18A = [batch.cfg("88e6", "e_down", gate_src="88e6", **LADDER, **g),
        batch.cfg("88e6", "e_spot100", gate_src="88e6", **g)]
WINDOWS_DIR = "result/pool-lp-windows"
OVERLAY_CAPITAL = (100_000, 10_000)
OVERLAY_GWEI = (3, 20)
OVERLAY_BPS = 1e-4  # one conversion, in or out
LP_FROM = {"cbbtc": pd.Timestamp("2024-10-13"), "wsteth": pd.Timestamp("2024-01-01")}
LAST_HOUR = pd.Timestamp("2026-09-30 23:00")
MAX_DD_SLACK = 0.02


# ---- sleeves of the book ----

SLEEVE_CFG = {"btc_spot": batch.cfg("99ac", "g_spot100", **g),
              "btc_down": batch.cfg("99ac", "g_down", **LADDER, **g),
              "eth_spot_btcgate": batch.cfg("88e6", "g_spot100", **g),
              "eth_spot": H18A[1], "eth_down": H18A[0]}


def sleeve_paths(name: str, start: date) -> list[str]:
    """Where a sleeve's net value may be: H4b wrote g_down to pool-lp-windows, a rerun here lands in pool-lp-batch."""
    c = SLEEVE_CFG[name]
    paths = [f"{batch.RESULT_DIR}/nav_{c.pool_key}_{c.name}_ema{c.ema}_{start}.csv"]
    if name == "btc_down":
        paths.insert(0, f"{WINDOWS_DIR}/nav_g_down_{start}.csv")
    return paths


def load_nav(name: str, start: date) -> pd.Series:
    """Hourly net value of a sleeve over its window, normalised to 1 at the first bar."""
    path = next(p for p in sleeve_paths(name, start) if os.path.exists(p))
    nav = pd.read_csv(path, index_col=0, parse_dates=True)["net"].resample("1h").last().ffill()
    return nav / nav.iloc[0]


def missing_runs() -> list[tuple]:
    return [(SLEEVE_CFG[n], s, batch.window_end(s)) for n in SLEEVE_CFG for s in batch.window_starts("99ac")
            if not any(os.path.exists(p) for p in sleeve_paths(n, s))]


def max_dd(nav: pd.Series) -> float:
    return float((nav / nav.cummax() - 1).min())


# ---- H17 / H18-B overlays ----

def lp_index(kind: str) -> tuple[pd.Series, pd.DatetimeIndex]:
    out, events = yl.load_sleeve(f"{kind}_lp0.005", yl.HOLDOUT_TAG)
    return out["nav"], events


def overlay(gate: pd.Series, hours: pd.DatetimeIndex, level: pd.Series, events: pd.DatetimeIndex | None,
            avail_from: pd.Timestamp, capital: float, gwei: float, eth_usd: pd.Series, enter_units: int,
            exit_units: int) -> pd.Series:
    """
    Value multiple of a sleeve that holds `level` (a value index in the sleeve's base coin) instead of the base coin
    while the gate is on, on `hours`. Costs are a share of `capital`. The state over (h-1, h] is the one at h-1.
    """
    level = level.reindex(hours.union(level.index)).ffill().reindex(hours)
    on = gate.reindex(hours.normalize(), method="ffill").to_numpy().astype(bool)
    on &= (hours >= avail_from) & level.notna().to_numpy()
    held = np.r_[False, on[:-1]]
    step = np.where(held, (level / level.shift(1)).fillna(1.0).to_numpy(), 1.0)
    cost = np.zeros(len(hours))

    def usd(units: int, t: pd.Timestamp) -> float:
        return units * gwei * 1e-9 * float(eth_usd.asof(t.normalize()))

    for i, t in enumerate(hours):
        was = on[i - 1] if i else False
        if on[i] and not was:
            cost[i] += usd(enter_units, t) / capital + OVERLAY_BPS
        elif was and not on[i]:
            cost[i] += usd(exit_units, t) / capital + OVERLAY_BPS
    for t in (events if events is not None else []):
        i = hours.searchsorted(t)
        if 0 < i < len(hours) and hours[i] == t and on[i] and on[i - 1]:
            cost[i] += usd(GAS_EVENT_UNITS["recentre"], t) / capital
    return pd.Series(np.cumprod(step * (1 - cost)), index=hours)


def overlay_windows(kind: str) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    first = LP_FROM[kind]
    starts = ([] if first.day == 1 else [first]) + \
        [s for s in (pd.Timestamp(y, m, 1) for y in (2024, 2025, 2026) for m in (1, 4, 7, 10)) if s >= first]
    windows = [(s, s + pd.DateOffset(months=6) - pd.Timedelta(hours=1)) for s in starts]
    return [(s, e) for s, e in windows if e <= LAST_HOUR]


def overlays(btc_gate: pd.Series, eth_gate: pd.Series, eth_usd: pd.Series) -> pd.DataFrame:
    cb, cb_ev = lp_index("cbbtc")
    ws, ws_ev = lp_index("wsteth")
    ratio = yl.wsteth_ratio(pd.date_range(LP_FROM["wsteth"], LAST_HOUR, freq="1h"))
    rows = []
    for kind, gate in (("cbbtc", btc_gate), ("wsteth", eth_gate)):
        for s, e in overlay_windows(kind):
            hours = pd.date_range(s, e, freq="1h")
            on_share = float(gate.reindex(hours.normalize(), method="ffill").mean())
            for capital in OVERLAY_CAPITAL:
                for gwei in OVERLAY_GWEI:
                    row = {"kind": kind, "start": s.date(), "end": e.date(), "capital": capital, "gwei": gwei,
                           "on_share": on_share}
                    lp = dict(capital=capital, gwei=gwei, eth_usd=eth_usd, enter_units=GAS_EVENT_UNITS["enter"],
                              exit_units=GAS_EVENT_UNITS["exit"])
                    if kind == "cbbtc":
                        row["lp"] = overlay(gate, hours, cb, cb_ev, LP_FROM[kind], **lp).iloc[-1] - 1
                    else:
                        lp_m = overlay(gate, hours, ws, ws_ev, LP_FROM[kind], **lp).iloc[-1]
                        hold_m = overlay(gate, hours, ratio, None, LP_FROM[kind], capital, gwei, eth_usd,
                                         GAS_EVENT_UNITS["swap"], GAS_EVENT_UNITS["swap"]).iloc[-1]
                        row.update(lp=lp_m - 1, wsteth=hold_m - 1, lp_vs_wsteth=lp_m / hold_m - 1)
                    rows.append(row)
    return pd.DataFrame(rows)


# ---- H19 ----

BOOKS = {"P0": ("btc_spot", "eth_spot_btcgate"), "P1": ("btc_down", "eth_spot_btcgate"),
         "P2": ("btc_down", "eth_spot"), "P3": ("btc_down", "eth_down")}
DIFFS = (("P3 - P0", "P3", "P0"), ("P1 - P0", "P1", "P0"), ("P2 - P1", "P2", "P1"), ("P3 - P2", "P3", "P2"),
         ("P3_q - P0_q", "P3_q", "P0_q"), ("P3_lp - P3", "P3_lp", "P3"))


def book(btc: pd.Series, eth: pd.Series, rebalance: bool) -> pd.Series:
    """Half in each sleeve (both start at 1); rebalance = back to half and half at every quarter start."""
    idx = btc.index.union(eth.index)
    b, e = btc.reindex(idx).ffill(), eth.reindex(idx).ffill()
    if not rebalance:
        return 0.5 * b + 0.5 * e
    out, level, prev = [], 1.0, 0
    for _, pos in pd.Series(np.arange(len(idx)), index=idx).groupby(idx.to_period("Q")):
        pos = pos.to_numpy()
        seg = level * (0.5 * b.iloc[pos] / b.iloc[prev] + 0.5 * e.iloc[pos] / e.iloc[prev])
        out.append(seg)
        level, prev = float(seg.iloc[-1]), pos[-1]
    return pd.concat(out)


def h19(btc_gate: pd.Series, eth_gate: pd.Series, eth_usd: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    cb, cb_ev = lp_index("cbbtc")
    ws, ws_ev = lp_index("wsteth")
    rows = []
    for s in batch.window_starts("99ac"):
        navs = {n: load_nav(n, s) for n in {x for pair in BOOKS.values() for x in pair}}
        for p, (bn, en) in BOOKS.items():
            for reb in (False, True):
                nav = book(navs[bn], navs[en], reb)
                rows.append({"book": p + ("_q" if reb else ""), "start": s, "net": nav.iloc[-1] - 1,
                             "maxDD": max_dd(nav)})
        lp = dict(capital=100_000, gwei=3, eth_usd=eth_usd, enter_units=GAS_EVENT_UNITS["enter"],
                  exit_units=GAS_EVENT_UNITS["exit"])
        bh, eh = navs["btc_down"].index, navs["eth_down"].index
        nav = book(navs["btc_down"] * overlay(btc_gate, bh, cb, cb_ev, LP_FROM["cbbtc"], **lp),
                   navs["eth_down"] * overlay(eth_gate, eh, ws, ws_ev, LP_FROM["wsteth"], **lp), False)
        rows.append({"book": "P3_lp", "start": s, "net": nav.iloc[-1] - 1, "maxDD": max_dd(nav)})
    t = pd.DataFrame(rows)
    nets = t.pivot(index="start", columns="book", values="net").sort_index()
    dds = t.pivot(index="start", columns="book", values="maxDD").sort_index()
    out = []
    for name, a, b in DIFFS:
        x = nets[a] - nets[b]
        c = batch.checks(x)
        half = len(x) // 2
        out.append({"diff": name, "median": x.median(), "positive": int((x > 0).sum()), "n": len(x),
                    "first_half": x.iloc[:half].median(), "second_half": x.iloc[half:].median(),
                    "maxDD_a": dds[a].median(), "maxDD_b": dds[b].median(),
                    "checks": "PASS" if all(c.values()) else "fail: " + "; ".join(k for k, ok in c.items() if not ok)})
    return t, pd.DataFrame(out)


def combine():
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    fmt = lambda v: f"{v:.4f}"
    btc_gate, eth_gate, eth_usd = batch.gate("99ac", 100), batch.gate("88e6", 100), batch.eth_daily()

    starts = batch.window_starts("99ac")
    nets = {n: pd.Series({s: load_nav(n, s).iloc[-1] - 1 for s in starts})
            for n in ("eth_down", "eth_spot", "eth_spot_btcgate")}
    x = nets["eth_down"] - nets["eth_spot"]
    c = batch.checks(x)
    print("H18-A e_down - e_spot100: median %.4f, positive %d/%d, halves %.4f / %.4f -> %s" % (
        x.median(), (x > 0).sum(), len(x), x.iloc[:8].median(), x.iloc[8:].median(),
        "PASS" if all(c.values()) else c))
    print("  by window:", " ".join(f"{v * 100:+.1f}" for v in x))
    y = nets["eth_spot"] - nets["eth_spot_btcgate"]
    print("H18-C e_spot100 (ETH gate) - g_spot100 (BTC gate), 88e6: median %.4f, positive %d/%d (listed)" % (
        y.median(), (y > 0).sum(), len(y)))
    print("  by window:", " ".join(f"{v * 100:+.1f}" for v in y))

    o = overlays(btc_gate, eth_gate, eth_usd)
    o.to_csv(f"{batch.RESULT_DIR}/overlay_h17_h18b.csv", index=False)
    print(o.to_string(index=False, float_format=fmt))
    for kind, col, name in (("cbbtc", "lp", "H17"), ("wsteth", "lp_vs_wsteth", "H18-B"),
                            ("wsteth", "wsteth", "wstETH - WETH")):
        for (cap, gw), part in o[o["kind"] == kind].groupby(["capital", "gwei"]):
            v = part[col]
            judged = cap == 100_000 and gw == 3 and name != "wstETH - WETH"
            ok = v.median() > 0 and (v > 0).sum() > len(v) / 2
            print(f"{name} ${cap:,} {gw} gwei: median {v.median():.4f}, positive {(v > 0).sum()}/{len(v)}"
                  + (f" -> {'PASS' if ok else 'fail'}" if judged else " (listed)"))

    t, s = h19(btc_gate, eth_gate, eth_usd)
    t.to_csv(f"{batch.RESULT_DIR}/windows_h19.csv", index=False)
    s.to_csv(f"{batch.RESULT_DIR}/summary_h19.csv", index=False)
    print(t.pivot(index="start", columns="book", values="net").to_string(float_format=fmt))
    print(s.to_string(index=False, float_format=fmt))
    p = s.iloc[0]
    dd_ok = p["maxDD_a"] >= p["maxDD_b"] - MAX_DD_SLACK
    print(f"H19 P3 - P0: {p['checks']}, median maxDD P3 {p['maxDD_a']:.4f} vs P0 {p['maxDD_b']:.4f} -> "
          f"{'PASS' if p['checks'] == 'PASS' and dd_ok else 'fail'}")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--test", action="store_true")
    a.add_argument("--runs", action="store_true")
    a.add_argument("--combine", action="store_true")
    a.add_argument("--workers", type=int, default=3)
    a = a.parse_args()
    if not (a.test or a.runs or a.combine):
        sys.exit("pass --test, --runs or --combine")
    os.makedirs(batch.RESULT_DIR, exist_ok=True)
    batch.eth_daily()  # fill the caches before the workers read them
    batch.gate("99ac", 100)
    batch.gate("88e6", 100)
    if a.test:
        for c in H18A:
            print(pd.Series(batch.run(c, date(2022, 5, 1), date(2022, 5, 31))).to_string(), flush=True)
        return
    if a.runs:
        tasks = missing_runs()
        print(f"{len(tasks)} runs", flush=True)
        with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
            rows = pool.starmap(batch.run, tasks, chunksize=1)
        pd.DataFrame(rows).to_csv(f"{batch.RESULT_DIR}/windows_h18a.csv", index=False)
    if a.combine:
        combine()


if __name__ == "__main__":
    main()
