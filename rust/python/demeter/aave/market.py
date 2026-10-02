"""
Aave v3 market backed by the Rust engine.

Same public API as the original python ``AaveV3Market``. Supplies, borrows, market status and
data live in ``demeter._rs.AaveMarketCore``; ``_supplies`` / ``_borrows`` are live dict-like views
of them.
"""

import logging
import os
from collections.abc import Mapping, MutableMapping
from datetime import date
from decimal import Decimal
from typing import Dict, List, Set

import orjson
import pandas as pd

from . import helper
from ._typing import (
    AaveBalance,
    Supply,
    Borrow,
    supply_to_dataframe,
    borrow_to_dataframe,
    AaveDescription,
    AaveMarketStatus,
)
from .helper import AaveMarketData, REQUIRED_DATA_COLUMN
from .. import _rs
from .._bridge import interval_to_seconds, pandas_to_ipc
from .._typing import DemeterError, TokenInfo, ChainType, USD
from ..broker import Market, MarketInfo
from ..utils import get_formatted_predefined, STYLE, get_formatted_from_dict, console_text


class _SupplyInfoView:
    """Live ``SupplyInfo`` of one supplied token (fields read from / written to the engine)."""

    __slots__ = ("_core", "_name")

    def __init__(self, core, name: str):
        self._core = core
        self._name = name

    def _get(self, i):
        for row in self._core.supply_infos():
            if row[0] == self._name:
                return row[i]
        raise KeyError(self._name)

    base_amount = property(lambda s: s._get(2), lambda s, v: s._core.set_supply_field(s._name, "base_amount", v))
    collateral = property(lambda s: s._get(3), lambda s, v: s._core.set_supply_field(s._name, "collateral", v))
    begin_supply_index = property(lambda s: s._get(4), lambda s, v: s._core.set_supply_field(s._name, "begin_supply_index", v))

    def __repr__(self):
        return f"SupplyInfo(base_amount={self.base_amount}, collateral={self.collateral}, begin_supply_index={self.begin_supply_index})"


class _BorrowInfoView:
    """Live ``BorrowInfo`` of one borrowed token."""

    __slots__ = ("_core", "_name")

    def __init__(self, core, name: str):
        self._core = core
        self._name = name

    def _get(self, i):
        for row in self._core.borrow_infos():
            if row[0] == self._name:
                return row[i]
        raise KeyError(self._name)

    base_amount = property(lambda s: s._get(2), lambda s, v: s._core.set_borrow_field(s._name, "base_amount", v))
    begin_borrow_index = property(lambda s: s._get(3), lambda s, v: s._core.set_borrow_field(s._name, "begin_borrow_index", v))

    def __repr__(self):
        return f"BorrowInfo(base_amount={self.base_amount}, begin_borrow_index={self.begin_borrow_index})"


class _InfoMap(MutableMapping):
    """``market._supplies`` / ``market._borrows``: live dicts keyed by TokenInfo, like the python ones.
    As with the python dicts, writing an entry does not refresh the cached values of this minute."""

    def __init__(self, market: "AaveV3Market", supplies: bool):
        self._m = market
        self._is_supply = supplies

    def _rows(self):
        core = self._m._core
        return core.supply_infos() if self._is_supply else core.borrow_infos()

    def _names(self):
        return [r[0] for r in self._rows()]

    @staticmethod
    def _name(key) -> str:
        return key.name if isinstance(key, TokenInfo) else str(key).upper()

    def __getitem__(self, key):
        name = self._name(key)
        if name not in self._names():
            raise KeyError(key)
        view = _SupplyInfoView if self._is_supply else _BorrowInfoView
        return view(self._m._core, name)

    def __setitem__(self, key: TokenInfo, value):
        self._m._remember(key)
        if self._is_supply:
            self._m._core.set_supply_info(key.name, key.decimal, value.base_amount, bool(value.collateral), value.begin_supply_index)
        else:
            self._m._core.set_borrow_info(key.name, key.decimal, value.base_amount, value.begin_borrow_index)

    def __delitem__(self, key):
        name = self._name(key)
        core = self._m._core
        removed = core.remove_supply_info(name) if self._is_supply else core.remove_borrow_info(name)
        if not removed:
            raise KeyError(key)

    def __contains__(self, key):
        return self._name(key) in self._names()

    def __iter__(self):
        return iter([self._m._tok(r[0], r[1]) for r in self._rows()])

    def __len__(self):
        return len(self._rows())

    def __repr__(self):
        return "{" + ", ".join(f"{k}: {self[k]}" for k in self) + "}"


