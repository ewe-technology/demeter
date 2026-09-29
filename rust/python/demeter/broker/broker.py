"""
Broker backed by the Rust engine: token balances live in ``demeter._rs.BrokerCore``.
Same public API as the original python Broker.
"""

from datetime import datetime
from decimal import Decimal
from typing import Callable, Dict

import pandas as pd

from ._typing import (
    Asset,
    TokenInfo,
    AccountStatus,
    MarketDict,
    AssetDict,
    BaseAction,
)
from .market import Market
from .._typing import DemeterError, UnitDecimal
from ..utils import get_formatted_from_dict, get_formatted_predefined, STYLE


class AssetView(Asset):
    """An ``Asset`` whose balance is read from / written to the engine."""

    def __init__(self, broker: "Broker", token: TokenInfo):
        self._broker = broker
        self.token_info = token
        self.name = token.name
        self.decimal = token.decimal

    @property
    def balance(self) -> Decimal:
        return self._broker._core.get_token_balance(self.name)

    @balance.setter
    def balance(self, value):
        self._broker._core.set_balance(self.name, self.decimal, value)

    def add(self, amount=Decimal(0)):
        self._broker._core.add_to_balance(self.name, self.decimal, amount)
        return self

    def sub(self, amount=Decimal(0), allow_negative_balance=False):
        self._broker._core.subtract_from_balance(self.name, self.decimal, amount)
        return self


