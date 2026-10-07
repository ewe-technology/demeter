"""
H2 - H4 of reports/single_pool_loop.md: LPs in a 0.3% WBTC/stable pool against holding, in Demeter on minute bars.

One position of [p/k_down, p k_up], k = 1 + width, checked at every full hour; out of range -> remove and re-centre
with add_liquidity_by_value, which swaps the difference in the same 0.3% pool (single_pool_backtest.SinglePool, no
breaker). $100k of the stablecoin, which is also the quote. Demeter adds our own liquidity to the pool's when sharing
fees (market.py).

Gated versions (H4b) switch at 00:00 UTC on the BTC gate: on while the pool's previous daily close is above its
EMA100 (pandas ewm span 100, adjust=False, over every daily close from the pool's first day). Each state is one of
  range   the position above, re-centred hourly when out of range
  spot    hold `spot_weight` of the value in WBTC, the rest in the stablecoin (swapped at the switch only)
  cash    all stablecoin
A switch removes the position and swaps straight to the new state.

Costs, all subtracted from net value:
  swap fee   0.3%, charged by Demeter
  impact     not in Demeter: each swap of N USD also costs N x N / (L sqrt(P)) (raw units, L and P of the pool at the
             swap's minute), the arbitrum_check.py formula, uncapped
  gas        tri_btc_eth_gate.GAS_UNITS per action x the year's gwei (2026: 3) x the ETH price (88e6 daily close)

Windows: 12 months starting on the first day of every quarter, 2022-01 .. 2025-10 (16 windows, the last ends
2026-09-30), each from cash.

Excess = net after all costs minus holding, from the window's first bar, the WBTC share that the first position
holds (0.5 for a symmetric range). Listed with it (H4a on): the hourly average WBTC weight of the book, and the excess
over holding that weight, rebalanced daily ("matched").

Verdicts, each fixed before its run (commit of this file):
  H2   w10, w20 in 0x99ac. A version passes if, over the 16 windows, the excess
         1. has a median > 0,
         2. is > 0 in at least 12 windows,
         3. has a median > 0 both over the 8 windows starting in 2022-2023 and over the 8 starting in 2024-2025.
  H3a  w30, w50 in 0x99ac: both must meet 1-3, and each must have a median excess >= -10% over the five rally
       windows (50/50 hold above +50% in H2: starts 2023-01, 2023-04, 2023-07, 2023-10, 2024-01).
  H3b  usdt_w20, +/-20% in 0x9Db9 (WBTC/USDT 0.3%): meets 1-3.
  H3c  asymmetric ranges in 0x99ac, excess against holding the first position's WBTC share: skew_up [p/1.10, p 1.33],
       skew_down [p/1.33, p 1.10], one_up [p/1.01, p 1.40], one_down [p/1.40, p 1.01]. Each is judged on its own
       by 1-3 plus the rally median >= -10%; the *_down versions are the controls for the direction of the skew.
       Same hourly out-of-range re-centre for all; the excess without gas is listed, not judged.
  H4a  skew_down reproduced. sd_33_10 (= skew_down, rerun to log the weight), usdt_sd_33_10 in 0x9Db9, and four
       neighbours in 0x99ac: sd_25_10, sd_50_10, sd_33_05, sd_33_15 (k_down - 1, k_up - 1 in %). Passes if
         a. usdt_sd_33_10 meets 1-3 plus the rally median >= -10%,
         b. at least 3 of the 4 neighbours meet 1-3 plus the rally median >= -10%,
         c. the matched excess has a median > 0 for both sd_33_10 and usdt_sd_33_10.
  H4b  the BTC gate in 0x99ac. Each gated LP is judged against a gated spot control with the same gate and, while
       on, the same WBTC share as its first position (excess = LP net - control net, both after all costs):
         g_up    on: one_up range [p/1.01, p 1.40]       off: cash     control: on 96.9% WBTC spot, off cash
         g_sd    on: skew_down range [p/1.33, p 1.10]    off: cash     control: on 25.9% WBTC spot, off cash
         g_sym   on: +/-20% range                         off: cash     control: on 50% WBTC spot, off cash
         g_down  on: 100% WBTC spot                       off: one_down range [p/1.40, p 1.01]
                                                                        control: on 100% WBTC spot, off cash
       A gated LP passes if its excess over the control meets 1-3. The control g_spot100 (on 100% WBTC, off cash)
       is also listed against the 50/50 hold and against holding WBTC, not judged.

Run from samples/strategy-example (minute CSVs in ../real-data/<pool>/):
  PYTHONPATH=../.. python pool_lp_windows.py --set h2        # also h3ab, h3c, h4a, h4b
  PYTHONPATH=../.. python pool_lp_windows.py --test        # w10 2022-01-01 .. 01-10, g_up and g_down 2023-01
"""
import argparse
import glob
import multiprocessing
import os
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from demeter import Actuator, Snapshot, TokenInfo
from demeter.uniswap import UniLpMarket, UniV3Pool
import pool_screen as ps
from single_pool_backtest import KEY, Config, SinglePool
from tri_btc_eth_gate import GAS_GWEI, GAS_UNITS, load_market, usdc, usdt, wbtc

