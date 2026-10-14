"""
H38 and H39 of reports/plan_2026-10-14_strategy_exchange.md (registered in ea8fc90, signal source revised in a8247c3,
before this code ran): maker-defense ETH/USDC v3 (gamma_maker_defense_ethusdc_v3.py from origin/maker-defense 5cec767,
unchanged) on hourly bars, with the costs of pool_lp_batch.py.

  H38  one F' series (v3, Binance closes from the committed binance_ethusdt_1d.csv), three uses of the deployed money:
         lp     v3 as is, all of F' in the 16-band valley LP
         mix    half the book through v3's LP, half through the spot rules below (two $50k books, see the plan's
                change record: the follow threshold applies to each half, not to the sum)
         spot   all of F' in ETH spot: below centre x 0.80 sell everything, above centre x 1.20 only move the centre
                (sell everything when the divergence flag is on, as v3), follow F' with v3's 12.5% rule
       and the lp run split into price, impermanent loss, fees and costs (combine step).
  H39  the lp version only: one continuous book, 16 windows, the same with a one-hour delay, and 24 judgement hours
       (signal from 0x88e6 hourly prices, listed only).

Costs (plan 2.2): Demeter charges the pool fee inside every swap; v3's own extra charges are off (SWAP_COST_RATE,
SLIPPAGE_MODEL = None). Price impact (N x N / (L sqrt P)) and gas (GAS_UNITS x GAS_GWEI of the year x ETH, or
ARB_GAS_USD on Base) come from the recorded actions afterwards and are subtracted from the net value, as in
pool_lp_batch.run. Every add / remove / collect / swap of each band counts. Fees are collected only at a rebuild.

Bars: the minute files are read a year at a time and resampled to hourly ("price" is the first price of the hour),
cached in RESULT_DIR. v3 settles at 23:59 of the end day; on hourly bars that is 23:00.

Run from samples/strategy-example:
  PYTHONPATH=../.. python maker_defense_h38.py --cache                # hourly caches (88e6, d0b5)
  PYTHONPATH=../.. python maker_defense_h38.py --test                 # 2 months, plumbing only
  PYTHONPATH=../.. python maker_defense_h38.py --calibrate            # 2 windows on minute bars
  PYTHONPATH=../.. python maker_defense_h38.py --runs --workers 2     # every Demeter run, skips finished ones
  PYTHONPATH=../.. python maker_defense_h38.py --spot                 # the spot books
"""
import argparse
import copy
import math
import multiprocessing
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

from demeter import Actuator, MarketInfo, TokenInfo
from demeter.uniswap import UniV3Pool
from demeter.uniswap.data import resample

import gamma_maker_defense_ethusdc_v3 as v3
import pool_lp_batch as batch
from market_v2 import UniLpMarketV2
from tri_btc_eth_gate import GAS_GWEI, GAS_UNITS

RESULT_DIR = "result/maker-defense-h38"
SIGNAL_END = date(2026, 8, 31)  # last day of binance_ethusdt_1d.csv
CONT_START = date(2022, 1, 1)
WINDOW_STARTS = [date(y, m, 1) for y in (2022, 2023, 2024, 2025) for m in (1, 4, 7, 10)]
CALIBRATION = (date(2022, 1, 1), date(2024, 7, 1))
BASE_START = date(2023, 9, 7)  # first full day of 0xd0b5 (the 2023-09-06 file is a partial day)

usdc = TokenInfo(name="usdc", decimal=6)
eth = TokenInfo(name="eth", decimal=18)


@dataclass(frozen=True)
class PoolSpec:
    key: str
    address: str
    chain: str
    token0: TokenInfo
    token1: TokenInfo
    first_day: date


POOLS = {"88e6": PoolSpec("88e6", "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", "ethereum", usdc, eth, date(2021, 5, 5)),
         "d0b5": PoolSpec("d0b5", "0xd0b53D9277642d899DF5C87A3966A349A798F224", "base", eth, usdc, BASE_START)}


@dataclass(frozen=True)
class Run:
    name: str
    pool: str = "88e6"
    start: date = CONT_START
    end: date = SIGNAL_END
    initial: int = 100_000
    signal: str = "binance"  # "binance" or "pool"
    hour: int = 0  # judgement hour: the book starts and the daily work runs at this UTC hour
    delay: int = 0  # hours between the decision and the trades
    bar: str | None = "1h"  # None = minute bars (calibration only)


def window_end(s: date) -> date:
    return min((pd.Timestamp(s) + pd.DateOffset(years=1) - pd.Timedelta(days=1)).date(), SIGNAL_END)


def runs_h38() -> list[Run]:
    return [Run("lp_100k"), Run("lp_50k", initial=50_000), Run("base_lp_100k", pool="d0b5", start=BASE_START)]


