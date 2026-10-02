//! `AaveMarketCore` (the Rust side of python `AaveV3Market`), its data handle and the views of
//! its market status.

use crate::conv::*;
use crate::engine::PyBrokerCore;
use demeter_core::aave::{
    AaveData, AavePrices, AaveTokenStatus, AaveV3Market, BorrowInfo, SupplyInfo,
    REQUIRED_DATA_COLUMN,
};
use demeter_core::broker::{shared, Shared};
use demeter_core::data;
use demeter_core::dec::Dec;
use demeter_core::types::{AaveBalance, MarketInfo, MarketType, TokenInfo, Ts};
use pyo3::exceptions::{PyAttributeError, PyKeyError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyBytes, PyDict, PyFloat, PyList, PyTuple};
use std::sync::Arc;

fn ipc_bytes<'py>(
    py: Python<'py>,
    mut df: polars::prelude::DataFrame,
) -> PyResult<Bound<'py, PyBytes>> {
    let b = data::frame_to_ipc(&mut df).py()?;
    Ok(PyBytes::new(py, &b))
}

fn token(name: &str, decimal: u32) -> TokenInfo {
    TokenInfo::new(name, decimal)
}

fn tokens_with_address(tokens: Vec<(String, u32, String)>) -> Vec<TokenInfo> {
    tokens
        .iter()
        .map(|(n, d, a)| TokenInfo::with_address(n, *d, a))
        .collect()
}

fn dec_or_nan<'py>(py: Python<'py>, v: Option<Dec>) -> PyResult<Bound<'py, PyAny>> {
    match v {
        Some(d) => dec_to_py(py, &d),
        None => Ok(PyFloat::new(py, f64::NAN).into_any()),
    }
}

fn prices_from_py(prices: Option<Vec<(String, Bound<'_, PyAny>)>>) -> PyResult<AavePrices> {
    Ok(match prices {
        None => AavePrices::Unset,
        Some(v) => AavePrices::Values(
            v.iter()
                .map(|(n, p)| Ok((n.clone(), dec_from_py(p)?)))
                .collect::<PyResult<_>>()?,
        ),
    })
}

// ------------------------------------------------------------------ data

/// Immutable aave market data (cheap to copy: shared).
#[pyclass(name = "AaveDataHandle", module = "demeter._rs", skip_from_py_object)]
#[derive(Clone)]
pub struct PyAaveDataHandle {
    pub data: Arc<AaveData>,
}

#[pymethods]
impl PyAaveDataHandle {
    fn __len__(&self) -> usize {
        self.data.len()
    }
    /// whole table as Arrow IPC bytes, columns `timestamp` and `TOKEN|column`
    fn to_ipc<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        ipc_bytes(py, self.data.to_polars().py()?)
    }
    fn timestamps(&self) -> Vec<i64> {
        self.data.ts.clone()
    }
    fn tokens(&self) -> Vec<String> {
        self.data.tokens.iter().map(|t| t.name.clone()).collect()
    }
    fn has_token(&self, name: &str) -> bool {
        self.data.token(name).is_some()
    }
    fn has_column(&self, token: &str, column: &str) -> bool {
        self.data.has_column(token, column)
    }
    /// identity of the underlying table
    fn ptr(&self) -> usize {
        Arc::as_ptr(&self.data) as usize
    }
    fn copy(&self) -> PyAaveDataHandle {
        self.clone()
    }
    fn __copy__(&self) -> PyAaveDataHandle {
        self.clone()
    }
    fn __deepcopy__(&self, _memo: &Bound<'_, PyAny>) -> PyAaveDataHandle {
        self.clone()
    }
    /// from Arrow IPC bytes with `timestamp` and `TOKEN|column` columns
    #[staticmethod]
    fn from_ipc(ipc: &[u8]) -> PyResult<PyAaveDataHandle> {
        let df = data::frame_from_ipc(ipc).py()?;
        Ok(PyAaveDataHandle {
            data: Arc::new(AaveData::from_polars(&df).py()?),
        })
    }
    /// python `load_aave_data(chain, tokens, start, end, data_path)`; tokens: [(name, decimal, address)]
    #[staticmethod]
    fn load(
        chain: &str,
        tokens: Vec<(String, u32, String)>,
        start: chrono::NaiveDate,
        end: chrono::NaiveDate,
        data_path: &str,
    ) -> PyResult<PyAaveDataHandle> {
        let d = demeter_core::aave::load_aave_data(
            chain,
            &tokens_with_address(tokens),
            start,
            end,
            data_path,
        )
        .py()?;
        Ok(PyAaveDataHandle { data: Arc::new(d) })
    }
}