RESULT_DIR = "result/pool-lp-windows"
USDC_POOL = "0x99ac8cA7087fA4A2A1FB6357269965A2014ABc35"  # WBTC / USDC 0.3%
USDT_POOL = "0x9Db9e0e53058C89e5B94e29621a205198648425B"  # WBTC / USDT 0.3%
INITIAL = 100_000
WINDOW_STARTS = [date(y, m, 1) for y in range(2022, 2026) for m in (1, 4, 7, 10)]
RALLY_STARTS = [date(2023, 1, 1), date(2023, 4, 1), date(2023, 7, 1), date(2023, 10, 1), date(2024, 1, 1)]
LAST_DAY = date(2026, 9, 30)
EMA_SPAN = 100
WORKERS = 3


@dataclass(frozen=True)
class Config30(Config):
    up: float = 0.0  # width above the price; 0 = same as below (`width`)
    gated: bool = False
    on: str = "range"  # range / spot / cash while the gate is on (range uses width, up)
    off: str = "cash"  # range / cash while the gate is off (range uses off_width, off_up)
    off_width: float = 0.0
    off_up: float = 0.0
    spot_weight: float = 1.0

    def pool(self) -> UniV3Pool:
        return UniV3Pool(token0=self.token0, token1=self.token1, fee=0.3, quote_token=self.quote, tick_spacing=60)

    @property
    def k_down(self) -> float:
        return 1 + self.width

    @property
    def k_up(self) -> float:
        return 1 + (self.up or self.width)

    def wbtc_share(self) -> float:
        """Value share of WBTC in a fresh position: x p = L (sqrt p - p / sqrt pb), y = L (sqrt p - sqrt pa)."""
        return share_of(self.k_down, self.k_up)


def share_of(k_down: float, k_up: float) -> float:
    a, b = 1 - k_up ** -0.5, 1 - k_down ** -0.5
    return a / (a + b)


def version(name: str, width: float, up: float = 0.0, pool: str = USDC_POOL, quote: TokenInfo = usdc, **kw) -> Config30:
    return Config30(name, pool, wbtc, quote, quote, INITIAL, width, up=up, **kw)


def gated(name: str, on: str, width: float = 0.0, up: float = 0.0, off: str = "cash", off_width: float = 0.0,
          off_up: float = 0.0, spot_weight: float = 1.0) -> Config30:
    return version(name, width, up, gated=True, on=on, off=off, off_width=off_width, off_up=off_up,
                   spot_weight=spot_weight)


SETS = {
    "h2": [version("w10", 0.10), version("w20", 0.20)],
    "h3ab": [version("w30", 0.30), version("w50", 0.50), version("usdt_w20", 0.20, pool=USDT_POOL, quote=usdt)],
    "h3c": [version("skew_up", 0.10, up=0.33), version("skew_down", 0.33, up=0.10),
            version("one_up", 0.01, up=0.40), version("one_down", 0.40, up=0.01)],
    "h4a": [version("sd_33_10", 0.33, up=0.10), version("usdt_sd_33_10", 0.33, up=0.10, pool=USDT_POOL, quote=usdt),
            version("sd_25_10", 0.25, up=0.10), version("sd_50_10", 0.50, up=0.10),
            version("sd_33_05", 0.33, up=0.05), version("sd_33_15", 0.33, up=0.15)],
    "h4b": [gated("g_up", "range", 0.01, 0.40), gated("g_sd", "range", 0.33, 0.10), gated("g_sym", "range", 0.20),
            gated("g_down", "spot", off="range", off_width=0.40, off_up=0.01),
            gated("g_spot97", "spot", spot_weight=share_of(1.01, 1.40)),
            gated("g_spot26", "spot", spot_weight=share_of(1.33, 1.10)),
            gated("g_spot50", "spot", spot_weight=0.5), gated("g_spot100", "spot")],
}
H4B_CONTROL = {"g_up": "g_spot97", "g_sd": "g_spot26", "g_sym": "g_spot50", "g_down": "g_spot100"}


