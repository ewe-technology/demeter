"""
Daily simulator of Maker's ETH/USDC defense v1 / v2 / v3 spec sheets (Drive: "ETH-USDC MGL 規格書 v2", "... v3"), for the
overfitting tests in VALIDATION-2026-10-13-defense-v1-v3.md.

Signal engine: the virtual accounts of gamma_maker_defense_ethusdc_v3.py (branch maker-defense), copied with the
module constants turned into a Config. Real account: spec v3 section 4 (one valley ladder, upper rebuild, lower stop,
follow F' at 12.5 %). Rewards: spec v2 section 6 model, daily reward = k(year) x active liquidity at the close x
sqrt(close), k calibrated so that a signal-free valley 40 % earns the spec's yearly dollars (2022-25), other years at
the 2022-25 mean. Swap cost 0.1 % of the swapped value. Standard mode pays rewards out; compound mode reinvests them at
each month end at the current LP ratio.

Closes for decision hour h are the Binance ETHUSDT 1 h closes at h:00 UTC (samples/binance_ethusdt_1h.csv, built from
data.binance.vision); h = 0 is the spec's daily close.

    python spec_daily_sim.py check      # reproduction table (T0)
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

HOURLY_CSV = Path(__file__).resolve().parents[2] / "binance_ethusdt_1h.csv"
WEIGHTS = [0.012, 0.046, 0.088, 0.130, 0.160, 0.180, 0.190, 0.194]  # spec section 4, centre outward, one side
BAND_STEP = 0.025
EMA_SPANS = (90, 100, 110, 120)
SPEC_REWARD = {2022: 25_898, 2023: 29_796, 2024: 46_687, 2025: 34_867}  # signal-free valley 40 %, $100k from 1/1


@dataclass(frozen=True)
class Config:
    name: str = "v2"
    refill: tuple = (1.075, 1.125, 1.175, 1.225)  # close / low for stages 1..4
    confirm_days: int = 3
    f_by_value: bool = True
    weak_share: float | None = 0.25               # virtual share below EMA100 x 0.95 (None = v1: no weak share)
    spec_start: bool = True
    div_on: float | None = None                   # v3: 0.40
    div_off: float = 0.20
    follow: float = 0.125
    swap_cost: float = 0.001
    reward_mult: float = 1.0                      # T9: 0.8
    signal: str = "ema"                           # "ema" or "given" (T8a: F' supplied from outside)


V1 = Config("v1", refill=(1.05, 1.0833, 1.1167, 1.15), f_by_value=False, weak_share=None, spec_start=False)
V2 = Config("v2")
V3 = Config("v3", div_on=0.40, div_off=0.20)
VERSIONS = {"v1": V1, "v2": V2, "v3": V3}


# ---------------------------------------------------------------- ladder maths (USD per ETH)
def build_ladder(value: float, centre: float, eth_share: float, uniform: bool = False):
    """(lo, hi, liquidity) per band holding `value` at `centre`: eth_share as ETH above, the rest as USDC below."""
    side = [1 / 8] * 8 if uniform else WEIGHTS
    tot = sum(side)
    bands = []
    for i, w in enumerate(side):
        lo, hi = centre * (1 + BAND_STEP * i), centre * (1 + BAND_STEP * (i + 1))
        eth = value * eth_share * w / tot / centre
        bands.append((lo, hi, eth / (1 / math.sqrt(lo) - 1 / math.sqrt(hi))))
        hi2, lo2 = centre * (1 - BAND_STEP * i), centre * (1 - BAND_STEP * (i + 1))
        usd = value * (1 - eth_share) * w / tot
        bands.append((lo2, hi2, usd / (math.sqrt(hi2) - math.sqrt(lo2))))
    return bands


def ladder_amounts(bands, price: float):
    """(eth, usd) held by the ladder at `price`."""
    eth = usd = 0.0
    for lo, hi, liq in bands:
        if price <= lo:
            eth += liq * (1 / math.sqrt(lo) - 1 / math.sqrt(hi))
        elif price >= hi:
            usd += liq * (math.sqrt(hi) - math.sqrt(lo))
        else:
            eth += liq * (1 / math.sqrt(price) - 1 / math.sqrt(hi))
            usd += liq * (math.sqrt(price) - math.sqrt(lo))
    return eth, usd


def ladder_value(bands, price: float) -> float:
    eth, usd = ladder_amounts(bands, price)
    return eth * price + usd


def active_liquidity(bands, price: float) -> float:
    return sum(liq for lo, hi, liq in bands if lo <= price < hi)


# ---------------------------------------------------------------- signal engine (copy of maker-defense v3 VirtualAccount)
@dataclass
class VirtualAccount:
    span: int
    cfg: Config
    armed: bool = False
    deployed: float = 0.0
    assets: float = 1.0
    cash: float = 1.0
    bands: list = field(default_factory=list)
    centre: float | None = None
    low: float | None = None
    stage: int = 0
    confirm: int = 0
    started: bool = False

    def exit(self, close, assets):
        self.cash, self.bands = assets, []
        self.centre, self.low, self.stage, self.confirm = None, close, 0, 0

    def build(self, close, ema, ema100, assets, lp_value):
        if self.cfg.weak_share is not None and close < ema100 * 0.95:
            share = self.cfg.weak_share
        else:
            share = 0.7 if close > ema else 0.5
        self.bands, self.cash, self.centre = build_ladder(lp_value, close, share), assets - lp_value, close

    def step(self, close, ema, ema100):
        lp = ladder_value(self.bands, close) if self.bands else 0.0
        assets = self.cash + lp
        if not self.started:
            self.started, self.armed = True, (close >= ema if self.cfg.spec_start else close > ema)
            if self.armed:
                self.stage, lp = 4, assets
                self.build(close, ema, ema100, assets, lp)
            else:
                self.low = close
        else:
            if self.armed and close < ema:
                self.exit(close, assets)
                self.armed, lp = False, 0.0
            elif not self.armed and close > ema:
                self.armed = True
            if self.stage > 0 and close < self.centre * 0.80:
                self.exit(close, assets)
                lp = 0.0
            elif self.stage > 0 and close > self.centre * 1.20:
                self.build(close, ema, ema100, assets, lp)
            if self.stage < 4:
                self.low = min(self.low, close)
                self.confirm = self.confirm + 1 if close >= self.low * self.cfg.refill[0] else 0
                nxt = self.stage + 1
                advance = (self.confirm >= self.cfg.confirm_days if nxt == 1
                           else close >= self.low * self.cfg.refill[nxt - 1])
                if advance:
                    self.stage, lp = nxt, nxt / 4 * assets
                    self.build(close, ema, ema100, assets, lp)
        self.assets = assets
        self.deployed = lp / assets if self.cfg.f_by_value else self.stage / 4


def signal_frame(close: pd.Series, cfg: Config) -> pd.DataFrame:
    """close, ema100, F and F' per day from the first close (EMA seed) on."""
    c = close.to_numpy(float)
    emas = {n: close.ewm(span=n, adjust=False).mean().to_numpy() for n in EMA_SPANS}
    accounts = [VirtualAccount(n, cfg) for n in EMA_SPANS]
    F = np.zeros(len(c))
    for i in range(len(c)):
        if i or not cfg.spec_start:
            for a in accounts:
                a.step(c[i], emas[a.span][i], emas[100][i])
        F[i] = sum(a.deployed for a in accounts) / 4
    out = pd.DataFrame({"close": c, "ema": emas[100], "F": F}, index=close.index)
    d = out["close"] / out["ema"] - 1
    flag = np.zeros(len(c), dtype=int)
    if cfg.div_on is not None:
        on = False
        for i, x in enumerate(d.to_numpy()):
            on = x >= (cfg.div_off if on else cfg.div_on)
            flag[i] = on
    out["diverged"] = flag
    out["Fp"] = np.where(flag == 1, 0.0, F)
    return out


