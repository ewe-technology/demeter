"""
谷型LP防禦邏輯 規格書 v6（ETH 70%・單一階梯方式）的回測入口。

從 remix_dao_gamma_ig_gap_bands.py 複製，參數固定為規格書的谷型 LP 對照組：
8+8 段 inverted_gaussian、±20%（MIRROR_PRICE）、中心無 gap、日線判定。
2025 年基準：總報酬 -6.2%、本金 $60.3k、手續費 $33.5k（PDF 谷型 LP -6.4%）。
已加：eth_share（固定 / EMA100 切換 0.7-0.5）與 deploy=signal（規格書 2.2 四帳戶訊號引擎算 F、
2.3 每日追隨 F 重建，其餘留 USDC）。2025 1-4 月短測：−8.6%，同期 ETH −46%。詳見 ETH_SHARE_TODO.md。
"""
import copy

from dataclasses import dataclass
import math
from collections import deque
import multiprocessing
import random
import time
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import List, Tuple, Dict

import numpy as np
import pandas as pd
from pandas import Series

import demeter
from demeter import (
    Strategy,
    Snapshot,
    Actuator,
    TokenInfo,
    MarketInfo,
    ChainType,
    AtTimeTrigger,
    PeriodTrigger
)
from demeter.result.metrics.calculator import max_draw_down
from demeter.result import performance_metrics, return_rate
from demeter.uniswap import UniLpMarket, UniV3Pool, V3CoreLib, base_unit_price_to_sqrt_price_x96, \
    PositionInfo
from datetime import date, timedelta, datetime

from remix_dao_utils import RemixDaoUtils, RemixDAOParams, WeeklyTrigger, performance_metrics_for_dca, getPrice, INIT_PRICE
from export_file import export_file, ExportData, export_apr_results, export_stable_apr_results
from rm_types import RescaleFrequency, TestParams, GlobalParams, RangeStrategy, PriceActionLog, DcaTiming, DcaAddition
from market_v2 import UniLpMarketV2
from math_const import ZERO, ONE, HUNDRED, CONSERVATIVE_FLUCTUATION
from base_strategy import BaseRemixDaoStrategy
from demeter.uniswap.helper import (
    tick_to_base_unit_price,
    base_unit_price_to_tick,
    base_unit_price_to_sqrt_price_x96,
    sqrt_price_x96_to_base_unit_price,
    tick_to_sqrt_price_x96,
    get_swap_value_with_part_balance_used,
    MIN_ERROR,
    nearest_usable_tick,
    sqrt_price_x96_to_tick,
    load_uni_v3_data,
    get_price_from_data,
    _add_statistic_column,
)

conservative_fluctuation = CONSERVATIVE_FLUCTUATION

BAND_COUNT = 17


# short shape names for report files
SHAPE_LABELS = {"inverted_gaussian_9": "ig9", "inverted_gaussian": "ig17"}

# lower_ratio value meaning "mirror the upper side in ticks" (the original tick symmetric layout)
MIRROR_TICKS = "tick"
# lower_ratio value meaning "same percentage as the upper side" (+50% / -50%), resolved per sweep row
MIRROR_PRICE = "price"
# half_gap value meaning "one 17-band slot each side", the centre gap the original gamma
# inverted_gaussian_9 layout has (480 ticks at ratio 0.50 on a spacing 10 pool)
BAND_GAP = "band"
# half_gap written as "4+" keeps the same gap but does NOT subtract it from the reach: bands are
# sized as if there were no gap and pushed outward by it, so the outer edge lands at gap + ratio
GAP_OUTSIDE = "+"


def gap_label(half_gap: int | str) -> str:
    """Folder / report friendly name for a gap: 1 -> "1sp-" (one spacing each side, taken out of the
    reach), "1+" -> "1sp+" (same gap, added outside the reach), BAND_GAP -> "band"."""
    if half_gap == BAND_GAP:
        return half_gap
    return f"{half_gap[:-1]}sp+" if isinstance(half_gap, str) else f"{half_gap}sp-"


def ratio_label(ratio: Decimal | str) -> str:
    """Folder / report friendly name for a ratio, e.g. Decimal("0.05") -> "5%"; MIRROR_TICKS -> "tick"."""
    return ratio if isinstance(ratio, str) else f"{float(ratio * HUNDRED):g}%"


# eth_share value meaning "spec sheet 2.1": rebuild with ETH 70% when the last daily close is above
# EMA100, else 50%. Judged on the last COMPLETED UTC day, like the spec sheet's 00:00 close.
EMA_SHARE = "ema100"
EMA_SPAN = 100
SHARE_ABOVE_EMA, SHARE_BELOW_EMA = Decimal("0.7"), Decimal("0.5")

# spec sheet 2.2 signal engine: one virtual account per EMA span, F = mean of their deployed fractions.
# spec sheet 2.3: the real ladder is rebuilt to F x equity when |F - current| >= FOLLOW_THRESHOLD.
DEPLOY_FULL, DEPLOY_SIGNAL = "full", "signal"
EMA_SPANS = (90, 100, 110, 120)
EMA_WARMUP_DAYS = 3 * max(EMA_SPANS)  # adjust=False EMA needs ~3 spans of history to forget its seed
LOWER_STOP, UPPER_REBUILD = 0.80, 1.20
REFILL_CONFIRM_DAYS = 3                                   # stage 1 needs this many consecutive closes
REFILL_STAGES = ((1, 1.05), (2, 1.0833), (3, 1.1167), (4, 1.15))  # (stage, close / low), stage k -> k/4 deployed
FOLLOW_THRESHOLD = Decimal("0.125")
# EXP-001 (v6.1): share of the deployed F x equity held as spot base outside the bands (0 = v6)
SPOT_SLEEVE = Decimal("0")
# EXP-002 (v6.2): sell the sleeve when the daily close < SLEEVE_STOP x its high since bought (None = no stop)
SLEEVE_STOP: float | None = None
# EXP-003 (v6.3): the stop's high survives range-exit / follow rebuilds; only a (re-)arm resets it (False = v6.2)
SLEEVE_HIGH_KEEP = False
# EXP-004 (v6.4): daily supply APR (float, indexed by UTC day) earned on idle quote; None = cash earns nothing
CASH_APR: pd.Series | None = None
# EXP-005 (v6.5): a rising F adds its increment as a quote-only range order over the ladder's lower half (buys only
# on the dip, earns fees while waiting) instead of rebuilding and market-buying base. Falling F: as v6.
REFILL_ORDER = False
# EXP-006 (v6.6): place only the ladder's quote side; the base the upper bands would hold stays spot, so a rally
# does not sell it (upside IL). Exits are judged on the full ladder span v6 would have built. False = v6.
HALF_LADDER = False
# EXP-007 (v6.7): half ladder only for builds judged in an accelerating uptrend: EMA100's first difference > 0 and its
# second difference > 0 on the last completed day. Otherwise the full v6 ladder. False = v6.
HALF_WHEN_ACCEL = False
# EXP-012 (v6.9): deploy only while the pool pays its liquidity. The daily frame's F is zeroed on days whose trailing
# LVR_GATE_DAYS fee income per unit of in-range liquidity is below LVR_GATE_MIN x that unit's LVR (fee_lvr_ratio).
# Applied to the frame by the caller (v6_validate.daily_frame); the strategy itself reads the gated F. False = v6.
LVR_GATE = False
LVR_GATE_DAYS, LVR_GATE_MIN = 7, 1.0
# EXP-013 (v6.10): at every build shift the ladder's reaches SKEW toward the EMA100 trend: last daily close > EMA100
# -> lower reach - SKEW, upper reach + SKEW; otherwise the mirror. Read once per build (resolve_skew). 0 = v6.
SKEW = Decimal("0")
# EXP-014 (v6.11): short HEDGE x the base held inside the bands on a USDT-M perpetual. Set to target once a day at
# 00:00 UTC after the builds (all builds happen at 00:00), taker fee HEDGE_FEE on the traded notional, daily
# settlement of the price PnL, 8h funding from HEDGE_FUNDING (rate per settlement time, positive = the short
# receives). Every hedge cash flow goes to the quote balance: the margin account is part of the book. 0 = v6.
HEDGE = Decimal("0")
HEDGE_FEE = Decimal("0.0005")
HEDGE_LEVERAGE = Decimal("5")   # initial margin = notional / leverage, held in quote outside the ladder at each build
HEDGE_FUNDING: pd.Series | None = None
# EXP-016 (v6.13): when |ln(P_t / P_{t-PAUSE_WINDOW})| >= PAUSE_RET the whole ladder is pulled (fees collected) for
# PAUSE_MINUTES, then the same tick ranges are re-added from the wallet at the current price. No swap, no F change;
# the daily checks skip while paused. PAUSE_RET 0 = v6.
PAUSE_RET = 0.0
PAUSE_WINDOW, PAUSE_MINUTES = 5, 30
# EXP-018 (v6.14): while the daily frame's "short" flag is set (F = 0, close below every EMA in EMA_SPANS and a negative
# 12-month return, judged on the last completed day; built by the caller, see bear_short_flags) hold a perp short of
# BEAR_SHORT x book equity, re-sized at 00:00 after the builds. EXP-014's perp machinery (settlement, funding, fee).
# 0 = v6.
BEAR_SHORT = Decimal("0")
BEAR_SHORT_LOOKBACK = 365   # days, Moskowitz-Ooi-Pedersen 12-month time-series momentum
# EXP-020 (v6.16): no new bear short on a crash day — a daily log return below −BEAR_CRASH_SIGMA x the standard
# deviation of the previous BEAR_CRASH_WINDOW daily log returns (momentum shorts crash after panics, Daniel-Moskowitz
# 2016); a short already open is kept, entry waits for the next non-crash day with the condition still on. 0 = v6.14.
BEAR_CRASH_SIGMA = 0.0
BEAR_CRASH_WINDOW = 30
# EXP-022 (v6.17): collected LP fees (sold for quote) stay in the book: F x equity and every rebuild include them, so
# they are redeployed into the ladder at the next build. False = v6 (fees are paid out: held aside as idle quote).
FEE_COMPOUND = False
# EXP-023 (v6.18): also rebuild (recentre) the ladder when the base price is RECENTRE_UP above the price of the last
# build, i.e. halfway to the ladder's upper edge, instead of waiting for it to leave the ±20% span. Upside only:
# LP impermanent loss grows with the square of the move, so two half-width legs give up about half of one full-width
# leg in a trend. Judged at the same daily 00:00 check as the range exit. 0 = v6.
RECENTRE_UP = Decimal("0")
# EXP-024..027 (v6.19..v6.22): the regime line each virtual account compares the daily close with. "ema" = v6 (EMA of
# span n for n in EMA_SPANS). Others use the same four lengths n (90, 100, 110, 120): "donchian" = midpoint of the n-day
# high / low channel (daily high / low from the minute prices); "hma" = Hull MA(n); "roc" = the close n days ago
# (armed while the n-day return is positive); "supertrend" = ATR(n) x SUPERTREND_MULT trailing band. The s rule keeps
# EMA100, and the account logic (exit, re-arm, stop, staged refill) is unchanged.
REGIME = "ema"
SUPERTREND_MULT = 3.0
# EXP-028 / EXP-031 (v6.23 / v6.26): combinations of two regime lines. "ens_ed" = 8 accounts (4 EMA + 4 Donchian), F =
# their mean; "max_ed" = 4 accounts armed only while the close is above BOTH the EMA(n) and the Donchian midpoint(n).
# EXP-029 (v6.24): the ETH value share s moves with the share of the EMA spans (90, 100, 110, 120) the last close is above:
# s = SHARE_BELOW_EMA + (SHARE_ABOVE_EMA - SHARE_BELOW_EMA) x that share (v6: all or nothing on EMA100 alone). False = v6.
SHARE_BY_ARMED = False
# EXP-030 (v6.25): ladder half-width per build = WIDTH_VOL_K x sigma x sqrt(WIDTH_VOL_DAYS), sigma = std of the last
# WIDTH_VOL_DAYS completed daily log returns, clamped to [WIDTH_VOL_MIN, WIDTH_VOL_MAX] and rounded to WIDTH_VOL_GRID, the
# same width up and down (the ladder keeps v6's valley shape). False = v6's fixed +-20%.
WIDTH_VOL = False
WIDTH_VOL_K, WIDTH_VOL_DAYS = 1.0, 30
WIDTH_VOL_MIN, WIDTH_VOL_MAX, WIDTH_VOL_GRID = 0.10, 0.30, 0.05
# EXP-044 (v6.31): the ladder is rebuilt after a range exit only when the price is outside it at EXIT_CONFIRM consecutive
# daily checks (the one-sided ladder earns no fees meanwhile; a close back inside cancels the exit). 1 = v6.
EXIT_CONFIRM = 1
# EXP-045 (v6.32): the signal engine's F is read once a week: the Sunday close's F is held until the next Sunday. False = v6.
F_WEEKLY = False
# EXP-047 (v6.34): F never below F_FLOOR (one of the four refill stages always stays deployed). 0 = v6.
F_FLOOR = 0.0
# EXP-052 (v6.39): idle quote outside the ladder (the reserve (1 - F) x equity, not the paid-out fees) is LP'd in the
# mainnet Uniswap v3 USDC/USDT pool, ±0.1% around the peg (samples/make_stable_lp_series.py). STABLE_LP = daily net
# return per $ (fee share + mark to market), booked once a day at 00:00 on the reserve held then, paid out like the fees;
# every change of the reserve pays STABLE_SWITCH_FEE on half the moved amount (the position is ~half USDT). None = v6.
STABLE_LP: pd.Series | None = None
STABLE_SWITCH_FEE = Decimal("0.0001")
# EXP-053 (v6.40): downside volatility targeting. On days the close is <= EMA100, F x min(1, VOL_TARGET / sigma_14),
# sigma_14 = std of the last VOL_TARGET_DAYS daily log returns, VOL_TARGET = the asset's median sigma_14 over
# 2019-01-01..2021-04-30 (Binance daily closes, before any pool data). None = v6.
VOL_TARGET: float | None = None
VOL_TARGET_DAYS = 14
# EXP-054 (v6.41): chop gate on the EMA exit. An armed account's "close < EMA" exit fires only while Kaufman's efficiency
# ratio over ER_DAYS daily closes is >= 1 / sqrt(ER_DAYS), the random-walk level (below it the market moved less than a
# random walk: chop, the exit would be a whipsaw). The lower stop, re-arm and refill rules are unchanged. False = v6.
ER_GATE = False
ER_DAYS = 30
# EXP-055 (v6.42): a follow rebuild (|F - deployed| >= FOLLOW_THRESHOLD) resizes the ladder in place instead of rebuilding it:
# every band keeps its ticks and its liquidity is scaled by target / current (fees collected first). Shrinking sells the
# withdrawn base for quote (the reserve stays quote); growing buys the base the bands need at their current composition and
# adds liquidity to the same ticks. No recentre and no swap back to the target ETH share on F changes; range exits, the
# first build and builds from an empty book are v6's full rebuilds. False = v6.
RESIZE_IN_PLACE = False
# EXP-056 (v6.43): the range-exit check (price outside the ladder -> full rebuild) runs every hour instead of once a day at
# 00:00 UTC. F, the ETH share and the follow rule are still judged once a day on the last completed day. False = v6.
EXIT_CHECK_HOURLY = False
# EXP-057 (v6.44): a range-exit rebuild places the new ladder from the inventory the old one left, without the swap back to
# the target ETH share (Charm Alpha Vault "base + limit"): each side's bands take all of that side's token, so after an
# upward exit (all quote) the ladder is bids below the price, after a downward exit (all base) asks above it; the pool
# converts them while paying fees. Follow rebuilds (F changes) and builds from an empty book keep v6's swap. False = v6.
SWAPLESS_EXIT = False
# EXP-058 (v6.45): hybrid of v6 and EXP-055 on follow events: while the price is in the inner half of the ladder (within half
# of each side's reach, ~±10%, of the tick of the last full build) the ladder is resized in place (resize_work); farther out,
# v6's full rebuild recentres it. False = v6.
RESIZE_NEAR_CENTRE = False
# EXP-059 (v6.46): scheduled-event pause. MACRO_EVENTS = sorted release times (UTC) of FOMC statements and US CPI
# (samples/macro_events_utc.csv). The ladder is pulled MACRO_BEFORE before each release (EXP-016's pause_ladder: burns,
# fees collected, no swap) and re-added MACRO_AFTER after it at the same ticks from the tokens that came out (the reserve is
# not added). The daily checks skip while paused, as in EXP-016. None = v6.
MACRO_EVENTS: list | None = None
MACRO_BEFORE, MACRO_AFTER = timedelta(minutes=30), timedelta(hours=2)
# EXP-060 (v6.47): EXP-059 with an exact restore. At the re-add every band gets back the liquidity it had before the pause:
# its token amounts at the current price are computed, one net swap covers the difference with the tokens that came out
# (the reserve is not used), then the bands are minted at the same ticks. No idle leftover, so no extra follow rebuild.
MACRO_RESTORE = False
# EXP-061 (v6.48): existing liquidity is never recentred on a follow event. F up: the increment (target - current) x equity is
# placed as a new 17-band tranche centred on today's price at the target ETH share (one swap for the increment only); bands
# with the same ticks merge. F down (> 0): every band shrinks by target / current (EXP-055's shrink). Range exits (price
# outside the union of all tranches), first builds, builds from an empty book and F = 0 are v6's full rebuilds. False = v6.
TRANCHE_ADD = False
# EXP-062 (v6.49): asymmetric follow: F down (> 0) shrinks every band in place (EXP-055's shrink, no recentre); F up is v6's full
# rebuild (recentre at today's price). False = v6.
FOLLOW_ASYM = False
# EXP-063 (v6.50): the four virtual accounts become four real sub-ladders. Account j (EMA span j) owns a 17-band valley of
# deployed_j / 4 x book equity centred on the price of the day its state last changed; the sub-ladder is rebuilt (burn, one
# net swap for all changed sub-ladders, re-mint at today's price, v6's ETH share) only when its account's deployed fraction or
# centre changes (staged refill, upper rebuild at 1.2 x centre, EMA exit, lower stop at 0.8 x centre), judged daily at 00:00
# on the last completed day. v6's single-ladder range exit and follow rule are off. Each sub-ladder tracks the liquidity it
# added, so bands shared by two sub-ladders are reduced only by the rebuilt one's part. False = v6.
ACCOUNT_TRANCHES = False
# EXP-064 (v6.51): CPPI-style floor on the strategy's own net value. The follow rule's target becomes F x m, m = clip((W / HWM -
# CPPI_FLOOR) / (1 - CPPI_FLOOR), 0, 1), W = total book value (LP + wallet, paid-out fees included), HWM = its high since the
# start, both read at the daily 00:00 check. CPPI_FLOOR = 0.8 = v6's own lower stop (LOWER_STOP). None = v6.
CPPI_FLOOR: float | None = None
# EXP-065 (v6.52): time-based recentre in addition to v6's triggers: every Sunday at 00:00 UTC a deployed ladder gets v6's full
# rebuild (recentre at today's price, swap to the target share, size F x equity). False = v6.
WEEKLY_RECENTRE = False
# EXP-066..068 (v6.53..v6.55): ablations of the signal engine's account rules (nothing tuned, one rule removed or restricted):
# NO_LOWER_STOP drops rule 3 (exit at close < 0.8 x centre); REFILL_ARMED_ONLY allows the staged refill (rule 5) only while the
# account is armed (close above its EMA); REARM_FULL replaces the staged refill by a full deployment at the re-arm (close crosses
# above the EMA: deployed 1, centre = close), i.e. a plain EMA trend filter with v6's stop and upper rebuild. False = v6.
NO_LOWER_STOP = False
REFILL_ARMED_ONLY = False
REARM_FULL = False
# EXP-069 (v6.56): ablation of rule 4 (upper rebuild: close > 1.2 x centre moves the virtual centre up); the centre then stays
# at the price of the last refill stage, so the lower stop (0.8 x centre) does not trail a rally. False = v6.
NO_UPPER_REBUILD = False
# EXP-071 (v6.58): EXP-065's weekly recentre only in the uptrend state (last completed close > EMA100, the state of v6's ETH
# share rule); below EMA100 no extra recentre. False = v6.
WEEKLY_RECENTRE_UP = False
# EXP-072 (v6.59): follow events below EMA100 (last completed close <= EMA100) resize the ladder in place (EXP-055); above it,
# v6's full rebuild. False = v6.
RESIZE_BELOW_EMA = False
# EXP-074..075 (v6.61..v6.62): ablations of the real ladder's range-exit rebuild. "all": a ladder the price has left is never
# rebuilt for that reason (it waits, out of range, for the next follow event); "down": only exits below the ladder are skipped
# (the ladder, now all base, waits), exits above are v6's. False = v6.
NO_EXIT_REBUILD: str | bool = False
# EXP-077..081 (v6.64..v6.68): ablations of how the engine turns its accounts into F. F_AGG "min" / "max": F = the lowest /
# highest account's deployed fraction instead of their mean. F_BINARY "any": F = 1 while any account is deployed, else 0; "all":
# F = 1 only while every account is fully deployed, else 0. REFILL_ONE_STAGE: the staged refill's first stage (close >= 1.05 x
# low for 3 days) deploys the account fully (no stages 2-4). (EXP-076, one EMA100 account, is EMA_SPANS = (100,).) v6 = mean,
# no binarisation, four stages.
F_AGG = "mean"
F_BINARY: str | None = None
REFILL_ONE_STAGE = False
# EXP-082..086 (v6.69..v6.73): non-price information for the refill / F, from EXTRA (a daily frame the caller builds, index =
# UTC day): "dvol" (Deribit DVOL of the pool's asset), "fund" (Binance perp funding of the asset, daily mean of the 8h rates),
# "other" (Binance daily close of the other asset: BTC for ETH pools, ETH for BTC pools). Days without data never block.
# REFILL_GATE "dvol_turn": a refill stage fires only while DVOL is falling: its 3-day mean is below the 3-day mean of 3 days earlier
# (the refill's own 3-day confirmation length);
# "xasset": only if the other asset closes >= 1.05 x its lowest close since the exit.
# FUND_REFILL "accel": stage 1 fires without the 3-day hold when the 7-day mean funding is < 0 (and close >= 1.05 x low);
# "accel_brake": also, stages 2-4 wait while the 3-day mean funding is > FUND_HOT (3 x Binance's 0.01% base rate).
# FUND_CAP: F <= 0.5 while the 3-day mean funding is > FUND_HOT. None / False = v6.
EXTRA: pd.DataFrame | None = None
REFILL_GATE: str | None = None
FUND_REFILL: str | None = None
FUND_CAP = False
FUND_HOT = 0.0003
# EXP-087..091 (v6.74..v6.78): REFILL_VOL_CONFIRM: a refill stage fires only if the pool's 3-day swap volume (EXTRA "pvol", daily)
# is >= its 30-day median. REFILL_NO_NEW_LOW: a day counts for a refill stage only if its intraday low (minute data) stays above
# the account's low since the exit. TWAP_ENGINE: the engine (EMAs, stops, refills, share rule) reads the daily time-weighted
# mean price instead of the last price of the day. VRP_PULL: while the 7-day realised vol of daily log returns (annualised, %)
# is above DVOL, F = max(0, F - 0.25) (one refill stage less). BREADTH_CAP: F <= the mean of F and the other asset's F (EXTRA
# "other_F", v6's engine on the other asset's Binance closes). False = v6.
REFILL_VOL_CONFIRM = False
REFILL_NO_NEW_LOW = False
TWAP_ENGINE = False
VRP_PULL = False
BREADTH_CAP = False
FULL_TOLERANCE = Decimal("0.02")  # ponytail: "fully deployed" / "empty" with dust tolerance, else daily rebuilds
POOL_FIRST_DATA_DATE = date(2021, 5, 6)  # first minute file of the mainnet USDC/WETH 0.05% pool in real-data