// ------------------------------------------------------------------ status views

/// Pool status of one token (python `market_status.data[token]`, a pandas row).
#[pyclass(name = "AaveTokenStatusView", unsendable, module = "demeter._rs")]
pub struct AaveTokenStatusView {
    pub name: String,
    pub status: Option<AaveTokenStatus>,
}

impl AaveTokenStatusView {
    fn value<'py>(&self, py: Python<'py>, column: &str) -> PyResult<Option<Bound<'py, PyAny>>> {
        if !REQUIRED_DATA_COLUMN.contains(&column) {
            return Ok(None);
        }
        dec_or_nan(py, self.status.and_then(|s| s.get(column))).map(Some)
    }
}

#[pymethods]
impl AaveTokenStatusView {
    fn __getattr__<'py>(&self, py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
        if name == "name" {
            return Ok(self.name.clone().into_pyobject(py)?.into_any());
        }
        self.value(py, name)?.ok_or_else(|| {
            PyAttributeError::new_err(format!(
                "'AaveTokenStatusView' object has no attribute '{name}'"
            ))
        })
    }
    fn __getitem__<'py>(&self, py: Python<'py>, column: &str) -> PyResult<Bound<'py, PyAny>> {
        self.value(py, column)?
            .ok_or_else(|| PyKeyError::new_err(column.to_string()))
    }
    fn __contains__(&self, column: &str) -> bool {
        REQUIRED_DATA_COLUMN.contains(&column)
    }
    /// iterates the values, like a pandas Series
    fn __iter__<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let values: Vec<Bound<'py, PyAny>> = REQUIRED_DATA_COLUMN
            .iter()
            .map(|c| dec_or_nan(py, self.status.and_then(|s| s.get(c))))
            .collect::<PyResult<_>>()?;
        PyList::new(py, values)?
            .into_any()
            .try_iter()
            .map(|i| i.into_any())
    }
    fn __len__(&self) -> usize {
        REQUIRED_DATA_COLUMN.len()
    }
    #[pyo3(signature = (column, default=None))]
    fn get<'py>(
        &self,
        py: Python<'py>,
        column: &str,
        default: Option<Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        Ok(match self.value(py, column)? {
            Some(v) => v,
            None => default.unwrap_or_else(|| py.None().into_bound(py)),
        })
    }
    fn keys(&self) -> Vec<&'static str> {
        REQUIRED_DATA_COLUMN.to_vec()
    }
    #[getter]
    fn index(&self) -> Vec<&'static str> {
        REQUIRED_DATA_COLUMN.to_vec()
    }
    fn to_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let d = PyDict::new(py);
        for c in REQUIRED_DATA_COLUMN {
            d.set_item(c, self.value(py, c)?)?;
        }
        Ok(d)
    }
    fn __repr__(&self) -> String {
        let p = demeter_core::dec::to_plain_string;
        match &self.status {
            Some(s) => format!(
                "AaveTokenStatus({}: liquidity_rate={}, stable_borrow_rate={}, variable_borrow_rate={}, liquidity_index={}, variable_borrow_index={})",
                self.name,
                p(&s.liquidity_rate),
                p(&s.stable_borrow_rate),
                p(&s.variable_borrow_rate),
                p(&s.liquidity_index),
                p(&s.variable_borrow_index),
            ),
            None => format!("AaveTokenStatus({}: NaN)", self.name),
        }
    }
}

