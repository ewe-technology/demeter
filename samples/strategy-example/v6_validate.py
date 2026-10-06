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
import traceback
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
    # EXP-011: Base USDC/cbBTC 0.05% (the deck's "Growth" pool)
    "0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef": (("usdc", 6), ("btc", 8), 1, 0.05, "../base-data"),
    # EXP-015: Base WETH/USDC 0.3% (token0 is WETH, tick spacing 60)
    "0x6c561b446416e1a00e8e93e221854d6ea4171372": (("eth", 18), ("usdc", 6), 0, 0.3, "../base-data"),
    # EXP-020 holdout: mainnet LINK/USDC 0.3% (token0 LINK), an asset no strategy run has touched
    "0xfad57d2039c21811c8f2b5d5b65308aa99d31559": (("link", 18), ("usdc", 6), 0, 0.3, "../holdout-data"),
    # EXP-021 holdout: mainnet LINK/WETH 0.3% and UNI/WETH 0.3% (token0 the alt, WETH the quote / numeraire)
    "0xa6cc3c2531fdaa6ae1a3ca84c2855806728693e8": (("link", 18), ("eth", 18), 0, 0.3, "../holdout-data"),
    "0x1d42064fc4beb5f8aaf85f4617ae8b3b5b8bd801": (("uni", 18), ("eth", 18), 0, 0.3, "../holdout-data"),
    # EXP-022 holdout: Arbitrum WETH/USDC 0.05% (native USDC; files from the team's Demeter S3 bucket) and mainnet
    # AAVE/WETH 0.3%. Gas is still priced as mainnet (reported only).
    "0xc6962004f452be9203591991d15f6b388e09e8d0": (("eth", 18), ("usdc", 6), 0, 0.05, "../holdout-data"),
    "0x5ab53ee1d50eef2c1dd3d5402789cd27bb52c1bb": (("aave", 18), ("eth", 18), 0, 0.3, "../holdout-data"),
    # EXP-117: mainnet USDC/WETH 0.3% (same token order as 0x88e6, tick spacing 60), fetched with fetch_uni_minute.py
    "0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8": (("usdc", 6), ("eth", 18), 1, 0.3, "../holdout-data"),
}
# the EMA warm-up needs a year of history before the pool existed: read ETH/USD from the mainnet pool
WARM_POOL = {"0xd0b53d9277642d899df5c87a3966a349a798f224": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
             "0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef": "0x99ac8ca7087fa4a2a1fb6357269965a2014abc35",
             "0x6c561b446416e1a00e8e93e221854d6ea4171372": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
             "0xc6962004f452be9203591991d15f6b388e09e8d0": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"}
FIRST_DATA = {"0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640": date(2021, 5, 6),
              "0x99ac8ca7087fa4a2a1fb6357269965a2014abc35": date(2021, 11, 2),
              "0x4585fe77225b41b697c938b018e2ac67ac5a20c0": date(2021, 11, 2),
              "0xd0b53d9277642d899df5c87a3966a349a798f224": date(2023, 12, 1),
              "0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef": date(2024, 10, 1),
              "0x6c561b446416e1a00e8e93e221854d6ea4171372": date(2024, 1, 1),
              "0xfad57d2039c21811c8f2b5d5b65308aa99d31559": date(2021, 6, 1),
              "0xa6cc3c2531fdaa6ae1a3ca84c2855806728693e8": date(2021, 6, 1),
              "0x1d42064fc4beb5f8aaf85f4617ae8b3b5b8bd801": date(2021, 6, 1),
              "0xc6962004f452be9203591991d15f6b388e09e8d0": date(2023, 6, 9),
              "0x5ab53ee1d50eef2c1dd3d5402789cd27bb52c1bb": date(2021, 6, 1),
              "0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8": date(2021, 5, 6)}
# EXP-004: daily Aave USDC supply APR per pool's chain (samples/fetch_aave_rates.py)
RATE_CSV = {"0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640": "../aave_usdc_ethereum_daily.csv",
            "0x99ac8ca7087fa4a2a1fb6357269965a2014abc35": "../aave_usdc_ethereum_daily.csv",
            "0xd0b53d9277642d899df5c87a3966a349a798f224": "../aave_usdc_base_daily.csv",
            "0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef": "../aave_usdc_base_daily.csv",
            "0x6c561b446416e1a00e8e93e221854d6ea4171372": "../aave_usdc_base_daily.csv",
            "0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8": "../aave_usdc_ethereum_daily.csv"}
# EXP-014: Binance USDT-M 8h funding of the pool's base asset (samples/fetch_binance_funding.py)
FUNDING_CSV = {"0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640": "../binance_funding_ETHUSDT.csv",
               "0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8": "../binance_funding_ETHUSDT.csv",
               "0xd0b53d9277642d899df5c87a3966a349a798f224": "../binance_funding_ETHUSDT.csv",
               "0x99ac8ca7087fa4a2a1fb6357269965a2014abc35": "../binance_funding_BTCUSDT.csv",
               "0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef": "../binance_funding_BTCUSDT.csv",
               "0xfad57d2039c21811c8f2b5d5b65308aa99d31559": "../binance_funding_LINKUSDT.csv",
               # EXP-021: synthetic ALT/ETH perp = short ALTUSDT + long ETHUSDT (samples/make_synthetic_funding.py)
               "0xa6cc3c2531fdaa6ae1a3ca84c2855806728693e8": "../binance_funding_LINKETH_synth.csv",
               "0x1d42064fc4beb5f8aaf85f4617ae8b3b5b8bd801": "../binance_funding_UNIETH_synth.csv"}
# EXP-018: Binance daily closes of the pool's base asset, for the 12-month return (samples/fetch_binance_daily.py)
LONG_CLOSE_CSV = "../binance_daily_closes.csv"
LONG_CLOSE_COL = {"0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640": "ETHUSDT",
                  "0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8": "ETHUSDT",
                  "0xd0b53d9277642d899df5c87a3966a349a798f224": "ETHUSDT",
                  "0x99ac8ca7087fa4a2a1fb6357269965a2014abc35": "BTCUSDT",
                  "0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef": "BTCUSDT",
                  "0xfad57d2039c21811c8f2b5d5b65308aa99d31559": "LINKUSDT",
                  # EXP-021: ETH-quoted pools read the ratio of two USDT closes
                  "0xa6cc3c2531fdaa6ae1a3ca84c2855806728693e8": ("LINKUSDT", "ETHUSDT"),
                  "0x1d42064fc4beb5f8aaf85f4617ae8b3b5b8bd801": ("UNIUSDT", "ETHUSDT")}
INIT_QUOTE = Decimal(100000)
INIT_BY_POOL = {"0x4585fe77225b41b697c938b018e2ac67ac5a20c0": Decimal(2),  # quote units; default INIT_QUOTE
                "0xfad57d2039c21811c8f2b5d5b65308aa99d31559": Decimal(10000),   # thin pool: keep the fee share small
                "0xa6cc3c2531fdaa6ae1a3ca84c2855806728693e8": Decimal(40),      # EXP-021: 40 WETH ≈ $100k
                "0x1d42064fc4beb5f8aaf85f4617ae8b3b5b8bd801": Decimal(40),
                "0x5ab53ee1d50eef2c1dd3d5402789cd27bb52c1bb": Decimal(40)}
G_REMOVE, G_ADD, G_SWAP = 260_000, 450_000, 150_000
GAS_CSV = "../gas_ethereum_hourly.csv"
ETH_USD_CSV = "../eth_usd_hourly.csv"
# EXP-117: swap route per LP pool, (hop pool, fee %) in order; every hop holds WETH on one side. Used when SWAP_ROUTE == "pool".
SWAP_ROUTES = {"0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8": (("0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", 0.05),),
               "0x99ac8ca7087fa4a2a1fb6357269965a2014abc35": (("0x4585fe77225b41b697c938b018e2ac67ac5a20c0", 0.05),
                                                              ("0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", 0.05)),
               # EXP-128: Base WETH/USDC 0.3% ladder, swaps on Base WETH/USDC 0.05% (token0 is WETH there)
               "0x6c561b446416e1a00e8e93e221854d6ea4171372": (("0xd0b53d9277642d899df5c87a3966a349a798f224", 0.05),)}
ROUTE_DATA: list | None = None   # EXP-117: per hop (fee %, minute frame of closeTick / currentLiquidity), set in run_variant


def route_frame(pool: str, start: date, end: date) -> pd.DataFrame:
    """EXP-117: a hop pool's minute closeTick and currentLiquidity over [start, end] (raw files, no demeter cache), plus
    `eth0` = 1 when WETH is the pool's token0 (EXP-128), else 0 (token1)."""
    assert ("eth", 18) in POOLS[pool][:2], pool
    folder = f"{POOLS[pool][4]}/{pool}"
    frames = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".minute.csv") and start <= date.fromisoformat(name[-21:-11]) <= end:
            frames.append(pd.read_csv(f"{folder}/{name}", usecols=["timestamp", "closeTick", "currentLiquidity"],
                                      parse_dates=["timestamp"]))
    m = pd.concat(frames).set_index("timestamp").sort_index()
    m = m.apply(pd.to_numeric, errors="coerce").astype(float).ffill()
    m["eth0"] = 1.0 if POOLS[pool][0] == ("eth", 18) else 0.0
    return m


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
HI_SVR = {"INTRADAY_STOP": True, "REFILL_VOL_CONFIRM": True, "SWAP_ROUTE": "pool", "EXTRA": "pool"}   # EXP-124's WBTC half (intraday stop + volume refill + routing), reused by EXP-129..132
OPT = {"A": Variant("A_v6"),
       "B": Variant("B_spot_sleeve", {"SPOT_SLEEVE": Decimal("0.5")}),   # EXP-001
       "C": Variant("C_sleeve_stop", {"SPOT_SLEEVE": Decimal("0.5"), "SLEEVE_STOP": 0.80}),   # EXP-002
       "D": Variant("D_stop_keep_high", {"SPOT_SLEEVE": Decimal("0.5"), "SLEEVE_STOP": 0.80,
                                         "SLEEVE_HIGH_KEEP": True}),   # EXP-003
       "E": Variant("E_cash_yield", {"CASH_APR": "pool"}),   # EXP-004: idle USDC earns the pool chain's Aave rate
       "F": Variant("F_refill_order", {"REFILL_ORDER": True}),   # EXP-005
       "G": Variant("G_half_ladder", {"HALF_LADDER": True}),   # EXP-006
       "H": Variant("H_half_when_accel", {"HALF_WHEN_ACCEL": True}),   # EXP-007
       "I": Variant("I_lvr_gate", {"LVR_GATE": True}),   # EXP-012: F = 0 while 7-day pool fees / LVR < 1
       "J": Variant("J_trend_skew", {"SKEW": Decimal("0.05")}),   # EXP-013: -15/+25 above EMA100, -25/+15 below
       "K": Variant("K_perp_hedge", {"HEDGE": Decimal("0.6"), "HEDGE_FUNDING": "pool"}),   # EXP-014: short 60% of the ladder's delta
       "L": Variant("L_tox_pause", {"PAUSE_RET": 0.01}),   # EXP-016: pull the ladder 30 min after a 1% five-minute move
       "M": Variant("M_bear_short", {"BEAR_SHORT": Decimal("0.5"), "HEDGE_FUNDING": "pool"}),   # EXP-018
       "N": Variant("N_bear_short_cash", {"BEAR_SHORT": Decimal("0.5"), "HEDGE_FUNDING": "pool",
                                          "CASH_APR": "pool"}),   # EXP-018: M + EXP-004's cash yield
       "O": Variant("O_bear_short_nocrash", {"BEAR_SHORT": Decimal("0.5"), "HEDGE_FUNDING": "pool",
                                             "BEAR_CRASH_SIGMA": 2.0}),   # EXP-020: M without entries on 2-sigma crash days
       "P": Variant("P_bear_short_nocrash_2leg", {"BEAR_SHORT": Decimal("0.5"), "HEDGE_FUNDING": "pool",
                                                  "BEAR_CRASH_SIGMA": 2.0, "HEDGE_FEE": Decimal("0.001")}),   # EXP-021: O, synthetic ALT/ETH perp (two taker legs)
       "Q": Variant("Q_fee_compound", {"FEE_COMPOUND": True}),   # EXP-022: collected fees redeployed at the next build
       "R": Variant("R_recentre_up", {"RECENTRE_UP": Decimal("0.1")}),   # EXP-023: recentre at +10% from the build price
       "S": Variant("S_donchian", {"REGIME": "donchian"}),   # EXP-024: regime line = Donchian channel midpoint, n = 90..120
       "T": Variant("T_hma", {"REGIME": "hma"}),   # EXP-025: regime line = Hull MA(n)
       "U": Variant("U_roc", {"REGIME": "roc"}),   # EXP-026: regime = n-day return > 0
       "W": Variant("W_supertrend", {"REGIME": "supertrend"}),   # EXP-027: Supertrend(ATR n, x3)
       "X": Variant("X_ens_ema_donchian", {"REGIME": "ens_ed"}),   # EXP-028: 4 EMA + 4 Donchian accounts, F = mean of 8
       "Y": Variant("Y_share_by_armed", {"SHARE_BY_ARMED": True}),   # EXP-029: s = 0.5 + 0.2 x share of EMA spans above
       "Z": Variant("Z_vol_width", {"WIDTH_VOL": True}),   # EXP-030: half-width = sigma_30d x sqrt(30), 10..30%
       "AA": Variant("AA_consensus", {"REGIME": "max_ed"}),   # EXP-031: armed only above both EMA(n) and Donchian mid(n)
       "AB": Variant("AB_sma", {"REGIME": "sma"}),   # EXP-036: SMA(170/190/210/230)
       "AD": Variant("AD_ichimoku", {"REGIME": "ichimoku"}),   # EXP-037: Ichimoku cloud top, scale 1..2.5
       "AE": Variant("AE_aroon", {"REGIME": "aroon"}),   # EXP-038: Aroon Up(n) > Aroon Down(n)
       "AF": Variant("AF_drawdown", {"REGIME": "dd"}),   # EXP-039: close within 20% of its n-day high
       "AG": Variant("AG_exit_confirm", {"EXIT_CONFIRM": 2}),   # EXP-044: range exit needs 2 consecutive daily checks
       "AH": Variant("AH_weekly_F", {"F_WEEKLY": True}),   # EXP-045: F read once a week (Sundays)
       "AI": Variant("AI_share_50", {"SHARE_ABOVE_EMA": Decimal("0.5")}),   # EXP-046: ETH share 50% in both trend states
       "AJ": Variant("AJ_f_floor", {"F_FLOOR": 0.25}),   # EXP-047: F never below 25%
       "AK": Variant("AK_s50_confirm", {"SHARE_ABOVE_EMA": Decimal("0.5"), "EXIT_CONFIRM": 2}),   # EXP-048: EXP-046 + EXP-044
       "AL": Variant("AL_s50_volwidth", {"SHARE_ABOVE_EMA": Decimal("0.5"), "WIDTH_VOL": True}),   # EXP-049: EXP-046 + EXP-030
       "AM": Variant("AM_s50_consensus", {"SHARE_ABOVE_EMA": Decimal("0.5"), "REGIME": "max_ed"}),   # EXP-050: EXP-046 + EXP-031
       "AN": Variant("AN_s50_confirm_volwidth", {"SHARE_ABOVE_EMA": Decimal("0.5"), "EXIT_CONFIRM": 2, "WIDTH_VOL": True}),   # EXP-051: EXP-046 + 044 + 030
       "AO": Variant("AO_stable_lp", {"STABLE_LP": "pool"}),   # EXP-052: reserve LP'd in USDC/USDT ±0.1%
       "AP": Variant("AP_down_vol_target", {"VOL_TARGET": "pool"}),   # EXP-053: F x min(1, sigma*/sigma_14) below EMA100
       "AQ": Variant("AQ_er_gate", {"ER_GATE": True}),   # EXP-054: EMA exit only while ER(30) >= 1/sqrt(30)
       "AR": Variant("AR_resize_in_place", {"RESIZE_IN_PLACE": True}),   # EXP-055: follow F by scaling bands in place
       "AS": Variant("AS_exit_check_hourly", {"EXIT_CHECK_HOURLY": True}),   # EXP-056: range-exit check every hour
       "AT": Variant("AT_swapless_exit", {"SWAPLESS_EXIT": True}),   # EXP-057: range-exit rebuild from inventory, no swap
       "AU": Variant("AU_resize_near_centre", {"RESIZE_NEAR_CENTRE": True}),   # EXP-058: resize while in the ladder's inner half
       "AV": Variant("AV_macro_pause", {"MACRO_EVENTS": "csv"}),   # EXP-059: pull the ladder 30 min before to 2 h after FOMC / CPI
       "AW": Variant("AW_macro_pause_restore", {"MACRO_EVENTS": "csv", "MACRO_RESTORE": True}),   # EXP-060: EXP-059 + exact restore
       "AX": Variant("AX_tranche_add", {"TRANCHE_ADD": True}),   # EXP-061: F up -> new tranche at today's price; F down -> shrink
       "AY": Variant("AY_follow_asym", {"FOLLOW_ASYM": True}),   # EXP-062: F down -> shrink in place; F up -> v6 recentre
       "BA": Variant("BA_account_tranches", {"ACCOUNT_TRANCHES": True}),   # EXP-063: one real sub-ladder per virtual account
       "BB": Variant("BB_cppi", {"CPPI_FLOOR": 0.8}),   # EXP-064: F x clip((W/HWM - 0.8)/0.2, 0, 1)
       "BC": Variant("BC_weekly_recentre", {"WEEKLY_RECENTRE": True}),   # EXP-065: full recentre every Sunday 00:00
       "BD": Variant("BD_no_lower_stop", {"NO_LOWER_STOP": True}),   # EXP-066: engine without the 0.8 x centre stop
       "BE": Variant("BE_refill_armed_only", {"REFILL_ARMED_ONLY": True}),   # EXP-067: staged refill only above the EMA
       "BF": Variant("BF_rearm_full", {"REARM_FULL": True}),   # EXP-068: full deployment at the re-arm, no staged refill
       "BG": Variant("BG_no_upper_rebuild", {"NO_UPPER_REBUILD": True}),   # EXP-069: engine without the virtual upper rebuild
       "BH": Variant("BH_weekly_s50", {"WEEKLY_RECENTRE": True, "SHARE_ABOVE_EMA": Decimal("0.5")}),   # EXP-070: EXP-065 + EXP-046
       "BI": Variant("BI_weekly_recentre_up", {"WEEKLY_RECENTRE_UP": True}),   # EXP-071: weekly recentre only above EMA100
       "BJ": Variant("BJ_resize_below_ema", {"RESIZE_BELOW_EMA": True}),   # EXP-072: follow by resize below EMA100, v6 above
       "BL": Variant("BL_share_70", {"SHARE_BELOW_EMA": Decimal("0.7")}),   # EXP-073: ETH share 70% in both trend states
       "BM": Variant("BM_no_exit_rebuild", {"NO_EXIT_REBUILD": "all"}),   # EXP-074: no range-exit rebuild
       "BN": Variant("BN_no_down_exit_rebuild", {"NO_EXIT_REBUILD": "down"}),   # EXP-075: no rebuild after downward exits
       "BO": Variant("BO_single_account", {"EMA_SPANS": (100,)}),   # EXP-076: one EMA100 account instead of four
       "BP": Variant("BP_f_min", {"F_AGG": "min"}),   # EXP-077: F = lowest account
       "BQ": Variant("BQ_f_max", {"F_AGG": "max"}),   # EXP-078: F = highest account
       "BR": Variant("BR_f_any", {"F_BINARY": "any"}),   # EXP-079: full ladder while any account is deployed
       "BS": Variant("BS_f_all", {"F_BINARY": "all"}),   # EXP-080: full ladder only while all accounts are fully deployed
       "BT": Variant("BT_refill_one_stage", {"REFILL_ONE_STAGE": True}),   # EXP-081: first refill stage deploys fully
       "BU": Variant("BU_dvol_turn", {"REFILL_GATE": "dvol_turn", "EXTRA": "pool"}),   # EXP-082: refill after the DVOL peak
       "BV": Variant("BV_fund_accel", {"FUND_REFILL": "accel", "EXTRA": "pool"}),   # EXP-083: negative funding waives the hold
       "BW": Variant("BW_fund_accel_brake", {"FUND_REFILL": "accel_brake", "EXTRA": "pool"}),   # EXP-084: + hot funding brake
       "BX": Variant("BX_fund_cap", {"FUND_CAP": True, "EXTRA": "pool"}),   # EXP-085: F <= 0.5 while funding is hot
       "BY": Variant("BY_xasset_refill", {"REFILL_GATE": "xasset", "EXTRA": "pool"}),   # EXP-086: other asset must rebound too
       "BZ": Variant("BZ_vol_confirm_refill", {"REFILL_VOL_CONFIRM": True, "EXTRA": "pool"}),   # EXP-087: pool volume confirms the rebound
       "CA": Variant("CA_no_new_low_refill", {"REFILL_NO_NEW_LOW": True}),   # EXP-088: no new intraday low on refill days
       "CB": Variant("CB_twap_engine", {"TWAP_ENGINE": True}),   # EXP-089: engine on the daily TWAP
       "CC": Variant("CC_vrp_pull", {"VRP_PULL": True, "EXTRA": "pool"}),   # EXP-090: realised vol > DVOL -> one stage less
       "CD": Variant("CD_breadth_cap", {"BREADTH_CAP": True, "EXTRA": "pool"}),   # EXP-091: F <= mean(F, other asset's F)
       "CE": Variant("CE_gas_panic_hold", {"GAS_PANIC_HOLD": True, "EXTRA": "pool"}),   # EXP-092: no refill for 3 days after a gas spike
       "CF": Variant("CF_stable_flow_refill", {"STABLE_FLOW_REFILL": True, "EXTRA": "pool"}),   # EXP-093: stablecoin supply rising
       "CG": Variant("CG_no_weekend_refill", {"NO_WEEKEND_REFILL": True}),   # EXP-094: no refill stage on weekends
       "CH": Variant("CH_exit_vol_confirm", {"EXIT_VOL_CONFIRM": True, "EXTRA": "pool"}),   # EXP-095: EMA exit needs volume
       "CI": Variant("CI_flow_refill", {"FLOW_REFILL": True, "EXTRA": "pool"}),   # EXP-096: pool net buying confirms refill
       "CJ": Variant("CJ_exit_full_day", {"EXIT_FULL_DAY": True}),   # EXP-097: EMA exit only without an intraday reclaim
       "CK": Variant("CK_low_from_wick", {"LOW_FROM_WICK": True}),   # EXP-098: low since the exit from the minute low
       "CL": Variant("CL_up_day_refill", {"UP_DAY_REFILL": True}),   # EXP-099: refill days must close above their open
       "CM": Variant("CM_strong_close_refill", {"STRONG_CLOSE_REFILL": True}),   # EXP-100: close in the upper half of the range
       "CN": Variant("CN_intraday_stop", {"INTRADAY_STOP": True}),   # EXP-101: lower stop on the minute low
       # EXP-102..104: fee-tier rules: "hi" switches on pools with fee >= 0.3%, "lo" switches on cheaper pools
       "CO": Variant("CO_tier_pace", {"TIER": {"hi": {"LOW_FROM_WICK": True}, "lo": {"UP_DAY_REFILL": True}}}),   # EXP-102
       "CP": Variant("CP_tier_stop_nolow", {"TIER": {"hi": {"INTRADAY_STOP": True}, "lo": {"REFILL_NO_NEW_LOW": True}}}),   # EXP-103
       "CQ": Variant("CQ_tier_vol_nolow", {"TIER": {"hi": {"REFILL_VOL_CONFIRM": True, "EXTRA": "pool"}, "lo": {"REFILL_NO_NEW_LOW": True}}}),   # EXP-104
       "CR": Variant("CR_crowd_cap", {"CROWD_CAP": True, "EXTRA": "pool"}),   # EXP-105: F <= 0.5 while liquidity is crowded
       "CS": Variant("CS_nolow_exit_confirm", {"REFILL_NO_NEW_LOW": True, "EXIT_CONFIRM": 2}),   # EXP-106: v6.75 + v6.31
       "CT": Variant("CT_fail_cooldown", {"FAIL_COOLDOWN": True}),   # EXP-107: longer stage-1 wait after a fast-failed refill
       "CU": Variant("CU_crowd_refill", {"CROWD_REFILL": True, "EXTRA": "pool"}),   # EXP-108: no refill while crowded
       "CV": Variant("CV_crowd_refill_nolow", {"CROWD_REFILL": True, "REFILL_NO_NEW_LOW": True, "EXTRA": "pool"}),   # EXP-109
       "CW": Variant("CW_tier_wick_nolow", {"TIER": {"hi": {"LOW_FROM_WICK": True}, "lo": {"REFILL_NO_NEW_LOW": True}}}),   # EXP-110
       "CX": Variant("CX_tier_vol_nolowconfirm", {"TIER": {"hi": {"REFILL_VOL_CONFIRM": True, "EXTRA": "pool"},
                                                            "lo": {"REFILL_NO_NEW_LOW": True, "EXIT_CONFIRM": 2}}}),   # EXP-111
       # EXP-112..116: fee-tier pairs, each with at least one half not yet run on its holdout window
       "CY": Variant("CY_tier_stopvol_nolow", {"TIER": {"hi": {"INTRADAY_STOP": True, "REFILL_VOL_CONFIRM": True, "EXTRA": "pool"},
                                                         "lo": {"REFILL_NO_NEW_LOW": True}}}),   # EXP-112
       "CZ": Variant("CZ_tier_vol_nolow70", {"TIER": {"hi": {"REFILL_VOL_CONFIRM": True, "EXTRA": "pool"},
                                                       "lo": {"REFILL_NO_NEW_LOW": True, "SHARE_BELOW_EMA": Decimal("0.7")}}}),   # EXP-113
       "DA": Variant("DA_tier_nostopvol_nolow", {"TIER": {"hi": {"NO_LOWER_STOP": True, "REFILL_VOL_CONFIRM": True, "EXTRA": "pool"},
                                                           "lo": {"REFILL_NO_NEW_LOW": True}}}),   # EXP-114
       "DB": Variant("DB_tier_tranchestop_nolow", {"TIER": {"hi": {"ACCOUNT_TRANCHES": True, "INTRADAY_STOP": True},
                                                             "lo": {"REFILL_NO_NEW_LOW": True}}}),   # EXP-115
       "DC": Variant("DC_tier_stop_nolow70", {"TIER": {"hi": {"INTRADAY_STOP": True},
                                                        "lo": {"REFILL_NO_NEW_LOW": True, "SHARE_BELOW_EMA": Decimal("0.7")}}}),   # EXP-116
       # EXP-118..122 (DD..DF are left to the other session's EXP-117)
       "DG": Variant("DG_tier_tranchevol_nolow", {"TIER": {"hi": {"ACCOUNT_TRANCHES": True, "REFILL_VOL_CONFIRM": True, "EXTRA": "pool"},
                                                            "lo": {"REFILL_NO_NEW_LOW": True}}}),   # EXP-118
       "DH": Variant("DH_tier_nostoptranche_nolow", {"TIER": {"hi": {"NO_LOWER_STOP": True, "ACCOUNT_TRANCHES": True},
                                                               "lo": {"REFILL_NO_NEW_LOW": True}}}),   # EXP-119
       "DI": Variant("DI_tier_stopvol_nolowmacro", {"TIER": {"hi": {"INTRADAY_STOP": True, "REFILL_VOL_CONFIRM": True, "EXTRA": "pool"},
                                                              "lo": {"REFILL_NO_NEW_LOW": True, "MACRO_EVENTS": "csv", "MACRO_RESTORE": True}}}),   # EXP-120
       "DJ": Variant("DJ_tier_stopvoltranche_nolow", {"TIER": {"hi": {"INTRADAY_STOP": True, "REFILL_VOL_CONFIRM": True, "ACCOUNT_TRANCHES": True,
                                                                       "EXTRA": "pool"},
                                                                "lo": {"REFILL_NO_NEW_LOW": True}}}),   # EXP-121
       "DK": Variant("DK_nolow_macro", {"REFILL_NO_NEW_LOW": True, "MACRO_EVENTS": "csv", "MACRO_RESTORE": True}),   # EXP-122: v6.75 + v6.47
       "DD": Variant("DD_lp03_swap005", {"SWAP_ROUTE": "pool"}),   # EXP-117: ladder in the 0.3% pool, swaps on the 0.05% route
       # EXP-123..127: cheapest-tier routing (SWAP_ROUTE "pool" is a no-op on pools without a route, e.g. 0x88e6 0.05%)
       "DL": Variant("DL_nolow_route", {"REFILL_NO_NEW_LOW": True, "SWAP_ROUTE": "pool"}),   # EXP-123: one rule for both pools
       "DM": Variant("DM_tier_svroute_nolow", {"TIER": {"hi": {"INTRADAY_STOP": True, "REFILL_VOL_CONFIRM": True, "SWAP_ROUTE": "pool", "EXTRA": "pool"},
                                                         "lo": {"REFILL_NO_NEW_LOW": True}}}),   # EXP-124
       "DN": Variant("DN_tier_nostoproute_nolow", {"TIER": {"hi": {"NO_LOWER_STOP": True, "SWAP_ROUTE": "pool"},
                                                             "lo": {"REFILL_NO_NEW_LOW": True}}}),   # EXP-125
       "DO": Variant("DO_nolow_macro_route", {"REFILL_NO_NEW_LOW": True, "MACRO_EVENTS": "csv", "MACRO_RESTORE": True, "SWAP_ROUTE": "pool"}),   # EXP-126
       "DP": Variant("DP_tier_svroute_nolowupday", {"TIER": {"hi": {"INTRADAY_STOP": True, "REFILL_VOL_CONFIRM": True, "SWAP_ROUTE": "pool", "EXTRA": "pool"},
                                                              "lo": {"REFILL_NO_NEW_LOW": True, "UP_DAY_REFILL": True}}}),   # EXP-127
       # EXP-129..132: WBTC half = EXP-124's (stop + volume + routing); ETH half = v6.75 + one ETH dev winner, new on H5
       "DQ": Variant("DQ_tier_svr_nolowbreadth", {"TIER": {"hi": HI_SVR, "lo": {"REFILL_NO_NEW_LOW": True, "BREADTH_CAP": True, "EXTRA": "pool"}}}),   # EXP-129
       "DR": Variant("DR_tier_svr_nolowxasset", {"TIER": {"hi": HI_SVR, "lo": {"REFILL_NO_NEW_LOW": True, "REFILL_GATE": "xasset", "EXTRA": "pool"}}}),   # EXP-130
       "DS": Variant("DS_tier_svr_nolowfundcap", {"TIER": {"hi": HI_SVR, "lo": {"REFILL_NO_NEW_LOW": True, "FUND_CAP": True, "EXTRA": "pool"}}}),   # EXP-131
       "DT": Variant("DT_tier_svr_nolowstrong", {"TIER": {"hi": HI_SVR, "lo": {"REFILL_NO_NEW_LOW": True, "STRONG_CLOSE_REFILL": True}}}),   # EXP-132
       "DE": Variant("DE_basis_reserve", {"BASIS": "pool"}),   # EXP-133: reserve held as spot + short perp, earning funding
       # EXP-134..138: rebuild mechanics (rise rebuild, share-flip rebuild, swap tolerance)
       "DV": Variant("DV_tier_svr_nolowrise", {"TIER": {"hi": HI_SVR, "lo": {"REFILL_NO_NEW_LOW": True, "REBUILD_ON_RISE": True}}}),   # EXP-134
       "DW": Variant("DW_nolow_route_flip", {"REFILL_NO_NEW_LOW": True, "SWAP_ROUTE": "pool", "SHARE_FLIP_REBUILD": True}),   # EXP-135
       "DX": Variant("DX_tier_svr_nolowflip", {"TIER": {"hi": HI_SVR, "lo": {"REFILL_NO_NEW_LOW": True, "SHARE_FLIP_REBUILD": True}}}),   # EXP-136
       "DY": Variant("DY_nolow_route_rise", {"REFILL_NO_NEW_LOW": True, "SWAP_ROUTE": "pool", "REBUILD_ON_RISE": True}),   # EXP-137
       "DZ": Variant("DZ_tier_svr_nolowriseflip", {"TIER": {"hi": HI_SVR, "lo": {"REFILL_NO_NEW_LOW": True, "REBUILD_ON_RISE": True,
                                                                                 "SHARE_FLIP_REBUILD": True}}}),   # EXP-138
       # EXP-139..143: building on EXP-130's ETH half (v6.75 + cross-asset refill)
       "EA": Variant("EA_tier_svr_nlxrise", {"TIER": {"hi": HI_SVR, "lo": {"REFILL_NO_NEW_LOW": True, "REFILL_GATE": "xasset", "EXTRA": "pool", "REBUILD_ON_RISE": True}}}),   # EXP-139
       "EB": Variant("EB_tier_svr_nlxmacro", {"TIER": {"hi": HI_SVR, "lo": {"REFILL_NO_NEW_LOW": True, "REFILL_GATE": "xasset", "EXTRA": "pool", "MACRO_EVENTS": "csv", "MACRO_RESTORE": True}}}),   # EXP-140
       "EC": Variant("EC_tier_svrrise_nlx", {"TIER": {"hi": {**HI_SVR, "REBUILD_ON_RISE": True}, "lo": {"REFILL_NO_NEW_LOW": True, "REFILL_GATE": "xasset", "EXTRA": "pool"}}}),   # EXP-141
       "ED": Variant("ED_nolow_route_macro_rise", {"REFILL_NO_NEW_LOW": True, "SWAP_ROUTE": "pool", "MACRO_EVENTS": "csv", "MACRO_RESTORE": True,
                                                   "REBUILD_ON_RISE": True}),   # EXP-142: one rule for both pools
       "EE": Variant("EE_tier_svr_nlxconfirm", {"TIER": {"hi": HI_SVR, "lo": {"REFILL_NO_NEW_LOW": True, "REFILL_GATE": "xasset", "EXTRA": "pool", "EXIT_CONFIRM": 2}}}),   # EXP-143
       # EXP-144..148: the cross-asset refill on both pools, and EXP-139 + EXP-140 merged
       "EF": Variant("EF_nolow_xasset_route", {"REFILL_NO_NEW_LOW": True, "REFILL_GATE": "xasset", "EXTRA": "pool", "SWAP_ROUTE": "pool"}),   # EXP-144: one rule for both pools
       "EG": Variant("EG_nolow_xasset_route_rise", {"REFILL_NO_NEW_LOW": True, "REFILL_GATE": "xasset", "EXTRA": "pool", "SWAP_ROUTE": "pool", "REBUILD_ON_RISE": True}),   # EXP-145
       "EH": Variant("EH_tier_svrx_nlx", {"TIER": {"hi": {**HI_SVR, "REFILL_GATE": "xasset"}, "lo": {"REFILL_NO_NEW_LOW": True, "REFILL_GATE": "xasset", "EXTRA": "pool"}}}),   # EXP-146
       "EI": Variant("EI_tier_svr_nlxrisemacro", {"TIER": {"hi": HI_SVR, "lo": {"REFILL_NO_NEW_LOW": True, "REFILL_GATE": "xasset", "EXTRA": "pool", "REBUILD_ON_RISE": True,
                                                                               "MACRO_EVENTS": "csv", "MACRO_RESTORE": True}}}),   # EXP-147
       "EJ": Variant("EJ_nolow_xasset_route_macro", {"REFILL_NO_NEW_LOW": True, "REFILL_GATE": "xasset", "EXTRA": "pool", "SWAP_ROUTE": "pool", "MACRO_EVENTS": "csv",
                                                     "MACRO_RESTORE": True}),   # EXP-148: one rule for both pools
       # EXP-149..152: EXP-140's ETH half (v6.75 + cross-asset refill + macro restore) with new WBTC halves, and one clean rule
       "EK": Variant("EK_tier_svrmacro_nlxmacro", {"TIER": {"hi": {**HI_SVR, "MACRO_EVENTS": "csv", "MACRO_RESTORE": True},
                                                            "lo": {"REFILL_NO_NEW_LOW": True, "REFILL_GATE": "xasset", "EXTRA": "pool", "MACRO_EVENTS": "csv", "MACRO_RESTORE": True}}}),   # EXP-149
       "EL": Variant("EL_tier_svrnolow_nlxmacro", {"TIER": {"hi": {**HI_SVR, "REFILL_NO_NEW_LOW": True}, "lo": {"REFILL_NO_NEW_LOW": True, "REFILL_GATE": "xasset", "EXTRA": "pool", "MACRO_EVENTS": "csv", "MACRO_RESTORE": True}}}),   # EXP-150
       "EM": Variant("EM_tier_svr_nlxmacrotranche", {"TIER": {"hi": HI_SVR, "lo": {"REFILL_NO_NEW_LOW": True, "REFILL_GATE": "xasset", "EXTRA": "pool", "MACRO_EVENTS": "csv", "MACRO_RESTORE": True, "ACCOUNT_TRANCHES": True}}}),   # EXP-151
       "EN": Variant("EN_nolow_route_macro_vol", {"REFILL_NO_NEW_LOW": True, "SWAP_ROUTE": "pool", "MACRO_EVENTS": "csv", "MACRO_RESTORE": True,
                                                  "REFILL_VOL_CONFIRM": True, "EXTRA": "pool"}),   # EXP-152: one rule for both pools
       "EO": Variant("EO_onesided_above_ema", {"SHARE_ABOVE_EMA": Decimal("1.0")}),   # EXP-153: one-sided ETH ladder above EMA100
       "EP": Variant("EP_widetop_above_ema", {"WIDE_TOP_ABOVE_EMA": Decimal("0.40")})}   # EXP-154: +40% / -20% above EMA100