@dataclass
class VirtualAccount:
    """One spec sheet 2.2 virtual account, stepped once per daily close. Floats: it only produces F."""
    span: int
    armed: bool = False
    deployed: float = 0.0          # 0 / .25 / .5 / .75 / 1
    centre: float | None = None    # virtual ladder centre, None when out
    low: float | None = None       # lowest close since the exit, drives the refill
    stage: int = 0
    confirm: int = 0
    started: bool = False
    dvol_peak: float | None = None   # EXP-082: highest DVOL since the exit
    olow: float | None = None        # EXP-086: lowest close of the other asset since the exit

    def exit(self, close: float) -> None:
        self.deployed, self.centre, self.low, self.stage, self.confirm = 0.0, None, close, 0, 0
        self.dvol_peak, self.olow = None, None

    def step(self, close: float, ema: float, trend_ok: bool = True, ctx: dict | None = None) -> None:
        if not self.started:  # ponytail: engine starts at warm-up start, not 2017; 360 days settle it
            self.started, self.armed = True, close > ema
            if self.armed:
                self.deployed, self.stage, self.centre = 1.0, 4, close
            else:
                self.low = close
            return
        if self.armed and close < ema and trend_ok:         # 1 EMA exit (spec: low resets even if empty); EXP-054 gate
            self.exit(close)
            self.armed = False
        elif not self.armed and close > ema:                # 2 re-arm, no buy
            self.armed = True
            if REARM_FULL:                                  # EXP-068: re-arm deploys fully
                self.deployed, self.stage, self.centre = 1.0, 4, close
        if not NO_LOWER_STOP and self.deployed > 0 and close < self.centre * LOWER_STOP:      # 3 lower stop (EXP-066 drops it)
            self.exit(close)
        elif not NO_UPPER_REBUILD and self.deployed > 0 and close > self.centre * UPPER_REBUILD: # 4 upper rebuild (EXP-069 drops it)
            self.centre = close
        if self.deployed < 1 and not REARM_FULL and (self.armed or not REFILL_ARMED_ONLY):   # 5 staged refill (EXP-067 / 068)
            ctx = ctx or {}
            dv, ot = ctx.get("dvol", float("nan")), ctx.get("other", float("nan"))
            if dv == dv:   # EXP-082: track the DVOL peak since the exit
                self.dvol_peak = dv if self.dvol_peak is None else max(self.dvol_peak, dv)
            if ot == ot:   # EXP-086: track the other asset's low since the exit
                self.olow = ot if self.olow is None else min(self.olow, ot)
            self.low = min(self.low, close)
            ok_day = not (REFILL_NO_NEW_LOW and (ctx or {}).get("dlow", float("inf")) <= self.low)   # EXP-088
            self.confirm = self.confirm + 1 if (close >= self.low * REFILL_STAGES[0][1] and ok_day) else 0
            # at most one stage per day (spec author's clarification); a pullback keeps the stage,
            # only an exit resets it
            nxt = self.stage + 1
            if nxt == 1:
                advance = self.confirm >= REFILL_CONFIRM_DAYS
            else:
                advance = close >= self.low * REFILL_STAGES[nxt - 1][1]
            if FUND_REFILL and nxt == 1 and not advance and close >= self.low * REFILL_STAGES[0][1] \
                    and ctx.get("fund7", 0.0) < 0:   # EXP-083 / 084: shorts crowded -> no 3-day hold
                advance = True
            if FUND_REFILL == "accel_brake" and nxt >= 2 and ctx.get("fund3", 0.0) > FUND_HOT:   # EXP-084
                advance = False
            if advance and REFILL_VOL_CONFIRM and ctx.get("pvol_ok", 1.0) == 0.0:   # EXP-087
                advance = False
            if advance and REFILL_NO_NEW_LOW and ctx.get("dlow", float("inf")) <= self.low:   # EXP-088
                advance = False
            if advance and REFILL_GATE == "dvol_turn":   # EXP-082: implied vol must be falling
                d3, d3p = ctx.get("dvol3", float("nan")), ctx.get("dvol3_prev", float("nan"))
                advance = not (d3 == d3 and d3p == d3p and d3 >= d3p)
            if advance and REFILL_GATE == "xasset":   # EXP-086
                advance = not (ot == ot and self.olow is not None and ot < self.olow * REFILL_STAGES[0][1])
            if advance:
                self.stage, self.deployed, self.centre = nxt, nxt / 4, close
                if REFILL_ONE_STAGE:   # EXP-081
                    self.stage, self.deployed = 4, 1.0


def share_label(eth_share: Decimal | str | None) -> str:
    """Report / folder label for the ETH value share: None -> "sgeo" (range geometry decides),
    0.7 -> "s70", EMA_SHARE -> "sema100"."""
    if eth_share is None:
        return "sgeo"
    if eth_share == EMA_SHARE:
        return f"sema{EMA_SPAN}"
    return f"s{float(eth_share * HUNDRED):g}"


def _wma(x: pd.Series, n: int) -> pd.Series:
    w = np.arange(1, n + 1, dtype=float)
    return x.rolling(n, min_periods=1).apply(lambda v: float(np.dot(v, w[-len(v):]) / w[-len(v):].sum()), raw=True)


def _supertrend(high: pd.Series, low: pd.Series, close: pd.Series, period: int, mult: float) -> pd.Series:
    """Standard Supertrend line (Wilder ATR): the lower band while the trend is up, the upper band while down."""
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    mid = (high + low) / 2
    ub, lb = (mid + mult * atr).to_numpy(), (mid - mult * atr).to_numpy()
    c = close.to_numpy()
    fub, flb, line = ub.copy(), lb.copy(), np.empty(len(c))
    line[0] = flb[0] if c[0] > mid.iloc[0] else fub[0]
    for i in range(1, len(c)):
        fub[i] = ub[i] if ub[i] < fub[i - 1] or c[i - 1] > fub[i - 1] else fub[i - 1]
        flb[i] = lb[i] if lb[i] > flb[i - 1] or c[i - 1] < flb[i - 1] else flb[i - 1]
        if line[i - 1] == fub[i - 1]:
            line[i] = fub[i] if c[i] <= fub[i] else flb[i]
        else:
            line[i] = flb[i] if c[i] >= flb[i] else fub[i]
    return pd.Series(line, index=close.index)


SLOW_SPANS = (170, 190, 210, 230)      # EXP-036: SMA lengths around the classic 200 days, ~10% apart like v6's EMA spans
DD_FRAC = 0.20                         # EXP-039: armed while the close is within DD_FRAC of its n-day high (= the ladder half-width)
ICHIMOKU_K = (1.0, 1.5, 2.0, 2.5)      # EXP-037: scale of the standard Ichimoku periods 9 / 26 / 52 (shift 26)


def _ichimoku_top(high: pd.Series, low: pd.Series, k: float) -> pd.Series:
    """Upper edge of the Ichimoku cloud (max of Senkou A and B), standard 9/26/52 periods and 26 displacement x k."""
    conv, base, span, shift = (max(int(round(v * k)), 1) for v in (9, 26, 52, 26))
    mid = lambda n: (high.rolling(n, min_periods=1).max() + low.rolling(n, min_periods=1).min()) / 2
    a, b = (mid(conv) + mid(base)) / 2, mid(span)
    return pd.concat([a.shift(shift), b.shift(shift)], axis=1).max(axis=1).bfill()


def _aroon(x: pd.Series, n: int, up: bool) -> pd.Series:
    """Aroon Up (up=True, on highs) / Down (on lows): 100 x (n - days since the n-day extreme) / n."""
    since = x.rolling(n + 1, min_periods=1).apply(lambda v: len(v) - 1 - (np.argmax(v) if up else np.argmin(v)), raw=True)
    return 100.0 * (n - since) / n


def regime_components() -> list:
    return {"ens_ed": ["ema", "donchian"], "max_ed": ["max_ed"]}.get(REGIME, [REGIME])