class Broker:
    """
    Broker keeps token balances (cash) and the markets.

    :param allow_negative_balance: allow cash balance can be negative value or not. Default is False
    :type allow_negative_balance: bool
    """

    def __init__(self, allow_negative_balance=False, record_action_callback: Callable[[BaseAction], None] = None, _core=None):
        from .. import _rs

        allow_negative_balance = bool(allow_negative_balance)
        self._core = _core if _core is not None else _rs.BrokerCore(allow_negative_balance)
        self._core.allow_negative_balance = allow_negative_balance
        self._markets: MarketDict[Market] = MarketDict()
        self._tokens: Dict[str, TokenInfo] = {}
        self._asset_views: Dict[str, AssetView] = {}
        self._record_action_callback = record_action_callback
        self.__quote_token: TokenInfo | None = None

    # region properties
    @property
    def allow_negative_balance(self) -> bool:
        return self._core.allow_negative_balance

    @allow_negative_balance.setter
    def allow_negative_balance(self, value: bool):
        self._core.allow_negative_balance = bool(value)

    @property
    def markets(self) -> MarketDict[Market]:
        return self._markets

    @property
    def assets(self) -> AssetDict[Asset]:
        d = AssetDict()
        for name, decimal, _ in self._core.assets():
            token = self._token(name, decimal)
            d[token] = self._asset_view(token)
        return d

    def _asset_view(self, token: TokenInfo) -> "AssetView":
        v = self._asset_views.get(token.name)
        if v is None:
            v = AssetView(self, token)
            self._asset_views[token.name] = v
        return v

    @property
    def quote_token(self):
        return self.__quote_token

    @property
    def _quote_token(self):
        return self.__quote_token

    @_quote_token.setter
    def _quote_token(self, token: TokenInfo):
        self.__quote_token = token
        if token is not None:
            self._core.set_quote_token(token.name, token.decimal)

    # endregion

    def _token(self, name: str, decimal: int) -> TokenInfo:
        t = self._tokens.get(name)
        if t is None:
            t = TokenInfo(name, decimal)
            self._tokens[name] = t
        return t

    def _remember(self, token: TokenInfo):
        self._tokens.setdefault(token.name, token)

    def __str__(self):
        return '{{"assets":[{}],"markets":[{}]}}'.format(
            ",".join(f"{asset}" for asset in self.assets.values()), ",".join(f"{v}" for k, v in self.markets.items())
        )

    def add_market(self, market: Market):
        """Set a new market to broker"""
        if market.market_info in self._markets:
            raise DemeterError("market has exist")
        self._core.add_market(market._core)
        self._markets[market.market_info] = market
        market.broker = self
        market._record_action_callback = self._record_action_callback
        for t in (market.token0, market.token1):
            self._remember(t)

    def add_to_balance(self, token: TokenInfo, amount: Decimal | float) -> Asset:
        self._remember(token)
        self._core.add_to_balance(token.name, token.decimal, amount)
        return self._asset_view(token)

    def set_balance(self, token: TokenInfo, amount: Decimal | float) -> Asset:
        self._remember(token)
        self._core.set_balance(token.name, token.decimal, amount)
        return self._asset_view(token)

    def subtract_from_balance(self, token: TokenInfo, amount: Decimal | float) -> Asset:
        self._remember(token)
        self._core.subtract_from_balance(token.name, token.decimal, amount)
        return self._asset_view(token)

    def get_token_balance(self, token: TokenInfo) -> Decimal:
        return self._core.get_token_balance(token.name)

    def get_token_balance_with_unit(self, token: TokenInfo) -> UnitDecimal:
        return UnitDecimal(self.get_token_balance(token), token.name)

    def get_account_status(self, prices: pd.Series | Dict[str, Decimal], timestamp=None) -> AccountStatus:
        """Get account status, including net value, cash balance and balance in all markets"""
        if isinstance(prices, pd.Series):
            prices = prices.to_dict()
        elif not isinstance(prices, dict):
            prices = prices.to_dict()
        ts = timestamp if timestamp is not None else datetime(1970, 1, 1)
        row = self._core.get_account_status({str(k): v for k, v in prices.items()}, ts)
        return account_status_from_row(row, self)

    def formatted_str(self):
        str_to_print = get_formatted_predefined("Token balance in broker", STYLE["header2"]) + "\n"
        balances = {}
        for name, _, balance in self._core.assets():
            balances[name] = balance
        str_to_print += get_formatted_from_dict(balances) + "\n"
        str_to_print += get_formatted_predefined("Position value in markets", STYLE["header2"]) + "\n"
        for market in self._markets.values():
            str_to_print += market.formatted_str() + "\n"
        return str_to_print

    def check_backtest(self):
        if len(self.markets) < 1:
            raise AssertionError("No market assigned")
        for market in self.markets.values():
            market.check_market()

    def swap_by_from(self, from_token: TokenInfo, to_token: TokenInfo, amount, prices, fee_rate: Decimal = Decimal("0.003")):
        self._core.swap_by_from(
            (from_token.name, from_token.decimal), (to_token.name, to_token.decimal), amount, prices[from_token.name], prices[to_token.name], fee_rate
        )

    def swap_by_to(self, from_token: TokenInfo, to_token: TokenInfo, amount, prices, fee_rate: Decimal = Decimal("0.003")):
        self._core.swap_by_to(
            (from_token.name, from_token.decimal), (to_token.name, to_token.decimal), amount, prices[from_token.name], prices[to_token.name], fee_rate
        )


def account_status_from_row(row, broker: Broker) -> AccountStatus:
    """(timestamp, net_value, asset_value, [(token, decimal, balance)], [(market, balance tuple)]) -> AccountStatus"""
    from ..uniswap._typing import UniLpBalance

    ts, net_value, asset_value, assets, markets = row
    status = AccountStatus(timestamp=ts, net_value=net_value, asset_value=asset_value)
    for name, decimal, bal in assets:
        status.asset_balances[broker._token(name, decimal)] = bal
    by_name = {k.name: (k, m) for k, m in broker.markets.items()}
    for mname, (nv, lv, bu, qu, bp, qp, count) in markets:
        key, market = by_name[mname]
        b, q = market.base_token.name, market.quote_token.name
        status.market_status[key] = UniLpBalance(
            net_value=nv,
            liquidity_value=UnitDecimal(lv, q),
            base_uncollected=UnitDecimal(bu, b),
            quote_uncollected=UnitDecimal(qu, q),
            base_in_position=UnitDecimal(bp, b),
            quote_in_position=UnitDecimal(qp, q),
            position_count=count,
        )
    return status
