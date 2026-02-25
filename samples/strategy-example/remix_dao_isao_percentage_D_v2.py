import copy

from dataclasses import dataclass
import math
import multiprocessing
import random
import time
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import List, Tuple, Dict

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
from demeter.uniswap import UniLpMarket, UniV3Pool, V3CoreLib, base_unit_price_to_sqrt_price_x96
from datetime import date, timedelta, datetime

from remix_dao_utils import RemixDaoUtils, RemixDAOParams, WeeklyTrigger, performance_metrics_for_dca, getPrice
from export_file import export_file, ExportData, export_apr_results, export_stable_apr_results
from chaos_lab_utils import standard_deviation_over_last, average_true_range
from rm_types import RescaleFrequency, TestParams, GlobalParams, RangeStrategy, PriceActionLog, DcaTiming, DcaAddition
from market_v2 import UniLpMarketV2
from math_const import ZERO, ONE, HUNDRED, CONSERVATIVE_FLUCTUATION
from base_strategy import BaseRemixDaoStrategy

conservative_fluctuation = CONSERVATIVE_FLUCTUATION



class RemixDaoDcaWeekStratStrategy(BaseRemixDaoStrategy):

    def __init__(self, _utils: RemixDaoUtils, _params: TestParams, _gp: GlobalParams,
                 usdc_prices: pd.Series | None = None):
        super().__init__(_utils, _params, _gp)

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
        self.out_of_range_count: int = 0
        # self.total_pause_minutes: int = 0
        self.last_rescale_side: int = 0  # 1 all base, -1 all quote, 0 initial
        self.invest_token0: Decimal = ZERO
        self.invest_token1: Decimal = ZERO
        self.idle_base: Decimal = ZERO
        self.idle_quote: Decimal = ZERO
        self.leftover_base: Decimal = ZERO
        self.leftover_quote: Decimal = ZERO
        self.out_of_fund_date: datetime | None = None
        self.rescale_range: tuple[Decimal, Decimal] = (ZERO, ZERO)
        self.removed_base_fee = ZERO
        self.removed_quote_fee = ZERO
        self.is_lp_removed = False


    def initialize(self):

        new_trigger = AtTimeTrigger(time=self.params.cal_start_datetime, do=self.first_lp)
        self.triggers.append(new_trigger)

        market_data = self.data[self.utils.market_key]

        # print(market_data.keys()) ==>
        # Index(['netAmount0', 'netAmount1', 'closeTick', 'openTick', 'lowestTick',
        #        'highestTick', 'inAmount0', 'inAmount1', 'currentLiquidity', 'open',
        #        'price', 'low', 'high', 'volume0', 'volume1'],
        #       dtype='object')

        if self.usdc_prices is not None:
            self.add_column(self.utils.market_key, "usdc_price", self.usdc_prices)

        # match self.params.rescale_frequency:
        #     case RescaleFrequency.minute5:
        #         self.triggers.append(PeriodTrigger(time_delta=timedelta(minutes=5), do=self.rescale_work))
        #     case RescaleFrequency.minute15:
        #         self.triggers.append(PeriodTrigger(time_delta=timedelta(minutes=15), do=self.rescale_work))
        #     case RescaleFrequency.minute30:
        #         self.triggers.append(PeriodTrigger(time_delta=timedelta(minutes=30), do=self.rescale_work))
        #     case RescaleFrequency.hourly:
        #         self.triggers.append(PeriodTrigger(time_delta=timedelta(hours=1), do=self.rescale_work))
        #
        #     case RescaleFrequency.daily:
        #         self.triggers.append(PeriodTrigger(time_delta=timedelta(days=1), do=self.rescale_work))

        self.triggers.append(PeriodTrigger(time_delta=self.params.rescale_frequency.value, do=self.rescale_work))
        dt = datetime(self.params.data_end_date.year, self.params.data_end_date.month, self.params.data_end_date.day,
                      23, 59, 0)
        end_trigger = AtTimeTrigger(time=dt, do=self.calculate_final_result)
        self.triggers.append(end_trigger)

        self.total_invested = self.broker.get_token_balance(self.broker.quote_token)
        pass




    def calculate_range(self, lp_market: UniLpMarketV2, current_price: Decimal) -> tuple[Decimal, Decimal, int, int]:
        percent = Decimal(self.utils.params.init_tick_spread) / HUNDRED / Decimal(2)
        price_dif = current_price * percent
        upper_price, lower_price = current_price + price_dif, current_price - price_dif
        lower_tick = lp_market.price_to_raw_tick(lower_price)
        upper_tick = lp_market.price_to_raw_tick(upper_price)

        if lower_tick > upper_tick:
            lower_tick, upper_tick = upper_tick, lower_tick

        # print(f"before rounding tick {lower_tick}, {upper_tick}")
        lower_tick, upper_tick = self.round_to_tick_space(lower_tick, upper_tick)
        # print(f"after rounding tick {lower_tick}, {upper_tick}")
        return lower_price, upper_price, lower_tick, upper_tick

    def check_rebalance(self, lp_market: UniLpMarketV2, current_price: Decimal) -> tuple[bool, Decimal, Decimal, int, int]:
        # token0, token1 = lp_market.get_position_amount(self.utils.current_position_info)
        # rebalance = False
        # if lp_market.pool_info.is_token0_quote:
        #     rebalance = self.is_base_zero(token1) or self.is_quote_zero(token0)
        # else:
        #     rebalance = self.is_base_zero(token0) or self.is_quote_zero(token1)
        #
        # if rebalance:
        #     lower_price, upper_price, lower_tick, upper_tick = self.calculate_range(lp_market, current_price)
        #     return True, lower_price, upper_price, lower_tick, upper_tick
        # else:
        #     return False, ZERO, ZERO, ZERO, ZERO
        if current_price < self.rescale_range[0] or current_price > self.rescale_range[1]:

            lower_price, upper_price, lower_tick, upper_tick = self.calculate_range(lp_market, current_price)
            return True, lower_price, upper_price, lower_tick, upper_tick
        else:
            return False, ZERO, ZERO, 0, 0


    def get_balance_base_quote_amounts(self) -> tuple[Decimal, Decimal]:
        base = self.broker.get_token_balance(self.gp.base_token)
        quote = self.broker.get_token_balance(self.gp.quote_token)

        return base, quote

    def rescale_work(self, row_data: Snapshot):

        # if row_data.timestamp.hour == 0 and row_data.timestamp.minute == 0:
        #     self.lock_until_time = None

        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]

        if self.out_of_fund_date is not None:
            return

        current_price = lp_market.market_status.data.price
        try:
            allow_rescale, _, _, new_tick_lower, new_tick_upper = self.check_rebalance(lp_market, current_price)

            # Check if rescaling is allowed
            if not allow_rescale and not self.is_lp_removed:
                # print("current condition not allow rescale: " + row_data.timestamp.strftime("%Y-%m-%d %H:%M:%S"))
                return

            tick_spacing, current_tick, _, _ = self.utils.get_tick_info(row_data)

            if not allow_rescale and self.is_lp_removed:
                # If we are here, it means is_lp_removed is True, so we need to add liquidity back.
                # But allow_rescale is False, so check_rebalance didn't calculate new ticks.
                # We should use the calculate_range to get valid ticks based on current price.
                _, _, new_tick_lower, new_tick_upper = self.calculate_range(lp_market, current_price)
                if new_tick_lower == new_tick_upper:
                     # fallback to old position ticks if current calculation fails to create a range
                     new_tick_lower, new_tick_upper = old_position_info[0], old_position_info[1]
            old_position_info = self.utils.current_position_info

            if not self.is_lp_removed:
                if ((new_tick_lower == old_position_info[0] and new_tick_upper == old_position_info[1])
                        or new_tick_lower >= new_tick_upper):
                    print(f"same tick, do not rescale: {new_tick_lower}, {new_tick_upper}")
                    return

                if old_position_info[0] > current_tick:
                    self.upper_rescale_count += 1
                else:
                    self.lower_rescale_count += 1

                if current_tick < old_position_info[0] or current_tick > old_position_info[1]:
                    self.out_of_range_count += 1

                base_fee, quote_fee = lp_market.collect_fee(self.utils.current_position_info, collect_to_user=True)

                try:
                    base_removed, quote_removed = lp_market.remove_liquidity(self.utils.current_position_info, collect=True)
                except Exception as e:
                    print(f"{row_data.timestamp.strftime("%Y-%m-%d %H:%M")} => failed to remove liquidity: {self.utils.current_position_info}")
                    print(f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} => current tick: {current_tick}, positions: {lp_market.positions}")
                    raise e

                self.total_base_fee += base_fee
                self.total_quote_fee += quote_fee
            else:
                # was already removed, record fees earned if any (though should be zero if removed)
                base_fee, quote_fee = self.removed_base_fee, self.removed_quote_fee
                self.total_base_fee += base_fee
                self.total_quote_fee += quote_fee
                self.removed_base_fee = ZERO
                self.removed_quote_fee = ZERO
                self.is_lp_removed = False
                base_removed, quote_removed = ZERO, ZERO

            rebalance_base_fee, rebalance_quote_fee = ZERO, ZERO

            try:
                to_swap_base = lp_market.broker.get_token_balance(self.gp.base_token) - self.total_base_fee
                to_swap_quote = lp_market.broker.get_token_balance(self.gp.quote_token) - self.total_quote_fee

                base_to_swap, quote_to_swap = self.calculate_swap_amount(current_tick, new_tick_lower, new_tick_upper, to_swap_base, to_swap_quote)
                swapped_base, swapped_quote, base_used_fee, quote_used_fee = self.execute_swap(lp_market, base_to_swap, quote_to_swap)

                self.total_base_swap_fee += base_used_fee if base_used_fee is not None else ZERO
                self.total_quote_swap_fee += quote_used_fee if quote_used_fee is not None else ZERO

                base = lp_market.broker.get_token_balance(self.gp.base_token) - self.total_base_fee
                quote = lp_market.broker.get_token_balance(self.gp.quote_token) - self.total_quote_fee

                self.utils.current_position_info, base_used, quote_used, _ = lp_market.add_liquidity_by_tick(
                    new_tick_lower, new_tick_upper, base, quote, tick=current_tick)

                left_base = lp_market.broker.get_token_balance(self.gp.base_token) - self.total_base_fee
                left_quote = lp_market.broker.get_token_balance(self.gp.quote_token) - self.total_quote_fee

                # update next rescale price
                lower_price = lp_market.tick_to_price(new_tick_lower)
                diff = abs(lower_price - current_price) / Decimal(2)
                self.rescale_range = (current_price - diff, current_price + diff)
                # print(
                #     f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} orig base: {to_swap_base}, orig quote: {to_swap_quote},"
                #     f" swapped_base: {swapped_base}, swapped_quote: {swapped_quote}, final balance base: {base}, quote: {quote}, base_used: {base_used}, quote_used: {quote_used}, left_base: {left_base}, left_quote: {left_quote},"
                #     f" current price: {current_price}, rescale range: {self.rescale_range}, current_tick: {current_tick}, new_tick_lower: {new_tick_lower}, new_tick_upper: {new_tick_upper}")
                # lock until today is over
                # self.lock_until_time = datetime(row_data.timestamp.year, row_data.timestamp.month,
                #                                 row_data.timestamp.day, 23, 59, 0)

                    # print(f"add LP => new position info ({current_tick}): { self.utils.current_position_info}, base: {base_used}, quote: {quote_used}, base_leftover: {base_leftover}, quote_leftover: {quote_leftover} ")
            except Exception as e:
                if new_tick_upper == new_tick_lower:
                    print(f"ERROR: new_tick_upper and new_tick_lower are both {new_tick_upper}. current_price: {current_price}, allow_rescale: {allow_rescale}, is_lp_removed: {self.is_lp_removed}")
                print(
                    f"failed to add liquidity, current tick: {current_tick}, upper: {new_tick_upper}, lower: {new_tick_lower}")
                raise e

            _, current_tick, _, _ = self.utils.get_tick_info(row_data)

            if base_used == ZERO and quote_used == ZERO:
                self.out_of_fund_date = row_data.timestamp
                print(
                    f"\nno position place ({row_data.timestamp.strftime("%Y-%m-%d %H:%M:%S")}): {self.utils.current_position_info}, old_position_info: {old_position_info}, "
                    f"current_tick: {current_tick}, new_tick_lower: {new_tick_lower}, new_tick_upper: {new_tick_upper}, "
                    f"positions: {lp_market.positions}, base: {base}, quote: {quote}, "
                    f"rebalance_base_fee: {rebalance_base_fee}, rebalance_quote_fee: {rebalance_quote_fee}, balance_data: {self.balance_data}")

            ed = ExportData()
            ed.time = row_data.timestamp
            ed.price = current_price
            ed.tick = current_tick

            ed.tick_lower, ed.tick_upper = old_position_info[0], old_position_info[1]

            pos = lp_market.positions[self.utils.current_position_info]
            ed.price_lower, ed.price_upper = pos.lower_price, pos.upper_price

            # param_changed = False
            # current_param_type = "bull" if self.utils.bull else "bear"

            # if not self.params.to_swap and self.params.range_strategy == RangeStrategy.remix_dao:
            #     bull: bool | None = None
            #     if current_tick > new_tick_upper: # range is under price
            #         new_upper_price = pos.upper_price
            #         self.ps_lower, bull = self.price_trend_check(current_price, new_upper_price, self.pa_lower)
            #         if bull is not None and len(self.pa_lower) >= 3:
            #             if self.utils.bull == bull: # same price trend as param
            #                 # trim self.ps_lower to the last price action
            #                 self.ps_lower = [self.pa_lower[-1]]
            #             else: # change param
            #                 param_changed = True
            #                 if bull:
            #                     self.utils.use_bull_params()
            #                 else:
            #                     self.utils.use_bear_params()
            #     else:
            #         new_lower_price = pos.lower_price
            #         self.ps_upper, bull = self.price_trend_check(current_price, new_lower_price, self.pa_upper)
            #         if bull is not None and len(self.ps_upper) >= 3:
            #             if self.utils.bull == bull: # same price trend as param
            #                 # trim self.ps_upper to the last price action
            #                 self.ps_upper = [self.ps_upper[-1]]
            #             else: # change param
            #                 param_changed = True
            #                 if bull:
            #                     self.utils.use_bull_params()
            #                 else:
            #                     self.utils.use_bear_params()
            #     if param_changed:
            #         self.pa_lower = []
            #         self.pa_upper = []
            #     pass

            ed.new_tick_lower, ed.new_tick_upper = self.utils.current_position_info[0], \
                self.utils.current_position_info[1]

            ed.base_fee, ed.quote_fee = base_fee, quote_fee
            ed.base_removed, ed.quote_removed = base_removed, quote_removed
            ed.base_added, ed.quote_added = base_used, quote_used
            ed.was_in_range = self.was_in_range
            ed.total_base_fee, ed.total_quote_fee = self.total_base_fee + self.removed_base_fee, self.total_quote_fee + self.removed_quote_fee
            ed.is_lp_removed = self.is_lp_removed

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
                ed.indicator_value = new_tick_upper - new_tick_lower

            ed.param_type = "bull" if self.utils.bull else "bear"

            self.export_actions.append(ed)

            pos_info = self.utils.current_position_info
            tick_spread = pos_info[1] - pos_info[0]
            self.tick_spreads.loc[len(self.tick_spreads)] = tick_spread

            # print(
            #     f"rescaled at {row_data.timestamp.strftime("%Y-%m-%d %H:%M:%S")}, removed: {base} / {quote}, fee: {base_fee} / {quote_fee}, used: {base_used} / {quote_used}, "
            #     f"tick: {current_tick}, old_position_info: {old_position_info}, position_info: {str(self.utils.current_position_info)}, was_in_range: {self.was_in_range}, price: {current_price}")

            self.last_rescale_tick = current_tick
            self.was_in_range = False

        finally:
            self.last_price = current_price
        pass

    def first_lp(self, row_data: Snapshot):

        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]
        # lp_row_data = row_data.market_status[self.utils.market_key]

        if len(lp_market.positions) > 0:
            raise RuntimeError("shouldn't have any position")

        quote_usdc_price = self.init_quote_usd_price = self.get_quote_usdc_price(row_data)
        quote_amount = self.gp.init_quote  # self.gp.init_quote_usdc / quote_usdc_price

        lp_market.broker.add_to_balance(self.gp.quote_token, quote_amount)
        self.total_invested += quote_amount
        # self.total_invested_usdc += self.gp.init_quote_usdc * quote_usdc_price
        self.total_invested_usdc += self.gp.init_quote * quote_usdc_price

        tick_spacing, current_tick, _, _ = self.utils.get_tick_info(row_data)
        _lower_price = _upper_price = None
        current_price = lp_market.market_status.data.price
        # if not self.params.initial_swap:
        if self.params.initial_type == 0:  # all quote

            if self.gp.token0 == self.gp.quote_token:
                current_tick_lower = current_tick + tick_spacing
            else:
                current_tick_lower = current_tick - tick_spacing

            lower, upper = self.utils.calculate_one_tick_spacing_rescale_tick_boundary(current_tick,
                                                                                       current_tick_lower)
        elif self.params.initial_type == -1:  # all base

            lp_market.swap(from_token=self.gp.quote_token, to_token=self.gp.base_token, from_amount=quote_amount)
            if self.gp.token0 == self.gp.base_token:
                current_tick_lower = current_tick + tick_spacing
            else:
                current_tick_lower = current_tick - tick_spacing

            lower, upper = self.utils.calculate_one_tick_spacing_rescale_tick_boundary(current_tick,
                                                                                       current_tick_lower)
            pass
        else:

            # need to know how to place initial position

            (_lower_price, _upper_price, lower, upper) = self.calculate_range(lp_market, current_price)

            to_swap_base, to_swap_quote = self.get_balance_base_quote_amounts()
            # _, _, base_fee, quote_fee = self.even_rebalance(lp_market)
            base_to_swap, quote_to_swap = self.calculate_swap_amount(current_tick, lower, upper,
                                                                     to_swap_base, to_swap_quote)
            swapped_base, swapped_quote, base_fee, quote_fee = self.execute_swap(lp_market, base_to_swap,
                                                                                           quote_to_swap)


            final_base = lp_market.broker.get_token_balance(self.gp.base_token)
            final_quote = lp_market.broker.get_token_balance(self.gp.quote_token)
            self.total_base_swap_fee += base_fee if base_fee is not None else ZERO
            self.total_quote_swap_fee += quote_fee if quote_fee is not None else ZERO

        self.utils.current_position_info, base_used, quote_used, _ = lp_market.add_liquidity_by_tick(lower, upper, final_base, final_quote, tick=current_tick) # tick=current_tick
        left_base = lp_market.broker.get_token_balance(self.gp.base_token)
        left_quote = lp_market.broker.get_token_balance(self.gp.quote_token)

        print(f"initial swap: {final_base} / {final_quote}, fee: {base_fee} / {quote_fee}")
        print(
            f"{row_data.timestamp.strftime('%Y-%m-%d %H:%M')} first_lp final base: {final_base}, quote: {final_quote}, "
            f"base_used: {base_used}, quote_used: {quote_used}, left_base: {left_base}, left_quote: {left_quote}")
        print(
            f"\nadding first liquidity, price: {str(current_price)}, range: {str(lower)} ~ {str(upper)}, price: {_lower_price} ~ {_upper_price}, current tick: {current_tick}")

        self.was_in_range = True
        self.last_price = self.last_dca_price = self.last_check_price = current_price

        pass

    def calculate_final_result(self, row_data: Snapshot):

        lp_market: UniLpMarket = self.broker.markets[self.utils.market_key]
        _, current_tick, _, _ = self.utils.get_tick_info(row_data)
        current_price = lp_market.market_status.data.price
        ed = ExportData()
        ed.time = row_data.timestamp
        ed.price = current_price
        ed.tick = current_tick

        position_info = self.utils.current_position_info
        ed.tick_lower, ed.tick_upper = position_info[0], position_info[1]
        base_fee, quote_fee = ZERO, ZERO
        pos = lp_market.positions.get(position_info, None)
        if pos is None:
            ed.price_lower, ed.price_upper = None, None
        else:
            ed.price_lower, ed.price_upper = pos.lower_price, pos.upper_price
            base_fee, quote_fee = lp_market.collect_fee(self.utils.current_position_info, collect_to_user=True)

        ed.new_tick_lower, ed.new_tick_upper = position_info[0], position_info[1]


        self.total_base_fee += base_fee + self.removed_base_fee
        self.total_quote_fee += quote_fee + self.removed_quote_fee
        self.removed_base_fee = ZERO
        self.removed_quote_fee = ZERO

        ed.base_fee, ed.quote_fee = base_fee, quote_fee
        ed.base_removed, ed.quote_removed = None, None
        ed.base_added, ed.quote_added = None, None
        ed.was_in_range = self.was_in_range
        ed.total_base_fee, ed.total_quote_fee = self.total_base_fee, self.total_quote_fee
        ed.is_lp_removed = self.is_lp_removed

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
        pos_info = self.utils.current_position_info
        if pos_info is None:
            return

        lp_market: UniLpMarketV2 = self.broker.markets[self.utils.market_key]
        current_price = lp_market.market_status.data.price

        if self.out_of_fund_date is None and not self.is_lp_removed and (current_price < self.rescale_range[0] or current_price > self.rescale_range[1]):
            # remove liquidity
            base_fee, quote_fee = lp_market.collect_fee(self.utils.current_position_info, collect_to_user=True)
            self.removed_base_fee += base_fee
            self.removed_quote_fee += quote_fee

            lp_market.remove_liquidity(self.utils.current_position_info, collect=True)
            self.is_lp_removed = True
            self.out_of_range_count += 1

            # logging removal
            ed = ExportData()
            ed.time = row_data.timestamp
            ed.price = current_price
            _, current_tick, _, _ = self.utils.get_tick_info(row_data)
            ed.tick = current_tick
            ed.tick_lower, ed.tick_upper = pos_info[0], pos_info[1]
            ed.base_fee, ed.quote_fee = base_fee, quote_fee
            ed.total_base_fee, ed.total_quote_fee = self.total_base_fee + self.removed_base_fee, self.total_quote_fee + self.removed_quote_fee
            ed.is_lp_removed = self.is_lp_removed
            ed.lp_net_value = lp_market.get_market_balance().net_value
            ed.quote_balance = lp_market.broker.get_token_balance(self.gp.quote_token)
            ed.base_balance = lp_market.broker.get_token_balance(self.gp.base_token)
            ed.total_net_value = ed.lp_net_value + ed.quote_balance + (ed.base_balance * ed.price)
            ed.total_net_value_base = ed.total_net_value / ed.price
            ed.param_type = "bull" if self.utils.bull else "bear"
            self.export_actions.append(ed)

        lp_row_data = row_data.market_status[self.utils.market_key]
        in_lock = self.is_in_lock(row_data)

        in_range = self.out_of_fund_date is None and not self.is_lp_removed and (
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
             processed_data: pd.DataFrame | None, usdc_price_data: pd.DataFrame | None = None) -> Dict[str, Decimal]:
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
        strat = RemixDaoDcaWeekStratStrategy(utils, params, gp, usdc_prices=usdc_prices)
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
        metrics["out_of_range_count"] = Decimal(strat.out_of_range_count)

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
        print(f"error for {params.range_strategy.value}, {str(bull_params)}, {str(bear_params)}")
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

    # base_token, quote_token, init_quote = eth, usdc, Decimal(1000000)  #  USDC

    base_token, quote_token, init_quote = eth, usdc, Decimal(100000)  # DCA USDC

    # base_token, quote_token, init_quote = btc, eth, Decimal(1)  # ETH
    # base_token, quote_token, init_quote = eth, btc, Decimal(1)  # BTC
    # base_token, quote_token, init_quote = cbbtc, btc, Decimal(1)  # BTC/cbBTC
    # base_token, quote_token, init_quote = usdt, usdc, Decimal(2000)  # USDC/USDT
    # base_token, quote_token, init_quote = wstEth, eth, Decimal(100)  # wstETH/ETH
    # base_token, quote_token, init_quote = dai, usdt, Decimal(2000)  # dai/usdt

    # token0, token1 = usdc, usdt
    # contract_address, fee, chain_name = "0x3416cF6C708Da44DB2624D63ea0AAef7113527C6", 0.01, ChainType.ethereum.name  # usdc/usdt  2021-11-20
    # token0, token1 = btc, cbbtc
    # contract_address, fee, chain_name = "0xe8f7c89C5eFa061e340f2d2F206EC78FD8f7e124", 0.01, ChainType.ethereum.name  # wbtc/cbbtc  2021-09-20
    # token0, token1 = wstEth, eth
    # contract_address, fee, chain_name = "0x109830a1AAaD605BbF02a9dFA7B0B92EC2FB7dAa", 0.01, ChainType.ethereum.name  # wstEth/eth  2022-08-25
    # token0, token1 = dai, usdt
    # contract_address, fee, chain_name = "0x48DA0965ab2d2cbf1C17C09cFB5Cbe67Ad5B1406", 0.01, ChainType.ethereum.name  # dai/usdt  2022-07-20

    # token0, token1 = btc, eth
    # contract_address, fee, chain_name, load_eth_price = "0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0", 0.05, ChainType.ethereum.name, True # wbtc/weth  2021-05-13
    # contract_address, fee, chain_name = "0x2f5e87C9312fa29aed5c179E456625D79015299c", 0.05, ChainType.arbitrum.name # wbtc/weth
    # contract_address, fee, chain_name = "0xCBCdF9626bC03E24f779434178A73a0B4bad62eD", 0.3, ChainType.ethereum.name # wbtc/weth

    ## negative tick: token0 is worthless than token1

    token0, token1 = usdc, eth
    contract_address, fee, chain_name = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", 0.05, ChainType.ethereum.name  # weth/usdc
    # token0, token1 = eth, usdc
    # contract_address, fee, chain_name = "0xC6962004f452bE9203591991D15f6b388e09E8D0", 0.05, ChainType.arbitrum.name  # weth/usdc
    _init_quote_usdc = init_quote * INIT_PRICE
    _dca_usdc_amount = Decimal(10000)

    # pool = UniV3Pool(btc, eth, _fee, _quote_token)
    _starting_mark_price = Decimal(0)
    _is_stable = False
    _tick_spacing = 1 if _is_stable else int(fee * 200)  # 10  # should simply be fee * 200
    _aggressive = True
    _compound = False
    _folder_prefix = f"ISAO-percentage-Dv2-{token0.name.lower()}{token1.name.lower()}-{"aggressive" if _aggressive else "conservative"}-{quote_token.name.lower()}"
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


    l: List[int] = [
        3, 5, 10, 15, 20, 30, 40 # 用來當range percent, 是total range percent，單邊要除以2
    ]

    _remix_spreads = list(map(lambda i: RescaleParam(init_tick_spread=i, bull_lower_spread=i, bull_upper_spread=i,
                                                     bear_lower_spread=i, bear_upper_spread=i, ), l))

    # _rescale_frequencies = [RescaleFrequency.minute5, RescaleFrequency.minute15, RescaleFrequency.minute30, RescaleFrequency.hourly]  # RescaleFrequency.hourly,
    _rescale_frequencies = [RescaleFrequency.hourly, RescaleFrequency.hour4, RescaleFrequency.hour8,
                            RescaleFrequency.hour12, RescaleFrequency.daily] #RescaleFrequency.hourly,
    # _rescale_frequencies = [RescaleFrequency.minute5, RescaleFrequency.minute15, ]
    # _rescale_frequencies = [RescaleFrequency.hourly]

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
    parameters: List[Tuple[RemixDAOParams, RemixDAOParams, TestParams]] = []

    for rescale_frequency in _rescale_frequencies:
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
                                          # report_name=f"{"agg" if _aggressive else "cons"}-{init_quote}{quote_token.name}_{RangeStrategy.remix_dao.name}_no_offset_{bull_no_offset.init_tick_spread}_{bull_no_offset.tick_spread_lower}-{bull_no_offset.tick_spread_upper}_{bear_no_offset.tick_spread_lower}-{bear_no_offset.tick_spread_upper}_{rescale_frequency.name}-{gp.dca_add_if_non_empty}",
                                          report_name=f"{"agg" if _aggressive else "cons"}-{init_quote}{quote_token.name}_{RangeStrategy.remix_dao.name}_no_offset_{bear_no_offset.init_tick_spread}_{rescale_frequency}",
                                          indicator_length_hr=1, to_swap=False,
                                          aggressive=_aggressive, compound=_compound,
                                          rescale_frequency=rescale_frequency,
                                          cal_start_datetime=csd, data_start_date=dsd, data_end_date=ded, folder=folder,
                                          initial_swap=spread.initial_swap(), flip_param_dates=flip_param_dates,
                                          start_with_bull_param=start_with_bull_param,
                                          initial_type=_init_type,
                                          starting_mark_price=_starting_mark_price,)
                               ))
            # parameters.append((no_offset,
            #                    TestParams(range_strategy=RangeStrategy.remix_dao, indicator_mult=1,
            #                               report_name=f"{"agg" if _aggressive else "cons"}-{init_quote}{quote_token.name}_{RangeStrategy.remix_dao.name}_rebalance_{no_offset.init_tick_spread}_{no_offset.tick_spread_lower}_{no_offset.tick_spread_upper}_{rescale_frequency.name}{_cmp}",
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

    usdc_price_data = None
    if load_eth_price:
        contract_address_usdc = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
        market_key_usdc = MarketInfo("usdc")
        pool_usdc = UniV3Pool(usdc, eth, fee, usdc)
        market_usdc = UniLpMarket(market_key_usdc, pool_usdc)
        market_usdc.data_path = f"../real-data/{contract_address_usdc}"
        market_usdc.load_data(chain_name, contract_address_usdc, dsd, ded)
        usdc_price_data = market_usdc.data
    else:
        # create a pd.DataFrame with column "price" of 1 for every minute from dsd to ded
        index = pd.date_range(start=dsd, end=datetime.combine(ded, datetime.max.time()), freq="min")
        usdc_price_data = pd.DataFrame(index=index, data={"price": ONE})

    # result = list(map(lambda p: (p[2].report_name, run_test(p[0], p[1], p[2], gp, market.data, market_usdc.data)), parameters))
    result = list(
        map(lambda p: (p[2].report_name, run_test(p[0], p[1], p[2], gp, market.data, usdc_price_data)), parameters))
    export_stable_apr_results(f"{folder}/apr_remix_{init_quote}_results.csv", result)
    pass


if __name__ == "__main__":

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
        #  2023/01/01~2023/12/31
        (datetime(2023, 1, 1, 0, 0, 0), date(2023, 1, 1), date(2023, 12, 31), "", []),
        #  2024/01/01~2024/09/30
        (datetime(2024, 1, 1, 0, 0, 0), date(2024, 1, 1), date(2024, 12, 31), "", []),
        (datetime(2025, 1, 1, 0, 0, 0), date(2025, 1, 1), date(2025, 12, 31), "", []),
        (datetime(2022, 1, 1, 0, 0, 0), date(2022, 1, 1), date(2025, 12, 31), "", []),


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
