"""
H24 - H28 of reports/single_pool_loop.md (registered 2026-10-08 in 2b04a7c, before H17 - H23 ran): robustness checks
on g_down. 0x99ac, $100k, BTC gate, the 16 windows and costs of pool_lp_batch.py unless stated.

H24  placebo: the BTC EMA100 gate from 2021-08-16 .. 2026-09-30 rolled by k days (np.roll, so the count and length of
     the gate-off spells stay the same), 20 k from +-[60, 900] (seed 24). g_down and g_spot100 per k.
       Verdict: per k the median over the windows of (g_down - g_spot100). If at most 4 of the 20 are >= the real
       gate's median (H4b g_down - H13 g_spot100), the gate's timing is the main source of the gain. If 5 or more,
       and the median of the 20 medians is > 0, the gain mostly comes from this price path.
H25  delay: the same signal (close of day d-1), the switch and placement at 01:00 (d1) and 04:00 (d4).
       Verdict: d1's (g_down - g_spot100), both delayed, meets H2's 1-3. d4 listed.
H26  daily out-of-range check: the gate-off ladder is re-centred only at 00:00 (g_down_d1x), at $100k and $10k with
     each year's gwei, against H13's and H12's g_spot100.
       Verdict: each capital passes if (g_down_d1x - g_spot100) meets H2's 1-3.
H27  map, descriptive: EMA {50, 100, 200} x lower p / {1.20, 1.40, 1.60} x upper p x {1.00, 1.01, 1.03}, each against
     the g_spot100 of its EMA. The 5 cells run before (H4b, H8, H13) are read from their files, 22 are new. Upper
     p x 1.00 is off_up = 1e-6 (0 means "same as below" in Config30): all USDC, the upper edge at the last usable tick
     at or below the price (RobustGated.place), re-centred like the others once the price is above p.
       Described: 20 or more of 27 cells with median > 0 is a plateau, 10 or fewer is a point.
H28  block bootstrap, no new runs: the daily (g_down, g_spot100) returns of H4b's Jan-1 windows (2022 .. 2025) and of
     the 2025-10 window over 2026-01 .. 09, chained into 2022-01 .. 2026-09 (entry costs at each Jan 1 kept). 30-day
     circular blocks, 10,000 draws, seed 28: 90% interval of the annualised excess.
       Described: lower bound > 0, "not likely luck within this path"; <= 0, "overlapping windows overstate it".

Run from samples/strategy-example:
  PYTHONPATH=../.. python pool_lp_robust.py --test                  # equivalence and one short run per change
  PYTHONPATH=../.. python pool_lp_robust.py --set h25 --workers 3   # also h26, h27, h24
  PYTHONPATH=../.. python pool_lp_robust.py --report                # every set with results, and H28
"""
import argparse
import dataclasses
import multiprocessing
import os
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

import pool_lp_batch as batch
from demeter.uniswap.helper import nearest_usable_tick
from pool_lp_windows import GatedPool

LADDER = dict(off="range", off_width=0.40, off_up=0.01)
PLACEBO_FROM, PLACEBO_TO = "2021-08-16", "2026-09-30"
LOWS = {120: 0.20, 140: 0.40, 160: 0.60}
UPS = {100: 1e-6, 101: 0.01, 103: 0.03}


@dataclasses.dataclass(frozen=True)
class ConfigR(batch.ConfigX):
    shift: int = 0  # H24: days the gate is rolled by
    delay: int = 0  # H25: UTC hour the gate is read and the book switched
    daily_check: bool = False  # H26: re-centre only at the gate hour


def rcfg(name: str, ema: int = 100, initial: float | None = None, **kw) -> ConfigR:
    extra = {k: kw.pop(k) for k in ("shift", "delay", "daily_check") if k in kw}
    base = batch.cfg("99ac", name, initial=initial, ema=ema, gated=True, on="spot", **kw)
    return ConfigR(**{f.name: getattr(base, f.name) for f in dataclasses.fields(base)}, **extra)