# ---------------------------------------------------------------- prices
@lru_cache(maxsize=None)
def hourly() -> pd.Series:
    s = pd.read_csv(HOURLY_CSV, parse_dates=["open_time"]).set_index("open_time")["close"].astype(float)
    s.index = s.index + pd.Timedelta(hours=1)  # close time
    return s


@lru_cache(maxsize=None)
def daily_closes(hour: int = 0) -> pd.Series:
    """Close at hour:00 UTC each day, indexed by the judged day D (hour 0 -> the close of D's daily candle, at D+1 00:00)."""
    s = hourly()
    s = s[s.index.hour == hour]
    idx = s.index - pd.Timedelta(days=1) if hour == 0 else s.index
    out = pd.Series(s.to_numpy(), index=idx.normalize())
    out = out[~out.index.duplicated()]
    return out.asfreq("1D").ffill()


@lru_cache(maxsize=None)
def signal_cached(cfg: Config, hour: int) -> pd.DataFrame:
    return signal_frame(daily_closes(hour), cfg)


# ---------------------------------------------------------------- real account
@dataclass
class Result:
    equity: pd.Series      # principal + paid-out rewards (standard) or principal (compound), daily
    rewards: float
    swap_cost: float
    rebuilds: int

    @property
    def terminal(self):
        return float(self.equity.iloc[-1])

    @property
    def maxdd(self):
        e = self.equity.to_numpy()
        return float((e / np.maximum.accumulate(e) - 1).min())


