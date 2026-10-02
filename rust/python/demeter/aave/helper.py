"""
Aave data helpers. Data loading runs in Rust (``demeter._rs.AaveDataHandle``); the risk parameter
DataFrame is built here with pandas, as before.
"""

import logging
import os
from _decimal import Decimal
from datetime import date
from typing import Dict, List

import pandas as pd

from .. import _rs
from .._bridge import ipc_to_pandas, pandas_to_ipc
from .._typing import DemeterError, ChainType, TokenInfo
from ..broker import MarketTypeEnum
from ._typing import RiskParameter

MIN_TOKEN_VALUE = 1e-18 - 1e-27


def sub_base_amount(old_v, value):
    """
    | Subtract base amount.
    | Usually, max token decimal is 18. so if token value is below 1e-18, we consider it's 0
    | It's necessary because number here is kept in decimal instead of int256. so there will be calculation errors.
    """

    new_v = old_v - value
    if new_v < MIN_TOKEN_VALUE:
        return 0
    else:
        return new_v


REQUIRED_DATA_COLUMN = [
    "liquidity_rate",
    "stable_borrow_rate",
    "variable_borrow_rate",
    "liquidity_index",
    "variable_borrow_index",
]


def load_risk_parameter(token_setting_path: str) -> pd.DataFrame | Dict[str, RiskParameter]:
    """
    | Load risk parameter, and convert float to decimal.
    | Download by "demeter-fetch aave -h"

    :param token_setting_path: risk parameter file path
    :type token_setting_path: str
    :return: risk parameter dataframe
    :rtype: DataFrame | Dict[str, RiskParameter]
    """
    path = os.path.join(token_setting_path)
    if not os.path.exists(path):
        raise DemeterError(f"risk parameter file {path} not exist, please download csv with 'demeter-fetch aave -h'")
    rp = pd.read_csv(path)
    usdc = rp["symbol"] == "USDC"
    rp.loc[usdc, "symbol"] = rp.loc[usdc, "name"].apply(lambda x: "USDC" if x == "USD Coin" else "USDC.E")
    rp = rp[
        [
            "symbol",
            "usageAsCollateralEnabled",
            "baseLTVasCollateral",
            "reserveLiquidationThreshold",
            "reserveLiquidationBonus",
            "reserveFactor",
            "borrowingEnabled",
            "optimalUsageRatio",
            "variableRateSlope1",
            "variableRateSlope2",
            "baseVariableBorrowRate",
            "supplyCap",
            "borrowCap",
            "borrowableInIsolation",
            "flashLoanEnabled",
        ]
    ]

    rp["reserveLiquidationBonus"] = rp["reserveLiquidationBonus"].apply(lambda x: Decimal(x - 10000)) / 10000
    rp[["baseLTVasCollateral", "reserveLiquidationThreshold", "reserveFactor"]] = (
        rp[["baseLTVasCollateral", "reserveLiquidationThreshold", "reserveFactor"]].map(lambda x: Decimal(x)) / 10000
    )
    rp[["optimalUsageRatio", "baseVariableBorrowRate", "variableRateSlope1", "variableRateSlope2"]] = (
        rp[["optimalUsageRatio", "baseVariableBorrowRate", "variableRateSlope1", "variableRateSlope2"]].map(lambda x: Decimal(x)) / 10**27
    )

    rp = rp.set_index("symbol")
    return rp


class AaveMarketData:
    """
    Stand-in for the aave ``market.data`` frame (columns are a (token, column) MultiIndex).

    The engine reads rows natively. ``data.index``, ``len(data)``, ``(token, column) in data`` and
    ``data.columns`` don't build a DataFrame; any other pandas usage (``data["WETH"]``,
    ``data.iloc[0]``, ``data.loc[...]``) builds it once and caches it. Use ``to_pandas()`` for a
    real DataFrame. Writing into that frame does not change the market: assign a new frame to
    ``market.data`` instead.
    """

    __slots__ = ("_handle", "_df")

    def __init__(self, handle):
        object.__setattr__(self, "_handle", handle)
        object.__setattr__(self, "_df", None)

    @property
    def handle(self):
        return self._handle

    def to_pandas(self) -> pd.DataFrame:
        if self._df is None:
            df = ipc_to_pandas(self._handle.to_ipc())
            df.columns = pd.MultiIndex.from_tuples([tuple(c.split("|", 1)) for c in df.columns])
            object.__setattr__(self, "_df", df)
        return self._df

    def __len__(self):
        return len(self._handle)

    @property
    def index(self):
        return pd.DatetimeIndex(pd.to_datetime(self._handle.timestamps(), unit="s"))

    @property
    def columns(self):
        tuples = [(t, c) for t in self._handle.tokens() for c in REQUIRED_DATA_COLUMN if self._handle.has_column(t, c)]
        return pd.MultiIndex.from_tuples(tuples) if tuples else pd.MultiIndex.from_tuples([], names=[None, None])

    @property
    def shape(self):
        return len(self), len(self.columns)

    def __contains__(self, key):
        if isinstance(key, tuple) and len(key) == 2:
            return self._handle.has_column(str(key[0]), str(key[1]))
        return isinstance(key, str) and self._handle.has_token(key)

    def __iter__(self):
        return iter(self.columns)

    def __getitem__(self, key):
        return self.to_pandas()[key]

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return getattr(object.__getattribute__(self, "to_pandas")(), name)

    def __copy__(self):
        return AaveMarketData(self._handle.copy())

    def __deepcopy__(self, memo):
        return AaveMarketData(self._handle.copy())

    def __reduce__(self):
        return (_aave_data_from_ipc, (bytes(self._handle.to_ipc()),))

    def __repr__(self):
        return f"AaveMarketData(rows={len(self)}, tokens={self._handle.tokens()})"


def _aave_data_from_ipc(buf: bytes) -> AaveMarketData:
    return AaveMarketData(_rs.AaveDataHandle.from_ipc(buf))


def frame_to_handle(df: pd.DataFrame):
    """(token, column) MultiIndex DataFrame -> engine data handle"""
    flat = df.copy(deep=False)
    flat.columns = [f"{str(c[0]).upper()}|{c[1]}" if isinstance(c, tuple) else str(c) for c in df.columns]
    return _rs.AaveDataHandle.from_ipc(pandas_to_ipc(flat))


def load_aave_data(chain: ChainType, token_info_list: List[TokenInfo], start_date: date, end_date: date, data_path: str):
    """
    Load data from folder set in data_path. Those data file should be downloaded by demeter, and meet name rule. [chain]-aave_v3-[token_contract_address]-[date].minute.csv

    :param chain: chain type
    :type chain: ChainType
    :param token_info_list: tokens to load
    :type token_info_list: List[TokenInfo]
    :param start_date: start day
    :type start_date: date
    :param end_date: end day, the end day will be included
    :type end_date: date
    :param data_path: path to load data
    :type data_path: str
    :return: market data (see :class:`AaveMarketData`), to assign to ``market.data``
    """
    logger = logging.getLogger("Aave data")
    logger.info(f"{MarketTypeEnum.aave_v3.name} start load files from {start_date} to {end_date}...")
    chain_name = chain.name if hasattr(chain, "name") else str(chain)
    handle = _rs.AaveDataHandle.load(chain_name, [(t.name, t.decimal, t.address) for t in token_info_list], start_date, end_date, str(data_path))
    logger.info("data has been prepared")
    return AaveMarketData(handle)