def regime_lines(minute_price: pd.Series, close: pd.Series, kind: str) -> dict:
    """EXP-024..031: per account span n, the line the daily close is compared with (see REGIME)."""
    high = minute_price.resample("1D").max().reindex(close.index)
    low = minute_price.resample("1D").min().reindex(close.index)
    out = {}
    for n in EMA_SPANS:
        if kind == "ema":
            out[n] = close.ewm(span=n, adjust=False).mean()
        elif kind == "sma":   # EXP-036: simple MA over the slow lengths SMA_SPANS (the EMA_SPANS slot picks the position)
            out[n] = close.rolling(SLOW_SPANS[EMA_SPANS.index(n)], min_periods=1).mean()
        elif kind == "dd":   # EXP-039: line = (1 - DD_FRAC) x the n-day high of the close
            out[n] = (1 - DD_FRAC) * close.rolling(n, min_periods=1).max()
        elif kind == "ichimoku":   # EXP-037: top of the cloud, periods and shift scaled by ICHIMOKU_K[position]
            out[n] = _ichimoku_top(high, low, ICHIMOKU_K[EMA_SPANS.index(n)])
        elif kind == "aroon":   # EXP-038: armed while Aroon Up(n) > Aroon Down(n): line = half / double the close
            up = _aroon(high, n, True) > _aroon(low, n, False)
            out[n] = close.where(~up, close * 0.5).where(up, close * 2.0)
        elif kind == "max_ed":
            ema = close.ewm(span=n, adjust=False).mean()
            out[n] = np.maximum(ema, (high.rolling(n, min_periods=1).max() + low.rolling(n, min_periods=1).min()) / 2)
        elif kind == "donchian":
            out[n] = (high.rolling(n, min_periods=1).max() + low.rolling(n, min_periods=1).min()) / 2
        elif kind == "hma":
            out[n] = _wma(2 * _wma(close, max(n // 2, 1)) - _wma(close, n), max(int(round(n ** 0.5)), 1))
        elif kind == "roc":
            out[n] = close.shift(n).bfill()
        elif kind == "supertrend":
            out[n] = _supertrend(high, low, close, n, SUPERTREND_MULT)
        else:
            raise ValueError(kind)
    return out


def daily_ema_frame(minute_price: pd.Series) -> pd.DataFrame:
    """UTC daily closes (last price of each day), their EMA100 ("ema", for the s rule) and the signal
    engine's target deployment F, from a minute price series that should start EMA_WARMUP_DAYS before
    the backtest window so the EMAs and the virtual accounts are settled on day one."""
    close = minute_price.astype(float).resample("1D").last().dropna()
    if TWAP_ENGINE:   # EXP-089: daily time-weighted mean of the minute prices
        close = minute_price.astype(float).resample("1D").mean().reindex(close.index)
    day_low = minute_price.astype(float).resample("1D").min().reindex(close.index)   # EXP-088
    emas = {n: close.ewm(span=n, adjust=False).mean() for n in EMA_SPANS}
    comps = regime_components()
    lines = {k: emas if k == "ema" else regime_lines(minute_price.astype(float), close, k) for k in comps}
    accounts = [(k, VirtualAccount(n)) for k in comps for n in EMA_SPANS]
    path = close.diff().abs().rolling(ER_DAYS, min_periods=ER_DAYS).sum()   # EXP-054: Kaufman efficiency ratio
    er = ((close - close.shift(ER_DAYS)).abs() / path).fillna(1.0)
    trend_ok = (er >= 1 / np.sqrt(ER_DAYS)) if ER_GATE else pd.Series(True, index=close.index)
    fractions = []
    states = {f"{x}{j}": [] for j in range(len(EMA_SPANS)) for x in ("dep", "ctr")}   # EXP-063
    ex = None
    if EXTRA is not None:   # EXP-082..086: daily context, aligned to the closes
        ex = EXTRA.reindex(close.index)
        if "dvol" in ex:
            ex["dvol3"] = ex["dvol"].rolling(3, min_periods=1).mean()
            ex["dvol3_prev"] = ex["dvol3"].shift(3)
        if "pvol" in ex:   # EXP-087: 3-day volume vs its 30-day median (unknown -> ok)
            v3, med = ex["pvol"].rolling(3, min_periods=3).sum(), (ex["pvol"].rolling(3, min_periods=3).sum()).rolling(30, min_periods=30).median()
            ex["pvol_ok"] = (~(v3 < med)).astype(float)
        if "fund" in ex:
            ex["fund3"] = ex["fund"].rolling(3, min_periods=1).mean()
            ex["fund7"] = ex["fund"].rolling(7, min_periods=1).mean()
    for day, c in close.items():
        ctx = {k: float(v) for k, v in ex.loc[day].items()} if ex is not None else {}
        ctx["dlow"] = float(day_low[day]) if day_low[day] == day_low[day] else float("inf")
        for k, a in accounts:
            a.step(float(c), float(lines[k][a.span][day]), bool(trend_ok[day]) if k == "ema" else True, ctx)
        deps = [a.deployed for _, a in accounts]
        f = min(deps) if F_AGG == "min" else max(deps) if F_AGG == "max" else sum(deps) / len(deps)   # EXP-077 / 078
        if F_BINARY == "any":   # EXP-079
            f = 1.0 if f > 0 and max(deps) > 0 else 0.0
        elif F_BINARY == "all":   # EXP-080
            f = 1.0 if min(deps) >= 1.0 else 0.0
        fractions.append(f)
        if ACCOUNT_TRANCHES:
            for j, (_, a) in enumerate([x for x in accounts if x[0] == "ema"]):
                states[f"dep{j}"].append(a.deployed)
                states[f"ctr{j}"].append(a.centre if (a.deployed > 0 and a.centre is not None) else float("nan"))
    if F_WEEKLY:   # EXP-045: the Sunday value, held until the next Sunday
        fs = pd.Series(fractions, index=close.index)
        fractions = fs.where(fs.index.dayofweek == 6).ffill().bfill().tolist()
    if VRP_PULL and ex is not None and "dvol" in ex:   # EXP-090
        rv7 = np.log(close).diff().rolling(7, min_periods=7).std() * np.sqrt(365) * 100
        hot = (rv7 > ex["dvol"]).fillna(False).tolist()
        fractions = [max(0.0, f - 0.25) if h else f for f, h in zip(fractions, hot)]
    if BREADTH_CAP and ex is not None and "other_F" in ex:   # EXP-091
        of = ex["other_F"].tolist()
        fractions = [min(f, (f + o) / 2) if o == o else f for f, o in zip(fractions, of)]
    if FUND_CAP and ex is not None and "fund3" in ex:   # EXP-085
        hot = (ex["fund3"] > FUND_HOT).fillna(False).tolist()
        fractions = [min(f, 0.5) if h else f for f, h in zip(fractions, hot)]
    if F_FLOOR > 0:   # EXP-047
        fractions = [max(f, F_FLOOR) for f in fractions]
    if VOL_TARGET is not None:   # EXP-053: downside-only volatility targeting of F
        s14 = np.log(close).diff().rolling(VOL_TARGET_DAYS, min_periods=VOL_TARGET_DAYS).std()
        scale = np.minimum(1.0, VOL_TARGET / s14).fillna(1.0)
        down = close <= close.ewm(span=EMA_SPAN, adjust=False).mean()
        fractions = [f * (float(k) if d else 1.0) for f, k, d in zip(fractions, scale, down)]
    arm = sum((close > emas[n]).astype(float) for n in EMA_SPANS) / len(EMA_SPANS)   # EXP-029
    sigma = np.log(close).diff().rolling(WIDTH_VOL_DAYS, min_periods=WIDTH_VOL_DAYS).std()   # EXP-030
    out = pd.DataFrame({"close": close, "ema": emas[EMA_SPAN], "F": fractions, "arm": arm, "sigma": sigma})
    if ACCOUNT_TRANCHES:   # EXP-063
        for key, vals in states.items():
            out[key] = vals
    return out


def fee_lvr_ratio(minute: pd.DataFrame, fee_pct: float, days: int | None = None) -> pd.Series:
    """EXP-012: per UTC day, the pool's fee income per unit of in-range liquidity over that unit's LVR, both summed
    over the trailing `days` completed days (fewer at the start of the data). Raw token1 per unit liquidity on
    both sides, so the ratio is unit-free and the same for every band shape:
      fee_m = fee x (inAmount1 + inAmount0 x P) / currentLiquidity,   P = 1.0001^closeTick
      lvr_m = ln(P_m / P_{m-1})^2 x sqrt(P) / 4   (in-range v3 = constant product on virtual reserves L/sqrt(P),
              L sqrt(P); LVR rate sigma^2 P^2 |x'(P)| / 2 = sigma^2 L sqrt(P) / 4, Milionis et al. 2022)
    `fee_pct` is the pool fee in percent (0.05 -> 0.0005)."""
    days = days or LVR_GATE_DAYS
    p = np.power(1.0001, minute["closeTick"].astype(float))
    liq = minute["currentLiquidity"].astype(float)
    vol1 = minute["inAmount1"].astype(float) + minute["inAmount0"].astype(float) * p
    fee = ((fee_pct / 100.0) * vol1 / liq.where(liq > 0)).fillna(0.0)
    r = np.log(p).diff().fillna(0.0)
    lvr = r * r * np.sqrt(p) / 4
    daily = pd.DataFrame({"fee": fee, "lvr": lvr}).resample("1D").sum(min_count=1).dropna()
    roll = daily.rolling(days, min_periods=1).sum()
    return (roll["fee"] / roll["lvr"]).rename("R")


def gate_fractions(daily: pd.DataFrame, ratio: pd.Series, minimum: float | None = None) -> pd.DataFrame:
    """EXP-012: copy of the daily signal frame with F zeroed where `ratio` < `minimum`; the raw F is kept as
    "F_raw" and the ratio as "R". Days without a ratio (no pool data yet) keep their F."""
    minimum = LVR_GATE_MIN if minimum is None else minimum
    out = daily.copy()
    out["F_raw"] = out["F"]
    out["R"] = ratio.reindex(out.index)
    out["F"] = out["F"].where(out["R"].isna() | (out["R"] >= minimum), 0.0)
    return out


def perp_enabled() -> bool:
    """A perp leg is in play: EXP-014's delta hedge or EXP-018's bear short."""
    return HEDGE > ZERO or BEAR_SHORT > ZERO


def bear_short_flags(daily: pd.DataFrame, long_close: pd.Series) -> pd.DataFrame:
    """EXP-018: copy of the daily signal frame with a boolean "short" column: F == 0, the close below the EMA of every
    span in EMA_SPANS, and close / close BEAR_SHORT_LOOKBACK days earlier < 1. The 12-month return is read from
    `long_close` (daily closes reaching further back than the pool's minutes); days without it are never short."""
    out = daily.copy()
    below = pd.Series(True, index=out.index)
    for n in EMA_SPANS:
        below &= out["close"] < out["close"].ewm(span=n, adjust=False).mean()
    lc = long_close.astype(float).sort_index()
    year_ret = (lc / lc.shift(BEAR_SHORT_LOOKBACK, freq="D").reindex(lc.index)).reindex(out.index)
    out["year_ret"] = year_ret
    cond = (out["F"] == 0) & below & (year_ret < 1)
    if BEAR_CRASH_SIGMA:   # EXP-020: no new short on a crash day; an open short is kept
        r = np.log(out["close"].astype(float)).diff()
        crash = r < -BEAR_CRASH_SIGMA * r.rolling(BEAR_CRASH_WINDOW).std().shift(1)
        on, flags = False, []
        for c, k in zip(cond, crash):
            on = bool(c) and (on or not bool(k))
            flags.append(on)
        cond = pd.Series(flags, index=out.index)
    out["short"] = cond
    return out


def daily_row_for(daily: pd.DataFrame, timestamp: datetime) -> tuple[pd.Timestamp, pd.Series]:
    """The last completed UTC day before `timestamp` and its row (spec sheet judges on that close)."""
    day = pd.Timestamp(timestamp - timedelta(days=1)).normalize()
    return day, daily.loc[day]


def ema_share_for(daily: pd.DataFrame, timestamp: datetime) -> tuple[Decimal, pd.Timestamp, float, float]:
    """(share, judged day, close, ema) for a (re)build at `timestamp`."""
    day, row = daily_row_for(daily, timestamp)
    if SHARE_BY_ARMED:   # EXP-029: arm is a multiple of 1/4 (four spans), exact in Decimal
        share = SHARE_BELOW_EMA + (SHARE_ABOVE_EMA - SHARE_BELOW_EMA) * Decimal(str(row["arm"]))
    else:
        share = SHARE_ABOVE_EMA if row["close"] > row["ema"] else SHARE_BELOW_EMA
    return share, day, float(row["close"]), float(row["ema"])


def ema_accelerating(daily: pd.DataFrame, timestamp: datetime) -> bool:
    """EMA100's first and second daily differences both > 0 on the last completed day (EXP-007)."""
    day = daily_row_for(daily, timestamp)[0]
    ema = daily["ema"].loc[:day].tail(3)
    if len(ema) < 3:
        return False
    d1, d0 = ema.iloc[2] - ema.iloc[1], ema.iloc[1] - ema.iloc[0]
    return bool(d1 > 0 and d1 - d0 > 0)


def target_fraction_for(daily: pd.DataFrame, timestamp: datetime) -> Decimal:
    """Signal engine F (0..1, multiples of 1/16) judged on the last completed day."""
    return Decimal(str(daily_row_for(daily, timestamp)[1]["F"]))


def swap_to_value_share(base: Decimal, quote: Decimal, price: Decimal, base_share: Decimal) -> Tuple[Decimal, Decimal]:
    """
    How much to swap so base holds `base_share` of total value (spec sheet s: 0.7 = ETH 70% / USDC 30%).
    `price` is the base price in quote. Returns (base_to_swap, quote_to_swap), one of them zero, same
    interface as BaseRemixDaoStrategy.calculate_swap_amount. Swap fees are not modelled here, so the
    share lands a little under target; the spec sheet only asks for "about 70%".
    """
    if not (ZERO <= base_share <= ONE):
        raise ValueError(f"base_share must be within [0, 1], got {base_share}")
    total = quote + base * price
    target_base = total * base_share / price
    if target_base > base:
        return ZERO, (target_base - base) * price
    return base - target_base, ZERO


def build_gap_bands(upper_ratio: Decimal, lower_ratio: Decimal | str, tick_spacing: int,
                    side_count: int, half_gap: int | str) -> List[Tuple[int, int]]:
    """
    Bands as tick offsets from the (rounded) current tick: `side_count` equal bands below the
    price, a centre band of [-half_gap, +half_gap], and `side_count` equal bands above.

    `upper_ratio` 0.50 reaches +50% in price; `lower_ratio` 0.50 reaches -50% (price x 0.5). The
    two sides are sized independently, so a price symmetric range is more ticks below than above.
    `lower_ratio` MIRROR_TICKS ("tick") mirrors the upper side in ticks (the original tick
    symmetric layout, which for +50% reaches about -33% in price).
    `half_gap` is in tick spacings each side: 0 means the two sides meet at the centre tick, 1 leaves
    one spacing above and below. BAND_GAP ("band") sizes it as one 17-band slot of the upper reach,
    which is the gap the original gamma layout had. "4+" (GAP_OUTSIDE suffix) is a 4 spacing gap that
    is not taken out of the reach: band width is computed as if there were no gap, so the outer
    edge sits at gap + reach instead of at reach.
    """
    if upper_ratio <= ZERO or (lower_ratio != MIRROR_TICKS and not (ZERO < lower_ratio < ONE)):
        raise ValueError(f"upper_ratio must be > 0 and 0 < lower_ratio < 1, got {upper_ratio} / {lower_ratio}")
    if side_count <= 0:
        raise ValueError(f"side_count must be positive, got {side_count}")
    gap_outside = isinstance(half_gap, str) and half_gap.endswith(GAP_OUTSIDE)
    if gap_outside:
        half_gap = int(half_gap[:-1])
    if half_gap != BAND_GAP and half_gap < 0:
        raise ValueError(f"half_gap must be BAND_GAP or a non-negative number of tick spacings, got {half_gap}")

    up_reach = math.log(1 + float(upper_ratio)) / math.log(1.0001)

    def band_width(reach: float) -> int:
        width = round((reach - (0 if gap_outside else half_gap)) / side_count / tick_spacing) * tick_spacing
        if width <= 0:
            raise ValueError(f"reach {reach:.0f} ticks minus gap {half_gap} over {side_count} bands is narrower than tick spacing {tick_spacing}")
        return width

    if half_gap == BAND_GAP:
        # gamma's 17-band arithmetic, so results match remix_dao_gamma_bands9: one band snapped to
        # twice the spacing, the centre band is the gap, each side band is two of them, and the outer
        # edge lands at 8.5 bands (480 / 240 / 960 / 4080 at ratio 0.50 on a spacing 10 pool)
        if side_count != 4:
            raise ValueError(f"BAND_GAP pairs 17 bands into 9, got a shape with {2 * side_count + 1}")
        step = 2 * tick_spacing
        band17 = round(up_reach * 2 / BAND_COUNT / step) * step
        half_gap = band17 // 2
        up = 2 * band17
    else:
        half_gap = half_gap * tick_spacing
        up = band_width(up_reach)
    down = up if lower_ratio == MIRROR_TICKS else band_width(math.log(1 / (1 - float(lower_ratio))) / math.log(1.0001))
    right = [(half_gap + up * i, half_gap + up * (i + 1)) for i in range(side_count)]
    left = [(-half_gap - down * (i + 1), -half_gap - down * i) for i in reversed(range(side_count))]
    return left + [(-half_gap, half_gap)] + right


# Share of TOTAL portfolio value each band holds. One entry per column of the shape sheet,
# in band order, low to high. Columns are meant to sum to 1; sheet rounding leaves some
# of them a little off (camel 1.0001, uniform 0.9996), which build_shape_config normalises away.
SHAPE_WEIGHTS: Dict[str, List[Decimal]] = {
    "triangle": [Decimal(w) for w in
                 ["0", "0.0088", "0.0263", "0.0439", "0.0614", "0.0789", "0.0965", "0.1140",
                  "0.1404",
                  "0.1140", "0.0965", "0.0789", "0.0614", "0.0439", "0.0263", "0.0088", "0"]],
    "gaussian": [Decimal(w) for w in
                 ["0.0017", "0.0048", "0.0119", "0.0258", "0.0486", "0.0796", "0.1131", "0.1396",
                  "0.1498",
                  "0.1396", "0.1131", "0.0796", "0.0486", "0.0258", "0.0119", "0.0048", "0.0017"]],
    "exponential": [Decimal(w) for w in
                    ["0.0096", "0.0140", "0.0204", "0.0296", "0.0431", "0.0627", "0.0912", "0.1328",
                     "0.1932",
                     "0.1328", "0.0912", "0.0627", "0.0431", "0.0296", "0.0204", "0.0140", "0.0096"]],
    "camel": [Decimal(w) for w in
              ["0.0343", "0.0383", "0.0467", "0.0608", "0.0781", "0.0924", "0.0939", "0.0391",
               "0.0329",
               "0.0391", "0.0939", "0.0924", "0.0781", "0.0608", "0.0467", "0.0383", "0.0343"]],
    # flat: every band holds the same 5.88% (1/17) of total value
    "uniform": [Decimal("0.0588")] * BAND_COUNT,
    # The inverted shapes put their trough at the money: the centre band is 0, so
    # build_shape_config drops it and liquidity starts one band out on either side.
    "inverted_triangle": [Decimal(w) for w in
                          ["0.110315", "0.096815", "0.083234", "0.069570", "0.055823", "0.041993",
                           "0.028080", "0.014082",
                           "0",
                           "0.014087", "0.028089", "0.042008", "0.055843", "0.069595", "0.083263",
                           "0.096850", "0.110354"]],
    "inverted_gaussian": [Decimal(w) for w in
                          ["0.096979", "0.094757", "0.089643", "0.079964", "0.064624", "0.044438",
                           "0.023057", "0.0063597",
                           "0",  # centre band, absent from the source sheet (its 16 values sum to 100)
                           "0.0063642", "0.023073", "0.044470", "0.064670", "0.080020", "0.089707",
                           "0.094825", "0.097048"]],
    # Nine-band version made by pairing adjacent weights in the 17-band inverted Gaussian and
    # averaging the tiny left/right rounding differences. The zero centre band is dropped at
    # placement time, leaving four active positions on each side of the current price.
    "inverted_gaussian_9": [Decimal(w) for w in
                            ["0.191805", "0.169667", "0.109101", "0.029427",
                             "0",
                             "0.029427", "0.109101", "0.169667", "0.191805"]],
    "inverted_exponential": [Decimal(w) for w in
                             ["0.080287", "0.078469", "0.075739", "0.071697", "0.065765", "0.057112",
                              "0.044542", "0.026332",
                              "0",
                              "0.026338", "0.044552", "0.057125", "0.065780", "0.071713", "0.075756",
                              "0.078487", "0.080306"]],
}


def build_shape_config(shape: str, upper_ratio: Decimal, lower_ratio: Decimal | str, tick_spacing: int,
                       half_gap: int | str) -> List[List]:
    """
    Turn one column of the shape sheet into the [lower tick offset, upper tick offset, share] rows
    the strategy places liquidity with.

    The sheet weights are shares of total value, and the portfolio is swapped to a 50/50 value split
    (which a tick symmetric range wants) before the bands are placed.

    The band straddling the current tick uses both tokens, so it takes its own share of each balance.
    Every other band consumes only one of the two tokens, so its share is rescaled against the side
    it sits on: the bands below the price must together use all the quote the centre band leaves, and
    the bands above must use all the base. For a column whose halves are exactly equal that works out
    to simply doubling the weight; columns that are only nearly symmetric (the inverted shapes, whose
    halves differ in the fourth decimal) would otherwise ask for more than 100% of one token and
    overdraw the balance on the last band.

    Zero weight bands are dropped: an empty position would earn nothing while still widening the
    range that check_rebalance treats as in range.
    """
    if shape not in SHAPE_WEIGHTS:
        raise ValueError(f"unknown shape {shape}, expected one of {list(SHAPE_WEIGHTS.keys())}")

    weights = SHAPE_WEIGHTS[shape]
    side_count = len(weights) // 2
    if half_gap == 0 and weights[side_count] != ZERO:
        raise ValueError(f"shape {shape} puts weight on the centre band, so half_gap 0 would leave it "
                         f"zero width; use an inverted shape or a positive gap")
    bands = build_gap_bands(upper_ratio, lower_ratio, tick_spacing, side_count, half_gap)

    total = sum(weights)
    if total <= ZERO:
        raise ValueError(f"shape {shape} weights sum to {total}")

    shares = [w / total for w in weights]
    straddles = [lower < 0 < upper for lower, upper in bands]

    centre_share = sum(s for s, straddle in zip(shares, straddles) if straddle)
    below_share = sum(s for s, (lower, upper) in zip(shares, bands) if upper <= 0)
    above_share = sum(s for s, (lower, upper) in zip(shares, bands) if lower >= 0)

    config: List[List] = []
    for (lower_offset, upper_offset), share, straddle in zip(bands, shares, straddles):
        if share == ZERO:
            continue
        if straddle:
            band_share = share
        else:
            side_share = below_share if upper_offset <= 0 else above_share
            band_share = share / side_share * (ONE - centre_share)
        config.append([lower_offset, upper_offset, band_share])

    return config


class RemixDaoDcaWeekStratStrategy(BaseRemixDaoStrategy):

    def __init__(self, _utils: RemixDaoUtils, _params: TestParams, _gp: GlobalParams,
                 usdc_prices: pd.Series | None = None, shape: str = "inverted_gaussian_9",
                 upper_ratio: Decimal = Decimal("0.50"), lower_ratio: Decimal | str = Decimal("0.50"),
                 half_gap: int | str = 0, eth_share: Decimal | str | None = None,
                 daily_ema: pd.DataFrame | None = None, deploy: str = DEPLOY_FULL):
        super().__init__(_utils, _params, _gp)
        # spec sheet 2.3: DEPLOY_SIGNAL sizes every (re)build to F x equity and parks the rest in quote
        self.signal_deploy = deploy == DEPLOY_SIGNAL
        if self.signal_deploy and daily_ema is None:
            raise ValueError("deploy=signal needs the daily_ema frame (it carries F)")
        if self.signal_deploy and eth_share is None:
            raise ValueError("deploy=signal needs an explicit eth_share; sgeo sizes by range geometry")
        self.deployed_at_build = ONE     # F used by the latest (re)build
        self.reserve_quote = ZERO        # quote parked outside the bands by the latest (re)build
        self.reserve_base = ZERO         # spot base held outside the bands by the latest (re)build (SPOT_SLEEVE)
        self.sleeve_high: float | None = None   # SLEEVE_STOP: highest daily close since the sleeve was bought
        self.sleeve_stopped = False
        self.stop_low_f: Decimal | None = None  # lowest F since the stop; a rise above it re-arms
        self.sleeve_stops = 0
        self.total_interest = ZERO       # CASH_APR: lending interest earned on idle quote (EXP-052: stable LP income)
        self.stable_held = ZERO          # EXP-052: reserve in the stable LP at the last accrual
        self.refill_orders = 0           # REFILL_ORDER: F increases placed as quote-only range orders
        self.ladder_span: tuple[int, int] | None = None   # (lowest, highest) tick of the last built ladder
        self.half_now = False            # HALF_WHEN_ACCEL: the latest build placed only the quote side
        self.half_builds = 0
        self.force_rebuild = False       # set by follow_work to push rescale_work past its range check
        self.follow_rebuild_count = 0
        self.resize_count = 0            # EXP-055: follow events handled by resize_work
        self.swapless_exits = 0          # EXP-057: range-exit rebuilds placed without a swap
        self.macro_next = 0              # EXP-059: index of the next scheduled release
        self.tranche_adds = 0            # EXP-061: follow events handled by tranche_add
        self.tranches = None             # EXP-063: per-account sub-ladders
        self.tranche_rebuilds = 0
        self.cppi_hwm = ZERO             # EXP-064
        self.cppi_min_m = 1.0
        self.weekly_recentres = 0        # EXP-065
        self.skipped_exits = 0           # EXP-074 / EXP-075
        self.tranche_io = (0, 0)
        self.fee_log: List[dict] = []    # daily: collected fees (quote) + pending fees still in the positions
        # spec sheet s: base (ETH) share of total value before the bands are placed. None keeps the
        # original behaviour, where calculate_swap_amount lets the full-range geometry pick the ratio.
        # EMA_SHARE switches 0.7 / 0.5 on the last daily close vs EMA100 (needs daily_ema).
        self.eth_share = eth_share
        self.daily_ema = daily_ema
        if eth_share == EMA_SHARE and daily_ema is None:
            raise ValueError("eth_share=EMA_SHARE needs the daily_ema frame")
        self.last_share: Decimal | None = None      # share used by the latest (re)build, for the log
        self.share_picks: Dict[str, int] = {}       # how often each share was picked

        self.last_rescale_tick = 0
        self.total_base_fee = ZERO
        self.total_quote_fee = ZERO
        self.export_actions = []
        self.lock_until_time = None
        self.last_price = ZERO
        self.balance_data = {}
        self.tick_spreads = pd.Series([])
        self.total_fee = ZERO
        self.final_total_net_value = ZERO
        self.final_lp_net_value = ZERO
        self.total_base_swap_fee = ZERO
        self.total_quote_swap_fee = ZERO
        self.total_swap_fee = ZERO
        # EXP-014 hedge ledger
        self.hedge_size = ZERO        # base units short
        self.hedge_entry = ZERO       # mark of the open size (settled daily)
        self.hedge_pnl = ZERO         # settled price PnL of the short
        self.hedge_fees = ZERO
        self.hedge_funding = ZERO
        self.hedge_trades = 0
        self.hedge_max_ratio = 0.0    # max short notional / equity
        self.hedge_min_cash = None    # lowest quote balance after a hedge debit (negative = margin call territory)
        self.bear_short_days = 0      # EXP-018: days the bear short was on
        # EXP-016 pause state
        self.price_hist: deque = deque(maxlen=PAUSE_WINDOW + 1)
        self.paused_until: datetime | None = None
        self.paused_bands: list = []   # (PositionInfo, base, quote) that came out of the pulled ladder
        self.build_tick: int | None = None
        self.build_price: Decimal | None = None   # EXP-023: base price at the last build
        self.recentre_count = 0                   # EXP-023: rebuilds triggered by the early upside recentre
        self.pauses = 0
        self.pause_minutes = 0
        # self.pa_upper: List[PriceActionLog] = []
        # self.pa_lower: List[PriceActionLog] = []
        self.total_invested: Decimal = ZERO
        self.total_invested_usdc: Decimal = ZERO
        self.last_check_price: Decimal = ZERO
        self.usdc_prices: pd.Series | None = usdc_prices
        self.total_fee_usd: Decimal = ZERO
        self.total_net_value_usd: Decimal = ZERO
        self.total_lp_value_usd: Decimal = ZERO
        self.init_quote_usd_price: Decimal = ZERO
        self.final_quote_usd_price: Decimal = ZERO
        self.total_minutes: int = 0
        self.total_in_range_minutes: int = 0
        self.total_in_range_and_in_lock_minutes: int = 0
        self.total_out_of_range_and_in_lock_minutes: int = 0
        self.total_lock_count: int = 0
        self.upper_rescale_count: int = 0
        self.lower_rescale_count: int = 0
        # self.total_pause_minutes: int = 0
        self.last_rescale_side: int = 0  # 1 all base, -1 all quote, 0 initial
        self.invest_token0: Decimal = ZERO
        self.invest_token1: Decimal = ZERO
        self.idle_base: Decimal = ZERO
        self.idle_quote: Decimal = ZERO
        self.leftover_base: Decimal = ZERO
        self.leftover_quote: Decimal = ZERO
        self.out_of_fund_date: datetime | None = None
        self.starting_tick: int | None = None
        self.rescale_left_too_much_count: int = 0
        self.positions: List[PositionInfo] = []
        # [lower tick offset, upper tick offset, share of the balance to place]
        self.shape = shape
        self.upper_ratio, self.lower_ratio, self.half_gap = upper_ratio, lower_ratio, half_gap
        quote_is_0, spacing = _utils.lp_market.pool_info.is_token0_quote, _utils.params.tick_spacing

        def config(up: Decimal, lo: Decimal | str) -> List[List]:
            # build_gap_bands reaches +upper_ratio on positive tick offsets and -lower_ratio on negative ones.
            # When token0 is the quote (USDC/WETH mainnet) a higher tick is a LOWER base price, so the positive
            # side must reach "-lower_ratio" and the negative side "+upper_ratio". Re-express both in the other
            # side's formula: 1+u' = 1/(1-l) and 1/(1-l') = 1+u. Swapping the ratios alone is a no-op when they
            # are equal, which is why the first dnprice rerun still came out as +102%/-34%. MIRROR_TICKS is symmetric.
            if lo != MIRROR_TICKS and quote_is_0:
                up, lo = lo / (ONE - lo), up / (ONE + up)
            return build_shape_config(shape, up, lo, spacing, half_gap)

        # EXP-013: one config per trend state, "flat" is v6's; resolve_skew picks the state at every build.
        self.shape_configs: Dict[str, List[List]] = {"flat": config(upper_ratio, lower_ratio)}
        if SKEW > ZERO:
            if lower_ratio == MIRROR_TICKS:
                raise ValueError("SKEW needs a percentage lower_ratio")
            self.shape_configs["up"] = config(upper_ratio + SKEW, lower_ratio - SKEW)
            self.shape_configs["down"] = config(upper_ratio - SKEW, lower_ratio + SKEW)
        self._config = config
        self.exit_streak = 0   # EXP-044: consecutive daily checks with the price outside the ladder
        self.skew_state = "flat"
        self.skew_builds = {"up": 0, "down": 0}
        self.width_builds: Dict[str, int] = {}   # EXP-030: builds per half-width

    @property
    def shape_config(self) -> List[List]:
        """[lower tick offset, upper tick offset, share] rows of the ladder the current skew state places."""
        return self.shape_configs[self.skew_state]

    def resolve_skew(self, timestamp: datetime) -> None:
        """EXP-013: pick the reaches of the ladder built at `timestamp` from the s rule's trend sign (last completed
        daily close vs EMA100); the state then stays for the life of that ladder."""
        if WIDTH_VOL and self.daily_ema is not None:   # EXP-030
            try:
                sigma = float(daily_row_for(self.daily_ema, timestamp)[1]["sigma"])
            except KeyError:
                sigma = float("nan")
            width = 0.20 if math.isnan(sigma) else min(max(WIDTH_VOL_K * sigma * math.sqrt(WIDTH_VOL_DAYS), WIDTH_VOL_MIN),
                                                       WIDTH_VOL_MAX)
            width = round(round(width / WIDTH_VOL_GRID) * WIDTH_VOL_GRID, 4)
            self.skew_state = f"w{width}"
            if self.skew_state not in self.shape_configs:
                self.shape_configs[self.skew_state] = self._config(Decimal(str(width)), Decimal(str(width)))
            self.width_builds[self.skew_state] = self.width_builds.get(self.skew_state, 0) + 1
            return
        if SKEW <= ZERO or self.daily_ema is None:
            self.skew_state = "flat"
            return
        try:
            _, day, close, ema = ema_share_for(self.daily_ema, timestamp)
        except KeyError:
            self.skew_state = "flat"
            return
        self.skew_state = "up" if close > ema else "down"
        self.skew_builds[self.skew_state] += 1
        print(f"{timestamp.strftime('%Y-%m-%d %H:%M')} skew {self.skew_state} on {day.date()} "
              f"({'+' if self.skew_state == 'up' else '-'}{float(SKEW * HUNDRED):g} pts)")


    def initialize(self):

        new_trigger = AtTimeTrigger(time=self.params.cal_start_datetime, do=self.first_lp)
        self.triggers.append(new_trigger)

        if self.usdc_prices is not None:
            self.add_column(self.utils.market_key, "usdc_price", self.usdc_prices)

        self.triggers.append(PeriodTrigger(time_delta=timedelta(hours=1) if EXIT_CHECK_HOURLY else self.params.rescale_frequency.value,
                                           do=self.rescale_work))   # EXP-056: hourly range-exit check
        if CASH_APR is not None:
            self.triggers.append(PeriodTrigger(time_delta=timedelta(days=1), do=self.accrue_cash))
        if ACCOUNT_TRANCHES:   # EXP-063
            self.triggers.append(PeriodTrigger(time_delta=timedelta(days=1), do=self.tranche_work))
        if STABLE_LP is not None:   # EXP-052
            self.triggers.append(PeriodTrigger(time_delta=timedelta(days=1), do=self.accrue_stable))
        if self.signal_deploy:  # spec sheet 2.3: judged once a day on the previous close
            self.triggers.append(PeriodTrigger(time_delta=timedelta(days=1), do=self.follow_work))
        self.triggers.append(PeriodTrigger(time_delta=timedelta(days=1), do=self.log_fees))
        if perp_enabled():   # EXP-014 / EXP-018: after every 00:00 build; funding at 00:00 / 08:00 / 16:00
            self.broker.allow_negative_balance = True   # a settlement past the margin shows as negative cash (reported)
            self.triggers.append(PeriodTrigger(time_delta=timedelta(days=1), do=self.hedge_rebalance))
            self.triggers.append(PeriodTrigger(time_delta=timedelta(hours=8), do=self.hedge_funding_work))
        dt = datetime(self.params.data_end_date.year, self.params.data_end_date.month, self.params.data_end_date.day,
                      23, 59, 0)
        end_trigger = AtTimeTrigger(time=dt, do=self.calculate_final_result)
        self.triggers.append(end_trigger)

        self.total_invested = self.broker.get_token_balance(self.broker.quote_token)
        pass


    def calculate_range(self, lp_market: UniLpMarketV2, current_tick: int, lower_tick_offset: int, upper_tick_offset: int) -> tuple[Decimal, Decimal, int, int]:
        """
        Place a band at [current tick + lower_tick_offset, current tick + upper_tick_offset], both
        snapped to tick spacing. Adjacent bands share a boundary offset, so they stay contiguous
        even when tick spacing does not divide the offsets evenly.
        """
        tick_spacing = self.utils.params.tick_spacing
        center_tick = self.utils.round_tick(current_tick, tick_spacing)

        lower_tick = center_tick + round(lower_tick_offset / tick_spacing) * tick_spacing
        upper_tick = center_tick + round(upper_tick_offset / tick_spacing) * tick_spacing

        lower_price = lp_market.tick_to_price(lower_tick)
        upper_price = lp_market.tick_to_price(upper_tick)
        

        if lower_price > upper_price:
            lower_price, upper_price = upper_price, lower_price

        return lower_price, upper_price, lower_tick, upper_tick

    def resolve_share(self, timestamp: datetime) -> Decimal | None:
        """The ETH share this (re)build uses; EMA_SHARE is judged on the last completed daily close."""
        if self.eth_share == EMA_SHARE:
            try:
                share, day, close, ema = ema_share_for(self.daily_ema, timestamp)
                print(f"{timestamp.strftime('%Y-%m-%d %H:%M')} ema{EMA_SPAN} on {day.date()}: close {close:.0f} "
                      f"{'>' if close > ema else '<='} ema {ema:.0f} -> s={share}")
            except KeyError:
                share = SHARE_BELOW_EMA  # ponytail: no daily row (should not happen with warm-up) -> the safe 50%
                print(f"{timestamp.strftime('%Y-%m-%d %H:%M')} no daily close for ema{EMA_SPAN}, using s={share}")
        else:
            share = self.eth_share
        self.last_share = share
        self.share_picks[share_label(share)] = self.share_picks.get(share_label(share), 0) + 1
        return share

    def pre_placement_swap(self, lp_market: UniLpMarketV2, current_tick: int, lower_boundary: int,
                           upper_boundary: int, base: Decimal, quote: Decimal,
                           timestamp: datetime) -> tuple[Decimal, Decimal]:
        """(base_to_swap, quote_to_swap) before placing the bands: spec sheet s when eth_share is set,
        otherwise whatever a single position over the whole range wants."""
        share = self.resolve_share(timestamp)
        price = lp_market.tick_to_price(current_tick)
        fraction = target_fraction_for(self.daily_ema, timestamp) if self.signal_deploy else ONE
        self.deployed_at_build = fraction
        if HEDGE > ZERO and share is not None:   # EXP-014: the short's initial margin stays in quote, outside the ladder
            fraction = fraction * (ONE - HEDGE * share / HEDGE_LEVERAGE)
        sleeve = ZERO if self.sleeve_stopped else SPOT_SLEEVE
        if HALF_WHEN_ACCEL:
            self.half_now = ema_accelerating(self.daily_ema, timestamp)
            self.half_builds += self.half_now
        # a stopped sleeve's share stays in quote with the reserve
        self.reserve_quote = (ONE - fraction + (SPOT_SLEEVE - sleeve) * fraction) * (base * price + quote)
        self.reserve_base = sleeve * fraction * (base * price + quote) / price
        if SLEEVE_STOP is not None and self.reserve_base > ZERO and not (SLEEVE_HIGH_KEEP and self.sleeve_high is not None):
            self.sleeve_high = float(price)
        elif SLEEVE_HIGH_KEEP and self.reserve_base <= ZERO and not self.sleeve_stopped:
            self.sleeve_high = None   # F went to 0: the sleeve is gone, its next purchase starts a new high
        if share is None:  # sgeo, only reachable with fraction 1 (constructor check)
            return self.calculate_swap_amount(current_tick, lower_boundary, upper_boundary, base, quote)
        # bands get share x F of total value in base and (1 - share) x F in quote; the reserve stays quote.
        # With a spot sleeve k the bands get (1 - k) x F and the sleeve k x F, all of it base.
        return swap_to_value_share(base, quote, price, fraction * (sleeve + share * (ONE - SPOT_SLEEVE)))

    def log_fees(self, row_data: Snapshot):
        """Daily fee snapshot for the monthly income breakdown: collected so far, plus fees accrued in the
        open positions but not collected yet (both in quote)."""
        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]
        price = row_data.prices[self.gp.base_token.name]
        pending0 = sum((pos.pending_amount0 for pos in lp_market.positions.values()), ZERO)
        pending1 = sum((pos.pending_amount1 for pos in lp_market.positions.values()), ZERO)
        pending = pending0 + pending1 * price if lp_market.pool_info.is_token0_quote else pending1 + pending0 * price
        self.fee_log.append({"date": row_data.timestamp.date(), "price": float(price),
                             "collected_quote": float(self.total_base_fee * price + self.total_quote_fee),
                             "pending_quote": float(pending),
                             "lp_value": float(lp_market.get_market_balance().net_value) if lp_market.positions else 0.0})

    def follow_work(self, row_data: Snapshot):
        """Spec sheet 2.3 rule 3: rebuild to F x equity when the book drifted >= FOLLOW_THRESHOLD from F."""
        if ACCOUNT_TRANCHES:   # EXP-063
            return
        if self.starting_tick is None or self.out_of_fund_date is not None or self.paused_until is not None:
            return
        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]
        price = row_data.prices[self.gp.base_token.name]
        lp_value = lp_market.get_market_balance().net_value if len(lp_market.positions) > 0 else ZERO
        free_base = lp_market.broker.get_token_balance(self.gp.base_token) - self.fee_reserve_base()
        free_quote = lp_market.broker.get_token_balance(self.gp.quote_token) - self.fee_reserve_quote()
        equity = lp_value + free_base * price + free_quote
        if equity <= ZERO:
            return
        # with a spot sleeve the free base is deployed capital too
        current = (lp_value + (free_base * price if (SPOT_SLEEVE > ZERO or HALF_LADDER or HALF_WHEN_ACCEL) else ZERO)) / equity
        target = target_fraction_for(self.daily_ema, row_data.timestamp)
        if CPPI_FLOOR is not None:   # EXP-064
            total = lp_value + self.broker.get_token_balance(self.gp.base_token) * price + self.broker.get_token_balance(self.gp.quote_token)
            self.cppi_hwm = max(self.cppi_hwm, total)
            m = (total / self.cppi_hwm - Decimal(str(CPPI_FLOOR))) / (ONE - Decimal(str(CPPI_FLOOR)))
            target = target * min(ONE, max(ZERO, m))
            self.cppi_min_m = min(self.cppi_min_m, float(min(ONE, max(ZERO, m))))
        up = None
        if WEEKLY_RECENTRE_UP or RESIZE_BELOW_EMA:   # EXP-071 / EXP-072: v6's EMA100 state on the last completed day
            _, _row = daily_row_for(self.daily_ema, row_data.timestamp)
            up = _row["close"] > _row["ema"]
        if (WEEKLY_RECENTRE or (WEEKLY_RECENTRE_UP and up)) and row_data.timestamp.weekday() == 6 \
                and current > FULL_TOLERANCE and target > ZERO:   # EXP-065 / EXP-071
            self.weekly_recentres += 1
            self.force_rebuild = True
            try:
                self.rescale_work(row_data)
            finally:
                self.force_rebuild = False
            return
        if HEDGE > ZERO and self.eth_share is not None:   # EXP-014: the build keeps the short's margin out of the ladder
            share_now = ema_share_for(self.daily_ema, row_data.timestamp)[0] if self.eth_share == EMA_SHARE else self.eth_share
            target = target * (ONE - HEDGE * share_now / HEDGE_LEVERAGE)
        if SLEEVE_STOP is not None:
            self.sleeve_stop_work(row_data, target, free_base)
            if self.sleeve_stopped:
                target = target * (ONE - SPOT_SLEEVE)   # the ladder half only; the sleeve's share stays quote
                current = lp_value / equity
        due = (abs(target - current) >= FOLLOW_THRESHOLD
               or (target == ZERO and current > FULL_TOLERANCE)
               or (target >= ONE - FULL_TOLERANCE and current < ONE - FULL_TOLERANCE))
        if not due:
            return
        if REFILL_ORDER and target > current and self.place_refill_order(row_data, (target - current) * equity):
            self.deployed_at_build = target
            return
        if (TRANCHE_ADD or FOLLOW_ASYM) and self.positions and current > FULL_TOLERANCE and ZERO < target < current:
            self.resize_work(row_data, target, current)   # EXP-061 / EXP-062: shrink in place
            return
        if TRANCHE_ADD and self.positions and current > FULL_TOLERANCE and target > current:   # EXP-061: add a tranche
            self.tranche_add(row_data, target, current, equity)
            return
        if RESIZE_BELOW_EMA and up is not None and not up and self.positions and current > FULL_TOLERANCE and target > ZERO and \
                (abs(target - current) >= FOLLOW_THRESHOLD):   # EXP-072
            self.resize_work(row_data, target, current)
            return
        if RESIZE_IN_PLACE and self.positions and current > FULL_TOLERANCE and target > ZERO:   # EXP-055
            self.resize_work(row_data, target, current)
            return
        if RESIZE_NEAR_CENTRE and self.positions and current > FULL_TOLERANCE and target > ZERO \
                and self.build_tick is not None:   # EXP-058: resize only while the price is near the build centre
            lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]
            inner = (self.shape_config[-1][1] - self.shape_config[0][0]) / 4   # half of each side's reach
            if abs(lp_market.price_to_raw_tick(price) - self.build_tick) < inner:
                self.resize_work(row_data, target, current)
                return
        print(f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} follow F: target {float(target):.4f} "
              f"current {float(current):.4f} -> rebuild")
        self.follow_rebuild_count += 1
        self.force_rebuild = True
        try:
            self.rescale_work(row_data)
        finally:
            self.force_rebuild = False

    def resize_work(self, row_data: Snapshot, target: Decimal, current: Decimal) -> None:
        """EXP-055: scale every band's liquidity by target / current at its own ticks (see RESIZE_IN_PLACE)."""
        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]
        k = target / current
        price = row_data.prices[self.gp.base_token.name]
        base_is_0 = self.gp.base_token.name == self.gp.token0.name
        bands = []
        for pos in list(self.positions):
            self.collect_fee_as_quote(lp_market, pos)
            if pos not in lp_market.positions:
                continue
            a0, a1 = lp_market.get_position_amount(pos)
            bands.append((pos, a0 if base_is_0 else a1, a1 if base_is_0 else a0))
        self.positions = [b[0] for b in bands]
        free_base = lambda: self.broker.get_token_balance(self.gp.base_token) - self.fee_reserve_base()
        free_quote = lambda: self.broker.get_token_balance(self.gp.quote_token) - self.fee_reserve_quote()
        if k < ONE:
            for pos, _, _ in bands:
                part = int(Decimal(lp_market.positions[pos].liquidity) * (ONE - k))
                if part > 0:
                    lp_market.remove_liquidity(pos, liquidity=part, collect=True, remove_dry_pool=False)
            if free_base() > ZERO:
                _, _, fee_b, _ = self.execute_swap(lp_market, free_base(), ZERO)
                self.total_base_swap_fee += fee_b if fee_b is not None else ZERO
        else:
            need = sum((b for _, b, _ in bands), ZERO) * (k - ONE)
            buy = need - free_base()
            if buy > ZERO:
                pay = min(free_quote(), buy * price / (ONE - Decimal(lp_market.pool_info.fee_rate)))
                _, _, _, fee_q = self.execute_swap(lp_market, ZERO, pay)
                self.total_quote_swap_fee += fee_q if fee_q is not None else ZERO
            tick = lp_market.price_to_raw_tick(price)
            for pos, b, q in bands:
                base_amt = max(ZERO, min(b * (k - ONE), free_base()))
                quote_amt = max(ZERO, min(q * (k - ONE), free_quote()))
                if base_amt > ZERO or quote_amt > ZERO:
                    lp_market.add_liquidity_by_tick(pos[0], pos[1], base_amt, quote_amt, tick=tick)
        self.deployed_at_build = target
        self.resize_count += 1
        print(f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} resize in place x{float(k):.3f} "
              f"(F {float(current):.3f} -> {float(target):.3f})")

    def tranche_add(self, row_data: Snapshot, target: Decimal, current: Decimal, equity: Decimal) -> None:
        """EXP-061: place (target - current) x equity as a new ladder centred on today's price (see TRANCHE_ADD)."""
        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]
        price = row_data.prices[self.gp.base_token.name]
        share = self.resolve_share(row_data.timestamp)
        add = (target - current) * equity
        free_base = self.broker.get_token_balance(self.gp.base_token) - self.fee_reserve_base()
        want_base = share * add / price
        if want_base > free_base:
            pay = (want_base - free_base) * price / (ONE - Decimal(lp_market.pool_info.fee_rate))
            _, _, _, fee_q = self.execute_swap(lp_market, ZERO, pay)
            self.total_quote_swap_fee += fee_q if fee_q is not None else ZERO
        base_for = min(want_base, self.broker.get_token_balance(self.gp.base_token) - self.fee_reserve_base())
        quote_for = (ONE - share) * add
        tick = lp_market.price_to_raw_tick(price)
        new = []
        for config in self.ladder_configs():
            _, _, lower_tick, upper_tick = self.calculate_range(lp_market, tick, config[0], config[1])
            base_amt, quote_amt = self.band_amounts(base_for, quote_for, config[2])
            pos, bu, qu, _ = lp_market.add_liquidity_by_tick(lower_tick, upper_tick, base_amt, quote_amt, tick=tick)
            if bu == ZERO and qu == ZERO:
                if pos not in self.positions:
                    lp_market.positions.pop(pos, None)
                continue
            new.append(pos)
        self.positions = sorted(set(self.positions) | set(new), key=lambda p: (p[0], p[1]))
        self.deployed_at_build = target
        self.reserve_quote = max(ZERO, (ONE - target) * equity)
        self.tranche_adds += 1
        print(f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} tranche add {float(add):,.0f} at s={share} "
              f"(F {float(current):.3f} -> {float(target):.3f}), {len(self.positions)} bands")

    def tranche_work(self, row_data: Snapshot) -> None:
        """EXP-063: rebuild the sub-ladders whose virtual account changed state (see ACCOUNT_TRANCHES)."""
        if self.starting_tick is None:
            return
        _, row = daily_row_for(self.daily_ema, row_data.timestamp)
        n = len(EMA_SPANS)
        if self.tranches is None:
            self.tranches = [{"bands": [], "dep": 0.0, "ctr": float("nan")} for _ in range(n)]
        want = [(float(row[f"dep{j}"]), float(row[f"ctr{j}"])) for j in range(n)]
        same = lambda t, w: t["dep"] == w[0] and (w[0] == 0 or t["ctr"] == w[1])
        changed = [j for j in range(n) if not same(self.tranches[j], want[j])]
        self.tranche_io = (0, 0)
        if not changed:
            return
        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]
        price = row_data.prices[self.gp.base_token.name]
        free_b = lambda: self.broker.get_token_balance(self.gp.base_token) - self.fee_reserve_base()
        free_q = lambda: self.broker.get_token_balance(self.gp.quote_token) - self.fee_reserve_quote()
        lp_value = lp_market.get_market_balance().net_value if lp_market.positions else ZERO
        equity = lp_value + free_b() * price + free_q()
        removed = 0
        for j in changed:   # burn the changed sub-ladders (their own liquidity only)
            for pos, liq in self.tranches[j]["bands"]:
                if pos not in lp_market.positions:
                    continue
                self.collect_fee_as_quote(lp_market, pos)
                if pos not in lp_market.positions:
                    continue
                part = min(int(liq), int(lp_market.positions[pos].liquidity))
                if part > 0:
                    lp_market.remove_liquidity(pos, liquidity=part, collect=True)
                    removed += 1
            self.tranches[j]["bands"] = []
        share = self.resolve_share(row_data.timestamp)
        values = {j: Decimal(str(want[j][0])) / Decimal(n) * equity for j in changed if want[j][0] > 0}
        need_b = sum((share * v / price for v in values.values()), ZERO)
        fee = Decimal(lp_market.pool_info.fee_rate)
        if free_b() > need_b:   # one net swap for all rebuilt sub-ladders (surplus base -> quote: the reserve stays quote)
            _, _, fb, _ = self.execute_swap(lp_market, free_b() - need_b, ZERO)
            self.total_base_swap_fee += fb if fb is not None else ZERO
        elif need_b > free_b():
            pay = min(free_q(), (need_b - free_b()) * price / (ONE - fee))
            if pay > ZERO:
                _, _, _, fq = self.execute_swap(lp_market, ZERO, pay)
                self.total_quote_swap_fee += fq if fq is not None else ZERO
        tick = lp_market.price_to_raw_tick(price)
        k = min(ONE, free_b() / need_b) if need_b > ZERO else ONE
        added = 0
        for j in changed:
            self.tranches[j]["dep"], self.tranches[j]["ctr"] = want[j]
            if j not in values:
                continue
            b_j = share * values[j] / price * k
            q_j = min((ONE - share) * values[j], max(ZERO, free_q()))
            for config in self.ladder_configs():
                _, _, lower_tick, upper_tick = self.calculate_range(lp_market, tick, config[0], config[1])
                base_amt, quote_amt = self.band_amounts(b_j, q_j, config[2])
                if base_amt <= ZERO and quote_amt <= ZERO:
                    continue
                pos = PositionInfo(lower_tick, upper_tick)
                before = lp_market.positions[pos].liquidity if pos in lp_market.positions else 0
                pos, bu, qu, _ = lp_market.add_liquidity_by_tick(lower_tick, upper_tick, base_amt, quote_amt, tick=tick)
                if bu == ZERO and qu == ZERO:
                    if before == 0:
                        lp_market.positions.pop(pos, None)
                    continue
                self.tranches[j]["bands"].append((pos, lp_market.positions[pos].liquidity - before))
                added += 1
        self.positions = sorted({p for t in self.tranches for p, _ in t["bands"] if p in lp_market.positions},
                                key=lambda p: (p[0], p[1]))
        self.deployed_at_build = Decimal(str(sum(w[0] for w in want) / n))
        self.tranche_rebuilds += len(changed)
        self.tranche_io = (removed, added)
        print(f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} sub-ladders {changed} rebuilt, deployed "
              f"{[w[0] for w in want]}, {len(self.positions)} bands")

    def ladder_configs(self) -> List[List]:
        """The bands a (re)build places: all of them, or with HALF_LADDER only the quote side (a range above the
        current tick holds token0, below it token1)."""
        if not (HALF_LADDER or (HALF_WHEN_ACCEL and self.half_now)):
            return self.shape_config
        quote_is_0 = self.utils.lp_market.pool_info.is_token0_quote
        return [c for c in self.shape_config if (c[1] > 0 if quote_is_0 else c[0] < 0)]

    def set_ladder_span(self, lp_market: UniLpMarketV2, current_tick: int):
        """Tick span of the ladder v6 builds here (None when nothing is deployed); exits are judged on it when the
        placed positions do not cover the price (REFILL_ORDER orders, HALF_LADDER)."""
        if not self.positions:
            self.ladder_span = None
            return
        _, _, lo, hi = self.calculate_range(lp_market, current_tick, self.shape_config[0][0], self.shape_config[-1][1])
        self.ladder_span = (lo, hi)

    def place_refill_order(self, row_data: Snapshot, amount: Decimal) -> bool:
        """EXP-005: put `amount` of quote into one position spanning the ladder's quote side (current price down to
        -lower_ratio): it holds only quote now and turns into base only if the price comes down into it."""
        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]
        free_quote = self.broker.get_token_balance(self.gp.quote_token) - self.fee_reserve_quote()
        amount = min(amount, free_quote)
        if amount <= ZERO:
            return False
        current_tick = self.utils.get_raw_tick(row_data)
        spacing = self.utils.params.tick_spacing
        # a range above the current tick holds only token0, below only token1
        if lp_market.pool_info.is_token0_quote:
            lo, hi = 2 * spacing, self.shape_config[-1][1]
        else:
            lo, hi = self.shape_config[0][0], -2 * spacing
        _, _, lower_tick, upper_tick = self.calculate_range(lp_market, current_tick, lo, hi)
        position, base_used, quote_used, _ = lp_market.add_liquidity_by_tick(lower_tick, upper_tick, ZERO, amount,
                                                                             tick=current_tick)
        if quote_used == ZERO:
            lp_market.positions.pop(position, None)
            return False
        if position not in self.positions:  # an order on the same ticks as an existing position merges into it
            self.positions.append(position)
            self.positions.sort(key=lambda p: (p[0], p[1]))
        self.refill_orders += 1
        if self.ladder_span is None:  # no ladder (F was 0): exits are judged on the ladder v6 would have built here
            _, _, span_lo, span_hi = self.calculate_range(lp_market, current_tick, self.shape_config[0][0],
                                                          self.shape_config[-1][1])
            self.ladder_span = (span_lo, span_hi)
        print(f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} refill order: {float(quote_used):,.2f} quote over "
              f"ticks {lower_tick}..{upper_tick} (current {current_tick}), base used {float(base_used)}")
        return True

    def accrue_cash(self, row_data: Snapshot):
        """EXP-004: one day of lending interest on every quote token held outside the ladder (reserve, collected
        fees, earlier interest), at the previous day's supply APR. Booked as income like the fees: not deployed."""
        if self.starting_tick is None:
            return
        day = pd.Timestamp(row_data.timestamp - timedelta(days=1)).normalize()
        apr = CASH_APR.asof(day)
        if pd.isna(apr) or apr <= 0:
            return
        held = self.broker.get_token_balance(self.gp.quote_token)
        interest = held * Decimal(str(apr)) / Decimal(365)
        if interest > ZERO:
            self.broker.add_to_balance(self.gp.quote_token, interest)
            self.total_quote_fee += interest
            self.total_interest += interest

    def accrue_stable(self, row_data: Snapshot):
        """EXP-052: one day of the USDC/USDT LP's net return on the reserve (quote held outside the ladder minus the
        paid-out fees and income), at the previous day's return; a change of the reserve since the last day pays
        STABLE_SWITCH_FEE on half the moved amount. Booked as income like the fees: not deployed."""
        if self.starting_tick is None:
            return
        day = pd.Timestamp(row_data.timestamp - timedelta(days=1)).normalize()
        held = max(ZERO, self.broker.get_token_balance(self.gp.quote_token) - self.total_quote_fee)
        moved = abs(held - self.stable_held)
        self.stable_held = held
        ret = STABLE_LP.get(day, np.nan)
        income = (held * Decimal(str(ret)) if not pd.isna(ret) else ZERO) - moved * STABLE_SWITCH_FEE / 2
        self.broker.add_to_balance(self.gp.quote_token, income)
        self.total_quote_fee += income
        self.total_interest += income

    # ---- EXP-016: toxicity pause ----
    def pause_work(self, row_data: Snapshot) -> None:
        """Every minute: track the PAUSE_WINDOW-minute return; pull the ladder on a spike, put it back after the pause."""
        ts = row_data.timestamp
        price = float(row_data.prices[self.gp.base_token.name])
        self.price_hist.append(price)
        if self.paused_until is not None:
            self.pause_minutes += 1
            if ts >= self.paused_until:
                self.resume_ladder(row_data)
            return
        if len(self.price_hist) <= PAUSE_WINDOW or not self.positions or self.starting_tick is None:
            return
        if abs(math.log(price / self.price_hist[0])) < PAUSE_RET:
            return
        end = datetime(self.params.data_end_date.year, self.params.data_end_date.month, self.params.data_end_date.day, 23, 59)
        if ts + timedelta(minutes=PAUSE_MINUTES) > end:
            return
        self.pause_ladder(row_data)

    def macro_work(self, row_data: Snapshot) -> None:
        """EXP-059: every minute, pull the ladder MACRO_BEFORE ahead of a scheduled release and re-add it MACRO_AFTER later."""
        ts = row_data.timestamp
        if self.paused_until is not None:
            self.pause_minutes += 1
            if ts >= self.paused_until:
                self.restore_ladder(row_data) if MACRO_RESTORE else self.resume_ladder(row_data)
            return
        while self.macro_next < len(MACRO_EVENTS) and MACRO_EVENTS[self.macro_next] + MACRO_AFTER <= ts:
            self.macro_next += 1
        if self.macro_next >= len(MACRO_EVENTS) or not self.positions or self.starting_tick is None:
            return
        event = MACRO_EVENTS[self.macro_next]
        if event - MACRO_BEFORE <= ts < event + MACRO_AFTER:
            end = datetime(self.params.data_end_date.year, self.params.data_end_date.month, self.params.data_end_date.day, 23, 59)
            if event + MACRO_AFTER > end:
                return
            self.price_hist.clear()   # pause_ladder logs a move from price_hist[0]: log 0 here
            self.price_hist.append(float(row_data.prices[self.gp.base_token.name]))
            self.pause_ladder(row_data)
            self.paused_until = event + MACRO_AFTER
            self.macro_next += 1

    def pause_ladder(self, row_data: Snapshot) -> None:
        """Remove every band (fees collected as in a rebuild), remember the ranges and the tokens that came out."""
        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]
        bands = []
        self.paused_liq = []   # EXP-060: (band, liquidity) before the pull
        for position_info in self.positions:
            self.collect_fee_as_quote(lp_market, position_info)
            if position_info not in lp_market.positions:
                continue
            self.paused_liq.append((position_info, lp_market.positions[position_info].liquidity))
            base, quote = lp_market.remove_liquidity(position_info, collect=True)
            bands.append((position_info, base, quote))
        self.paused_bands = bands
        self.positions = []
        self.paused_until = row_data.timestamp + timedelta(minutes=PAUSE_MINUTES)
        self.pauses += 1
        print(f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} pause: {len(bands)} bands pulled, "
              f"{PAUSE_WINDOW}-min move {math.log(float(row_data.prices[self.gp.base_token.name]) / self.price_hist[0]):+.2%}")

    def restore_ladder(self, row_data: Snapshot) -> None:
        """EXP-060: mint every pulled band again with its pre-pause liquidity; one net swap first (see MACRO_RESTORE)."""
        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]
        pool = lp_market.pool_info
        price = row_data.prices[self.gp.base_token.name]
        sqrt = base_unit_price_to_sqrt_price_x96(price, pool.token0.decimal, pool.token1.decimal, pool.is_token0_quote)
        base_is_0 = self.gp.base_token.name == self.gp.token0.name
        need = []
        for pos, liq in self.paused_liq:
            a0, a1 = V3CoreLib.get_token_amounts(pool, pos, sqrt, liq)
            need.append((pos, a0 if base_is_0 else a1, a1 if base_is_0 else a0))
        need_b = sum((b for _, b, _ in need), ZERO)
        need_q = sum((q for _, _, q in need), ZERO)
        free_b = lambda: self.broker.get_token_balance(self.gp.base_token) - self.fee_reserve_base()
        free_q = lambda: max(ZERO, self.broker.get_token_balance(self.gp.quote_token) - self.fee_reserve_quote() - self.reserve_quote)
        fee = Decimal(pool.fee_rate)
        if need_b > free_b():   # buy the missing base with the surplus quote
            pay = min(max(ZERO, free_q() - need_q), (need_b - free_b()) * price / (ONE - fee))
            if pay > ZERO:
                _, _, _, fq = self.execute_swap(lp_market, ZERO, pay)
                self.total_quote_swap_fee += fq if fq is not None else ZERO
        elif need_q > free_q():   # sell the surplus base for the missing quote
            sell = min(max(ZERO, free_b() - need_b), (need_q - free_q()) / price / (ONE - fee))
            if sell > ZERO:
                _, _, fb, _ = self.execute_swap(lp_market, sell, ZERO)
                self.total_base_swap_fee += fb if fb is not None else ZERO
        # what the swap fee took is shared out pro rata
        k = min([ONE] + [free_b() / need_b if need_b > ZERO else ONE] + [free_q() / need_q if need_q > ZERO else ONE])
        tick = lp_market.price_to_raw_tick(price)
        placed = []
        for pos, b, q in need:
            if b * k <= ZERO and q * k <= ZERO:
                continue
            p, bu, qu, _ = lp_market.add_liquidity_by_tick(pos[0], pos[1], b * k, q * k, tick=tick)
            if bu == ZERO and qu == ZERO:
                lp_market.positions.pop(p, None)
                continue
            placed.append(p)
        self.positions = placed
        self.paused_bands, self.paused_liq = [], []
        self.paused_until = None

    def resume_ladder(self, row_data: Snapshot) -> None:
        """Re-add the pulled ladder: the build loop again at the build's tick (same ranges, same side-rescaled band
        shares) from the wallet's free tokens at the current price. A second pass tops the bands up with what the
        first pass left (the price moved, so the band straddling it wants a different token mix); whatever still
        does not fit stays idle until the next rebuild, as v6's leftovers do."""
        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]
        current_tick = self.utils.get_raw_tick(row_data)
        price = row_data.prices[self.gp.base_token.name]
        placed: Dict[PositionInfo, bool] = {}
        for _pass in range(2):
            free_base = self.broker.get_token_balance(self.gp.base_token) - self.fee_reserve_base()
            free_quote = self.broker.get_token_balance(self.gp.quote_token) - self.fee_reserve_quote()
            if MACRO_EVENTS is not None:   # EXP-059: the reserve stays out of the re-added ladder
                free_quote = max(ZERO, free_quote - self.reserve_quote)
            if free_base * price + free_quote < Decimal(1):
                break
            for config in self.ladder_configs():
                _, _, lower_tick, upper_tick = self.calculate_range(lp_market, self.build_tick, config[0], config[1])
                base_amt, quote_amt = self.band_amounts(free_base, free_quote, config[2])
                if base_amt <= ZERO and quote_amt <= ZERO:
                    continue
                pos, base_used, quote_used, _ = lp_market.add_liquidity_by_tick(lower_tick, upper_tick, base_amt, quote_amt,
                                                                                tick=current_tick)
                if base_used == ZERO and quote_used == ZERO:
                    if pos not in placed:
                        lp_market.positions.pop(pos, None)   # dry band (as the build loop does)
                    continue
                placed[pos] = True
        self.positions = list(placed)
        self.paused_bands = []
        self.paused_until = None

    # ---- EXP-014: perp delta hedge ----
    def ladder_base(self, lp_market: UniLpMarketV2) -> Decimal:
        """Base tokens held inside the bands = the ladder's delta (dV/dP = x for a v3 position)."""
        total = ZERO
        for pos in self.positions:
            a0, a1 = lp_market.get_position_amount(pos)
            total += a1 if lp_market.pool_info.is_token0_quote else a0
        return total

    def hedge_book(self, amount: Decimal) -> None:
        """A hedge cash flow (PnL, funding, fee) to the quote balance; the margin account is part of the book."""
        if amount >= ZERO:
            self.broker.add_to_balance(self.gp.quote_token, amount)
        else:
            self.broker.subtract_from_balance(self.gp.quote_token, -amount)
            cash = self.broker.get_token_balance(self.gp.quote_token)
            self.hedge_min_cash = cash if self.hedge_min_cash is None else min(self.hedge_min_cash, cash)

    def hedge_settle(self, price: Decimal) -> None:
        """Settle the open short against `price` and re-mark it there (daily settlement)."""
        if self.hedge_size > ZERO:
            pnl = (self.hedge_entry - price) * self.hedge_size
            self.hedge_pnl += pnl
            self.hedge_book(pnl)
        self.hedge_entry = price

    def hedge_rebalance(self, row_data: Snapshot) -> None:
        """Settle, then set the short to HEDGE x the ladder's base (EXP-014) or, while the day's "short" flag is set,
        to BEAR_SHORT x book equity (EXP-018); taker fee on the traded notional."""
        if not perp_enabled() or self.starting_tick is None:
            return
        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]
        price = row_data.prices[self.gp.base_token.name]
        self.hedge_settle(price)
        if BEAR_SHORT > ZERO:
            on = bool(daily_row_for(self.daily_ema, row_data.timestamp)[1]["short"])
            lp_value = lp_market.get_market_balance().net_value if len(lp_market.positions) > 0 else ZERO
            equity = lp_value + self.broker.get_token_balance(self.gp.base_token) * price + \
                self.broker.get_token_balance(self.gp.quote_token)
            target = BEAR_SHORT * equity / price if on and equity > ZERO else ZERO
            self.bear_short_days += int(on)
        else:
            target = HEDGE * self.ladder_base(lp_market)
        diff = target - self.hedge_size
        if abs(diff) * price >= Decimal(1):   # under $1 of notional: leave it
            fee = abs(diff) * price * HEDGE_FEE
            self.hedge_fees += fee
            self.hedge_book(-fee)
            self.hedge_size = target
            self.hedge_trades += 1
        lp_value = lp_market.get_market_balance().net_value if len(lp_market.positions) > 0 else ZERO
        equity = lp_value + self.broker.get_token_balance(self.gp.base_token) * price + self.broker.get_token_balance(self.gp.quote_token)
        if equity > ZERO:
            self.hedge_max_ratio = max(self.hedge_max_ratio, float(self.hedge_size * price / equity))

    def hedge_funding_work(self, row_data: Snapshot) -> None:
        """8h funding on the open short: rate x notional, positive rate = the short receives."""
        if not perp_enabled() or self.hedge_size <= ZERO or HEDGE_FUNDING is None:
            return
        rate = HEDGE_FUNDING.get(pd.Timestamp(row_data.timestamp))
        if rate is None or pd.isna(rate):
            return
        pay = Decimal(str(rate)) * self.hedge_size * row_data.prices[self.gp.base_token.name]
        self.hedge_funding += pay
        self.hedge_book(pay)

    def hedge_close(self, price: Decimal) -> None:
        """End of the run: settle and close the short, paying the taker fee."""
        if not perp_enabled() or self.hedge_size <= ZERO:
            return
        self.hedge_settle(price)
        fee = self.hedge_size * price * HEDGE_FEE
        self.hedge_fees += fee
        self.hedge_book(-fee)
        self.hedge_size = ZERO
        self.hedge_trades += 1

    def sleeve_stop_work(self, row_data: Snapshot, target: Decimal, free_base: Decimal):
        """EXP-002: trailing stop on the spot sleeve, and its re-arm (refill above the post-stop low F, or a new high)."""
        close = float(daily_row_for(self.daily_ema, row_data.timestamp)[1]["close"])
        if self.sleeve_stopped:
            if target > self.stop_low_f or close > self.sleeve_high:
                self.sleeve_stopped, self.stop_low_f = False, None
                if SLEEVE_HIGH_KEEP:
                    self.sleeve_high = None   # the next build that buys the sleeve starts a new high
                print(f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} sleeve re-armed: F {float(target):.4f} close {close:.4f}")
            else:
                self.stop_low_f = min(self.stop_low_f, target)
            return
        if self.reserve_base <= ZERO or self.sleeve_high is None:
            return
        self.sleeve_high = max(self.sleeve_high, close)
        if close < SLEEVE_STOP * self.sleeve_high and free_base > ZERO:
            lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]
            _, _, fee_base, fee_quote = self.execute_swap(lp_market, free_base, ZERO)
            self.total_base_swap_fee += fee_base if fee_base is not None else ZERO
            self.total_quote_swap_fee += fee_quote if fee_quote is not None else ZERO
            self.reserve_base, self.sleeve_stopped, self.stop_low_f = ZERO, True, target
            self.sleeve_stops += 1
            print(f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} sleeve stop: close {close:.4f} < "
                  f"{SLEEVE_STOP} x high {self.sleeve_high:.4f}, sold {float(free_base):.4f} base")

    def placed_base_share(self, lp_market: UniLpMarketV2, current_tick: int,
                          base_used: Decimal, quote_used: Decimal) -> Decimal:
        """Share of the placed value sitting on the base side; should track eth_share (or ~0.5 for sgeo)."""
        base_value = base_used * lp_market.tick_to_price(current_tick)
        total = base_value + quote_used
        return base_value / total if total > ZERO else ZERO

    def fee_reserve_base(self) -> Decimal:
        """Base held back from the book as paid-out rewards; EXP-022: nothing is held back when fees compound."""
        return ZERO if FEE_COMPOUND else self.total_base_fee

    def fee_reserve_quote(self) -> Decimal:
        return ZERO if FEE_COMPOUND else self.total_quote_fee

    def collect_fee_as_quote(self, lp_market: UniLpMarketV2, position_info) -> tuple[Decimal, Decimal]:
        """Collect a position's fees and sell the base part for quote (spec sheet: rewards are paid in USDC).
        Returns (base fee collected, quote credited incl. the sold base). The sale pays the pool fee."""
        base_fee, quote_fee = lp_market.collect_fee(position_info, collect_to_user=True)
        if base_fee > ZERO:
            _, sold_quote, sale_fee_base, _ = self.execute_swap(lp_market, base_fee, ZERO)
            self.total_base_swap_fee += sale_fee_base if sale_fee_base is not None else ZERO
            quote_fee += sold_quote
        self.total_quote_fee += quote_fee
        return base_fee, quote_fee

    def band_amounts(self, base: Decimal, quote: Decimal, share: Decimal) -> tuple[Decimal, Decimal]:
        """
        `share` of the pre-placement balances, clamped to what is still free. With half_gap 0 the real
        tick sits inside one side band, which then takes a sliver of the other side's token; without
        the clamp the last band on that side overdraws by that sliver.
        """
        free_base = self.broker.get_token_balance(self.gp.base_token) - self.fee_reserve_base()
        free_quote = self.broker.get_token_balance(self.gp.quote_token) - self.fee_reserve_quote()
        return max(ZERO, min(base * share, free_base)), max(ZERO, min(quote * share, free_quote))

    def check_rebalance(self, lp_market: UniLpMarketV2, current_tick: int) -> bool:
        # Check if the current price is outside the current LP range
        rebalance = False
        # REFILL_ORDER: range orders sit off the price on purpose; judge exits on the ladder span of the last build
        lo, hi = self.ladder_span if ((REFILL_ORDER or HALF_LADDER or HALF_WHEN_ACCEL) and self.ladder_span) else (self.positions[0][0], self.positions[-1][1])
        if not (lo <= current_tick < hi):
            self.exit_streak += 1
            rebalance = self.exit_streak >= EXIT_CONFIRM
            if NO_EXIT_REBUILD and not self.force_rebuild:   # EXP-074 / EXP-075
                base_is_0 = self.gp.base_token.name == self.gp.token0.name
                up = (current_tick >= hi) if base_is_0 else (current_tick < lo)
                if NO_EXIT_REBUILD == "all" or (NO_EXIT_REBUILD == "down" and not up):
                    self.skipped_exits += rebalance
                    rebalance = False
            if rebalance:
                print("allow rescale", self.positions[0][0], current_tick, self.positions[-1][1])
        else:
            self.exit_streak = 0

        return rebalance

    def get_balance_base_quote_amounts(self) -> tuple[Decimal, Decimal]:
        base = self.broker.get_token_balance(self.gp.base_token)
        quote = self.broker.get_token_balance(self.gp.quote_token)
        # if self.broker.quote_token == usdc:
        #     quote = usdc_balance
        #     base = eth_balance
        # else:
        #     base = usdc_balance
        #     quote = eth_balance

        return base, quote

    def rescale_work(self, row_data: Snapshot):
        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]

        if (len(lp_market.positions) == 0 and not self.force_rebuild) or self.out_of_fund_date is not None \
                or self.paused_until is not None or ACCOUNT_TRANCHES:   # EXP-063: sub-ladders handle all rebuilds
            return

        current_price = row_data.prices[self.gp.base_token.name]
        try:
            current_tick = lp_market.price_to_raw_tick(current_price)
            allow_rescale = self.force_rebuild or self.check_rebalance(lp_market, current_tick)
            if not allow_rescale and RECENTRE_UP and self.build_price and \
                    current_price >= self.build_price * (ONE + RECENTRE_UP):   # EXP-023: recentre early on the way up
                allow_rescale = True
                self.recentre_count += 1

            # Check if rescaling is allowed
            if not allow_rescale:
                # print("current condition not allow rescale: " + row_data.timestamp.strftime("%Y-%m-%d %H:%M:%S"))
                return

            old_position_infos = self.positions

            if not old_position_infos:
                pass  # follow rebuild from an empty book (F was 0)
            elif old_position_infos[0][0] > current_tick:
                self.upper_rescale_count += 1
            elif current_tick >= old_position_infos[-1][1]:
                self.lower_rescale_count += 1


            base_fee, quote_fee = ZERO, ZERO
            base_removed, quote_removed = ZERO, ZERO
            for position_info in self.positions:
                position_base_fee, position_quote_fee = self.collect_fee_as_quote(lp_market, position_info)
                if position_info not in lp_market.positions:
                    continue  # dry band (zero liquidity, zero pending fee): collect_fee already deleted it
                try:
                    base, quote = lp_market.remove_liquidity(position_info, collect=True)
                    base_removed += base
                    quote_removed += quote
                except Exception as e:
                    print(f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} => failed to remove liquidity: {position_info}")
                    print(f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} => current tick: {current_tick}, positions: {lp_market.positions}")
                    raise e

                base_fee += position_base_fee
                quote_fee += position_quote_fee  # already includes the base fee sold for quote

            self.positions = []
            rebalance_base_fee, rebalance_quote_fee = ZERO, ZERO

            self.resolve_skew(row_data.timestamp)
            lowest, highest = self.shape_config[0][0], self.shape_config[-1][1]
            (_lower_price, _upper_price, lower_boundary, upper_boundary) = self.calculate_range(lp_market, current_tick, lowest, highest)
            try:

                # to_swap_base = lp_market.broker.get_token_balance(self.gp.base_token) - self.fee_reserve_base()
                # to_swap_quote = lp_market.broker.get_token_balance(self.gp.quote_token) - self.fee_reserve_quote()

                # # base_to_swap, quote_to_swap = self.calculate_swap_amount(current_tick, new_tick_lower, new_tick_upper, to_swap_base, to_swap_quote)
                # # swapped_base, swapped_quote, base_used_fee, quote_used_fee = self.execute_swap(lp_market, base_to_swap, quote_to_swap)
                # base, quote, rebalance_base_fee, rebalance_quote_fee = self.even_rebalance(lp_market, to_swap_base,
                #                                                                                     to_swap_quote)

                # self.total_base_swap_fee += rebalance_base_fee if rebalance_base_fee is not None else ZERO
                # self.total_quote_swap_fee += rebalance_quote_fee if rebalance_quote_fee is not None else ZERO

                to_swap_base = lp_market.broker.get_token_balance(self.gp.base_token) - self.fee_reserve_base()
                to_swap_quote = lp_market.broker.get_token_balance(self.gp.quote_token) - self.fee_reserve_quote()

                base_to_swap, quote_to_swap = self.pre_placement_swap(lp_market, current_tick, lower_boundary, upper_boundary, to_swap_base, to_swap_quote, row_data.timestamp)
                if SWAPLESS_EXIT and old_position_infos and not self.force_rebuild:   # EXP-057: range exit, no swap
                    base_to_swap, quote_to_swap = ZERO, ZERO
                    self.swapless_exits += 1
                swapped_base, swapped_quote, rebalance_base_fee, rebalance_quote_fee = self.execute_swap(lp_market, base_to_swap, quote_to_swap)

                self.total_base_swap_fee += rebalance_base_fee if rebalance_base_fee is not None else ZERO
                self.total_quote_swap_fee += rebalance_quote_fee if rebalance_quote_fee is not None else ZERO

                base = lp_market.broker.get_token_balance(self.gp.base_token) - self.fee_reserve_base()
                quote = lp_market.broker.get_token_balance(self.gp.quote_token) - self.fee_reserve_quote()


                # if self.params.compound:
                #     self.utils.current_position_info, base_used, quote_used, _ = lp_market.add_liquidity_by_tick(
                #         new_tick_lower, new_tick_upper, tick=current_tick)
                # else:
                total_base_used, total_quote_used = ZERO, ZERO
                quote_for_bands = max(ZERO, quote - self.reserve_quote)
                base_for_bands = max(ZERO, base - self.reserve_base)
                self.build_tick, self.build_price = current_tick, row_data.prices[self.gp.base_token.name]   # EXP-016 / EXP-023
                for config in (self.ladder_configs() if self.deployed_at_build > ZERO else []):
                    lower_price, upper_price, lower_tick, upper_tick = self.calculate_range(lp_market, current_tick, config[0], config[1])
                    base_amt, quote_amt = self.band_amounts(base_for_bands, quote_for_bands, config[2])
                    position, base_used, quote_used, _ = lp_market.add_liquidity_by_tick(lower_tick, upper_tick, base_amt, quote_amt, tick=current_tick)
                    if base_used == ZERO and quote_used == ZERO:
                        lp_market.positions.pop(position, None)  # ponytail: drop the dry band instead of tracking it
                        continue
                    total_base_used += base_used
                    total_quote_used += quote_used
                    self.positions.append(position)

                base_left_ratio = (base_for_bands - total_base_used) / base_for_bands if base_for_bands > ZERO else ZERO
                quote_left_ratio = (quote_for_bands - total_quote_used) / quote_for_bands if quote_for_bands > ZERO else ZERO
                print(f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} rescale placed base share "
                      f"{float(self.placed_base_share(lp_market, current_tick, total_base_used, total_quote_used)):.3f} "
                      f"(target {share_label(self.last_share)}), F {float(self.deployed_at_build):.4f}, "
                      f"reserve quote {float(self.reserve_quote):,.0f}, left base {float(base_left_ratio):.4f} quote {float(quote_left_ratio):.4f}")

                # if base_left_ratio > 0.001 or quote_left_ratio > 0.001:
                #     self.rescale_left_too_much_count += 1
                #     print("rescale_work left too much: left_base", base_left_ratio, "left_quote", quote_left_ratio)

                left_base = lp_market.broker.get_token_balance(self.gp.base_token) - self.fee_reserve_base()
                left_quote = lp_market.broker.get_token_balance(self.gp.quote_token) - self.fee_reserve_quote()

                # print(f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} orig base: {to_swap_base}, orig quote: {to_swap_quote}, base_to_swap: {base_to_swap}, quote_to_swap: {quote_to_swap},"
                #       f" swapped base: {swapped_base}, quote: {swapped_quote}, final base: {base}, quote: {quote}, base_used: {base_used}, quote_used: {quote_used}, left_base: {left_base}, left_quote: {left_quote}")


                # lock until today is over
                # self.lock_until_time = datetime(row_data.timestamp.year, row_data.timestamp.month,
                #                                 row_data.timestamp.day, 23, 59, 0)

                    # print(f"add LP => new position info ({current_tick}): { self.utils.current_position_info}, base: {base_used}, quote: {quote_used}, base_leftover: {base_leftover}, quote_leftover: {quote_leftover} ")
            except Exception as e:
                print(
                    f"failed to add liquidity, current tick: {current_tick}, upper: {upper_boundary}, lower: {lower_boundary}")
                raise e

            # current_tick = lp_market.price_to_raw_tick(current_price)

            if self.deployed_at_build > ZERO and total_base_used == ZERO and total_quote_used == ZERO:
                self.out_of_fund_date = row_data.timestamp
                print(
                    f"\nno position place ({row_data.timestamp.strftime("%Y-%m-%d %H:%M:%S")}): {self.positions}, old_position_info: {old_position_infos}, "
                    f"current_tick: {current_tick}, new_tick_lower: {lower_boundary}, new_tick_upper: {upper_boundary}, "
                    f"positions: {lp_market.positions}, base: {base}, quote: {quote}, "
                    f"rebalance_base_fee: {rebalance_base_fee}, rebalance_quote_fee: {rebalance_quote_fee}, balance_data: {self.balance_data}")

            ed = ExportData()
            ed.time = row_data.timestamp
            ed.price = current_price
            ed.tick = current_tick

            ed.tick_lower, ed.tick_upper = (old_position_infos[0][0], old_position_infos[-1][1]) if old_position_infos else (0, 0)

            # pos = lp_market.positions[self.utils.current_position_info]
            ed.price_lower, ed.price_upper = (lp_market.positions[self.positions[0]].lower_price, lp_market.positions[self.positions[-1]].upper_price) if self.positions else (None, None)

            ed.new_tick_lower, ed.new_tick_upper = (self.positions[0][0], self.positions[-1][1]) if self.positions else (0, 0)

            ed.base_fee, ed.quote_fee = base_fee, quote_fee
            ed.base_removed, ed.quote_removed = base_removed, quote_removed
            ed.base_added, ed.quote_added = total_base_used, total_quote_used
            ed.was_in_range = self.was_in_range
            ed.total_base_fee, ed.total_quote_fee = self.total_base_fee, self.total_quote_fee

            ed.lp_net_value = lp_market.get_market_balance().net_value
            ed.lp_net_value_with_idle = (self.idle_base * ed.price) + self.idle_quote + ed.lp_net_value
            ed.quote_balance = lp_market.broker.get_token_balance(self.gp.quote_token)
            ed.base_balance = lp_market.broker.get_token_balance(self.gp.base_token)
            ed.total_net_value = ed.lp_net_value + ed.quote_balance + (ed.base_balance * ed.price)
            ed.total_net_value_base = ed.total_net_value / ed.price
            ed.swap_fee_base = self.total_base_swap_fee
            ed.swap_fee_quote = self.total_quote_swap_fee

            lp_row_data = self.utils.get_lp_row_data(row_data)
            if self.params.range_strategy == RangeStrategy.std:
                ed.indicator_value = lp_row_data.std_1_hr
            elif self.params.range_strategy == RangeStrategy.atr:
                ed.indicator_value = lp_row_data.atr_1_hr
            else:
                ed.indicator_value = upper_boundary - lower_boundary

            ed.param_type = "bull" if self.utils.bull else "bear"

            self.export_actions.append(ed)

            # pos_info = self.utils.current_position_info
            # tick_spread = pos_info[1] - pos_info[0]
            if self.positions:
                self.tick_spreads.loc[len(self.tick_spreads)] = self.positions[-1][1] - self.positions[0][0]

            # print(
            #     f"rescaled at {row_data.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, removed: {base} / {quote}, fee: {base_fee} / {quote_fee}, used: {base_used} / {quote_used}, "
            #     f"tick: {current_tick}, s: {old_position_info}, position_info: {str(self.utils.current_position_info)}, was_in_range: {self.was_in_range}, price: {current_price}")

            self.last_rescale_tick = current_tick
            self.was_in_range = False
            self.set_ladder_span(lp_market, current_tick)

        finally:
            self.last_price = current_price
        pass

    def first_lp(self, row_data: Snapshot):
        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]

        if len(lp_market.positions) > 0:
            raise RuntimeError("shouldn't have any position")

        quote_usdc_price = self.init_quote_usd_price = self.get_quote_usdc_price(row_data)
        quote_amount = self.gp.init_quote

        lp_market.broker.add_to_balance(self.gp.quote_token, quote_amount)
        self.total_invested += quote_amount
        self.total_invested_usdc += self.gp.init_quote * quote_usdc_price

        tick_spacing, _, _, _ = self.utils.get_tick_info(row_data)
        current_tick = self.utils.get_raw_tick(row_data)
        
        # _lower_price = _upper_price = None
        current_price = row_data.prices[self.gp.base_token.name]


        self.resolve_skew(row_data.timestamp)
        lowest, highest = self.shape_config[0][0], self.shape_config[-1][1]
        (_lower_price, _upper_price, lower_boundary, upper_boundary) = self.calculate_range(lp_market, current_tick, lowest, highest)
        self.starting_tick = current_tick
        if ACCOUNT_TRANCHES:   # EXP-063: the sub-ladders are built right away by tranche_work
            self.was_in_range = True
            self.last_price = self.last_dca_price = self.last_check_price = current_price
            self.tranche_work(row_data)
            return

        init_base = lp_market.broker.get_token_balance(self.gp.base_token)
        init_quote = lp_market.broker.get_token_balance(self.gp.quote_token)

        base_to_swap, quote_to_swap = self.pre_placement_swap(lp_market, current_tick, lower_boundary, upper_boundary, init_base, init_quote, row_data.timestamp)
        swapped_base, swapped_quote, base_fee, quote_fee = self.execute_swap(lp_market, base_to_swap, quote_to_swap)

        final_base = lp_market.broker.get_token_balance(self.gp.base_token)
        final_quote = lp_market.broker.get_token_balance(self.gp.quote_token)
        self.total_base_swap_fee += base_fee if base_fee is not None else ZERO
        self.total_quote_swap_fee += quote_fee if quote_fee is not None else ZERO

        total_base_used = 0
        total_quote_used = 0

        quote_for_bands = max(ZERO, final_quote - self.reserve_quote)
        base_for_bands = max(ZERO, final_base - self.reserve_base)
        self.build_tick, self.build_price = current_tick, row_data.prices[self.gp.base_token.name]   # EXP-016 / EXP-023
        for config in (self.ladder_configs() if self.deployed_at_build > ZERO else []):
            lower_price, upper_price, lower_tick, upper_tick = self.calculate_range(lp_market, current_tick, config[0], config[1])
            base_amt, quote_amt = self.band_amounts(base_for_bands, quote_for_bands, config[2])
            position, base_used, quote_used, _ = lp_market.add_liquidity_by_tick(lower_tick, upper_tick, base_amt, quote_amt, tick=current_tick)
            if base_used == ZERO and quote_used == ZERO:
                lp_market.positions.pop(position, None)
                continue
            total_base_used += base_used
            total_quote_used += quote_used
            self.positions.append(position)

        # self.utils.current_position_info, base_used, quote_used, _ = lp_market.add_liquidity_by_tick(lower, upper, final_base, final_quote, tick=current_tick) # tick=current_tick
        # print(f"first LP: new_tick_upper: {upper}, new_tick_lower: {lower}, current_tick: {current_tick}")
        left_base = lp_market.broker.get_token_balance(self.gp.base_token)
        left_quote = lp_market.broker.get_token_balance(self.gp.quote_token)

        print(f"initial swap: {final_base} / {final_quote}, fee: {base_fee} / {quote_fee}, placed base share "
              f"{float(self.placed_base_share(lp_market, current_tick, total_base_used, total_quote_used)):.3f} (target {share_label(self.last_share)}), "
              f"F {float(self.deployed_at_build):.4f}, reserve quote {float(self.reserve_quote):,.0f}")
        print(
            f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} first_lp base_to_swap: {base_to_swap}, quote_to_swap: {quote_to_swap}, "
            f"swapped base: {swapped_base}, quote: {swapped_quote}, final base: {final_base}, quote: {final_quote}, "
            f"base_used: {total_base_used}, quote_used: {total_quote_used}, left_base: {left_base}, left_quote: {left_quote}")
        print(
            f"\nadding first liquidity, price: {str(current_price)}, range: {str(lower_boundary)} ~ {str(upper_boundary)}, price: {_lower_price} ~ {_upper_price}, current tick: {current_tick}")

        self.was_in_range = True
        self.last_price = self.last_dca_price = self.last_check_price = current_price
        self.set_ladder_span(lp_market, current_tick)

        pass

    def calculate_final_result(self, row_data: Snapshot):
        if self.fee_log:
            pd.DataFrame(self.fee_log).to_csv(f"{self.params.folder}/fees_{self.params.report_name}.csv", index=False)
        print(f"final result: rescale_left_too_much_count: {self.rescale_left_too_much_count}, "
              f"follow rebuilds: {self.follow_rebuild_count}, share picks: {self.share_picks}, "
              f"last F: {float(self.deployed_at_build):.4f}")

        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]
        # _, current_tick, _, _ = self.utils.get_tick_info(row_data)
        current_tick = self.utils.get_raw_tick(row_data)
        current_price = row_data.prices[self.gp.base_token.name]
        self.hedge_close(current_price)   # EXP-014: the short is closed into the final equity
        ed = ExportData()
        ed.time = row_data.timestamp
        ed.price = current_price
        ed.tick = current_tick

        position_info = self.utils.current_position_info
        ed.tick_lower, ed.tick_upper = (self.positions[0][0], self.positions[-1][1]) if self.positions else (0, 0)

        # pos = lp_market.positions.get(position_info, None)
        # if pos is None:
        #     ed.price_lower, ed.price_upper = None, None
        # else:
        #     ed.price_lower, ed.price_upper = pos.lower_price, pos.upper_price
        if len(lp_market.positions) == 0:
            ed.price_lower, ed.price_upper = None, None
        else:
            ed.price_lower, ed.price_upper = (lp_market.positions[self.positions[0]].lower_price, lp_market.positions[self.positions[-1]].upper_price) if self.positions else (None, None)

        ed.new_tick_lower, ed.new_tick_upper = ed.tick_lower, ed.tick_upper

        # base_fee, quote_fee = lp_market.collect_fee(self.utils.current_position_info, collect_to_user=True)
        last_base_fee, last_quote_fee = 0, 0
        for position_info in self.positions:
            base_fee, quote_fee = self.collect_fee_as_quote(lp_market, position_info)
            last_base_fee += base_fee
            last_quote_fee += quote_fee


        ed.base_fee, ed.quote_fee = last_base_fee, last_quote_fee
        ed.base_removed, ed.quote_removed = None, None
        ed.base_added, ed.quote_added = None, None
        ed.was_in_range = self.was_in_range
        ed.total_base_fee, ed.total_quote_fee = self.total_base_fee, self.total_quote_fee

        ed.lp_net_value = lp_market.get_market_balance().net_value
        ed.quote_balance = lp_market.broker.get_token_balance(
            self.gp.quote_token) + self.idle_quote + self.leftover_quote
        ed.base_balance = lp_market.broker.get_token_balance(self.gp.base_token) + self.idle_base + self.leftover_base
        ed.total_net_value = ed.lp_net_value + ed.quote_balance + (ed.base_balance * ed.price)
        # lp_row_data = self.utils.get_lp_row_data(row_data)
        ed.indicator_value = None

        ed.param_type = "bull" if self.utils.bull else "bear"
        self.export_actions.append(ed)

        self.total_swap_fee = self.total_quote_swap_fee + self.total_base_swap_fee * current_price
        self.total_fee = self.total_quote_fee + self.total_base_fee * current_price
        self.final_total_net_value = ed.total_net_value
        self.final_lp_net_value = ed.lp_net_value

        # usd_price = self.final_quote_usd_price = Decimal(
        #     getPrice(self.gp.quote_token.name, row_data.timestamp))  # Decimal(FINAL_PRICE) #ONE #lp_row_data.usdc_price
        usd_price = self.final_quote_usd_price = self.get_quote_usdc_price(row_data)

        self.total_fee_usd = self.total_fee * usd_price
        self.total_net_value_usd = self.final_total_net_value * usd_price
        self.total_lp_value_usd = self.final_lp_net_value * usd_price
        
        pass

    def on_bar(self, row_data: Snapshot):
        """
        Called after triggers on each iteration, at this time, market are not updated yet(Take uniswap market for example, fee of this minute are not added to positions).

        :param row_data: data in this iteration, include current timestamp, price, all columns data, and indicators(such as simple moving average)
        :type row_data: Snapshot
        """
        if PAUSE_RET > 0:   # EXP-016
            self.pause_work(row_data)
        if MACRO_EVENTS is not None:   # EXP-059
            self.macro_work(row_data)

        pos_info = self.utils.current_position_info
        if pos_info is None:
            return

        lp_row_data = row_data.market_status[self.utils.market_key]
        in_lock = self.is_in_lock(row_data)

        in_range = (
            # check if the tick range ever overlaps the LP range
                self.utils.current_position_info[0] <= lp_row_data.highestTick and
                self.utils.current_position_info[1] >= lp_row_data.lowestTick)
        if in_range:
            self.total_in_range_minutes += 1
            self.total_in_range_and_in_lock_minutes += 1 if in_lock else 0
        elif in_lock:
            self.total_out_of_range_and_in_lock_minutes += 1

        self.total_minutes += 1

        if self.was_in_range:
            return

        self.was_in_range = in_range

        pass

    def finalize(self):
        """
        this will run after all the data processed. You can access broker.account_status, broker.market.status to do some calculation

        """

        export_file(f"{self.params.folder}/result_{self.params.report_name}.csv", self.export_actions)
        pass


