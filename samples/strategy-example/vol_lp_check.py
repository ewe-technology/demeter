"""
Diagnostic before any volatility-gated LP strategy: does an ETH/USDC or WBTC/WETH LP beat holding the same tokens
on days whose trailing volatility is low?

Each pool runs one LP position the whole time through Demeter (hourly bars, the LP version's ranges: ETH/USDC
+/- 20%, WBTC/WETH +/- 10%, re-centred at 00:00 when out of range). For every day:

  excess = LP return - return of holding, as spot, the token mix the position had at 00:00

which is that day's fees minus impermanent loss minus re-centring costs (report section 10 measured the same thing
over whole runs). Days are bucketed by the pool price's 30-day realised volatility known at 00:00, for all days and
for days the BTC gate is open (the only days the strategy would swap its spot for an LP).

No strategy is chosen here. If low-volatility days do not show a steady positive excess in every year, the idea stops.

Run from samples/strategy-example (the spot price cache of spot_btc_eth_gate.py must exist):
  PYTHONPATH=../.. python vol_lp_check.py
"""
import math
import multiprocessing
import os
import time
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

import spot_robustness as sr
from demeter import Actuator
from demeter.uniswap import UniLpMarket, UniV3Pool
from spot_btc_eth_gate import load_prices
from tri_btc_eth_gate import ETH_POOL, RATIO_POOL, load_market, usdc, wbtc, weth
from yield_layer import KEY, Sleeve, SleeveLP

RESULT_DIR = "result/vol-lp"
START, END = date(2021, 12, 1), date(2026, 9, 30)  # December 2021 only warms up the volatility
FIRST_DAY = "2022-01-01"
VOL_DAYS = 30
BUCKETS = 5


@dataclass(frozen=True)
class PoolSleeve(Sleeve):
    fee: float = 0.05
    tick_spacing: int = 10

    def pool(self) -> UniV3Pool:
        return UniV3Pool(token0=self.token0, token1=self.token1, fee=self.fee, quote_token=self.quote,
                         tick_spacing=self.tick_spacing)


SLEEVES = (
    PoolSleeve("ethusdc_lp0.2", ETH_POOL, usdc, weth, usdc, START, END, 0.20, 50_000),
    PoolSleeve("wbtcweth_lp0.1", RATIO_POOL, wbtc, weth, weth, START, END, 0.10, 15),
)


class RecordingLP(SleeveLP):
    """SleeveLP that also records the range of every placement."""

    def __init__(self, s: Sleeve):
        super().__init__(s)
        self.ranges = []  # (time, low, high) in quote per base

    def on_bar(self, snapshot):
        before = self.bounds
        super().on_bar(snapshot)
        if self.bounds is not None and self.bounds is not before:
            self.ranges.append((snapshot.timestamp, float(self.bounds[0]), float(self.bounds[1])))


def run(s: PoolSleeve) -> tuple[str, pd.DataFrame, pd.DataFrame, float]:
    started = time.time()
    data, _ = load_market(KEY, s.pool(), s.address, s.start, s.end, "1h", s.chain)
    market = UniLpMarket(KEY, s.pool())
    market.data = data
    actuator = Actuator()
    actuator.broker.add_market(market)
    actuator.broker.set_balance(s.quote, s.initial)
    price = data["price"].astype(float)
    actuator.set_price(pd.DataFrame({s.base.name: price, s.quote.name: 1.0}, index=data.index), s.quote)
    strategy = RecordingLP(s)
    actuator.strategy = strategy
    actuator.run(print_result=False)
    nav = actuator.account_status_df[("net_value", "")].astype(float)
    out = pd.DataFrame({"nav": nav.to_numpy(), "price": price.reindex(nav.index).to_numpy()},
                       index=pd.DatetimeIndex(nav.index))
    ranges = pd.DataFrame(strategy.ranges, columns=["t", "lo", "hi"]).set_index("t")
    return s.name, out, ranges, time.time() - started


def base_share(p: float, lo: float, hi: float) -> float:
    """Value share of the base token in a v3 position over [lo, hi] at price p (all in quote per base)."""
    if p <= lo:
        return 1.0
    if p >= hi:
        return 0.0
    x = 1 / math.sqrt(p) - 1 / math.sqrt(hi)  # base per unit of liquidity
    y = math.sqrt(p) - math.sqrt(lo)  # quote per unit of liquidity
    return x * p / (x * p + y)