def runs_h39() -> list[Run]:
    out = [Run(f"win_{s}", start=s, end=window_end(s)) for s in WINDOW_STARTS]
    out += [Run(f"delay_win_{s}", start=s, end=window_end(s), delay=1) for s in WINDOW_STARTS]
    out.append(Run("delay_cont", delay=1))
    out += [Run(f"hour_{h:02d}", signal="pool", hour=h) for h in range(24)]
    return out


def all_runs() -> list[Run]:
    return runs_h38() + runs_h39()


# ---------- data ----------

def hourly_path(pool: str) -> str:
    return f"{RESULT_DIR}/hourly_{pool}.pkl"


def build_hourly(pool: str, last: date = date(2026, 9, 30)) -> pd.DataFrame:
    """The pool's minute files a year at a time, resampled to hourly bars, cached."""
    path = hourly_path(pool)
    if os.path.exists(path):
        return pd.read_pickle(path)
    p = POOLS[pool]
    parts, s = [], p.first_day
    while s <= last:
        e = min(date(s.year, 12, 31), last)
        parts.append(resample(minute_data(pool, s, e), "1h"))
        print(f"{pool} {s} .. {e}: {len(parts[-1])} hours", flush=True)
        s = e + timedelta(days=1)
    data = pd.concat(parts)
    os.makedirs(RESULT_DIR, exist_ok=True)
    data.to_pickle(path)
    return data


def minute_data(pool: str, s: date, e: date) -> pd.DataFrame:
    p = POOLS[pool]
    m = UniLpMarketV2(MarketInfo("lp"), UniV3Pool(p.token0, p.token1, 0.05, usdc))
    m.data_path = f"../real-data/{p.address}"
    m.load_data(p.chain, p.address, s, e)
    return m.data


def pool_signal(hourly: pd.DataFrame, hour: int, end: date) -> pd.DataFrame:
    """v3's daily frame from 0x88e6 closes at `hour`: the close keyed by day d is the price at d+1 `hour`:00, so
    v3's daily_row_for (the row of the timestamp minus one day) reads the close at the judgement time itself."""
    price = hourly["price"].astype(float)
    close = price[price.index.hour == hour]
    close.index = close.index.normalize() - pd.Timedelta(days=1)
    return v3.daily_ema_frame(close[close.index <= pd.Timestamp(end)])


# ---------- v3 patches ----------

v3.SWAP_COST_RATE = None  # plan 2.2 point 4: one cost model, applied afterwards
v3.SLIPPAGE_MODEL = None
_AtTime = v3.AtTimeTrigger
_BAR_MINUTES = [60]


def _at_bar(time, *a, **kw):
    """v3's settlement at 23:59 of the end day; with hourly bars the last bar is 23:00."""
    if time.minute == 59 and _BAR_MINUTES[0] == 60:
        time = time.replace(minute=0)
    return _AtTime(time, *a, **kw)


v3.AtTimeTrigger = _at_bar
_LAST = {}


class Capture(Actuator):
    def run(self, *a, **kw):
        _LAST["actuator"] = self
        return super().run(*a, **kw)


v3.Actuator = Capture


class Delayed(v3.RemixDaoDcaWeekStratStrategy):
    """The daily range check and follow-F decided at the judgement bar with that bar's price and signal, traded
    `delay` hours later at the pool price then. With delay 0 on 0x88e6 it is v3. v3 tells an upper from a lower
    break by the tick direction of a token0-quote pool; on a token1-quote pool (0xd0b5) every day goes through the
    replay below, which tells them apart by price."""
    delay = 0

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._pending = None
        self._replaying = False

    def _own_path(self) -> bool:
        return bool(self.delay) or not self.broker.markets[self.utils.market_key].pool_info.is_token0_quote

    def rescale_work(self, row_data):
        if not self._own_path() or self._replaying:
            return super().rescale_work(row_data)
        self._pending = row_data  # the daily trigger; follow_work of the same bar is folded into the replay

    def follow_work(self, row_data):
        if not self._own_path() or self._replaying:
            return super().follow_work(row_data)

    def on_bar(self, row_data):
        super().on_bar(row_data)
        p = self._pending
        if p is None or row_data.timestamp < p.timestamp + timedelta(hours=self.delay):
            return
        self._pending = None
        self._replaying = True
        try:
            self._replay(p, row_data)
        finally:
            self._replaying = False
            self.force_rebuild = False

    def _replay(self, decided, now):
        lp_market = self.broker.markets[self.utils.market_key]
        base = self.gp.base_token.name
        p0, p1 = decided.prices[base], now.prices[base]
        if self.positions and self.out_of_fund_date is None:
            tick0 = lp_market.price_to_raw_tick(p0)
            if self.check_rebalance(lp_market, tick0):
                upper = self.positions[0][0] > tick0  # token0 is the quote on 0x88e6: a lower tick is a higher price
                if not lp_market.pool_info.is_token0_quote:
                    upper = not upper
                if self.signal_deploy:
                    self.build_fraction = Decimal(0) if (not upper or v3.diverged_for(self.daily_ema, decided.timestamp)) \
                        else self.lp_fraction(lp_market, p1)
                self.force_rebuild = True
                super().rescale_work(now)
                self.force_rebuild = False
        if not self.signal_deploy or self.starting_tick is None or self.out_of_fund_date is not None:
            return
        current = self.lp_fraction(lp_market, p0)
        if current is None:
            return
        target = v3.target_fraction_for(self.daily_ema, decided.timestamp)
        due = (abs(target - current) >= v3.FOLLOW_THRESHOLD
               or (target == 0 and current > v3.FOLLOW_EMPTY_TOL)
               or (target >= v3.FOLLOW_FULL_F and current < 1 - v3.FOLLOW_FULL_GAP))
        if due:
            self.follow_rebuild_count += 1
            self.force_rebuild = True
            super().rescale_work(now)
            self.force_rebuild = False


