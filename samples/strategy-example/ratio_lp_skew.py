"""
H29 and H30 of reports/plan_2026-10-12_two_coin.md (registered 2026-10-12 in 08df3f4, before H23 ran), on top of H23
(ratio_lp_gate.py): the BTC gate decides in or out as in H23, and the WBTC/WETH ratio gate decides which way the LP
range leans.

H29  p = WETH per WBTC. Ratio gate: 4585's ratio above its EMA (pool_lp_batch.gate, from the pool's first day) = BTC
     strong against ETH. The range is [p / (1 + down), p (1 + up)], 20% wide in all:
       tr (with the trend)     BTC strong -> (down, up) = (a, b), mostly WBTC; ETH strong -> (b, a), mostly WETH
       ct (against the trend)  the other way round
     a/b in {5/15, 2/18}, ratio EMA in {50, 100, 200}, pools 4585 and cbcd: 24 sleeves; the 4 judged ones (5/15, EMA100)
     also with the ratio read at 08 and 16 UTC for H30: 32 sleeves in all. Each sleeve is one Demeter position always
     open (yield_layer.SleeveLP's frame, 40 WETH, hourly bars), checked once a day at its ratio hour: the ratio flipped
     -> remove and place the new lean; out of range -> re-centre with the current lean. Every re-placement sells the
     WBTC first and lets add_liquidity_by_value swap back, as SleeveLP does for H23's L, and pays a re-centre's gas.
     Books, combined like H23 with sleeve_sim (costs as ratio_lp_gate.py):
       L_skew   on: all in the skewed sleeve      off: parked
       L        H23's centred +/- 10% sleeve (ratio_lp_gate.py's result)
       B        H23's control
       B_tilt   on: spot at the skewed range's opening WBTC share by the same ratio gate (5/15 ~ 74/26, 2/18 ~ 89/11)
     Verdict (5/15, EMA100, $100k, per direction and pool): (L_skew - L) total > 0 and > 0 in at least two thirds of
     the calendar years (4585 2022 .. 2026: 4 of 5; cbcd 2022 .. 2024-09: 2 of 3). A direction holds if it passes on
     both pools and, on each pool, at least 3 of its other 5 variants (2/18 or EMA50 / 200, ratio at 00) have
     (L_skew - L) total > 0. H29R: cbcd 2024-10-01 .. 2026-09-30 judged as H23R (total > 0, 2025 and 2026 > 0).
     Listed: L_skew - B, L_skew - B_tilt, $1M, no gas.
H30  The BTC gate in n slices, n in {1, 2, 3, 4, 6, 8, 12, 24}: slice k holds 1/n of the book and reads the gate at
     its own hour (spot_robustness.gate(hour=)), the n hours spread evenly; every offset 0 .. 24/n - 1 of the set is
     run (worst / median / best). Each slice pays its own gas at its own size ($100k / n). The ratio inside the LP stays
     at 00, except for the 4 judged H29 versions at n = 3, offset 0, where slice k reads both gates at 00 / 08 / 16.
     Verdict: per pool, n = 3 at 00 / 08 / 16, (L_3 - B_3) meets H23's rule; for each H29 version that passed H29,
     (L_skew_3 - L_3) meets H29's rule. Listed: every n and offset, gas and trades, $1M for n in {1, 3, 6}, and one
     book that reads the gate m in {2, 3, 6} times a day (closes every 24/m hours, EMA span 100 m).

Run from samples/strategy-example after ratio_lp_gate.py --sleeves (spot price cache of spot_btc_eth_gate.py and
yield_layer's park_usdc_to2026 must exist; 4585 and cbcd in ../real-data):
  PYTHONPATH=../.. python ratio_lp_skew.py --test                   # short sleeves, then the books over them
  PYTHONPATH=../.. python ratio_lp_skew.py --sleeves --workers 3    # the 32 Demeter runs, skips finished ones
  PYTHONPATH=../.. python ratio_lp_skew.py --combine                # H29
  PYTHONPATH=../.. python ratio_lp_skew.py --slices --workers 3     # H30
"""
import argparse
import math
import multiprocessing
import os
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

