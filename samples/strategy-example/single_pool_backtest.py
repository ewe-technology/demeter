"""
Step 1 of reports/single_pool_lp_plan.md: the shock breaker and the dynamic width, in Demeter on minute bars,
with every swap fee and an estimate of gas, 2022-01-01 ~ 2026-09-30 (2026 was never looked at before).

One pool, one position of [p/k, p k] with k = 1 + width, checked at every full hour:
  out of range                       -> re-centre (remove, add by value: only the difference is swapped)
  breaker: last hour |log return| above train's (2022-2023) 99th percentile
                                     -> remove; hold the two tokens (hold) or swap the base to the quote (park);
                                        re-centre once `off` hours pass without another hit (step 1b, keep_range:
                                        re-enter in the range held before the exit if the price is still inside it)
  dyn: multiplier m = clip(sigma_ref / sigma_24h, 0.25, 4) rounded to the nearest power of two, sigma_ref such that
       m averages 1 over train (single_pool_width.py W24h a1); a new level or out of range -> re-centre at the
       width whose per-capital edge is m times that of +/-10%

Each calendar year is its own run, starting from the quote at a centred position on 1 January (2026: to 30
September), which keeps one worker at about a year of minute data. Per year: net return (after gas) minus a 50/50
hold from the year's first bar, in the quote (USDC for ETH/USDC,
WETH for WBTC/WETH). Gas: tri_btc_eth_gate.GAS_UNITS per action, its yearly gwei, 3 gwei in 2026.

Run from samples/strategy-example (minute CSVs in ../real-data/<pool>/):
  PYTHONPATH=../.. python single_pool_backtest.py                       # every config, the full period
  PYTHONPATH=../.. python single_pool_backtest.py --start 2025-02-01 --end 2025-02-10 --only eth_hold1h
"""
import argparse
import json
import math
import multiprocessing
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from demeter import Actuator, MarketInfo, Snapshot, Strategy, TokenInfo
from demeter.uniswap import UniLpMarket, UniV3Pool
import single_pool_edge as spe
from tri_btc_eth_gate import ETH_POOL, GAS_GWEI, GAS_UNITS, RATIO_POOL, load_market, usdc, wbtc, weth

RESULT_DIR = "result/single-pool-bt"
KEY = MarketInfo("lp")
START, END = date(2022, 1, 1), date(2026, 9, 30)
TRAIN = (2022, 2023)
REF_K = 1.10
LEVELS = (0.25, 0.5, 1.0, 2.0, 4.0)
WORKERS = 3  # about 1 GB each with a year of minute data


@dataclass(frozen=True)
class Config:
    name: str
    address: str
    token0: TokenInfo
    token1: TokenInfo
    quote: TokenInfo
    initial: float  # in quote
    width: float  # k = 1 + width; dyn starts here
    breaker_off: int = 0  # hours out after a hit, 0 = no breaker
    park: bool = False
    dyn: bool = False
    keep_range: bool = False  # breaker re-entry reuses the range held before the exit while the price is inside it

    @property
    def base(self) -> TokenInfo:
        return self.token1 if self.quote == self.token0 else self.token0

    def pool(self) -> UniV3Pool:
        return UniV3Pool(token0=self.token0, token1=self.token1, fee=0.05, quote_token=self.quote, tick_spacing=10)


def eth(name, width, **kw):
    return Config(f"eth_{name}", ETH_POOL, usdc, weth, usdc, 100_000, width, **kw)


def btc(name, width, **kw):
    return Config(f"wbtc_{name}", RATIO_POOL, wbtc, weth, weth, 40, width, **kw)


CONFIGS = [
    eth("base10", 0.10), eth("base12.5", 0.125), eth("base20", 0.20),
    eth("hold1h", 0.10, breaker_off=1), eth("hold4h", 0.10, breaker_off=4),
    eth("park1h", 0.10, breaker_off=1, park=True), eth("park4h", 0.10, breaker_off=4, park=True),
    eth("dyn", 0.10, dyn=True),
    btc("base10", 0.10), btc("base5", 0.05),
    btc("hold1h", 0.10, breaker_off=1), btc("hold4h", 0.10, breaker_off=4),
    # step 1b: pause instead of re-centre
    eth("pause1h", 0.10, breaker_off=1, keep_range=True), eth("pause4h", 0.10, breaker_off=4, keep_range=True),
    btc("pause1h", 0.10, breaker_off=1, keep_range=True), btc("pause4h", 0.10, breaker_off=4, keep_range=True),
]


def width_for(m: float) -> float:
    """Width whose per-capital edge is m times that of +/-10%: 1 - k^-1/2 = (1 - 1.1^-1/2) / m."""
    return (1 - (1 - REF_K ** -0.5) / m) ** -2 - 1