v3.RemixDaoDcaWeekStratStrategy = Delayed


# ---------- one v3 run ----------

def gp_params(r: Run, pool: PoolSpec, csd: datetime, folder: str):
    """process_for_date's settings, with this run's capital, pool and dates."""
    gp = v3.GlobalParams(token0=pool.token0, token1=pool.token1, fee=0.05, init_quote=Decimal(r.initial),
                         quote_token=usdc, base_token=eth, chain_name=pool.chain,
                         contract_address=pool.address, swap_fee=False, dca_usdc_amount=Decimal(10000),
                         dca_add_if_non_empty=False, dca_add_timing=v3.DcaTiming.none,
                         init_quote_usdc=Decimal(r.initial) * v3.INIT_PRICE, dca_addon_price_percent=v3.ZERO,
                         dca_addon_amount_percent=v3.ZERO, dca_addition=v3.DcaAddition.none)
    rp = v3.RemixDAOParams(tick_spread_upper=410, tick_spread_lower=410, tick_upper_boundary_offset=0,
                           tick_lower_boundary_offset=0, rescale_tick_upper_boundary_offset=0,
                           rescale_tick_lower_boundary_offset=0, init_tick_spread=410, tick_spacing=10,
                           tick_gap_lower=1, tick_gap_upper=1)
    tp = v3.TestParams(range_strategy=v3.RangeStrategy.remix_dao, indicator_mult=1, report_name=r.name,
                       indicator_length_hr=1, to_swap=False, aggressive=True, compound=False,
                       rescale_frequency=v3.RescaleFrequency.daily, cal_start_datetime=csd,
                       data_start_date=r.start, data_end_date=r.end, folder=folder, initial_swap=True,
                       flip_param_dates=[], start_with_bull_param=True, initial_type=1,
                       starting_mark_price=Decimal(20))
    return gp, rp, copy.copy(rp), tp


def swap_impact(notional: float, px: float, liquidity: float, pool: PoolSpec) -> float:
    """pool_lp_batch.run's price impact of a swap of `notional` USDC."""
    quote_is_1 = pool.token1 == usdc
    scale = 10.0 ** (pool.token0.decimal - pool.token1.decimal)
    p_raw = (px if quote_is_1 else 1 / px) / scale
    raw1 = notional * (1.0 if quote_is_1 else 1 / px) * 10 ** pool.token1.decimal
    return notional * raw1 / (liquidity * math.sqrt(p_raw)) if liquidity > 0 else 0.0


def gas_usd(name: str, ts: pd.Timestamp, pool: PoolSpec, eth_usd: pd.Series) -> float:
    if pool.chain == "base":
        return batch.ARB_GAS_USD.get(name, 0.0)
    if name not in GAS_UNITS:
        return 0.0
    return GAS_UNITS[name] * GAS_GWEI.get(ts.year, GAS_GWEI[2025]) * 1e-9 * float(eth_usd.asof(ts.normalize()))


