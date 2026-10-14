"""
Uniswap v3 LP market backed by the Rust engine.

Same public API as the original python ``UniLpMarket``. State (positions, fee accrual, data) lives
in ``demeter._rs.MarketCore``. Subclassing works as before: for example ``UniLpMarketV2`` in the
samples reads ``self._market_status``, ``self._pool``, ``self._is_token0_quote`` and calls
``self._convert_pair``, and all of those are available here.
"""

import logging
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Dict, Tuple

import orjson
import pandas as pd

from demeter.utils import orjson_default
from ._typing import (
    UniV3Pool,
    TokenInfo,
    UniLpBalance,
    PositionInfo,
    Position,
    UniDescription,
    UniswapMarketStatus,
    PositionStatus,
)
from .helper import _add_statistic_column
from .. import _rs
from .._bridge import MarketData, ipc_to_pandas, interval_to_seconds, pandas_to_ipc, to_ts
from .._typing import DemeterError, UnitDecimal
from ..broker import MarketBalance, Market, MarketInfo
from ..utils import get_formatted_from_dict, get_formatted_predefined, STYLE



class PositionView:
    """Live view of a position (python ``Position`` dataclass fields, read/write)."""

    __slots__ = ("_core", "_key")

    def __init__(self, core, key: PositionInfo):
        self._core = core
        self._key = key

    def _get(self, i):
        return self._core.position(self._key[0], self._key[1])[i]

    def _set(self, field, v):
        self._core.set_position_field(self._key[0], self._key[1], field, v)

    pending_amount0 = property(lambda s: s._get(0), lambda s, v: s._set("pending_amount0", v))
    pending_amount1 = property(lambda s: s._get(1), lambda s, v: s._set("pending_amount1", v))
    liquidity = property(lambda s: s._get(2), lambda s, v: s._set("liquidity", v))
    lower_price = property(lambda s: s._get(3), lambda s, v: s._set("lower_price", v))
    upper_price = property(lambda s: s._get(4), lambda s, v: s._set("upper_price", v))
    init_price = property(lambda s: s._get(5), lambda s, v: s._set("init_price", v))
    transferred = property(lambda s: s._get(6), lambda s, v: s._set("transferred", v))

    def __bool__(self):
        return True

    def __repr__(self):
        p = self._core.position(self._key[0], self._key[1])
        return (
            f"Position(pending_amount0={p[0]}, pending_amount1={p[1]}, liquidity={p[2]}, lower_price={p[3]}, "
            f"upper_price={p[4]}, init_price={p[5]}, transferred={p[6]})"
        )


class PositionsView(Mapping):
    """``market.positions``: a live, dict-like view keyed by ``PositionInfo``."""

    def __init__(self, core):
        self._core = core

    def __getitem__(self, key) -> PositionView:
        lower, upper = int(key[0]), int(key[1])
        if not self._core.has_position(lower, upper):
            raise KeyError(key)
        return PositionView(self._core, PositionInfo(lower, upper))

    def __contains__(self, key):
        try:
            return self._core.has_position(int(key[0]), int(key[1]))
        except (TypeError, IndexError):
            return False

    def __iter__(self):
        return iter([PositionInfo(lo, up) for lo, up in self._core.position_keys()])

    def __len__(self):
        return self._core.position_count()

    def copy(self) -> Dict[PositionInfo, PositionView]:
        """plain dict snapshot of the keys (values stay live views, like the python dict's shallow copy)"""
        return {k: PositionView(self._core, k) for k in self}

    def __delitem__(self, key):
        # like deleting from the python dict: the entry is forgotten, nothing goes back to the broker
        if not self._core.drop_position(int(key[0]), int(key[1])):
            raise KeyError(key)

    _MISSING = object()

    def pop(self, key, default=_MISSING):
        """``dict.pop``: remove the position and return a detached ``Position`` copy of it"""
        if key in self:
            value = Position(*self._core.position(int(key[0]), int(key[1])))
            self._core.drop_position(int(key[0]), int(key[1]))
            return value
        if default is PositionsView._MISSING:
            raise KeyError(key)
        return default

    def __repr__(self):
        return "{" + ", ".join(f"{k}: {self[k]}" for k in self) + "}"


