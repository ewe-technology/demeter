//! Objects handed to python strategies on every iteration.
//!
//! python demeter passes pandas rows (`pd.Series`) here; building one per minute is the main
//! cost of the old engine. These classes are lazy views with the same attribute / item access.

use crate::conv::*;
use demeter_core::actuator::PriceTable;
use demeter_core::broker::Shared;
use demeter_core::data::{Bar, ExtraColumn};
use demeter_core::dec;
use demeter_core::trigger::TriggerCond;
use demeter_core::types::Ts;
use demeter_core::uniswap::UniLpMarket;
use pyo3::exceptions::{PyAttributeError, PyKeyError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::rc::Rc;

/// A row of market data (python: `snapshot.market_status[key]`, `market.market_status.data`).
#[pyclass(name = "BarView", unsendable, module = "demeter._rs")]
pub struct BarView {
    pub market: Shared<UniLpMarket>,
    pub bar: Bar,
    pub ts: Ts,
    pub row: usize,
}

const BAR_FIELDS: [&str; 13] = [
    "netAmount0",
    "netAmount1",
    "closeTick",
    "openTick",
    "lowestTick",
    "highestTick",
    "inAmount0",
    "inAmount1",
    "currentLiquidity",
    "close",
    "price",
    "volume0",
    "volume1",
];

impl BarView {
    fn value<'py>(&self, py: Python<'py>, name: &str) -> PyResult<Option<Bound<'py, PyAny>>> {
        let b = &self.bar;
        let d = |v: &dec::Dec| dec_to_py(py, v).map(Some);
        // ticks are float64 in the python frame (reindex introduces NaN)
        let t = |v: i32| Ok(Some(pyo3::types::PyFloat::new(py, v as f64).into_any()));
        match name {
            "price" => d(&b.price),
            "close" => d(&b.close),
            "closeTick" => t(b.close_tick),
            "openTick" => t(b.open_tick),
            "lowestTick" => t(b.lowest_tick),
            "highestTick" => t(b.highest_tick),
            "currentLiquidity" => d(&dec::from_u128(b.current_liquidity)),
            "inAmount0" => d(&dec::from_i128(b.in_amount0)),
            "inAmount1" => d(&dec::from_i128(b.in_amount1)),
            "netAmount0" => d(&dec::from_i128(b.net_amount0)),
            "netAmount1" => d(&dec::from_i128(b.net_amount1)),
            "volume0" => d(&b.volume0),
            "volume1" => d(&b.volume1),
            _ => {
                let m = self.market.borrow();
                let Some(data) = m.data.as_ref() else {
                    return Ok(None);
                };
                let Some(col) = data.extra(name) else {
                    return Ok(None);
                };
                if self.row >= col.len() || data.ts.get(self.row) != Some(&self.ts) {
                    return Ok(Some(py.None().into_bound(py)));
                }
                let v: Bound<'py, PyAny> = match col {
                    ExtraColumn::Dec(v) => match &v[self.row] {
                        Some(x) => dec_to_py(py, x)?,
                        None => pyo3::types::PyFloat::new(py, f64::NAN).into_any(),
                    },
                    ExtraColumn::F64(v) => pyo3::types::PyFloat::new(py, v[self.row]).into_any(),
                    ExtraColumn::I64(v) => match v[self.row] {
                        Some(x) => x.into_pyobject(py)?.into_any(),
                        None => pyo3::types::PyFloat::new(py, f64::NAN).into_any(),
                    },
                    ExtraColumn::Bool(v) => match v[self.row] {
                        Some(x) => pyo3::types::PyBool::new(py, x).to_owned().into_any(),
                        None => py.None().into_bound(py),
                    },
                    ExtraColumn::Str(v) => match &v[self.row] {
                        Some(x) => x.into_pyobject(py)?.into_any(),
                        None => py.None().into_bound(py),
                    },
                };
                Ok(Some(v))
            }
        }
    }
}