# EXP-082..: daily non-price inputs (samples/fetch_deribit_dvol.py, fetch_binance_funding.py, fetch_binance_daily.py)
DVOL_CSV = "../deribit_dvol_daily.csv"
FUND_LONG_CSV = {"ETHUSDT": "../binance_funding_ETHUSDT_long.csv", "BTCUSDT": "../binance_funding_BTCUSDT_long.csv"}


def extra_frame() -> pd.DataFrame:
    """EXP-082..: daily dvol / fund / other for the pool's asset (ETH or BTC by LONG_CLOSE_COL)."""
    sym = LONG_CLOSE_COL[POOL]
    asset, other = ("ETH", "BTCUSDT") if sym == "ETHUSDT" else ("BTC", "ETHUSDT")
    dvol = pd.read_csv(DVOL_CSV, parse_dates=["date"]).set_index("date")[asset]
    f = pd.read_csv(FUND_LONG_CSV[sym], parse_dates=["timestamp"]).set_index("timestamp")["rate"]
    fund = f.resample("1D").mean()
    oth = pd.read_csv(LONG_CLOSE_CSV, parse_dates=["date"]).set_index("date")[other]
    gas = pd.read_csv(GAS_CSV, parse_dates=["timestamp"]).set_index("timestamp")["gwei"].resample("1D").median()   # EXP-092
    stable = pd.read_csv(FLOW_CSV, parse_dates=["date"]).set_index("date")["stable_mcap"]   # EXP-093
    out = pd.DataFrame({"dvol": dvol, "fund": fund, "other": oth, "gas": gas, "stable": stable})
    if POOL_VOL is not None:   # EXP-087
        out = out.reindex(out.index.union(POOL_VOL.index))
        out["pvol"] = POOL_VOL
    if POOL_FLOW is not None:   # EXP-096
        out = out.reindex(out.index.union(POOL_FLOW.index))
        out["flow"] = POOL_FLOW
    if POOL_LIQ is not None:   # EXP-105
        out = out.reindex(out.index.union(POOL_LIQ.index))
        out["liq"] = POOL_LIQ
    return out


