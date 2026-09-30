//! `MarketCore` (the Rust side of python `UniLpMarket`) and `DataHandle` (market data).

use crate::conv::*;
use crate::snapshot::BarView;
use demeter_core::broker::{shared, Shared};
use demeter_core::data::{self, ExtraColumn, UniData};
use demeter_core::dec::Dec;
use demeter_core::types::{MarketInfo, MarketType, PositionInfo, TokenInfo, Ts, UniV3Pool};
use demeter_core::uniswap::UniLpMarket;
use pyo3::exceptions::{PyKeyError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyList, PyTuple};
use std::sync::Arc;

fn to_market_type(v: i64) -> MarketType {
    if v == 0 {
        MarketType::Broker
    } else {
        MarketType::UniswapV3
    }
}

/// Build an extra column from python values aligned to `rows` (None = missing).
pub fn extra_from_values(
    kind: &str,
    values: &Bound<'_, PyList>,
    rows: &[Option<usize>],
) -> PyResult<ExtraColumn> {
    let get = |i: Option<usize>| -> Option<Bound<'_, PyAny>> {
        i.and_then(|i| values.get_item(i).ok())
            .filter(|v| !v.is_none())
    };
    Ok(match kind {
        "dec" => ExtraColumn::Dec(
            rows.iter()
                .map(|r| get(*r).map(|v| dec_from_py(&v)).transpose())
                .collect::<PyResult<Vec<_>>>()?,
        ),
        "f64" => ExtraColumn::F64(
            rows.iter()
                .map(|r| {
                    get(*r)
                        .map(|v| v.extract::<f64>())
                        .transpose()
                        .map(|x| x.unwrap_or(f64::NAN))
                })
                .collect::<PyResult<Vec<_>>>()?,
        ),
        "i64" => ExtraColumn::I64(
            rows.iter()
                .map(|r| get(*r).map(|v| v.extract::<i64>()).transpose())
                .collect::<PyResult<Vec<_>>>()?,
        ),
        "bool" => ExtraColumn::Bool(
            rows.iter()
                .map(|r| get(*r).map(|v| v.is_truthy()).transpose())
                .collect::<PyResult<Vec<_>>>()?,
        ),
        _ => ExtraColumn::Str(
            rows.iter()
                .map(|r| get(*r).map(|v| v.str().map(|s| s.to_string())).transpose())
                .collect::<PyResult<Vec<_>>>()?,
        ),
    })
}

fn ipc_bytes<'py>(
    py: Python<'py>,
    mut df: polars::prelude::DataFrame,
) -> PyResult<Bound<'py, PyBytes>> {
    let b = data::frame_to_ipc(&mut df).py()?;
    Ok(PyBytes::new(py, &b))
}

/// Immutable snapshot of market data (cheap to copy: copy-on-write).
#[pyclass(name = "DataHandle", module = "demeter._rs", skip_from_py_object)]
#[derive(Clone)]
pub struct PyDataHandle {
    pub data: Arc<UniData>,
}