def daily_excess(out: pd.DataFrame, ranges: pd.DataFrame, gate_on: pd.Series) -> pd.DataFrame:
    at0 = out[out.index.hour == 0]
    rows = []
    for (t0, a), (t1, b) in zip(at0.iterrows(), at0.iloc[1:].iterrows()):
        if (t1 - t0) != pd.Timedelta(days=1):
            continue
        r = ranges[ranges.index <= t0]
        if r.empty:
            continue
        lo, hi = r.iloc[-1]["lo"], r.iloc[-1]["hi"]
        s = base_share(a["price"], lo, hi)
        hold = s * b["price"] / a["price"] + (1 - s)
        rows.append({"date": t0.normalize(), "excess": b["nav"] / a["nav"] - hold, "base_share": s})
    df = pd.DataFrame(rows).set_index("date")
    logret = np.log(at0["price"]).diff()
    logret.index = logret.index.normalize()
    # volatility known at 00:00 of day d: the VOL_DAYS daily returns ending at that 00:00
    df["vol30"] = (logret.rolling(VOL_DAYS).std() * math.sqrt(365)).reindex(df.index)
    df["gate_on"] = gate_on.reindex(df.index).fillna(False).astype(bool)
    return df.loc[FIRST_DAY:].dropna(subset=["vol30"])


def summarise(name: str, df: pd.DataFrame) -> tuple[list, list]:
    edges = df["vol30"].quantile(np.linspace(0, 1, BUCKETS + 1)).to_numpy()
    df = df.assign(bucket=pd.cut(df["vol30"], edges, labels=False, include_lowest=True) + 1)
    buckets, years = [], []
    for days, part in (("all days", df), ("gate open", df[df["gate_on"]])):
        for b, g in part.groupby("bucket"):
            buckets.append({"pool": name, "days": days, "bucket": int(b), "vol from": edges[int(b) - 1],
                            "vol to": edges[int(b)], "n": len(g), "excess annual": g["excess"].mean() * 365,
                            "positive days": (g["excess"] > 0).mean()})
        low = part[part["bucket"] <= 2]
        for y, g in low.groupby(low.index.year):
            years.append({"pool": name, "days": days + ", vol buckets 1-2", "year": y, "n": len(g),
                          "excess annual": g["excess"].mean() * 365, "positive days": (g["excess"] > 0).mean()})
        for y, g in part.groupby(part.index.year):
            years.append({"pool": name, "days": days + ", every bucket", "year": y, "n": len(g),
                          "excess annual": g["excess"].mean() * 365, "positive days": (g["excess"] > 0).mean()})
    return buckets, years


if __name__ == "__main__":
    os.makedirs(RESULT_DIR, exist_ok=True)
    prices, _, _ = load_prices()
    w = sr.gate(prices)
    gate_on = (w["eth"] + w["btc"] > 0)
    gate_on.index = gate_on.index.normalize()
    gate_on = gate_on[~gate_on.index.duplicated()]
    with multiprocessing.Pool(len(SLEEVES)) as pool:
        results = pool.map(run, SLEEVES)
    all_buckets, all_years = [], []
    for name, out, ranges, secs in results:
        out.to_csv(f"{RESULT_DIR}/sleeve_{name}.csv")
        ranges.to_csv(f"{RESULT_DIR}/ranges_{name}.csv")
        df = daily_excess(out, ranges, gate_on)
        df.to_csv(f"{RESULT_DIR}/daily_{name}.csv")
        print(f"{name}: {len(df)} days, {len(ranges)} placements, mean excess {df['excess'].mean() * 365:+.2%}/yr, "
              f"{secs:.0f}s")
        b, y = summarise(name, df)
        all_buckets += b
        all_years += y
    buckets, years = pd.DataFrame(all_buckets), pd.DataFrame(all_years)
    buckets.to_csv(f"{RESULT_DIR}/buckets.csv", index=False)
    years.to_csv(f"{RESULT_DIR}/years.csv", index=False)
    pd.set_option("display.width", 250)
    fmt = {"vol from": "{:.0%}".format, "vol to": "{:.0%}".format, "excess annual": "{:+.1%}".format,
           "positive days": "{:.0%}".format}
    print("\n== by 30-day volatility bucket (1 = lowest) ==")
    print(buckets.to_string(index=False, formatters=fmt))
    print("\n== by year ==")
    print(years.to_string(index=False, formatters=fmt))
    print("VOL_LP_DONE")
