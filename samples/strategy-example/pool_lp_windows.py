"""
H2 and H3 of reports/single_pool_loop.md: a plain LP in a 0.3% WBTC/stable pool against holding, in Demeter on
minute bars.

One position of [p/k_down, p k_up], k = 1 + width, checked at every full hour; out of range -> remove and re-centre
with add_liquidity_by_value, which swaps the difference in the same 0.3% pool (single_pool_backtest.SinglePool, no
breaker). $100k of the stablecoin, which is also the quote. Demeter adds our own liquidity to the pool's when sharing
fees (market.py).

Costs, all subtracted from net value:
  swap fee   0.3%, charged by Demeter
  impact     not in Demeter: each swap of N USD also costs N x N / (L sqrt(P)) (raw units, L and P of the pool at the
             swap's minute), the arbitrum_check.py formula, uncapped
  gas        tri_btc_eth_gate.GAS_UNITS per action x the year's gwei (2026: 3) x the ETH price (88e6 daily close)

Windows: 12 months starting on the first day of every quarter, 2022-01 .. 2025-10 (16 windows, the last ends
2026-09-30), each from cash at a position placed at the window's first price.

Excess = net after all costs minus holding, from the window's first bar, the WBTC share that the first position
holds (0.5 for a symmetric range).

Verdicts, each fixed before its run (commit of this file):
  H2   w10, w20 in 0x99ac. A version passes if, over the 16 windows, the excess
         1. has a median > 0,
         2. is > 0 in at least 12 windows,
         3. has a median > 0 both over the 8 windows starting in 2022-2023 and over the 8 starting in 2024-2025.
  H3a  w30, w50 in 0x99ac: both must meet 1-3, and each must have a median excess >= -10% over the five rally
       windows (50/50 hold above +50% in H2: starts 2023-01, 2023-04, 2023-07, 2023-10, 2024-01).
  H3b  usdt_w20, +/-20% in 0x9Db9 (WBTC/USDT 0.3%): meets 1-3.

Run from samples/strategy-example (minute CSVs in ../real-data/<pool>/):
  PYTHONPATH=../.. python pool_lp_windows.py --set h2
  PYTHONPATH=../.. python pool_lp_windows.py --set h3ab
  PYTHONPATH=../.. python pool_lp_windows.py --test        # w10, 2022-01-01 .. 2022-01-10, for timing
"""
import argparse
import multiprocessing
import os
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from demeter import Actuator, TokenInfo
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
WORKERS = 3


@dataclass(frozen=True)
class Config30(Config):
    up: float = 0.0  # width above the price; 0 = same as below (`width`)

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
        a, b = 1 - self.k_up ** -0.5, 1 - self.k_down ** -0.5
        return a / (a + b)


def version(name: str, width: float, up: float = 0.0, pool: str = USDC_POOL, quote: TokenInfo = usdc) -> Config30:
    return Config30(name, pool, wbtc, quote, quote, INITIAL, width, up=up)


SETS = {
    "h2": [version("w10", 0.10), version("w20", 0.20)],
    "h3ab": [version("w30", 0.30), version("w50", 0.50), version("usdt_w20", 0.20, pool=USDT_POOL, quote=usdt)],
}


class RangePool(SinglePool):
    """SinglePool with a range of [p / k_down, p k_up]; the symmetric case places exactly the same ticks."""

    def place(self, price: Decimal, width: float, kind: str, t):
        m: UniLpMarket = self.markets[KEY]
        lo, hi = price / Decimal(self.cfg.k_down), price * Decimal(self.cfg.k_up)
        t1, t2 = m.price_to_tick(lo), m.price_to_tick(hi)
        m.add_liquidity_by_value(min(t1, t2), max(t1, t2), None)
        self.bounds = (lo, hi)
        self.events.append((t, kind))


def window_end(start: date) -> date:
    end = (pd.Timestamp(start) + pd.DateOffset(years=1) - pd.Timedelta(days=1)).date()
    return min(end, LAST_DAY)


def eth_daily() -> pd.Series:
    path = f"{RESULT_DIR}/eth_usd_daily.csv"
    if not os.path.exists(path):
        tick = ps.load_minutes(ps.POOLS["eth/usdc 5 mainnet"][0])[0]["closeTick"].resample("1D").last()
        (1e12 / np.power(1.0001, tick)).rename("eth_usd").to_csv(path)  # 88e6 price is WETH raw per USDC raw
    return pd.read_csv(path, index_col=0, parse_dates=True)["eth_usd"]


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
    strategy = RangePool(cfg, 0.0, 0.0)
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
    tag = f"{cfg.name}_{start}"
    pd.DataFrame({"net": net, "price": price.reindex(net.index)}).to_csv(f"{RESULT_DIR}/nav_{tag}.csv")
    ev = pd.DataFrame(strategy.events, columns=["t", "kind"])
    ev.to_csv(f"{RESULT_DIR}/events_{tag}.csv", index=False)
    r = net.iloc[-1] / net.iloc[0] - 1
    share = cfg.wbtc_share()
    hold = share * (price.iloc[-1] / price.iloc[0] - 1)
    gas = float(paid.iloc[-1]) - impact if len(paid) else 0.0
    return {"width": cfg.name, "start": start, "end": end, "net": r, "wbtc_share": share, "hold": hold,
            "hold5050": 0.5 * (price.iloc[-1] / price.iloc[0] - 1), "excess": r - hold,
            "excess_free_swaps": r - hold + (swap_fee + impact) / INITIAL,
            "swap_fee": swap_fee, "impact": impact, "gas": gas, "recentres": int((ev["kind"] == "recentre").sum()),
            "maxDD": float((net / net.cummax() - 1).min()), "secs": round(time.time() - started)}


def verdict(t: pd.DataFrame, rally: bool = False) -> str:
    starts = pd.to_datetime(t["start"])
    first, second = t[starts.dt.year <= 2023]["excess"], t[starts.dt.year >= 2024]["excess"]
    checks = {"median > 0": t["excess"].median() > 0, ">= 12 of 16 > 0": (t["excess"] > 0).sum() >= 12,
              "both halves median > 0": first.median() > 0 and second.median() > 0}
    if rally:
        on_rally = t[starts.dt.date.isin(RALLY_STARTS)]["excess"]
        checks["rally median >= -10%"] = on_rally.median() >= -0.10
    failed = [k for k, ok in checks.items() if not ok]
    return "PASS" if not failed else "fail: " + "; ".join(failed)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--set", choices=list(SETS), default="h2")
    p.add_argument("--test", action="store_true")
    p.add_argument("--workers", type=int, default=WORKERS)
    a = p.parse_args()
    os.makedirs(RESULT_DIR, exist_ok=True)
    eth_daily()  # fill the cache before the workers read it
    if a.test:
        print(pd.Series(run(SETS["h2"][0], date(2022, 1, 1), date(2022, 1, 10))).to_string())
        return
    tasks = [(c, s, window_end(s)) for c in SETS[a.set] for s in WINDOW_STARTS]
    with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
        rows = pool.starmap(run, tasks, chunksize=1)
    t = pd.DataFrame(rows)
    t.to_csv(f"{RESULT_DIR}/windows_{a.set}.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(t.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    for w, g in t.groupby("width", sort=False):
        rally = a.set == "h3ab" and not w.startswith("usdt")
        print(f"{w}: median excess {g['excess'].median():.4f}, positive {(g['excess'] > 0).sum()}/16, {verdict(g, rally)}")


if __name__ == "__main__":
    main()