def train_stats(address: str) -> tuple[float, float]:
    """
    Breaker cut (99th pct of hourly |log return|) and sigma_ref of the dynamic width, both from train, read with
    single_pool_edge's fast loader so they are the exact numbers of steps 0 and 0b. Cached per pool.
    """
    path = f"{RESULT_DIR}/train_{address}.json"
    if os.path.exists(path):
        with open(path) as f:
            return tuple(json.load(f))
    years = spe.YEARS
    spe.YEARS = range(TRAIN[0], TRAIN[1] + 1)
    try:
        logp = spe.edge_frame(spe.load_minutes(address), 0.0005)["logp"]
    finally:
        spe.YEARS = years
    r = logp.resample("1h").last().diff()
    train = (r.index.year >= TRAIN[0]) & (r.index.year <= TRAIN[1])
    cut = float(r[train].abs().quantile(0.99))
    sigma = r.rolling(24).std().shift(1)[train].dropna()
    lo, hi = math.log(sigma.min()), math.log(sigma.max())
    for _ in range(60):
        mid = (lo + hi) / 2
        mean = np.clip(math.exp(mid) / sigma, LEVELS[0], LEVELS[-1]).mean()
        lo, hi = (lo, mid) if mean > 1 else (mid, hi)
    with open(path, "w") as f:
        json.dump([cut, math.exp(lo)], f)
    return cut, math.exp(lo)


class SinglePool(Strategy):
    def __init__(self, cfg: Config, cut: float, sigma_ref: float):
        super().__init__()
        self.cfg, self.cut, self.sigma_ref = cfg, cut, sigma_ref
        self.bounds = None
        self.level = 1.0
        self.last_price = None
        self.returns = deque(maxlen=24)
        self.blocked_until = None
        self.saved = None  # range held before a breaker exit, for keep_range
        self.events = []  # (time, kind)

    def target_level(self) -> float:
        if len(self.returns) < 24:
            return 1.0
        sigma = float(np.std(self.returns, ddof=1))
        m = min(max(self.sigma_ref / sigma, LEVELS[0]), LEVELS[-1]) if sigma > 0 else LEVELS[-1]
        return min(LEVELS, key=lambda lv: abs(math.log2(lv / m)))

    def place(self, price: Decimal, width: float, kind: str, t):
        m: UniLpMarket = self.markets[KEY]
        k = Decimal(1 + width)
        t1, t2 = m.price_to_tick(price / k), m.price_to_tick(price * k)
        m.add_liquidity_by_value(min(t1, t2), max(t1, t2), None)
        self.bounds = (price / k, price * k)
        self.events.append((t, kind))

    def remove(self):
        self.markets[KEY].remove_all_liquidity()
        self.bounds = None

    def on_bar(self, snapshot: Snapshot):
        t = snapshot.timestamp
        m: UniLpMarket = self.markets[KEY]
        price = m.market_status.data.price
        cfg = self.cfg
        if self.last_price is None:  # first bar
            self.last_price = price
            self.place(price, cfg.width, "start", t)
            return
        if t.minute != 0:
            return
        ret = math.log(price / self.last_price)
        self.last_price = price
        self.returns.append(ret)

        if cfg.breaker_off and abs(ret) > self.cut:
            self.blocked_until = t + pd.Timedelta(hours=cfg.breaker_off)
            if self.bounds is not None:
                self.saved = self.bounds
                self.remove()
                if cfg.park:
                    base = self.broker.get_token_balance(cfg.base)
                    if base > 0:
                        m.swap(base, cfg.base, cfg.quote)
                self.events.append((t, "exit"))
            return
        if self.blocked_until is not None:
            if t < self.blocked_until:
                return
            self.blocked_until = None
            if cfg.keep_range and self.saved[0] <= price <= self.saved[1]:
                lo, hi = self.saved
                t1, t2 = m.price_to_tick(lo), m.price_to_tick(hi)
                m.add_liquidity_by_value(min(t1, t2), max(t1, t2), None)  # swaps only what the move shifted
                self.bounds = self.saved
                self.events.append((t, "resume"))
            else:
                self.place(price, cfg.width, "reenter", t)
            return

        out = not (self.bounds[0] <= price <= self.bounds[1])
        if cfg.dyn:
            level = self.target_level()
            if level != self.level or out:
                self.level = level
                self.remove()
                self.place(price, width_for(level), "recentre" if out else "resize", t)
        elif out:
            self.remove()
            self.place(price, cfg.width, "recentre", t)