class UniLpMarket(Market):
    """
    | UniLpMarket is the simulator of uniswap v3, it can simulate transactions such as add/remove liquidity, swap assets. and calculate position net value
    | UniLpMarket corresponds to a pool on chain, which means a token pair in a chain.

    :param market_info: key of this market
    :type market_info: MarketInfo
    :param pool_info: Uniswap v3 pool info
    :type pool_info: UniV3Pool
    """

    def __init__(self, market_info: MarketInfo, pool_info: UniV3Pool, data: pd.DataFrame = None, data_path: str = "./data"):
        # Market.__init__ is not called: its attributes are properties backed by the core here
        self._market_info: MarketInfo = market_info
        self._pool: UniV3Pool = pool_info
        self._core = _rs.MarketCore(
            market_info.name,
            market_info.type.value,
            (pool_info.token0.name, pool_info.token0.decimal),
            (pool_info.token1.name, pool_info.token1.decimal),
            str(pool_info.fee_rate * Decimal(100)),
            pool_info.quote_token.name,
            pool_info.tick_spacing,
        )
        self.data_path = data_path
        self.broker = None
        self._record_action_callback = None
        self.logger = logging.getLogger(__name__)
        self._price_status = None
        self.open = None
        self._is_token0_quote = pool_info.is_token0_quote
        self.base_token, self.quote_token = self._convert_pair(self.pool_info.token0, self.pool_info.token1)
        self._pool_price_unit = f"{self.base_token.name}/{self.quote_token.name}"
        if data is not None:
            self.data = data

    # region properties

    def __str__(self):
        return orjson.dumps(self.description, default=orjson_default).decode()

    @property
    def description(self) -> UniDescription:
        return UniDescription(
            type=type(self).__name__,
            name=self._market_info.name,
            token0=self.pool_info.token0,
            token1=self.pool_info.token1,
            quote_token=self.pool_info.quote_token,
            base_token=self.pool_info.base_token,
            fee_rate=self.pool_info.fee_rate,
        )

    @property
    def market_info(self) -> MarketInfo:
        return self._market_info

    @property
    def positions(self) -> PositionsView:
        """current positions (live view keyed by PositionInfo)"""
        return PositionsView(self._core)

    @property
    def _positions(self) -> PositionsView:
        return PositionsView(self._core)

    @property
    def pool_info(self) -> UniV3Pool:
        return self._pool

    @property
    def token0(self) -> TokenInfo:
        return self._pool.token0

    @property
    def token1(self) -> TokenInfo:
        return self._pool.token1

    @property
    def market_status(self) -> UniswapMarketStatus:
        ts = self._core.status_timestamp()
        if ts is None:
            return UniswapMarketStatus(None, pd.Series(dtype=object))
        return UniswapMarketStatus(pd.Timestamp(ts, unit="s").to_pydatetime(), self._core.status_bar())

    @property
    def _market_status(self) -> UniswapMarketStatus:
        return self.market_status

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
    def last_tick(self):
        return self._core.last_tick

    @last_tick.setter
    def last_tick(self, value):
        self._core.last_tick = value

    @property
    def data(self) -> MarketData | None:
        """
        Market data. A :class:`demeter._bridge.MarketData` proxy: column access returns pandas
        Series, other pandas operations work on a frame materialized on first use (cached).
        Writes must go through ``market.data[name] = series`` or ``market.data = frame``.
        """
        if not self._core.has_data():
            return None
        proxy = self.__dict__.get("_data_proxy")
        if proxy is None:
            proxy = MarketData(None, market=self)
            self.__dict__["_data_proxy"] = proxy
        return proxy

    @data.setter
    def data(self, value):
        if isinstance(value, MarketData):
            self._core.set_data(value.handle)
        elif isinstance(value, pd.DataFrame):
            self._core.set_data(_rs.DataHandle.from_ipc(pandas_to_ipc(value), self._core))
        else:
            raise ValueError("data must be a pandas DataFrame or demeter MarketData")
        self._refresh_data_handle()

    def _refresh_data_handle(self):
        """Keep a python-side reference to the current data (thread-safe handle), so pickling
        never touches the engine object: multiprocessing pickles from a helper thread."""
        self.__dict__["_data_handle"] = self._core.get_data() if self._core.has_data() else None

    @property
    def _data(self):
        return self.data

    # endregion

    def _record_action(self, action):
        pass  # actions are recorded by the engine

    def get_position(self, position_info: PositionInfo) -> PositionView:
        return self.positions[position_info]

    def set_market_status(self, market_status, price: pd.Series | None = None):
        """
        Set current pool status. The engine does this every iteration from market data; it can
        also be called directly, with ``market_status.data`` holding the row (pandas Series or
        UniV3PoolStatus with price, closeTick, currentLiquidity, inAmount0, inAmount1).
        """
        self._price_status = price
        ts = market_status.timestamp if hasattr(market_status, "timestamp") else market_status
        data = getattr(market_status, "data", None)
        if data is None:
            self._core.set_market_status(to_ts(ts))
            return

        def get(name, default=None):
            if isinstance(data, pd.Series):
                v = data[name] if name in data.index else default
            else:
                v = getattr(data, name, default)
            return default if v is None else v

        self._core.set_market_status_bar(
            to_ts(ts) if ts is not None else 0,
            get("price"),
            get("closeTick", 0),
            get("currentLiquidity", 0),
            get("inAmount0", 0),
            get("inAmount1", 0),
            get("openTick"),
            get("lowestTick"),
            get("highestTick"),
            get("netAmount0"),
            get("netAmount1"),
        )

    def _convert_pair(self, any0, any1):
        """
        convert order of token0/token1 to base_token/quote_token, according to self.is_token0_quote.
        Or convert order of base_token/quote_token to token0/token1
        """
        return (any1, any0) if self._is_token0_quote else (any0, any1)

    def check_market(self):
        if not self._core.has_data():
            raise DemeterError("data must be type of data frame")
        self._core.check_market()

    def update(self):
        """re-calculate status (fee accrual of this minute)."""
        self._core.update()

    def _get_value(self, amount0, amount1, pool_price):
        base, quote = self._convert_pair(amount0, amount1)
        return base * pool_price + quote

    def get_position_status(self, pos_key: PositionInfo) -> PositionStatus:
        return PositionStatus(*self._core.get_position_status(int(pos_key[0]), int(pos_key[1])))

    def get_position_amount(self, position_info: PositionInfo) -> Tuple[Decimal, Decimal]:
        return self._core.get_position_amount(int(position_info[0]), int(position_info[1]))

    def get_market_balance(self) -> MarketBalance:
        nv, lv, bu, qu, bp, qp, count = self._core.get_market_balance()
        b, q = self.base_token.name, self.quote_token.name
        return UniLpBalance(
            net_value=nv,
            liquidity_value=UnitDecimal(lv, q),
            base_uncollected=UnitDecimal(bu, b),
            quote_uncollected=UnitDecimal(qu, q),
            base_in_position=UnitDecimal(bp, b),
            quote_in_position=UnitDecimal(qp, q),
            position_count=count,
        )

    def transfer_position_out(self, position_info: PositionInfo):
        self._core.transfer_position_out(int(position_info[0]), int(position_info[1]))

    def transfer_position_in(self, position_info: PositionInfo):
        self._core.transfer_position_in(int(position_info[0]), int(position_info[1]))

    def tick_to_price(self, tick: int) -> Decimal:
        return self._core.tick_to_price(tick)

    def estimate_liquidity(self, value: Decimal, position: PositionInfo) -> Tuple[int, Decimal, Decimal]:
        return self._core.estimate_liquidity(value, int(position[0]), int(position[1]))

    def estimate_amount(self, value: Decimal, lower_tick: int, upper_tick: int) -> Tuple[Decimal, Decimal]:
        return self._core.estimate_amount(value, int(lower_tick), int(upper_tick))

    def price_to_tick(self, price: Decimal | float) -> int:
        """convert price to tick (snapped to the tick spacing)"""
        return self._core.price_to_tick(price)

    def price_to_raw_tick(self, price: Decimal | float) -> int:
        """convert price to tick without snapping to the tick spacing"""
        return self._core.price_to_raw_tick(price)

    def _add_liquidity_by_tick(self, token0_amount: Decimal, token1_amount: Decimal, lower_tick: int, upper_tick: int, sqrt_price_x96: int = -1):
        sqrt = None if sqrt_price_x96 == -1 or sqrt_price_x96 is None else int(sqrt_price_x96)
        lo, up, used0, used1, liq = self._core.add_liquidity_by_tick_raw(token0_amount, token1_amount, lower_tick, upper_tick, sqrt)
        return PositionInfo(lo, up), used0, used1, liq

    # action for strategy

    def add_liquidity(
        self,
        lower_quote_price: Decimal | float,
        upper_quote_price: Decimal | float,
        quote_max_amount: Decimal | float = None,
        base_max_amount: Decimal | float = None,
    ) -> (PositionInfo, Decimal, Decimal, int):
        """
        add liquidity, then get a new position

        :return: added position, base token used, quote token used, liquidity
        """
        lo, up, base_used, quote_used, liq = self._core.add_liquidity(lower_quote_price, upper_quote_price, quote_max_amount, base_max_amount)
        return PositionInfo(lo, up), base_used, quote_used, liq

    def add_liquidity_by_tick(
        self,
        lower_tick: int,
        upper_tick: int,
        base_max_amount: Decimal | float = None,
        quote_max_amount: Decimal | float = None,
        sqrt_price_x96: int = -1,
        tick: int = -1,
        trim_tick: bool = True,
    ) -> (PositionInfo, Decimal, Decimal, int):
        """
        add liquidity by tick range.

        :return: added position, base token used, quote token used, liquidity
        """
        sqrt = None if sqrt_price_x96 == -1 or sqrt_price_x96 is None else int(sqrt_price_x96)
        t = None if tick == -1 or tick is None else tick
        lo, up, base_used, quote_used, liq = self._core.add_liquidity_by_tick(
            lower_tick, upper_tick, base_max_amount, quote_max_amount, sqrt, t, trim_tick
        )
        return PositionInfo(lo, up), base_used, quote_used, liq

    def remove_liquidity(
        self,
        position: PositionInfo,
        liquidity: int = None,
        collect: bool = True,
        sqrt_price_x96: int = -1,
        remove_dry_pool: bool = True,
    ) -> (Decimal, Decimal):
        """remove liquidity; returns (base, quote) collected (or moved to pending if collect=False)"""
        if liquidity and liquidity < 0:
            raise DemeterError("liquidity should large than 0")
        sqrt = None if sqrt_price_x96 == -1 or sqrt_price_x96 is None else int(sqrt_price_x96)
        return self._core.remove_liquidity(int(position[0]), int(position[1]), liquidity, collect, sqrt, remove_dry_pool)

    def collect_fee(
        self,
        position: PositionInfo,
        max_collect_amount0: Decimal = None,
        max_collect_amount1: Decimal = None,
        remove_dry_pool: bool = True,
        collect_to_user: bool = True,
    ) -> (Decimal, Decimal):
        """collect fee and tokens of a position; returns (base, quote)"""
        if (max_collect_amount0 and max_collect_amount0 < 0) or (max_collect_amount1 and max_collect_amount1 < 0):
            raise DemeterError("collect amount should large than 0")
        return self._core.collect_fee(
            int(position[0]), int(position[1]), max_collect_amount0, max_collect_amount1, remove_dry_pool, collect_to_user
        )

    def swap(self, from_amount, from_token: TokenInfo, to_token: TokenInfo, price=None, throw_action=True):
        """Swap token with this pool. returns (fee in from token, to_amount)"""
        return self._core.swap(from_amount, from_token.name, to_token.name, price, throw_action)

    def buy(self, base_token_amount: Decimal | float, price: Decimal | float = None) -> (Decimal, Decimal, Decimal):
        """buy base token; returns (fee in quote, quote spent, base got)"""
        return self._core.buy(base_token_amount, price)

    def sell(self, base_token_amount: Decimal | float, price: Decimal | float = None) -> (Decimal, Decimal, Decimal):
        """sell base token; returns (fee in base, base spent, quote got)"""
        return self._core.sell(base_token_amount, price)

    def add_liquidity_by_value(self, lower_tick: int, upper_tick: int, value_to_use: Decimal | None = None, trim_tick: bool = True):
        lo, up, base_used, quote_used, liq = self._core.add_liquidity_by_value(lower_tick, upper_tick, value_to_use, trim_tick)
        return PositionInfo(lo, up), base_used, quote_used, liq

    def even_rebalance(self, price: Decimal | None = None):
        """Divide assets equally between two tokens."""
        self._core.even_rebalance(price)

    def remove_all_liquidity(self):
        self._core.remove_all_liquidity()

    def formatted_str(self) -> str:
        value = get_formatted_predefined(f"{self.market_info.name}({type(self).__name__})", STYLE["header3"]) + "\n"
        value += (
            get_formatted_from_dict(
                {
                    "token0": self.pool_info.token0.name,
                    "token1": self.pool_info.token1.name,
                    "fee(%)": self.pool_info.fee_rate * 100,
                    "quote token": self.quote_token.name,
                }
            )
            + "\n"
        )
        value += get_formatted_predefined("positions", STYLE["key"]) + "\n"
        rows = {"lower_tick": [], "upper_tick": [], "pending0": [], "pending1": [], "liquidity": []}
        for k in self.positions:
            p = self._core.position(k[0], k[1])
            rows["lower_tick"].append(k[0])
            rows["upper_tick"].append(k[1])
            rows["pending0"].append(p[0])
            rows["pending1"].append(p[1])
            rows["liquidity"].append(p[2])
        df = pd.DataFrame(rows)
        value += df.to_string() if len(df.index) > 0 else "Empty DataFrame\n"
        return value

    def _resample(self, freq: str):
        self._core.resample(interval_to_seconds(freq))
        self._refresh_data_handle()

    def load_data(self, chain: str, contract_addr: str, start_date: date, end_date: date):
        self._core.load_data(chain, contract_addr, start_date, end_date, str(self.data_path))
        self._refresh_data_handle()

    def get_price_from_data(self):
        """(price dataframe, quote token); the dataframe has base price and quote price 1"""
        return ipc_to_pandas(self._core.price_ipc()), self.pool_info.quote_token

    # pickling (BacktestManager sends markets to worker processes)
    def __getstate__(self):
        # Only python-side state: multiprocessing pickles on a helper thread, where the engine
        # object must not be touched. Positions and market status are not carried over.
        state = {k: v for k, v in self.__dict__.items() if k not in ("_core", "_data_proxy", "_data_handle", "broker", "logger")}
        handle = self.__dict__.get("_data_handle")
        state["_data_ipc"] = bytes(handle.to_ipc()) if handle is not None else None
        return state

    def __setstate__(self, state):
        data_ipc = state.pop("_data_ipc")
        UniLpMarket.__init__(self, state["_market_info"], state["_pool"], data_path=state.get("data_path", "./data"))
        self.__dict__.update(state)
        if data_ipc is not None:
            self._core.set_data(_rs.DataHandle.from_ipc(data_ipc, self._core))
            self._refresh_data_handle()

    def add_statistic_column(self, df):
        """(re)compute close / price / volume columns of `df` (MarketData or pandas DataFrame) in place"""
        if isinstance(df, MarketData):
            new = df.handle.with_statistics(self._core)
            if df._market is not None:
                df._market._core.set_data(new)
                df._market._refresh_data_handle()
            else:
                object.__setattr__(df, "_handle", new)
                object.__setattr__(df, "_df", None)
        else:
            _add_statistic_column(df, self.pool_info)


# methods the engine calls natively (backtest loop, or from other engine methods such as
# even_rebalance / add_liquidity_by_value / remove_liquidity); python overrides of them are not used there
ENGINE_CALLED_METHODS = (
    "update", "set_market_status", "get_market_balance", "check_market", "swap", "buy", "sell",
    "collect_fee", "add_liquidity_by_tick", "_add_liquidity_by_tick",
)


def overridden_engine_methods(market) -> list:
    """names in ENGINE_CALLED_METHODS that a python subclass of UniLpMarket overrides"""
    cls = type(market)
    return [n for n in ENGINE_CALLED_METHODS if getattr(cls, n, None) is not getattr(UniLpMarket, n)]