POOL_VOL: pd.Series | None = None   # EXP-087: daily quote-token swap volume of the pool (warm-up + window)
POOL_FLOW: pd.Series | None = None   # EXP-096: daily net base-token flow into the pool (> 0 = net selling)
POOL_LIQ: pd.Series | None = None   # EXP-105: daily mean active liquidity (currentLiquidity) of the pool
FLOW_CSV = "../flow_daily.csv"   # EXP-093: stablecoin market cap (DefiLlama), samples/fetch_flow_daily.py


def other_fraction() -> pd.Series:
    """EXP-091: v6's F on the other asset's Binance daily closes (all engine switches at v6 defaults, restored after)."""
    sym = LONG_CLOSE_COL[POOL]
    other = "BTCUSDT" if sym == "ETHUSDT" else "ETHUSDT"
    c = pd.read_csv(LONG_CLOSE_CSV, parse_dates=["date"]).set_index("date")[other].dropna()
    saved = {k: getattr(V, k) for k in ENGINE_DEFAULTS}
    try:
        for k, v in ENGINE_DEFAULTS.items():
            setattr(V, k, v)
        f = V.daily_ema_frame(pd.Series(c.to_numpy(), index=c.index + pd.Timedelta(hours=23, minutes=59)))["F"]
    finally:
        for k, v in saved.items():
            setattr(V, k, v)
    return f