def run_test(bull_params: RemixDAOParams, bear_params: RemixDAOParams, params: TestParams, gp: GlobalParams,
             processed_data: pd.DataFrame | None, usdc_price_data: pd.DataFrame | None = None,
             shape: str = "inverted_gaussian_9", upper_ratio: Decimal = Decimal("0.50"),
             lower_ratio: Decimal | str = Decimal("0.50"), half_gap: int | str = 0,
             eth_share: Decimal | str | None = None, daily_ema: pd.DataFrame | None = None,
             deploy: str = DEPLOY_FULL) -> Dict[str, Decimal]:
    try:

        usdc_prices: pd.Series | None = None
        if usdc_price_data is not None:
            # print(f"columns: {usdc_price_data.columns}")
            usdc_prices = usdc_price_data["price"]

            # print(usdc_prices)
            pass

        market_key = MarketInfo("lp")

        actuator = Actuator()  # declare actuator
        broker = actuator.broker
        pool = UniV3Pool(gp.token0, gp.token1, gp.fee, gp.quote_token,
                         tick_spacing=bull_params.tick_spacing)  # declare pool, Arbitrum One
        market = UniLpMarketV2(market_key, pool)

        broker.add_market(market)
        # broker.set_balance(gp.quote_token, gp.init_quote)
        broker.set_balance(gp.quote_token, 0)
        broker.set_balance(gp.base_token, 0)

        utils = RemixDaoUtils(market, market_key, bull_params, bear_params, params.start_with_bull_param)
        strat = RemixDaoDcaWeekStratStrategy(utils, params, gp, usdc_prices=usdc_prices, shape=shape,
                                             upper_ratio=upper_ratio, lower_ratio=lower_ratio,
                                             half_gap=half_gap, eth_share=eth_share, daily_ema=daily_ema,
                                             deploy=deploy)
        actuator.strategy = strat
        market.data_path = f"../real-data/{gp.contract_address}"
        if processed_data is not None:
            # print("use prepared data")
            processed_data_copy = copy.deepcopy(processed_data)
            market.add_statistic_column(processed_data_copy)
            market.data = processed_data_copy
        else:

            start = datetime.now()
            market.load_data(
                gp.chain_name, gp.contract_address, params.data_start_date, params.data_end_date
            )

            dif = datetime.now() - start
            print(f"load data: {dif.total_seconds()} seconds")

        # start = datetime.now()
        actuator.set_price(market.get_price_from_data())
        actuator.run(False)  # run test
        # dif = datetime.now() - start
        # print(f"run: {dif.total_seconds()} seconds")

        price_name = gp.base_token.name.upper()
        benchmark_series = actuator.account_status_df["price"][price_name]
        metrics: dict[str, Decimal] = performance_metrics_for_dca(
            actuator.account_status_df["net_value"], 0, benchmark=benchmark_series,
            total_fee=strat.total_fee,
        )

        benchmark_final = benchmark_series.iloc[-1]
        # print(metrics)
        metrics["action_count"] = Decimal(len(strat.export_actions))

        spread_mean = strat.tick_spreads.mean()
        spread_median = strat.tick_spreads.median()
        if math.isnan(spread_mean):
            spread_mean = Decimal(-1)
        metrics["spread_mean"] = Decimal(int(spread_mean))
        metrics["spread_median"] = spread_median

        metrics["lp_net_value"] = strat.final_lp_net_value
        metrics["total_net_value"] = strat.final_total_net_value
        metrics["total_fee"] = strat.total_fee
        metrics["fee_to_total_net_value"] = strat.total_fee / strat.final_total_net_value
        metrics["total_base_swap_fee"] = strat.total_base_swap_fee
        metrics["total_quote_swap_fee"] = strat.total_quote_swap_fee
        metrics["total_swap_fee"] = strat.total_swap_fee

        bench_price = actuator.account_status_df["price"][price_name].apply(lambda x: float(x))
        metrics["benchmark_max_draw_down"] = max_draw_down(bench_price)

        metrics["total_dca"] = ZERO  # strat.dca_total_added
        metrics["dca_count"] = ZERO  # Decimal(strat.dca_count)
        metrics["dca_addon_count"] = ZERO  # Decimal(strat.dca_addon_count)
        metrics["total_fee_usd"] = strat.total_fee_usd
        metrics["total_net_value_usd"] = strat.total_net_value_usd
        metrics["lp_net_value_usd"] = strat.total_lp_value_usd
        metrics["total_return_usd"] = Decimal(
            return_rate(float(strat.total_invested_usdc), float(strat.total_net_value_usd)))
        metrics["total_invested_usd"] = strat.total_invested_usdc

        if strat.usdc_prices is not None:
            init_price = strat.usdc_prices.iloc[0]
            final_price = strat.usdc_prices.iloc[-1]
        else:
            init_price = getPrice(gp.quote_token.name, params.data_start_date)  # INIT_PRICE #ONE #
            final_price = getPrice(gp.quote_token.name,
                                   params.data_end_date)  # FINAL_PRICE #ONE #strat.usdc_prices.iloc[-1]

        metrics["quote_return_usd"] = Decimal(return_rate(init_price, final_price))

        metrics["lock_count"] = Decimal(strat.total_lock_count)
        metrics["rescale_count"] = Decimal(strat.lower_rescale_count + strat.upper_rescale_count)
        metrics["upper_rescale_count"] = Decimal(strat.upper_rescale_count)
        metrics["lower_rescale_count"] = Decimal(strat.lower_rescale_count)

        metrics["in_range_pct"] = Decimal(
            strat.total_in_range_minutes / strat.total_minutes) if strat.total_minutes > 0 else Decimal(0)
        metrics["in_range_locked_pct"] = Decimal(
            strat.total_in_range_and_in_lock_minutes / strat.total_in_range_minutes) if strat.total_in_range_minutes > 0 else Decimal(
            0)
        metrics["out_range_locked_pct"] = Decimal(
            strat.total_out_of_range_and_in_lock_minutes / (strat.total_minutes - strat.total_in_range_minutes)) if (
                                                                                                                                strat.total_minutes - strat.total_in_range_minutes) > 0 else Decimal(
            0)
        metrics["lock_pct"] = Decimal((
                                                  strat.total_out_of_range_and_in_lock_minutes + strat.total_in_range_and_in_lock_minutes) / strat.total_minutes) if strat.total_minutes > 0 else Decimal(
            0)
        metrics["out_of_fund_date"] = Decimal(
            strat.out_of_fund_date.timestamp()) if strat.out_of_fund_date is not None else None

        return metrics
    except Exception as e:
        print(f"error for {params.range_strategy.value}, shape: {shape}, "
              f"ratio: +{upper_ratio}/-{lower_ratio}, half_gap: {half_gap}, "
              f"{str(bull_params)}, {str(bear_params)}")
        raise e
    # plot_position_return_decomposition(actuator.account_status_df, actuator.token_prices[_base_token.name], market_key)


