"""
ETH-cbBTC MGL 規格書 v2.2（自動再投入，2026-10-27）的回測入口。

從 gamma_ig_gap_bands_defense_btceth_v2_1.py 複製（QUAN-1212），只改第 5 節的獎勵處理：

* 取消標準／複利模式，改為單一運作＋「自動再投入」開關（預設開啟）。MODE_REINVEST / MODE_NO_REINVEST 各跑一次
* 再投入關閉 = v2.1 標準模式（數字一位不差）：淨獎勵全額留作可領取的 cbBTC 餘額
* 再投入開啟：每月 1 日 00:00 判定與 claim（與當天的重建）之後，cbBTC 獎勵餘額全額加入原資，依當時 F 與 ETH 強弱的
  「目標」配置（第 4 節表格）分到 LP / ETH / BTC / USDC（v2.1 複利模式用「當時」比例）。LP 部分加進現有區間；F = 0
  時全額為撤退標的（弱勢 BTC、強勢 USDC）。餘額 <= $5 的月份不再投入，累積到下月（v2.1 複利模式沒有門檻）
* 假設 1（規格書未寫，同 v3.2 沒有階梯時的規則）：目標 LP > 0 但沒有 LP 部位（偏離未達 12.5% 重建門檻，還沒建 LP）時，
  LP 部分也放撤退標的
* 假設 2（同 v2.1 複利模式）：LP 部分加進現有區間，不以當下池價重新置中（第 4 節「追加存入」是否含再投入未寫明）
* 1 日缺 Binance 收盤時當天整個跳過（同 v2.1），該月不再投入也不記錄，餘額留到下月
* 每月再投入判定寫在 <run folder>/reinvest_<report>.csv（略過的月份也記）

以下沿用 v2.1 的說明（v2.1 從 gamma_ig_gap_bands_defense_btceth_v2.py 複製，v2 檔依前版規格書「WB＋ETH強勢25%」）：

* 訊號只用 Binance 日K（第 2 節）：G = sqrt(ETHUSDT x BTCUSDT)，R = ETHBTC 交易對；池價只用於 LP 評價與手續費。
  EMA 以 2017-08-17 為初始值連續計算，虛擬帳戶 2017-08-18 起執行，收盤 >= EMA_n 為已武裝滿倉（第 3 節「啟動時」）
* F = 四個虛擬帳戶（虛擬 LP 價值 / 虛擬帳戶資產）的平均（第 3 節），虛擬 LP 是 ±20% 谷型、形狀規則同 ETH-USDC
  （低於 EMA100(G) x 0.95 為 25%、高於 EMA_n 為 70%、其餘 50%）；F_BY_VALUE = False 退回階段值
* 重建條件 3 是「目標 LP >= 99.9%」（v2 檔寫 >= 100%，階段值時等價，價值比例時不等價）
* 獎勵（第 5 節）：每天未收取手續費超過 $5 就 claim，重建與結算時一律 claim；扣成功報酬（預設 0，規格書數字為扣前）後，
  WETH 換成 cbBTC，計入獎勵餘額（cbBTC）。再投入方式見上方 v2.2 的說明
* 區間（第 4 節，v2.1 新增）：中心用執行當下的池價，中心與上下邊界各自取最近的 tick spacing 倍數
  （v2 檔是先取整中心再加取整後的寬度，邊界可能差一個 spacing）
* daily 檔以判定日 D 標記（第 2 節「日期」），另列執行時間

未建模：防操縱檢查（池價對 Chainlink，回測的池價即成交價）、gas 壅塞與執行手續費（規格書數字也未扣）。
池子預設 Base WETH/cbBTC 0.05%（2024-09-13 起有資料）；主網 WBTC/WETH 0.05% 是規格書校正手續費的池子，兩種 token 順序都支援。
mode=plain 是「一般LP 20%」對照組：均等型 ±10%、無訊號、出界即重建，獎勵同再投入關閉。
"""
import copy
import math
import multiprocessing
import os
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
MODE_REINVEST, MODE_NO_REINVEST, MODE_PLAIN = "reinvest", "noreinvest", "plain"
POOLS = {   # name -> (token0 is BTC, address, chain), both 0.05%
    "base": (False, "0x7AeA2E8A3843516afa07293a10Ac8E49906dabD1", ChainType.base.name),         # weth/cbbtc, 2024-09-13
    "mainnet": (True, "0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0", ChainType.ethereum.name),   # wbtc/weth, spec's fee calibration
}

# spec section 2: Binance spot UTC daily closes (date = the K-line's UTC day, close = its 24:00 close), from 2017-08-17
BINANCE_DIR = Path(__file__).parent
EMA_SEED_DAY = date(2017, 8, 17)

# spec section 3: four virtual accounts on G, each with its own EMA; F = mean of their LP shares
EMA_SPANS = (90, 100, 110, 120)
# QUAN-1216 L6 robustness runs (VALIDATION-2026-10-29-v3_2-v2_2.md, L6): L6_EMA_SHIFT=-10 / 10 shifts the four account spans by
# one grid step; VIRTUAL_EMA and STRENGTH_SPAN stay. L6_WIDTH=0.9 / 1.1 multiplies every width: the real LP ranges, the
# virtual band step and the lower stop / upper rebuild distance. Off = the spec; the folder gets "-l6ema-10" / "-l6w0.9".
L6_EMA_SHIFT = int(os.environ.get("L6_EMA_SHIFT", "0"))
L6_WIDTH = Decimal(os.environ.get("L6_WIDTH", "1"))
L6_TAG = f"{f'-l6ema{L6_EMA_SHIFT:+d}' if L6_EMA_SHIFT else ''}{f'-l6w{L6_WIDTH}' if L6_WIDTH != 1 else ''}"
EMA_SPANS = tuple(n + L6_EMA_SHIFT for n in EMA_SPANS)
EMA_SLOPE_DAYS = 20                                     # exit also needs EMA_n < EMA_n 20 days ago
LOWER_STOP, UPPER_REBUILD = 0.80, 1.20
REFILL_CONFIRM_DAYS = 3
REFILL_STAGES = ((1, 1.05), (2, 1.0833), (3, 1.1167), (4, 1.15))  # (stage, close / low), stage k -> k/4 deployed
# True = a virtual account's share is (virtual LP value / virtual account assets), drifting with G after a build (the spec);
# False = the stage value 0 / .25 / .5 / .75 / 1 (the v2 file and the CTO's implementation, spec section 8 open item)
F_BY_VALUE = True
# virtual LP (same as ETH-USDC): +-20% valley, 8 bands of 2.5% of the centre per side, weights from the centre outward
BAND_STEP = 0.025
BAND_WEIGHTS = (0.006, 0.023, 0.044, 0.065, 0.08, 0.09, 0.095, 0.097)
# share of the virtual LP above the centre (the G side): 25% below EMA100(G) x 0.95, 70% above the account's EMA, else 50%.
# Assumption, as in ethusdc v3: refills and the start build use the same rule (the spec states it for the rebuild).
VIRTUAL_SHARE_WEAK, WEAK_EMA_FACTOR, VIRTUAL_EMA = 0.25, 0.95, 100