#[pymethods]
impl BarView {
    fn __getattr__<'py>(&self, py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
        if name == "name" {
            return ts_to_py(py, self.ts);
        }
        self.value(py, name)?.ok_or_else(|| {
            PyAttributeError::new_err(format!("'BarView' object has no attribute '{name}'"))
        })
    }
    fn __getitem__<'py>(&self, py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
        self.value(py, name)?
            .ok_or_else(|| PyKeyError::new_err(name.to_string()))
    }
    fn __contains__(&self, name: &str) -> bool {
        self.keys().iter().any(|k| k == name)
    }
    #[pyo3(signature = (name, default=None))]
    fn get<'py>(
        &self,
        py: Python<'py>,
        name: &str,
        default: Option<Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        Ok(match self.value(py, name)? {
            Some(v) => v,
            None => default.unwrap_or_else(|| py.None().into_bound(py)),
        })
    }
    fn keys(&self) -> Vec<String> {
        let mut v: Vec<String> = BAR_FIELDS.iter().map(|s| s.to_string()).collect();
        if let Some(d) = self.market.borrow().data.as_ref() {
            v.extend(d.extra.iter().map(|(n, _)| n.clone()));
        }
        v
    }
    /// pandas Series compatibility: `row.index`
    #[getter]
    fn index(&self) -> Vec<String> {
        self.keys()
    }
    #[getter]
    fn timestamp<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        ts_to_py(py, self.ts)
    }
    fn to_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let d = PyDict::new(py);
        for k in self.keys() {
            if let Some(v) = self.value(py, &k)? {
                d.set_item(k, v)?;
            }
        }
        Ok(d)
    }
    fn __repr__(&self) -> String {
        format!(
            "BarView({} price={} closeTick={})",
            demeter_core::types::ts_to_string(self.ts),
            dec::to_plain_string(&self.bar.price),
            self.bar.close_tick
        )
    }
}

/// Prices of the current iteration (python: `snapshot.prices`, a pandas row).
#[pyclass(name = "PriceRow", unsendable, module = "demeter._rs")]
pub struct PriceRow {
    pub prices: Rc<PriceTable>,
    pub row: usize,
}

#[pymethods]
impl PriceRow {
    fn __getitem__<'py>(&self, py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
        match self.prices.token_index(name) {
            Some(i) => dec_to_py(py, &self.prices.cols[i][self.row]),
            None => Err(PyKeyError::new_err(name.to_string())),
        }
    }
    fn __getattr__<'py>(&self, py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
        match self.prices.token_index(name) {
            Some(i) => dec_to_py(py, &self.prices.cols[i][self.row]),
            None => Err(PyAttributeError::new_err(name.to_string())),
        }
    }
    fn __contains__(&self, name: &str) -> bool {
        self.prices.token_index(name).is_some()
    }
    fn __len__(&self) -> usize {
        self.prices.tokens.len()
    }
    fn keys(&self) -> Vec<String> {
        self.prices.tokens.clone()
    }
    #[getter]
    fn index(&self) -> Vec<String> {
        self.prices.tokens.clone()
    }
    #[pyo3(signature = (name, default=None))]
    fn get<'py>(
        &self,
        py: Python<'py>,
        name: &str,
        default: Option<Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        match self.prices.token_index(name) {
            Some(i) => dec_to_py(py, &self.prices.cols[i][self.row]),
            None => Ok(default.unwrap_or_else(|| py.None().into_bound(py))),
        }
    }
    fn to_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let d = PyDict::new(py);
        for (i, t) in self.prices.tokens.iter().enumerate() {
            d.set_item(t, dec_to_py(py, &self.prices.cols[i][self.row])?)?;
        }
        Ok(d)
    }
    fn items<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let l = PyList::empty(py);
        for (i, t) in self.prices.tokens.iter().enumerate() {
            l.append((t, dec_to_py(py, &self.prices.cols[i][self.row])?))?;
        }
        Ok(l)
    }
}

/// One market handed to a snapshot: (python MarketInfo key, market name, core market).
pub struct SnapMarket {
    pub key: Py<PyAny>,
    pub name: String,
    pub market: Shared<UniLpMarket>,
}

/// python `snapshot.market_status` (a `MarketDict` of rows).
#[pyclass(name = "MarketStatusMap", unsendable, module = "demeter._rs")]
pub struct MarketStatusMap {
    pub markets: Rc<Vec<SnapMarket>>,
}

impl MarketStatusMap {
    fn find(&self, key: &Bound<'_, PyAny>) -> PyResult<Option<usize>> {
        let name: String = if let Ok(s) = key.extract::<String>() {
            s
        } else {
            key.getattr("name")?.extract()?
        };
        Ok(self.markets.iter().position(|m| m.name == name))
    }
    fn bar(&self, i: usize) -> PyResult<BarView> {
        let m = &self.markets[i];
        let mk = m.market.borrow();
        let st = mk.status().py()?;
        Ok(BarView {
            market: m.market.clone(),
            bar: st.bar.clone(),
            ts: st.ts,
            row: st.row,
        })
    }
}

