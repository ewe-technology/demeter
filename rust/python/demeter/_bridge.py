"""
Glue between the Rust engine (``demeter._rs``) and the pandas based public API.

Data crosses the boundary as Arrow IPC bytes (written by polars in Rust, read by pyarrow here),
so no pyo3-polars / version coupling is needed.
"""

import calendar
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

import pandas as pd
import pyarrow as pa

from . import _rs


# ------------------------------------------------------------------ time


def to_ts(t: Any) -> int:
    """datetime / date / pandas Timestamp -> seconds since epoch (naive, like pandas)."""
    if isinstance(t, pd.Timestamp):
        t = t.to_pydatetime()
    if isinstance(t, datetime):
        return calendar.timegm(t.timetuple())
    if isinstance(t, date):
        return calendar.timegm(datetime(t.year, t.month, t.day).timetuple())
    if isinstance(t, int):
        return t
    raise TypeError(f"expected a datetime, got {type(t)}")


def interval_to_seconds(interval: str) -> int:
    if not interval[0].isdigit():
        interval = "1" + interval
    return int(pd.Timedelta(interval).total_seconds())


# ------------------------------------------------------------------ arrow <-> pandas


def ipc_to_pandas(buf: bytes, index: str = "timestamp") -> pd.DataFrame:
    table = pa.ipc.open_file(pa.py_buffer(buf)).read_all()
    df = table.to_pandas()
    if index in df.columns:
        df[index] = pd.to_datetime(df[index]).astype("datetime64[ns]")
        df = df.set_index(index)
        df.index.name = None
        df.index.freq = None
    return df


def _index_ms(index) -> pa.Array:
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert(None)
    return pa.array(idx.values.astype("datetime64[ms]"))


def _column_to_arrow(s: pd.Series) -> pa.Array:
    if s.dtype == object:
        out = []
        for v in s.tolist():
            if v is None or (isinstance(v, float) and math.isnan(v)):
                out.append(None)
            else:
                out.append(str(v))
        return pa.array(out, type=pa.string())
    if pd.api.types.is_bool_dtype(s.dtype):
        return pa.array(s.to_numpy(dtype=bool))
    if pd.api.types.is_integer_dtype(s.dtype):
        return pa.array(s.to_numpy(dtype="int64"))
    if pd.api.types.is_float_dtype(s.dtype):
        return pa.array(s.to_numpy(dtype="float64"))
    return pa.array([None if pd.isna(v) else str(v) for v in s.tolist()], type=pa.string())


def pandas_to_ipc(df: pd.DataFrame) -> bytes:
    cols = {"timestamp": _index_ms(df.index)}
    for c in df.columns:
        cols[str(c)] = _column_to_arrow(df[c])
    table = pa.table(cols)
    sink = pa.BufferOutputStream()
    with pa.ipc.new_file(sink, table.schema) as w:
        w.write_table(table)
    return sink.getvalue().to_pybytes()


def column_kind(s: pd.Series) -> tuple[str, list]:
    """(kind, values) for MarketCore.add_column"""
    if pd.api.types.is_bool_dtype(s.dtype):
        return "bool", [None if pd.isna(v) else bool(v) for v in s.tolist()]
    if pd.api.types.is_integer_dtype(s.dtype):
        return "i64", s.tolist()
    if pd.api.types.is_float_dtype(s.dtype):
        return "f64", s.tolist()
    values = s.tolist()
    first = next((v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))), None)
    if isinstance(first, (Decimal, int)) and not isinstance(first, bool):
        return "dec", values
    if isinstance(first, float):
        return "f64", [float("nan") if v is None else v for v in values]
    return "str", values


def series_timestamps(s: pd.Series) -> list[int]:
    idx = pd.DatetimeIndex(s.index)
    if idx.tz is not None:
        idx = idx.tz_convert(None)
    return (idx.values.astype("datetime64[s]").astype("int64")).tolist()


def account_status_from_ipc(buf: bytes) -> pd.DataFrame:
    df = ipc_to_pandas(buf)
    df.columns = pd.MultiIndex.from_tuples([tuple(c.split("|", 1)) for c in df.columns], names=["l1", "l2"])
    return df


# ------------------------------------------------------------------ market data proxy

_RS_COLUMN = "_demeter_rs_column"

# Engine objects are not picklable, and pandas deep-copies `attrs`, so frames only carry an
# integer token pointing into this small registry (most recent entries kept).
_SOURCES: "dict[int, object]" = {}
_SOURCES_MAX = 256
_next_token = [0]