@dataclass
class RescaleParam:
    bull_lower_spread: int
    bull_upper_spread: int
    bear_lower_spread: int
    bear_upper_spread: int
    init_tick_spread: int

    def initial_swap(self) -> bool:
        return self.init_tick_spread != 0


def _run_one(bull, bear, tp: TestParams, gp: GlobalParams, data, usdc_price_data, shape, upper_ratio,
             lower_ratio, half_gap, eth_share, daily_ema, deploy) -> Tuple[str, Dict[str, Decimal]]:
    """Pool worker: one (params, gap, eth_share, deploy) combination. Top level so it pickles under spawn."""
    return tp.report_name, run_test(bull, bear, tp, gp, data, usdc_price_data, shape=shape,
                                    upper_ratio=upper_ratio, lower_ratio=lower_ratio, half_gap=half_gap,
                                    eth_share=eth_share, daily_ema=daily_ema, deploy=deploy)


def process_for_date(csd: datetime, dsd: date, ded: date, id: str, flip_param_dates: list[datetime]):
    demeter.Formats.global_num_format = ".4g"  # change out put formats here
    usdc = TokenInfo(name="usdc", decimal=6)
    eth = TokenInfo(name="eth", decimal=18)
    wstEth = TokenInfo(name="wsteth", decimal=18)
    btc = TokenInfo(name="btc", decimal=8)
    cbbtc = TokenInfo(name="cbbtc", decimal=8)
    usdt = TokenInfo(name="usdt", decimal=6)
    dai = TokenInfo(name="dai", decimal=18)
    load_eth_price = False
    _is_stable = False
    load_btc_price = False
    base_token, quote_token, init_quote = eth, usdc, Decimal(100000)  #  USDC

    # base_token, quote_token, init_quote = eth, usdc, Decimal(100000)  # DCA USDC

    # base_token, quote_token, init_quote = btc, eth, Decimal(1)  # ETH
    # base_token, quote_token, init_quote = eth, btc, Decimal(1)  # BTC
    # base_token, quote_token, init_quote = cbbtc, btc, Decimal(1)  # BTC/cbBTC
    # base_token, quote_token, init_quote = usdt, usdc, Decimal(2000)  # USDC/USDT
    # base_token, quote_token, init_quote = wstEth, eth, Decimal(100)  # wstETH/ETH
    # base_token, quote_token, init_quote = dai, usdt, Decimal(100000)  # dai/usdt

    # token0, token1 = usdc, usdt
    # contract_address, fee, chain_name, _is_stable = "0x3416cF6C708Da44DB2624D63ea0AAef7113527C6", 0.01, ChainType.ethereum.name, True  # usdc/usdt  2021-11-20
    # token0, token1 = btc, cbbtc
    # contract_address, fee, chain_name, _is_stable, load_btc_price = "0xe8f7c89C5eFa061e340f2d2F206EC78FD8f7e124", 0.01, ChainType.ethereum.name, True, True  # wbtc/cbbtc  2021-09-20
    # token0, token1 = wstEth, eth
    # contract_address, fee, chain_name, _is_stable, load_eth_price = "0x109830a1AAaD605BbF02a9dFA7B0B92EC2FB7dAa", 0.01, ChainType.ethereum.name, True, True  # wstEth/eth  2022-08-25
    # token0, token1 = dai, usdt
    # contract_address, fee, chain_name, _is_stable = "0x48DA0965ab2d2cbf1C17C09cFB5Cbe67Ad5B1406", 0.01, ChainType.ethereum.name, True  # dai/usdt  2022-07-20

    # token0, token1 = btc, eth
    # contract_address, fee, chain_name, load_eth_price = "0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0", 0.05, ChainType.ethereum.name, True # wbtc/weth  2021-05-13
    # contract_address, fee, chain_name = "0x2f5e87C9312fa29aed5c179E456625D79015299c", 0.05, ChainType.arbitrum.name # wbtc/weth
    # contract_address, fee, chain_name = "0xCBCdF9626bC03E24f779434178A73a0B4bad62eD", 0.3, ChainType.ethereum.name # wbtc/weth

    ## negative tick: token0 is worthless than token1

    token0, token1 = usdc, eth
    contract_address, fee, chain_name = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", 0.05, ChainType.ethereum.name  # weth/usdc
    # token0, token1 = eth, usdc
    # contract_address, fee, chain_name = "0xC6962004f452bE9203591991D15f6b388e09E8D0", 0.05, ChainType.arbitrum.name  # weth/usdc
    # USD conversion for the "... USD" result columns: quote is already USD for a stable quote, so only
    # an eth or btc quote needs the matching usdc pool price. Overrides the per-pool flags above.
    load_eth_price = quote_token.name == "eth"
    load_btc_price = quote_token.name == "btc"
    _init_quote_usdc = init_quote * INIT_PRICE
    _dca_usdc_amount = Decimal(10000)

    # pool = UniV3Pool(btc, eth, _fee, _quote_token)
    _starting_mark_price = Decimal(20)

    _tick_spacing = 1 if _is_stable else int(fee * 200)  # 10  # should simply be fee * 200
    _aggressive = True
    _compound = False
    # liquidity shape to backtest, one column of the shape sheet. switch it by hand
    # _shape: str = "triangle"
    # _shape: str = "gaussian"
    # _shape: str = "exponential"
    # _shape: str = "camel"
    # _shape: str = "uniform"
    # _shape: str = "inverted_triangle"
    # _shape: str = "inverted_gaussian"
    # spec sheet (谷型LP規格書 v6): 8+8 bands, ±20%, no centre gap, see ETH_SHARE_TODO.md
    _shapes: List[str] = ["inverted_gaussian"]
    # _shapes: List[str] = ["inverted_gaussian_9"]
    # _shape: str = "inverted_exponential"
    # how far the outermost band reaches above / below the price, switch by hand.
    # 0.50 / 0.50 is price symmetric (+50% / -50%). MIRROR_TICKS copies the upper side's tick
    # count downwards, the original gamma layout (+50% / -33% at 0.50)
    # every upper ratio to sweep; each is one more row per gap x frequency
    # _upper_ratios: List[Decimal] = [Decimal(r) for r in ("0.10", "0.20", "0.30", "0.40", "0.50")]
    _upper_ratios: List[Decimal] = [Decimal(r) for r in ("0.20",)]
    # _upper_ratios: List[Decimal] = [Decimal(r) for r in ("0.20", "0.50")]
    # _lower_ratio: Decimal | str = Decimal("0.50")
    # MIRROR_TICKS: -33% at +50% (same ticks); MIRROR_PRICE: -50% at +50% (same percentage)
    # every lower-side rule to sweep: MIRROR_PRICE = true -20% (spec sheet), MIRROR_TICKS = same tick count
    # as the upper side (about -17% at +20%)
    _lower_ratios: List[Decimal | str] = [MIRROR_PRICE]  # spec sheet; add MIRROR_TICKS to compare (2024 -6.4pt, 2025 flat)
    # _lower_ratio: Decimal | str = MIRROR_TICKS  # MIRROR_PRICE (true +-50%) tested 2025: worse, see GAP_BANDS_FINDINGS.md
    # centre gap each side, in tick spacings. 0 = sides meet at the centre tick, 1 = one spacing
    # above and below, BAND_GAP = one 17-band slot (the old gamma gap, 480 ticks total at 50%)
    # "4+" = same 4 spacing gap, but sized as if gap-less and pushed outward (outer edge = gap + 50%)
    # "1+" is skipped: at 50% on a spacing 10 pool it rounds to the same bands as 1
    # _centre_half_gaps: List[int | str] = [1, 4, "4+", 12, "12+"]
    _centre_half_gaps: List[int | str] = [0]  # spec sheet has no centre gap; inverted shapes have zero centre weight so 0 is valid
    # _centre_half_gaps: List[int | str] = ["12+"]
    # spec sheet s: ETH share of total value when the bands are (re)built. None = original behaviour
    # (range geometry decides, ~50/50 on a symmetric range); 0.7 = ETH 70% / USDC 30%
    # EMA_SHARE = spec sheet rule (0.7 above EMA100, else 0.5). sgeo / s70 for 2025 are in the earlier
    # gamma-pdfv6-...-sgeo+s70 folder; s50 is the floor the EMA rule falls back to
    _eth_shares: List[Decimal | str | None] = [EMA_SHARE]
    # DEPLOY_FULL = always 100% in the bands (the runs so far); DEPLOY_SIGNAL = spec sheet 2.2 / 2.3 engine
    _deploy_modes: List[str] = [DEPLOY_SIGNAL]
    # parallel runs; each worker copies the minute data, ~4 min per run on the 2025 set
    _workers = 5
    _folder_prefix = (f"gamma-pdfv6-{'+'.join(SHAPE_LABELS.get(sh, sh) for sh in _shapes)}-gap-up{ratio_label(_upper_ratios[0])}~{ratio_label(_upper_ratios[-1])}-"
                      f"dn{'+'.join(ratio_label(lr) for lr in _lower_ratios)}-"
                      f"{'+'.join(share_label(es) for es in _eth_shares)}-{'+'.join(_deploy_modes)}-"
                      f"{token0.name.lower()}{token1.name.lower()}-{quote_token.name.lower()}")
    _dca_add_if_non_empty = False
    _dca_timing = DcaTiming.none
    _dca_addon_price_percent = ZERO  # Decimal(0.5)
    _dca_addon_amount_percent = ZERO
    _dca_addition = DcaAddition.none

    gp = GlobalParams(token0=token0, token1=token1, fee=fee, init_quote=init_quote,
                      quote_token=quote_token, base_token=base_token,
                      chain_name=chain_name, contract_address=contract_address, swap_fee=False,
                      dca_usdc_amount=_dca_usdc_amount,
                      dca_add_if_non_empty=_dca_add_if_non_empty,
                      dca_add_timing=_dca_timing,
                      init_quote_usdc=_init_quote_usdc,
                      dca_addon_price_percent=_dca_addon_price_percent,
                      dca_addon_amount_percent=_dca_addon_amount_percent,
                      dca_addition=_dca_addition)


    # l: List[int] = list(range(1, 11)) # 1 - 10 用來當tick spread
    # l: List[int] = list(range(1, 3))  # 1 - 10 用來當tick spread
    # l: List[int] = [140,95, 48]
    # l: List[int] = [58]
    l: List[int] = [410]
    _remix_spreads = list(map(lambda i: RescaleParam(init_tick_spread=i, bull_lower_spread=i, bull_upper_spread=i,
                                                     bear_lower_spread=i, bear_upper_spread=i, ), l))

    # _rescale_frequencies = [RescaleFrequency.minute5, RescaleFrequency.minute15, RescaleFrequency.minute30, RescaleFrequency.hourly]  # RescaleFrequency.hourly,
    # _rescale_frequencies = [RescaleFrequency.hourly, RescaleFrequency.hour4, RescaleFrequency.hour8,
    #                         RescaleFrequency.hour12, RescaleFrequency.daily]
    _rescale_frequencies = [RescaleFrequency.daily]  # spec sheet judges on the daily close; 8h/12h were worse in 2024
    # _rescale_frequencies = [RescaleFrequency.hour8, RescaleFrequency.hour12, RescaleFrequency.daily]
    # _rescale_frequencies = [RescaleFrequency.minute5, RescaleFrequency.minute15, ]
    # _rescale_frequencies = [RescaleFrequency.minute30, RescaleFrequency.hourly]  # RescaleFrequency.hourly,

    _init_type: int = 1
    _param_with_offset = RemixDAOParams(  # offset + range
        tick_spread_upper=60,
        tick_spread_lower=60,
        tick_upper_boundary_offset=0,
        tick_lower_boundary_offset=0,
        rescale_tick_upper_boundary_offset=10,
        rescale_tick_lower_boundary_offset=10,
        # rescale_tick_tolerance=10,
        init_tick_spread=120,
        tick_spacing=_tick_spacing,
        tick_gap_lower=1,
        tick_gap_upper=1, )
    _param_no_offset = RemixDAOParams(  # offset + range
        tick_spread_upper=60,
        tick_spread_lower=60,
        tick_upper_boundary_offset=0,
        tick_lower_boundary_offset=0,
        rescale_tick_upper_boundary_offset=0,
        rescale_tick_lower_boundary_offset=0,
        # rescale_tick_tolerance=10,
        init_tick_spread=120,
        tick_spacing=_tick_spacing,
        tick_gap_lower=1,
        tick_gap_upper=1, )

    _cmp = ""
    if _compound:
        _cmp = "_cmp"
    # csd = _cal_start_date
    # dsd = _data_start_date
    # ded = _data_end_date

    folder = f"result/{_folder_prefix}-{init_quote}-{csd.strftime("%Y%m%d")}-{ded.strftime("%Y%m%d")}"
    Path(folder).mkdir(parents=True, exist_ok=True)
    parameters: List[Tuple[RemixDAOParams, RemixDAOParams, TestParams, int | str, Decimal, str]] = []

    for rescale_frequency in _rescale_frequencies:
     for shape in _shapes:
      for upper_ratio in _upper_ratios:
       for half_gap in _centre_half_gaps:
        for spread in _remix_spreads:
            # lower = upper
            bull_no_offset = copy.copy(_param_no_offset)
            bull_with_offset = copy.copy(_param_with_offset)
            bear_no_offset = copy.copy(_param_no_offset)
            bear_with_offset = copy.copy(_param_with_offset)

            # init: int | None = None
            # if len(spread) == 1:
            #     lower = upper = spread[0]
            # elif len(spread) == 2:
            #     lower = spread[0]
            #     upper = spread[1]
            # else:
            #     init = spread[0]
            #     lower = spread[1]
            #     upper = spread[2]

            bull_with_offset.tick_spread_lower = spread.bull_lower_spread
            bull_with_offset.tick_spread_upper = spread.bull_upper_spread
            bull_no_offset.tick_spread_lower = spread.bull_lower_spread
            bull_no_offset.tick_spread_upper = spread.bull_upper_spread
            bear_with_offset.tick_spread_lower = spread.bear_lower_spread
            bear_with_offset.tick_spread_upper = spread.bear_upper_spread
            bear_no_offset.tick_spread_lower = spread.bear_lower_spread
            bear_no_offset.tick_spread_upper = spread.bear_upper_spread

            # if init is not None:
            #     with_offset.init_tick_spread = init
            #     no_offset.init_tick_spread = init
            bull_with_offset.init_tick_spread = spread.init_tick_spread
            bull_no_offset.init_tick_spread = spread.init_tick_spread
            bear_with_offset.init_tick_spread = spread.init_tick_spread
            bear_no_offset.init_tick_spread = spread.init_tick_spread

            start_with_bull_param: bool = True

            # parameters.append((bull_with_offset, bear_with_offset,
            #                    TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1,
            #                               report_name=f"{init_quote}{quote_token.name}_{RangeStrategy.remix_dao.name}_with_offset_{bull_with_offset.init_tick_spread}_{bull_with_offset.tick_spread_lower}-{bull_with_offset.tick_spread_upper}_{bear_with_offset.tick_spread_lower}-{bear_with_offset.tick_spread_upper}_{rescale_frequency.name}-{gp.dca_add_if_non_empty}",
            #                               indicator_length_hr=1, to_swap=False,
            #                               aggressive=_aggressive, compound=_compound,
            #                               rescale_frequency=rescale_frequency,
            #                               cal_start_datetime=csd, data_start_date=dsd, data_end_date=ded, folder=folder,
            #                               initial_swap=spread.initial_swap(), flip_param_dates=flip_param_dates,
            #                               start_with_bull_param=start_with_bull_param)
            #                    ))
            parameters.append((bull_no_offset, bear_no_offset,
                               TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1,
                                          # report_name=f"{init_quote}{quote_token.name}_{RangeStrategy.remix_dao.name}_no_offset_{bull_no_offset.init_tick_spread}_{bull_no_offset.tick_spread_lower}-{bull_no_offset.tick_spread_upper}_{bear_no_offset.tick_spread_lower}-{bear_no_offset.tick_spread_upper}_{rescale_frequency.name}-{gp.dca_add_if_non_empty}",
                                          report_name=f"{init_quote}{quote_token.name}_{SHAPE_LABELS.get(shape, shape)}_up{ratio_label(upper_ratio)}_g{gap_label(half_gap)}_{rescale_frequency}",
                                          indicator_length_hr=1, to_swap=False,
                                          aggressive=_aggressive, compound=_compound,
                                          rescale_frequency=rescale_frequency,
                                          cal_start_datetime=csd, data_start_date=dsd, data_end_date=ded, folder=folder,
                                          initial_swap=spread.initial_swap(), flip_param_dates=flip_param_dates,
                                          start_with_bull_param=start_with_bull_param,
                                          initial_type=_init_type,
                                          starting_mark_price=_starting_mark_price,),
                               half_gap, upper_ratio, shape))
            # parameters.append((no_offset,
            #                    TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1,
            #                               report_name=f"{init_quote}{quote_token.name}_{RangeStrategy.remix_dao.name}_rebalance_{no_offset.init_tick_spread}_{no_offset.tick_spread_lower}_{no_offset.tick_spread_upper}_{rescale_frequency.name}{_cmp}",
            #                               indicator_length_hr=1, to_swap=True,
            #                               aggressive=_aggressive, compound=_compound, rescale_frequency=rescale_frequency,
            #                               cal_start_datetime=csd, data_start_date=dsd, data_end_date=ded, folder=folder,
            #                               initial_swap=initial_swap, flip_param_dates=flip_param_dates,
            #                               start_with_bull_param=start_with_bull_param)
            #                    ))

            # upper = lower * 2
            # no_offset_1 = copy.copy(_param_no_offset)
            # with_offset_1 = copy.copy(_param_with_offset)
            # lower_spread = spread
            # upper_spread = spread * 2
            # with_offset_1.tick_spread_lower = lower_spread
            # with_offset_1.tick_spread_upper = upper_spread
            # no_offset_1.tick_spread_lower = lower_spread
            # no_offset_1.tick_spread_upper = upper_spread

            # parameters.append((with_offset_1,
            #                    TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1,
            #                               report_name=f"{init_quote}{quote_token.name}_{RangeStrategy.remix_dao.name}_with_offset_{with_offset_1.init_tick_spread}_{lower_spread}_{upper_spread}_{rescale_frequency.name}{_cmp}",
            #                               indicator_length_hr=1, to_swap=False,
            #                               aggressive=_aggressive, compound=_compound, rescale_frequency=rescale_frequency,
            #                               cal_start_datetime=csd, data_start_date=dsd, data_end_date=ded, folder=folder,
            #             #                               initial_swap=initial_swap)
            #                    ))
            # parameters.append((no_offset_1,
            #                    TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1,
            #                               report_name=f"{init_quote}{quote_token.name}_{RangeStrategy.remix_dao.name}_without_offset_{no_offset_1.init_tick_spread}_{lower_spread}_{upper_spread}_{rescale_frequency.name}{_cmp}",
            #                               indicator_length_hr=1, to_swap=False,
            #                               aggressive=_aggressive, compound=_compound, rescale_frequency=rescale_frequency,
            #                               cal_start_datetime=csd, data_start_date=dsd, data_end_date=ded, folder=folder,
            #             #                               initial_swap=initial_swap)
            #                    ))
            # parameters.append((no_offset_1,
            #                    TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1,
            #                               report_name=f"{init_quote}{quote_token.name}_{RangeStrategy.remix_dao.name}_rebalance_{no_offset_1.init_tick_spread}_{lower_spread}_{upper_spread}_{rescale_frequency.name}{_cmp}",
            #                               indicator_length_hr=1, to_swap=True,
            #                               aggressive=_aggressive, compound=_compound, rescale_frequency=rescale_frequency,
            #                               cal_start_datetime=csd, data_start_date=dsd, data_end_date=ded, folder=folder,
            #             #                               initial_swap=initial_swap)
            #                    ))

            # lower = upper * 2
            # no_offset_2 = copy.copy(_param_no_offset)
            # with_offset_2 = copy.copy(_param_with_offset)
            # lower_spread = spread * 2
            # upper_spread = spread
            # with_offset_2.tick_spread_lower = lower_spread
            # with_offset_2.tick_spread_upper = upper_spread
            # no_offset_2.tick_spread_lower = lower_spread
            # no_offset_2.tick_spread_upper = upper_spread

            # parameters.append((with_offset_2,
            #                    TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1,
            #                               report_name=f"{init_quote}{quote_token.name}_{RangeStrategy.remix_dao.name}_with_offset_{with_offset_2.init_tick_spread}_{lower_spread}_{upper_spread}_{rescale_frequency.name}{_cmp}",
            #                               indicator_length_hr=1, to_swap=False,
            #                               aggressive=_aggressive, compound=_compound, rescale_frequency=rescale_frequency,
            #                               cal_start_datetime=csd, data_start_date=dsd, data_end_date=ded, folder=folder,
            #             #                               initial_swap=initial_swap)
            #                    ))
            # parameters.append((no_offset_2,
            #                    TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1,
            #                               report_name=f"{init_quote}{quote_token.name}_{RangeStrategy.remix_dao.name}_without_offset_{no_offset_2.init_tick_spread}_{lower_spread}_{upper_spread}_{rescale_frequency.name}{_cmp}",
            #                               indicator_length_hr=1, to_swap=False,
            #                               aggressive=_aggressive, compound=_compound, rescale_frequency=rescale_frequency,
            #                               cal_start_datetime=csd, data_start_date=dsd, data_end_date=ded, folder=folder,
            #             #                               initial_swap=initial_swap)
            #                    ))
            # parameters.append((no_offset_2,
            #                    TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1,
            #                               report_name=f"{init_quote}{quote_token.name}_{RangeStrategy.remix_dao.name}_rebalance_{no_offset_2.init_tick_spread}_{lower_spread}_{upper_spread}_{rescale_frequency.name}{_cmp}",
            #                               indicator_length_hr=1, to_swap=True,
            #                               aggressive=_aggressive, compound=_compound, rescale_frequency=rescale_frequency,
            #                               cal_start_datetime=csd, data_start_date=dsd, data_end_date=ded, folder=folder,
            #             #                               initial_swap=initial_swap)
            #                    ))
    # preload data to speed things up
    print(f"preload data {dsd.strftime("%Y%m%d")} ~ {ded.strftime("%Y%m%d")}")
    market_key = MarketInfo("lp")
    pool = UniV3Pool(token0, token1, fee, quote_token)
    market = UniLpMarketV2(market_key, pool)
    market.data_path = f"../real-data/{contract_address}"
    # Random short sleep (5–10 seconds) to stagger parallel preload calls and avoid rate limits / I/O spikes
    try:
        _delay = random.uniform(2, 6)
        print(f"stagger preload: sleeping {_delay:.2f}s before loading data for {contract_address}")
        time.sleep(_delay)
    except Exception:
        # If anything goes wrong, proceed without sleeping
        pass

    market.load_data(chain_name, contract_address, dsd, ded)
    # daily closes + EMA100 for EMA_SHARE, with EMA_WARMUP_DAYS of history before the window so the
    # EMA is settled on day one (ema_share_for judges on the last completed day)
    daily_ema = None
    if EMA_SHARE in _eth_shares or DEPLOY_SIGNAL in _deploy_modes:
        warm = UniLpMarketV2(MarketInfo("warm"), UniV3Pool(token0, token1, fee, quote_token))
        warm.data_path = market.data_path
        # the pool's minute data starts 2021-05-06, so a 2022 window gets ~240 warm-up days instead of 360
        warm_start = max(dsd - timedelta(days=EMA_WARMUP_DAYS), POOL_FIRST_DATA_DATE)
        warm.load_data(chain_name, contract_address, warm_start, dsd - timedelta(days=1))
        daily_ema = daily_ema_frame(pd.concat([warm.data.price, market.data.price]))
        first, last = daily_ema.loc[pd.Timestamp(dsd) - timedelta(days=1)], daily_ema.iloc[-1]
        print(f"ema{EMA_SPAN}: {len(daily_ema)} daily closes, day before window close {first['close']:.0f} ema {first['ema']:.0f} F {first['F']:.3f}, "
              f"last close {last['close']:.0f} ema {last['ema']:.0f} F {last['F']:.3f}")
        window = daily_ema.loc[pd.Timestamp(dsd):]
        print(f"signal engine F over the window: mean {window['F'].mean():.3f}, days at 0: {(window['F'] == 0).sum()}, "
              f"days at 1: {(window['F'] == 1).sum()}, changes: {(window['F'].diff().fillna(0) != 0).sum()}")

    usdc_price_data = None
    if load_eth_price:
        contract_address_usdc = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
        market_key_usdc = MarketInfo("usdc")
        pool_usdc = UniV3Pool(usdc, eth, fee, usdc)
        market_usdc = UniLpMarketV2(market_key_usdc, pool_usdc)
        market_usdc.data_path = f"../real-data/{contract_address_usdc}"
        market_usdc.load_data(chain_name, contract_address_usdc, dsd, ded)
        usdc_price_data = market_usdc.data
    elif load_btc_price:
        contract_address_usdc = "0x56534741CD8B152df6d48AdF7ac51f75169A83b2"
        market_key_usdc = MarketInfo("usdc")
        pool_usdc = UniV3Pool(btc, usdc, fee, usdc)
        market_usdc = UniLpMarketV2(market_key_usdc, pool_usdc)
        market_usdc.data_path = f"../real-data/{contract_address_usdc}"
        market_usdc.load_data(chain_name, contract_address_usdc, dsd, ded)
        usdc_price_data = market_usdc.data
    else:
        # create a pd.DataFrame with column "price" of 1 for every minute from dsd to ded
        index = pd.date_range(start=dsd, end=datetime.combine(ded, datetime.max.time()), freq="min")
        usdc_price_data = pd.DataFrame(index=index, data={"price": ONE})

    # result = list(map(lambda p: (p[2].report_name, run_test(p[0], p[1], p[2], gp, market.data, market_usdc.data)), parameters))
    # one run per (lower rule, eth_share, deploy) for every (shape, ratio, gap, frequency) row; the report
    # name gets their labels
    def _with_share(p, lower_ratio, eth_share, deploy):
        tp = copy.copy(p[2])
        tp.report_name = f"{p[2].report_name}_dn{ratio_label(lower_ratio)}_{share_label(eth_share)}_{deploy}"
        return (p[0], p[1], tp, p[3], p[4], p[5], eth_share, deploy, lower_ratio)
    parameters = [_with_share(p, lr, es, dm) for p in parameters for lr in _lower_ratios
                  for es in _eth_shares for dm in _deploy_modes]
    with multiprocessing.Pool(_workers) as pool:
        result = pool.starmap(_run_one, [
            (p[0], p[1], p[2], gp, market.data, usdc_price_data, p[5], p[4],
             p[4] if p[8] == MIRROR_PRICE else p[8], p[3], p[6], daily_ema, p[7])
            for p in parameters])
    export_stable_apr_results(f"{folder}/apr_remix_{init_quote}_results.csv", result)
    pass