MACRO_CSV = "../macro_events_utc.csv"   # EXP-059
# EXP-052: daily net return per $ of the USDC/USDT LP (samples/make_stable_lp_series.py), for USDC-quoted pools
STABLE_LP_CSV = "../stable_lp_daily.csv"
# EXP-053: median 14-day std of daily log returns, Binance closes 2019-01-01..2021-04-30 (fixed in the pre-registration)
VOL_TARGET_BY_ASSET = {"ETHUSDT": 0.04179, "BTCUSDT": 0.03219}


ENGINE_DEFAULTS = {k: getattr(V, k) for k in ["EMA_SPANS", "REFILL_STAGES", "REFILL_CONFIRM_DAYS", "LOWER_STOP",
                                                "FOLLOW_THRESHOLD", "SHARE_ABOVE_EMA", "SPOT_SLEEVE", "SLEEVE_STOP", "SLEEVE_HIGH_KEEP", "CASH_APR", "REFILL_ORDER", "HALF_LADDER", "HALF_WHEN_ACCEL", "LVR_GATE", "SKEW", "HEDGE", "HEDGE_FUNDING", "PAUSE_RET", "BEAR_SHORT", "BEAR_CRASH_SIGMA", "HEDGE_FEE", "FEE_COMPOUND", "RECENTRE_UP", "REGIME", "SUPERTREND_MULT", "SHARE_BY_ARMED", "WIDTH_VOL", "WIDE_TOP_ABOVE_EMA", "EXIT_CONFIRM", "F_WEEKLY", "F_FLOOR", "STABLE_LP", "VOL_TARGET", "ER_GATE", "RESIZE_IN_PLACE", "EXIT_CHECK_HOURLY", "SWAPLESS_EXIT", "RESIZE_NEAR_CENTRE", "MACRO_EVENTS", "MACRO_RESTORE", "TRANCHE_ADD", "FOLLOW_ASYM", "ACCOUNT_TRANCHES", "CPPI_FLOOR", "WEEKLY_RECENTRE", "NO_LOWER_STOP", "REFILL_ARMED_ONLY", "REARM_FULL", "NO_UPPER_REBUILD", "WEEKLY_RECENTRE_UP", "RESIZE_BELOW_EMA", "SHARE_BELOW_EMA", "NO_EXIT_REBUILD", "F_AGG", "F_BINARY", "REFILL_ONE_STAGE", "EXTRA", "REFILL_GATE", "FUND_REFILL", "FUND_CAP", "REFILL_VOL_CONFIRM", "REFILL_NO_NEW_LOW", "TWAP_ENGINE", "VRP_PULL", "BREADTH_CAP", "GAS_PANIC_HOLD", "STABLE_FLOW_REFILL", "NO_WEEKEND_REFILL", "EXIT_VOL_CONFIRM", "FLOW_REFILL", "EXIT_FULL_DAY", "LOW_FROM_WICK", "UP_DAY_REFILL", "STRONG_CLOSE_REFILL", "INTRADAY_STOP", "CROWD_CAP", "FAIL_COOLDOWN", "CROWD_REFILL", "SWAP_ROUTE", "REBUILD_ON_RISE", "SHARE_FLIP_REBUILD", "BASIS"]}


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
GATE_MINUTES: pd.DataFrame | None = None   # EXP-012: the pool's own minutes, LVR_GATE_DAYS + 1 days before start .. end
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
        self.route_rebate, self.route_impact = 0.0, 0.0   # EXP-117

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
        notional = float(base_in) * price + float(quote_in)
        if ROUTE_DATA and notional > 0:   # EXP-117: the swap is charged on the 0.05% route instead (only when the pool has a route)
            eth_usd = float(ETH_USD.asof(ts))
            side = float(base_in) * price if base_in > 0 else float(quote_in)   # same side as v6's impact above
            route = 0.0
            for _, hop in ROUTE_DATA:
                h = hop.asof(ts)
                sp = 1.0001 ** (h["closeTick"] / 2)
                weth = h["currentLiquidity"] / sp if h["eth0"] else h["currentLiquidity"] * sp   # WETH-side virtual reserve
                route += side ** 2 / (weth / 1e18 * eth_usd)
            rebate = notional * (float(self.gp.fee) - sum(fee for fee, _ in ROUTE_DATA)) / 100
            self.route_rebate += rebate
            self.route_impact += route
            impact = route - rebate
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

    def resize_work(self, row_data, target, current):   # EXP-055: partial burns / mints and one swap
        n = len(self.positions)
        b0, q0 = self.total_base_swap_fee, self.total_quote_swap_fee
        super().resize_work(row_data, target, current)
        self.charge(row_data, n if target < current else 0, n if target > current else 0, *self.swapped_since(b0, q0))

    def tranche_work(self, row_data):   # EXP-063: partial burns, one net swap, mints
        b0, q0 = self.total_base_swap_fee, self.total_quote_swap_fee
        super().tranche_work(row_data)
        if self.tranche_io != (0, 0):
            self.charge(row_data, *self.tranche_io, *self.swapped_since(b0, q0))

    def tranche_add(self, row_data, target, current, equity):   # EXP-061: one swap, mints
        b0, q0 = self.total_base_swap_fee, self.total_quote_swap_fee
        n = len(self.positions)
        super().tranche_add(row_data, target, current, equity)
        self.charge(row_data, 0, len(self.positions) - n or 1, *self.swapped_since(b0, q0))

    def restore_ladder(self, row_data):   # EXP-060: one net swap, mints
        b0, q0 = self.total_base_swap_fee, self.total_quote_swap_fee
        super().restore_ladder(row_data)
        self.charge(row_data, 0, len(self.positions), *self.swapped_since(b0, q0))

    def pause_ladder(self, row_data):   # EXP-016: burns, no swap
        super().pause_ladder(row_data)
        self.charge(row_data, len(self.paused_bands), 0, ZERO, ZERO)

    def resume_ladder(self, row_data):   # EXP-016: mints, no swap
        super().resume_ladder(row_data)
        self.charge(row_data, 0, len(self.positions), ZERO, ZERO)

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
        daily = V.daily_ema_frame(PRICE)
    else:
        ema_span = V.EMA_SPAN
        V.EMA_SPAN = V.EMA_SPANS[0]
        try:
            daily = V.daily_ema_frame(PRICE)
        finally:
            V.EMA_SPAN = ema_span
        daily["ema"] = daily["close"].ewm(span=ema_span, adjust=False).mean()
    if V.LVR_GATE:   # EXP-012: zero F on days the pool did not pay its liquidity over the trailing week
        daily = V.gate_fractions(daily, V.fee_lvr_ratio(GATE_MINUTES, POOLS[POOL][3]))
    if V.BEAR_SHORT > 0:   # EXP-018: the bear-short flag on top of the final F
        closes = pd.read_csv(LONG_CLOSE_CSV, parse_dates=["date"]).set_index("date")
        col = LONG_CLOSE_COL[POOL]
        long_close = closes[col[0]] / closes[col[1]] if isinstance(col, tuple) else closes[col]
        daily = V.bear_short_flags(daily, long_close)
    return daily