def register_source(obj) -> int:
    _next_token[0] += 1
    _SOURCES[_next_token[0]] = obj
    while len(_SOURCES) > _SOURCES_MAX:
        _SOURCES.pop(next(iter(_SOURCES)))
    return _next_token[0]


def lookup_source(token):
    return _SOURCES.get(token)


class MarketData:
    """
    Stand-in for the pandas ``market.data`` frame.

    Row access during the backtest never goes through pandas. Column access (``data["price"]`` or
    ``data.price``) returns a pandas Series built from just that column. Any other pandas usage
    (``data.loc[...]``, ``data.head()``) materializes the full frame once and caches it.
    ``copy.deepcopy`` is cheap (copy on write).
    """

    __slots__ = ("_handle", "_market", "_df", "_df_ptr")

    def __init__(self, handle, market=None):
        object.__setattr__(self, "_handle", handle)
        object.__setattr__(self, "_market", market)  # bound UniLpMarket, writes go through it
        object.__setattr__(self, "_df", None)
        object.__setattr__(self, "_df_ptr", None)

    # -- core access
    @property
    def handle(self):
        if self._market is not None:
            return self._market._core.get_data()
        return self._handle

    def to_pandas(self) -> pd.DataFrame:
        """
        The data as a pandas DataFrame (built once per data version and cached).

        Note: this is a copy. Writing into it (``df.loc[...] = x``) does not change what the
        engine uses; use ``market.data[name] = series`` or ``market.data = new_frame`` instead.
        """
        handle = self.handle
        if self._df is None or self._df_ptr != handle.ptr():
            object.__setattr__(self, "_df", ipc_to_pandas(handle.to_ipc()))
            object.__setattr__(self, "_df_ptr", handle.ptr())
        return self._df

    def _column(self, name: str) -> pd.Series:
        return ipc_to_pandas(self.handle.column_ipc(name))[name]

    # -- pandas-like surface
    def __len__(self):
        return len(self.handle)

    @property
    def columns(self):
        return pd.Index(self.handle.columns())

    @property
    def index(self):
        return pd.DatetimeIndex(pd.to_datetime(self.handle.timestamps(), unit="s"))

    @property
    def shape(self):
        return len(self), len(self.handle.columns())

    def __getitem__(self, key):
        if isinstance(key, str) and self.handle.has_column(key):
            return self._column(key)
        return self.to_pandas()[key]

    def __setitem__(self, name, value):
        if not isinstance(value, pd.Series):
            value = pd.Series(value, index=self.index)
        kind, values = column_kind(value)
        if self._market is not None:
            self._market._core.add_column(name, kind, series_timestamps(value), values)
            self._market._refresh_data_handle()
        else:
            object.__setattr__(self, "_handle", self._handle.with_column(name, kind, series_timestamps(value), values))
        object.__setattr__(self, "_df", None)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        handle = object.__getattribute__(self, "handle")
        if handle.has_column(name):
            return object.__getattribute__(self, "_column")(name)
        return getattr(object.__getattribute__(self, "to_pandas")(), name)

    def __iter__(self):
        return iter(self.columns)

    def __contains__(self, item):
        return self.handle.has_column(item)

    def __copy__(self):
        return MarketData(self.handle.copy())

    def __deepcopy__(self, memo):
        return MarketData(self.handle.copy())

    def __reduce__(self):
        # picklable (e.g. BacktestManager with processes): data travels as Arrow IPC bytes.
        # Uses the python-side handle: pickling may happen on a multiprocessing helper thread.
        handle = self._market.__dict__.get("_data_handle") if self._market is not None else self._handle
        return (_market_data_from_ipc, (bytes(handle.to_ipc()),))

    def __repr__(self):
        return f"MarketData(rows={len(self)}, columns={list(self.columns)})"


def _market_data_from_ipc(buf: bytes) -> "MarketData":
    return MarketData(_rs.DataHandle.from_ipc(buf))


def rs_column_source(s: pd.Series):
    """If `s` is an untouched column taken from a MarketData, return (handle, column)."""
    tag = s.attrs.get(_RS_COLUMN) if hasattr(s, "attrs") else None
    if tag and len(tag) == 4 and tag[2] == id(s) and len(s) == tag[3]:
        handle = lookup_source(tag[0])
        if handle is not None:
            return handle, tag[1]
    return None


def is_rs_column(values: Iterable) -> bool:
    return isinstance(values, pd.Series) and rs_column_source(values) is not None


_rs  # re-export for convenience