def costs_from_actions(actions, price: pd.Series, liq: pd.Series, pool: PoolSpec, eth_usd: pd.Series):
    """Price impact and gas per action timestamp, in USDC; the pool fee is already in Demeter's balances."""
    rows, swap_fee, impact, gas, fee_sale_gas = {}, 0.0, 0.0, 0.0, 0.0
    adds_at = {pd.Timestamp(a.timestamp) for a in actions if type(a).__name__ == "AddLiquidityAction"}
    for a in actions:
        ts = pd.Timestamp(a.timestamp)
        name = type(a).__name__
        g = gas_usd(name, ts, pool, eth_usd)
        gas += g
        cost = g
        if name in ("SwapAction", "BuyAction", "SellAction"):  # v3's market records its swaps as buy / sell
            px = float(price.asof(ts))
            if hasattr(a, "quote_change"):
                notional = abs(float(a.quote_change))
            else:
                notional = float(a.amount) * (px if a.amount.unit.upper() == "ETH" else 1.0)
            swap_fee += float(a.fee) * (px if a.fee.unit.upper() == "ETH" else 1.0)
            hit = swap_impact(notional, px, float(liq.asof(ts)), pool)
            impact += hit
            cost += hit
            if name == "SellAction" and notional < 1_000 and ts in adds_at:
                fee_sale_gas += g  # v3 sells each band's ETH fee in its own swap at a rebuild
        rows[ts] = rows.get(ts, 0.0) + cost
    paid = pd.Series(rows, dtype=float).sort_index().cumsum()
    return paid, {"swap_fee": swap_fee, "impact": impact, "gas": gas, "fee_sale_swap_gas": fee_sale_gas}


def run_one(r: Run) -> dict:
    started = time.time()
    pool = POOLS[r.pool]
    folder = f"{RESULT_DIR}/v3"
    os.makedirs(folder, exist_ok=True)
    if r.bar:
        data = pd.read_pickle(hourly_path(r.pool))
    else:
        _BAR_MINUTES[0] = 1
        data = minute_data(r.pool, r.start, r.end)
    t0 = pd.Timestamp(r.start) + pd.Timedelta(hours=r.hour)
    t1 = pd.Timestamp(r.end) + pd.Timedelta(hours=23, minutes=0 if r.bar else 59)
    daily = pool_signal(data, r.hour, r.end) if r.signal == "pool" else v3.binance_daily_frame(r.start, r.end)
    data = data[(data.index >= t0) & (data.index <= t1)]
    gp, bull, bear, tp = gp_params(r, pool, t0.to_pydatetime(), folder)
    usdc_px = pd.DataFrame(index=data.index, data={"price": v3.ONE})
    Delayed.delay = r.delay
    v3.run_test(bull, bear, tp, gp, data, usdc_px, shape="inverted_gaussian_spec_price",
                upper_ratio=Decimal("0.20"), lower_ratio=Decimal("0.20"), half_gap=0,
                eth_share=v3.EMA_SHARE, daily_ema=daily, deploy=v3.DEPLOY_SIGNAL)
    act = _LAST["actuator"]
    strat = act._strategy
    st = act.account_status_df
    nav_pre = st[("net_value", "")].astype(float)
    nav_pre.index = pd.DatetimeIndex(nav_pre.index)
    price = data["price"].astype(float)
    paid, c = costs_from_actions(act.actions, price, data["currentLiquidity"].astype(float), pool, batch.eth_daily())
    cum = paid.reindex(nav_pre.index, method="ffill").fillna(0.0) if len(paid) else 0.0
    nav = nav_pre - cum
    out = pd.DataFrame({"net": nav, "net_pre": nav_pre, "price": price.reindex(nav.index).ffill()})
    for col in st.columns:  # LP market and wallet columns, for the attribution and the ETH exposure
        if col[0] not in ("net_value", "price"):
            out["|".join(map(str, col))] = pd.to_numeric(st[col].astype(float), errors="coerce").to_numpy()
    if not r.bar:
        out = out.resample("1h").first()
    out.to_csv(f"{RESULT_DIR}/nav_{r.name}.csv")
    ev = pd.DataFrame([(pd.Timestamp(a.timestamp), type(a).__name__) for a in act.actions], columns=["t", "action"])
    ev.to_csv(f"{RESULT_DIR}/actions_{r.name}.csv", index=False)
    window = daily.loc[pd.Timestamp(r.start):pd.Timestamp(r.end)]
    step = paid.diff().fillna(paid) if len(paid) else pd.Series(dtype=float)
    row = {"run": r.name, "pool": f"0x{r.pool}", "start": str(r.start), "end": str(r.end), "initial": r.initial,
           "signal": r.signal, "hour": r.hour, "delay": r.delay, "bar": r.bar or "1min",
           "net": nav.iloc[-1] / r.initial - 1, "net_pre_cost": nav_pre.iloc[-1] / r.initial - 1,
           "maxDD": float((nav / nav.cummax() - 1).min()),
           "builds": int(ev.loc[ev["action"] == "AddLiquidityAction", "t"].nunique()),
           "follow_rebuilds": strat.follow_rebuild_count, "upper": strat.upper_rescale_count,
           "lower": strat.lower_rescale_count, "fees_collected": float(strat.total_quote_fee) / r.initial,
           **{k: v / r.initial for k, v in c.items()},
           "costs_from_2025": float(step.loc["2025":].sum()) / r.initial if len(step) else 0.0,
           "F_mean": float(window["Fp"].mean()), "diverged_days": int(window["diverged"].sum()),
           "secs": round(time.time() - started)}
    pd.DataFrame([row]).to_csv(f"{RESULT_DIR}/run_{r.name}.csv", index=False)
    if r.signal == "pool":
        window.rename_axis("date").to_csv(f"{RESULT_DIR}/signal_pool_h{r.hour:02d}.csv")
    elif r.name == "lp_100k":
        window.rename_axis("date").to_csv(f"{RESULT_DIR}/signal_binance.csv")
    print(f"{r.name}: net {row['net']:+.4f} (pre-cost {row['net_pre_cost']:+.4f}), maxDD {row['maxDD']:+.3f}, "
          f"builds {row['builds']}, gas {row['gas']:.4f}, impact {row['impact']:.4f}, {row['secs']} s", flush=True)
    return row