#[pymethods]
impl PyDataHandle {
    fn __len__(&self) -> usize {
        self.data.len()
    }
    /// whole table as Arrow IPC bytes
    fn to_ipc<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        ipc_bytes(py, self.data.to_polars().py()?)
    }
    /// `[timestamp, name]` as Arrow IPC bytes
    fn column_ipc<'py>(&self, py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyBytes>> {
        ipc_bytes(py, self.data.column_frame(name).py()?)
    }
    fn columns(&self) -> Vec<String> {
        self.data.column_names()
    }
    fn has_column(&self, name: &str) -> bool {
        self.data.column_names().iter().any(|c| c == name)
    }
    /// timestamps in seconds since the epoch
    fn timestamps(&self) -> Vec<i64> {
        self.data.ts.clone()
    }
    /// identity of the underlying table (equal for handles sharing the same data)
    fn ptr(&self) -> usize {
        Arc::as_ptr(&self.data) as usize
    }
    fn copy(&self) -> PyDataHandle {
        self.clone()
    }
    fn __copy__(&self) -> PyDataHandle {
        self.clone()
    }
    fn __deepcopy__(&self, _memo: &Bound<'_, PyAny>) -> PyDataHandle {
        self.clone()
    }
    /// python `_add_statistic_column(df, pool)` on a copy; returns the new handle.
    fn with_statistics(&self, market: &PyMarketCore) -> PyResult<PyDataHandle> {
        let mut d = (*self.data).clone();
        d.add_statistic_columns(&market.inner.borrow().pool).py()?;
        Ok(PyDataHandle { data: Arc::new(d) })
    }
    /// set a user column from values indexed by `timestamps` (seconds); returns a new handle
    fn with_column(
        &self,
        name: &str,
        kind: &str,
        timestamps: Vec<i64>,
        values: &Bound<'_, PyList>,
    ) -> PyResult<PyDataHandle> {
        let rows = self.data.align_rows(&timestamps);
        let col = extra_from_values(kind, values, &rows)?;
        let mut d = (*self.data).clone();
        d.set_extra(name, col).py()?;
        Ok(PyDataHandle { data: Arc::new(d) })
    }
    /// read a frame produced from pandas (Arrow IPC bytes)
    #[staticmethod]
    #[pyo3(signature = (ipc, market=None))]
    fn from_ipc(ipc: &[u8], market: Option<&PyMarketCore>) -> PyResult<PyDataHandle> {
        let df = data::frame_from_ipc(ipc).py()?;
        let pool = market.map(|m| m.inner.borrow().pool.clone());
        Ok(PyDataHandle {
            data: Arc::new(UniData::from_polars(&df, pool.as_ref()).py()?),
        })
    }
}

#[pyclass(name = "MarketCore", unsendable, module = "demeter._rs")]
pub struct PyMarketCore {
    pub inner: Shared<UniLpMarket>,
}

fn pos(lower: i32, upper: i32) -> PositionInfo {
    PositionInfo {
        lower_tick: lower,
        upper_tick: upper,
    }
}

#[pymethods]
impl PyMarketCore {
    #[new]
    #[pyo3(signature = (name, market_type, token0, token1, fee_percent, quote_name, tick_spacing=None))]
    fn new(
        name: &str,
        market_type: i64,
        token0: (String, u32),
        token1: (String, u32),
        fee_percent: &Bound<'_, PyAny>,
        quote_name: &str,
        tick_spacing: Option<i32>,
    ) -> PyResult<Self> {
        let t0 = TokenInfo::new(&token0.0, token0.1);
        let t1 = TokenInfo::new(&token1.0, token1.1);
        let quote = if t0.name == quote_name.to_uppercase() {
            t0.clone()
        } else {
            t1.clone()
        };
        let pool = UniV3Pool::new(t0, t1, dec_from_py(fee_percent)?, quote, tick_spacing);
        let info = MarketInfo {
            name: name.to_string(),
            kind: to_market_type(market_type),
        };
        Ok(PyMarketCore {
            inner: shared(UniLpMarket::new(info, pool)),
        })
    }

    // ------------------------------------------------ properties
    #[getter]
    fn tick_spacing(&self) -> i32 {
        self.inner.borrow().pool.tick_spacing
    }
    #[getter]
    fn is_token0_quote(&self) -> bool {
        self.inner.borrow().pool.is_token0_quote
    }
    #[getter]
    fn has_update(&self) -> bool {
        self.inner.borrow().has_update
    }
    #[setter]
    fn set_has_update(&self, v: bool) {
        self.inner.borrow_mut().has_update = v;
    }
    #[getter]
    fn is_open(&self) -> bool {
        self.inner.borrow().is_open
    }
    #[getter]
    fn legacy_quirks(&self) -> bool {
        self.inner.borrow().compat.legacy_quirks
    }
    #[setter]
    fn set_legacy_quirks(&self, v: bool) {
        self.inner.borrow_mut().compat.legacy_quirks = v;
    }
    #[getter]
    fn last_tick(&self) -> Option<i32> {
        self.inner.borrow().last_tick
    }
    #[setter]
    fn set_last_tick(&self, v: Option<&Bound<'_, PyAny>>) -> PyResult<()> {
        self.inner.borrow_mut().last_tick = match v {
            Some(x) if !x.is_none() => Some(tick_from_py(x)?),
            _ => None,
        };
        Ok(())
    }