def run_variant(args):
    variant, start, end, folder = args
    t0 = time.time()
    # pool workers are reused: restore every default before applying this variant's overrides
    engine = {k: v for k, v in variant.engine.items() if k != "TIER"}
    if "TIER" in variant.engine:   # EXP-102..104: the pool's fee tier picks the switch set
        engine.update(variant.engine["TIER"]["hi" if POOLS[POOL][3] >= 0.3 else "lo"])
    for k, v in {**ENGINE_DEFAULTS, **engine}.items():
        if k == "CASH_APR" and v == "pool":
            v = pd.read_csv(RATE_CSV[POOL], parse_dates=["date"]).set_index("date")["apr"].sort_index()
        if k == "EXTRA" and v == "pool":
            v = extra_frame()
        if k == "MACRO_EVENTS" and v == "csv":
            v = sorted(pd.read_csv(MACRO_CSV, parse_dates=["release_utc"])["release_utc"].dt.to_pydatetime().tolist())
        if k == "BASIS" and v == "pool":   # EXP-133: the pool asset's daily funding sum (Binance USDT-M, 8-hour rates)
            f = pd.read_csv(FUND_LONG_CSV[LONG_CLOSE_COL[POOL]], parse_dates=["timestamp"]).set_index("timestamp")["rate"]
            v = f.resample("1D").sum(min_count=1).dropna()
        if k == "STABLE_LP" and v == "pool":
            v = pd.read_csv(STABLE_LP_CSV, parse_dates=["date"]).set_index("date")["ret"].sort_index()
        if k == "VOL_TARGET" and v == "pool":
            v = VOL_TARGET_BY_ASSET[LONG_CLOSE_COL[POOL]]
        if k == "HEDGE_FUNDING" and v == "pool":
            v = pd.read_csv(FUNDING_CSV[POOL], parse_dates=["timestamp"]).set_index("timestamp")["rate"].sort_index()
        setattr(V, k, v)
    global ROUTE_DATA
    ROUTE_DATA = None
    route = SWAP_ROUTES.get(POOL) if V.SWAP_ROUTE == "pool" else None   # EXP-123..: no route entry -> v6's own ledger
    if route:   # EXP-117: hop pools' minute liquidity for the route's impact
        ROUTE_DATA = [(fee, route_frame(hop, start - timedelta(days=1), end)) for hop, fee in route]
    if V.BREADTH_CAP and V.EXTRA is not None:   # EXP-091: the other asset's F, computed with v6's engine
        V.EXTRA = V.EXTRA.copy()
        V.EXTRA["other_F"] = other_fraction().reindex(V.EXTRA.index)
    daily = daily_frame()
    window = daily.loc[pd.Timestamp(start):]
    bull, bear, tp, gp = inputs(variant, start, end, folder)
    usdc_price = pd.DataFrame(index=pd.date_range(start=start, end=datetime.combine(end, datetime.max.time()),
                                                  freq="min"), data={"price": ONE})
    ratio = Decimal(variant.ratio)
    try:
        with contextlib.redirect_stdout(open(os.environ["DEBUG_LOG"], "w") if os.environ.get("DEBUG_LOG") else io.StringIO()):
            m = V.run_test(bull, bear, tp, gp, DATA, usdc_price, shape="inverted_gaussian", upper_ratio=ratio,
                           lower_ratio=ratio, half_gap=0, eth_share=variant.eth_share, daily_ema=daily,
                           deploy=variant.deploy)
    except Exception as e:
        return {"variant": variant.name, "error": repr(e)[:200] + " @ " + " | ".join(l.strip() for l in traceback.format_exc().splitlines()[-7:-1])[:600]}
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
            "gate_closed_days": int(((window["F_raw"] > 0) & (window["F"] == 0)).sum()) if "F_raw" in window else 0,
            "median_R": float(window["R"].median()) if "R" in window else float("nan"),
            "width_builds": str(s.width_builds), "skew_up_builds": s.skew_builds["up"], "skew_down_builds": s.skew_builds["down"],
            "hedge_pnl": float(s.hedge_pnl), "hedge_funding": float(s.hedge_funding), "hedge_fees": float(s.hedge_fees),
            "hedge_trades": s.hedge_trades, "hedge_max_ratio": s.hedge_max_ratio,
            "hedge_min_cash": float(s.hedge_min_cash) if s.hedge_min_cash is not None else float("nan"),
            "stable_income": float(s.total_interest) if V.STABLE_LP is not None else 0.0, "pauses": s.pauses, "pause_minutes": s.pause_minutes, "bear_short_days": s.bear_short_days, "recentres": s.recentre_count, "resizes": s.resize_count, "swapless_exits": s.swapless_exits, "tranche_adds": s.tranche_adds, "tranche_rebuilds": s.tranche_rebuilds, "cppi_min_m": s.cppi_min_m, "weekly_recentres": s.weekly_recentres, "skipped_exits": s.skipped_exits,
            "benchmark_return": float(m["benchmark_rate"]), "route_rebate": s.route_rebate, "route_impact": s.route_impact,
            "basis_income": float(s.basis_income),
            "secs": round(time.time() - t0)}