def placebo_shifts() -> list[int]:
    rng = np.random.default_rng(24)
    out = []
    while len(out) < 20:
        k = int(rng.integers(60, 901)) * int(rng.choice([-1, 1]))
        if k not in out:
            out.append(k)
    return out


def rolled(gate: pd.Series, k: int) -> pd.Series:
    seg = gate.loc[PLACEBO_FROM:PLACEBO_TO]
    return pd.Series(np.roll(seg.to_numpy(), k), index=seg.index)


class RobustGated(GatedPool):
    """GatedPool with a rolled gate (shift), a later switch hour (delay) and a daily-only re-centre (daily_check).
    With the defaults it does what GatedPool.on_bar does (checked by --test)."""

    def __init__(self, cfg, gate: pd.Series):
        super().__init__(cfg, rolled(gate, cfg.shift) if getattr(cfg, "shift", 0) else gate)

    def on_bar(self, snapshot):
        c = self.cfg
        t = snapshot.timestamp
        price = self.markets[batch.KEY].market_status.data.price
        first = self.state is None
        gate_bar = t.hour == getattr(c, "delay", 0) and t.minute == 0
        switched = False
        if first or gate_bar:
            on = bool(self.gate.asof(pd.Timestamp(t).normalize()))
            if on != self.state:
                self.go(on, price, t)
                switched = True
        check = gate_bar and not switched if getattr(c, "daily_check", False) else not gate_bar
        if (not first and check and t.minute == 0 and self.mode == "range"
                and not (self.bounds[0] <= price <= self.bounds[1])):
            self.remove()
            self.place(price, 0.0, "recentre", t)
        if t.minute == 0:
            self.log_weight(t, price)

    def place(self, price: Decimal, width: float, kind: str, t):
        """Upper p x 1.00 (H27): add_liquidity_by_value needs the price strictly inside, so sell the WBTC and add the
        USDC by tick, the upper edge at the last usable tick at or below the price."""
        c = self.cfg
        if self.state is not False or c.off_up >= 1e-3:
            return super().place(price, width, kind, t)
        m = self.markets[batch.KEY]
        btc = self.broker.get_token_balance(c.base)
        if btc > 0:
            m.swap(btc, c.base, c.quote)
        sp = m.pool_info.tick_spacing
        cur, low = m.price_to_tick(price), m.price_to_tick(price / Decimal(self.k[0]))
        assert low < cur, "the range below the price must have lower ticks (quote is token1, as on 0x99ac)"
        m.add_liquidity_by_tick(nearest_usable_tick(low, sp), cur // sp * sp, trim_tick=False)
        self.bounds = (price / Decimal(self.k[0]), price * Decimal(self.k[1]))
        self.events.append((t, kind))


batch.GatedPool = RobustGated  # pool_lp_batch.run builds the gated strategy from this name; the workers fork after

EXISTING = {(100, 140, 101), (50, 140, 101), (200, 140, 101), (100, 120, 101), (100, 160, 101)}
SETS = {
    "h24": [rcfg(f"{v}_s{k:+d}", shift=k, **kw) for k in placebo_shifts()
            for v, kw in (("g_down", LADDER), ("g_spot100", {}))],
    "h25": [rcfg(f"{v}_d{d}", delay=d, **kw) for d in (1, 4) for v, kw in (("g_down", LADDER), ("g_spot100", {}))],
    "h26": [rcfg("g_down_d1x", daily_check=True, **LADDER),
            rcfg("g_down_d1x_10k", initial=10_000, daily_check=True, **LADDER)],
    "h27": [rcfg(f"gd_{lo}_{up}", ema=e, off="range", off_width=LOWS[lo], off_up=UPS[up])
            for e in (50, 100, 200) for lo in LOWS for up in UPS if (e, lo, up) not in EXISTING],
}


def net(path: str) -> float:
    n = pd.read_csv(path, index_col=0, parse_dates=True)["net"]
    return n.iloc[-1] / n.iloc[0] - 1


def nav_path(version: str, ema: int, start: date) -> str:
    """The NAV file of one window; H4b's g_down lives in pool_lp_windows.py's folder."""
    paths = [f"{batch.RESULT_DIR}/nav_99ac_{version}_ema{ema}_{start}.csv"]
    if version == "g_down" and ema == 100:
        paths.insert(0, f"result/pool-lp-windows/nav_g_down_{start}.csv")
    for p in paths:
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"no NAV for {version} ema{ema} {start}: {paths}")


