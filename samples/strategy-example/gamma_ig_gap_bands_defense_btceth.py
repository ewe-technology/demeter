"""
ETH-cbBTC 防禦邏輯 規格書（WB＋ETH強勢25%）的回測入口。

從 gamma_ig_gap_bands_defense_v6.py 複製後改寫，沿用資料載入、平行執行、報表框架與四個 EMA 虛擬帳戶
的階段復歸邏輯；訊號價格、資產配置、LP 形狀與獎勵處理改為新規格書版本。與 v6 的差異：

* 訊號價格 G = sqrt(ETH/USD x BTC/USD)，EMA 退避多一條「EMA 低於 20 日前」的斜率條件
* ETH 強弱 = R(ETH/BTC) 對 EMA100；強勢時 F 的 25% 留 ETH、退避資金放 USDC，弱勢時退避資金放 BTC
* LP 為均等單一區間：強勢合計 20%（±10%），弱勢合計 40%（±20%）；上下出界都以當時價格為中心重建
* 四種資產（LP、ETH、BTC、USDC）任一項偏離目標 12.5% 才重建；換倉成本 0.1%（只算最小兌換量）
* 手續費不再投入，以 ETH 計 1 ETH 起算；報表以 ETH 枚數為主，另列 BTC 與美元

池子用主網 WBTC/WETH 0.05%（repo 內有資料，也是規格書校正手續費的池子），Base cbBTC/WETH 沒有資料。
mode=plain 是規格書的「通常LP」對照組：均等型 ±10%、無訊號、出界即重建。
"""
import copy
import math
import multiprocessing
import random
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

import demeter
from demeter import Actuator, AtTimeTrigger, ChainType, MarketInfo, PeriodTrigger, Snapshot, TokenInfo
from demeter.result import return_rate
from demeter.result.metrics.calculator import max_draw_down
from demeter.uniswap import UniV3Pool

from base_strategy import BaseRemixDaoStrategy
from export_file import export_stable_apr_results
from market_v2 import UniLpMarketV2
from math_const import ZERO, ONE
from remix_dao_utils import RemixDaoUtils, RemixDAOParams, performance_metrics_for_dca
from rm_types import RescaleFrequency, TestParams, GlobalParams, RangeStrategy

USDC = TokenInfo(name="usdc", decimal=6)
MODE_SIGNAL, MODE_PLAIN = "signal", "plain"

# spec sheet 2.3: four virtual accounts on G, each with its own EMA; F = mean of their deployed fractions
EMA_SPANS = (90, 100, 110, 120)
EMA_SLOPE_DAYS = 20                                     # exit also needs EMA_n < EMA_n 20 days ago
EMA_WARMUP_DAYS = 3 * max(EMA_SPANS) + EMA_SLOPE_DAYS   # adjust=False EMA needs ~3 spans to forget its seed
DATA_FLOOR = date(2021, 5, 13)   # first day with minute data for both pools (WBTC/WETH lacks 2021-05-12);
                                # 2022 runs warm up from here, ~230 days instead of the spec sheet's 2017 start
LOWER_STOP, UPPER_REBUILD = 0.80, 1.20
REFILL_CONFIRM_DAYS = 3
REFILL_STAGES = ((1, 1.05), (2, 1.0833), (3, 1.1167), (4, 1.15))  # (stage, close / low), stage k -> k/4 deployed

# spec sheet 2.1 / 2.5: strength on R = ETH/BTC vs EMA100(R); strong keeps 25% of LP allocation as ETH
STRENGTH_SPAN = 100
ETH_KEEP = Decimal("0.25")
RANGE_STRONG, RANGE_WEAK = Decimal("0.10"), Decimal("0.20")   # half width: 合計 20% / 40%

# spec sheet 2.6
FOLLOW_THRESHOLD = Decimal("0.125")   # any of LP / ETH / BTC / USDC this far from target -> rebuild
LP_SHORT_TOL = Decimal("0.01")        # target LP 100% but LP short by more than this
USDC_DUST = Decimal("0.001")          # target USDC 0 but holding more than this
SWAP_COST = Decimal("0.001")          # on the minimum converted volume; slippage cap 0.5% is not a cost
LOG_TICK = math.log(1.0001)