def run_safe(r: Run) -> dict:
    try:
        return run_one(r)
    except Exception as e:  # keep the queue going; the failure is in the log
        import traceback
        traceback.print_exc()
        print(f"{r.name}: FAILED {e!r}", flush=True)
        return {"run": r.name, "error": repr(e)}


# ---------- spot rules (H38) ----------

def spot_sim(name: str, initial: float, pool: str = "88e6", start: date = CONT_START, end: date = SIGNAL_END) -> dict:
    """F' in ETH spot, the rest USDC; v3's daily order at 00 UTC: the range rules, then follow F'. The pool fee is
    paid in the fill; price impact and one swap's gas per trade are subtracted afterwards, as for the LP runs."""
    p = POOLS[pool]
    data = pd.read_pickle(hourly_path(pool))
    t0, t1 = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(hours=23)
    data = data[(data.index >= t0) & (data.index <= t1)]
    price = data["price"].astype(float)
    liq = data["currentLiquidity"].astype(float)
    daily = v3.binance_daily_frame(start, end)
    eth_usd = batch.eth_daily()

    def row_for(ts):
        return daily.loc[(ts - pd.Timedelta(days=1)).normalize()]

    cash, coin, centre = float(initial), 0.0, None
    trades = []
    cash_path, coin_path = np.empty(len(price)), np.empty(len(price))

    def trade(ts, px, target_value, kind):
        nonlocal cash, coin
        delta = target_value - coin * px  # USDC notional, + buys ETH
        if abs(delta) < 1e-6:
            return
        fee = abs(delta) * 0.0005
        coin += delta / px
        cash -= delta + fee
        trades.append({"t": ts, "kind": kind, "notional": abs(delta), "swap_fee": fee,
                       "impact": swap_impact(abs(delta), px, float(liq.asof(ts)), p),
                       "gas": gas_usd("SwapAction", ts, p, eth_usd)})

    prev_target = None
    for i, ts in enumerate(price.index):
        px = float(price.iloc[i])
        if i == 0:
            target = float(row_for(ts)["Fp"])
            trade(ts, px, target * cash, "first")
            centre, prev_target = (px if target > 0 else None), target
        elif ts.hour == 0:
            r0 = row_for(ts)
            if coin > 0 and centre is not None:
                if px < centre * v3.LOWER_STOP:
                    trade(ts, px, 0.0, "lower")
                    centre = None
                elif px > centre * v3.UPPER_REBUILD:
                    if int(r0["diverged"]):
                        trade(ts, px, 0.0, "upper_diverged")
                        centre = None
                    else:
                        centre = px
            value = cash + coin * px
            current = coin * px / value if value > 0 else 0.0
            target = float(r0["Fp"])
            due = (abs(target - current) >= float(v3.FOLLOW_THRESHOLD) or (target == 0 and current > 0)
                   or (target >= float(v3.FOLLOW_FULL_F) and current < 1 - float(v3.FOLLOW_FULL_GAP)))
            if due:
                trade(ts, px, target * value, "follow" if target != prev_target else "drift")
                centre = px if target > 0 else None
            prev_target = target
        cash_path[i], coin_path[i] = cash, coin
    t = pd.DataFrame(trades, columns=["t", "kind", "notional", "swap_fee", "impact", "gas"])
    paid = (t["impact"] + t["gas"]).groupby(t["t"]).sum().cumsum() if len(t) else pd.Series(dtype=float)
    nav_pre = pd.Series(cash_path, index=price.index) + pd.Series(coin_path, index=price.index) * price
    nav = nav_pre - (paid.reindex(price.index, method="ffill").fillna(0.0) if len(paid) else 0.0)
    pd.DataFrame({"net": nav, "net_pre": nav_pre, "price": price, "eth": coin_path}).to_csv(f"{RESULT_DIR}/nav_{name}.csv")
    t.to_csv(f"{RESULT_DIR}/trades_{name}.csv", index=False)
    drift = t["kind"] == "drift"
    row = {"run": name, "pool": f"0x{pool}", "start": str(start), "end": str(end), "initial": initial,
           "net": nav.iloc[-1] / initial - 1, "net_pre_cost": nav_pre.iloc[-1] / initial - 1,
           "maxDD": float((nav / nav.cummax() - 1).min()), "trades": len(t), "drift_trades": int(drift.sum()),
           "swap_fee": t["swap_fee"].sum() / initial, "impact": t["impact"].sum() / initial,
           "gas": t["gas"].sum() / initial,
           "drift_cost": t.loc[drift, ["swap_fee", "impact", "gas"]].to_numpy().sum() / initial}
    pd.DataFrame([row]).to_csv(f"{RESULT_DIR}/run_{name}.csv", index=False)
    print(f"{name}: net {row['net']:+.4f}, maxDD {row['maxDD']:+.3f}, trades {row['trades']} "
          f"(drift {row['drift_trades']})", flush=True)
    return row