def cell(version: str, ema: int = 100) -> pd.Series:
    starts = batch.window_starts("99ac")
    return pd.Series([net(nav_path(version, ema, s)) for s in starts], index=starts)


def verdict(x: pd.Series) -> str:
    c = batch.checks(x)
    return "PASS" if all(c.values()) else "fail: " + "; ".join(k for k, ok in c.items() if not ok)


def line(label: str, x: pd.Series) -> str:
    h = len(x) // 2
    return (f"{label}: median {x.median():+.4f}, positive {(x > 0).sum()}/{len(x)}, "
            f"halves {x.iloc[:h].median():+.4f} / {x.iloc[h:].median():+.4f} -> {verdict(x)}")


def real_median() -> float:
    return float((cell("g_down") - cell("g_spot100")).median())


def report_h24():
    real = real_median()
    meds = pd.Series({k: (cell(f"g_down_s{k:+d}") - cell(f"g_spot100_s{k:+d}")).median() for k in placebo_shifts()})
    n_ge = int((meds >= real).sum())
    print(f"H24 real gate median {real:+.4f}; placebo medians (by shift, days):")
    print("  " + " ".join(f"{k:+d}:{v * 100:+.1f}" for k, v in meds.sort_index().items()))
    print(f"  placebos >= real: {n_ge}/20, median of placebo medians {meds.median():+.4f}")
    if n_ge <= 4:
        print("  -> the gate's timing is the main source of the gain")
    elif meds.median() > 0:
        print("  -> the gain mostly comes from this price path, not the gate's timing")
    else:
        print("  -> neither registered case (>= 5 placebos >= real, but the placebo median <= 0)")


def report_h25():
    for d in (1, 4):
        x = cell(f"g_down_d{d}") - cell(f"g_spot100_d{d}")
        print(line(f"H25 d{d} g_down - g_spot100" + (" (listed)" if d == 4 else ""), x),
              f"| median vs H4b {x.median() - real_median():+.4f}")


def report_h26():
    t = pd.read_csv(f"{batch.RESULT_DIR}/windows_h26.csv")
    for v, ctl in (("g_down_d1x", "g_spot100"), ("g_down_d1x_10k", "g_spot100_10k")):
        print(line(f"H26 {v} - {ctl}", cell(v) - cell(ctl)))
        g = t[t["version"] == v]
        print(f"  median recentres {g['recentres'].median():.0f}, gas {g['gas'].median():.4f}")
    print(f"  g_down_d1x - g_down median: {(cell('g_down_d1x') - cell('g_down')).median():+.4f}")


def gd_name(e: int, lo: int, up: int) -> str:
    """The version name of a map cell, the 5 run before under their own names."""
    if (lo, up) == (140, 101):
        return "g_down"
    if (e, up) == (100, 101):
        return f"gd_{lo}"
    return f"gd_{lo}_{up}"


def report_h27():
    rows = []
    for e in (50, 100, 200):
        ctl = cell("g_spot100", e)
        for lo in LOWS:
            for up in UPS:
                x = cell(gd_name(e, lo, up), e) - ctl
                rows.append({"ema": e, "lower": f"p/{lo / 100:.2f}", "upper": f"p*{up / 100:.2f}",
                             "median": x.median(), "share_pos": (x > 0).mean()})
    m = pd.DataFrame(rows)
    m.to_csv(f"{batch.RESULT_DIR}/summary_h27.csv", index=False)
    print("H27 median of (cell - g_spot100), %:")
    print((m.pivot_table(index=["ema", "lower"], columns="upper", values="median") * 100).round(1).to_string())
    n = int((m["median"] > 0).sum())
    print(f"  cells with median > 0: {n}/27 ->",
          "a plateau" if n >= 20 else "a point" if n <= 10 else "in between: see which directions fail")


