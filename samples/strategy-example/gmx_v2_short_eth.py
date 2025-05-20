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

_HUNDRED = HUNDRED
_ONE = ONE
MARKET_KEY = MarketInfo("GMX_ETH", MarketTypeEnum.gmx_v2)

OPEN_PERCENT = Decimal("0.01")
STOP_LOSS_PERCENT = Decimal("0.01")
CLOSE_PERCENT = Decimal("0.01")
start_date, end_date = date(2024, 10, 1), date(2024, 12, 31)
INIT_USDC = Decimal("0")
CHECK_INTERVAL_MIN = 1
PRINT_PRICE = False
SHORT_OPEN_STRATEGY = "standard"


@dataclass
class MacdConfig:
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    sample_period: str = "1h"


class GmxV2LpStrategy(Strategy):

    def __init__(self, macd_config: MacdConfig = MacdConfig()):
        super().__init__()
        self.mark_price: Decimal = ZERO
        # self.last_price: Decimal = ZERO
        self.initial_usdc: Decimal = INIT_USDC
        self.current_usdc: Decimal = self.initial_usdc
        # self.short_position_opened: bool = False
        self.short_open_price: Decimal | None = None
        self.short_stop_loss_price: Decimal = ZERO
        self.short_lowest_price: Decimal = ZERO
        self.total_gain: Decimal = ZERO
        self.total_loss: Decimal = ZERO
        self.total_gain_cnt: int = 0
        self.total_loss_cnt: int = 0
        self.last_macd_delta: Decimal = ZERO
        self.macd_config = macd_config


    def initialize(self):

        market_data = self.data[MARKET_KEY]
        # print(f"{market_data.keys()}")
        if SHORT_OPEN_STRATEGY == "macd":

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

        new_trigger = AtTimeTrigger(time=datetime(start_date.year, start_date.month, start_date.day, 0,0,0,0), do=self.work)
        self.triggers.append(new_trigger)

        self.triggers.append(PeriodTrigger(time_delta=timedelta(minutes=CHECK_INTERVAL_MIN), do=self.on_price_check))

        self.triggers.append(AtTimeTrigger(time=datetime(end_date.year, end_date.month, end_date.day, 23,59,0,0), do=self.finish_work))

        if PRINT_PRICE:
            self.triggers.append(PeriodTrigger(time_delta=timedelta(minutes=1), do=self.print_price))

        pass

    def work(self, snapshot: Snapshot):
        # gmx_market: GmxV2Market = self.markets[MARKET_KEY]
        # result = gmx_market.deposit(0, self.initial_usdc)
        # print(f"result => {result}")
        # series = snapshot.market_status[MARKET_KEY]
        # print(f"long price: {series['longPrice']}, short price: {series['shortPrice']}, ethPrice: {snapshot.prices["WETH"]}, keys: {series.keys()}")
        self.last_price = self.mark_price = snapshot.prices["WETH"]
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


    def open_short(self, eth_price: Decimal):
        self.short_open_price = eth_price
        self.short_stop_loss_price = eth_price * (ONE + STOP_LOSS_PERCENT)
        self.short_lowest_price = eth_price

    def check_open_short(self, snapshot: Snapshot, eth_price: Decimal):

        mark_diff = self.mark_price - eth_price
        mark_diff_percent = mark_diff / self.mark_price
        # print(f"marked price: {self.mark_price} - {mark_diff_percent}%")
        if mark_diff_percent >= OPEN_PERCENT:  # open short
            self.open_short(eth_price)
            print(
                f"==>> [open]  short => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
                f"mark price: {self.format_price(self.mark_price)}, price difference: {round(mark_diff_percent * HUNDRED, 2)}%, "
                f"stop loss price: {self.format_price(self.short_stop_loss_price)}")
            pass

    def check_open_short_MACD(self, snapshot: Snapshot, eth_price: Decimal):
        series = snapshot.market_status[MARKET_KEY]
        current_macd_delta = series.macd_delta

        if current_macd_delta is None or math.isnan(current_macd_delta):
            return

        if self.last_macd_delta > ZERO and current_macd_delta < ZERO:
            self.open_short(eth_price)
            print(
                f"==>> [open]  short => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
                f"last MACD Delta: {self.format_price(self.last_macd_delta)}, current MADC Delta: {self.format_price(current_macd_delta)}, "
                f"stop loss price: {self.format_price(self.short_stop_loss_price)}")
            pass

        self.last_macd_delta = current_macd_delta
        pass

    def on_price_check(self, snapshot: Snapshot):
        eth_price = snapshot.prices["WETH"]

        if self.short_open_price is None:

            if SHORT_OPEN_STRATEGY == "macd":
                self.check_open_short_MACD(snapshot, eth_price)
            else:
                self.check_open_short(snapshot, eth_price)
                if eth_price > self.mark_price:
                    self.mark_price = eth_price


        else:

            if eth_price < self.short_lowest_price:
                self.short_lowest_price = eth_price

            diff = eth_price - self.short_lowest_price
            diff_percent = diff / self.short_lowest_price
            # abs_diff_percent = diff_percent * Decimal(-1) if diff_percent < ZERO else diff
            if eth_price >= self.short_stop_loss_price or diff_percent >= CLOSE_PERCENT: # close short
                diff = self.short_open_price - eth_price
                short_return = diff / self.short_open_price
                amount_diff = self.current_usdc * short_return
                self.current_usdc += amount_diff
                if amount_diff < ZERO:
                    self.total_loss -= amount_diff
                    self.total_loss_cnt += 1
                else:
                    self.total_gain += amount_diff
                    self.total_gain_cnt += 1

                print(f"==>> [close] short => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
                      f"lowest_price: {self.format_price(self.short_lowest_price)}, price change from lowest: {round(diff_percent * HUNDRED, 2)}%, "
                      f"short_open_price: {self.format_price(self.short_open_price)}, gain/loss: {self.format_price(amount_diff)}")
                self.short_open_price = None
                self.mark_price = eth_price

        # self.last_price = eth_price
        pass

    def finish_work(self, snapshot: Snapshot):
        eth_price = snapshot.prices["WETH"]

        if self.short_open_price is None:
            print(f"==>> no short opened")
            return

        diff = self.short_open_price - eth_price
        short_return = diff / self.short_open_price
        amount_diff = self.current_usdc * short_return
        self.current_usdc += amount_diff
        if amount_diff < ZERO:
            self.total_loss -= amount_diff
            self.total_loss_cnt += 1
        else:
            self.total_gain += amount_diff
            self.total_gain_cnt += 1

        print(f"==>> final close short => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
              f"last_price: {self.format_price(self.last_price)}, "
              f"short_open_price: {self.format_price(self.short_open_price)}, gain/loss: {self.format_price(amount_diff)}")
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

    start_date = date(sd.year, sd.month, sd.day)
    end_date = date(ed.year, ed.month, ed.day)
    INIT_USDC = Decimal(config_file.get("initial_amount"))
    CHECK_INTERVAL_MIN = config_file.get("check_interval_min")
    PRINT_PRICE = config_file.get("print_price")
    SHORT_OPEN_STRATEGY = config_file.get("short_open_strategy")

    print(f"==>> initial value: {INIT_USDC}, start_date: {start_date}, end_date: {end_date}, time interval (minute): {CHECK_INTERVAL_MIN}, take profit percent: {CLOSE_PERCENT}, stop loss percent: {STOP_LOSS_PERCENT}")

    macd_config = config_file.get("macd")
    macd_config = MacdConfig(**macd_config)

    print(f"==>> macd config: {macd_config}")

    market = GmxV2Market(MARKET_KEY, pool, data_path="../real-data/gmx_v2/arb_short_eth/")
    market.load_data(
        ChainType.arbitrum, "0x70d95587d40a2caf56bd97485ab3eec10bee6336", start_date, end_date
    )

    actuator = Actuator()
    actuator.broker.add_market(market)
    actuator.broker.set_balance(usdc, INIT_USDC)
    actuator.broker.set_balance(weth, 0)
    strat = GmxV2LpStrategy(macd_config)
    actuator.strategy = strat  # set strategy to actuator
    actuator.set_price(market.get_price_from_data())  # set actuator price
    actuator.run(print_result=False)

    return_rate = ((strat.current_usdc / strat.initial_usdc) - ONE) * HUNDRED
    print(f"==>> final amount: {round(strat.current_usdc, 4)}, pnl: {round(strat.current_usdc - strat.initial_usdc, 4)}, return rate: {round(return_rate, 2)}%, gain({strat.total_gain_cnt}): {round(strat.total_gain, 4)}, loss({strat.total_loss_cnt}): {round(strat.total_loss, 4)}")