import pool_lp_batch as batch
import ratio_lp_gate as rg
import spot_robustness as sr
import yield_layer as yl
from pool_lp_windows import share_of
from sleeve_sim import mainnet_gas, simulate
from spot_btc_eth_gate import load_prices
from tri_btc_eth_gate import wbtc, weth

RESULT_DIR = "result/ratio-lp-skew"
SKEWS = {"5_15": (0.05, 0.15), "2_18": (0.02, 0.18)}
DIRS = ("tr", "ct")
EMAS = (50, 100, 200)
JUDGED = ("5_15", 100)
SLICE_HOURS = (0, 8, 16)
NS = (1, 2, 3, 4, 6, 8, 12, 24)
CHECKS_A_DAY = (2, 3, 6)
PERIODS = [("4585", "2022-01-01", "2026-10-01", "H29"), ("cbcd", "2022-01-01", "2024-10-01", "H29"),
           ("cbcd", "2024-10-01", "2026-10-01", "H29R")]
CAPITALS = (None, 100_000, 1_000_000)


@dataclass(frozen=True)
class SkewSleeve(rg.RatioSleeve):
    direction: str = "tr"
    skew: str = "5_15"
    ratio_ema: int = 100
    hour: int = 0


def sleeve_name(key: str, d: str, sk: str, ema: int, hour: int = 0) -> str:
    return f"{key}_{d}_{sk}_ema{ema}" + (f"_h{hour:02d}" if hour else "")


def skew_sleeves() -> list[SkewSleeve]:
    out = []
    for key, (address, fee, spacing, lo, hi) in rg.POOLS.items():
        for d in DIRS:
            for sk in SKEWS:
                for ema in EMAS:
                    for h in (SLICE_HOURS if (sk, ema) == JUDGED else (0,)):
                        out.append(SkewSleeve(sleeve_name(key, d, sk, ema, h), address, wbtc, weth, weth,
                                              date.fromisoformat(lo), min(date.fromisoformat(hi), rg.LAST_DATA), 0.10,
                                              rg.INITIAL_WETH,
                                              fee=fee, spacing=spacing, direction=d, skew=sk, ratio_ema=ema, hour=h))
    return out


def btc_heavy(direction: str, btc_strong: bool) -> bool:
    return btc_strong if direction == "tr" else not btc_strong


_SleeveLP = yl.SleeveLP


class SkewLP(_SleeveLP):
    """SleeveLP whose range leans by the ratio gate (SkewSleeve); a plain Sleeve runs as SleeveLP."""

    def __init__(self, s):
        super().__init__(s)
        self.ratio = batch.gate("4585", s.ratio_ema, s.hour) if isinstance(s, SkewSleeve) else None
        self.side = None

    def on_bar(self, snapshot):
        if self.ratio is None:
            return super().on_bar(snapshot)
        s, t = self.s, snapshot.timestamp
        if t.minute != 0 or t.hour != s.hour:
            return
        m = self.markets[yl.KEY]
        price = m.market_status.data.price
        heavy = btc_heavy(s.direction, bool(self.ratio.asof(pd.Timestamp(t))))
        a, b = SKEWS[s.skew]
        down, up = (a, b) if heavy else (b, a)
        if self.bounds is not None and (heavy != self.side or not (self.bounds[0] <= price <= self.bounds[1])):
            m.remove_all_liquidity()
            base = self.broker.get_token_balance(s.base)
            if base > 0:
                m.swap(base, s.base, s.quote)
            self.bounds = None
            self.events.append(t)  # a flip or a re-centre
        if self.bounds is None:
            lo, hi = price / Decimal(1 + down), price * Decimal(1 + up)
            t1, t2 = m.price_to_tick(lo), m.price_to_tick(hi)
            m.add_liquidity_by_value(min(t1, t2), max(t1, t2), None)
            self.bounds, self.side = (lo, hi), heavy


