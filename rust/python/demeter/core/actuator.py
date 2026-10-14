"""
Actuator backed by the Rust engine.

The backtest loop runs in Rust (``demeter._rs.ActuatorCore``); it calls back into the python strategy
only for the hooks it overrides and for python-defined triggers. Built-in triggers (AtTimeTrigger,
PeriodTrigger, ...) are evaluated natively. Public API is the same as the original python Actuator.
"""

import logging
import os
import pickle
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Tuple, Union

import pandas as pd

from .. import Broker, Asset, ActionTypeEnum, _rs
from .._bridge import account_status_from_ipc, interval_to_seconds, pandas_to_ipc
from .._typing import DemeterError, UnitDecimal, DemeterWarning, TokenInfo, USD, DemeterLog
from ..broker import BaseAction, AccountStatus, MarketInfo, MarketDict, MarketTypeEnum
from ..broker._typing import BrokerSwapAction
from ..broker.broker import account_status_from_row
from ..result import BackTestDescription
from ..strategy import Strategy
from ..strategy.trigger import NATIVE_TRIGGER_TYPES
from ..uniswap import PositionInfo
from ..uniswap._typing import AddLiquidityAction, RemoveLiquidityAction, CollectFeeAction, SwapAction, BuyAction, SellAction
import warnings

from ..uniswap.market import overridden_engine_methods
from ..utils import get_formatted_predefined, STYLE, to_decimal, console_text, config_log

config_log()

BASIC_INTERVAL = pd.Timedelta("1min")

_ACTION_CLASSES = {
    "uni_lp_add_liquidity": AddLiquidityAction,
    "uni_lp_remove_liquidity": RemoveLiquidityAction,
    "uni_lp_collect": CollectFeeAction,
    "uni_lp_swap": SwapAction,
    "uni_lp_buy": BuyAction,
    "uni_lp_sell": SellAction,
    "general_swap": BrokerSwapAction,
}


def make_action(d: dict) -> BaseAction:
    """Build the python action dataclass from the engine's action record."""
    market = MarketInfo(d["market_name"], MarketTypeEnum(d["market_type"]))
    kwargs = {}
    for k, v in d["fields"].items():
        if isinstance(v, tuple) and len(v) == 2 and isinstance(v[1], str):
            kwargs[k] = UnitDecimal(v[0], v[1])
        elif k == "position":
            kwargs[k] = PositionInfo(*v)
        elif k in ("from_token", "to_token"):
            kwargs[k] = TokenInfo(v, 0)
        else:
            kwargs[k] = v
    action = _ACTION_CLASSES[d["type"]](market=market, **kwargs)
    action.set_type()
    action.timestamp = d["timestamp"]
    action.comment = d["comment"]
    return action


@dataclass
class RunningCount:
    get_account_status_df: int = 0


class _AccountStatusList(Sequence):
    """``actuator.account_status``: live list of AccountStatus built on access."""

    def __init__(self, actuator: "Actuator"):
        self._a = actuator

    def __len__(self):
        return self._a._core.account_status_len()

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [self[j] for j in range(*i.indices(len(self)))]
        n = len(self)
        if i < 0:
            i += n
        if not 0 <= i < n:
            raise IndexError(i)
        return account_status_from_row(self._a._core.account_status_row(i), self._a.broker)


class _ActionList(Sequence):
    """``actuator.actions`` / ``strategy.actions``: live list of actions."""

    def __init__(self, actuator: "Actuator"):
        self._a = actuator
        self._cache: List[BaseAction] = []

    def _sync(self):
        n = self._a._core.actions_len()
        if len(self._cache) != n:
            if len(self._cache) > n:
                self._cache = []
            self._cache.extend(make_action(d) for d in self._a._core.actions(len(self._cache)))
        return self._cache

    def __len__(self):
        return self._a._core.actions_len()

    def __getitem__(self, i):
        return self._sync()[i]

    def __iter__(self):
        return iter(self._sync())