class VirtualAccount:
    """One spec sheet 2.3 virtual account, stepped once per daily close of G. Floats: it only produces F."""

    def __init__(self, span: int):
        self.span = span
        self.armed = False          # True once close was above the EMA since the last exit
        self.deployed = 0.0         # 0 / .25 / .5 / .75 / 1
        self.centre: float | None = None
        self.low: float | None = None   # lowest close since the exit, drives the refill
        self.stage = 0
        self.confirm = 0
        self.started = False

    def exit(self, close: float) -> None:
        self.deployed, self.centre, self.low, self.stage, self.confirm = 0.0, None, close, 0, 0

    def step(self, close: float, ema: float, ema_prev: float = float("nan")) -> None:
        if not self.started:  # ponytail: engine starts at warm-up start, not 2017; ~360 days settle it
            self.started, self.armed = True, close > ema
            if self.armed:
                self.deployed, self.stage, self.centre = 1.0, 4, close
            else:
                self.low = close
            return
        # 1 EMA exit: close under EMA and the EMA itself falling (NaN slope in the first days -> no exit)
        if self.armed and close < ema and ema < ema_prev:
            self.exit(close)
            self.armed = False
        elif not self.armed and close > ema:                # 2 re-arm, no buy
            self.armed = True
        if self.deployed > 0 and close < self.centre * LOWER_STOP:      # 3 lower stop
            self.exit(close)
        elif self.deployed > 0 and close > self.centre * UPPER_REBUILD: # 4 upper rebuild, same size
            self.centre = close
        if self.deployed < 1:                               # 5 staged refill on the rebound from low
            self.low = min(self.low, close)
            self.confirm = self.confirm + 1 if close >= self.low * REFILL_STAGES[0][1] else 0
            nxt = self.stage + 1   # at most one stage a day; a pullback keeps the stage, only an exit resets it
            advance = (self.confirm >= REFILL_CONFIRM_DAYS if nxt == 1
                       else close >= self.low * REFILL_STAGES[nxt - 1][1])
            if advance:
                self.stage, self.deployed, self.centre = nxt, nxt / 4, close


def signal_frame(btc_eth: pd.Series, eth_usd: pd.Series) -> pd.DataFrame:
    """UTC daily closes -> G, R, EMA100(R), strong flag and the signal engine F.
    `btc_eth` is the pool price (ETH per BTC), `eth_usd` the ETH/USDC price; both minute series that should
    start EMA_WARMUP_DAYS before the window. BTC/USD = btc_eth x eth_usd, so G = eth_usd x sqrt(btc_eth)."""
    d = pd.concat({"p": btc_eth.astype(float).resample("1D").last(),
                   "e": eth_usd.astype(float).resample("1D").last()}, axis=1).dropna()
    g = d["e"] * d["p"] ** 0.5
    r = 1.0 / d["p"]
    r_ema = r.ewm(span=STRENGTH_SPAN, adjust=False).mean()
    emas = {n: g.ewm(span=n, adjust=False).mean() for n in EMA_SPANS}
    prevs = {n: emas[n].shift(EMA_SLOPE_DAYS) for n in EMA_SPANS}
    accounts = [VirtualAccount(n) for n in EMA_SPANS]
    fractions = []
    for day, close in g.items():
        for a in accounts:
            a.step(float(close), float(emas[a.span][day]), float(prevs[a.span][day]))
        fractions.append(sum(a.deployed for a in accounts) / len(accounts))
    return pd.DataFrame({"G": g, "R": r, "R_ema": r_ema, "strong": r >= r_ema, "F": fractions})


def allocation(f: Decimal, strong: bool) -> Tuple[Dict[str, Decimal], Decimal]:
    """Spec sheet 2.5: (value share of LP / ETH kept out of LP / BTC / USDC, LP half width)."""
    if strong:
        return {"lp": f * (ONE - ETH_KEEP), "eth": f * ETH_KEEP, "btc": ZERO, "usdc": ONE - f}, RANGE_STRONG
    return {"lp": f, "eth": ZERO, "btc": ONE - f, "usdc": ZERO}, RANGE_WEAK


def range_ticks(current_tick: int, ratio: Decimal, spacing: int) -> Tuple[int, int]:
    """Tick range covering price x (1 - ratio) ... x (1 + ratio) around the rounded current tick
    (higher tick = higher BTC price, the WBTC/WETH orientation)."""
    centre = round(current_tick / spacing) * spacing
    up = round(math.log1p(float(ratio)) / LOG_TICK / spacing) * spacing
    down = round(-math.log1p(-float(ratio)) / LOG_TICK / spacing) * spacing
    return centre - down, centre + up