/// Pool status of all tokens in one minute (python `snapshot.market_status[aave_key]` and
/// `market.market_status.data`: a pandas row with a (token, column) index).
/// `row["WETH"].liquidity_index` and `row[("WETH", "liquidity_index")]` both work.
#[pyclass(name = "AaveStatusView", unsendable, module = "demeter._rs")]
pub struct AaveStatusView {
    pub ts: Ts,
    pub tokens: Vec<(String, Option<AaveTokenStatus>)>,
}

impl AaveStatusView {
    fn token_view(&self, name: &str) -> Option<AaveTokenStatusView> {
        self.tokens
            .iter()
            .find(|(n, _)| n == name)
            .map(|(n, s)| AaveTokenStatusView {
                name: n.clone(),
                status: *s,
            })
    }

    fn lookup<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'py, PyAny>,
    ) -> PyResult<Option<Bound<'py, PyAny>>> {
        if let Ok((tok, col)) = key.extract::<(String, String)>() {
            return match self.token_view(&tok) {
                Some(v) => v.value(py, &col),
                None => Ok(None),
            };
        }
        let Ok(name) = key.extract::<String>() else {
            return Ok(None);
        };
        match self.token_view(&name) {
            Some(v) => Ok(Some(Bound::new(py, v)?.into_any())),
            None => Ok(None),
        }
    }
}

#[pymethods]
impl AaveStatusView {
    fn __getitem__<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        self.lookup(py, key)?
            .ok_or_else(|| PyKeyError::new_err(key.clone().unbind()))
    }
    fn __getattr__<'py>(&self, py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
        if name == "name" || name == "timestamp" {
            return ts_to_py(py, self.ts);
        }
        match self.token_view(name) {
            Some(v) => Ok(Bound::new(py, v)?.into_any()),
            None => Err(PyAttributeError::new_err(format!(
                "'AaveStatusView' object has no attribute '{name}'"
            ))),
        }
    }
    fn __contains__<'py>(&self, py: Python<'py>, key: &Bound<'py, PyAny>) -> PyResult<bool> {
        Ok(self.lookup(py, key)?.is_some())
    }
    fn __len__(&self) -> usize {
        self.tokens.len() * REQUIRED_DATA_COLUMN.len()
    }
    /// iterates the values in (token, column) order, like a pandas Series
    fn __iter__<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let mut values = Vec::with_capacity(self.__len__());
        for (_, s) in &self.tokens {
            for c in REQUIRED_DATA_COLUMN {
                values.push(dec_or_nan(py, s.and_then(|s| s.get(c)))?);
            }
        }
        PyList::new(py, values)?
            .into_any()
            .try_iter()
            .map(|i| i.into_any())
    }
    #[pyo3(signature = (key, default=None))]
    fn get<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'py, PyAny>,
        default: Option<Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        Ok(match self.lookup(py, key)? {
            Some(v) => v,
            None => default.unwrap_or_else(|| py.None().into_bound(py)),
        })
    }
    /// token names
    fn tokens(&self) -> Vec<String> {
        self.tokens.iter().map(|(n, _)| n.clone()).collect()
    }
    /// (token, column) pairs, like the pandas MultiIndex
    fn keys(&self) -> Vec<(String, &'static str)> {
        self.tokens
            .iter()
            .flat_map(|(n, _)| REQUIRED_DATA_COLUMN.iter().map(move |c| (n.clone(), *c)))
            .collect()
    }
    #[getter]
    fn index(&self) -> Vec<(String, &'static str)> {
        self.keys()
    }
    /// {(token, column): value}
    fn to_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let d = PyDict::new(py);
        for (n, s) in &self.tokens {
            for c in REQUIRED_DATA_COLUMN {
                d.set_item((n, c), dec_or_nan(py, s.and_then(|s| s.get(c)))?)?;
            }
        }
        Ok(d)
    }
    /// [(token, [5 values in REQUIRED_DATA_COLUMN order] or None)]
    fn values_by_token<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let l = PyList::empty(py);
        for (n, s) in &self.tokens {
            match s {
                Some(s) => {
                    let v: Vec<Bound<'py, PyAny>> = s
                        .values()
                        .iter()
                        .map(|d| dec_to_py(py, d))
                        .collect::<PyResult<_>>()?;
                    l.append((n, v))?;
                }
                None => l.append((n, py.None()))?,
            }
        }
        Ok(l)
    }
    fn __repr__(&self) -> String {
        let names: Vec<&String> = self.tokens.iter().map(|(n, _)| n).collect();
        format!(
            "AaveStatusView({}, tokens={names:?})",
            demeter_core::types::ts_to_string(self.ts)
        )
    }
}

