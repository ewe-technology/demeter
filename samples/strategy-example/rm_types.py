from dataclasses import dataclass
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum

from demeter import TokenInfo
from math_const import *


class RangeStrategy(str, Enum):
    remix_dao = "remix-dao"
    std = "std"
    atr = "atr"


# class RescaleFrequency(str, Enum):
#     minute1 = "1m"
#     minute5 = "5m"
#     minute15 = "15m"
#     minute30 = "30m"
#     hourly = "1h"
#     daily = "1d"

class RescaleFrequency(Enum):
    minute1 = timedelta(minutes=1)
    minute5 = timedelta(minutes=5)
    minute15 = timedelta(minutes=15)
    minute30 = timedelta(minutes=30)
    hourly = timedelta(hours=1)
    hour4 = timedelta(hours=4)
    hour8 = timedelta(hours=8)
    hour12 = timedelta(hours=12)
    daily = timedelta(days=1)

    def __str__(self) -> str:
        match self:
            case RescaleFrequency.minute1:
                return "1m"
            case RescaleFrequency.minute5:
                return "5m"
            case RescaleFrequency.minute15:
                return "15m"
            case RescaleFrequency.minute30:
                return "30m"
            case RescaleFrequency.hourly:
                return "1h"
            case RescaleFrequency.hour4:
                return "4h"
            case RescaleFrequency.hour8:
                return "8h"
            case RescaleFrequency.hour12:
                return "12h"
            case RescaleFrequency.daily:
                return "1d"
        return ""


class DcaTiming(str, Enum):
    base_only = "base_only"
    quote_only = "quote_only"
    out_of_range = "out_of_range"
    always = "always"
    none = "none"

class DcaAddition(str, Enum):
    on_base_only = "on_base_only"
    on_quote_only = "on_quote_only"
    none = "none"

@dataclass
class GlobalParams:
    token0: TokenInfo
    token1: TokenInfo
    fee: float
    base_token: TokenInfo
    quote_token: TokenInfo
    init_quote: Decimal
    chain_name: str
    contract_address: str
    swap_fee: bool = False
    init_quote_usdc: Decimal = ZERO
    dca_usdc_amount: Decimal = ZERO
    dca_add_if_non_empty: bool = False
    dca_add_timing: DcaTiming = DcaTiming.base_only
    dca_addon_price_percent: Decimal = Decimal(10000)  # in decimal form 0.1 is 10%
    dca_addon_amount_percent: Decimal = ZERO  # in the amount to add in percent, 1 is to add 100%, 0.4 is to add 40%
    dca_addition: DcaAddition = DcaAddition.none
    init_short_amount: Decimal = ZERO
    short_stop_loss_ratio: Decimal = Decimal(1)
    do_lp_rebalance: bool = True
    refill_percent: Decimal | None = None # in decimal form 0.1 is 10%

@dataclass
class ShortInfo:
    short_amount: Decimal
    short_stop_loss_hit: bool = False
    short_stop_loss_price: Decimal | None = None
    short_price: Decimal | None = None
    short_stop_loss_cnt: int = 0
    short_win_cnt: int = 0
    prev_stop_loss: bool = False
    consecutive_short_stop_loss_cnt: int = 0
    short_total_gain: Decimal = ZERO
    short_total_loss: Decimal = ZERO
    short_to_lp: Decimal = ZERO
    lp_to_short: Decimal = ZERO


class TestParams:

    def __init__(self, range_strategy: RangeStrategy, indicator_mult: float, report_name: str,
                 cal_start_datetime: datetime,
                 data_start_date: date,
                 data_end_date: date,
                 folder: str,
                 indicator_length_hr: int = 1,
                 to_swap: bool = False,
                 aggressive: bool = True,
                 compound: bool = False,
                 rescale_frequency: RescaleFrequency = RescaleFrequency.hourly,
                 initial_swap: bool = True,
                 flip_param_dates: list[datetime] = [],
                 start_with_bull_param: bool = True,
                 initial_type: int = 1,
                 starting_mark_price: Decimal = ZERO):
        self.range_strategy = range_strategy
        self.indicator_mult = indicator_mult
        self.report_name = report_name
        self.to_swap = to_swap
        self.aggressive = aggressive
        self.compound = compound
        if range_strategy == RangeStrategy.atr:
            self.indicator_length_min = indicator_length_hr * 60
        elif range_strategy == RangeStrategy.std:
            self.indicator_length_min = indicator_length_hr * 60
        else:
            self.indicator_length_min = 0
        self.rescale_frequency = rescale_frequency
        self.cal_start_datetime = cal_start_datetime
        self.data_start_date = data_start_date
        self.data_end_date = data_end_date
        self.folder = folder
        self.initial_swap = initial_swap
        self.flip_param_dates = flip_param_dates
        self.start_with_bull_param = start_with_bull_param
        self.initial_type = initial_type # 1: even balance, 0: dont swap, -1: all swap
        self.starting_mark_price = starting_mark_price
        

# class PriceAction(Enum):
#     lower_low = "lower_low"
#     higher_high = "higher_high"

class PriceActionLog:
    def __init__(self, price: Decimal, lp_price: Decimal):
        self.price = price
        self.lp_price = lp_price
        