# spec section 2 / 4: strength on R = ETH/BTC vs EMA100(R); strong keeps 25% of LP allocation as ETH
STRENGTH_SPAN = 100
ETH_KEEP = Decimal("0.25")
RANGE_STRONG, RANGE_WEAK = Decimal("0.10"), Decimal("0.20")   # half width: 合計 20% / 40%
if L6_WIDTH != 1:   # off: the spec constants untouched, bit for bit
    BAND_STEP *= float(L6_WIDTH)
    LOWER_STOP, UPPER_REBUILD = 1 - (1 - LOWER_STOP) * float(L6_WIDTH), 1 + (UPPER_REBUILD - 1) * float(L6_WIDTH)
    RANGE_STRONG, RANGE_WEAK = RANGE_STRONG * L6_WIDTH, RANGE_WEAK * L6_WIDTH

# spec section 4 rebuild conditions
FOLLOW_THRESHOLD = Decimal("0.125")   # any of LP / ETH / BTC / USDC this far from target -> rebuild
FOLLOW_FULL_F = Decimal("0.999")      # target LP >= 99.9% ...
LP_SHORT_TOL = Decimal("0.01")        # ... but LP short by more than this
USDC_DUST = Decimal("0.001")          # target USDC 0 but holding more than this
SWAP_COST = Decimal("0.001")          # on the minimum converted volume; slippage cap 0.5% is not a cost
LOG_TICK = math.log(1.0001)

# spec section 5: claim when the unclaimed fees exceed $5 (gas / congestion not modelled), always at a rebuild and at the end
CLAIM_MIN_USD = Decimal(5)
PERFORMANCE_FEE = Decimal(0)          # spec: 25% of each claim; its numbers are before it, so 0 here. Decimal("0.25") = after
REWARD_SWAP_COST = SWAP_COST          # the net WETH reward is swapped to cbBTC at the same cost as a rebalance swap
REINVEST_MIN_USD = Decimal(5)         # spec v2.2 section 5: a reward balance of $5 or less is not reinvested that month


def build_virtual_lp(value: float, centre: float, up_share: float) -> List[Tuple[float, float, float]]:
    """The +-20% valley as (price_low, price_high, liquidity) per band, holding `value` USD at price `centre`:
    up_share of it as the G asset in the 8 bands above (valued at the centre), the rest as USD in the 8 below."""
    total = sum(BAND_WEIGHTS)
    bands = []
    for i, w in enumerate(BAND_WEIGHTS):
        up_lo, up_hi = centre * (1 + BAND_STEP * i), centre * (1 + BAND_STEP * (i + 1))
        units = value * up_share * w / total / centre
        bands.append((up_lo, up_hi, units / (1 / math.sqrt(up_lo) - 1 / math.sqrt(up_hi))))
        dn_hi, dn_lo = centre * (1 - BAND_STEP * i), centre * (1 - BAND_STEP * (i + 1))
        usd = value * (1 - up_share) * w / total
        bands.append((dn_lo, dn_hi, usd / (math.sqrt(dn_hi) - math.sqrt(dn_lo))))
    return bands


def virtual_lp_value(bands: List[Tuple[float, float, float]], price: float) -> float:
    """USD value of a virtual LP at `price`; fees and swap costs are not modelled."""
    value = 0.0
    for lo, hi, liq in bands:
        if price <= lo:    # below the band: all G asset
            units, usd = liq * (1 / math.sqrt(lo) - 1 / math.sqrt(hi)), 0.0
        elif price >= hi:  # above the band: all USD
            units, usd = 0.0, liq * (math.sqrt(hi) - math.sqrt(lo))
        else:
            units, usd = liq * (1 / math.sqrt(price) - 1 / math.sqrt(hi)), liq * (math.sqrt(price) - math.sqrt(lo))
        value += price * units + usd
    return value


class VirtualAccount:
    """One spec section 3 virtual account, stepped once per daily close of G. Floats: it only produces F.
    It holds virtual cash and a virtual LP (`bands`); `assets` is their value at the last close."""

    def __init__(self, span: int):
        self.span = span
        self.armed = False          # True once close was above the EMA since the last exit
        self.deployed = 0.0         # share of assets in the virtual LP (F_BY_VALUE) or stage / 4
        self.assets = self.cash = 1.0
        self.bands: list = []
        self.centre: float | None = None
        self.low: float | None = None   # lowest close since the exit, drives the refill
        self.stage = 0
        self.confirm = 0
        self.started = False

    def exit(self, close: float, assets: float) -> None:
        self.cash, self.bands = assets, []
        self.centre, self.low, self.stage, self.confirm = None, close, 0, 0

    def build(self, close: float, ema: float, ema100: float, assets: float, lp_value: float) -> None:
        share = VIRTUAL_SHARE_WEAK if close < ema100 * WEAK_EMA_FACTOR else (0.7 if close > ema else 0.5)
        self.bands, self.cash, self.centre = build_virtual_lp(lp_value, close, share), assets - lp_value, close

    def step(self, close: float, ema: float, ema_prev: float = float("nan"), ema100: float | None = None) -> None:
        ema100 = ema if ema100 is None else ema100
        lp = virtual_lp_value(self.bands, close) if self.bands else 0.0   # yesterday's LP at today's close
        assets = self.cash + lp
        if not self.started:   # spec section 3 start: close >= EMA_n -> armed and fully in, else unarmed from the low
            self.started, self.armed = True, close >= ema
            if self.armed:
                self.stage, lp = 4, assets
                self.build(close, ema, ema100, assets, lp)
            else:
                self.low = close
        else:
            # 1 EMA exit: close under EMA and the EMA itself falling (NaN slope in the first days -> no exit)
            if self.armed and close < ema and ema < ema_prev:
                self.exit(close, assets)
                self.armed, lp = False, 0.0
            elif not self.armed and close > ema:                            # 2 re-arm, no buy
                self.armed = True
            if self.stage > 0 and close < self.centre * LOWER_STOP:         # 3 lower stop
                self.exit(close, assets)
                lp = 0.0
            elif self.stage > 0 and close > self.centre * UPPER_REBUILD:    # 4 upper rebuild, same size
                self.build(close, ema, ema100, assets, lp)
            if self.stage < 4:                                              # 5 staged refill on the rebound from low
                self.low = min(self.low, close)
                self.confirm = self.confirm + 1 if close >= self.low * REFILL_STAGES[0][1] else 0
                nxt = self.stage + 1   # at most one stage a day; a pullback keeps the stage, only an exit resets it
                advance = (self.confirm >= REFILL_CONFIRM_DAYS if nxt == 1
                           else close >= self.low * REFILL_STAGES[nxt - 1][1])
                if advance:
                    self.stage, lp = nxt, nxt / 4 * assets   # LP rebuilt at the close, size = stage x assets
                    self.build(close, ema, ema100, assets, lp)
        self.assets = assets
        self.deployed = lp / assets if F_BY_VALUE else self.stage / 4


