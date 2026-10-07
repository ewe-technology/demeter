"""
H2 of reports/single_pool_loop.md: a plain centred LP in WBTC/USDC 0.3% (0x99ac, the one pool that cleared H1)
against a 50/50 hold, in Demeter on minute bars.

One position of [p/k, p k], k = 1 + width, checked at every full hour; out of range -> remove and re-centre with
add_liquidity_by_value, which swaps the difference in the same 0.3% pool (single_pool_backtest.SinglePool, no
breaker). $100k USDC, quote USDC. Demeter adds our own liquidity to the pool's when sharing fees (market.py).

Costs, all subtracted from net value:
  swap fee   0.3%, charged by Demeter
  impact     not in Demeter: each swap of N USD also costs N x N / (L sqrt(P)) (raw units, L and P of the pool at the
             swap's minute), the arbitrum_check.py formula, uncapped
  gas        tri_btc_eth_gate.GAS_UNITS per action x the year's gwei (2026: 3) x the ETH price (88e6 daily close)

Windows: 12 months starting on the first day of every quarter, 2022-01 .. 2025-10 (16 windows, the last ends
2026-09-30), each from cash at a centred position. Widths +/-10% and +/-20%.

Verdict, fixed before the run (commit of this file): a width passes if, over the 16 windows, the excess (net after all
costs minus the 50/50 hold from the window's first bar)
  1. has a median > 0,
  2. is > 0 in at least 12 windows,
  3. has a median > 0 both over the 8 windows starting in 2022-2023 and over the 8 starting in 2024-2025.

Run from samples/strategy-example (minute CSVs in ../real-data/<pool>/):
  PYTHONPATH=../.. python pool_lp_windows.py
  PYTHONPATH=../.. python pool_lp_windows.py --test        # one width, 2022-01-01 .. 2022-01-10, for timing
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

from demeter import Actuator
from demeter.uniswap import UniLpMarket, UniV3Pool
import pool_screen as ps
from single_pool_backtest import KEY, Config, SinglePool
from tri_btc_eth_gate import GAS_GWEI, GAS_UNITS, load_market, usdc, wbtc

RESULT_DIR = "result/pool-lp-windows"
POOL = "0x99ac8cA7087fA4A2A1FB6357269965A2014ABc35"  # WBTC / USDC 0.3%
WIDTHS = (0.10, 0.20)
INITIAL = 100_000
WINDOW_STARTS = [date(y, m, 1) for y in range(2022, 2026) for m in (1, 4, 7, 10)]
LAST_DAY = date(2026, 9, 30)
WORKERS = 3


@dataclass(frozen=True)
class Config30(Config):
    def pool(self) -> UniV3Pool:
        return UniV3Pool(token0=self.token0, token1=self.token1, fee=0.3, quote_token=self.quote, tick_spacing=60)


def window_end(start: date) -> date:
    end = (pd.Timestamp(start) + pd.DateOffset(years=1) - pd.Timedelta(days=1)).date()
    return min(end, LAST_DAY)


def eth_daily() -> pd.Series:
    path = f"{RESULT_DIR}/eth_usd_daily.csv"
    if not os.path.exists(path):
        tick = ps.load_minutes(ps.POOLS["eth/usdc 5 mainnet"][0])[0]["closeTick"].resample("1D").last()
        (1e12 / np.power(1.0001, tick)).rename("eth_usd").to_csv(path)  # 88e6 price is WETH raw per USDC raw
    return pd.read_csv(path, index_col=0, parse_dates=True)["eth_usd"]


def run(width: float, start: date, end: date) -> dict:
    started = time.time()
    cfg = Config30(f"w{round(width * 100)}", POOL, wbtc, usdc, usdc, INITIAL, width)
    data, _ = load_market(KEY, cfg.pool(), POOL, start, end, None)
    price = data["price"].astype(float)
    market = UniLpMarket(KEY, cfg.pool())
    market.data = data
    actuator = Actuator()
    actuator.broker.add_market(market)
    actuator.broker.set_balance(usdc, Decimal(INITIAL))
    actuator.set_price(pd.DataFrame({wbtc.name: price, usdc.name: 1.0}, index=price.index), usdc)
    strategy = SinglePool(cfg, 0.0, 0.0)
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
            sqrtp = (px * 10 ** (usdc.decimal - wbtc.decimal)) ** 0.5  # raw USDC per raw WBTC
            hit = usd * (usd * 10 ** usdc.decimal) / (float(liq.asof(ts)) * sqrtp)
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
    hold = 0.5 * price.iloc[-1] / price.iloc[0] + 0.5 - 1
    gas = float(paid.iloc[-1]) - impact if len(paid) else 0.0
    return {"width": cfg.name, "start": start, "end": end, "net": r, "hold5050": hold, "excess": r - hold,
            "excess_free_swaps": r - hold + (swap_fee + impact) / INITIAL,
            "swap_fee": swap_fee, "impact": impact, "gas": gas, "recentres": int((ev["kind"] == "recentre").sum()),
            "maxDD": float((net / net.cummax() - 1).min()), "secs": round(time.time() - started)}


def verdict(t: pd.DataFrame) -> str:
    first = t[pd.to_datetime(t["start"]).dt.year <= 2023]["excess"]
    second = t[pd.to_datetime(t["start"]).dt.year >= 2024]["excess"]
    checks = {"median > 0": t["excess"].median() > 0, ">= 12 of 16 > 0": (t["excess"] > 0).sum() >= 12,
              "both halves median > 0": first.median() > 0 and second.median() > 0}
    failed = [k for k, ok in checks.items() if not ok]
    return "PASS" if not failed else "fail: " + "; ".join(failed)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--test", action="store_true")
    p.add_argument("--workers", type=int, default=WORKERS)
    a = p.parse_args()
    os.makedirs(RESULT_DIR, exist_ok=True)
    eth_daily()  # fill the cache before the workers read it
    if a.test:
        print(pd.Series(run(0.10, date(2022, 1, 1), date(2022, 1, 10))).to_string())
        return
    tasks = [(w, s, window_end(s)) for w in WIDTHS for s in WINDOW_STARTS]
    with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
        rows = pool.starmap(run, tasks, chunksize=1)
    t = pd.DataFrame(rows)
    t.to_csv(f"{RESULT_DIR}/windows.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(t.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    for w, g in t.groupby("width"):
        print(f"{w}: median excess {g['excess'].median():.4f}, positive {(g['excess'] > 0).sum()}/16, {verdict(g)}")


if __name__ == "__main__":
    main()