def gas_in_quote(actions, cfg: Config, price: pd.Series) -> pd.Series:
    """Cumulative gas in the quote token by action time: ETH/USDC pays ETH x price, WBTC/WETH pays WETH as is."""
    rows = {}
    for a in actions:
        units = GAS_UNITS.get(type(a).__name__)
        if units:
            ts = pd.Timestamp(a.timestamp)
            in_eth = units * GAS_GWEI.get(ts.year, GAS_GWEI[2025]) * 1e-9
            rows[ts] = rows.get(ts, 0.0) + (in_eth * float(price.asof(ts)) if cfg.quote == usdc else in_eth)
    return pd.Series(rows, dtype=float).sort_index().cumsum()


def run(cfg: Config, start: date, end: date) -> dict:
    started = time.time()
    cut, sigma_ref = train_stats(cfg.address)  # train is 2022-2023 whatever window is backtested
    data, _ = load_market(KEY, cfg.pool(), cfg.address, start, end, None)
    price = data["price"].astype(float)
    market = UniLpMarket(KEY, cfg.pool())
    market.data = data
    actuator = Actuator()
    actuator.broker.add_market(market)
    actuator.broker.set_balance(cfg.quote, Decimal(cfg.initial))
    actuator.set_price(pd.DataFrame({cfg.base.name: price, cfg.quote.name: 1.0}, index=price.index), cfg.quote)
    strategy = SinglePool(cfg, cut, sigma_ref)
    actuator.strategy = strategy
    actuator.run(print_result=False)

    nav = actuator.account_status_df[("net_value", "")].astype(float)
    nav.index = pd.DatetimeIndex(nav.index)
    gas = gas_in_quote(actuator.actions, cfg, price)
    net = nav - gas.reindex(nav.index, method="ffill").fillna(0.0)
    swap_fee = sum(float(a.fee) * (1.0 if a.fee.unit.upper() == cfg.quote.name
                                   else float(price.asof(pd.Timestamp(a.timestamp))))
                   for a in actuator.actions if type(a).__name__ == "SwapAction")
    tag = f"{cfg.name}_{start.year}"
    pd.DataFrame({"net": net, "price": price.reindex(net.index)}).to_csv(f"{RESULT_DIR}/nav_{tag}.csv")
    ev = pd.DataFrame(strategy.events, columns=["t", "kind"])
    ev.to_csv(f"{RESULT_DIR}/events_{tag}.csv", index=False)
    return {"config": cfg.name, "year": start.year, "cut": cut, "sigma_ref": sigma_ref,
            "gas": float(gas.iloc[-1]) if len(gas) else 0.0, "swap_fee": swap_fee, **{f"n_{k}": v for k, v in ev["kind"].value_counts().items()},
            "secs": round(time.time() - started)}


def yearly(name: str, years: list[int]) -> pd.DataFrame:
    rows = []
    for y in years:
        g = pd.read_csv(f"{RESULT_DIR}/nav_{name}_{y}.csv", index_col=0, parse_dates=True)
        net = g["net"].iloc[-1] / g["net"].iloc[0] - 1
        hold = 0.5 * (g["price"].iloc[-1] / g["price"].iloc[0]) + 0.5 - 1
        rows.append({"config": name, "year": y, "net": net, "hold5050": hold, "excess": net - hold,
                     "maxDD": (g["net"] / g["net"].cummax() - 1).min()})
    return pd.DataFrame(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=date.fromisoformat, default=START)
    p.add_argument("--end", type=date.fromisoformat, default=END)
    p.add_argument("--only", nargs="*", default=None)
    p.add_argument("--workers", type=int, default=WORKERS)
    a = p.parse_args()
    os.makedirs(RESULT_DIR, exist_ok=True)
    configs = [c for c in CONFIGS if a.only is None or c.name in a.only]
    for address in {c.address for c in configs}:  # fill the cache before the workers read it
        print(address, "cut %.5f sigma_ref %.5f" % train_stats(address))
    spans = [(max(a.start, date(y, 1, 1)), min(a.end, date(y, 12, 31))) for y in range(a.start.year, a.end.year + 1)]
    with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
        runs = pool.starmap(run, [(c, s, e) for c in configs for s, e in spans], chunksize=1)
    meta = pd.DataFrame(runs)
    meta.to_csv(f"{RESULT_DIR}/runs.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(meta.to_string(index=False))
    years = pd.concat([yearly(c.name, [s.year for s, _ in spans]) for c in configs], ignore_index=True)
    years.to_csv(f"{RESULT_DIR}/years.csv", index=False)
    print(years.pivot(index="config", columns="year", values="excess").round(4))


if __name__ == "__main__":
    main()