def run(cfg: Config, start, end, hour: int = 0, mode: str = "standard", k: dict | None = None,
        fp: pd.Series | None = None, closes: pd.Series | None = None, plain: bool = False,
        no_signal: bool = False) -> Result:
    """One account from `start` (decision on that day's close) to `end`, $100k. `fp` overrides F'; `closes` overrides
    the price path (Monte Carlo); `plain` = uniform ±20 % LP rebuilt on any exit; `no_signal` = valley always full,
    rebuilt on any exit (the spec's reward calibration run)."""
    if closes is None:
        sig = signal_cached(cfg, hour)
    else:
        sig = signal_frame(closes, cfg)
    sig = sig.loc[pd.Timestamp(start):pd.Timestamp(end)]
    target = fp.reindex(sig.index).to_numpy() if fp is not None else sig["Fp"].to_numpy()
    k = k if k is not None else reward_coefficients()
    cash, bands, centre = 100_000.0, [], None
    paid = pending = cost_total = 0.0
    rebuilds = 0
    eq = np.zeros(len(sig))
    closes_arr, ema_arr = sig["close"].to_numpy(), sig["ema"].to_numpy()
    months = sig.index.month
    years = sig.index.year

    def rebuild(price, size, ema):
        nonlocal cash, bands, centre, cost_total, rebuilds
        eth0, usd0 = ladder_amounts(bands, price) if bands else (0.0, 0.0)
        total = cash + eth0 * price + usd0
        if size <= 0:
            new_bands, eth1 = [], 0.0
        else:
            share = 0.5 if plain else (0.7 if price > ema else 0.5)
            new_bands = build_ladder(size * total, price, share, uniform=plain)
            eth1 = ladder_amounts(new_bands, price)[0]
        c = abs(eth1 - eth0) * price * cfg.swap_cost
        cost_total += c
        lp_new = ladder_value(new_bands, price) if new_bands else 0.0
        cash = total - lp_new - c
        bands, centre = new_bands, (price if new_bands else None)
        rebuilds += 1

    for i, p in enumerate(closes_arr):
        # rewards for the day just ended, earned by the ladder held through it, valued at this close
        if bands:
            r = k.get(int(years[i]), k["mean"]) * cfg.reward_mult * active_liquidity(bands, p) * math.sqrt(p)
            if mode == "standard":
                paid += r
            else:
                pending += r
        lp = ladder_value(bands, p) if bands else 0.0
        assets = cash + lp
        if mode == "compound" and i and months[i] != months[i - 1] and pending > 0:
            ratio = lp / assets if assets else 0.0
            if bands and ratio > 0:
                g = ratio * pending / lp
                eth_add = ladder_amounts(bands, p)[0] * g
                bands = [(lo, hi, liq * (1 + g)) for lo, hi, liq in bands]
                c = eth_add * p * cfg.swap_cost
                cash += pending - ratio * pending - c
                cost_total += c
            else:
                cash += pending
            pending = 0.0
            lp = ladder_value(bands, p) if bands else 0.0
            assets = cash + lp
        if i == 0:
            rebuild(p, 1.0 if (plain or no_signal) else target[i], ema_arr[i])
        elif plain or no_signal:
            if p > centre * 1.20 or p < centre * 0.80:
                rebuild(p, 1.0, ema_arr[i])
        else:
            f = target[i]
            if bands and p > centre * 1.20:
                rebuild(p, lp / assets, ema_arr[i])
            elif bands and p < centre * 0.80:
                rebuild(p, 0.0, ema_arr[i])
            lp = ladder_value(bands, p) if bands else 0.0
            cur = lp / (cash + lp)
            if (abs(f - cur) >= cfg.follow or (f == 0 and cur > 0)
                    or (f >= 0.999 and cur < 0.99)):
                rebuild(p, f, ema_arr[i])
        lp = ladder_value(bands, p) if bands else 0.0
        eq[i] = cash + lp + paid + pending
    return Result(pd.Series(eq, index=sig.index), paid + pending, cost_total, rebuilds)