class _LazyAccountFrame:
    """Given to strategies as ``account_status_df``; becomes the real DataFrame on first use."""

    def __init__(self, actuator: "Actuator"):
        self._a = actuator

    def _df(self):
        return self._a.account_status_df

    def __getattr__(self, item):
        return getattr(self._df(), item)

    def __getitem__(self, item):
        return self._df()[item]

    def __len__(self):
        return len(self._df())

    def __iter__(self):
        return iter(self._df())

    def __repr__(self):
        return repr(self._df())


class Actuator(object):
    """
    Core component of a back test. Manage the resources in a test, including broker/strategy/data/indicator,

    :param allow_negative_balance: Allow cash balance of broker can be negative value or not. Default is False
    :type allow_negative_balance: bool
    """

    def __init__(self, allow_negative_balance=False):
        self._core = _rs.ActuatorCore(allow_negative_balance)
        self._broker: Broker = Broker(allow_negative_balance, _core=self._core.broker())
        self._strategy: Strategy = Strategy()
        self._token_prices: pd.DataFrame | None = None
        self._logs: List[DemeterLog] = []
        self._account_status_df: pd.DataFrame | None = None
        self._actions = _ActionList(self)
        self.logger = logging.getLogger("Actuator")
        self.__start_time = None
        self.__backtest_duration = None
        self.__backtest_finished = False
        self.__runnning_count: RunningCount = RunningCount()
        self.print_action = False
        self.init_account_status = None
        # set backtest with other freq to make it faster, freq should be larger than 1 minute
        self.interval: str = "1min"

    # region property
    @property
    def legacy_quirks(self) -> bool:
        """
        True (default): reproduce the python engine's behaviour exactly, including its quirks.
        False: corrected behaviour. See rust/README.md, "Python engine quirks".
        """
        return self._core.legacy_quirks

    @legacy_quirks.setter
    def legacy_quirks(self, value: bool):
        self._core.legacy_quirks = bool(value)

    @property
    def account_status(self) -> Sequence:
        return _AccountStatusList(self)

    @property
    def token_prices(self) -> pd.DataFrame:
        return self._token_prices

    @property
    def final_status(self) -> AccountStatus:
        if self.__backtest_finished:
            return self.account_status[-1]
        else:
            raise DemeterError("please run strategy first")

    def reset(self):
        self._account_status_df = None
        self.__backtest_finished = False

    @property
    def actions(self) -> Sequence:
        return self._actions

    @property
    def _action_list(self) -> List[BaseAction]:
        """python-engine private name of `actions`"""
        return list(self._actions)

    @property
    def _account_status_list(self) -> Sequence:
        """python-engine private name of `account_status`"""
        return self.account_status

    @property
    def broker(self) -> Broker:
        return self._broker

    @property
    def strategy(self) -> Strategy:
        return self._strategy

    @strategy.setter
    def strategy(self, value):
        if isinstance(value, Strategy):
            self._strategy = value
        else:
            raise ValueError()

    @property
    def account_status_df(self) -> pd.DataFrame:
        """
        Account status of every minute: net value, token balances, market balances, prices.
        Columns are a (l1, l2) MultiIndex, e.g. ``df["net_value"]``, ``df["price"]["ETH"]``.
        """
        if not self.__backtest_finished:
            if self.__runnning_count.get_account_status_df >= 10:
                raise DemeterWarning(
                    "Frequent calls to account_status_df will generate multiple DataFrame objects, "
                    "consuming a lot of time and memory. Consider using account_status instead."
                )
            self.__runnning_count.get_account_status_df += 1
            if self._core.account_status_len() == 0:
                return pd.DataFrame()
            return account_status_from_ipc(self._core.account_status_ipc())
        if self._account_status_df is None:
            self._account_status_df = account_status_from_ipc(self._core.account_status_ipc())
        return self._account_status_df

    @account_status_df.setter
    def account_status_df(self, new_df: pd.DataFrame):
        if not self.__backtest_finished:
            raise DemeterError("Back test has not finish yet, can not write account_status_df")
        self._account_status_df = new_df
        self._strategy.account_status_df = new_df

    # endregion

    def comment_last_action(self, message: str, action_type: ActionTypeEnum | None = None):
        self._core.comment_last_action(message, action_type.name if action_type is not None else None)
        self._actions._cache = []

    def set_assets(self, assets: List[Asset]):
        for asset in assets:
            self._broker.set_balance(asset.token_info, asset.balance)

    def set_price(self, prices: Union[pd.DataFrame, pd.Series, Tuple[pd.DataFrame, TokenInfo]], quote_token: TokenInfo = None):
        """
        Set price to actuator: a dataframe (one column per token, upper case name), a series, or the
        (dataframe, quote token) tuple returned by ``market.get_price_from_data()``.
        """
        if isinstance(prices, pd.DataFrame):
            quote_token = quote_token if quote_token is not None else USD
        elif isinstance(prices, tuple):  # Got from uniswap market
            quote_token = prices[1]
            prices = prices[0]
        else:
            quote_token = quote_token if quote_token is not None else USD
            prices = pd.DataFrame(data=prices, index=prices.index)

        self._core.set_price_ipc(pandas_to_ipc(prices), quote_token.name, quote_token.decimal)

        prices = prices.map(lambda y: to_decimal(y))
        if self._token_prices is None:
            self._token_prices = prices
        else:
            self._token_prices = pd.concat([self._token_prices, prices])

        self.broker._quote_token = quote_token
        self.logger.info("quote token in backtest is {}".format(quote_token))
        if quote_token is USD or quote_token == USD:
            self._token_prices[USD.name] = 1

    def notify(self, strategy: Strategy, actions: List[BaseAction]):
        if len(actions) < 1:
            return
        for action in actions:
            strategy.notify(action)
            if self.print_action:
                print(action.get_output_str())

    def _log(self, timestamp: datetime, message: str, level: int = logging.INFO):
        self._logs.append(DemeterLog(timestamp, message, level))

    def get_test_range(self):
        longest = None
        for m in self._broker.markets.values():
            if longest is None or len(m.data) > len(longest):
                longest = m.data
        return longest.index

    def run(self, print_result: bool = True):
        """
        Start back test (the loop itself runs in Rust):

        * reset actuator
        * initialize strategy (set object to strategy, then run strategy.initialize())
        * process each row in data: triggers, on_bar, market update, after_bar, account status, notify
        * run strategy.finalize()
        * output result if required
        """
        self.__start_time = time.time()
        self.reset()
        self._actions._cache = []
        for market in self._broker.markets.values():
            names = overridden_engine_methods(market) if hasattr(market, "_core") else []
            if names:
                warnings.warn(
                    f"{type(market).__name__} overrides {', '.join(names)}: the Rust engine calls its native "
                    "version from the backtest loop and from other engine methods, so these overrides are "
                    "only used when your own code calls them directly.",
                    stacklevel=2,
                )
        self.__runnning_count = RunningCount()
        self._core.interval_secs = interval_to_seconds(self.interval)
        if interval_to_seconds(self.interval) < 60:
            raise DemeterError("interval should be larger than 1 minute")

        if self._token_prices is None:
            for market in self.broker.markets.values():
                if hasattr(market, "get_price_from_data"):
                    self.set_price(market.get_price_from_data())
                    break
            if self._token_prices is None:
                raise DemeterError("token prices is not set")

        self.logger.info(f"Quote token is {self.broker.quote_token}")
        self.logger.info("init strategy...")
        self.init_strategy()

        strategy = self._strategy
        base = Strategy
        hooks = {name: getattr(type(strategy), name) is not getattr(base, name) for name in ("before_bar", "on_bar", "after_bar", "notify")}
        markets = [(k, m._core) for k, m in self._broker.markets.items()]

        def on_finished():
            self.__backtest_finished = True
            init = self._core.init_account_status()
            self.init_account_status = account_status_from_row(init, self._broker) if init is not None else None
            self._account_status_df = None
            self._strategy.account_status_df = _LazyAccountFrame(self)

        self.logger.info("start main loop...")
        try:
            self._core.run(strategy, markets, list(NATIVE_TRIGGER_TYPES), hooks, make_action, on_finished, self.print_action)
        finally:
            for market in self._broker.markets.values():
                if hasattr(market, "_refresh_data_handle"):
                    market._refresh_data_handle()  # the engine may have resampled the data
        self.logger.info("main loop finished")
        if print_result:
            self.print_result()
        self.__backtest_duration = time.time() - self.__start_time
        self.logger.info(f"Backtest with process id: {os.getpid()} finished, execute time {(time.time() - self.__start_time):.3f}s")

    def _generate_account_status_df(self):
        self._account_status_df = account_status_from_ipc(self._core.account_status_ipc())
        self._strategy.account_status_df = self._account_status_df

    def print_result(self):
        if not self.__backtest_finished:
            raise DemeterError("Please run strategy first")
        self.logger.info(f"Print actuator summary")
        print("")
        print(get_formatted_predefined("Final account status", STYLE["header1"]))
        print("")
        print(self.broker.formatted_str())
        print(get_formatted_predefined(f"Quote by: {self.broker.quote_token}", STYLE["key"]))
        print("")
        print(get_formatted_predefined("Account balance history", STYLE["header1"]))
        print("")
        console_text.print_dataframe_with_precision(self.account_status_df)

    def save_result(self, path: str, file_name: str = None, decimals: int | None = None, file_format: str = "csv", **custom_attr) -> List[str]:
        """Save backtesting result (pkl of BackTestDescription + account status csv/pickle)."""
        file_name_head = file_name if file_name is not None else "backtest-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        if not os.path.exists(path):
            os.makedirs(path)
        file_list = []
        backtest_result = BackTestDescription(
            strategy_name=type(self._strategy).__name__,
            quote_token=self.broker.quote_token,
            init_status=self.init_account_status.asset_balances if self.init_account_status else None,
            assets=list(self.broker.assets.keys()),
            markets=[m.description for m in self.broker.markets.values()],
            actions=list(self.actions),
            backtest_start=datetime.fromtimestamp(self.__start_time),
            backtest_duration=self.__backtest_duration,
            backtest_end=datetime.now(),
            logs=self._logs,
        )
        for k, v in custom_attr.items():
            setattr(backtest_result, k, v)
        pkl_name = os.path.join(path, file_name_head + ".pkl")
        with open(pkl_name, "wb") as outfile1:
            pickle.dump(backtest_result, outfile1)
        file_list.append(pkl_name)

        if file_format == "csv":
            account_file_path = os.path.join(path, file_name_head + ".account.csv")
        elif file_format == "pickle":
            account_file_path = os.path.join(path, file_name_head + ".account.pkl")
        else:
            raise RuntimeError("File format should be csv or pickle")
        df_2_save: pd.DataFrame = self.account_status_df
        if decimals is not None:
            df_2_save = df_2_save.astype(float).round(decimals)
        if file_format == "csv":
            df_2_save.to_csv(account_file_path)
        else:
            df_2_save.to_pickle(account_file_path, compression="gzip")
        file_list.append(account_file_path)
        self.logger.info(f"files have saved to {','.join(file_list)}")
        return file_list

    def init_strategy(self):
        """set engine objects on the strategy (python `init_strategy`, without calling initialize)"""
        if not isinstance(self._strategy, Strategy):
            raise DemeterError("strategy must be inherit from Strategy")
        s = self._strategy
        s.broker = self._broker
        s.markets = self._broker.markets
        market_datas = MarketDict()
        for k, v in self.broker.markets.items():
            market_datas[k] = v.data
        market_datas.set_default_key(self.broker.markets.get_default_key())
        s.data = market_datas
        s.prices = self._token_prices
        s.account_status = self.account_status
        s.actions = self._actions
        s.assets = self.broker.assets
        s.account_status_df = pd.DataFrame()
        s.actuator = self
        s.comment_last_action = self.comment_last_action
        s.log = self._log
        for k, v in self.broker.markets.items():
            setattr(s, k.name, v)
        for k, v in self.broker.assets.items():
            setattr(s, k.name, v)

    def __str__(self):
        return ('{{"Account status":{}, "action_count":{}, "strategy":"{}", "price_df_rows":{}, "price_assets":{} }}').format(
            str(self.broker),
            len(self.actions),
            type(self._strategy).__name__,
            len(self._token_prices.index) if self._token_prices is not None else 0,
            ("[" + ",".join(f'"{x}"' for x in self._token_prices.columns) + "]" if self._token_prices is not None else str([])),
        )