class RangePool(SinglePool):
    """SinglePool with a range of [p / k_down, p k_up]; the symmetric case places exactly the same ticks."""

    def __init__(self, cfg: Config30):
        super().__init__(cfg, 0.0, 0.0)
        self.k = (cfg.k_down, cfg.k_up)
        self.weights = []  # (time, WBTC value / book value) at every full hour

    def place(self, price: Decimal, width: float, kind: str, t):
        m: UniLpMarket = self.markets[KEY]
        lo, hi = price / Decimal(self.k[0]), price * Decimal(self.k[1])
        t1, t2 = m.price_to_tick(lo), m.price_to_tick(hi)
        m.add_liquidity_by_value(min(t1, t2), max(t1, t2), None)
        self.bounds = (lo, hi)
        self.events.append((t, kind))

    def log_weight(self, t, price: Decimal):
        btc = self.broker.get_token_balance(self.cfg.base)
        quote = self.broker.get_token_balance(self.cfg.quote)
        if self.bounds is not None:
            status = self.markets[KEY].get_market_balance()
            btc += status.base_in_position + status.base_uncollected
            quote += status.quote_in_position + status.quote_uncollected
        btc_value = float(btc * price)
        total = btc_value + float(quote)
        self.weights.append((t, btc_value / total if total > 0 else 0.0))

    def on_bar(self, snapshot: Snapshot):
        super().on_bar(snapshot)
        if snapshot.timestamp.minute == 0:
            self.log_weight(snapshot.timestamp, self.markets[KEY].market_status.data.price)


class GatedPool(RangePool):
    def __init__(self, cfg: Config30, gate: pd.Series):
        super().__init__(cfg)
        self.gate = gate  # bool by day, known at that day's 00:00
        self.state = None
        self.mode = None

    def go(self, on: bool, price: Decimal, t):
        cfg = self.cfg
        m: UniLpMarket = self.markets[KEY]
        if self.bounds is not None:
            self.remove()
        self.state, self.mode = on, (cfg.on if on else cfg.off)
        if self.mode == "range":
            self.k = (cfg.k_down, cfg.k_up) if on else (1 + cfg.off_width, 1 + (cfg.off_up or cfg.off_width))
            self.place(price, 0.0, "on" if on else "off", t)
            return
        weight = cfg.spot_weight if self.mode == "spot" else 0.0
        btc = self.broker.get_token_balance(cfg.base)
        quote = self.broker.get_token_balance(cfg.quote)
        target = (btc * price + quote) * Decimal(weight) / price
        if target > btc and quote > 0:
            m.swap(min(quote, (target - btc) * price), cfg.quote, cfg.base)
        elif btc > target:
            m.swap(btc - target, cfg.base, cfg.quote)
        self.events.append((t, "on" if on else "off"))

    def on_bar(self, snapshot: Snapshot):
        t = snapshot.timestamp
        price = self.markets[KEY].market_status.data.price
        if self.state is None or (t.hour == 0 and t.minute == 0):
            on = bool(self.gate.asof(pd.Timestamp(t).normalize()))
            if on != self.state:
                self.go(on, price, t)
        elif t.minute == 0 and self.mode == "range" and not (self.bounds[0] <= price <= self.bounds[1]):
            self.remove()
            self.place(price, 0.0, "recentre", t)
        if t.minute == 0:
            self.log_weight(t, price)


def window_end(start: date) -> date:
    end = (pd.Timestamp(start) + pd.DateOffset(years=1) - pd.Timedelta(days=1)).date()
    return min(end, LAST_DAY)


def eth_daily() -> pd.Series:
    path = f"{RESULT_DIR}/eth_usd_daily.csv"
    if not os.path.exists(path):
        tick = ps.load_minutes(ps.POOLS["eth/usdc 5 mainnet"][0])[0]["closeTick"].resample("1D").last()
        (1e12 / np.power(1.0001, tick)).rename("eth_usd").to_csv(path)  # 88e6 price is WETH raw per USDC raw
    return pd.read_csv(path, index_col=0, parse_dates=True)["eth_usd"]