@lru_cache(maxsize=None)
def _k_cached() -> tuple:
    k = {}
    for y, target in SPEC_REWARD.items():
        r = run(V2, f"{y}-01-01", f"{y}-12-31", k={y: 1.0, "mean": 1.0}, no_signal=True)
        k[y] = target / r.rewards
    k["mean"] = float(np.mean([k[y] for y in SPEC_REWARD]))
    return tuple(k.items())


def reward_coefficients() -> dict:
    return dict(_k_cached())


# ---------------------------------------------------------------- T0 reproduction
SPEC_TABLE = [  # (label, version, start, end, mode, spec $k)
    ("v2 std 2021-05-05..2026-08-31", "v2", "2021-05-05", "2026-08-31", "standard", 186.2),
    ("v3 std 2021-05-05..2026-08-31", "v3", "2021-05-05", "2026-08-31", "standard", 231.9),
    ("v2 cmp 2021-05-05..2026-08-31", "v2", "2021-05-05", "2026-08-31", "compound", 262.5),
    ("v3 cmp 2021-05-05..2026-08-31", "v3", "2021-05-05", "2026-08-31", "compound", 323.7),
    ("v2 std 2022-01-01..2025-12-31", "v2", "2022-01-01", "2025-12-31", "standard", 185.9),
    ("v2 cmp 2022-01-01..2025-12-31", "v2", "2022-01-01", "2025-12-31", "compound", 224.5),
    ("v2 std 2018-01-01..2025-12-31", "v2", "2018-01-01", "2025-12-31", "standard", 178.9),
] + [(f"v2 std {y}", "v2", f"{y}-01-01", f"{y}-12-31", "standard", v) for y, v in
     {2018: 78.9, 2019: 85.9, 2020: 189.6, 2021: 162.6, 2022: 115.1, 2023: 123.1, 2024: 125.2, 2025: 128.7}.items()]

SPEC_SHIFT = [("v2 std 2021-05..2026-08 24h mean", "v2", 142.8), ("v3 std 2021-05..2026-08 24h mean", "v3", 193.4)]


def check():
    print("k:", {kk: round(v, 4) for kk, v in reward_coefficients().items()})
    for label, v, s, e, mode, spec in SPEC_TABLE:
        r = run(VERSIONS[v], s, e, mode=mode)
        print(f"{label:34s} sim {r.terminal / 1e3:7.1f}  spec {spec:6.1f}  gap {r.terminal / 1e3 / spec - 1:+6.1%}"
              f"  maxDD {r.maxdd:6.1%}")
    for label, v, spec in SPEC_SHIFT:
        vals = [run(VERSIONS[v], "2021-05-05", "2026-08-31", hour=h).terminal / 1e3 for h in range(24)]
        print(f"{label:34s} sim {np.mean(vals):7.1f}  spec {spec:6.1f}  gap {np.mean(vals) / spec - 1:+6.1%}")


if __name__ == "__main__":
    {"check": check}[sys.argv[1]]()
