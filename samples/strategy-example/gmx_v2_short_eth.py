from dataclasses import dataclass
import math
from datetime import date, datetime, timedelta
from decimal import Decimal

import pandas as pd

from demeter import TokenInfo, Actuator, Strategy, Snapshot, ChainType, MarketInfo, AtTimeTrigger, PeriodTrigger, MarketTypeEnum
from demeter.gmx import GmxV2Market
from demeter.gmx._typing2 import GmxV2Pool

from chaos_lab_utils import macd, resample_data

import toml
from math_const import *

# To print all the columns of dataframe, we should set up display option.
pd.options.display.max_columns = None
pd.set_option("display.width", 5000)

_MACD = "macd"
_HUNDRED = HUNDRED
_ONE = ONE
MARKET_KEY = MarketInfo("GMX_ETH", MarketTypeEnum.gmx_v2)

OPEN_PERCENT = Decimal("0.01")
STOP_LOSS_PERCENT = Decimal("0.01")
CLOSE_PERCENT = Decimal("0.01")
_START_DATE, _END_DATE = date(2024, 10, 1), date(2024, 12, 31)
DATA_START_DATE = _START_DATE
INIT_USDC = Decimal("0")
CHECK_INTERVAL_MIN = 1
# _OPEN_LONG = False
# _OPEN_SHORT = True
PRINT_PRICE = False
POSITION_OPEN_STRATEGY = "standard"


@dataclass
class MacdConfig:
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    sample_period: str = "1h"

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