def lp_quote_share(current_tick: int, lower_tick: int, upper_tick: int) -> Decimal:
    """Share of an in-range position's value held in the quote token (ETH). Raw units cancel:
    y = sqrt(p) - sqrt(pa) and x*p = p/sqrt(p) - p/sqrt(pb) are both in raw token1."""
    sc, sa, sb = (1.0001 ** (t / 2) for t in (current_tick, lower_tick, upper_tick))
    y, xp = sc - sa, sc * sc * (1 / sc - 1 / sb)
    return Decimal(str(round(y / (y + xp), 12)))


def swap_deltas(cur: List[Decimal], want: List[Decimal], prices: List[Decimal],
                cost: Decimal = SWAP_COST) -> Tuple[List[Decimal], Decimal]:
    """Net token changes moving `cur` to `want` (prices in ETH), and the cost in ETH. The cost is `cost` x the
    minimum converted volume; buyers receive (1 - cost) of what they asked for, like a fee on the trade."""
    sold = -sum(((w - c) * p for c, w, p in zip(cur, want, prices) if w < c), ZERO)
    return [(w - c) * (ONE - cost) if w > c else w - c for c, w in zip(cur, want)], sold * cost


class EthBtcDefenseStrategy(BaseRemixDaoStrategy):
    """Base = BTC, quote = ETH, plus USDC as a third broker asset priced in ETH (see run_test)."""

    def __init__(self, _utils: RemixDaoUtils, _params: TestParams, _gp: GlobalParams,
                 usdc_prices: pd.Series, daily: pd.DataFrame | None, mode: str = MODE_SIGNAL):
        super().__init__(_utils, _params, _gp)
        if _utils.lp_market.pool_info.is_token0_quote:
            raise ValueError("only the WBTC/WETH orientation (token0 = base) is supported")
        if mode == MODE_SIGNAL and daily is None:
            raise ValueError("mode=signal needs the signal_frame")
        self.daily, self.mode, self.usdc_prices = daily, mode, usdc_prices
        self.positions: list = []                 # at most one (lower_tick, upper_tick, ...) position
        self.starting_tick: int | None = None
        self.out_of_fund_date: datetime | None = None
        self.reward_eth = ZERO                    # fees valued in ETH on the day they were collected
        self.swap_cost_eth = ZERO
        self.rebuild_count = self.out_of_range_rebuilds = 0
        self.lp_share_sum, self.lp_share_days = ZERO, 0
        self.daily_log: List[dict] = []
        self.rebuild_log: List[dict] = []
        self.spreads: List[int] = []
        # filled by calculate_final_result
        self.total_fee = self.total_swap_fee = ZERO
        self.total_base_swap_fee = self.total_quote_swap_fee = ZERO
        self.final_total_net_value = self.final_lp_net_value = ZERO
        self.total_invested_usdc = self.total_fee_usd = ZERO
        self.total_net_value_usd = self.total_lp_value_usd = ZERO
        self.init_quote_usd_price = self.final_quote_usd_price = ZERO
        self.final_price = ZERO
        self.fee_value_end = ZERO

    def initialize(self):
        self.triggers.append(AtTimeTrigger(time=self.params.cal_start_datetime, do=self.first_lp))
        self.add_column(self.utils.market_key, "usdc_price", self.usdc_prices)
        self.triggers.append(PeriodTrigger(time_delta=timedelta(days=1), do=self.daily_work))  # 00:00 UTC judgement
        end = self.params.data_end_date
        self.triggers.append(AtTimeTrigger(time=datetime(end.year, end.month, end.day, 23, 59, 0),
                                           do=self.calculate_final_result))

    # ---- state -------------------------------------------------------------------------------------------
    def _lp_market(self) -> UniLpMarketV2:
        return self.broker.markets[self.utils.market_key]

    def _prices(self, row_data: Snapshot) -> Tuple[Decimal, Decimal]:
        """(BTC price in ETH, USDC price in ETH)"""
        return row_data.prices[self.gp.base_token.name], row_data.prices[USDC.name]

    def _wallet(self) -> Tuple[Decimal, Decimal, Decimal]:
        """Free (btc, eth, usdc): collected fees stay in the wallet but out of the strategy's capital."""
        return (self.broker.get_token_balance(self.gp.base_token) - self.total_base_fee,
                self.broker.get_token_balance(self.gp.quote_token) - self.total_quote_fee,
                self.broker.get_token_balance(USDC))

    def _lp_value(self) -> Decimal:
        return self._lp_market().get_market_balance().net_value if self.positions else ZERO

    def target(self, timestamp: datetime) -> Tuple[Dict[str, Decimal], Decimal, Decimal, bool]:
        """(shares, half width, F, strong) judged on the last completed UTC day, like the 00:00 close."""
        if self.mode == MODE_PLAIN:
            return {"lp": ONE, "eth": ZERO, "btc": ZERO, "usdc": ZERO}, RANGE_STRONG, ONE, False
        row = self.daily.loc[pd.Timestamp(timestamp - timedelta(days=1)).normalize()]
        f, strong = Decimal(str(row["F"])), bool(row["strong"])
        shares, ratio = allocation(f, strong)
        return shares, ratio, f, strong

    # ---- actions -----------------------------------------------------------------------------------------
    def collect_fees(self, price: Decimal) -> None:
        lp_market = self._lp_market()
        for pos in list(self.positions):
            base_fee, quote_fee = lp_market.collect_fee(pos, collect_to_user=True)
            self.total_base_fee += base_fee
            self.total_quote_fee += quote_fee
            self.reward_eth += quote_fee + base_fee * price
            if pos not in lp_market.positions:   # collect_fee drops an empty position
                self.positions.remove(pos)

    def rebuild(self, row_data: Snapshot, why: str) -> None:
        lp_market = self._lp_market()
        p, u = self._prices(row_data)
        current_tick = lp_market.price_to_raw_tick(p)
        self.collect_fees(p)
        old = (self.positions[0][0], self.positions[0][1]) if self.positions else None
        for pos in self.positions:
            lp_market.remove_liquidity(pos, collect=True)
        self.positions = []

        shares, ratio, f, strong = self.target(row_data.timestamp)
        btc, eth, usdc = self._wallet()
        value = btc * p + eth + usdc * u
        lp_value, lp_btc, lp_eth, tick_lo, tick_hi = shares["lp"] * value, ZERO, ZERO, None, None
        if lp_value > ZERO:
            tick_lo, tick_hi = range_ticks(current_tick, ratio, self.utils.params.tick_spacing)
            w = lp_quote_share(current_tick, tick_lo, tick_hi)   # ETH / BTC halves that fill the range exactly
            lp_eth, lp_btc = lp_value * w, lp_value * (ONE - w) / p
        want = [shares["btc"] * value / p + lp_btc, shares["eth"] * value + lp_eth, shares["usdc"] * value / u]
        deltas, cost = swap_deltas([btc, eth, usdc], want, [p, ONE, u])
        for token, delta in zip((self.gp.base_token, self.gp.quote_token, USDC), deltas):
            if delta > ZERO:
                self.broker.add_to_balance(token, delta)
            elif delta < ZERO:
                self.broker.subtract_from_balance(token, -delta)
        self.swap_cost_eth += cost
        self.total_quote_swap_fee += cost

        if lp_value > ZERO:
            free_btc, free_eth, _ = self._wallet()
            position, used_base, used_quote, _ = lp_market.add_liquidity_by_tick(
                tick_lo, tick_hi, min(lp_btc, free_btc), min(lp_eth, free_eth), tick=current_tick)
            if used_base == ZERO and used_quote == ZERO:
                lp_market.positions.pop(position, None)
                self.out_of_fund_date = row_data.timestamp
            else:
                self.positions.append(position)
                self.spreads.append(tick_hi - tick_lo)
        self.rebuild_count += 1
        self.rebuild_log.append({"time": row_data.timestamp, "why": why, "F": float(f), "strong": strong,
                                 "btc_eth": float(p), "equity_eth": float(value), "old_range": old,
                                 "new_range": (tick_lo, tick_hi), "swap_cost_eth": float(cost)})
        print(f"[{self.mode}] {row_data.timestamp:%Y-%m-%d %H:%M} rebuild ({why}) F {float(f):.4f} "
              f"{'strong' if strong else 'weak'} equity {float(value):.4f} ETH range +-{float(ratio):.0%}")

    def first_lp(self, row_data: Snapshot) -> None:
        if self._lp_market().positions:
            raise RuntimeError("shouldn't have any position")
        self.init_quote_usd_price = self.get_quote_usdc_price(row_data)
        self.broker.add_to_balance(self.gp.quote_token, self.gp.init_quote)
        self.total_invested_usdc = self.gp.init_quote * self.init_quote_usd_price
        self.starting_tick = self._lp_market().price_to_raw_tick(self._prices(row_data)[0])
        self.rebuild(row_data, "start")

    def daily_work(self, row_data: Snapshot) -> None:
        """Spec sheet 2.6: once a day, rebuild everything to the target when the book drifted or the LP ran out."""
        if self.starting_tick is None or self.out_of_fund_date is not None:
            return
        try:
            shares, _, f, strong = self.target(row_data.timestamp)
        except KeyError:  # spec sheet: missing close -> do nothing that day
            print(f"[{self.mode}] {row_data.timestamp:%Y-%m-%d} no daily close, skip")
            return
        p, u = self._prices(row_data)
        self.collect_fees(p)
        btc, eth, usdc = self._wallet()
        lp_value = self._lp_value()
        value = lp_value + btc * p + eth + usdc * u
        if value <= ZERO:
            return
        cur = {"lp": lp_value / value, "eth": eth / value, "btc": btc * p / value, "usdc": usdc * u / value}
        self.lp_share_sum += cur["lp"]
        self.lp_share_days += 1
        tick = self._lp_market().price_to_raw_tick(p)
        out_of_range = bool(self.positions) and not (self.positions[0][0] <= tick < self.positions[0][1])
        why = None
        if out_of_range:
            why = "out of range"
        elif any(abs(cur[k] - shares[k]) >= FOLLOW_THRESHOLD for k in cur):
            why = "drift >= 12.5%"
        elif shares["lp"] == ZERO and self.positions:
            why = "target LP 0"
        elif shares["lp"] >= ONE and cur["lp"] < ONE - LP_SHORT_TOL:
            why = "target LP 100%"
        elif shares["usdc"] == ZERO and cur["usdc"] > USDC_DUST:
            why = "target USDC 0"
        self.daily_log.append({"date": row_data.timestamp.date(), "btc_eth": float(p), "F": float(f),
                               "strong": strong, "equity_eth": float(value), **{f"cur_{k}": float(v) for k, v in cur.items()},
                               "rebuild": why or ""})
        if why:
            if out_of_range:
                self.out_of_range_rebuilds += 1
            self.rebuild(row_data, why)

    def calculate_final_result(self, row_data: Snapshot) -> None:
        p, u = self._prices(row_data)
        self.collect_fees(p)
        lp_value = self._lp_value()
        assets = (self.broker.get_token_balance(self.gp.base_token) * p + self.broker.get_token_balance(self.gp.quote_token)
                  + self.broker.get_token_balance(USDC) * u)
        self.final_price = p
        self.final_lp_net_value = lp_value
        self.final_total_net_value = lp_value + assets
        self.fee_value_end = self.total_quote_fee + self.total_base_fee * p
        self.total_fee = self.fee_value_end
        self.total_swap_fee = self.total_quote_swap_fee
        usd = self.final_quote_usd_price = self.get_quote_usdc_price(row_data)
        self.total_fee_usd = self.total_fee * usd
        self.total_net_value_usd = self.final_total_net_value * usd
        self.total_lp_value_usd = lp_value * usd

    def on_bar(self, row_data: Snapshot):
        pass

    def finalize(self):
        name = self.params.report_name
        pd.DataFrame(self.daily_log).to_csv(f"{self.params.folder}/daily_{name}.csv", index=False)
        pd.DataFrame(self.rebuild_log).to_csv(f"{self.params.folder}/rebuilds_{name}.csv", index=False)