def load_minutes(start: date, end: date, pool: str | None = None) -> pd.DataFrame:
    pool = pool or POOL
    token0, token1, base, quote, fee = tokens(pool)
    market = UniLpMarketV2(MarketInfo("lp"), UniV3Pool(token0, token1, fee, quote))
    market.data_path = f"{POOLS[pool][4]}/{pool}"
    market.load_data(ChainType.ethereum.name, pool, start, end)
    return market.data


def daily_quote_volume(m: pd.DataFrame, pool: str) -> pd.Series:
    """EXP-087: daily swap volume in the pool's quote token (volume0 / volume1 by token order)."""
    t0, t1, base_i, _, _ = POOLS[pool]
    col = "volume1" if base_i == 0 else "volume0"
    return m[col].astype(float).resample("1D").sum()


def daily_base_flow(m: pd.DataFrame, pool: str) -> pd.Series:
    """EXP-096: daily net base-token amount swapped into the pool (> 0: net selling of the base token)."""
    base_i = POOLS[pool][2]
    return m[f"netAmount{base_i}"].astype(float).resample("1D").sum() / 10 ** POOLS[pool][base_i][1]


def main():
    global POOL, DATA, PRICE, GATE_MINUTES, GAS, ETH_USD
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
    warm_from = start - timedelta(days=warm_days)
    parts = []
    if os.environ.get("BINANCE_WARM") and warm_from < FIRST_DATA[warm_pool]:
        # EXP-040..: window before the pool's own data (out-of-time holdout): the missing warm-up days come from the
        # Binance daily closes of the base asset (close only: the day's high and low equal its close on those days)
        col = LONG_CLOSE_COL[POOL]
        closes = pd.read_csv(LONG_CLOSE_CSV, parse_dates=["date"]).set_index("date")[col]
        seg = closes.loc[pd.Timestamp(warm_from):pd.Timestamp(min(FIRST_DATA[warm_pool], start) - timedelta(days=1))].dropna()
        parts.append(pd.Series(seg.to_numpy(), index=seg.index + pd.Timedelta(hours=23, minutes=59)))
    vol_parts, flow_parts, liq_parts = [], [], []
    if start > FIRST_DATA[warm_pool]:
        warm_m = load_minutes(max(warm_from, FIRST_DATA[warm_pool]), start - timedelta(days=1), warm_pool)
        parts.append(warm_m.price)
        vol_parts.append(daily_quote_volume(warm_m, warm_pool))
        flow_parts.append(daily_base_flow(warm_m, warm_pool))
        liq_parts.append(warm_m["currentLiquidity"].astype(float).resample("1D").mean())
    global POOL_VOL, POOL_FLOW, POOL_LIQ
    POOL_LIQ = pd.concat(liq_parts + [DATA["currentLiquidity"].astype(float).resample("1D").mean()])   # EXP-105
    POOL_VOL = pd.concat(vol_parts + [daily_quote_volume(DATA, POOL)])   # EXP-087
    POOL_FLOW = pd.concat(flow_parts + [daily_base_flow(DATA, POOL)])   # EXP-096
    PRICE = pd.concat(parts + [DATA.price])
    if any(v.engine.get("LVR_GATE") for v in variants):   # EXP-012: the gate needs the pool's own week before start
        gate_start = max(start - timedelta(days=V.LVR_GATE_DAYS + 1), FIRST_DATA[POOL])
        GATE_MINUTES = DATA if gate_start >= start else \
            pd.concat([load_minutes(gate_start, start - timedelta(days=1)), DATA])
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