yl.SleeveLP = SkewLP  # yield_layer.run_sleeve builds the strategy from this name; the workers fork after


def save_sleeve(rdir: str, name: str, out: pd.DataFrame, events: list):
    out.to_csv(f"{rdir}/sleeve_{name}.csv")
    pd.Series(pd.DatetimeIndex(events), name="t").to_csv(f"{rdir}/events_{name}.csv", index=False)


def load(rdir: str, name: str) -> tuple[pd.Series, pd.DatetimeIndex]:
    out = pd.read_csv(f"{rdir}/sleeve_{name}.csv", index_col=0, parse_dates=True)
    events = pd.read_csv(f"{rdir}/events_{name}.csv", parse_dates=["t"])["t"]
    return out["nav"], pd.DatetimeIndex(events)


def prepare_gates():
    for ema in EMAS:
        batch.gate("4585", ema)
    for h in SLICE_HOURS[1:]:
        batch.gate("4585", JUDGED[1], h)


def _run(job):
    for attempt in range(5):  # another worker may be writing the same Demeter cache file (as in pool_lp_batch.run)
        try:
            return yl.run_sleeve(*job)
        except (EOFError, OSError, ValueError):
            if attempt == 4:
                raise
            time.sleep(30)


def run_sleeves(workers: int):
    prepare_gates()
    jobs = [(s, "1h", s.start, s.end) for s in skew_sleeves() if not os.path.exists(f"{RESULT_DIR}/sleeve_{s.name}.csv")]
    print(f"{len(jobs)} sleeves to run", flush=True)
    with multiprocessing.Pool(workers, maxtasksperchild=1) as pool:
        for name, out, events, secs in pool.imap_unordered(_run, jobs):
            save_sleeve(RESULT_DIR, name, out, events)
            nav = out["nav"]
            print(f"{name}: {nav.index[0].date()} .. {nav.index[-1].date()}, total {nav.iloc[-1] / nav.iloc[0] - 1:+.2%} "
                  f"in WETH, {len(events)} re-placements, {secs:.0f} s", flush=True)


# ---- books ----

class Inputs:
    """Prices, the parked cash index and the gates, loaded once."""

    def __init__(self):
        self.prices, _, _ = load_prices()
        self.hours = self.prices.index
        self.eth, self.btc = self.prices["eth"], self.prices["btc"]
        park, self.ev_park = yl.load_sleeve("park_usdc", yl.HOLDOUT_TAG)
        self.cash = yl.index_on(park["nav"], self.hours, yl.FULL[0])
        self.gates = {}
        self.ratios = {}

    def gate(self, hour: int) -> pd.DataFrame:
        if hour not in self.gates:
            self.gates[hour] = sr.gate(self.prices, hour=hour)
        return self.gates[hour]

    def ratio(self, ema: int) -> pd.Series:
        if ema not in self.ratios:
            self.ratios[ema] = batch.gate("4585", ema)
        return self.ratios[ema]


def load_lp(lp_dir: str, name: str) -> tuple[pd.Series, pd.DatetimeIndex]:
    return rg.load(name) if lp_dir == rg.RESULT_DIR else load(lp_dir, name)


def lp_book(inp: Inputs, w: pd.DataFrame, lp: pd.Series, ev: pd.DatetimeIndex, lo: str, hi: str,
            capital: float | None):
    scale = 0 if capital is None else 100_000 / capital
    values = pd.DataFrame({"lp": inp.eth * yl.index_on(lp, inp.hours, lo), "cash": inp.cash})
    values = values[values.index < hi]  # trades, swaps and gas counted inside the stretch only
    gas = {s: mainnet_gas(inp.eth, scale) for s in ("lp", "cash")} if scale else None
    return simulate(pd.DataFrame({"lp": w["eth"] + w["btc"]}), values, start=lo, cost_bps={"lp": 11},
                    cash_cost_bps=0.5, gas=gas, lp={"lp": ev, "cash": inp.ev_park})