def binance_signal_frame(ded: date) -> pd.DataFrame:
    """signal_engine on the Binance daily closes from the first row (spec: 2017-08-17) up to `ded`."""
    c = {}
    for sym in ("btcusdt", "ethusdt", "ethbtc"):
        f = BINANCE_DIR / f"binance_{sym}_1d.csv"
        c[sym] = pd.read_csv(f, parse_dates=["date"]).set_index("date")["close"].loc[:pd.Timestamp(ded)]
        if c[sym].index[0] != pd.Timestamp(EMA_SEED_DAY) or c[sym].index[-1] < pd.Timestamp(ded):
            raise ValueError(f"{f.name} covers {c[sym].index[0].date()}..{c[sym].index[-1].date()}, "
                             f"needs {EMA_SEED_DAY}..{ded}")
        if (c[sym].index[1:] - c[sym].index[:-1]).max() > timedelta(days=1):
            raise ValueError(f"{f.name} has a gap in its daily closes")
    d = pd.concat(c, axis=1).dropna()
    return signal_engine((d["btcusdt"] * d["ethusdt"]) ** 0.5, d["ethbtc"])


def signal_engine(g: pd.Series, r: pd.Series) -> pd.DataFrame:
    """G = sqrt(BTC/USD x ETH/USD), R = ETH/BTC price (BTC per ETH), both daily closes indexed by the judgement day D.
    Returns G, R, EMA100(R), strong flag, F and the per-account state (spec section 7 stage 1 reconciliation view).
    The first close only seeds the EMAs; the accounts start the next day."""
    r_ema = r.ewm(span=STRENGTH_SPAN, adjust=False).mean()
    emas = {n: g.ewm(span=n, adjust=False).mean() for n in (*EMA_SPANS, VIRTUAL_EMA)}   # an L6 shift may drop 100
    prevs = {n: emas[n].shift(EMA_SLOPE_DAYS) for n in EMA_SPANS}
    accounts = [VirtualAccount(n) for n in EMA_SPANS]
    fractions, states = [], []
    for i, (day, close) in enumerate(g.items()):
        row = {}
        for a in accounts:
            if i:
                a.step(float(close), float(emas[a.span][day]), float(prevs[a.span][day]),
                       float(emas[VIRTUAL_EMA][day]))
            row.update({f"ema{a.span}": float(emas[a.span][day]), f"armed{a.span}": int(a.armed),
                        f"stage{a.span}": a.stage, f"low{a.span}": a.low, f"confirm{a.span}": a.confirm,
                        f"centre{a.span}": a.centre, f"deployed{a.span}": a.deployed})
        states.append(row)
        fractions.append(sum(a.deployed for a in accounts) / len(accounts))
    frame = pd.DataFrame({"G": g, "R": r, "R_ema": r_ema, "strong": r > r_ema, "F": fractions})
    return frame.join(pd.DataFrame(states, index=g.index))


def allocation(f: Decimal, strong: bool) -> Tuple[Dict[str, Decimal], Decimal]:
    """Spec section 4: (value share of LP / ETH kept out of LP / BTC / USDC, LP half width)."""
    if strong:
        return {"lp": f * (ONE - ETH_KEEP), "eth": f * ETH_KEEP, "btc": ZERO, "usdc": ONE - f}, RANGE_STRONG
    return {"lp": f, "eth": ZERO, "btc": ONE - f, "usdc": ZERO}, RANGE_WEAK


def reinvest_allocation(reward_usd: Decimal, f: Decimal, strong: bool, has_lp: bool) -> Dict[str, Decimal] | None:
    """Spec v2.2 section 5 month-end reinvest: value shares of the reward balance going to LP / ETH / BTC / USDC, or None
    when the balance is REINVEST_MIN_USD or less (carried to the next month). The split is the section 4 target
    allocation, so F = 0 puts it all in the retreat asset (BTC weak, USDC strong). Assumption (the spec is silent, v3.2's
    rule for a missing ladder): with no LP position to add to, the LP part also goes to the retreat asset."""
    if reward_usd <= REINVEST_MIN_USD:
        return None
    shares = allocation(f, strong)[0]
    if not has_lp:
        shares["usdc" if strong else "btc"] += shares["lp"]
        shares["lp"] = ZERO
    return shares


def range_ticks(current_tick: int, ratio: Decimal, spacing: int, token0_quote: bool = False) -> Tuple[int, int, int]:
    """Spec v2.1 section 4: (lower, upper, centre) raw ticks for BTC price x (1 - ratio) ... x (1 + ratio) around the
    execution-time pool price; the centre and both edges are each rounded to the nearest tick spacing multiple.
    A higher raw tick is a higher BTC price when BTC is token0 (WBTC/WETH), a lower one when ETH is token0
    (Base WETH/cbBTC), so there the edges are taken from the other side."""
    snap = lambda t: round(t / spacing) * spacing
    up, down = math.log1p(float(ratio)) / LOG_TICK, -math.log1p(-float(ratio)) / LOG_TICK
    if token0_quote:
        up, down = down, up
    return snap(current_tick - down), snap(current_tick + up), snap(current_tick)