def _price_list(price):
    """price Series / dict / engine PriceRow -> [(token, price)]"""
    if price is None:
        return None
    return [(str(k), v) for k, v in price.items()]


def _status_rows(data):
    """market status data (engine view, pandas Series with a (token, column) index, or a mapping
    token -> status) -> [(token, [values in REQUIRED_DATA_COLUMN order] or None)]"""
    if isinstance(data, _rs.AaveStatusView):
        return data.values_by_token()
    if isinstance(data, pd.Series) and isinstance(data.index, pd.MultiIndex):
        tokens = list(dict.fromkeys(data.index.get_level_values(0)))
        return [(str(t), [data[(t, c)] for c in REQUIRED_DATA_COLUMN]) for t in tokens]
    rows = []
    for t, s in data.items():
        if isinstance(s, (pd.Series, Mapping)):
            rows.append((str(t), [s[c] for c in REQUIRED_DATA_COLUMN]))
        else:
            rows.append((str(t), [getattr(s, c) for c in REQUIRED_DATA_COLUMN]))
    return rows


class AaveV3Market(Market):
    """
    | AaveV3Market is the simulator of aave v3, here you can simulate some transactions like supply/borrow etc. this class also tracks value change.
    | AaveV3Market corresponds to a pool on chain, and one chan has one pool.

    :param market_info: key of this market
    :type market_info: MarketInfo
    :param risk_parameters_path: path to load risk parameters csv file, those files can be downloaded form https://www.config.fyi. One csv file for each chain.
    :type risk_parameters_path: str
    :param tokens: Tokens which will be used in this market
    :type tokens: List[TokenInfo]
    """

    def __init__(
        self,
        market_info: MarketInfo,
        risk_parameters_path: str,
        tokens: List[TokenInfo] = None,
        data: pd.DataFrame | None = None,
        data_path: str = "./data",
    ):
        # Market.__init__ is not called: its attributes are properties backed by the core here
        tokens = tokens if tokens is not None else []
        self._market_info: MarketInfo = market_info
        # absolute, so an unpickled copy (BacktestManager workers) finds the file from any directory
        self._risk_parameters_path = os.path.abspath(str(risk_parameters_path))
        self._core = _rs.AaveMarketCore(
            market_info.name, market_info.type.value, self._risk_parameters_path, [(t.name, t.decimal, t.address) for t in tokens]
        )
        self._risk_parameters = None
        self._token_objs: Dict[str, TokenInfo] = {}
        for t in tokens:
            self._remember(t)
        self.data_path = data_path
        self._broker = None
        self._record_action_callback = None
        self.logger = logging.getLogger(__name__)
        self.open = None
        self.quote_token: TokenInfo = USD
        self._data_cache = None
        if data is not None:
            self.data = data

    # region properties

    def __str__(self):
        from demeter.utils import orjson_default

        return orjson.dumps(self.description, default=orjson_default).decode()

    def _remember(self, token: TokenInfo):
        self._token_objs.setdefault(token.name, token)

    def _tok(self, name: str, decimal: int = 0, address: str = "") -> TokenInfo:
        t = self._token_objs.get(name)
        if t is None:
            t = TokenInfo(name, decimal, address)
            self._token_objs[name] = t
        return t

    @property
    def market_info(self) -> MarketInfo:
        return self._market_info

    @property
    def broker(self):
        return self._broker

    @broker.setter
    def broker(self, value):
        self._broker = value
        if value is not None:
            self._core.attach_broker(value._core)

    @property
    def has_update(self) -> bool:
        return self._core.has_update

    @has_update.setter
    def has_update(self, value: bool):
        self._core.has_update = bool(value)

    @property
    def is_open(self) -> bool:
        return self._core.is_open

    @is_open.setter
    def is_open(self, value):
        pass  # computed by the engine from the data index

    @property
    def description(self):
        """
        Get a brief description of this market
        """
        return AaveDescription(type(self).__name__, self._market_info.name, len(self._supplies), len(self._borrows))

    @property
    def risk_parameters(self) -> pd.DataFrame:
        """
        Get risk parameters
        """
        if self._risk_parameters is None:
            self._risk_parameters = helper.load_risk_parameter(self._risk_parameters_path)
        return self._risk_parameters

    @property
    def _supplies(self) -> _InfoMap:
        return _InfoMap(self, True)

    @property
    def _borrows(self) -> _InfoMap:
        return _InfoMap(self, False)

    @property
    def _price_status(self) -> pd.Series | None:
        prices = self._core.price_status()
        if prices is None:
            return None
        return pd.Series({k: v for k, v in prices}, dtype=object)

    def set_token_data(self, token_info: TokenInfo, token_data: pd.DataFrame):
        """
        Set aave pool data of one token. Usually demeter-fetch will keep one csv file for each token.

        :param token_info: which token to set
        :type token_info: TokenInfo
        :param token_data: data
        :type token_data: DataFrame
        """
        if self._core.has_data() and self._core.get_data().has_token(token_info.name):
            raise DemeterError(f"{token_info.name} has already set to data")
        if not isinstance(token_data, pd.DataFrame):
            raise ValueError()
        self._remember(token_info)
        self._core.set_token_data(token_info.name, pandas_to_ipc(token_data))
        self._data_cache = None

    @property
    def tokens(self) -> Set[TokenInfo]:
        """
        Get tokens in aave back test
        """
        return {self._tok(n, d, a) for n, d, a in self._core.tokens()}

    def _values(self, rows) -> Dict[TokenInfo, Decimal]:
        return {self._tok(n, d): v for n, d, v in rows}

    @property
    def supplies_value(self) -> Dict[TokenInfo, Decimal]:
        """
        Get value of all supplied token. unit is usd
        """
        return self._values(self._core.supplies_value())

    @property
    def total_supply_value(self) -> Decimal:
        """
        Get sum supply value in this pool, unit is usd
        """
        return self._core.total_supply_value()

    @property
    def collateral_value(self) -> Dict[TokenInfo, Decimal]:
        """
        Get value of all collateral token. unit is usd
        """
        return self._values(self._core.collateral_value())

    @property
    def total_collateral_value(self) -> Decimal:
        """
        Get sum collateral value in this pool, unit is usd
        """
        return self._core.total_collateral_value()

    @property
    def borrows_value(self) -> Dict[TokenInfo, Decimal]:
        """
        Get value of all borrowed token. unit is usd
        """
        return self._values(self._core.borrows_value())

    @property
    def total_borrows_value(self) -> Decimal:
        """
        Get sum borrow value in this pool, unit is usd
        """
        return self._core.total_borrows_value()

    def _supply(self, row) -> Supply:
        name, decimal, base_amount, collateral, amount, apy, value, begin = row
        return Supply(
            token=self._tok(name, decimal),
            base_amount=base_amount,
            collateral=collateral,
            amount=amount,
            apy=apy,
            value=value,
            begin_supply_index=begin,
        )

    def _borrow(self, row) -> Borrow:
        name, decimal, base_amount, amount, apy, value, begin = row
        return Borrow(token=self._tok(name, decimal), base_amount=base_amount, amount=amount, apy=apy, value=value, begin_borrow_index=begin)

    @property
    def supplies(self) -> Dict[TokenInfo, Supply]:
        """
        Get amounts and values of all supplies
        """
        return {s.token: s for s in map(self._supply, self._core.supplies())}

    @property
    def supply_keys(self) -> List[TokenInfo]:
        """
        Get all supply keys
        """
        return list(self._supplies.keys())

    @property
    def borrows(self) -> Dict[TokenInfo, Borrow]:
        """
        Get amounts and values of all borrows
        """
        return {b.token: b for b in map(self._borrow, self._core.borrows())}

    @property
    def borrow_keys(self) -> List[TokenInfo]:
        """
        Get all borrow keys
        """
        return list(self._borrows.keys())

    @property
    def market_status(self) -> AaveMarketStatus | None:
        """
        Get market status. ``market_status.data`` is the pool status row: ``data["WETH"].liquidity_index``.
        """
        ts = self._core.status_timestamp()
        if ts is None:
            return None
        return AaveMarketStatus(pd.Timestamp(ts, unit="s").to_pydatetime(), self._core.status_view())

    @property
    def _market_status(self) -> AaveMarketStatus | None:
        return self.market_status

    def set_market_status(
        self,
        data: AaveMarketStatus,
        price: pd.Series,
    ):
        """
        Set up pool status of this moment, such as liquidity index, supply/borrow rate, and price.
        The engine does this every iteration. When calling it yourself, ``data.data`` may hold the
        pool status (a pandas Series with a (token, column) index, or ``market_status.data``);
        if it is None the row is read from the market data.

        :param data: market status
        :type data: AaveMarketStatus
        :param price: current price of tokens involved
        :type price: Series
        """
        ts = data.timestamp if hasattr(data, "timestamp") else data
        row = getattr(data, "data", None)
        prices = _price_list(price)
        if row is None:
            self._core.set_market_status(ts, prices)
        else:
            self._core.set_market_status_values(ts, _status_rows(row), prices)

    @property
    def liquidation_threshold(self) -> Decimal:
        """
        Get liquidation threshold
        """
        return self._core.liquidation_threshold()

    @property
    def max_ltv(self) -> Decimal:
        """
        Get current ltv, it's the max ltv of current user
        """
        return self._core.max_ltv()

    @property
    def ltv(self) -> Decimal:
        """
        Get current ltv
        """
        return self._core.ltv()

    @property
    def health_factor(self) -> Decimal:
        """
        Get health factor
        """
        return self._core.health_factor()

    @property
    def supply_apy(self) -> Decimal:
        """
        Calculate apy of all supplies
        """
        return self._core.supply_apy()

    @property
    def borrow_apy(self) -> Decimal:
        """
        Calculate apy of all borrows
        """
        return self._core.borrow_apy()

    @property
    def total_apy(self) -> Decimal:
        """
        Calculate total apy based on borrow/supply apy and amount
        """
        return self._core.total_apy()

    def get_supply(self, token_info: TokenInfo) -> Supply:
        """
        Get details of supply position, include value, amount, apy etc.
        """
        return self._supply(self._core.get_supply(token_info.name))

    def get_borrow(self, borrow_key: TokenInfo) -> Borrow:
        """
        Get details of borrow position. include type, amount, value etc.
        """
        return self._borrow(self._core.get_borrow(borrow_key.name))

    def add_token(self, token_info: TokenInfo | List[TokenInfo]):
        """
        Add one or an array of token to aave back test.
        """
        if not isinstance(token_info, list):
            token_info = [token_info]
        for t in token_info:
            self._remember(t)
            self._core.add_token(t.name, t.decimal, t.address)

    def get_market_balance(self) -> AaveBalance:
        """
        Get position and their values invested in aave market.
        """
        return aave_balance(self._core.get_market_balance())

    # region for subclass to override
    def check_market(self):
        """
        Check market tokens before back test
        """
        if not self._core.has_data():
            raise DemeterError("data must be type of data frame")
        self._core.check_market()

    def update(self):
        """
        Trigger update of this market (liquidation when health factor is below 1)
        """
        self._core.update()

    def formatted_str(self):
        """
        Return a brief description of this market in pretty format. Used for print in console.
        """
        value = get_formatted_predefined(f"{self.market_info.name}({type(self).__name__})", STYLE["header3"]) + "\n"
        token_dict = {"tokens": ",".join([t.name for t in self.tokens])}
        value += get_formatted_from_dict(token_dict) + "\n"
        balance = self.get_market_balance()
        value += (
            get_formatted_from_dict(
                {
                    "net_value": console_text.format_value(balance.net_value),
                    "health_factor": console_text.format_value(balance.health_factor),
                    "borrow_balance": console_text.format_value(balance.borrows_value),
                    "supply_balance": console_text.format_value(balance.supplies_value),
                    "collateral_balance": console_text.format_value(balance.collaterals_value),
                    "supply_apy": console_text.format_value(balance.supply_apy),
                    "borrow_apy": console_text.format_value(balance.borrow_apy),
                    "net_apy": console_text.format_value(balance.net_apy),
                }
            )
            + "\n"
        )
        value += get_formatted_predefined("Supplies", STYLE["key"]) + "\n"
        supply_df = supply_to_dataframe(self.supplies)
        value += supply_df.to_string() + "\n" if len(supply_df.index) > 0 else "Empty DataFrame\n"
        value += get_formatted_predefined("Borrows", STYLE["key"]) + "\n"
        borrow_df = borrow_to_dataframe(self.borrows)
        value += borrow_df.to_string() + "\n" if len(borrow_df.index) > 0 else "Empty DataFrame\n"

        return value

    # endregion

    def supply(self, token_info: TokenInfo, amount: Decimal | float, collateral: bool = True):
        """
        | Supply asset to aave pool
        | Note:
        | 1. some token are not allow to collateral, it's decided by risk parameter
        | 2. if append amount to existing supply, collateral can not change.
        """
        self._remember(token_info)
        self._core.supply(token_info.name, token_info.decimal, amount, bool(collateral))

    def change_collateral(self, token_info: TokenInfo, collateral: bool):
        """
        Change collateral type of supply position. Health factor will be checked to prevent liquidation
        """
        self._core.change_collateral(token_info.name, token_info.decimal, bool(collateral))

    def withdraw(self, token_info: TokenInfo, amount: Decimal | float = None):
        """
        Withdraw supply from aave pool. If amount is None, withdraw everything.
        """
        self._core.withdraw(token_info.name, token_info.decimal, amount)

    def get_max_withdraw_amount(self, token_info: TokenInfo) -> Decimal:
        """
        Get max available withdraw amount
        """
        return self._core.get_max_withdraw_amount(token_info.name)

    def get_max_borrow_amount(self, token_info: TokenInfo) -> Decimal:
        """
        Get max token amount to borrow.
        """
        return self._core.get_max_borrow_amount(token_info.name)

    def borrow(self, token_info: TokenInfo, amount: Decimal | float = None):
        """
        | Borrow token from aave pool. If amount is None, borrow the max amount.
        | 1. Risk parameter decides Which token is allowed to borrow
        | 2. If this borrow transaction will cause health factor below 1, an exception will be raised.
        | 3. If Borrow on existing borrow key, amount will be added to existing key
        """
        self._remember(token_info)
        self._core.borrow(token_info.name, token_info.decimal, amount)

    def get_max_repay_amount(self, token_info: TokenInfo) -> Decimal:
        """
        Get max token amount to repay.
        """
        return self._core.get_max_repay_amount(token_info.name)

    def _get_swap_amount(self, from_token: TokenInfo, to_token: TokenInfo, amount: Decimal, swap_fee=0):
        prices = self._price_status
        return amount * (1 - swap_fee) * prices.loc[from_token.name] / prices.loc[to_token.name]

    def repay(
        self,
        borrow_token: TokenInfo,
        payback_amount: Decimal | float = None,
        repay_with_collateral: bool = False,
        repay_collateral_token: TokenInfo = None,
    ):
        """
        Repay borrow. You can repay with collateral token or cash. If payback_amount is None, repay the whole debt.
        """
        collateral = None if repay_collateral_token is None else (repay_collateral_token.name, repay_collateral_token.decimal)
        self._core.repay(borrow_token.name, borrow_token.decimal, payback_amount, bool(repay_with_collateral), collateral)

    def _liquidate(self):
        """passive liquidation (what ``update`` does)"""
        self._core.update()

    def _resample(self, freq: str):
        self._core.resample(interval_to_seconds(freq))
        self._data_cache = None

    def load_data(
        self,
        chain: ChainType,
        token_info_list: List[TokenInfo],
        start_date: date,
        end_date: date,
    ):
        for t in token_info_list:
            self._remember(t)
        chain_name = chain.name if hasattr(chain, "name") else str(chain)
        self._core.load_data(chain_name, [(t.name, t.decimal, t.address) for t in token_info_list], start_date, end_date, str(self.data_path))
        self._data_cache = None

    @property
    def data(self) -> AaveMarketData | None:
        """
        Market data: an :class:`demeter.aave.helper.AaveMarketData` proxy with (token, column) columns.
        Assign a DataFrame (or what ``load_aave_data`` returns) to replace it.
        """
        if not self._core.has_data():
            return None
        handle = self._core.get_data()
        if self._data_cache is None or self._data_cache.handle.ptr() != handle.ptr():
            self._data_cache = AaveMarketData(handle)
        return self._data_cache

    @data.setter
    def data(self, value):
        if isinstance(value, AaveMarketData):
            self._core.set_data(value.handle)
        elif isinstance(value, pd.DataFrame):
            self._core.set_data(helper.frame_to_handle(value))
        else:
            raise ValueError()
        self._data_cache = None

    @property
    def _data(self):
        return self.data

    def _record_action(self, action):
        pass  # actions are recorded by the engine

    # pickling (BacktestManager sends markets to worker processes): settings and data travel,
    # supplies / borrows / market status do not
    def __getstate__(self):
        state = {k: v for k, v in self.__dict__.items() if k not in ("_core", "_broker", "logger", "_data_cache", "_risk_parameters")}
        state["_data_ipc"] = bytes(self._core.get_data().to_ipc()) if self._core.has_data() else None
        state["_tokens"] = list(self.tokens)
        return state

    def __setstate__(self, state):
        data_ipc = state.pop("_data_ipc")
        tokens = state.pop("_tokens")
        AaveV3Market.__init__(self, state["_market_info"], state["_risk_parameters_path"], tokens, data_path=state.get("data_path", "./data"))
        self.__dict__.update(state)
        if data_ipc is not None:
            self._core.set_data(_rs.AaveDataHandle.from_ipc(data_ipc))


