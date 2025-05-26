from datetime import date, datetime, timedelta
from decimal import Decimal

import pandas as pd

from demeter import TokenInfo, Actuator, Strategy, Snapshot, ChainType, MarketInfo, AtTimeTrigger, PeriodTrigger, MarketTypeEnum
from demeter.gmx import GmxV2Market
from demeter.gmx._typing2 import GmxV2Pool

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
CHECK_INTERVAL_MIN = 5

class GmxV2LpStrategy(Strategy):

    def __init__(self):
        super().__init__()
        self.mark_price: Decimal = ZERO
        self.last_price: Decimal = ZERO
        self.initial_usdc: Decimal = INIT_USDC
        self.current_usdc: Decimal = self.initial_usdc
        # self.short_position_opened: bool = False
        self.short_open_price: Decimal | None = None
        self.short_stop_loss_price: Decimal = ZERO
        self.total_gain: Decimal = ZERO
        self.total_loss: Decimal = ZERO
        self.total_gain_cnt: int = 0
        self.total_loss_cnt: int = 0


    def initialize(self):
        new_trigger = AtTimeTrigger(time=datetime(start_date.year, start_date.month, start_date.day, 0,0,0,0), do=self.work)
        self.triggers.append(new_trigger)

        self.triggers.append(PeriodTrigger(time_delta=timedelta(minutes=CHECK_INTERVAL_MIN), do=self.on_price_check))

        self.triggers.append(AtTimeTrigger(time=datetime(end_date.year, end_date.month, end_date.day, 23,59,0,0), do=self.finish_work))
        # self.triggers.append(PeriodTrigger(time_delta=timedelta(hours=2), do=self.print_price))
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
            f"{snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")} => long price: {self.format_price(series['longPrice'])}, short price: {self.format_price(series['shortPrice'])}, ethPrice: {self.format_price(snapshot.prices["WETH"])}")

    def on_price_check(self, snapshot: Snapshot):
        eth_price = snapshot.prices["WETH"]


        if self.short_open_price is None:
            mark_diff = self.mark_price - eth_price
            mark_diff_percent = mark_diff / self.mark_price
            # print(f"marked price: {self.open_short_mark_price} - {mark_diff_percent}%")
            if mark_diff_percent >= OPEN_PERCENT: # open short
                self.short_open_price = eth_price
                self.short_stop_loss_price = eth_price * (ONE + STOP_LOSS_PERCENT)
                print(
                    f"==>> [open]  short => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
                    f"mark price: {self.format_price(self.mark_price)}, price difference: {round(mark_diff_percent * HUNDRED, 2)}%, "
                    f"stop loss price: {self.format_price(self.short_stop_loss_price)}")
                pass

            if eth_price > self.mark_price:
                self.mark_price = eth_price
        else:
            diff = eth_price - self.last_price
            diff_percent = diff / self.last_price
            # abs_diff_percent = diff_percent * Decimal(-1) if diff_percent < ZERO else diff
            if eth_price >= self.short_stop_loss_price or diff_percent >= CLOSE_PERCENT: # open short
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
                      f"last_price: {self.format_price(self.last_price)}, price change: {round(diff_percent * HUNDRED, 2)}%, "
                      f"short_open_price: {self.format_price(self.short_open_price)}, gain/loss: {self.format_price(amount_diff)}")
                self.short_open_price = None
                self.mark_price = eth_price

        self.last_price = eth_price
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
    sd = datetime.strptime(config_file.get("_START_DATE"), "%Y-%m-%d")
    ed = datetime.strptime(config_file.get("_END_DATE"), "%Y-%m-%d")

    start_date = date(sd.year, sd.month, sd.day)
    end_date = date(ed.year, ed.month, ed.day)
    INIT_USDC = Decimal(config_file.get("initial_amount"))
    CHECK_INTERVAL_MIN = config_file.get("check_interval_min")

    print(f"==>> initial value: {INIT_USDC}, _START_DATE: {start_date}, _END_DATE: {end_date}, time interval (minute): {CHECK_INTERVAL_MIN}, take profit percent: {CLOSE_PERCENT}, stop loss percent: {STOP_LOSS_PERCENT}")

    market = GmxV2Market(MARKET_KEY, pool, data_path="../real-data/gmx_v2/arb_short_eth/")
    market.load_data(
        ChainType.arbitrum, "0x70d95587d40a2caf56bd97485ab3eec10bee6336", start_date, end_date
    )

    actuator = Actuator()
    actuator.broker.add_market(market)
    actuator.broker.set_balance(usdc, INIT_USDC)
    actuator.broker.set_balance(weth, 0)
    strat = GmxV2LpStrategy()
    actuator.strategy = strat  # set strategy to actuator
    actuator.set_price(market.get_price_from_data())  # set actuator price
    actuator.run(print_result=False)

    return_rate = ((strat.current_usdc / strat.initial_usdc) - ONE) * HUNDRED
    print(f"==>> final amount: {round(strat.current_usdc, 4)}, pnl: {round(strat.current_usdc - strat.initial_usdc, 4)}, return rate: {round(return_rate, 2)}%, gain({strat.total_gain_cnt}): {round(strat.total_gain, 4)}, loss({strat.total_loss_cnt}): {round(strat.total_loss, 4)}")