# ---------- combine ----------

YEARS = ("2022", "2023", "2024", "2025", "2026")


def load_nav(name: str) -> pd.DataFrame:
    return pd.read_csv(f"{RESULT_DIR}/nav_{name}.csv", index_col=0, parse_dates=True)


def stats(net: pd.Series, initial: float) -> dict:
    """Total, hourly max drawdown, the longest time under water (days), and calendar years (2026 to 8/31)."""
    x = net / initial
    under = x < x.cummax()
    runs = (under != under.shift()).cumsum()
    longest = under.groupby(runs).sum().max() / 24 if under.any() else 0.0
    out = {"total": x.iloc[-1] - 1, "maxDD": float((x / x.cummax() - 1).min()), "underwater_days": float(longest)}
    for y in YEARS:
        part = x.loc[:f"{y}-12-31 23:00"]
        prev = x.loc[:f"{int(y) - 1}-12-31 23:00"]
        if len(part) and part.index[-1].year == int(y):
            out[y] = part.iloc[-1] / (prev.iloc[-1] if len(prev) else 1.0) - 1
    return out


def column(df: pd.DataFrame, *parts: str) -> pd.Series:
    hits = [c for c in df.columns if all(p.lower() in c.lower() for p in parts)]
    if len(hits) != 1:
        raise KeyError(f"{parts}: {hits}")
    return df[hits[0]].astype(float)


def eth_exposure(nav: pd.DataFrame) -> pd.Series:
    """ETH value (in the bands, uncollected and in the wallet) over the net value before costs."""
    if "eth" in nav.columns:  # spot books
        return nav["eth"] * nav["price"] / nav["net_pre"]
    b = column(nav, "lp|base_in_position") + column(nav, "lp|base_uncollected") + column(nav, "tokens|eth")
    return b * nav["price"] / nav["net_pre"]


def attribution(name: str, initial: float) -> pd.DataFrame:
    """The LP book's hourly change split per calendar year, in pt of the initial capital:
      price     ETH held still: the coins placed at each build (fixed until the next build) plus the wallet's ETH
      il        the bands' value without fees minus those coins held still
      fees      the change of the uncollected fees (collected fees move to the wallet at a build, unchanged)
      builds    hours with an action: what is left of the change (the pool fee of the swaps, the price move of
                the hour's other coins); swap_fee is the pool fee Demeter charged, inside builds
      impact, gas  subtracted afterwards (costs_from_actions)
      other     remainder outside the build hours; should stay near 0"""
    nav = load_nav(name)
    p = nav["price"]
    bp, qp = column(nav, "lp|base_in_position"), column(nav, "lp|quote_in_position")
    bu, qu = column(nav, "lp|base_uncollected"), column(nav, "lp|quote_uncollected")
    bw, qw = column(nav, "tokens|eth"), column(nav, "tokens|usdc")
    act = pd.read_csv(f"{RESULT_DIR}/actions_{name}.csv", parse_dates=["t"])
    hours = set(act["t"].dt.floor("h"))
    is_act = pd.Series(nav.index.isin(list(hours)), index=nav.index)
    # a segment starts at every action hour (a build, a withdrawal to USDC, a recentre): the coins in the bands
    # right after it are what "held still" means until the next one
    seg = pd.Series(np.nan, index=nav.index)
    seg.loc[is_act] = range(int(is_act.sum()))
    seg = seg.ffill()
    hold = bp.groupby(seg).transform("first").fillna(0.0)
    dp = p.diff().fillna(0.0)
    lp_x = bp * p + qp
    price = (hold.shift().fillna(0.0) + bw.shift().fillna(0.0)) * dp
    il = lp_x.diff().fillna(0.0) - hold.shift().fillna(0.0) * dp
    fees = (bu * p + qu).diff().fillna(0.0)
    total = nav["net_pre"].diff().fillna(0.0)
    rest = total - price - il - fees
    builds_part = rest.where(is_act, 0.0)
    other = rest.where(~is_act, 0.0)
    # at a build hour the decomposition above is not valid: credit the previous holdings' price move to price and
    # leave the rest in builds
    held = (bp + bu + bw).shift().fillna(0.0) * dp
    price = price.where(~is_act, held)
    il = il.where(~is_act, 0.0)
    fees = fees.where(~is_act, 0.0)
    builds_part = (total - price - il - fees - other).where(is_act, 0.0)
    cost = (nav["net_pre"] - nav["net"]).diff().fillna(nav["net_pre"].iloc[0] - nav["net"].iloc[0])
    frame = pd.DataFrame({"price": price, "il": il, "fees": fees, "builds": builds_part, "other": other,
                          "impact_gas": -cost, "total": total - cost})
    out = frame.groupby(frame.index.year).sum() / initial * 100
    out.loc["all"] = out.sum()
    return out.round(1)