def spot_book(inp: Inputs, w: pd.DataFrame, lo: str, hi: str, capital: float | None):
    scale = 0 if capital is None else 100_000 / capital
    values = pd.DataFrame({"eth": inp.eth, "btc": inp.btc, "cash": inp.cash})
    values = values[values.index < hi]
    gas = {"cash": mainnet_gas(inp.eth, scale)} if scale else None
    return simulate(w, values, start=lo, cost_bps={"eth": 10, "btc": 10}, cash_cost_bps=0.5, gas=gas,
                    lp={"cash": inp.ev_park})


def tilt_weights(inp: Inputs, w: pd.DataFrame, direction: str, sk: str, ema: int) -> pd.DataFrame:
    a, b = SKEWS[sk]
    heavy_share = share_of(1 + a, 1 + b)  # WBTC's value share of a fresh [p / (1 + a), p (1 + b)]
    strong = inp.ratio(ema).reindex(w.index, method="ffill").fillna(False).astype(bool)
    heavy = strong if direction == "tr" else ~strong
    btc_share = np.where(heavy, heavy_share, 1 - heavy_share)
    on = (w["eth"] + w["btc"]).to_numpy()
    return pd.DataFrame({"eth": on * (1 - btc_share), "btc": on * btc_share}, index=w.index)


def row_of(nav: pd.Series, lo: str, hi: str, trades: int, paid: dict) -> dict:
    nav = nav[nav.index < hi]
    st = sr.stats(nav, lo, hi)
    row = {"total": st["total"], "maxDD": st["maxDD"], "trades": trades, "swap $": round(paid["swap"]),
           "gas $": round(paid["gas"])}
    row.update({y0[:4]: sr.stats(nav, y0, y1)["total"] for y0, y1 in rg.years_of(lo, hi)})
    return row


def rule(a: pd.Series, b: pd.Series, lo: str, hi: str, test: str) -> tuple[bool, dict, str]:
    """H23's rule on (a - b), or H23R's on the 2024-10 .. 2026-09 stretch."""
    yrs = [y0[:4] for y0, _ in rg.years_of(lo, hi)]
    diff = {y: a[y] - b[y] for y in yrs}
    if test.endswith("R"):
        return a["total"] - b["total"] > 0 and diff["2025"] > 0 and diff["2026"] > 0, diff, "2025 and 2026 > 0"
    need = math.ceil(2 * len(yrs) / 3)
    return (a["total"] - b["total"] > 0 and sum(v > 0 for v in diff.values()) >= need, diff,
            f"needs {need}/{len(yrs)} years > 0")