    // ------------------------------------------------ data
    fn load_data(
        &self,
        chain: &str,
        contract_addr: &str,
        start: chrono::NaiveDate,
        end: chrono::NaiveDate,
        data_path: &str,
    ) -> PyResult<()> {
        let mut m = self.inner.borrow_mut();
        m.data_path = data_path.to_string();
        m.load_data(chain, contract_addr, start, end).py()
    }
    fn has_data(&self) -> bool {
        self.inner.borrow().data.is_some()
    }
    fn get_data(&self) -> PyResult<PyDataHandle> {
        Ok(PyDataHandle {
            data: self.inner.borrow().data().py()?.clone(),
        })
    }
    fn set_data(&self, handle: &PyDataHandle) {
        self.inner.borrow_mut().set_data(handle.data.clone());
    }
    /// python `add_column`: values indexed by `timestamps` are aligned to the market rows
    fn add_column(
        &self,
        name: &str,
        kind: &str,
        timestamps: Vec<i64>,
        values: &Bound<'_, PyList>,
    ) -> PyResult<()> {
        let mut m = self.inner.borrow_mut();
        let rows = m.data().py()?.align_rows(&timestamps);
        let col = extra_from_values(kind, values, &rows)?;
        m.data_mut().py()?.set_extra(name, col).py()
    }
    /// fast path of `add_column` when the series came from another market's data
    fn add_column_from(
        &self,
        name: &str,
        source: &PyDataHandle,
        source_column: &str,
    ) -> PyResult<()> {
        let mut m = self.inner.borrow_mut();
        let rows = m.data().py()?.align_rows(&source.data.ts);
        let src = &source.data;
        let col = match src.extra(source_column) {
            Some(c) => take_aligned(c, &rows),
            None => {
                let vals: Vec<Option<Dec>> = match source_column {
                    "price" => src.bars.iter().map(|b| Some(b.price)).collect(),
                    "close" => src.bars.iter().map(|b| Some(b.close)).collect(),
                    "volume0" => src.bars.iter().map(|b| Some(b.volume0)).collect(),
                    "volume1" => src.bars.iter().map(|b| Some(b.volume1)).collect(),
                    _ => return Err(PyKeyError::new_err(source_column.to_string())),
                };
                ExtraColumn::Dec(rows.iter().map(|r| r.and_then(|i| vals[i])).collect())
            }
        };
        m.data_mut().py()?.set_extra(name, col).py()
    }
    fn resample(&self, interval_secs: i64) -> PyResult<()> {
        self.inner.borrow_mut().resample(interval_secs).py()
    }
    /// (timestamps, base price column, token names) for `get_price_from_data`
    fn price_ipc<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        let m = self.inner.borrow();
        let d = m.data().py()?;
        let (names, cols) = data::price_from_data(d, &m.pool);
        let df = price_frame(&d.ts, &names, &cols)?;
        ipc_bytes(py, df)
    }

    // ------------------------------------------------ status
    fn set_market_status(&self, ts: &Bound<'_, PyAny>) -> PyResult<()> {
        let ts = ts_from_py(ts)?;
        self.inner.borrow_mut().set_market_status(ts).py()
    }
    /// set the status from explicit values (python `set_market_status` with `data` given)
    #[pyo3(signature = (ts, price, close_tick, current_liquidity, in_amount0, in_amount1, open_tick=None, lowest_tick=None, highest_tick=None, net_amount0=None, net_amount1=None))]
    #[allow(clippy::too_many_arguments)]
    fn set_market_status_bar(
        &self,
        ts: i64,
        price: &Bound<'_, PyAny>,
        close_tick: &Bound<'_, PyAny>,
        current_liquidity: &Bound<'_, PyAny>,
        in_amount0: &Bound<'_, PyAny>,
        in_amount1: &Bound<'_, PyAny>,
        open_tick: Option<&Bound<'_, PyAny>>,
        lowest_tick: Option<&Bound<'_, PyAny>>,
        highest_tick: Option<&Bound<'_, PyAny>>,
        net_amount0: Option<&Bound<'_, PyAny>>,
        net_amount1: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<()> {
        let ct = tick_from_py(close_tick)?;
        let opt_tick = |v: Option<&Bound<'_, PyAny>>| -> PyResult<i32> {
            match v {
                Some(x) if !x.is_none() => tick_from_py(x),
                _ => Ok(ct),
            }
        };
        let int = |v: &Bound<'_, PyAny>| -> PyResult<i128> {
            Ok(demeter_core::dec::trunc_to_i128(&dec_from_py(v)?))
        };
        let opt_int = |v: Option<&Bound<'_, PyAny>>| -> PyResult<i128> {
            match v {
                Some(x) if !x.is_none() => int(x),
                _ => Ok(0),
            }
        };
        let m = self.inner.borrow();
        let (d0_, d1_) = (m.pool.token0.decimal, m.pool.token1.decimal);
        drop(m);
        let in0 = int(in_amount0)?;
        let in1 = int(in_amount1)?;
        let p = dec_from_py(price)?;
        let bar = demeter_core::data::Bar {
            net_amount0: opt_int(net_amount0)?,
            net_amount1: opt_int(net_amount1)?,
            close_tick: ct,
            open_tick: opt_tick(open_tick)?,
            lowest_tick: opt_tick(lowest_tick)?,
            highest_tick: opt_tick(highest_tick)?,
            in_amount0: in0,
            in_amount1: in1,
            current_liquidity: u128_from_py(current_liquidity)?,
            close: p,
            price: p,
            volume0: demeter_core::math::from_atomic_unit(in0, d0_),
            volume1: demeter_core::math::from_atomic_unit(in1, d1_),
        };
        self.inner.borrow_mut().set_market_status_bar(ts, bar).py()
    }
    fn status_timestamp(&self) -> Option<Ts> {
        self.inner.borrow().status.as_ref().map(|s| s.ts)
    }
    fn status_bar(&self) -> PyResult<Option<BarView>> {
        let m = self.inner.borrow();
        Ok(m.status.as_ref().map(|s| BarView {
            market: self.inner.clone(),
            bar: s.bar.clone(),
            ts: s.ts,
            row: s.row,
        }))
    }
    fn price<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        dec_to_py(py, &self.inner.borrow().price().py()?)
    }
    fn update(&self) -> PyResult<()> {
        self.inner.borrow_mut().update().py()
    }
    fn check_market(&self) -> PyResult<()> {
        self.inner.borrow().check_market().py()
    }

    // ------------------------------------------------ positions
    fn position_keys(&self) -> Vec<(i32, i32)> {
        self.inner
            .borrow()
            .positions
            .iter()
            .map(|(k, _)| (k.lower_tick, k.upper_tick))
            .collect()
    }
    fn position_count(&self) -> usize {
        self.inner.borrow().positions.len()
    }
    /// remove a position entry (python dict pop semantics: nothing goes back to the broker)
    fn drop_position(&self, lower: i32, upper: i32) -> bool {
        self.inner
            .borrow_mut()
            .drop_position(&pos(lower, upper))
            .is_some()
    }
    fn has_position(&self, lower: i32, upper: i32) -> bool {
        self.inner
            .borrow()
            .position_index(&pos(lower, upper))
            .is_some()
    }
    /// (pending_amount0, pending_amount1, liquidity, lower_price, upper_price, init_price, transferred)
    fn position<'py>(
        &self,
        py: Python<'py>,
        lower: i32,
        upper: i32,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let m = self.inner.borrow();
        let p = m.get_position(&pos(lower, upper)).py()?;
        PyTuple::new(
            py,
            [
                dec_to_py(py, &p.pending_amount0)?,
                dec_to_py(py, &p.pending_amount1)?,
                p.liquidity.into_pyobject(py)?.into_any(),
                dec_to_py(py, &p.lower_price)?,
                dec_to_py(py, &p.upper_price)?,
                dec_to_py(py, &p.init_price)?,
                pyo3::types::PyBool::new(py, p.transferred)
                    .to_owned()
                    .into_any(),
            ],
        )
    }
    fn set_position_field(
        &self,
        lower: i32,
        upper: i32,
        field: &str,
        value: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let mut m = self.inner.borrow_mut();
        let p = m.get_position_mut(&pos(lower, upper)).py()?;
        match field {
            "pending_amount0" => p.pending_amount0 = dec_from_py(value)?,
            "pending_amount1" => p.pending_amount1 = dec_from_py(value)?,
            "liquidity" => p.liquidity = u128_from_py(value)?,
            "lower_price" => p.lower_price = dec_from_py(value)?,
            "upper_price" => p.upper_price = dec_from_py(value)?,
            "init_price" => p.init_price = dec_from_py(value)?,
            "transferred" => p.transferred = value.is_truthy()?,
            _ => {
                return Err(PyValueError::new_err(format!(
                    "unknown position field {field}"
                )))
            }
        }
        Ok(())
    }
    fn get_position_status<'py>(
        &self,
        py: Python<'py>,
        lower: i32,
        upper: i32,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let s = self
            .inner
            .borrow()
            .get_position_status(&pos(lower, upper))
            .py()?;
        let mut v = vec![s.liquidity.into_pyobject(py)?.into_any()];
        for d in [
            &s.liquidity_amount0,
            &s.liquidity_amount1,
            &s.liquidity_value,
            &s.pending_amount0,
            &s.pending_amount1,
            &s.pending_value,
            &s.amount0,
            &s.amount1,
            &s.value,
            &s.h,
            &s.l,
            &s.p,
        ] {
            v.push(dec_to_py(py, d)?);
        }
        PyTuple::new(py, v)
    }
    fn get_position_amount<'py>(
        &self,
        py: Python<'py>,
        lower: i32,
        upper: i32,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
        let (a, b) = self
            .inner
            .borrow()
            .get_position_amount(&pos(lower, upper))
            .py()?;
        Ok((dec_to_py(py, &a)?, dec_to_py(py, &b)?))
    }
    /// (net_value, liquidity_value, base_uncollected, quote_uncollected, base_in_position, quote_in_position, position_count)
    fn get_market_balance<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        let b = self.inner.borrow().get_market_balance().py()?;
        balance_tuple(py, &b)
    }
    fn transfer_position_out(&self, lower: i32, upper: i32) -> PyResult<()> {
        self.inner
            .borrow_mut()
            .transfer_position_out(&pos(lower, upper))
            .py()
    }
    fn transfer_position_in(&self, lower: i32, upper: i32) -> PyResult<()> {
        self.inner
            .borrow_mut()
            .transfer_position_in(&pos(lower, upper))
            .py()
    }

    // ------------------------------------------------ price / tick
    fn tick_to_price<'py>(
        &self,
        py: Python<'py>,
        tick: &Bound<'_, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        dec_to_py(
            py,
            &self
                .inner
                .borrow()
                .tick_to_price(tick_from_py(tick)?)
                .py()?,
        )
    }
    fn price_to_tick(&self, price: &Bound<'_, PyAny>) -> PyResult<i32> {
        Ok(self.inner.borrow().price_to_tick(&dec_from_py(price)?))
    }
    fn price_to_raw_tick(&self, price: &Bound<'_, PyAny>) -> PyResult<i32> {
        Ok(self.inner.borrow().price_to_raw_tick(&dec_from_py(price)?))
    }

    // ------------------------------------------------ liquidity
    #[pyo3(signature = (lower_quote_price, upper_quote_price, quote_max_amount=None, base_max_amount=None))]
    fn add_liquidity<'py>(
        &self,
        py: Python<'py>,
        lower_quote_price: &Bound<'_, PyAny>,
        upper_quote_price: &Bound<'_, PyAny>,
        quote_max_amount: Option<&Bound<'_, PyAny>>,
        base_max_amount: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let r = self
            .inner
            .borrow_mut()
            .add_liquidity(
                dec_from_py(lower_quote_price)?,
                dec_from_py(upper_quote_price)?,
                opt_dec(quote_max_amount)?,
                opt_dec(base_max_amount)?,
            )
            .py()?;
        add_result(py, r)
    }
    #[pyo3(signature = (lower_tick, upper_tick, base_max_amount=None, quote_max_amount=None, sqrt_price_x96=None, tick=None, trim_tick=true))]
    #[allow(clippy::too_many_arguments)]
    fn add_liquidity_by_tick<'py>(
        &self,
        py: Python<'py>,
        lower_tick: &Bound<'_, PyAny>,
        upper_tick: &Bound<'_, PyAny>,
        base_max_amount: Option<&Bound<'_, PyAny>>,
        quote_max_amount: Option<&Bound<'_, PyAny>>,
        sqrt_price_x96: Option<&Bound<'_, PyAny>>,
        tick: Option<&Bound<'_, PyAny>>,
        trim_tick: bool,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let tick = match tick {
            Some(t) if !t.is_none() => Some(tick_from_py(t)?),
            _ => None,
        };
        let r = self
            .inner
            .borrow_mut()
            .add_liquidity_by_tick(
                tick_from_py(lower_tick)?,
                tick_from_py(upper_tick)?,
                opt_dec(base_max_amount)?,
                opt_dec(quote_max_amount)?,
                opt_u256(sqrt_price_x96)?,
                tick,
                trim_tick,
            )
            .py()?;
        add_result(py, r)
    }
    /// python `_add_liquidity_by_tick(token0_amount, token1_amount, lower_tick, upper_tick, sqrt_price_x96)`
    #[pyo3(signature = (token0_amount, token1_amount, lower_tick, upper_tick, sqrt_price_x96=None))]
    fn add_liquidity_by_tick_raw<'py>(
        &self,
        py: Python<'py>,
        token0_amount: &Bound<'_, PyAny>,
        token1_amount: &Bound<'_, PyAny>,
        lower_tick: &Bound<'_, PyAny>,
        upper_tick: &Bound<'_, PyAny>,
        sqrt_price_x96: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let r = self
            .inner
            .borrow_mut()
            .add_liquidity_by_tick_raw(
                dec_from_py(token0_amount)?,
                dec_from_py(token1_amount)?,
                tick_from_py(lower_tick)?,
                tick_from_py(upper_tick)?,
                opt_u256(sqrt_price_x96)?,
            )
            .py()?;
        add_result(py, r)
    }
    #[pyo3(signature = (lower, upper, liquidity=None, collect=true, sqrt_price_x96=None, remove_dry_pool=true))]
    #[allow(clippy::too_many_arguments)]
    fn remove_liquidity<'py>(
        &self,
        py: Python<'py>,
        lower: i32,
        upper: i32,
        liquidity: Option<&Bound<'_, PyAny>>,
        collect: bool,
        sqrt_price_x96: Option<&Bound<'_, PyAny>>,
        remove_dry_pool: bool,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
        let (a, b) = self
            .inner
            .borrow_mut()
            .remove_liquidity(
                &pos(lower, upper),
                opt_u128(liquidity)?,
                collect,
                opt_u256(sqrt_price_x96)?,
                remove_dry_pool,
            )
            .py()?;
        Ok((dec_to_py(py, &a)?, dec_to_py(py, &b)?))
    }
    #[pyo3(signature = (lower, upper, max_collect_amount0=None, max_collect_amount1=None, remove_dry_pool=true, collect_to_user=true))]
    #[allow(clippy::too_many_arguments)]
    fn collect_fee<'py>(
        &self,
        py: Python<'py>,
        lower: i32,
        upper: i32,
        max_collect_amount0: Option<&Bound<'_, PyAny>>,
        max_collect_amount1: Option<&Bound<'_, PyAny>>,
        remove_dry_pool: bool,
        collect_to_user: bool,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
        let (a, b) = self
            .inner
            .borrow_mut()
            .collect_fee(
                &pos(lower, upper),
                opt_dec(max_collect_amount0)?,
                opt_dec(max_collect_amount1)?,
                remove_dry_pool,
                collect_to_user,
            )
            .py()?;
        Ok((dec_to_py(py, &a)?, dec_to_py(py, &b)?))
    }
    fn remove_all_liquidity(&self) -> PyResult<()> {
        self.inner.borrow_mut().remove_all_liquidity().py()
    }

    // ------------------------------------------------ swaps
    #[pyo3(signature = (from_amount, from_token, to_token, price=None, throw_action=true))]
    fn swap<'py>(
        &self,
        py: Python<'py>,
        from_amount: &Bound<'_, PyAny>,
        from_token: &str,
        to_token: &str,
        price: Option<&Bound<'_, PyAny>>,
        throw_action: bool,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
        let (from, to) = {
            let m = self.inner.borrow();
            let find = |n: &str| -> TokenInfo {
                let n = n.to_uppercase();
                if m.pool.token0.name == n {
                    m.pool.token0.clone()
                } else if m.pool.token1.name == n {
                    m.pool.token1.clone()
                } else {
                    TokenInfo::new(&n, 0)
                }
            };
            (find(from_token), find(to_token))
        };
        let (a, b) = self
            .inner
            .borrow_mut()
            .swap(
                dec_from_py(from_amount)?,
                &from,
                &to,
                opt_dec(price)?,
                throw_action,
            )
            .py()?;
        Ok((dec_to_py(py, &a)?, dec_to_py(py, &b)?))
    }
    #[pyo3(signature = (base_token_amount, price=None))]
    fn buy<'py>(
        &self,
        py: Python<'py>,
        base_token_amount: &Bound<'_, PyAny>,
        price: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let (a, b, c) = self
            .inner
            .borrow_mut()
            .buy(dec_from_py(base_token_amount)?, opt_dec(price)?)
            .py()?;
        PyTuple::new(
            py,
            [dec_to_py(py, &a)?, dec_to_py(py, &b)?, dec_to_py(py, &c)?],
        )
    }
    #[pyo3(signature = (base_token_amount, price=None))]
    fn sell<'py>(
        &self,
        py: Python<'py>,
        base_token_amount: &Bound<'_, PyAny>,
        price: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let (a, b, c) = self
            .inner
            .borrow_mut()
            .sell(dec_from_py(base_token_amount)?, opt_dec(price)?)
            .py()?;
        PyTuple::new(
            py,
            [dec_to_py(py, &a)?, dec_to_py(py, &b)?, dec_to_py(py, &c)?],
        )
    }
    #[pyo3(signature = (price=None))]
    fn even_rebalance(&self, price: Option<&Bound<'_, PyAny>>) -> PyResult<()> {
        self.inner.borrow_mut().even_rebalance(opt_dec(price)?).py()
    }
    #[pyo3(signature = (lower_tick, upper_tick, value_to_use=None, trim_tick=true))]
    fn add_liquidity_by_value<'py>(
        &self,
        py: Python<'py>,
        lower_tick: &Bound<'_, PyAny>,
        upper_tick: &Bound<'_, PyAny>,
        value_to_use: Option<&Bound<'_, PyAny>>,
        trim_tick: bool,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let r = self
            .inner
            .borrow_mut()
            .add_liquidity_by_value(
                tick_from_py(lower_tick)?,
                tick_from_py(upper_tick)?,
                opt_dec(value_to_use)?,
                trim_tick,
            )
            .py()?;
        add_result(py, r)
    }
    fn estimate_liquidity<'py>(
        &self,
        py: Python<'py>,
        value: &Bound<'_, PyAny>,
        lower: i32,
        upper: i32,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let (l, a, b) = self
            .inner
            .borrow()
            .estimate_liquidity(dec_from_py(value)?, &pos(lower, upper))
            .py()?;
        PyTuple::new(
            py,
            [
                l.into_pyobject(py)?.into_any(),
                dec_to_py(py, &a)?,
                dec_to_py(py, &b)?,
            ],
        )
    }
    fn estimate_amount<'py>(
        &self,
        py: Python<'py>,
        value: &Bound<'_, PyAny>,
        lower: i32,
        upper: i32,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
        let (a, b) = self
            .inner
            .borrow()
            .estimate_amount(dec_from_py(value)?, lower, upper)
            .py()?;
        Ok((dec_to_py(py, &a)?, dec_to_py(py, &b)?))
    }
}

