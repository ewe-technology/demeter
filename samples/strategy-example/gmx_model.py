from dataclasses import dataclass, field
from enum import Enum
from math_const import *

class IndicatorType(Enum):
    STANDARD = "standard"
    MACD = "macd"
    RSI = "rsi"

@dataclass
class MacdConfig:
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    # sample_period: str = "1h"

@dataclass
class StockRsiConfig:
    time_period: int = 14
    fastk_period: int = 5
    fastd_period: int = 3
    fastd_matype: int = 0

@dataclass
class Position:
    is_short: bool
    close_mark_price: Decimal = ZERO
    open_price: Decimal = ZERO
    stop_loss_price: Decimal = ZERO

@dataclass
class WinLoss:
    win_cnt: int = 0
    loss_cnt: int = 0
    total_gain: Decimal = ZERO
    total_loss: Decimal = ZERO

@dataclass
class GmxConfig:
    open_change_rate: str = "0.02"  # 0.02 = 2%
    stop_loss_rate: str = "0.02"  # 0.05 = 5%
    trailing_stop_loss_rate: str = "0.02"  # 0.05 = 5%
    data_start_date: str = "2024-3-10"
    start_date: str = "2024-6-1"
    end_date: str = "2024-8-31"
    initial_amount: str = "1000"
    check_interval_min: int = 1
    print_price: bool = False
    trading_fee_rate: str = "0.0004"  # 0.0004 = 0.04%
    delayed_entry: bool = True

    position_open_strategy: str = IndicatorType.STANDARD.value  # "standard" or "macd" or "rsi"
    run_long: bool = True  # to run long or not
    run_short: bool = True  # to run short or not
    strategy_sample_period: str = "1h"  # '30min', '1h', '4h', '8h', '1d'
    strategy_delta_rounding_decimal: int = 10

    macd: MacdConfig = field(default_factory=MacdConfig)
    stock_rsi: StockRsiConfig = field(default_factory=StockRsiConfig)