def lp_quote_share(current_tick: int, lower_tick: int, upper_tick: int, token0_quote: bool = False) -> Decimal:
    """Share of an in-range position's value held in the quote token (ETH). Raw units cancel:
    y = sqrt(p) - sqrt(pa) and x*p = p/sqrt(p) - p/sqrt(pb) are both in raw token1, so y / (y + xp) is the
    token1 share: ETH for WBTC/WETH, BTC for WETH/cbBTC."""
    sc, sa, sb = (1.0001 ** (t / 2) for t in (current_tick, lower_tick, upper_tick))
    y, xp = sc - sa, sc * sc * (1 / sc - 1 / sb)
    token1_share = Decimal(str(round(y / (y + xp), 12)))
    return ONE - token1_share if token0_quote else token1_share


def swap_deltas(cur: List[Decimal], want: List[Decimal], prices: List[Decimal],
                cost: Decimal = SWAP_COST) -> Tuple[List[Decimal], Decimal]:
    """Net token changes moving `cur` to `want` (prices in ETH), and the cost in ETH. The cost is `cost` x the
    minimum converted volume; buyers receive (1 - cost) of what they asked for, like a fee on the trade."""
    sold = -sum(((w - c) * p for c, w, p in zip(cur, want, prices) if w < c), ZERO)
    return [(w - c) * (ONE - cost) if w > c else w - c for c, w in zip(cur, want)], sold * cost