class GmxV2LpStrategy(Strategy):

    def __init__(self, macd_config: MacdConfig = MacdConfig(), to_short: bool = True, to_long: bool = True):
        super().__init__()
        self.open_short_mark_price: Decimal = ZERO
        self.open_long_mark_price: Decimal = ZERO
        # self.close_mark_price: Decimal = ZERO

        # self.last_price: Decimal = ZERO
        self.initial_usdc: Decimal = INIT_USDC
        self.current_usdc: Decimal = self.initial_usdc
        # self.short_position_opened: bool = False
        # self.position_open_price: Decimal | None = None
        # self.position_stop_loss_price: Decimal = ZERO
        # self.total_short_gain: Decimal = ZERO
        # self.total_short_loss: Decimal = ZERO
        # self.total_gain_cnt: int = 0
        # self.total_loss_cnt: int = 0
        self.position: Position | None = None
        self.last_macd_delta: Decimal = ZERO
        self.long_wl: WinLoss | None = WinLoss() if to_long else None
        self.short_wl: WinLoss | None = WinLoss() if to_short else None
        self.macd_config = macd_config


    def initialize(self):

        market_data = self.data[MARKET_KEY]
        # print(f"{market_data.keys()}")
        if POSITION_OPEN_STRATEGY == _MACD:

            resampled_prices = resample_data(market_data.longPrice, self.macd_config.sample_period)
            # print(resampled_prices)
            # self.add_column(MARKET_KEY, "resampled_price", resampled_prices)

            macd_data, macd_signal, macd_delta = macd(resampled_prices, self.macd_config.fast_period, self.macd_config.slow_period, self.macd_config.signal_period)
            # print(f"{macd_data.keys()}")
            # print(f"{macd_signal.keys()}")
            # print(f"{macd_hist.keys()}")
            self.add_column(MARKET_KEY, "macd", macd_data)
            self.add_column(MARKET_KEY, "macd_signal", macd_signal)
            self.add_column(MARKET_KEY, "macd_delta", macd_delta)

        print(f"start date: {_START_DATE}")

        new_trigger = AtTimeTrigger(time=datetime(_START_DATE.year, _START_DATE.month, _START_DATE.day, 0, 0, 0, 0), do=self.start_work)
        self.triggers.append(new_trigger)

        self.triggers.append(PeriodTrigger(time_delta=timedelta(minutes=CHECK_INTERVAL_MIN), do=self.on_price_check))

        self.triggers.append(AtTimeTrigger(time=datetime(_END_DATE.year, _END_DATE.month, _END_DATE.day, 23, 59, 0, 0), do=self.finish_work))

        if PRINT_PRICE:
            self.triggers.append(PeriodTrigger(time_delta=timedelta(minutes=1), do=self.print_price))

        pass

    def start_work(self, snapshot: Snapshot):
        # gmx_market: GmxV2Market = self.markets[MARKET_KEY]
        # result = gmx_market.deposit(0, self.initial_usdc)
        # print(f"result => {result}")
        # series = snapshot.market_status[MARKET_KEY]
        # print(f"long price: {series['longPrice']}, short price: {series['shortPrice']}, ethPrice: {snapshot.prices["WETH"]}, keys: {series.keys()}")
        self.open_short_mark_price = self.open_long_mark_price = snapshot.prices["WETH"]
        if POSITION_OPEN_STRATEGY == _MACD:
            series = snapshot.market_status[MARKET_KEY]
            self.last_macd_delta = series.macd_delta
        pass

    def print_price(self, snapshot: Snapshot):
        series = snapshot.market_status[MARKET_KEY]
        print(
                f"{snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")} => ethPrice: {self.format_price(series['longPrice'])}")
        # print(
        #     f"{snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")} => long price: {self.format_price(series['longPrice'])}, short price: {self.format_price(series['shortPrice'])}, ethPrice: {self.format_price(snapshot.prices["WETH"])}")
        # macd = series.macd
        # signal = series.macd_signal
        # hist = series.macd_hist
        # print(f"{macd} ({signal}): {macd} ({hist})")

        # series_hourly = series.hourly_price
        #
        # print(f"{snapshot.timestamp.strftime('%Y-%m-%d %H:%M:%S')} => hourly price: {self.format_price(series_hourly)}, is_nan: {math.isnan(series_hourly)}")


    def open_position(self, eth_price: Decimal, is_short: bool):
        self.position = Position(is_short)
        self.position.open_price = self.position.close_mark_price = eth_price
        if is_short:
            self.position.stop_loss_price = eth_price * (ONE + STOP_LOSS_PERCENT)
        else:
            self.position.stop_loss_price = eth_price * (ONE - STOP_LOSS_PERCENT)

    def check_open_short(self, snapshot: Snapshot, eth_price: Decimal) -> tuple[bool, Decimal]:

        if POSITION_OPEN_STRATEGY == _MACD:
            series = snapshot.market_status[MARKET_KEY]
            current_macd_delta = series.macd_delta

            if self.last_macd_delta is None or math.isnan(self.last_macd_delta) or current_macd_delta is None or math.isnan(current_macd_delta):
                return False, ZERO

            to_open =  self.last_macd_delta > ZERO > current_macd_delta
            return to_open, current_macd_delta

        else:
            mark_diff = self.open_short_mark_price - eth_price
            mark_diff_percent = mark_diff / self.open_short_mark_price
            # print(f"marked price: {self.open_short_mark_price} - {mark_diff_percent}%")
            return mark_diff_percent >= OPEN_PERCENT, mark_diff_percent

    pass

    def check_open_long(self, snapshot: Snapshot, eth_price: Decimal) -> tuple[bool, Decimal]:

        if POSITION_OPEN_STRATEGY == _MACD:
            series = snapshot.market_status[MARKET_KEY]
            current_macd_delta = series.macd_delta

            if current_macd_delta is None or math.isnan(current_macd_delta):
                return False, ZERO

            return current_macd_delta > ZERO > self.last_macd_delta, current_macd_delta

        else:
            mark_diff =  eth_price - self.open_long_mark_price
            mark_diff_percent = mark_diff / self.open_long_mark_price
            # print(f"marked price: {self.open_short_mark_price} - {mark_diff_percent}%")
            return mark_diff_percent >= OPEN_PERCENT, mark_diff_percent

    pass

    def open_short(self, snapshot: Snapshot, eth_price: Decimal, payload: Decimal):

        self.open_position(eth_price, True)

        if POSITION_OPEN_STRATEGY == _MACD:

            print(
                f"==>> [open]  short => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
                f"last MACD Delta: {self.format_price(self.last_macd_delta)}, current MADC Delta: {self.format_price(payload)}, "
                f"stop loss price: {self.format_price(self.position.stop_loss_price)}")
            pass
        else:

            print(
                f"==>> [open]  short => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
                f"mark price: {self.format_price(self.open_short_mark_price)}, price difference: {round(payload * HUNDRED, 2)}%, "
                f"stop loss price: {self.format_price(self.position.stop_loss_price)}")
            pass

    def open_long(self, snapshot: Snapshot, eth_price: Decimal, payload: Decimal):

        self.open_position(eth_price, False)

        if POSITION_OPEN_STRATEGY == _MACD:

            print(
                f"==>> [open]  long => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
                f"last MACD Delta: {self.format_price(self.last_macd_delta)}, current MADC Delta: {self.format_price(payload)}, "
                f"stop loss price: {self.format_price(self.position.stop_loss_price)}")
            pass
        else:

            print(
                f"==>> [open]  long => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
                f"mark price: {self.format_price(self.open_short_mark_price)}, price difference: {round(payload * HUNDRED, 2)}%, "
                f"stop loss price: {self.format_price(self.position.stop_loss_price)}")
            pass

    # def check_open_position(self, snapshot: Snapshot, eth_price: Decimal):
    #
    #     mark_diff = self.open_short_mark_price - eth_price
    #     mark_diff_percent = mark_diff / self.open_short_mark_price
    #     # print(f"marked price: {self.open_short_mark_price} - {mark_diff_percent}%")
    #     if mark_diff_percent >= OPEN_PERCENT:  # open short
    #         self.open_position(eth_price, True)
    #         print(
    #             f"==>> [open]  short => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
    #             f"mark price: {self.format_price(self.open_short_mark_price)}, price difference: {round(mark_diff_percent * HUNDRED, 2)}%, "
    #             f"stop loss price: {self.format_price(self.position.stop_loss_price)}")
    #         pass
    #
    #
    #
    # def check_open_short_MACD(self, snapshot: Snapshot, eth_price: Decimal):
    #     series = snapshot.market_status[MARKET_KEY]
    #     current_macd_delta = series.macd_delta
    #
    #     if current_macd_delta is None or math.isnan(current_macd_delta):
    #         return
    #
    #     if self.last_macd_delta > ZERO and current_macd_delta < ZERO:
    #         self.open_position(eth_price)
    #         print(
    #             f"==>> [open]  short => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
    #             f"last MACD Delta: {self.format_price(self.last_macd_delta)}, current MADC Delta: {self.format_price(current_macd_delta)}, "
    #             f"stop loss price: {self.format_price(self.position.stop_loss_price)}")
    #         pass
    #
    #     self.last_macd_delta = current_macd_delta
    #     pass

    def on_price_check(self, snapshot: Snapshot):

        if snapshot.timestamp.date() < _START_DATE:
            return

        eth_price = snapshot.prices["WETH"]

        to_open_short = False
        to_open_long = False
        payload = ZERO
        if self.position is None or (self.position.is_short and self.long_wl is not None) or (not self.position.is_short and self.short_wl is not None):

            if  self.short_wl is not None and self.position is None or (self.position is not None and not self.position.is_short):
                to_open_short, payload = self.check_open_short(snapshot, eth_price)

            if  self.long_wl is not None and not to_open_short and self.position is None or (self.position is not None and self.position.is_short):
                to_open_long, payload = self.check_open_long(snapshot, eth_price)


        self.check_and_close_position(snapshot, eth_price, to_open_long, to_open_short)

        if to_open_short:
            self.open_short(snapshot, eth_price, payload)
        elif to_open_long:
            self.open_long(snapshot, eth_price, payload)

        if POSITION_OPEN_STRATEGY == _MACD:
            series = snapshot.market_status[MARKET_KEY]
            current = series.macd_delta
            if not (current is None or math.isnan(current)):
                #print(f"last macd: {self.last_macd_delta}, current macd: {current}")
                self.last_macd_delta = series.macd_delta
        else:
            if eth_price > self.open_short_mark_price:
                self.open_short_mark_price = eth_price
            if eth_price < self.open_long_mark_price:
                self.open_long_mark_price = eth_price
        # self.last_price = eth_price
        pass

    def check_and_close_position(self, snapshot:Snapshot, eth_price: Decimal, to_open_long: bool, to_open_short: bool):
        if self.position is None:
            return

        is_short = self.position.is_short
        amount_diff: Decimal = ZERO
        wl: WinLoss | None = None
        if is_short and eth_price < self.position.close_mark_price or not is_short and eth_price > self.position.close_mark_price:
            self.position.close_mark_price = eth_price

        diff = eth_price - self.position.close_mark_price
        diff_percent = diff / self.position.close_mark_price
        # abs_diff_percent = diff_percent * Decimal(-1) if diff_percent < ZERO else diff
        if to_open_long or (is_short and eth_price >= self.position.stop_loss_price or diff_percent >= CLOSE_PERCENT):  # close short
            diff = self.position.open_price - eth_price
            short_return = diff / self.position.open_price
            amount_diff = self.current_usdc * short_return
            wl = self.short_wl

        elif to_open_short or (not is_short and eth_price <= self.position.stop_loss_price or diff_percent <= -CLOSE_PERCENT):  # close long
            diff = eth_price - self.position.open_price
            long_return = diff / self.position.open_price
            amount_diff = self.current_usdc * long_return
            wl = self.long_wl

        if wl is not None:

            self.current_usdc += amount_diff
            if amount_diff < ZERO:
                wl.total_loss -= amount_diff
                wl.loss_cnt += 1
            else:
                wl.total_gain += amount_diff
                wl.win_cnt += 1

            reason: str = ""
            if to_open_long:
                reason = ", need to open long"
            elif to_open_short:
                reason = ", need to open short"
            # elif diff_percent >= CLOSE_PERCENT:
            #     reason = f"close short because price change from lowest: {round(diff_percent * HUNDRED, 2)}%"
            # elif diff_percent <= -CLOSE_PERCENT:
            #     reason = f"close long because price change from highest: {round(diff_percent * HUNDRED, 2)}%"
            # else:
            #     reason = f"close short because price change from lowest: {round(diff_percent * HUNDRED, 2)}% and stop loss price: {self.position.stop_loss_price}"
            print(
                f"==>> [close] {"short" if is_short else "long"} => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
                f"{"lowest" if is_short else "highest"}_price: {self.format_price(self.position.close_mark_price)}, price change from {"lowest" if is_short else "highest"}: {round(diff_percent * HUNDRED, 2)}%, "
                f"{"short" if is_short else "long"}_open_price: {self.format_price(self.position.open_price)}, gain/loss: {self.format_price(amount_diff)}{reason}")
            self.position = None
            self.open_short_mark_price = self.open_long_mark_price = eth_price


    def finish_work(self, snapshot: Snapshot):
        eth_price = snapshot.prices["WETH"]

        if self.position is None:
            print(f"==>> finish with no position opened")
            return

        diff = self.position.open_price - eth_price if self.position.is_short else eth_price - self.position.open_price
        short_return = diff / self.position.open_price
        amount_diff = self.current_usdc * short_return
        self.current_usdc += amount_diff
        wl = self.short_wl if self.position.is_short else self.long_wl
        if amount_diff < ZERO:
            wl.total_loss -= amount_diff
            wl.loss_cnt += 1
        else:
            wl.total_gain += amount_diff
            wl.win_cnt += 1

        print(f"==>> final close {"short" if self.position.is_short else "long"} => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
              f"position_open_price: {self.format_price(self.position.open_price)}, gain/loss: {self.format_price(amount_diff)}")
        pass

    @staticmethod
    def format_price(number: Decimal) -> str:
        return f"{number:.4f}"

