import math
from datetime import date, datetime, timedelta

import pandas as pd
from demeter import TokenInfo, Actuator, Strategy, Snapshot, ChainType, MarketInfo, AtTimeTrigger, PeriodTrigger, MarketTypeEnum
from demeter.gmx import GmxV2Market
from demeter.gmx._typing2 import GmxV2Pool
import toml

from chaos_lab_utils import macd as macd_function, resample_data, stochRSI
from math_const import *
from gmx_model import *

# To print all the columns of dataframe, we should set up display option.
pd.options.display.max_columns = None
pd.set_option("display.width", 5000)

MARKET_KEY = MarketInfo("GMX_ETH", MarketTypeEnum.gmx_v2)

class GmxV2LpStrategy(Strategy):

    def __init__(self, gmx_config: GmxConfig):
        super().__init__()
        self.open_short_mark_price: Decimal = ZERO
        self.open_long_mark_price: Decimal = ZERO
        # self.close_mark_price: Decimal = ZERO

        # self.last_price: Decimal = ZERO
        self.gmx_config = gmx_config
        self.initial_usdc: Decimal = Decimal(gmx_config.initial_amount)
        self.current_usdc: Decimal = self.initial_usdc
        self.position: Position | None = None
        self.last_strategy_delta: Decimal = ZERO
        self.long_wl: WinLoss | None = WinLoss() if gmx_config.run_long else None
        self.short_wl: WinLoss | None = WinLoss() if gmx_config.run_short else None
        self.pending_collateral_fee: Decimal = ZERO
        self.total_fee: Decimal = ZERO
        self.entry_delayed: bool = False
        self.is_entry_short: bool = False # False = long, True = short
        self.started: bool = False



    def initialize(self):

        market_data = self.data[MARKET_KEY]
        # print(f"{market_data.keys()}")
        if self.gmx_config.position_open_strategy == IndicatorType.MACD.value:

            resampled_prices = resample_data(market_data.longPrice, self.gmx_config.strategy_sample_period)
            # print(resampled_prices)
            # self.add_column(MARKET_KEY, "resampled_price", resampled_prices)

            macd_data, macd_signal, macd_delta = macd_function(resampled_prices, self.gmx_config.macd.fast_period, self.gmx_config.macd.slow_period, self.gmx_config.macd.signal_period)
            # print(f"{macd_data.keys()}")
            # print(f"{macd_signal.keys()}")
            # print(f"{macd_hist.keys()}")
            self.add_column(MARKET_KEY, "macd", macd_data)
            self.add_column(MARKET_KEY, "macd_signal", macd_signal)
            self.add_column(MARKET_KEY, "macd_delta", macd_delta)
        elif self.gmx_config.position_open_strategy == IndicatorType.RSI.value:
            resampled_prices = resample_data(market_data.longPrice, self.gmx_config.strategy_sample_period)

            rsi_fastk, rsi_fastd, rsi_delta = stochRSI(resampled_prices, self.gmx_config.stock_rsi.time_period,
                                                      self.gmx_config.stock_rsi.fastk_period,
                                                      self.gmx_config.stock_rsi.fastd_period, self.gmx_config.stock_rsi.fastd_matype)
            # print(f"{macd_data.keys()}")
            # print(f"{macd_signal.keys()}")
            # print(f"{macd_hist.keys()}")
            self.add_column(MARKET_KEY, "rsi_fastk", rsi_fastk)
            self.add_column(MARKET_KEY, "rsi_fastd", rsi_fastd)
            self.add_column(MARKET_KEY, "rsi_delta", rsi_delta)

        # Parse start_date and end_date from gmx_config
        sd = datetime.strptime(self.gmx_config.start_date, "%Y-%m-%d")
        ed = datetime.strptime(self.gmx_config.end_date, "%Y-%m-%d")
        start_date = date(sd.year, sd.month, sd.day)
        end_date = date(ed.year, ed.month, ed.day)

        print(f"start date: {start_date}")

        new_trigger = AtTimeTrigger(time=sd, do=self.start_work)
        self.triggers.append(new_trigger)

        self.triggers.append(PeriodTrigger(time_delta=timedelta(minutes=self.gmx_config.check_interval_min), do=self.on_price_check))

        self.triggers.append(AtTimeTrigger(time=datetime(end_date.year, end_date.month, end_date.day, 23, 59, 0, 0), do=self.finish_work))

        if self.gmx_config.print_price:
            self.triggers.append(PeriodTrigger(time_delta=timedelta(minutes=1), do=self.print_price))

        pass

    def start_work(self, snapshot: Snapshot):
        # gmx_market: GmxV2Market = self.markets[MARKET_KEY]
        # result = gmx_market.deposit(0, self.initial_usdc)
        # print(f"result => {result}")
        # series = snapshot.market_status[MARKET_KEY]
        # print(f"long price: {series['longPrice']}, short price: {series['shortPrice']}, ethPrice: {snapshot.prices["WETH"]}, keys: {series.keys()}")
        self.started = True
        self.open_short_mark_price = self.open_long_mark_price = snapshot.prices["WETH"]
        if self.gmx_config.position_open_strategy == IndicatorType.MACD.value:
            series = snapshot.market_status[MARKET_KEY]
            self.last_strategy_delta = series.macd_delta
        elif self.gmx_config.position_open_strategy == IndicatorType.RSI.value:
            series = snapshot.market_status[MARKET_KEY]
            self.last_strategy_delta = series.rsi_delta
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

    def cal_and_subtract_fee(self, is_open: bool) -> Decimal:
        position = self.current_usdc
        fee = position * Decimal(self.gmx_config.trading_fee_rate)
        if is_open:
            self.pending_collateral_fee = fee
        else:
            total_fee = fee + self.pending_collateral_fee
            self.total_fee += total_fee
            self.current_usdc -= total_fee
            self.pending_collateral_fee = ZERO
        return fee

    def get_current_strategy_delta(self, snapshot: Snapshot) -> Decimal | None:
        series = snapshot.market_status[MARKET_KEY]
        if self.gmx_config.position_open_strategy == IndicatorType.MACD.value:
            current_strategy_delta = series.macd_delta
        elif self.gmx_config.position_open_strategy == IndicatorType.RSI.value:
            current_strategy_delta = series.rsi_delta
        else:
            current_strategy_delta = None

        current_strategy_delta = round(current_strategy_delta, self.gmx_config.strategy_delta_rounding_decimal) if current_strategy_delta is not None else None

        return current_strategy_delta

    def open_position(self, eth_price: Decimal, is_short: bool) -> Decimal:
        self.position = Position(is_short)
        self.position.open_price = self.position.close_mark_price = eth_price
        stop_loss_percent = Decimal(self.gmx_config.stop_loss_rate)
        if is_short:
            self.position.stop_loss_price = eth_price * (ONE + stop_loss_percent)
        else:
            self.position.stop_loss_price = eth_price * (ONE - stop_loss_percent)
        fee = self.cal_and_subtract_fee(True)
        return fee

    def check_open_short(self, snapshot: Snapshot, eth_price: Decimal) -> tuple[bool, Decimal]:

        if not self.gmx_config.position_open_strategy == IndicatorType.STANDARD.value:
            current_strategy_delta = self.get_current_strategy_delta(snapshot)

            if self.last_strategy_delta is None or math.isnan(
                    self.last_strategy_delta) or current_strategy_delta is None or math.isnan(current_strategy_delta) or current_strategy_delta == ZERO:
                return False, ZERO

            to_open = self.last_strategy_delta > ZERO > current_strategy_delta
            return to_open, current_strategy_delta

        else:
            mark_diff = self.open_short_mark_price - eth_price
            mark_diff_percent = mark_diff / self.open_short_mark_price
            # print(f"marked price: {self.open_short_mark_price} - {mark_diff_percent}%")
            open_percent = Decimal(self.gmx_config.open_change_rate)
            return mark_diff_percent >= open_percent, mark_diff_percent

    pass

    def check_open_long(self, snapshot: Snapshot, eth_price: Decimal) -> tuple[bool, Decimal]:

        if not self.gmx_config.position_open_strategy == IndicatorType.STANDARD.value:
            current_strategy_delta = self.get_current_strategy_delta(snapshot)

            if self.last_strategy_delta is None or math.isnan(
                    self.last_strategy_delta) or current_strategy_delta is None or math.isnan(current_strategy_delta) or current_strategy_delta == ZERO:
                return False, ZERO

            return current_strategy_delta > ZERO > self.last_strategy_delta, current_strategy_delta

        else:
            mark_diff =  eth_price - self.open_long_mark_price
            mark_diff_percent = mark_diff / self.open_long_mark_price
            # print(f"marked price: {self.open_short_mark_price} - {mark_diff_percent}%")
            open_percent = Decimal(self.gmx_config.open_change_rate)
            return mark_diff_percent >= open_percent, mark_diff_percent

    pass

    def open_short(self, snapshot: Snapshot, eth_price: Decimal, payload: Decimal):

        fee = self.open_position(eth_price, True)

        if not self.gmx_config.position_open_strategy == IndicatorType.STANDARD.value:

            strat = self.gmx_config.position_open_strategy.upper()

            print(
                f"==>> [open   ] short => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
                f"last {strat} Delta: {self.format_price(self.last_strategy_delta)}, current {strat} Delta: {self.format_price(payload)}, "
                f"stop loss price: {self.format_price(self.position.stop_loss_price)}, position amount: {self.format_price(self.current_usdc)}, "
                f"collateral fee: {self.format_price(fee)}")

            pass
        else:

            print(
                f"==>> [open   ] short => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
                f"mark price: {self.format_price(self.open_short_mark_price)}, price difference: {round(payload * HUNDRED, 2)}%, "
                f"stop loss price: {self.format_price(self.position.stop_loss_price)}, position amount: {self.format_price(self.current_usdc)}, "
                f"collateral fee: {self.format_price(fee)}")
            pass

    def open_long(self, snapshot: Snapshot, eth_price: Decimal, payload: Decimal):

        fee = self.open_position(eth_price, False)

        if not self.gmx_config.position_open_strategy == IndicatorType.STANDARD.value:

            strat = self.gmx_config.position_open_strategy.upper()
            print(
                f"==>> [open   ] long  => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
                f"last {strat} Delta: {self.format_price(self.last_strategy_delta)}, current {strat} Delta: {self.format_price(payload)}, "
                f"stop loss price: {self.format_price(self.position.stop_loss_price)}, position amount: {self.format_price(self.current_usdc)}, "
                f"collateral fee: {self.format_price(fee)}")
            pass
        else:

            print(
                f"==>> [open   ] long  => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
                f"mark price: {self.format_price(self.open_short_mark_price)}, price difference: {round(payload * HUNDRED, 2)}%, "
                f"stop loss price: {self.format_price(self.position.stop_loss_price)}, position amount: {self.format_price(self.current_usdc)}, "
                f"collateral fee: {self.format_price(fee)}")
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

    @staticmethod
    def has_strategy_value(strategy_value: Decimal | None) -> bool:
        return not (strategy_value is None or math.isnan(strategy_value))

    def on_price_check(self, snapshot: Snapshot):

        # Parse start_date from gmx_config
        # sd = datetime.strptime(self.gmx_config.start_date, "%Y-%m-%d")
        # start_date = date(sd.year, sd.month, sd.day)
        #
        # if snapshot.timestamp.date() < start_date:
        #     return
        if not self.started:
            return

        eth_price = snapshot.prices["WETH"]

        to_open_short = False
        to_open_long = False
        payload = ZERO

        current_strategy_delta: Decimal | None = None
        if not self.gmx_config.position_open_strategy == IndicatorType.STANDARD.value:
            current_strategy_delta = self.get_current_strategy_delta(snapshot)

            if self.entry_delayed: # entry_delayed will be true only if macd


                if self.has_strategy_value(current_strategy_delta):
                    if self.is_entry_short:
                        self.check_and_close_position(snapshot, eth_price, False, True)
                        self.open_short(snapshot, eth_price, current_strategy_delta)
                    else:
                        self.check_and_close_position(snapshot, eth_price, True, False)
                        self.open_long(snapshot, eth_price, current_strategy_delta)
                    self.entry_delayed = False
                    self.last_strategy_delta = current_strategy_delta if not current_strategy_delta == 0 else self.last_strategy_delta
                    return
                else:
                    self.check_and_close_position(snapshot, eth_price, False, False)
                    return  # delayed entry and still not time for entry

        if self.position is None or (self.position.is_short and self.long_wl is not None) or (not self.position.is_short and self.short_wl is not None):

            if  self.short_wl is not None and self.position is None or (self.position is not None and not self.position.is_short):
                to_open_short, payload = self.check_open_short(snapshot, eth_price)

            if  self.long_wl is not None and not to_open_short and self.position is None or (self.position is not None and self.position.is_short):
                to_open_long, payload = self.check_open_long(snapshot, eth_price)

        if self.gmx_config.delayed_entry and (to_open_short or to_open_long):

            self.is_entry_short = to_open_short # if to_open_short is False to_open_long must be True

            self.check_and_close_position(snapshot, eth_price, False, False)
            self.entry_delayed = True
            strat = self.gmx_config.position_open_strategy.upper()
            print(
                f"==>> [delayed] {"short" if self.is_entry_short else "long "} => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
                f"last {strat} Delta: {self.format_price(self.last_strategy_delta)}, current {strat} Delta: {current_strategy_delta}")

        else:
            self.check_and_close_position(snapshot, eth_price, to_open_long, to_open_short)

            if to_open_short:
                self.open_short(snapshot, eth_price, payload)
            elif to_open_long:
                self.open_long(snapshot, eth_price, payload)

        if not self.gmx_config.position_open_strategy == IndicatorType.STANDARD.value:
            # series = snapshot.market_status[MARKET_KEY]
            # current = series.macd_delta
            if self.has_strategy_value(current_strategy_delta):
                #print(f"last macd: {self.last_macd_delta}, current macd: {current}")
                self.last_strategy_delta = current_strategy_delta if not current_strategy_delta == 0 else self.last_strategy_delta
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
        close_percent = Decimal(self.gmx_config.trailing_stop_loss_rate)
        if to_open_long or (is_short and eth_price >= self.position.stop_loss_price or diff_percent >= close_percent):  # close short
            diff = self.position.open_price - eth_price
            short_return = diff / self.position.open_price
            amount_diff = self.current_usdc * short_return
            wl = self.short_wl

        elif to_open_short or (not is_short and eth_price <= self.position.stop_loss_price or diff_percent <= -close_percent):  # close long
            diff = eth_price - self.position.open_price
            long_return = diff / self.position.open_price
            amount_diff = self.current_usdc * long_return
            wl = self.long_wl

        if wl is not None:

            self.current_usdc += amount_diff
            fee = self.cal_and_subtract_fee(False)
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

            print(
                f"==>> [close  ] {"short" if is_short else "long "} => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
                f"{"lowest" if is_short else "highest"}_price: {self.format_price(self.position.close_mark_price)}, price change from {"lowest" if is_short else "highest"}: {round(diff_percent * HUNDRED, 2)}%, "
                f"{"short" if is_short else "long"}_open_price: {self.format_price(self.position.open_price)}, gain/loss: {self.format_price(amount_diff)}, "
                f"fee: {self.format_price(fee)}{reason}")
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
        fee = self.cal_and_subtract_fee(False)

        wl = self.short_wl if self.position.is_short else self.long_wl
        if amount_diff < ZERO:
            wl.total_loss -= amount_diff
            wl.loss_cnt += 1
        else:
            wl.total_gain += amount_diff
            wl.win_cnt += 1

        print(f"==>> final close {"short" if self.position.is_short else "long"} => date: {snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, price: {self.format_price(eth_price)}, "
              f"position_open_price: {self.format_price(self.position.open_price)}, gain/loss: {self.format_price(amount_diff)}, "
              f"fee: {self.format_price(fee)}")
        pass

    @staticmethod
    def format_price(number: Decimal) -> str:
        return f"{number:.4f}"