def daily(path: str, lo: str, hi: str, from_entry: bool) -> pd.Series:
    n = pd.read_csv(path, index_col=0, parse_dates=True)["net"]
    d = n.resample("1D").last()
    if from_entry:  # the first day measured from the $100k it started with (row 0 is already after the entry)
        d = pd.concat([pd.Series([100_000.0], index=[d.index[0] - pd.Timedelta(days=1)]), d])
    return d.pct_change().loc[lo:hi]


def report_h28(draws: int = 10_000, block: int = 30):
    parts = []
    for y in (2022, 2023, 2024, 2025):
        s = date(y, 1, 1)
        parts.append(pd.DataFrame({v: daily(nav_path(v, 100, s), f"{y}-01-01", f"{y}-12-31", True)
                                   for v in ("g_down", "g_spot100")}))
    s = date(2025, 10, 1)
    parts.append(pd.DataFrame({v: daily(nav_path(v, 100, s), "2026-01-01", "2026-09-30", False)
                               for v in ("g_down", "g_spot100")}))
    r = pd.concat(parts).dropna().to_numpy()
    n = len(r)

    def ann_excess(a: np.ndarray) -> float:
        g = np.prod(1 + a, axis=0) ** (365 / len(a)) - 1
        return float(g[0] - g[1])

    rng = np.random.default_rng(28)
    k = -(-n // block)
    stats = np.empty(draws)
    for i in range(draws):
        idx = (rng.integers(0, n, k)[:, None] + np.arange(block)).ravel()[:n] % n
        stats[i] = ann_excess(r[idx])
    lo, hi = np.percentile(stats, [5, 95])
    print(f"H28 {n} days, annualised g_down - g_spot100 {ann_excess(r):+.4f}, 90% [{lo:+.4f}, {hi:+.4f}] ->",
          "not likely luck within this path" if lo > 0 else "overlapping windows overstate it")


def report():
    pd.set_option("display.width", 250)
    for name, fn in (("h24", report_h24), ("h25", report_h25), ("h26", report_h26), ("h27", report_h27)):
        if os.path.exists(f"{batch.RESULT_DIR}/windows_{name}.csv"):
            fn()
    report_h28()


def test():
    """Defaults reproduce GatedPool, then one short run per change (start off a quarter start so no window's file
    is overwritten)."""
    s, e = date(2022, 5, 3), date(2022, 6, 20)  # gate off most of the time, so the ladder re-centres
    batch.GatedPool = GatedPool
    a = batch.run(batch.cfg("99ac", "eq_orig", gated=True, on="spot", **LADDER), s, e)
    batch.GatedPool = RobustGated
    b = batch.run(rcfg("eq_robust", **LADDER), s, e)
    print(f"equivalence: GatedPool {a['net']:.6f} ({a['recentres']} re-centres), "
          f"RobustGated {b['net']:.6f} ({b['recentres']}) -> {'OK' if abs(a['net'] - b['net']) < 1e-9 else 'DIFFERS'}")
    for c in (SETS["h24"][0], SETS["h25"][0], SETS["h26"][0], SETS["h27"][0], SETS["h27"][1]):
        r = batch.run(c, s, e)
        print(c.name, {k: r[k] for k in ("net", "recentres", "switches", "gas")}, flush=True)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--set", choices=list(SETS))
    a.add_argument("--test", action="store_true")
    a.add_argument("--report", action="store_true")
    a.add_argument("--workers", type=int, default=3)
    a = a.parse_args()
    os.makedirs(batch.RESULT_DIR, exist_ok=True)
    batch.eth_daily()  # fill the caches before the workers read them
    for span in (50, 100, 200):
        batch.gate("99ac", span)
    if a.test:
        test()
        return
    if a.set:
        tasks = [(c, s, batch.window_end(s)) for c in SETS[a.set] for s in batch.window_starts("99ac")]
        with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
            rows = pool.starmap(batch.run, tasks, chunksize=1)
        pd.DataFrame(rows).to_csv(f"{batch.RESULT_DIR}/windows_{a.set}.csv", index=False)
    if a.report or a.set:
        report()


if __name__ == "__main__":
    main()