class EthBtcMglStrategy(BaseRemixDaoStrategy):
    """Base = BTC, quote = ETH, plus USDC as a third broker asset priced in ETH (see run_test).
    The BTC balance includes `reward_btc`, which is outside the principal (原資): the claimable reward balance, which
    with auto reinvest on joins the principal at the next month-end."""

    def __init__(self, _utils: RemixDaoUtils, _params: TestParams, _gp: GlobalParams,
                 usdc_prices: pd.Series, daily: pd.DataFrame | None, mode: str = MODE_REINVEST):
        super().__init__(_utils, _params, _gp)
        self.token0_quote = _utils.lp_market.pool_info.is_token0_quote   # True for Base WETH/cbBTC
        if mode != MODE_PLAIN and daily is None:
            raise ValueError(f"mode={mode} needs the signal frame")
        self.daily, self.mode, self.usdc_prices = daily, mode, usdc_prices
        self.positions: list = []                 # at most one (lower_tick, upper_tick, ...) position
        self.starting_tick: int | None = None
        self.out_of_fund_date: datetime | None = None
        self.reward_btc = ZERO                    # net rewards held as cbBTC outside the principal
        self.reward_eth = ZERO                    # net rewards valued in ETH on the day they were claimed
        self.reward_eth_open = ZERO               # the same, for the rewards still in reward_btc (not reinvested)
        self.gross_reward_eth = self.perf_fee_eth = self.reward_swap_cost_eth = ZERO
        self.reinvested_eth = ZERO                # auto reinvest: rewards added to the principal, in ETH at the time
        self.claim_count = self.reinvest_count = 0
        self.reinvest_log: List[dict] = []        # one row per month-end reinvest check, skipped months included
        self.swap_cost_eth = ZERO
        self.rebuild_count = self.out_of_range_rebuilds = 0
        self.lp_share_sum, self.lp_share_days = ZERO, 0
        self.daily_log: List[dict] = []
        self.rebuild_log: List[dict] = []
        self.spreads: List[int] = []
        # filled by calculate_final_result
        self.total_fee = self.total_swap_fee = ZERO
        self.total_base_swap_fee = self.total_quote_swap_fee = ZERO
        self.final_total_net_value = self.final_lp_net_value = self.final_principal = ZERO
        self.total_invested_usdc = self.total_fee_usd = ZERO
        self.total_net_value_usd = self.total_lp_value_usd = ZERO
        self.init_quote_usd_price = self.final_quote_usd_price = ZERO
        self.final_price = ZERO

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
        """Free principal (btc, eth, usdc): the reward cbBTC stays in the wallet but out of the principal."""
        return (self.broker.get_token_balance(self.gp.base_token) - self.reward_btc,
                self.broker.get_token_balance(self.gp.quote_token),
                self.broker.get_token_balance(USDC))

    def _lp_value(self) -> Decimal:
        """Liquidity only: unclaimed fees are rewards, not principal."""
        return self._lp_market().get_market_balance().liquidity_value if self.positions else ZERO

    def _book(self, p: Decimal, u: Decimal) -> Tuple[Decimal, Dict[str, Decimal]]:
        """(principal in ETH, its LP / ETH / BTC / USDC shares)"""
        btc, eth, usdc = self._wallet()
        lp_value = self._lp_value()
        value = lp_value + btc * p + eth + usdc * u
        if value <= ZERO:
            return value, {}
        return value, {"lp": lp_value / value, "eth": eth / value, "btc": btc * p / value, "usdc": usdc * u / value}

    def target(self, timestamp: datetime) -> Tuple[Dict[str, Decimal], Decimal, Decimal, bool]:
        """(shares, half width, F, strong) judged on the last completed UTC day D, executed at D+1 00:00."""
        if self.mode == MODE_PLAIN:
            return {"lp": ONE, "eth": ZERO, "btc": ZERO, "usdc": ZERO}, RANGE_STRONG, ONE, False
        row = self.daily.loc[pd.Timestamp(timestamp - timedelta(days=1)).normalize()]
        f, strong = Decimal(str(row["F"])), bool(row["strong"])
        shares, ratio = allocation(f, strong)
        return shares, ratio, f, strong

    # ---- actions -----------------------------------------------------------------------------------------
    def _apply(self, deltas: List[Decimal]) -> None:
        for token, delta in zip((self.gp.base_token, self.gp.quote_token, USDC), deltas):
            if delta > ZERO:
                self.broker.add_to_balance(token, delta)
            elif delta < ZERO:
                self.broker.subtract_from_balance(token, -delta)

    def claim(self, p: Decimal, u: Decimal, force: bool = False) -> bool:
        """Spec section 5 steps 1-3: claim when the unclaimed fees exceed CLAIM_MIN_USD (or `force`), keep
        PERFORMANCE_FEE of it back, swap the net WETH to cbBTC and book it as reward_btc."""
        if not self.positions:
            return False
        lp_market = self._lp_market()
        balance = lp_market.get_market_balance()
        pending_eth = balance.base_uncollected * p + balance.quote_uncollected
        if pending_eth <= ZERO or (not force and pending_eth / u < CLAIM_MIN_USD):   # 1 / u = ETH price in USD
            return False
        base_fee = quote_fee = ZERO
        for pos in list(self.positions):
            b, q = lp_market.collect_fee(pos, collect_to_user=True)
            base_fee, quote_fee = base_fee + b, quote_fee + q
            if pos not in lp_market.positions:   # collect_fee drops an empty position
                self.positions.remove(pos)
        gross = base_fee * p + quote_fee
        cut_base, cut_quote = base_fee * PERFORMANCE_FEE, quote_fee * PERFORMANCE_FEE   # paid to the contract
        net_base, net_quote = base_fee - cut_base, quote_fee - cut_quote
        deltas, cost = swap_deltas([ZERO, net_quote], [net_quote / p, ZERO], [p, ONE], REWARD_SWAP_COST)
        self._apply([deltas[0] - cut_base, deltas[1] - cut_quote, ZERO])
        self.reward_btc += net_base + deltas[0]
        self.gross_reward_eth += gross
        self.perf_fee_eth += gross * PERFORMANCE_FEE
        self.reward_swap_cost_eth += cost
        self.reward_eth += (net_base + deltas[0]) * p
        self.reward_eth_open += (net_base + deltas[0]) * p
        self.claim_count += 1
        return True

    def rebuild(self, row_data: Snapshot, why: str) -> None:
        lp_market = self._lp_market()
        p, u = self._prices(row_data)
        current_tick = lp_market.price_to_raw_tick(p)
        self.claim(p, u, force=True)
        old = (self.positions[0][0], self.positions[0][1]) if self.positions else None
        for pos in self.positions:
            lp_market.remove_liquidity(pos, collect=True)
        self.positions = []

        shares, ratio, f, strong = self.target(row_data.timestamp)
        btc, eth, usdc = self._wallet()
        value = btc * p + eth + usdc * u
        lp_value, lp_btc, lp_eth, tick_lo, tick_hi, centre = shares["lp"] * value, ZERO, ZERO, None, None, None
        if lp_value > ZERO:
            tick_lo, tick_hi, centre = range_ticks(current_tick, ratio, self.utils.params.tick_spacing, self.token0_quote)
            w = lp_quote_share(current_tick, tick_lo, tick_hi, self.token0_quote)   # ETH / BTC halves that fill the range exactly
            lp_eth, lp_btc = lp_value * w, lp_value * (ONE - w) / p
        want = [shares["btc"] * value / p + lp_btc, shares["eth"] * value + lp_eth, shares["usdc"] * value / u]
        deltas, cost = swap_deltas([btc, eth, usdc], want, [p, ONE, u])
        self._apply(deltas)
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
        self.rebuild_log.append({"time": row_data.timestamp, "judge_date": (row_data.timestamp - timedelta(days=1)).date(),
                                 "why": why, "F": float(f), "strong": strong, "btc_eth": float(p),
                                 "equity_eth": float(value), "old_range": old, "new_range": (tick_lo, tick_hi),
                                 "centre_tick": centre, "swap_cost_eth": float(cost)})
        print(f"[{self.mode}] {row_data.timestamp:%Y-%m-%d %H:%M} rebuild ({why}) F {float(f):.4f} "
              f"{'strong' if strong else 'weak'} equity {float(value):.4f} ETH range +-{float(ratio):.0%}")

    def reinvest(self, row_data: Snapshot, f: Decimal, strong: bool) -> None:
        """Spec v2.2 section 5 auto reinvest: on the 1st after the judgement, the claim and any rebuild, add the whole reward
        balance (cbBTC) to the principal at the target LP / ETH / BTC / USDC shares for F and strength judged on D
        (reinvest_allocation). The LP part is added to the existing range (no recentring). A balance of REINVEST_MIN_USD
        or less stays in the reward balance until the next month."""
        p, u = self._prices(row_data)
        pending, value = self.reward_btc, self.reward_btc * p
        split = reinvest_allocation(value / u, f, strong, bool(self.positions))   # 1 / u = ETH price in USD
        self.reinvest_log.append({"exec": row_data.timestamp, "judge_date": (row_data.timestamp - timedelta(days=1)).date(),
                                  "F": float(f), "strong": strong, "reward_btc": float(pending),
                                  "reward_eth": float(value), "reward_usd": float(value / u),
                                  "reinvested": split is not None,
                                  **{f"to_{k}": float(v) for k, v in (split or {}).items()}})
        if split is None:
            return
        self.reward_btc = self.reward_eth_open = ZERO   # from here on it is principal
        lp_market = self._lp_market()
        tick = lp_market.price_to_raw_tick(p)
        lp_part, lp_btc, lp_eth = split["lp"] * value, ZERO, ZERO   # LP part > 0 only with a position (split)
        if lp_part > ZERO:
            w = lp_quote_share(tick, self.positions[0][0], self.positions[0][1], self.token0_quote)
            lp_eth, lp_btc = lp_part * w, lp_part * (ONE - w) / p
        want = [(split["btc"] * value) / p + lp_btc, split["eth"] * value + lp_eth, split["usdc"] * value / u]
        deltas, cost = swap_deltas([pending, ZERO, ZERO], want, [p, ONE, u])
        self._apply(deltas)
        self.swap_cost_eth += cost
        self.total_quote_swap_fee += cost
        if lp_part > ZERO:
            lp_eth *= ONE - SWAP_COST   # the ETH leg arrived net of the swap cost
            position, _, _, _ = lp_market.add_liquidity_by_tick(self.positions[0][0], self.positions[0][1],
                                                                lp_btc, lp_eth, tick=tick)
            if position not in self.positions:
                self.positions.append(position)
        self.reinvested_eth += value
        self.reinvest_count += 1
        print(f"[{self.mode}] {row_data.timestamp:%Y-%m-%d %H:%M} reinvest {float(pending):.6f} BTC "
              f"({float(value):.4f} ETH) at LP {float(split['lp']):.3f} (F {float(f):.4f} {'strong' if strong else 'weak'})")

    def first_lp(self, row_data: Snapshot) -> None:
        if self._lp_market().positions:
            raise RuntimeError("shouldn't have any position")
        self.init_quote_usd_price = self.get_quote_usdc_price(row_data)
        self.broker.add_to_balance(self.gp.quote_token, self.gp.init_quote)
        self.total_invested_usdc = self.gp.init_quote * self.init_quote_usd_price
        self.starting_tick = self._lp_market().price_to_raw_tick(self._prices(row_data)[0])
        self.rebuild(row_data, "start")

    def daily_work(self, row_data: Snapshot) -> None:
        """Spec section 4 / 5, once a day at 00:00 UTC: claim above $5, rebuild everything to the target when the book
        drifted or the LP ran out of range, then (auto reinvest on, on the 1st) reinvest the reward balance."""
        if self.starting_tick is None or self.out_of_fund_date is not None:
            return
        try:
            shares, _, f, strong = self.target(row_data.timestamp)
        except KeyError:  # missing close -> do nothing that day
            print(f"[{self.mode}] {row_data.timestamp:%Y-%m-%d} no daily close, skip")
            return
        p, u = self._prices(row_data)
        claimed = self.claim(p, u)
        value, cur = self._book(p, u)
        if value <= ZERO:
            return
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
        elif shares["lp"] >= FOLLOW_FULL_F and cur["lp"] < ONE - LP_SHORT_TOL:
            why = "target LP >= 99.9%"
        elif shares["usdc"] == ZERO and cur["usdc"] > USDC_DUST:
            why = "target USDC 0"
        self.daily_log.append({"date": (row_data.timestamp - timedelta(days=1)).date(), "exec": row_data.timestamp,
                               "btc_eth": float(p), "F": float(f), "strong": strong, "principal_eth": float(value),
                               "reward_btc": float(self.reward_btc), "claimed": claimed,
                               **{f"cur_{k}": float(v) for k, v in cur.items()}, "rebuild": why or ""})
        if why:
            if out_of_range:
                self.out_of_range_rebuilds += 1
            self.rebuild(row_data, why)
        if self.mode == MODE_REINVEST and row_data.timestamp.day == 1:
            self.reinvest(row_data, f, strong)

    def calculate_final_result(self, row_data: Snapshot) -> None:
        p, u = self._prices(row_data)
        self.claim(p, u, force=True)   # spec: a withdrawal request always claims
        lp_value = self._lp_value()
        self.final_principal = self._book(p, u)[0]
        assets = (self.broker.get_token_balance(self.gp.base_token) * p + self.broker.get_token_balance(self.gp.quote_token)
                  + self.broker.get_token_balance(USDC) * u)
        self.final_price = p
        self.final_lp_net_value = lp_value
        self.final_total_net_value = lp_value + assets
        self.total_fee = self.gross_reward_eth
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
        if self.mode == MODE_REINVEST:
            pd.DataFrame(self.reinvest_log).to_csv(f"{self.params.folder}/reinvest_{name}.csv", index=False)


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
    strat = EthBtcMglStrategy(utils, params, gp, usdc_prices, daily, mode)
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
    # spec section 6 metrics (start = 1 ETH, x): principal + rewards. Reinvest off: rewards valued on the claim day (the
    # spec's "原資＋已領取獎勵") and the cbBTC reward balance at the end price. Reinvest on: everything is principal except
    # the rewards since the last month-end reinvest, so the two only differ by those.
    init = gp.init_quote
    p0 = account["price"][gp.base_token.name.upper()].iloc[0]
    usd_series = net_value.apply(float) * eth_usd.reindex(net_value.index, method="ffill")
    reward_end = strat.reward_btc * strat.final_price
    metrics["principal_eth"] = strat.final_principal / init
    metrics["reward_eth_receipt"] = strat.reward_eth_open / init
    metrics["reward_eth_end"] = reward_end / init
    metrics["eth_ratio_receipt"] = (strat.final_principal + strat.reward_eth_open) / init
    metrics["eth_ratio_end"] = final / init
    metrics["gross_reward_eth"] = strat.gross_reward_eth
    metrics["perf_fee_eth"] = strat.perf_fee_eth
    metrics["reinvested_eth"] = strat.reinvested_eth
    metrics["claim_count"] = Decimal(strat.claim_count)
    metrics["reinvest_count"] = Decimal(strat.reinvest_count)
    metrics["max_dd_eth"] = max_draw_down(net_value.apply(float))
    metrics["btc_ratio"] = (final / strat.final_price) / (init / p0)
    metrics["usd_ratio"] = strat.total_net_value_usd / strat.total_invested_usdc
    metrics["max_dd_usd"] = max_draw_down(usd_series)
    metrics["swap_cost_eth"] = strat.swap_cost_eth
    metrics["reward_swap_cost_eth"] = strat.reward_swap_cost_eth
    metrics["lp_avg_share"] = strat.lp_share_sum / strat.lp_share_days if strat.lp_share_days else ZERO
    return metrics