def aave_balance(t) -> AaveBalance:
    """engine balance tuple (AaveBalance field order) -> AaveBalance"""
    (
        net_value,
        supplies_count,
        borrows_count,
        borrows_value,
        supplies_value,
        collaterals_value,
        health_factor,
        max_ltv,
        ltv,
        liquidation_threshold,
        supply_apy,
        borrow_apy,
        net_apy,
    ) = t
    return AaveBalance(
        net_value=net_value,
        supplies_count=supplies_count,
        borrows_count=borrows_count,
        borrows_value=borrows_value,
        supplies_value=supplies_value,
        collaterals_value=collaterals_value,
        health_factor=health_factor,
        max_ltv=max_ltv,
        ltv=ltv,
        liquidation_threshold=liquidation_threshold,
        supply_apy=supply_apy,
        borrow_apy=borrow_apy,
        net_apy=net_apy,
    )


# methods the engine calls natively from the backtest loop; python overrides of them are not used there
ENGINE_CALLED_METHODS = ("update", "set_market_status", "get_market_balance", "check_market", "_liquidate")


def overridden_engine_methods(market) -> list:
    """names in ENGINE_CALLED_METHODS that a python subclass of AaveV3Market overrides"""
    cls = type(market)
    return [n for n in ENGINE_CALLED_METHODS if getattr(cls, n, None) is not getattr(AaveV3Market, n)]