def combine(rdir: str = RESULT_DIR, l_dir: str = rg.RESULT_DIR, periods=PERIODS, capitals=CAPITALS):
    inp = Inputs()
    w = inp.gate(0)
    rows = []
    for key, lo, hi, test in periods:
        for capital in capitals:
            base = {"pool": key, "test": test, "from": lo, "capital": capital or 0}
            nav, tr, paid = spot_book(inp, w, lo, hi, capital)
            rows.append({**base, "book": "B", **row_of(nav, lo, hi, tr, paid)})
            lp, ev = load_lp(l_dir, f"{key}_w10")
            nav, tr, paid = lp_book(inp, w, lp, ev, lo, hi, capital)
            rows.append({**base, "book": "L", **row_of(nav, lo, hi, tr, paid)})
            for d in DIRS:
                for sk in SKEWS:
                    for ema in EMAS:
                        name = sleeve_name(key, d, sk, ema)
                        if not os.path.exists(f"{rdir}/sleeve_{name}.csv"):
                            continue
                        lp, ev = load(rdir, name)
                        nav, tr, paid = lp_book(inp, w, lp, ev, lo, hi, capital)
                        rows.append({**base, "book": name, **row_of(nav, lo, hi, tr, paid)})
                        nav, tr, paid = spot_book(inp, tilt_weights(inp, w, d, sk, ema), lo, hi, capital)
                        rows.append({**base, "book": f"tilt_{d}_{sk}_ema{ema}", **row_of(nav, lo, hi, tr, paid)})
    t = pd.DataFrame(rows)
    t.to_csv(f"{rdir}/combine_h29.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(t.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    verdicts(t, periods)
    return t


def verdicts(t: pd.DataFrame, periods) -> dict:
    passed = {}
    for key, lo, hi, test in periods:
        part = t[(t["pool"] == key) & (t["test"] == test) & (t["capital"] == 100_000)].set_index("book")
        if "L" not in part.index:
            continue
        L, B = part.loc["L"], part.loc["B"]
        for d in DIRS:
            judged = sleeve_name(key, d, *JUDGED)
            if judged not in part.index:
                continue
            ok, diff, need = rule(part.loc[judged], L, lo, hi, test)
            others = [sleeve_name(key, d, sk, ema) for sk in SKEWS for ema in EMAS
                      if (sk, ema) != JUDGED and sleeve_name(key, d, sk, ema) in part.index]
            n_pos = sum(part.loc[o, "total"] - L["total"] > 0 for o in others)
            tilt = part.loc[f"tilt_{d}_{JUDGED[0]}_ema{JUDGED[1]}"]
            print(f"{test} {key} {d} 5/15 EMA100: L_skew - L total {part.loc[judged, 'total'] - L['total']:+.4f}, by year "
                  + " ".join(f"{y} {v:+.3f}" for y, v in diff.items())
                  + f" -> {'PASS' if ok else 'fail'} ({need}); other variants with total > L: {n_pos}/{len(others)}; "
                  f"listed: - B {part.loc[judged, 'total'] - B['total']:+.4f}, - B_tilt "
                  f"{part.loc[judged, 'total'] - tilt['total']:+.4f}")
            if test == "H29":
                passed[(key, d)] = (ok, n_pos >= 3)
    for d in DIRS:
        cells = [passed.get((key, d)) for key in rg.POOLS]
        if None in cells:
            continue
        holds = all(ok and robust for ok, robust in cells)
        print(f"H29 direction {d}: " + ", ".join(f"{k} {'pass' if c[0] else 'fail'}/{'3+ of 5' if c[1] else '<3 of 5'}"
                                                   for k, c in zip(rg.POOLS, cells))
              + f" -> {'HOLDS' if holds else 'does not hold'}")
    return passed


# ---- H30 ----

_INPUTS = None


def _init_inputs():
    global _INPUTS
    _INPUTS = Inputs()


def slice_job(args):
    """One slice: its book with the BTC gate at hour h and 1/n of the capital, normalised to 1."""
    kind, key, lo, hi, h, capital, lp_name, lp_dir = args
    inp = _INPUTS
    w = inp.gate(h)
    if kind == "B":
        nav, tr, paid = spot_book(inp, w, lo, hi, capital)
    else:
        lp, ev = load_lp(lp_dir, lp_name)
        nav, tr, paid = lp_book(inp, w, lp, ev, lo, hi, capital)
    return args, nav[nav.index < hi] / 100_000, tr, paid


def h30_books(key: str, rdir: str, l_dir: str) -> dict:
    """book -> (kind, LP sleeve at ratio hour 0, its dir, the sleeve per slice hour at n = 3 offset 0 or None)."""
    books = {"B": ("B", None, None, None), "L": ("L", f"{key}_w10", l_dir, None)}
    for d in DIRS:
        name = sleeve_name(key, d, *JUDGED)
        if os.path.exists(f"{rdir}/sleeve_{name}.csv"):
            by_hour = {h: sleeve_name(key, d, *JUDGED, h) for h in SLICE_HOURS}
            if not all(os.path.exists(f"{rdir}/sleeve_{v}.csv") for v in by_hour.values()):
                by_hour = None
            books[name] = ("L", name, rdir, by_hour)
    return books


def slices(workers: int, rdir: str = RESULT_DIR, l_dir: str = rg.RESULT_DIR, periods=PERIODS, ns=NS):
    jobs, plan = [], []
    for key, lo, hi, test in periods:
        books = h30_books(key, rdir, l_dir)
        for n in ns:
            step = 24 // n
            for off in range(step):
                hours = [off + k * step for k in range(n)]
                caps = [100_000] + ([1_000_000] if n in (1, 3, 6) and off == 0 else [])
                for cap in caps:
                    for book, (kind, lp_name, lp_dir, by_hour) in books.items():
                        parts = []
                        for h in hours:
                            name = by_hour[h] if (by_hour and n == 3 and off == 0) else lp_name
                            parts.append((kind, key, lo, hi, h, cap / n, name, lp_dir))
                        jobs += parts
                        plan.append((key, lo, hi, test, n, off, cap, book, parts))
    jobs = list(dict.fromkeys(jobs))
    print(f"H30: {len(jobs)} slice runs", flush=True)
    with multiprocessing.Pool(workers, initializer=_init_inputs) as pool:
        done = {args: (nav, tr, paid) for args, nav, tr, paid in pool.imap_unordered(slice_job, jobs, chunksize=4)}
    rows = []
    for key, lo, hi, test, n, off, cap, book, parts in plan:
        nav = pd.concat([done[p][0] for p in parts], axis=1).ffill().mean(axis=1)
        # each slice's costs are in units of its own book scaled to $100k, so the book pays their mean
        row = row_of(nav, lo, hi, sum(done[p][1] for p in parts),
                     {k: sum(done[p][2][k] for p in parts) / n for k in ("swap", "gas")})
        rows.append({"pool": key, "test": test, "from": lo, "n": n, "offset": off, "capital": cap, "book": book, **row})
    rows += checks_a_day(l_dir, periods)
    t = pd.DataFrame(rows)
    t.to_csv(f"{rdir}/slices_h30.csv", index=False)
    h30_report(t, periods, rdir)
    return t


def checks_a_day(l_dir: str, periods) -> list[dict]:
    """Listed: one book that reads the BTC gate m times a day, on closes every 24/m hours with an EMA of 100 m."""
    inp = Inputs()
    rows = []
    for m in CHECKS_A_DAY:
        c = inp.prices[inp.prices.index.hour % (24 // m) == 0]
        ema = c.ewm(span=100 * m, adjust=False).mean()
        on = (c["btc"] > ema["btc"]).astype(float)
        w = pd.DataFrame({"eth": 0.5 * on, "btc": 0.5 * on}, index=c.index)
        for key, lo, hi, test in periods:
            nav, tr, paid = spot_book(inp, w, lo, hi, 100_000)
            rows.append({"pool": key, "test": test, "from": lo, "n": f"m{m}", "offset": 0, "capital": 100_000,
                         "book": "B", **row_of(nav, lo, hi, tr, paid)})
            lp, ev = load_lp(l_dir, f"{key}_w10")
            nav, tr, paid = lp_book(inp, w, lp, ev, lo, hi, 100_000)
            rows.append({"pool": key, "test": test, "from": lo, "n": f"m{m}", "offset": 0, "capital": 100_000,
                         "book": "L", **row_of(nav, lo, hi, tr, paid)})
    return rows


def h30_report(t: pd.DataFrame, periods, rdir: str):
    pd.set_option("display.width", 250)
    passed = {}
    if os.path.exists(f"{rdir}/combine_h29.csv"):
        passed = verdicts(pd.read_csv(f"{rdir}/combine_h29.csv", dtype={"pool": str}), periods)
    t = t.assign(n=t["n"].astype(str))
    for key, lo, hi, test in periods:
        p = t[(t["pool"] == key) & (t["test"] == test)]
        one = p[(p["n"] == "3") & (p["offset"] == 0) & (p["capital"] == 100_000)].set_index("book")
        if {"B", "L"} <= set(one.index):
            ok, diff, need = rule(one.loc["L"], one.loc["B"], lo, hi, test)
            print(f"H30 {test} {key} n=3 00/08/16: L_3 - B_3 total {one.loc['L', 'total'] - one.loc['B', 'total']:+.4f}, "
                  "by year " + " ".join(f"{y} {v:+.3f}" for y, v in diff.items()) + f" -> {'PASS' if ok else 'fail'} ({need})")
        for d in DIRS:
            name = sleeve_name(key, d, *JUDGED)
            if name in one.index:
                ok, diff, need = rule(one.loc[name], one.loc["L"], lo, hi, test)
                judged = passed.get((key, d), (False, False))[0] if test == "H29" else True
                print(f"H30 {test} {key} {d} n=3: L_skew_3 - L_3 total {one.loc[name, 'total'] - one.loc['L', 'total']:+.4f}"
                      f" -> {('PASS' if ok else 'fail') if judged else 'listed (did not pass H29)'} ({need})")
        rows = []
        for n in [x for x in [str(v) for v in NS] + [f"m{m}" for m in CHECKS_A_DAY] if x in set(p["n"])]:
            q = p[(p["n"] == n) & (p["capital"] == 100_000)]
            lq, bq = q[q["book"] == "L"].set_index("offset"), q[q["book"] == "B"].set_index("offset")
            x = lq["total"] - bq["total"]
            rows.append({"n": n, "L-B worst": x.min(), "median": x.median(), "best": x.max(),
                         "B median": bq["total"].median(), "L median": lq["total"].median(),
                         "L gas $": lq["gas $"].median(), "L trades": lq["trades"].median()})
        print(f"  {test} {key} by n ($100k, listed):")
        print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f"{v:+.4f}"))


# ---- test ----

def test():
    """Short skewed and centred sleeves over 2023-01 .. 03 (in result/ratio-lp-skew/test), then H29's books and H30's
    slices over them."""
    rdir = f"{RESULT_DIR}/test"
    os.makedirs(rdir, exist_ok=True)
    prepare_gates()
    lo, hi = "2023-01-01", "2023-04-01"  # BTC gate on from mid-January, the ratio flips
    address, fee, spacing, _, _ = rg.POOLS["4585"]
    keep = {sleeve_name("4585", d, *JUDGED, h) for d in DIRS for h in SLICE_HOURS}
    jobs = [SkewSleeve(**{**s.__dict__, "start": date(2023, 1, 1), "end": date(2023, 3, 31)})
            for s in skew_sleeves() if s.name in keep]
    jobs.append(rg.RatioSleeve("4585_w10", address, wbtc, weth, weth, date(2023, 1, 1), date(2023, 3, 31), 0.10,
                               rg.INITIAL_WETH, fee=fee, spacing=spacing))
    for s in jobs:
        name, out, events, secs = yl.run_sleeve(s, "1h", s.start, s.end)
        save_sleeve(rdir, name, out, events)
        print(f"{name}: total {out['nav'].iloc[-1] - 1:+.4f} in WETH, {len(events)} re-placements, {secs:.0f} s",
              flush=True)
    ratio = batch.gate("4585", 100).loc[lo:hi].astype(int)
    print(f"ratio gate (BTC strong) {lo} .. {hi}: {ratio.sum()}/{len(ratio)} days, flips {int(ratio.diff().abs().sum())}")
    periods = [("4585", lo, hi, "H29")]
    combine(rdir, rdir, periods, (100_000,))
    slices(1, rdir, rdir, periods, (1, 3))


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--test", action="store_true")
    a.add_argument("--sleeves", action="store_true")
    a.add_argument("--combine", action="store_true")
    a.add_argument("--slices", action="store_true")
    a.add_argument("--workers", type=int, default=3)
    a = a.parse_args()
    os.makedirs(RESULT_DIR, exist_ok=True)
    if a.test:
        test()
        return
    if a.sleeves:
        run_sleeves(a.workers)
    if a.combine:
        combine()
    if a.slices:
        slices(a.workers)


if __name__ == "__main__":
    main()