def _run_one(bull, tp: TestParams, gp: GlobalParams, data, usdc_price_data, daily, mode) -> Tuple[str, Dict[str, Decimal]]:
    """Pool worker. Top level so it pickles under spawn."""
    return tp.report_name, run_test(bull, tp, gp, data, usdc_price_data, daily, mode)


EXTRA_COLUMNS = ["eth_ratio_receipt", "eth_ratio_end", "principal_eth", "reward_eth_receipt", "reward_eth_end",
                 "reinvested_eth", "gross_reward_eth", "perf_fee_eth", "max_dd_eth", "btc_ratio", "usd_ratio",
                 "max_dd_usd", "swap_cost_eth", "reward_swap_cost_eth", "lp_avg_share", "claim_count",
                 "reinvest_count", "rescale_count", "out_of_range_count"]


def process_for_date(csd: datetime, dsd: date, ded: date, pool_name: str = "base", modes: List[str] | None = None):
    demeter.Formats.global_num_format = ".4g"
    eth = TokenInfo(name="eth", decimal=18)
    btc = TokenInfo(name="btc", decimal=8)
    base_token, quote_token, init_quote = btc, eth, Decimal(1)   # 1 ETH start, spec section 6
    btc_token0, contract_address, chain_name = POOLS[pool_name]
    token0, token1 = (btc, eth) if btc_token0 else (eth, btc)
    fee = 0.05
    contract_usdc = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"                                                    # weth/usdc
    modes = modes or [MODE_REINVEST, MODE_NO_REINVEST]   # add MODE_PLAIN for the spec's 一般LP 20% comparison
    tick_spacing = int(fee * 200)   # 10

    gp = GlobalParams(token0=token0, token1=token1, fee=fee, init_quote=init_quote, quote_token=quote_token,
                      base_token=base_token, chain_name=chain_name, contract_address=contract_address,
                      swap_fee=False, init_quote_usdc=ZERO)
    bull = RemixDAOParams(tick_spread_upper=60, tick_spread_lower=60, tick_upper_boundary_offset=0,
                          tick_lower_boundary_offset=0, rescale_tick_upper_boundary_offset=0,
                          rescale_tick_lower_boundary_offset=0, init_tick_spread=120, tick_spacing=tick_spacing,
                          tick_gap_lower=1, tick_gap_upper=1)
    fee_tag = "" if PERFORMANCE_FEE == ZERO else f"-perf{float(PERFORMANCE_FEE) * 100:g}"
    folder = f"result/{pool_name}-ethbtc-mgl-v2_2{fee_tag}{L6_TAG}-{csd:%Y%m%d}-{ded:%Y%m%d}"
    Path(folder).mkdir(parents=True, exist_ok=True)

    def load(pool: UniV3Pool, address: str, start: date, end: date, chain_name_str: str | None = None) -> UniLpMarketV2:
        m = UniLpMarketV2(MarketInfo("data"), pool)
        m.data_path = f"../real-data/{address}"
        time.sleep(random.uniform(1, 3))   # stagger parallel loads
        m.load_data(chain_name_str or chain_name, address, start, end)
        return m

    print(f"preload data {dsd:%Y%m%d} ~ {ded:%Y%m%d}")
    market = load(UniV3Pool(token0, token1, fee, quote_token), contract_address, dsd, ded)
    usdc_market = load(UniV3Pool(USDC, eth, fee, USDC), contract_usdc, dsd, ded, ChainType.ethereum.name)
    daily = None
    if any(m != MODE_PLAIN for m in modes):
        daily = binance_signal_frame(ded)
        window = daily.loc[pd.Timestamp(dsd):]
        print(f"signal F over the window: mean {window['F'].mean():.3f}, days at 0: {(window['F'] == 0).sum()}, "
              f"days >= 0.999: {(window['F'] >= 0.999).sum()}, strong days: {int(window['strong'].sum())}/{len(window)}")
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
    print(folder)
    print(extra.to_string())