def run_test(bull_params: RemixDAOParams, params: TestParams, gp: GlobalParams, processed_data: pd.DataFrame,
             usdc_price_data: pd.DataFrame, daily: pd.DataFrame | None, mode: str) -> Dict[str, Decimal]:
    usdc_prices = usdc_price_data["price"]
    market_key = MarketInfo("lp")
    actuator = Actuator()
    broker = actuator.broker
    market = UniLpMarketV2(market_key, UniV3Pool(gp.token0, gp.token1, gp.fee, gp.quote_token,
                                                 tick_spacing=bull_params.tick_spacing))
    broker.add_market(market)
    for token in (gp.quote_token, gp.base_token, USDC):
        broker.set_balance(token, 0)

    utils = RemixDaoUtils(market, market_key, bull_params, bull_params, True)
    strat = EthBtcDefenseStrategy(utils, params, gp, usdc_prices, daily, mode)
    actuator.strategy = strat
    market.data_path = f"../real-data/{gp.contract_address}"
    data = copy.deepcopy(processed_data)
    market.add_statistic_column(data)
    market.data = data

    prices, quote = market.get_price_from_data()
    eth_usd = usdc_prices.astype(float).reindex(prices.index, method="ffill").bfill()
    prices[USDC.name] = 1.0 / eth_usd    # USDC in ETH, so the actuator values the wallet in ETH
    actuator.set_price((prices, quote))
    actuator.run(False)

    account = actuator.account_status_df
    net_value = account["net_value"]
    benchmark = account["price"][gp.base_token.name.upper()]
    metrics = performance_metrics_for_dca(net_value, 0, benchmark=benchmark, total_fee=strat.total_fee)
    final = strat.final_total_net_value
    metrics["lp_net_value"] = strat.final_lp_net_value
    metrics["total_net_value"] = final
    metrics["total_fee"] = strat.total_fee
    metrics["fee_to_total_net_value"] = strat.total_fee / final
    metrics["total_base_swap_fee"], metrics["total_quote_swap_fee"] = ZERO, strat.total_quote_swap_fee
    metrics["total_swap_fee"] = strat.total_swap_fee
    metrics["action_count"] = Decimal(strat.rebuild_count)
    metrics["spread_mean"] = Decimal(int(sum(strat.spreads) / len(strat.spreads))) if strat.spreads else Decimal(-1)
    metrics["spread_median"] = Decimal(int(sorted(strat.spreads)[len(strat.spreads) // 2])) if strat.spreads else Decimal(-1)
    metrics["benchmark_max_draw_down"] = max_draw_down(benchmark.apply(float))
    metrics["total_fee_usd"] = strat.total_fee_usd
    metrics["total_net_value_usd"] = strat.total_net_value_usd
    metrics["lp_net_value_usd"] = strat.total_lp_value_usd
    metrics["total_invested_usd"] = strat.total_invested_usdc
    metrics["total_return_usd"] = Decimal(return_rate(float(strat.total_invested_usdc), float(strat.total_net_value_usd)))
    metrics["quote_return_usd"] = Decimal(return_rate(float(usdc_prices.iloc[0]), float(usdc_prices.iloc[-1])))
    metrics["rescale_count"] = Decimal(strat.rebuild_count)
    metrics["out_of_range_count"] = Decimal(strat.out_of_range_rebuilds)
    metrics["final_base_price"] = strat.final_price
    metrics["out_of_fund_date"] = Decimal(strat.out_of_fund_date.timestamp()) if strat.out_of_fund_date else None
    # spec sheet metrics: ETH count (x, start = 1 ETH), rewards valued at receipt vs at the end, BTC count, USD
    init = gp.init_quote
    p0 = account["price"][gp.base_token.name.upper()].iloc[0]
    usd_series = net_value.apply(float) * eth_usd.reindex(net_value.index, method="ffill")
    metrics["eth_ratio_end"] = final / init
    metrics["eth_ratio_receipt"] = (final - strat.fee_value_end + strat.reward_eth) / init
    metrics["reward_eth"] = strat.reward_eth
    metrics["btc_ratio"] = (final / strat.final_price) / (init / p0)
    metrics["usd_ratio"] = strat.total_net_value_usd / strat.total_invested_usdc
    metrics["max_dd_usd"] = max_draw_down(usd_series)
    metrics["swap_cost_eth"] = strat.swap_cost_eth
    metrics["lp_avg_share"] = strat.lp_share_sum / strat.lp_share_days if strat.lp_share_days else ZERO
    return metrics


def _run_one(bull, tp: TestParams, gp: GlobalParams, data, usdc_price_data, daily, mode) -> Tuple[str, Dict[str, Decimal]]:
    """Pool worker. Top level so it pickles under spawn."""
    return tp.report_name, run_test(bull, tp, gp, data, usdc_price_data, daily, mode)


EXTRA_COLUMNS = ["eth_ratio_receipt", "eth_ratio_end", "reward_eth", "btc_ratio", "usd_ratio", "max_dd_usd",
                 "swap_cost_eth", "lp_avg_share", "rescale_count", "out_of_range_count"]


def process_for_date(csd: datetime, dsd: date, ded: date, modes: List[str] | None = None):
    demeter.Formats.global_num_format = ".4g"
    eth = TokenInfo(name="eth", decimal=18)
    btc = TokenInfo(name="btc", decimal=8)
    base_token, quote_token, init_quote = btc, eth, Decimal(1)   # 1 ETH start, spec sheet 4
    token0, token1 = btc, eth
    contract_address, fee, chain_name = "0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0", 0.05, ChainType.ethereum.name  # wbtc/weth
    contract_usdc = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"                                                    # weth/usdc
    modes = modes or [MODE_SIGNAL]   # add MODE_PLAIN for the spec sheet's 通常LP comparison
    tick_spacing = int(fee * 200)   # 10

    gp = GlobalParams(token0=token0, token1=token1, fee=fee, init_quote=init_quote, quote_token=quote_token,
                      base_token=base_token, chain_name=chain_name, contract_address=contract_address,
                      swap_fee=False, init_quote_usdc=ZERO)
    bull = RemixDAOParams(tick_spread_upper=60, tick_spread_lower=60, tick_upper_boundary_offset=0,
                          tick_lower_boundary_offset=0, rescale_tick_upper_boundary_offset=0,
                          rescale_tick_lower_boundary_offset=0, init_tick_spread=120, tick_spacing=tick_spacing,
                          tick_gap_lower=1, tick_gap_upper=1)
    folder = f"result/ethbtc-wb25-wbtceth-{csd:%Y%m%d}-{ded:%Y%m%d}"
    Path(folder).mkdir(parents=True, exist_ok=True)

    def load(pool: UniV3Pool, address: str, start: date, end: date) -> UniLpMarketV2:
        m = UniLpMarketV2(MarketInfo("data"), pool)
        m.data_path = f"../real-data/{address}"
        time.sleep(random.uniform(1, 3))   # stagger parallel loads
        m.load_data(chain_name, address, start, end)
        return m

    print(f"preload data {dsd:%Y%m%d} ~ {ded:%Y%m%d}")
    market = load(UniV3Pool(token0, token1, fee, quote_token), contract_address, dsd, ded)
    usdc_market = load(UniV3Pool(USDC, eth, fee, USDC), contract_usdc, dsd, ded)
    daily = None
    if MODE_SIGNAL in modes:
        warm_start, warm_end = max(dsd - timedelta(days=EMA_WARMUP_DAYS), DATA_FLOOR), dsd - timedelta(days=1)
        print(f"signal warm-up {warm_start} ~ {warm_end}: {(warm_end - warm_start).days + 1} days")
        warm = load(UniV3Pool(token0, token1, fee, quote_token), contract_address, warm_start, warm_end)
        warm_usdc = load(UniV3Pool(USDC, eth, fee, USDC), contract_usdc, warm_start, warm_end)
        daily = signal_frame(pd.concat([warm.data.price, market.data.price]),
                             pd.concat([warm_usdc.data.price, usdc_market.data.price]))
        window = daily.loc[pd.Timestamp(dsd):]
        print(f"signal F over the window: mean {window['F'].mean():.3f}, days at 0: {(window['F'] == 0).sum()}, "
              f"days at 1: {(window['F'] == 1).sum()}, strong days: {int(window['strong'].sum())}/{len(window)}")
        daily.to_csv(f"{folder}/signal_frame.csv")

    jobs = []
    for mode in modes:
        tp = TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1,
                        report_name=f"{init_quote}{quote_token.name}_{mode}", cal_start_datetime=csd,
                        data_start_date=dsd, data_end_date=ded, folder=folder,
                        rescale_frequency=RescaleFrequency.daily)
        jobs.append((bull, tp, gp, market.data, usdc_market.data, daily, mode))
    with multiprocessing.Pool(min(len(jobs), 5)) as pool:
        result = pool.starmap(_run_one, jobs)
    export_stable_apr_results(f"{folder}/apr_results.csv", result)
    extra = pd.DataFrame({name: {k: float(m[k]) for k in EXTRA_COLUMNS} for name, m in result}).T
    extra.to_csv(f"{folder}/eth_summary.csv")
    print(extra.to_string())


def _self_check():
    # allocation: spec sheet 2.5 example, F = 50% strong -> LP 37.5 / ETH 12.5 / USDC 50
    shares, ratio = allocation(Decimal("0.5"), True)
    assert shares == {"lp": Decimal("0.375"), "eth": Decimal("0.125"), "btc": ZERO, "usdc": Decimal("0.5")}, shares
    assert ratio == RANGE_STRONG
    shares, ratio = allocation(Decimal("0.5"), False)
    assert shares["lp"] == shares["btc"] == Decimal("0.5") and shares["usdc"] == ZERO and ratio == RANGE_WEAK
    for f in (ZERO, Decimal("0.0625"), Decimal("1")):
        for strong in (True, False):
            assert sum(allocation(f, strong)[0].values()) == ONE
    # range: price x0.9 / x1.1 is -1054 / +953 ticks, x0.8 / x1.2 is -2231 / +1823 (spacing 10 rounds them)
    lo, hi = range_ticks(-8200, RANGE_STRONG, 10)
    assert (lo, hi) == (-8200 - 1050, -8200 + 950), (lo, hi)
    lo, hi = range_ticks(0, RANGE_WEAK, 10)
    assert (lo, hi) == (-2230, 1820), (lo, hi)
    # in-range value split: a +-10% range holds ~52% ETH, +-20% ~55% (the geometry, not a flat half)
    assert abs(lp_quote_share(0, *range_ticks(0, RANGE_STRONG, 10)) - Decimal("0.5244")) < Decimal("0.002")
    assert abs(lp_quote_share(0, *range_ticks(0, RANGE_WEAK, 10)) - Decimal("0.5478")) < Decimal("0.002")
    # swaps: value is conserved except for the 0.1% on the minimum converted volume
    cur, want, px = [Decimal(1), Decimal(0), Decimal(0)], [Decimal(0), Decimal(10), Decimal(40000)], [Decimal(30), ONE, Decimal("0.0005")]
    assert sum(w * p for w, p in zip(want, px)) == Decimal(30), "targets must sum to the equity"
    deltas, cost = swap_deltas(cur, want, px)
    after = sum((c + d) * p for c, d, p in zip(cur, deltas, px))
    assert cost == Decimal("0.03") and abs(after - (Decimal(30) - cost)) < Decimal("1e-9"), (after, cost)
    assert deltas[0] == Decimal(-1) and deltas[1] == Decimal("9.99"), deltas
    # virtual account: EMA exit needs the falling-EMA condition; a close under a flat / rising EMA is no exit
    acct = VirtualAccount(100)
    acct.step(2000, 1900)                                   # armed, fully deployed
    assert acct.armed and acct.deployed == 1.0
    acct.step(1950, 1960, 1900)                             # close < EMA but EMA above 20 days ago -> stay
    assert acct.deployed == 1.0, acct.deployed
    acct.step(1950, 1960, 2000)                             # close < EMA and EMA falling -> exit
    assert acct.deployed == 0.0 and not acct.armed and acct.low == 1950
    for c in (2100, 2100, 2100):                            # re-arm, then 3 confirm days >= low x 1.05
        acct.step(c, 1990, 2100)
    assert acct.armed and acct.stage == 1 and acct.deployed == 0.25, acct.__dict__
    acct.step(2200, 1990, 2100)                             # 2200 >= low x 1.0833 -> stage 2, one stage a day
    assert acct.stage == 2 and acct.deployed == 0.5
    # signal frame: G = ETH/USD x sqrt(BTC/ETH); rising R (BTC/ETH falling) -> strong, falling R -> weak
    idx = pd.date_range("2024-01-01", periods=420, freq="D")
    p_down = pd.Series([30.0 * (0.999 ** i) for i in range(420)], index=idx)
    e = pd.Series([2000.0] * 420, index=idx)
    fr = signal_frame(p_down, e)
    assert abs(fr["G"].iloc[0] - 2000 * 30 ** 0.5) < 1e-6 and fr["strong"].iloc[-1], fr.tail(2)
    fr = signal_frame(p_down.iloc[::-1].set_axis(idx), e)
    assert not fr["strong"].iloc[-1], fr.tail(2)
    # G falling steadily for a year: every account is out, so F ends at 0
    fr = signal_frame(pd.Series([30.0] * 420, index=idx), pd.Series([3000.0 * (0.995 ** i) for i in range(420)], index=idx))
    assert fr["F"].iloc[-1] == 0.0, fr["F"].tail(3).tolist()


if __name__ == "__main__":
    _self_check()

    date_ranges: List[tuple[datetime, date, date]] = [
        # (cal start, data start, data end)
        # spec sheet 5.1: start Jan 1 and run 365 days (2024 is a leap year, so it ends Dec 30)
        # (datetime(2022, 1, 1), date(2022, 1, 1), date(2022, 12, 31)),
        # (datetime(2023, 1, 1), date(2023, 1, 1), date(2023, 12, 31)),
        # (datetime(2024, 1, 1), date(2024, 1, 1), date(2024, 12, 30)),
        (datetime(2025, 1, 1), date(2025, 1, 1), date(2025, 12, 31)),
        # spec sheet 5.2: 4 years 2022-2025 in one run
        # (datetime(2022, 1, 1), date(2022, 1, 1), date(2025, 12, 31)),
    ]
    for dr in date_ranges:  # one after another: each range loads its own minute data, in parallel they would eat the RAM
        process_for_date(*dr)