pub fn status_view(m: &AaveV3Market) -> Option<AaveStatusView> {
    m.status.as_ref().map(|s| AaveStatusView {
        ts: s.ts,
        tokens: s.tokens(),
    })
}

// ------------------------------------------------------------------ market

#[pyclass(name = "AaveMarketCore", unsendable, module = "demeter._rs")]
pub struct PyAaveMarketCore {
    pub inner: Shared<AaveV3Market>,
}

fn supply_tuple<'py>(
    py: Python<'py>,
    s: &demeter_core::aave::Supply,
) -> PyResult<Bound<'py, PyTuple>> {
    PyTuple::new(
        py,
        [
            s.token.name.clone().into_pyobject(py)?.into_any(),
            s.token.decimal.into_pyobject(py)?.into_any(),
            dec_to_py(py, &s.base_amount)?,
            PyBool::new(py, s.collateral).to_owned().into_any(),
            dec_to_py(py, &s.amount)?,
            dec_to_py(py, &s.apy)?,
            dec_to_py(py, &s.value)?,
            dec_to_py(py, &s.begin_supply_index)?,
        ],
    )
}

fn borrow_tuple<'py>(
    py: Python<'py>,
    b: &demeter_core::aave::Borrow,
) -> PyResult<Bound<'py, PyTuple>> {
    PyTuple::new(
        py,
        [
            b.token.name.clone().into_pyobject(py)?.into_any(),
            b.token.decimal.into_pyobject(py)?.into_any(),
            dec_to_py(py, &b.base_amount)?,
            dec_to_py(py, &b.amount)?,
            dec_to_py(py, &b.apy)?,
            dec_to_py(py, &b.value)?,
            dec_to_py(py, &b.begin_borrow_index)?,
        ],
    )
}

type TokenValues<'py> = Vec<(String, u32, Bound<'py, PyAny>)>;

fn values_list<'py>(py: Python<'py>, v: &[(TokenInfo, Dec)]) -> PyResult<TokenValues<'py>> {
    v.iter()
        .map(|(t, d)| Ok((t.name.clone(), t.decimal, dec_to_py(py, d)?)))
        .collect()
}

/// python `AaveBalance` fields, in dataclass order
pub fn aave_balance_tuple<'py>(py: Python<'py>, b: &AaveBalance) -> PyResult<Bound<'py, PyTuple>> {
    PyTuple::new(
        py,
        [
            dec_to_py(py, &b.net_value)?,
            b.supplies_count.into_pyobject(py)?.into_any(),
            b.borrows_count.into_pyobject(py)?.into_any(),
            dec_to_py(py, &b.borrows_value)?,
            dec_to_py(py, &b.supplies_value)?,
            dec_to_py(py, &b.collaterals_value)?,
            dec_to_py(py, &b.health_factor)?,
            dec_to_py(py, &b.max_ltv)?,
            dec_to_py(py, &b.ltv)?,
            dec_to_py(py, &b.liquidation_threshold)?,
            dec_to_py(py, &b.supply_apy)?,
            dec_to_py(py, &b.borrow_apy)?,
            dec_to_py(py, &b.net_apy)?,
        ],
    )
}