def _self_check():
    # allocation: spec section 4, F = 50% strong -> LP 37.5 / ETH 12.5 / USDC 50
    shares, ratio = allocation(Decimal("0.5"), True)
    assert shares == {"lp": Decimal("0.375"), "eth": Decimal("0.125"), "btc": ZERO, "usdc": Decimal("0.5")}, shares
    assert ratio == RANGE_STRONG
    shares, ratio = allocation(Decimal("0.5"), False)
    assert shares["lp"] == shares["btc"] == Decimal("0.5") and shares["usdc"] == ZERO and ratio == RANGE_WEAK
    for f in (ZERO, Decimal("0.0625"), Decimal("0.475"), Decimal("1")):
        for strong in (True, False):
            assert sum(allocation(f, strong)[0].values()) == ONE
    # v2.2 reinvest: split by the target allocation (section 4 table), F = 0 all to the retreat asset, <= $5 carried
    half, tenth = Decimal("0.5"), Decimal("0.1")
    assert reinvest_allocation(Decimal(100), half, True, True) == {
        "lp": Decimal("0.375"), "eth": Decimal("0.125"), "btc": ZERO, "usdc": Decimal("0.5")}
    assert reinvest_allocation(Decimal(100), half, False, True) == {"lp": half, "eth": ZERO, "btc": half, "usdc": ZERO}
    assert reinvest_allocation(Decimal(100), ZERO, False, False) == {"lp": ZERO, "eth": ZERO, "btc": ONE, "usdc": ZERO}
    assert reinvest_allocation(Decimal(100), ZERO, True, False) == {"lp": ZERO, "eth": ZERO, "btc": ZERO, "usdc": ONE}
    assert reinvest_allocation(Decimal(5), half, True, True) is None                # $5 or less: carried to next month
    assert reinvest_allocation(Decimal("5.01"), half, True, True) is not None
    # target LP > 0 but no position yet (drift stayed under the 12.5% rebuild trigger): the LP part goes to the retreat asset
    assert reinvest_allocation(Decimal(100), tenth, False, False) == {"lp": ZERO, "eth": ZERO, "btc": ONE, "usdc": ZERO}
    assert reinvest_allocation(Decimal(100), tenth, True, False) == {
        "lp": ZERO, "eth": Decimal("0.025"), "btc": ZERO, "usdc": Decimal("0.975")}
    # range: price x0.9 / x1.1 is -1054 / +953 ticks, x0.8 / x1.2 is -2231 / +1823; v2.1 rounds each edge of the
    # execution-time tick, so at tick 1234 the +-10% edges are 180 / 2190 (v2's rounded centre + width gave 180 / 2180)
    assert range_ticks(-8200, RANGE_STRONG, 10) == (-9250, -7250, -8200)
    assert range_ticks(0, RANGE_WEAK, 10) == (-2230, 1820, 0)
    assert range_ticks(1234, RANGE_STRONG, 10) == (180, 2190, 1230)
    # in-range value split: a +-10% range holds ~52% ETH, +-20% ~55% (the geometry, not a flat half)
    assert abs(lp_quote_share(0, *range_ticks(0, RANGE_STRONG, 10)[:2]) - Decimal("0.5244")) < Decimal("0.002")
    assert abs(lp_quote_share(0, *range_ticks(0, RANGE_WEAK, 10)[:2]) - Decimal("0.5478")) < Decimal("0.002")
    # mirrored order (Base WETH/cbBTC, BTC price = 1 / raw price): same BTC-price range, same ETH share
    for ratio, (lo_ex, hi_ex) in ((RANGE_STRONG, (-950, 1050)), (RANGE_WEAK, (-1820, 2230))):
        lo, hi, _ = range_ticks(0, ratio, 10, True)
        assert (lo, hi) == (lo_ex, hi_ex), (lo, hi)
        assert abs(1.0001 ** -hi - (1 - float(ratio))) < 1e-3 and abs(1.0001 ** -lo - (1 + float(ratio))) < 1e-3
        assert abs(lp_quote_share(0, *range_ticks(0, ratio, 10)[:2]) - lp_quote_share(0, lo, hi, True)) < Decimal("1e-9")
    lo, hi, c = range_ticks(-1234, RANGE_STRONG, 10, True)   # the mirror of tick 1234 above
    assert (lo, hi, c) == (-2190, -180, -1230), (lo, hi, c)
    # swaps: value is conserved except for the 0.1% on the minimum converted volume
    cur, want, px = [Decimal(1), Decimal(0), Decimal(0)], [Decimal(0), Decimal(10), Decimal(40000)], [Decimal(30), ONE, Decimal("0.0005")]
    assert sum(w * p for w, p in zip(want, px)) == Decimal(30), "targets must sum to the equity"
    deltas, cost = swap_deltas(cur, want, px)
    after = sum((c + d) * p for c, d, p in zip(cur, deltas, px))
    assert cost == Decimal("0.03") and abs(after - (Decimal(30) - cost)) < Decimal("1e-9"), (after, cost)
    assert deltas[0] == Decimal(-1) and deltas[1] == Decimal("9.99"), deltas
    # virtual LP: holds its value at the centre; above the top it is all USD, below the bottom all G asset
    bands = build_virtual_lp(100.0, 1000.0, 0.7)
    assert abs(virtual_lp_value(bands, 1000.0) - 100.0) < 1e-9
    assert abs(virtual_lp_value(bands, 1300.0) - virtual_lp_value(bands, 1250.0)) < 1e-9   # all USD above +20%
    assert virtual_lp_value(bands, 900.0) < 100.0 < virtual_lp_value(bands, 1100.0)
    # virtual account: EMA exit needs the falling-EMA condition; a close under a flat / rising EMA is no exit
    acct = VirtualAccount(100)
    acct.step(2000, 1900)                                   # start: close >= EMA -> armed, fully deployed
    assert acct.armed and acct.deployed == 1.0
    acct.step(1950, 1960, 1900)                             # close < EMA but EMA above 20 days ago -> stay
    assert abs(acct.deployed - 1.0) < 1e-12, acct.deployed  # all in the LP: value share stays 1
    acct.step(1950, 1960, 2000)                             # close < EMA and EMA falling -> exit
    assert acct.deployed == 0.0 and not acct.armed and acct.low == 1950
    for c in (2100, 2100, 2100):                            # re-arm, then 3 confirm days >= low x 1.05
        acct.step(c, 1990, 2100)
    assert acct.armed and acct.stage == 1 and abs(acct.deployed - 0.25) < 1e-12, acct.__dict__
    acct.step(2200, 1990, 2100)                             # 2200 >= low x 1.0833 -> stage 2, one stage a day
    assert acct.stage == 2 and abs(acct.deployed - 0.5) < 1e-12
    acct.step(2150, 1990, 2100)                             # no new stage: the share drifts with the LP value
    assert acct.stage == 2 and 0.49 < acct.deployed < 0.5, acct.deployed
    start = VirtualAccount(100)
    start.step(1900, 1900)                                  # spec start: close == EMA counts as armed
    assert start.armed and start.stage == 4
    # signal engine: rising R -> strong, falling R -> weak; the seed day only seeds (F = 0), the accounts start the next day
    idx = pd.date_range("2024-01-01", periods=420, freq="D")
    r_up = pd.Series([0.03 * (1.001 ** i) for i in range(420)], index=idx)
    g_flat = pd.Series([15000.0] * 420, index=idx)
    fr = signal_engine(g_flat, r_up)
    assert fr["strong"].iloc[-1] and fr["F"].iloc[0] == 0.0 and fr["F"].iloc[1] == 1.0, fr.head(3)
    assert not signal_engine(g_flat, r_up.iloc[::-1].set_axis(idx))["strong"].iloc[-1]
    # G falling steadily for a year: every account is out, so F ends at 0
    fr = signal_engine(pd.Series([15000.0 * (0.995 ** i) for i in range(420)], index=idx), r_up)
    assert fr["F"].iloc[-1] == 0.0, fr["F"].tail(3).tolist()