def _self_check():
    half = Decimal("0.5")
    bands = build_gap_bands(half, half, 10, 4, 1)
    assert bands[4] == (-10, 10) and bands[5][0] == 10 and bands[3][1] == -10, bands
    assert bands[-1][1] == 10 + 4 * 1010 and bands[0][0] == -10 - 4 * 1730, bands  # +50% / -50%
    tick_sym = build_gap_bands(half, MIRROR_TICKS, 10, 4, 1)
    assert tick_sym[0][0] == -tick_sym[-1][1] == -4050, tick_sym  # MIRROR_TICKS mirrors the upper side
    band_gap = build_gap_bands(half, MIRROR_TICKS, 10, 4, BAND_GAP)
    assert band_gap[4] == (-240, 240) and band_gap[-1][1] == 4080, band_gap  # same as gamma bands9 at 50%
    assert band_gap[5] == (240, 1200) and band_gap[0] == (-4080, -3120), band_gap
    assert build_gap_bands(Decimal("0.3"), MIRROR_TICKS, 10, 4, BAND_GAP)[4] == (-150, 150)
    cfg = build_shape_config("inverted_gaussian_9", half, half, 10, 0)
    assert len(cfg) == 8 and cfg[3][1] == 0 and cfg[4][0] == 0, cfg  # centre dropped, sides meet at 0
    assert abs(sum(c[2] for c in cfg[:4]) - 1) < Decimal("1e-6"), cfg  # each side spends its whole token
    # swap_to_value_share: after the swap, base holds exactly base_share of total value
    for base, quote, price, want in [(Decimal(0), Decimal(100000), Decimal(2000), Decimal("0.7")),
                                     (Decimal(25), Decimal(50000), Decimal(2000), Decimal("0.7")),
                                     (Decimal(50), Decimal(0), Decimal(2000), Decimal("0.5")),
                                     (Decimal(35), Decimal(30000), Decimal(2000), Decimal("0.7"))]:
        b2s, q2s = swap_to_value_share(base, quote, price, want)
        assert b2s == ZERO or q2s == ZERO, (b2s, q2s)
        base_after, quote_after = base - b2s + q2s / price, quote + b2s * price - q2s
        got = base_after * price / (base_after * price + quote_after)
        assert abs(got - want) < Decimal("1e-9") and base_after >= ZERO and quote_after >= ZERO, (base, quote, got)
    assert share_label(None) == "sgeo" and share_label(Decimal("0.7")) == "s70" and share_label(Decimal("0.5")) == "s50"
    assert share_label(EMA_SHARE) == "sema100"
    # ema rule: judged on the last completed day; rising tail -> above ema -> 0.7, falling tail -> 0.5
    idx = pd.date_range("2024-01-01", periods=400 * 24, freq="h")
    minute = pd.Series([2000.0] * (350 * 24) + list(range(2000, 2000 + 50 * 24)), index=idx)
    daily = daily_ema_frame(minute)
    assert len(daily) == 400 and abs(daily["ema"].iloc[349] - 2000) < 1e-6, daily["ema"].iloc[349]
    share, day, close, ema = ema_share_for(daily, datetime(2025, 2, 4, 8, 0))
    assert share == Decimal("0.7") and day == pd.Timestamp("2025-02-03") and close > ema, (share, day, close, ema)
    assert ema_share_for(daily, datetime(2024, 12, 1, 0, 0))[0] == Decimal("0.5")  # flat: close == ema -> 0.5
    # signal engine: flat -> never armed (close == ema) so F 0; +20% jump -> 3 confirm days then stage 1
    # (one stage a day, even though >= low x 1.15) so F 0.25; then a -21% close -> EMA exit so F 0
    days = pd.date_range("2024-01-01", periods=406, freq="D")
    path = pd.Series([2000.0] * 400 + [2400.0] * 3 + [1900.0] * 3, index=days)
    eng = daily_ema_frame(path)
    assert (eng["F"].iloc[:402] == 0).all(), eng["F"].iloc[398:403].tolist()
    assert eng["F"].iloc[402] == 0.25 and eng["F"].iloc[403] == 0.0, eng["F"].iloc[400:406].tolist()
    assert target_fraction_for(eng, datetime(2025, 2, 7, 0, 0)) == Decimal("0.25")  # judged on 2025-02-06 = day 402
    assert target_fraction_for(eng, datetime(2025, 2, 8, 8, 0)) == Decimal("0")
    acct = VirtualAccount(100)
    for c in [2000, 2000, 2000, 2400, 2400]:   # day 0 close == ema -> not armed; 2400 > ema re-arms, no buy
        acct.step(c, 2000)
    assert acct.armed and acct.stage == 0 and acct.confirm == 2 and acct.deployed == 0, acct
    acct.step(2100, 2000)                        # third confirm day at >= +5%, but < +8.33% -> stage 1 only
    assert acct.stage == 1 and acct.deployed == 0.25 and acct.centre == 2100, acct
    acct.step(2240, 2000)                        # >= +11.67%, but one stage a day -> stage 2
    assert acct.stage == 2 and acct.deployed == 0.5, acct
    acct.step(2180, 2000)                        # pullback below the stage 3 band: keeps stage 2, no downgrade
    assert acct.stage == 2 and acct.deployed == 0.5, acct
    acct.step(2240, 2000)                        # back above -> stage 3
    assert acct.stage == 3 and acct.deployed == 0.75, acct