fn take_aligned(c: &ExtraColumn, rows: &[Option<usize>]) -> ExtraColumn {
    match c {
        ExtraColumn::Dec(v) => {
            ExtraColumn::Dec(rows.iter().map(|r| r.and_then(|i| v[i])).collect())
        }
        ExtraColumn::F64(v) => ExtraColumn::F64(
            rows.iter()
                .map(|r| r.map(|i| v[i]).unwrap_or(f64::NAN))
                .collect(),
        ),
        ExtraColumn::I64(v) => {
            ExtraColumn::I64(rows.iter().map(|r| r.and_then(|i| v[i])).collect())
        }
        ExtraColumn::Bool(v) => {
            ExtraColumn::Bool(rows.iter().map(|r| r.and_then(|i| v[i])).collect())
        }
        ExtraColumn::Str(v) => {
            ExtraColumn::Str(rows.iter().map(|r| r.and_then(|i| v[i].clone())).collect())
        }
    }
}

fn add_result<'py>(
    py: Python<'py>,
    r: (PositionInfo, Dec, Dec, u128),
) -> PyResult<Bound<'py, PyTuple>> {
    let (p, a, b, l) = r;
    PyTuple::new(
        py,
        [
            p.lower_tick.into_pyobject(py)?.into_any(),
            p.upper_tick.into_pyobject(py)?.into_any(),
            dec_to_py(py, &a)?,
            dec_to_py(py, &b)?,
            l.into_pyobject(py)?.into_any(),
        ],
    )
}