if __name__ == "__main__":
    usdc = TokenInfo(name="usdc", decimal=6)
    weth = TokenInfo(name="weth", decimal=18)
    pool = GmxV2Pool(weth, usdc, weth)
    config_file = toml.load("./gmx_v2_short_eth.toml")

    # Convert nested dictionaries to appropriate config objects
    if "stock_rsi" in config_file:
        stock_rsi_dict = config_file.pop("stock_rsi")
        stock_rsi = StockRsiConfig(**stock_rsi_dict)
        config_file["stock_rsi"] = stock_rsi

    if "macd" in config_file:
        macd_dict = config_file.pop("macd")
        macd = MacdConfig(**macd_dict)
        config_file["macd"] = macd

    gmx_config = GmxConfig(**config_file)

    print(f"==>> gmx config: {gmx_config}")

    market = GmxV2Market(MARKET_KEY, pool, data_path="../real-data/gmx_v2/arb_short_eth/")
    # Parse data_start_date and end_date from gmx_config
    dsd = gmx_config.data_start_date
    if dsd is None or dsd == "":
        s = datetime.strptime(gmx_config.start_date, "%Y-%m-%d")
        data_start_date = date(s.year, s.month, s.day)
    else:
        s = datetime.strptime(dsd, "%Y-%m-%d")
        data_start_date = date(s.year, s.month, s.day)

    ed = datetime.strptime(gmx_config.end_date, "%Y-%m-%d")
    end_date = date(ed.year, ed.month, ed.day)

    # print(f"==>> initial value: {Decimal(gmx_config.initial_amount)}, data_start_date: {data_start_date}, start_date: {date(s.year, s.month, s.day)}, end_date: {end_date}, time interval (minute): {gmx_config.check_interval_min}, take profit percent: {Decimal(gmx_config.trailing_stop_loss_rate)}, stop loss percent: {Decimal(gmx_config.stop_loss_rate)}")

    market.load_data(
        ChainType.arbitrum, "0x70d95587d40a2caf56bd97485ab3eec10bee6336", data_start_date, end_date
    )

    actuator = Actuator()
    actuator.broker.add_market(market)
    actuator.broker.set_balance(usdc, Decimal(gmx_config.initial_amount))
    actuator.broker.set_balance(weth, 0)
    strat = GmxV2LpStrategy(gmx_config)
    actuator.strategy = strat  # set strategy to actuator
    actuator.set_price(market.get_price_from_data())  # set actuator price
    actuator.run(print_result=False)

    total_gain = ZERO
    total_gain_cnt = 0
    total_loss = ZERO
    total_loss_cnt = 0

    return_rate = ((strat.current_usdc / strat.initial_usdc) - ONE) * HUNDRED
    print(f"==>> final amount: {round(strat.current_usdc, 4)}, pnl: {round(strat.current_usdc - strat.initial_usdc, 4)}, return rate: {round(return_rate, 2)}%, total fee: {round(strat.total_fee, 4)} ")
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

    if gmx_config.run_long and gmx_config.run_short:
        print(f"==>> total gain({total_gain_cnt}): {round(total_gain, 4)}, loss({total_loss_cnt}): {round(total_loss, 4)}")



###