#[pymethods]
impl MarketStatusMap {
    fn __getitem__(&self, key: &Bound<'_, PyAny>) -> PyResult<BarView> {
        match self.find(key)? {
            Some(i) => self.bar(i),
            None => Err(PyKeyError::new_err(key.str()?.to_string())),
        }
    }
    fn __getattr__(&self, name: &str) -> PyResult<BarView> {
        match self.markets.iter().position(|m| m.name == name) {
            Some(i) => self.bar(i),
            None => Err(PyAttributeError::new_err(name.to_string())),
        }
    }
    fn __contains__(&self, key: &Bound<'_, PyAny>) -> PyResult<bool> {
        Ok(self.find(key)?.is_some())
    }
    fn __len__(&self) -> usize {
        self.markets.len()
    }
    #[getter]
    fn default(&self) -> PyResult<BarView> {
        self.bar(0)
    }
    fn get_default_key(&self, py: Python<'_>) -> Py<PyAny> {
        self.markets[0].key.clone_ref(py)
    }
    fn keys(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        self.markets.iter().map(|m| m.key.clone_ref(py)).collect()
    }
    fn values(&self) -> PyResult<Vec<BarView>> {
        (0..self.markets.len()).map(|i| self.bar(i)).collect()
    }
    fn items(&self, py: Python<'_>) -> PyResult<Vec<(Py<PyAny>, BarView)>> {
        (0..self.markets.len())
            .map(|i| Ok((self.markets[i].key.clone_ref(py), self.bar(i)?)))
            .collect()
    }
}

/// python `Snapshot(timestamp, row_id, prices, market_status)`
#[pyclass(name = "Snapshot", unsendable, module = "demeter._rs")]
pub struct PySnapshot {
    #[pyo3(get)]
    pub row_id: usize,
    /// timestamp in seconds (fast access for native code)
    #[pyo3(get)]
    pub ts: Ts,
    pub price_row: usize,
    pub prices: Rc<PriceTable>,
    pub markets: Rc<Vec<SnapMarket>>,
    pub timestamp_cache: Option<Py<PyAny>>,
}

#[pymethods]
impl PySnapshot {
    #[getter]
    fn timestamp(&mut self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        if let Some(t) = &self.timestamp_cache {
            return Ok(t.clone_ref(py));
        }
        let t = ts_to_py(py, self.ts)?.unbind();
        self.timestamp_cache = Some(t.clone_ref(py));
        Ok(t)
    }
    #[getter]
    fn prices(&self) -> PriceRow {
        PriceRow {
            prices: self.prices.clone(),
            row: self.price_row,
        }
    }
    #[getter]
    fn market_status(&self) -> MarketStatusMap {
        MarketStatusMap {
            markets: self.markets.clone(),
        }
    }
    fn __repr__(&self) -> String {
        format!(
            "Snapshot({}, row_id={})",
            demeter_core::types::ts_to_string(self.ts),
            self.row_id
        )
    }
}

/// Native state of the built-in triggers (`AtTimeTrigger`, `PeriodTrigger`, ...).
#[pyclass(name = "NativeTrigger", unsendable, module = "demeter._rs")]
pub struct NativeTrigger {
    pub cond: TriggerCond,
    #[pyo3(get, set)]
    pub legacy: bool,
}

#[pymethods]
impl NativeTrigger {
    #[staticmethod]
    fn at_time(ts: Ts) -> Self {
        NativeTrigger {
            cond: TriggerCond::at_time(ts),
            legacy: true,
        }
    }
    #[staticmethod]
    fn at_times(ts: Vec<Ts>) -> Self {
        NativeTrigger {
            cond: TriggerCond::at_times(&ts),
            legacy: true,
        }
    }
    #[staticmethod]
    fn time_range(start: Ts, end: Ts) -> Self {
        NativeTrigger {
            cond: TriggerCond::time_range(start, end),
            legacy: true,
        }
    }
    #[staticmethod]
    fn time_ranges(ranges: Vec<(Ts, Ts)>) -> Self {
        NativeTrigger {
            cond: TriggerCond::time_ranges(&ranges),
            legacy: true,
        }
    }
    #[staticmethod]
    fn period(delta: i64, trigger_immediately: bool, pending: i64) -> PyResult<Self> {
        Ok(NativeTrigger {
            cond: TriggerCond::period(delta, trigger_immediately, pending)
                .map_err(pyo3::exceptions::PyValueError::new_err)?,
            legacy: true,
        })
    }
    #[staticmethod]
    fn periods(deltas: Vec<i64>, trigger_immediately: bool, pending: i64) -> PyResult<Self> {
        Ok(NativeTrigger {
            cond: TriggerCond::periods(&deltas, trigger_immediately, pending)
                .map_err(pyo3::exceptions::PyValueError::new_err)?,
            legacy: true,
        })
    }
    pub fn when_ts(&mut self, ts: Ts) -> bool {
        self.cond.when(ts, self.legacy)
    }
    pub fn is_out_date_ts(&self, ts: Ts) -> bool {
        self.cond.is_out_date(ts)
    }
    fn reset(&mut self) {
        self.cond.reset()
    }
    /// next scheduled timestamp of a PeriodTrigger (python `_next_match`)
    #[getter]
    fn next_match(&self) -> Option<Ts> {
        match &self.cond {
            TriggerCond::Period { next, .. } => *next,
            _ => None,
        }
    }
}