pub fn balance_tuple<'py>(
    py: Python<'py>,
    b: &demeter_core::types::UniLpBalance,
) -> PyResult<Bound<'py, PyTuple>> {
    PyTuple::new(
        py,
        [
            dec_to_py(py, &b.net_value)?,
            dec_to_py(py, &b.liquidity_value)?,
            dec_to_py(py, &b.base_uncollected)?,
            dec_to_py(py, &b.quote_uncollected)?,
            dec_to_py(py, &b.base_in_position)?,
            dec_to_py(py, &b.quote_in_position)?,
            b.position_count.into_pyobject(py)?.into_any(),
        ],
    )
}

/// polars frame `[timestamp, <token>...]` of Decimal prices
pub fn price_frame(
    ts: &[Ts],
    names: &[String],
    values: &[Vec<Dec>],
) -> PyResult<polars::prelude::DataFrame> {
    use polars::prelude::*;
    let ts_ms: Vec<i64> = ts.iter().map(|t| t * 1000).collect();
    let tscol = Series::new("timestamp".into(), ts_ms)
        .cast(&DataType::Datetime(TimeUnit::Milliseconds, None))
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    let mut columns: Vec<Column> = vec![tscol.into()];
    for (n, c) in names.iter().zip(values) {
        let v: Vec<Option<Dec>> = c.iter().map(|x| Some(*x)).collect();
        columns.push(data::decimal_series_pub(n, &v).py()?.into());
    }
    DataFrame::new_infer_height(columns).map_err(|e| PyValueError::new_err(e.to_string()))
}