if __name__ == "__main__":
    usdc = TokenInfo(name="usdc", decimal=6)
    weth = TokenInfo(name="weth", decimal=18)
    pool = GmxV2Pool(weth, usdc, weth)
    config_file = toml.load("./gmx_v2_short_eth.toml")

    OPEN_PERCENT = Decimal(config_file.get("open_change_rate"))
    STOP_LOSS_PERCENT = Decimal(config_file.get("stop_loss_rate"))
    CLOSE_PERCENT = Decimal(config_file.get("trailing_stop_loss_rate"))
    sd = datetime.strptime(config_file.get("start_date"), "%Y-%m-%d")
    ed = datetime.strptime(config_file.get("end_date"), "%Y-%m-%d")

    _START_DATE = date(sd.year, sd.month, sd.day)
    _END_DATE = date(ed.year, ed.month, ed.day)
    INIT_USDC = Decimal(config_file.get("initial_amount"))
    CHECK_INTERVAL_MIN = config_file.get("check_interval_min")
    PRINT_PRICE = config_file.get("print_price")
    POSITION_OPEN_STRATEGY = config_file.get("position_open_strategy")
    dsd = config_file.get("data_start_date")
    if dsd is None or dsd == "":
        DATA_START_DATE = _START_DATE
    else:
        s = datetime.strptime(dsd, "%Y-%m-%d")
        DATA_START_DATE = date(s.year, s.month, s.day)

    to_long = config_file.get("run_long")
    to_short = config_file.get("run_short")

    print(f"==>> initial value: {INIT_USDC}, data_start_date: {DATA_START_DATE}, start_date: {_START_DATE}, end_date: {_END_DATE}, time interval (minute): {CHECK_INTERVAL_MIN}, take profit percent: {CLOSE_PERCENT}, stop loss percent: {STOP_LOSS_PERCENT}")

    macd_config = config_file.get("macd")
    macd_config = MacdConfig(**macd_config)

    print(f"==>> macd config: {macd_config}")

    market = GmxV2Market(MARKET_KEY, pool, data_path="../real-data/gmx_v2/arb_short_eth/")
    market.load_data(
        ChainType.arbitrum, "0x70d95587d40a2caf56bd97485ab3eec10bee6336", DATA_START_DATE, _END_DATE
    )

    actuator = Actuator()
    actuator.broker.add_market(market)
    actuator.broker.set_balance(usdc, INIT_USDC)
    actuator.broker.set_balance(weth, 0)
    strat = GmxV2LpStrategy(macd_config, to_short, to_long)
    actuator.strategy = strat  # set strategy to actuator
    actuator.set_price(market.get_price_from_data())  # set actuator price
    actuator.run(print_result=False)

    total_gain = ZERO
    total_gain_cnt = 0
    total_loss = ZERO
    total_loss_cnt = 0

    return_rate = ((strat.current_usdc / strat.initial_usdc) - ONE) * HUNDRED
    print(f"==>> final amount: {round(strat.current_usdc, 4)}, pnl: {round(strat.current_usdc - strat.initial_usdc, 4)}, return rate: {round(return_rate, 2)}% ")
    if strat.long_wl is not None:
        print(f"==>> long win({strat.long_wl.win_cnt}): {round(strat.long_wl.total_gain, 4)}, loss({strat.long_wl.loss_cnt}): {round(strat.long_wl.total_loss, 4)}")
        total_gain += strat.long_wl.total_gain
        total_gain_cnt += strat.long_wl.win_cnt
        total_loss += strat.long_wl.total_loss
        total_loss_cnt += strat.long_wl.loss_cnt

    if strat.short_wl is not None:
        print(f"==>> short win({strat.short_wl.win_cnt}): {round(strat.short_wl.total_gain, 4)}, loss({strat.short_wl.loss_cnt}): {round(strat.short_wl.total_loss, 4)}")
        total_gain += strat.short_wl.total_gain
        total_gain_cnt += strat.short_wl.win_cnt
        total_loss += strat.short_wl.total_loss
        total_loss_cnt += strat.short_wl.loss_cnt

    if to_long and to_short:
        print(f"==>> total gain({total_gain_cnt}): {round(total_gain, 4)}, loss({total_loss_cnt}): {round(total_loss, 4)}")