#[pymethods]
impl PyAaveMarketCore {
    /// tokens: [(name, decimal, address)]
    #[new]
    #[pyo3(signature = (name, market_type, risk_parameters_path, tokens))]
    fn new(
        name: &str,
        market_type: i64,
        risk_parameters_path: &str,
        tokens: Vec<(String, u32, String)>,
    ) -> PyResult<Self> {
        let info = MarketInfo {
            name: name.to_string(),
            kind: MarketType::from_value(market_type),
        };
        let m =
            AaveV3Market::from_risk_file(info, risk_parameters_path, tokens_with_address(tokens))
                .py()?;
        Ok(PyAaveMarketCore { inner: shared(m) })
    }

    fn add_token(&self, name: &str, decimal: u32, address: &str) {
        self.inner
            .borrow_mut()
            .add_token(TokenInfo::with_address(name, decimal, address));
    }
    /// [(name, decimal, address)]
    fn tokens(&self) -> Vec<(String, u32, String)> {
        self.inner
            .borrow()
            .tokens
            .iter()
            .map(|t| (t.name.clone(), t.decimal, t.address.clone()))
            .collect()
    }
    /// use the wallet and action log of a broker (python `market.broker = broker`)
    fn attach_broker(&self, broker: &PyBrokerCore) {
        self.inner.borrow_mut().set_broker(&broker.inner.borrow());
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

    // ------------------------------------------------ data
    fn has_data(&self) -> bool {
        self.inner.borrow().data.is_some()
    }
    fn get_data(&self) -> PyResult<PyAaveDataHandle> {
        Ok(PyAaveDataHandle {
            data: self.inner.borrow().data().py()?.clone(),
        })
    }
    fn set_data(&self, handle: &PyAaveDataHandle) {
        self.inner.borrow_mut().set_data(handle.data.clone());
    }
    /// python `set_token_data(token, frame)`; ipc has `timestamp` and plain column names
    fn set_token_data(&self, name: &str, ipc: &[u8]) -> PyResult<()> {
        let df = data::frame_from_ipc(ipc).py()?;
        let (ts, t) = AaveData::token_from_polars(name, &df).py()?;
        self.inner.borrow_mut().set_token_data(&ts, t).py()
    }
    /// tokens: [(name, decimal, address)]
    fn load_data(
        &self,
        chain: &str,
        tokens: Vec<(String, u32, String)>,
        start: chrono::NaiveDate,
        end: chrono::NaiveDate,
        data_path: &str,
    ) -> PyResult<()> {
        let mut m = self.inner.borrow_mut();
        m.data_path = data_path.to_string();
        m.load_data(chain, &tokens_with_address(tokens), start, end)
            .py()
    }
    fn resample(&self, interval_secs: i64) -> PyResult<()> {
        self.inner.borrow_mut().resample(interval_secs).py()
    }

    // ------------------------------------------------ status
    /// python `set_market_status(MarketStatus(ts), price)`; prices: [(token, price)] or None
    #[pyo3(signature = (ts, prices=None))]
    fn set_market_status(
        &self,
        ts: &Bound<'_, PyAny>,
        prices: Option<Vec<(String, Bound<'_, PyAny>)>>,
    ) -> PyResult<()> {
        let ts = ts_from_py(ts)?;
        let p = prices_from_py(prices)?;
        self.inner.borrow_mut().set_market_status(ts, p).py()
    }
    /// status given explicitly: tokens [(token, [5 values in REQUIRED_DATA_COLUMN order] or None)]
    #[pyo3(signature = (ts, tokens, prices=None))]
    fn set_market_status_values(
        &self,
        ts: &Bound<'_, PyAny>,
        tokens: Vec<(String, Option<Vec<Bound<'_, PyAny>>>)>,
        prices: Option<Vec<(String, Bound<'_, PyAny>)>>,
    ) -> PyResult<()> {
        let ts = if ts.is_none() { 0 } else { ts_from_py(ts)? };
        let mut rows = Vec::with_capacity(tokens.len());
        for (n, vals) in tokens {
            let status = match vals {
                None => None,
                Some(v) => {
                    if v.len() != REQUIRED_DATA_COLUMN.len() {
                        return Err(PyValueError::new_err(format!(
                            "{n}: expected {} values",
                            REQUIRED_DATA_COLUMN.len()
                        )));
                    }
                    let mut d = [Dec::ZERO; 5];
                    for (i, x) in v.iter().enumerate() {
                        d[i] = dec_from_py(x)?;
                    }
                    (!d.iter().any(|x| x.is_nan())).then(|| AaveTokenStatus::from_values(d))
                }
            };
            rows.push((n.to_uppercase(), status));
        }
        let p = prices_from_py(prices)?;
        self.inner
            .borrow_mut()
            .set_market_status_values(ts, rows, p);
        Ok(())
    }
    fn status_timestamp(&self) -> Option<Ts> {
        self.inner.borrow().status.as_ref().map(|s| s.ts)
    }
    fn status_view(&self) -> Option<AaveStatusView> {
        status_view(&self.inner.borrow())
    }
    /// [(token, price)] the market values tokens with (python `_price_status`); None if unset
    fn price_status<'py>(&self, py: Python<'py>) -> PyResult<Option<TokenPrices<'py>>> {
        let m = self.inner.borrow();
        if matches!(m.prices, AavePrices::Unset) {
            return Ok(None);
        }
        m.prices
            .names()
            .into_iter()
            .map(|n| {
                let p = m.prices.get(&n).py()?;
                Ok((n, dec_to_py(py, &p)?))
            })
            .collect::<PyResult<_>>()
            .map(Some)
    }

    // ------------------------------------------------ positions (python `_supplies` / `_borrows`)
    /// [(name, decimal, base_amount, collateral, begin_supply_index)]
    fn supply_infos<'py>(&self, py: Python<'py>) -> PyResult<Vec<Bound<'py, PyTuple>>> {
        self.inner
            .borrow()
            .supply_infos()
            .iter()
            .map(|(t, s)| {
                PyTuple::new(
                    py,
                    [
                        t.name.clone().into_pyobject(py)?.into_any(),
                        t.decimal.into_pyobject(py)?.into_any(),
                        dec_to_py(py, &s.base_amount)?,
                        PyBool::new(py, s.collateral).to_owned().into_any(),
                        dec_to_py(py, &s.begin_supply_index)?,
                    ],
                )
            })
            .collect()
    }
    fn set_supply_info(
        &self,
        name: &str,
        decimal: u32,
        base_amount: &Bound<'_, PyAny>,
        collateral: bool,
        begin_supply_index: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let info = SupplyInfo {
            base_amount: dec_from_py(base_amount)?,
            collateral,
            begin_supply_index: dec_from_py(begin_supply_index)?,
        };
        self.inner
            .borrow_mut()
            .set_supply_info(&token(name, decimal), info);
        Ok(())
    }
    fn set_supply_field(&self, name: &str, field: &str, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let mut m = self.inner.borrow_mut();
        let key = token(name, 0);
        let (t, mut info) = m
            .supply_infos()
            .iter()
            .find(|(k, _)| *k == key)
            .cloned()
            .ok_or_else(|| PyKeyError::new_err(name.to_string()))?;
        match field {
            "base_amount" => info.base_amount = dec_from_py(value)?,
            "collateral" => info.collateral = value.is_truthy()?,
            "begin_supply_index" => info.begin_supply_index = dec_from_py(value)?,
            _ => return Err(PyAttributeError::new_err(field.to_string())),
        }
        m.set_supply_info(&t, info);
        Ok(())
    }
    fn remove_supply_info(&self, name: &str) -> bool {
        self.inner
            .borrow_mut()
            .remove_supply_info(&token(name, 0))
            .is_some()
    }
    /// [(name, decimal, base_amount, begin_borrow_index)]
    fn borrow_infos<'py>(&self, py: Python<'py>) -> PyResult<Vec<Bound<'py, PyTuple>>> {
        self.inner
            .borrow()
            .borrow_infos()
            .iter()
            .map(|(t, b)| {
                PyTuple::new(
                    py,
                    [
                        t.name.clone().into_pyobject(py)?.into_any(),
                        t.decimal.into_pyobject(py)?.into_any(),
                        dec_to_py(py, &b.base_amount)?,
                        dec_to_py(py, &b.begin_borrow_index)?,
                    ],
                )
            })
            .collect()
    }
    fn set_borrow_info(
        &self,
        name: &str,
        decimal: u32,
        base_amount: &Bound<'_, PyAny>,
        begin_borrow_index: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let info = BorrowInfo {
            base_amount: dec_from_py(base_amount)?,
            begin_borrow_index: dec_from_py(begin_borrow_index)?,
        };
        self.inner
            .borrow_mut()
            .set_borrow_info(&token(name, decimal), info);
        Ok(())
    }
    fn set_borrow_field(&self, name: &str, field: &str, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let mut m = self.inner.borrow_mut();
        let key = token(name, 0);
        let (t, mut info) = m
            .borrow_infos()
            .iter()
            .find(|(k, _)| *k == key)
            .cloned()
            .ok_or_else(|| PyKeyError::new_err(name.to_string()))?;
        match field {
            "base_amount" => info.base_amount = dec_from_py(value)?,
            "begin_borrow_index" => info.begin_borrow_index = dec_from_py(value)?,
            _ => return Err(PyAttributeError::new_err(field.to_string())),
        }
        m.set_borrow_info(&t, info);
        Ok(())
    }
    fn remove_borrow_info(&self, name: &str) -> bool {
        self.inner
            .borrow_mut()
            .remove_borrow_info(&token(name, 0))
            .is_some()
    }

    // ------------------------------------------------ values
    fn supplies_value<'py>(&self, py: Python<'py>) -> PyResult<TokenValues<'py>> {
        values_list(py, &self.inner.borrow().supplies_value().py()?)
    }
    fn collateral_value<'py>(&self, py: Python<'py>) -> PyResult<TokenValues<'py>> {
        values_list(py, &self.inner.borrow().collateral_value().py()?)
    }
    fn borrows_value<'py>(&self, py: Python<'py>) -> PyResult<TokenValues<'py>> {
        values_list(py, &self.inner.borrow().borrows_value().py()?)
    }
    fn total_supply_value<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        dec_to_py(py, &self.inner.borrow().total_supply_value().py()?)
    }
    fn total_collateral_value<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        dec_to_py(py, &self.inner.borrow().total_collateral_value().py()?)
    }
    fn total_borrows_value<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        dec_to_py(py, &self.inner.borrow().total_borrows_value().py()?)
    }
    /// [(name, decimal, base_amount, collateral, amount, apy, value, begin_supply_index)]
    fn supplies<'py>(&self, py: Python<'py>) -> PyResult<Vec<Bound<'py, PyTuple>>> {
        let s = self.inner.borrow().supplies().py()?;
        s.iter().map(|(_, x)| supply_tuple(py, x)).collect()
    }
    /// [(name, decimal, base_amount, amount, apy, value, begin_borrow_index)]
    fn borrows<'py>(&self, py: Python<'py>) -> PyResult<Vec<Bound<'py, PyTuple>>> {
        let b = self.inner.borrow().borrows().py()?;
        b.iter().map(|(_, x)| borrow_tuple(py, x)).collect()
    }
    fn get_supply<'py>(&self, py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyTuple>> {
        let s = self.inner.borrow().get_supply(&token(name, 0)).py()?;
        supply_tuple(py, &s)
    }
    fn get_borrow<'py>(&self, py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyTuple>> {
        let b = self.inner.borrow().get_borrow(&token(name, 0)).py()?;
        borrow_tuple(py, &b)
    }
    fn liquidation_threshold<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        dec_to_py(py, &self.inner.borrow().liquidation_threshold().py()?)
    }
    fn max_ltv<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        dec_to_py(py, &self.inner.borrow().max_ltv().py()?)
    }
    fn ltv<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        dec_to_py(py, &self.inner.borrow().ltv().py()?)
    }
    fn health_factor<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        dec_to_py(py, &self.inner.borrow().health_factor().py()?)
    }
    fn supply_apy<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        dec_to_py(py, &self.inner.borrow().supply_apy().py()?)
    }
    fn borrow_apy<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        dec_to_py(py, &self.inner.borrow().borrow_apy().py()?)
    }
    fn total_apy<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        dec_to_py(py, &self.inner.borrow().total_apy().py()?)
    }
    /// python `AaveBalance` fields, in order
    fn get_market_balance<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        let b = self.inner.borrow().get_market_balance().py()?;
        aave_balance_tuple(py, &b)
    }
    fn check_market(&self) -> PyResult<()> {
        self.inner.borrow().check_market().py()
    }
    fn update(&self) -> PyResult<()> {
        self.inner.borrow_mut().update().py()
    }

    // ------------------------------------------------ operations
    fn supply(
        &self,
        name: &str,
        decimal: u32,
        amount: &Bound<'_, PyAny>,
        collateral: bool,
    ) -> PyResult<()> {
        let amount = dec_from_py(amount)?;
        self.inner
            .borrow_mut()
            .supply(&token(name, decimal), amount, collateral)
            .py()
    }
    fn change_collateral(&self, name: &str, decimal: u32, collateral: bool) -> PyResult<()> {
        self.inner
            .borrow_mut()
            .change_collateral(&token(name, decimal), collateral)
            .py()
    }
    #[pyo3(signature = (name, decimal, amount=None))]
    fn withdraw(
        &self,
        name: &str,
        decimal: u32,
        amount: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<()> {
        let amount = opt_dec(amount)?;
        self.inner
            .borrow_mut()
            .withdraw(&token(name, decimal), amount)
            .py()
    }
    fn get_max_withdraw_amount<'py>(
        &self,
        py: Python<'py>,
        name: &str,
    ) -> PyResult<Bound<'py, PyAny>> {
        let v = self
            .inner
            .borrow()
            .get_max_withdraw_amount(&token(name, 0))
            .py()?;
        dec_to_py(py, &v)
    }
    fn get_max_borrow_amount<'py>(
        &self,
        py: Python<'py>,
        name: &str,
    ) -> PyResult<Bound<'py, PyAny>> {
        let v = self
            .inner
            .borrow()
            .get_max_borrow_amount(&token(name, 0))
            .py()?;
        dec_to_py(py, &v)
    }
    #[pyo3(signature = (name, decimal, amount=None))]
    fn borrow(&self, name: &str, decimal: u32, amount: Option<&Bound<'_, PyAny>>) -> PyResult<()> {
        let amount = opt_dec(amount)?;
        self.inner
            .borrow_mut()
            .borrow(&token(name, decimal), amount)
            .py()
    }
    fn get_max_repay_amount<'py>(
        &self,
        py: Python<'py>,
        name: &str,
    ) -> PyResult<Bound<'py, PyAny>> {
        let v = self
            .inner
            .borrow()
            .get_max_repay_amount(&token(name, 0))
            .py()?;
        dec_to_py(py, &v)
    }
    /// collateral_token: (name, decimal) or None
    #[pyo3(signature = (name, decimal, amount=None, repay_with_collateral=false, collateral_token=None))]
    fn repay(
        &self,
        name: &str,
        decimal: u32,
        amount: Option<&Bound<'_, PyAny>>,
        repay_with_collateral: bool,
        collateral_token: Option<(String, u32)>,
    ) -> PyResult<()> {
        let amount = opt_dec(amount)?;
        let ct = collateral_token.map(|(n, d)| token(&n, d));
        self.inner
            .borrow_mut()
            .repay(
                &token(name, decimal),
                amount,
                repay_with_collateral,
                ct.as_ref(),
            )
            .py()
    }

    /// python `AaveV3CoreLib.rate_to_apy`, with python's 35 digit rounding
    #[staticmethod]
    fn rate_to_apy<'py>(py: Python<'py>, rate: &Bound<'_, PyAny>) -> PyResult<Bound<'py, PyAny>> {
        dec_to_py(py, &demeter_core::aave::rate_to_apy(&dec_from_py(rate)?))
    }
}

type TokenPrices<'py> = Vec<(String, Bound<'py, PyAny>)>;
