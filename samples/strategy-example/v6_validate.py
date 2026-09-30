"""
Robustness checks for defense v6 (gas ignored, price impact charged):

- sensitivity: v6 with one engine / ladder parameter moved at a time, per segment
- benchmark:   v6 against the plain valley LP (always fully deployed, geometry share)
- daily net value of every run is saved, for drawdown / regime / deflated Sharpe analysis

usage: python v6_validate.py <pool> <start> <end> <grid: sens|bench|opt:A,<key>,...> [processes]
"""
import contextlib
import copy
import io
import json
import multiprocessing
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

import gamma_ig_gap_bands_defense_v6 as V
from demeter import TokenInfo, MarketInfo, ChainType
from demeter.uniswap import UniV3Pool
from market_v2 import UniLpMarketV2
from math_const import ZERO, ONE
from remix_dao_utils import RemixDAOParams, INIT_PRICE
from rm_types import RescaleFrequency, TestParams, GlobalParams, RangeStrategy, DcaTiming, DcaAddition

# pool -> (token0, token1, base index, fee %, data dir)
POOLS = {
    "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640": (("usdc", 6), ("eth", 18), 1, 0.05, "../real-data"),
    "0x99ac8ca7087fa4a2a1fb6357269965a2014abc35": (("btc", 8), ("usdc", 6), 0, 0.3, "../holdout-data"),
    # EXP-001 holdout: WBTC/WETH 0.05%, ETH is the base, WBTC the quote (numeraire and reserve)
    "0x4585fe77225b41b697c938b018e2ac67ac5a20c0": (("btc", 8), ("eth", 18), 1, 0.05, "../holdout-data"),
    # Base USDC/WETH 0.05% (the deck's target pool; token0 is WETH here). Gas is still priced as mainnet.
    "0xd0b53d9277642d899df5c87a3966a349a798f224": (("eth", 18), ("usdc", 6), 0, 0.05, "../base-data"),
}
# the EMA warm-up needs a year of history before the pool existed: read ETH/USD from the mainnet pool
WARM_POOL = {"0xd0b53d9277642d899df5c87a3966a349a798f224": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"}
FIRST_DATA = {"0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640": date(2021, 5, 6),
              "0x99ac8ca7087fa4a2a1fb6357269965a2014abc35": date(2021, 11, 2),
              "0x4585fe77225b41b697c938b018e2ac67ac5a20c0": date(2021, 11, 2),
              "0xd0b53d9277642d899df5c87a3966a349a798f224": date(2023, 12, 1)}
# EXP-004: daily Aave USDC supply APR per pool's chain (samples/fetch_aave_rates.py)
RATE_CSV = {"0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640": "../aave_usdc_ethereum_daily.csv",
            "0x99ac8ca7087fa4a2a1fb6357269965a2014abc35": "../aave_usdc_ethereum_daily.csv",
            "0xd0b53d9277642d899df5c87a3966a349a798f224": "../aave_usdc_base_daily.csv"}
INIT_QUOTE = Decimal(100000)
INIT_BY_POOL = {"0x4585fe77225b41b697c938b018e2ac67ac5a20c0": Decimal(2)}  # quote units; default INIT_QUOTE
G_REMOVE, G_ADD, G_SWAP = 260_000, 450_000, 150_000
GAS_CSV = "../gas_ethereum_hourly.csv"
ETH_USD_CSV = "../eth_usd_hourly.csv"


@dataclass(frozen=True)
class Variant:
    name: str
    engine: dict = field(default_factory=dict)   # overrides of v6 module constants
    ratio: str = "0.20"
    deploy: str = V.DEPLOY_SIGNAL
    eth_share: object = V.EMA_SHARE

    def __hash__(self):
        return hash(self.name)


# experiment candidates for "opt:A,<key>,..." runs; A is always v6 itself. Add one entry per EXP (see experiments/).
OPT = {"A": Variant("A_v6"),
       "B": Variant("B_spot_sleeve", {"SPOT_SLEEVE": Decimal("0.5")}),   # EXP-001
       "C": Variant("C_sleeve_stop", {"SPOT_SLEEVE": Decimal("0.5"), "SLEEVE_STOP": 0.80}),   # EXP-002
       "D": Variant("D_stop_keep_high", {"SPOT_SLEEVE": Decimal("0.5"), "SLEEVE_STOP": 0.80,
                                         "SLEEVE_HIGH_KEEP": True}),   # EXP-003
       "E": Variant("E_cash_yield", {"CASH_APR": "pool"}),   # EXP-004: idle USDC earns the pool chain's Aave rate
       "F": Variant("F_refill_order", {"REFILL_ORDER": True}),   # EXP-005
       "G": Variant("G_half_ladder", {"HALF_LADDER": True}),   # EXP-006
       "H": Variant("H_half_when_accel", {"HALF_WHEN_ACCEL": True})}   # EXP-007


ENGINE_DEFAULTS = {k: getattr(V, k) for k in ["EMA_SPANS", "REFILL_STAGES", "REFILL_CONFIRM_DAYS", "LOWER_STOP",
                                                "FOLLOW_THRESHOLD", "SHARE_ABOVE_EMA", "SPOT_SLEEVE", "SLEEVE_STOP", "SLEEVE_HIGH_KEEP", "CASH_APR", "REFILL_ORDER", "HALF_LADDER", "HALF_WHEN_ACCEL"]}


def sens_grid():
    v = [Variant("base")]
    v += [Variant("ema_x0.8", {"EMA_SPANS": (72, 80, 88, 96)}),
          Variant("ema_x1.2", {"EMA_SPANS": (108, 120, 132, 144)})]
    v += [Variant("refill_x0.8", {"REFILL_STAGES": ((1, 1.04), (2, 1.0667), (3, 1.0933), (4, 1.12))}),
          Variant("refill_x1.2", {"REFILL_STAGES": ((1, 1.06), (2, 1.10), (3, 1.14), (4, 1.18))})]
    v += [Variant("confirm_1", {"REFILL_CONFIRM_DAYS": 1}), Variant("confirm_5", {"REFILL_CONFIRM_DAYS": 5})]
    v += [Variant("stop_0.75", {"LOWER_STOP": 0.75}), Variant("stop_0.85", {"LOWER_STOP": 0.85})]
    v += [Variant("follow_0.0625", {"FOLLOW_THRESHOLD": Decimal("0.0625")}),
          Variant("follow_0.25", {"FOLLOW_THRESHOLD": Decimal("0.25")})]
    v += [Variant("width_0.15", ratio="0.15"), Variant("width_0.25", ratio="0.25")]
    v += [Variant("share_0.6", {"SHARE_ABOVE_EMA": Decimal("0.6")}),
          Variant("share_0.8", {"SHARE_ABOVE_EMA": Decimal("0.8")})]
    v += [Variant("plain_lp", deploy=V.DEPLOY_FULL, eth_share=None)]
    return v


def bench_grid():
    return [Variant("base"), Variant("plain_lp", deploy=V.DEPLOY_FULL, eth_share=None)]


POOL = ""
DATA: pd.DataFrame | None = None
PRICE: pd.Series | None = None   # warm-up + window minute prices, for the daily engine
GAS: pd.Series | None = None
ETH_USD: pd.Series | None = None
CURRENT = None
EQUITY: pd.Series | None = None


class Checked(V.RemixDaoDcaWeekStratStrategy):
    """v6 plus a ledger of price impact and (reported only) gas per rebuild."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        global CURRENT
        CURRENT = self
        self.cost_log = []

    def swapped_since(self, b0, q0):
        rate = Decimal(str(self.gp.fee)) / Decimal(100)
        return (self.total_base_swap_fee - b0) / rate, (self.total_quote_swap_fee - q0) / rate

    def charge(self, row_data, n_removed, n_added, base_in, quote_in):
        ts = row_data.timestamp
        price = float(row_data.prices[self.gp.base_token.name])
        units = n_removed * G_REMOVE + n_added * G_ADD + (G_SWAP if (base_in > 0 or quote_in > 0) else 0)
        gas_usd = units * float(GAS.asof(ts)) * 1e-9 * float(ETH_USD.asof(ts))
        status = row_data.market_status[self.utils.market_key]
        liq = float(status.currentLiquidity)
        sqrtp = 1.0001 ** (float(status.closeTick) / 2)
        x0, x1 = liq / sqrtp, liq * sqrtp
        base_is_0 = self.gp.base_token.name == self.gp.token0.name
        impact = 0.0
        if base_in > 0:
            impact = float(base_in) * 10 ** self.gp.base_token.decimal / (x0 if base_is_0 else x1) * float(base_in) * price
        elif quote_in > 0:
            impact = float(quote_in) * 10 ** self.gp.quote_token.decimal / (x1 if base_is_0 else x0) * float(quote_in)
        self.cost_log.append((ts, gas_usd, impact, float(base_in) * price + float(quote_in)))

    def first_lp(self, row_data):
        b0, q0 = self.total_base_swap_fee, self.total_quote_swap_fee
        super().first_lp(row_data)
        self.charge(row_data, 0, len(self.positions), *self.swapped_since(b0, q0))

    def rescale_work(self, row_data):
        before, n = list(self.positions), len(self.export_actions)
        b0, q0 = self.total_base_swap_fee, self.total_quote_swap_fee
        super().rescale_work(row_data)
        if len(self.export_actions) > n:
            self.charge(row_data, len(before), len(self.positions), *self.swapped_since(b0, q0))

    def sleeve_stop_work(self, row_data, target, free_base):
        b0, q0 = self.total_base_swap_fee, self.total_quote_swap_fee
        stops = self.sleeve_stops
        super().sleeve_stop_work(row_data, target, free_base)
        if self.sleeve_stops > stops:
            self.charge(row_data, 0, 0, *self.swapped_since(b0, q0))

    def impact_series(self, index) -> pd.Series:
        if not self.cost_log:
            return pd.Series(0.0, index=index)
        c = pd.DataFrame(self.cost_log, columns=["ts", "gas", "impact", "notional"]).groupby("ts").sum()
        return c["impact"].cumsum().reindex(index, method="ffill").fillna(0.0)


_raw_metrics = V.performance_metrics_for_dca


def _net_metrics(values, *args, **kwargs):
    global EQUITY
    values = values.apply(float) - CURRENT.impact_series(values.index)
    EQUITY = values
    return _raw_metrics(values, *args, **kwargs)


V.performance_metrics_for_dca = _net_metrics
V.RemixDaoDcaWeekStratStrategy = Checked


def tokens(pool: str | None = None):
    t0, t1, base_i, fee, _ = POOLS[pool or POOL]
    token0, token1 = TokenInfo(name=t0[0], decimal=t0[1]), TokenInfo(name=t1[0], decimal=t1[1])
    base, quote = (token0, token1) if base_i == 0 else (token1, token0)
    return token0, token1, base, quote, fee


def inputs(variant: Variant, start: date, end: date, folder: str):
    token0, token1, base, quote, fee = tokens()
    spacing = int(fee * 200)
    init = INIT_BY_POOL.get(POOL, INIT_QUOTE)
    gp = GlobalParams(token0=token0, token1=token1, fee=fee, init_quote=init, quote_token=quote, base_token=base,
                      chain_name=ChainType.ethereum.name, contract_address=POOL, swap_fee=False,
                      dca_usdc_amount=Decimal(10000), dca_add_if_non_empty=False, dca_add_timing=DcaTiming.none,
                      init_quote_usdc=init * INIT_PRICE, dca_addon_price_percent=ZERO,
                      dca_addon_amount_percent=ZERO, dca_addition=DcaAddition.none)
    p = RemixDAOParams(tick_spread_upper=410, tick_spread_lower=410, tick_upper_boundary_offset=0,
                       tick_lower_boundary_offset=0, rescale_tick_upper_boundary_offset=0,
                       rescale_tick_lower_boundary_offset=0, init_tick_spread=410, tick_spacing=spacing,
                       tick_gap_lower=1, tick_gap_upper=1)
    tp = TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1, report_name=variant.name,
                    indicator_length_hr=1, to_swap=False, aggressive=True, compound=False,
                    rescale_frequency=RescaleFrequency.daily,
                    cal_start_datetime=datetime.combine(start, datetime.min.time()), data_start_date=start,
                    data_end_date=end, folder=folder, initial_swap=True, flip_param_dates=[],
                    start_with_bull_param=True, initial_type=1, starting_mark_price=Decimal(20))
    return p, copy.copy(p), tp, gp


def daily_frame() -> pd.DataFrame:
    """v6's daily frame; F from the (possibly overridden) EMA_SPANS, "ema" always EMA100 for the s rule.
    daily_ema_frame reads the EMA100 column out of EMA_SPANS, so a moved span set would drop it."""
    if V.EMA_SPAN in V.EMA_SPANS:
        return V.daily_ema_frame(PRICE)
    ema_span = V.EMA_SPAN
    V.EMA_SPAN = V.EMA_SPANS[0]
    try:
        daily = V.daily_ema_frame(PRICE)
    finally:
        V.EMA_SPAN = ema_span
    daily["ema"] = daily["close"].ewm(span=ema_span, adjust=False).mean()
    return daily


def run_variant(args):
    variant, start, end, folder = args
    t0 = time.time()
    # pool workers are reused: restore every default before applying this variant's overrides
    for k, v in {**ENGINE_DEFAULTS, **variant.engine}.items():
        if k == "CASH_APR" and v == "pool":
            v = pd.read_csv(RATE_CSV[POOL], parse_dates=["date"]).set_index("date")["apr"].sort_index()
        setattr(V, k, v)
    daily = daily_frame()
    window = daily.loc[pd.Timestamp(start):]
    bull, bear, tp, gp = inputs(variant, start, end, folder)
    usdc_price = pd.DataFrame(index=pd.date_range(start=start, end=datetime.combine(end, datetime.max.time()),
                                                  freq="min"), data={"price": ONE})
    ratio = Decimal(variant.ratio)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            m = V.run_test(bull, bear, tp, gp, DATA, usdc_price, shape="inverted_gaussian", upper_ratio=ratio,
                           lower_ratio=ratio, half_gap=0, eth_share=variant.eth_share, daily_ema=daily,
                           deploy=variant.deploy)
    except Exception as e:
        return {"variant": variant.name, "error": repr(e)[:300]}
    s = CURRENT
    c = pd.DataFrame(s.cost_log, columns=["ts", "gas", "impact", "notional"])
    eq = EQUITY.resample("1D").last().dropna()
    eq.to_csv(os.path.join(folder, f"equity_{variant.name}.csv"), header=["net_value"])
    net = float(eq.iloc[-1])
    return {"variant": variant.name, "pool": POOL[:6], "start": start.isoformat(), "end": end.isoformat(),
            "net_return": net / float(INIT_BY_POOL.get(POOL, INIT_QUOTE)) - 1, "max_draw_down": float(m["max_draw_down"]),
            "sharpe_ratio": float(m["sharpe_ratio"]), "impact": float(c["impact"].sum()),
            "gas_if_mainnet": float(c["gas"].sum()), "swap_notional": float(c["notional"].sum()),
            "max_swap_notional": float(c["notional"].max()), "rebuilds": len(c),
            "fees": float(s.total_fee), "sleeve_stops": s.sleeve_stops, "interest": float(s.total_interest), "refill_orders": s.refill_orders, "half_builds": s.half_builds, "lp_net_value": float(s.final_lp_net_value),
            "mean_F": float(window["F"].mean()) if variant.deploy == V.DEPLOY_SIGNAL else 1.0,
            "benchmark_return": float(m["benchmark_rate"]), "secs": round(time.time() - t0)}


def load_minutes(start: date, end: date, pool: str | None = None) -> pd.DataFrame:
    pool = pool or POOL
    token0, token1, base, quote, fee = tokens(pool)
    market = UniLpMarketV2(MarketInfo("lp"), UniV3Pool(token0, token1, fee, quote))
    market.data_path = f"{POOLS[pool][4]}/{pool}"
    market.load_data(ChainType.ethereum.name, pool, start, end)
    return market.data


def main():
    global POOL, DATA, PRICE, GAS, ETH_USD
    POOL = sys.argv[1]
    start, end, grid = date.fromisoformat(sys.argv[2]), date.fromisoformat(sys.argv[3]), sys.argv[4]
    procs = int(sys.argv[5]) if len(sys.argv) > 5 else 4
    # "opt:A,<key>,..." runs those OPT candidates (A = v6)
    variants = [OPT[k] for k in grid[4:].split(",")] if grid.startswith("opt:") else \
        {"sens": sens_grid, "bench": bench_grid}[grid]()
    grid = grid.replace(":", "-").replace(",", "")
    GAS = pd.read_csv(GAS_CSV, parse_dates=["timestamp"]).set_index("timestamp")["gwei"].sort_index().interpolate().bfill()
    ETH_USD = pd.read_csv(ETH_USD_CSV, parse_dates=["timestamp"]).set_index("timestamp")["usd"].sort_index()
    DATA = load_minutes(start, end)
    warm_days = 3 * max(max(v.engine.get("EMA_SPANS", V.EMA_SPANS)) for v in variants)
    warm_pool = WARM_POOL.get(POOL, POOL)
    warm = load_minutes(max(start - timedelta(days=warm_days), FIRST_DATA[warm_pool]), start - timedelta(days=1),
                        warm_pool)
    PRICE = pd.concat([warm.price, DATA.price])
    tag = f"{POOL[:6]}-{grid}-{start}-{end}"
    folder = os.path.join("result", "v6_validate", tag)
    os.makedirs(folder, exist_ok=True)
    out_csv = os.path.join("result", "v6_validate", f"{tag}.csv")
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(procs) as pool:
        for r in pool.imap_unordered(run_variant, [(v, start, end, folder) for v in variants]):
            pd.DataFrame([r]).to_csv(out_csv, mode="a", header=not os.path.exists(out_csv), index=False)
            print(f"{datetime.now():%H:%M:%S} {tag} {r['variant']} net={r.get('net_return')} "
                  f"err={r.get('error', '')}", flush=True)


if __name__ == "__main__":
    main()