if __name__ == "__main__":
    _self_check()

    date_ranges: List[tuple[datetime, date, date, str, list[datetime]]] = [
        # (_cal_start_date, _data_start_date, _data_end_date)
        # total-market
        # (datetime(2023, 10, 16, 0, 0, 0), date(2023, 10, 6), date(2024, 9, 3), []),
        # bull-market
        # (datetime(2023, 10, 16, 0, 0, 0), date(2023, 10, 6), date(2024, 5, 26), []),
        # bear-market
        # (datetime(2024, 5, 27, 0, 0, 0), date(2024, 5, 1), date(2024, 9, 3), []),
        # 20240311 - 20240903
        # (datetime(2024, 3, 11, 0, 0, 0), date(2024, 3, 11), date(2024, 9, 3), []),
        # BTC/ETH BEAR 20220613 - 20220912
        # (datetime(2022, 6, 13, 0, 0, 0), date(2022, 6, 13), date(2022, 9, 12), []),
        # 20240311 ~ 20240903
        # (datetime(2024, 3, 11, 0, 0, 0), date(2024, 3, 11), date(2024, 9, 3), []),

        # ISAO cases
        # (datetime(2024, 7, 1, 0, 0, 0), date(2024, 7, 1), date(2024, 11, 15), "dca", []),
        #  2021/05/04~2024/09/30
        # (datetime(2021, 5, 13, 0, 0, 0), date(2021, 5, 13), date(2024, 11, 11), "dca", []),
        #  2021/05/04~2021/12/31
        # (datetime(2021, 5, 13, 0, 0, 0), date(2021, 5, 13), date(2021, 12, 31), "dca", []),
        #  2022/01/01~2022/12/31
        (datetime(2022, 1, 1, 0, 0, 0), date(2022, 1, 1), date(2022, 12, 31), "", []),
        # (datetime(2022, 1, 1, 0, 0, 0), date(2022, 1, 1), date(2022, 7, 1), "", []),
        #  2023/01/01~2023/12/31
        (datetime(2023, 1, 1, 0, 0, 0), date(2023, 1, 1), date(2023, 12, 31), "", []),
         # 2024/01/01~2024/09/30
        (datetime(2024, 1, 1, 0, 0, 0), date(2024, 1, 1), date(2024, 12, 31), "", []),
        (datetime(2025, 1, 1, 0, 0, 0), date(2025, 1, 1), date(2025, 12, 31), "", []),
        # (datetime(2022, 1, 1, 0, 0, 0), date(2022, 1, 1), date(2025, 12, 31), "", []),


        # (datetime(2024, 1, 1, 0, 0, 0), date(2024, 1, 1), date(2025, 1, 1), "", []),

        # first btc/cbbtc
        # (datetime(2025, 1, 1, 0, 0, 0), date(2025, 1, 1), date(2025, 11, 9), "dca", []),
        # first usdc/usdt
        # (datetime(2021, 11, 20, 0, 0, 0), date(2021, 11, 20), date(2021, 12, 31), "dca", []),
        # full usdc/usdt
        # (datetime(2021, 11, 20, 0, 0, 0), date(2021, 11, 20), date(2025, 11, 9), "dca", []),
        # short
        # (datetime(2025, 11, 27, 0, 0, 0), date(2025, 11, 27), date(2025, 11, 30), "dca", []),
        # first wstETH/ETH
        # (datetime(2022, 8, 25, 0, 0, 0), date(2022, 8, 25), date(2022, 12, 31), "dca", []),
        # full wstETH/ETH
        # (datetime(2022, 8, 25, 0, 0, 0), date(2022, 8, 25), date(2025, 11, 9), "dca", []),
        # first DAI/USDT
        # (datetime(2022, 7, 20, 0, 0, 0), date(2022, 7, 20), date(2022, 12, 31), "dca", []),
        # full DAI/USDT
        # (datetime(2022, 7, 20, 0, 0, 0), date(2022, 7, 20), date(2025, 11, 9), "dca", []),
        # (datetime(2022, 1, 1, 0, 0, 0), date(2022, 1, 1), date(2022, 12, 31), "dca", []),
        # (datetime(2023, 1, 1, 0, 0, 0), date(2023, 1, 1), date(2023, 12, 31), "dca", []),
        # (datetime(2024, 1, 1, 0, 0, 0), date(2024, 1, 1), date(2024, 12, 31), "dca", []),
        # (datetime(2025, 1, 1, 0, 0, 0), date(2025, 1, 1), date(2025, 11, 9), "dca", []),

    ]

    threads = map(lambda dr: multiprocessing.Process(target=process_for_date, args=dr), date_ranges)
    for t in threads:
        t.start()

    for t in threads:
        t.join()