if __name__ == "__main__":
    _self_check()

    date_ranges: List[tuple[datetime, date, date, str]] = [
        # (cal start, data start, data end, pool). The "1/1 join" is priced at the 1/1 daily close (= 1/2 00:00 UTC), so
        # start on 1/2 like btceth v1. Base WETH/cbBTC has minute data from 2024-09-13, mainnet WBTC/WETH from 2021-05-13;
        # the signal always runs from 2017-08-17. Spec section 6 periods:
        (datetime(2025, 1, 2), date(2025, 1, 2), date(2025, 12, 31), "base"),
        (datetime(2026, 1, 2), date(2026, 1, 2), date(2026, 8, 31), "base"),
        (datetime(2022, 1, 2), date(2022, 1, 2), date(2022, 12, 31), "mainnet"),
        (datetime(2023, 1, 2), date(2023, 1, 2), date(2023, 12, 31), "mainnet"),
        (datetime(2024, 1, 2), date(2024, 1, 2), date(2024, 12, 31), "mainnet"),
        (datetime(2025, 1, 2), date(2025, 1, 2), date(2025, 12, 31), "mainnet"),
        (datetime(2026, 1, 2), date(2026, 1, 2), date(2026, 8, 31), "mainnet"),
        (datetime(2022, 1, 2), date(2022, 1, 2), date(2025, 12, 31), "mainnet"),   # continuous 2022-2025
        (datetime(2021, 5, 14), date(2021, 5, 14), date(2026, 8, 31), "mainnet"),  # spec: v3 launch 2021/5/5 ~ 2026/8; pool data from 5/13
    ]
    for dr in date_ranges:  # one after another: each range loads its own minute data, in parallel they would eat the RAM
        process_for_date(*dr)