def btc_gate() -> pd.Series:
    """True on day d if the 0x99ac close of day d-1 is above its EMA100 (every file from the pool's first day)."""
    path = f"{RESULT_DIR}/btc_gate.csv"
    if not os.path.exists(path):
        files = sorted(glob.glob(f"../real-data/{USDC_POOL}/*.minute.csv"))
        df = pd.concat((pd.read_csv(f, usecols=["timestamp", "closeTick"]) for f in files), ignore_index=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        tick = pd.to_numeric(df.set_index("timestamp").sort_index()["closeTick"], errors="coerce").dropna()
        close = (np.power(1.0001, tick) * 1e2).resample("1D").last().ffill()  # USDC raw per WBTC raw x 10^(8-6)
        ema = close.ewm(span=EMA_SPAN, adjust=False).mean()
        gate = (close > ema).shift(1, fill_value=False)
        pd.DataFrame({"close": close, "ema": ema, "gate": gate}).to_csv(path)
    return pd.read_csv(path, index_col=0, parse_dates=True)["gate"].astype(bool)


def run(cfg: Config30, start: date, end: date) -> dict:
    started = time.time()
    data, _ = load_market(KEY, cfg.pool(), cfg.address, start, end, None)
    price = data["price"].astype(float)
    market = UniLpMarket(KEY, cfg.pool())
    market.data = data
    actuator = Actuator()
    actuator.broker.add_market(market)
    actuator.broker.set_balance(cfg.quote, Decimal(INITIAL))
    actuator.set_price(pd.DataFrame({wbtc.name: price, cfg.quote.name: 1.0}, index=price.index), cfg.quote)
    strategy = GatedPool(cfg, btc_gate()) if cfg.gated else RangePool(cfg)
    actuator.strategy = strategy
    actuator.run(print_result=False)

    nav = actuator.account_status_df[("net_value", "")].astype(float)
    nav.index = pd.DatetimeIndex(nav.index)
    eth = eth_daily()
    liq = data["currentLiquidity"].astype(float)
    costs, swap_fee, impact = {}, 0.0, 0.0
    for a in actuator.actions:
        ts = pd.Timestamp(a.timestamp)
        cost = 0.0
        units = GAS_UNITS.get(type(a).__name__)
        if units:
            cost += units * GAS_GWEI.get(ts.year, GAS_GWEI[2025]) * 1e-9 * float(eth.asof(ts.normalize()))
        if type(a).__name__ == "SwapAction":
            px = float(price.asof(ts))
            usd = float(a.amount) * (px if a.amount.unit.upper() == wbtc.name.upper() else 1.0)
            swap_fee += float(a.fee) * (px if a.fee.unit.upper() == wbtc.name.upper() else 1.0)
            sqrtp = (px * 10 ** (cfg.quote.decimal - wbtc.decimal)) ** 0.5  # raw stable per raw WBTC
            hit = usd * (usd * 10 ** cfg.quote.decimal) / (float(liq.asof(ts)) * sqrtp)
            impact += hit
            cost += hit
        costs[ts] = costs.get(ts, 0.0) + cost
    paid = pd.Series(costs, dtype=float).sort_index().cumsum()
    net = nav - (paid.reindex(nav.index, method="ffill").fillna(0.0) if len(paid) else 0.0)
    weight = pd.Series(dict(strategy.weights), dtype=float)
    tag = f"{cfg.name}_{start}"
    pd.DataFrame({"net": net, "price": price.reindex(net.index)}).to_csv(f"{RESULT_DIR}/nav_{tag}.csv")
    ev = pd.DataFrame(strategy.events, columns=["t", "kind"])
    ev.to_csv(f"{RESULT_DIR}/events_{tag}.csv", index=False)
    r = net.iloc[-1] / net.iloc[0] - 1
    share = float("nan") if cfg.gated else cfg.wbtc_share()  # gated versions are judged against their controls
    hold = share * (price.iloc[-1] / price.iloc[0] - 1)
    w_avg = float(weight.mean()) if len(weight) else float("nan")
    daily = price.resample("1D").last().pct_change().dropna()
    matched = float(np.prod(1 + w_avg * daily) - 1)
    gas = float(paid.iloc[-1]) - impact if len(paid) else 0.0
    return {"width": cfg.name, "start": start, "end": end, "net": r, "wbtc_share": share, "hold": hold,
            "hold5050": 0.5 * (price.iloc[-1] / price.iloc[0] - 1), "excess": r - hold,
            "excess_free_swaps": r - hold + (swap_fee + impact) / INITIAL, "excess_no_gas": r - hold + gas / INITIAL,
            "w_avg": w_avg, "excess_matched": r - matched,
            "swap_fee": swap_fee, "impact": impact, "gas": gas, "recentres": int((ev["kind"] == "recentre").sum()),
            "switches": int(ev["kind"].isin(["on", "off"]).sum()),
            "maxDD": float((net / net.cummax() - 1).min()), "secs": round(time.time() - started)}


def checks(x: pd.Series, starts: pd.Series, rally: bool = False) -> dict:
    starts = pd.to_datetime(pd.Series(starts.values, index=x.index))
    c = {"median > 0": x.median() > 0, ">= 12 of 16 > 0": (x > 0).sum() >= 12,
         "both halves median > 0": x[starts.dt.year <= 2023].median() > 0 and x[starts.dt.year >= 2024].median() > 0}
    if rally:
        c["rally median >= -10%"] = x[starts.dt.date.isin(RALLY_STARTS)].median() >= -0.10
    return c


def verdict(t: pd.DataFrame, rally: bool = False) -> str:
    failed = [k for k, ok in checks(t["excess"], t["start"], rally).items() if not ok]
    return "PASS" if not failed else "fail: " + "; ".join(failed)


def report(t: pd.DataFrame, name: str) -> None:
    if name in ("h2", "h3ab", "h3c", "h4a"):
        for w, g in t.groupby("width", sort=False):
            rally = name != "h2" and w != "usdt_w20"
            print(f"{w}: median excess {g['excess'].median():.4f}, positive {(g['excess'] > 0).sum()}/16, "
                  f"median matched {g['excess_matched'].median():.4f}, {verdict(g, rally)}")
    if name == "h4a":
        ok = {w: all(checks(g["excess"], g["start"], True).values()) for w, g in t.groupby("width")}
        med = t.groupby("width")["excess_matched"].median()
        a = ok["usdt_sd_33_10"]
        b = sum(ok[w] for w in ("sd_25_10", "sd_50_10", "sd_33_05", "sd_33_15")) >= 3
        c = med["sd_33_10"] > 0 and med["usdt_sd_33_10"] > 0
        print(f"H4a: a {a}, b {b}, c {c} -> {'PASS' if a and b and c else 'fail'}")
    if name == "h4b":
        nets = t.pivot(index="start", columns="width", values="net")
        for lp, ctl in H4B_CONTROL.items():
            x = nets[lp] - nets[ctl]
            c = checks(x, pd.Series(x.index, index=x.index))
            print(f"{lp} - {ctl}: median {x.median():.4f}, positive {(x > 0).sum()}/16, "
                  f"{'PASS' if all(c.values()) else 'fail: ' + '; '.join(k for k, v in c.items() if not v)}")
        g = t[t["width"] == "g_spot100"].set_index("start")
        print("g_spot100 - 50/50 hold: median %.4f; - WBTC hold: median %.4f" % (
            (g["net"] - g["hold5050"]).median(), (g["net"] - 2 * g["hold5050"]).median()))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--set", choices=list(SETS), default="h2")
    p.add_argument("--test", action="store_true")
    p.add_argument("--workers", type=int, default=WORKERS)
    a = p.parse_args()
    os.makedirs(RESULT_DIR, exist_ok=True)
    eth_daily()  # fill the caches before the workers read them
    btc_gate()
    if a.test:
        print(pd.Series(run(SETS["h2"][0], date(2022, 1, 1), date(2022, 1, 10))).to_string())
        for cfg in (SETS["h4b"][0], SETS["h4b"][3]):  # the gate turns on in January 2023
            print(pd.Series(run(cfg, date(2023, 1, 1), date(2023, 1, 31))).to_string())
        return
    tasks = [(c, s, window_end(s)) for c in SETS[a.set] for s in WINDOW_STARTS]
    with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
        rows = pool.starmap(run, tasks, chunksize=1)
    t = pd.DataFrame(rows)
    t.to_csv(f"{RESULT_DIR}/windows_{a.set}.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(t.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    report(t, a.set)


if __name__ == "__main__":
    main()