def window_checks(x: pd.Series) -> dict:
    """H2's three, on the windows' net returns in start order: median > 0, >= 12 of 16 > 0, both halves' medians > 0."""
    x = x.sort_index()
    h = len(x) // 2
    return {"median": float(x.median()), "positive": int((x > 0).sum()), "n": len(x),
            "first_half": float(x.iloc[:h].median()), "second_half": float(x.iloc[h:].median()),
            "pass": bool(x.median() > 0 and (x > 0).sum() >= 12 and x.iloc[:h].median() > 0 and x.iloc[h:].median() > 0)}


def combine():
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    runs = pd.concat([pd.read_csv(f) for f in sorted(__import__("glob").glob(f"{RESULT_DIR}/run_*.csv"))
                      if "test_" not in f and "cal_" not in f], ignore_index=True).set_index("run")
    runs.to_csv(f"{RESULT_DIR}/runs_all.csv")
    # H38: three uses of F'
    lp, lp50, sp, sp50 = (load_nav(n) for n in ("lp_100k", "lp_50k", "spot_100k", "spot_50k"))
    idx = lp.index.intersection(sp.index)
    books = {"lp": lp["net"].reindex(idx), "spot": sp["net"].reindex(idx),
             "mix": (lp50["net"].reindex(idx) + sp50["net"].reindex(idx)),
             "hold ETH": 100_000 * lp["price"].reindex(idx) / lp["price"].iloc[0]}
    exp = {"lp": eth_exposure(lp).reindex(idx), "spot": eth_exposure(sp).reindex(idx),
           "mix": 0.5 * eth_exposure(lp50).reindex(idx) + 0.5 * eth_exposure(sp50).reindex(idx), "hold ETH": None}
    rows = []
    for k, net in books.items():
        r = {"book": k, **stats(net, 100_000)}
        if exp[k] is not None:
            r["eth_exposure_mean"] = float(exp[k].mean())
        rows.append(r)
    for name, key in (("base_lp_100k", "base lp (listed)"), ("base_spot_100k", "base spot (listed)")):
        if os.path.exists(f"{RESULT_DIR}/nav_{name}.csv"):
            n = load_nav(name)
            rows.append({"book": key, **stats(n["net"], 100_000), "eth_exposure_mean": float(eth_exposure(n).mean())})
    h38 = pd.DataFrame(rows).set_index("book")
    cost_cols = ["swap_fee", "impact", "gas", "costs_from_2025", "fee_sale_swap_gas", "builds", "trades",
                 "drift_trades", "drift_cost", "fees_collected"]
    h38_costs = runs.loc[[n for n in ("lp_100k", "lp_50k", "spot_100k", "spot_50k", "base_lp_100k", "base_spot_100k")
                          if n in runs.index], [c for c in cost_cols if c in runs.columns]]
    print("H38 books ($100k, 2022-01-01 .. 2026-08-31, hourly, after costs)\n", h38.to_string(float_format=lambda v: f"{v:+.4f}"))
    print("H38 costs and counts (fractions of capital)\n", h38_costs.to_string(float_format=lambda v: f"{v:.4f}"))
    d = h38.loc["spot"] - h38.loc["lp"]
    m = h38.loc["mix"] - h38.loc["lp"]
    print(f"H38 spot - lp (main comparison, descriptive): total {d['total']:+.4f}, maxDD {d['maxDD']:+.4f}, "
          + " ".join(f"{y} {d[y]:+.3f}" for y in YEARS))
    print(f"H38 mix - lp (listed): total {m['total']:+.4f}, maxDD {m['maxDD']:+.4f}")
    att = attribution("lp_100k", 100_000)
    print("H38 lp attribution (pt of $100k)\n", att.to_string())
    h38.to_csv(f"{RESULT_DIR}/h38_books.csv")
    att.to_csv(f"{RESULT_DIR}/h38_attribution.csv")
    pd.DataFrame(books).to_csv(f"{RESULT_DIR}/h38_navs.csv")
    # H39
    win = pd.Series({s: runs.loc[f"win_{s}", "net"] for s in map(str, WINDOW_STARTS)})
    dwin = pd.Series({s: runs.loc[f"delay_win_{s}", "net"] for s in map(str, WINDOW_STARTS)})
    wdd = pd.Series({s: runs.loc[f"win_{s}", "maxDD"] for s in map(str, WINDOW_STARTS)})
    dwdd = pd.Series({s: runs.loc[f"delay_win_{s}", "maxDD"] for s in map(str, WINDOW_STARTS)})
    wt = pd.DataFrame({"net": win, "delay_net": dwin, "delay_minus": dwin - win, "maxDD": wdd,
                       "delay_maxDD_minus": dwdd - wdd})
    print("H39 windows (net after costs; the last one is 11 months)\n", wt.to_string(float_format=lambda v: f"{v:+.4f}"))
    print("H39 positive-return check, UTC 00:", window_checks(win))
    print("H39 positive-return check, one-hour delay:", window_checks(dwin))
    cont = {"UTC 00": lp["net"], "delay 1h": load_nav("delay_cont")["net"]}
    hours = {h: load_nav(f"hour_{h:02d}")["net"] for h in range(24) if os.path.exists(f"{RESULT_DIR}/nav_hour_{h:02d}.csv")}
    ct = pd.DataFrame({k: stats(v, 100_000) for k, v in cont.items()}).T
    hs = pd.DataFrame({h: stats(v, 100_000) for h, v in hours.items()}).T
    print("H39 continuous\n", ct.to_string(float_format=lambda v: f"{v:+.4f}"))
    print("H39 24 judgement hours (pool signal, listed)\n",
          hs[["total", "maxDD"]].describe().loc[["mean", "50%", "min", "max"]].to_string(float_format=lambda v: f"{v:+.4f}"),
          f"\npositive total: {(hs['total'] > 0).sum()} of {len(hs)}")
    refs = {"hold ETH": books["hold ETH"]}
    h37 = "result/candidate-vs-c/nav_h37.csv"
    if os.path.exists(h37):
        e = pd.read_csv(h37, index_col=0, parse_dates=True)["ETH half"]
        e = e[(e.index >= lp.index[0]) & (e.index <= lp.index[-1])]
        refs["C ETH half"] = 100_000 * e / e.iloc[0]
    rt = pd.DataFrame({k: stats(v, 100_000) for k, v in refs.items()}).T
    print("H39 references (listed)\n", rt.to_string(float_format=lambda v: f"{v:+.4f}"))
    wt.to_csv(f"{RESULT_DIR}/h39_windows.csv")
    ct.to_csv(f"{RESULT_DIR}/h39_continuous.csv")
    hs.to_csv(f"{RESULT_DIR}/h39_hours.csv")
    rt.to_csv(f"{RESULT_DIR}/h39_references.csv")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--cache", action="store_true")
    a.add_argument("--test", action="store_true")
    a.add_argument("--calibrate", action="store_true")
    a.add_argument("--runs", action="store_true")
    a.add_argument("--spot", action="store_true")
    a.add_argument("--combine", action="store_true")
    a.add_argument("--only", default="", help="comma-separated run name prefixes")
    a.add_argument("--workers", type=int, default=1)
    a = a.parse_args()
    os.makedirs(RESULT_DIR, exist_ok=True)
    if a.combine:
        combine()
        return
    batch.eth_daily()  # fill the cache before the workers read it
    if a.cache:
        for k in POOLS:
            build_hourly(k)
        return
    if a.test:
        s, e = date(2024, 2, 20), date(2024, 4, 20)
        for r in (Run("test_lp", start=s, end=e), Run("test_delay", start=s, end=e, delay=1),
                  Run("test_hour07", start=s, end=e, signal="pool", hour=7),
                  Run("test_base", pool="d0b5", start=s, end=e)):
            run_one(r)
        spot_sim("test_spot", 100_000, start=s, end=e)
        return
    if a.calibrate:
        for s in CALIBRATION:
            run_safe(Run(f"cal_min_{s}", start=s, end=window_end(s), bar=None))
        return
    if a.spot:
        spot_sim("spot_100k", 100_000)
        spot_sim("spot_50k", 50_000)
        spot_sim("base_spot_100k", 100_000, pool="d0b5", start=BASE_START)
        return
    if a.runs:
        todo = [r for r in all_runs() if not os.path.exists(f"{RESULT_DIR}/run_{r.name}.csv")
                and (not a.only or r.name.startswith(tuple(a.only.split(","))))]
        print(f"{len(todo)} Demeter runs", flush=True)
        with multiprocessing.Pool(a.workers, maxtasksperchild=1) as pool:
            pool.map(run_safe, todo, chunksize=1)


if __name__ == "__main__":
    main()
