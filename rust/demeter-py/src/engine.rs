//! `BrokerCore`, `ActuatorCore` and the adapter that drives a python `Strategy` from the Rust loop.

use crate::conv::*;
use crate::market::{balance_tuple, price_frame, PyMarketCore};
use crate::snapshot::{NativeTrigger, PySnapshot, SnapMarket};
use demeter_core::actions::{Action, ActionKind, ActionLog, Ud};
use demeter_core::actuator::{Actuator, Ctx, PriceTable, Snapshot, Strategy};
use demeter_core::broker::{shared, AccountRow, Broker, Shared};
use demeter_core::data;
use demeter_core::dec::{self, Dec};
use demeter_core::types::{PositionInfo, TokenInfo, Ts};
use demeter_core::DemeterError;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyTuple};
use std::cell::{Cell, RefCell};
use std::rc::Rc;

// ------------------------------------------------------------------ broker

#[pyclass(name = "BrokerCore", unsendable, module = "demeter._rs")]
pub struct PyBrokerCore {
    pub inner: Shared<Broker>,
}

#[pymethods]
impl PyBrokerCore {
    #[new]
    #[pyo3(signature = (allow_negative_balance=false))]
    fn new(allow_negative_balance: bool) -> Self {
        PyBrokerCore {
            inner: shared(Broker::new(
                allow_negative_balance,
                shared(ActionLog::default()),
            )),
        }
    }
    #[getter]
    fn allow_negative_balance(&self) -> bool {
        self.inner.borrow().wallet.borrow().allow_negative_balance
    }
    #[setter]
    fn set_allow_negative_balance(&self, v: bool) {
        self.inner
            .borrow()
            .wallet
            .borrow_mut()
            .allow_negative_balance = v;
    }
    fn add_market(&self, market: &PyMarketCore) -> PyResult<()> {
        self.inner
            .borrow_mut()
            .add_market(market.inner.clone())
            .py()
    }
    fn set_balance(&self, name: &str, decimal: u32, amount: &Bound<'_, PyAny>) -> PyResult<()> {
        let t = TokenInfo::new(name, decimal);
        self.inner
            .borrow()
            .wallet
            .borrow_mut()
            .set(&t, dec_from_py(amount)?);
        Ok(())
    }
    fn add_to_balance(&self, name: &str, decimal: u32, amount: &Bound<'_, PyAny>) -> PyResult<()> {
        let t = TokenInfo::new(name, decimal);
        self.inner
            .borrow()
            .wallet
            .borrow_mut()
            .add(&t, dec_from_py(amount)?);
        Ok(())
    }
    fn subtract_from_balance(
        &self,
        name: &str,
        decimal: u32,
        amount: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let t = TokenInfo::new(name, decimal);
        let b = self.inner.borrow();
        let mut w = b.wallet.borrow_mut();
        w.sub(&t, dec_from_py(amount)?).py()
    }
    fn get_token_balance<'py>(&self, py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
        let t = TokenInfo::new(name, 0);
        let v = self.inner.borrow().wallet.borrow().balance(&t).py()?;
        dec_to_py(py, &v)
    }
    fn has_token(&self, name: &str) -> bool {
        self.inner
            .borrow()
            .wallet
            .borrow()
            .contains(&TokenInfo::new(name, 0))
    }
    /// [(name, decimal, balance)]
    fn assets<'py>(&self, py: Python<'py>) -> PyResult<Vec<(String, u32, Bound<'py, PyAny>)>> {
        let b = self.inner.borrow();
        let w = b.wallet.borrow();
        w.assets
            .iter()
            .map(|(t, v)| Ok((t.name.clone(), t.decimal, dec_to_py(py, v)?)))
            .collect()
    }
    #[getter]
    fn quote_token(&self) -> Option<(String, u32)> {
        self.inner
            .borrow()
            .quote_token
            .as_ref()
            .map(|t| (t.name.clone(), t.decimal))
    }
    fn set_quote_token(&self, name: &str, decimal: u32) {
        self.inner.borrow_mut().quote_token = Some(TokenInfo::new(name, decimal));
    }
    /// python `get_account_status(prices, timestamp)`; prices: {token name: price}
    fn get_account_status<'py>(
        &self,
        py: Python<'py>,
        prices: &Bound<'_, PyDict>,
        ts: &Bound<'_, PyAny>,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let mut map = std::collections::HashMap::new();
        for (k, v) in prices.iter() {
            map.insert(k.extract::<String>()?, dec_from_py(&v)?);
        }
        let price_of = |name: &str| {
            map.get(name)
                .copied()
                .ok_or_else(|| DemeterError::Data(format!("KeyError: {name}")))
        };
        let row = self
            .inner
            .borrow()
            .get_account_status(&price_of, ts_from_py(ts)?)
            .py()?;
        account_row_tuple(py, &row)
    }
    #[allow(clippy::too_many_arguments)]
    fn swap_by_from(
        &self,
        from: (String, u32),
        to: (String, u32),
        amount: &Bound<'_, PyAny>,
        from_price: &Bound<'_, PyAny>,
        to_price: &Bound<'_, PyAny>,
        fee_rate: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        self.inner
            .borrow()
            .swap_by_from(
                &TokenInfo::new(&from.0, from.1),
                &TokenInfo::new(&to.0, to.1),
                dec_from_py(amount)?,
                dec_from_py(from_price)?,
                dec_from_py(to_price)?,
                dec_from_py(fee_rate)?,
            )
            .py()
    }
    #[allow(clippy::too_many_arguments)]
    fn swap_by_to(
        &self,
        from: (String, u32),
        to: (String, u32),
        amount: &Bound<'_, PyAny>,
        from_price: &Bound<'_, PyAny>,
        to_price: &Bound<'_, PyAny>,
        fee_rate: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        self.inner
            .borrow()
            .swap_by_to(
                &TokenInfo::new(&from.0, from.1),
                &TokenInfo::new(&to.0, to.1),
                dec_from_py(amount)?,
                dec_from_py(from_price)?,
                dec_from_py(to_price)?,
                dec_from_py(fee_rate)?,
            )
            .py()
    }
    /// actions recorded through this broker (standalone use)
    fn actions<'py>(&self, py: Python<'py>) -> PyResult<Vec<Bound<'py, PyDict>>> {
        let b = self.inner.borrow();
        let log = b.log.borrow();
        log.actions.iter().map(|a| action_to_py(py, a)).collect()
    }
}

// ------------------------------------------------------------------ conversions

fn ud<'py>(py: Python<'py>, u: &Ud) -> PyResult<Bound<'py, PyTuple>> {
    PyTuple::new(
        py,
        [
            dec_to_py(py, &u.value)?,
            u.unit.clone().into_pyobject(py)?.into_any(),
        ],
    )
}

fn position_tuple<'py>(py: Python<'py>, p: &PositionInfo) -> PyResult<Bound<'py, PyTuple>> {
    PyTuple::new(py, [p.lower_tick, p.upper_tick])
}

/// Action -> dict {type, market_name, market_type, timestamp, comment, fields}
pub fn action_to_py<'py>(py: Python<'py>, a: &Action) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("type", a.kind.type_name())?;
    d.set_item("market_name", &a.market.name)?;
    d.set_item("market_type", a.market.kind as i64)?;
    d.set_item("timestamp", ts_to_py(py, a.timestamp)?)?;
    d.set_item("comment", &a.comment)?;
    let f = PyDict::new(py);
    match &a.kind {
        ActionKind::AddLiquidity {
            base_balance_after,
            quote_balance_after,
            base_amount_max,
            quote_amount_max,
            lower_quote_price,
            upper_quote_price,
            base_amount_actual,
            quote_amount_actual,
            position,
            liquidity,
        } => {
            f.set_item("base_balance_after", ud(py, base_balance_after)?)?;
            f.set_item("quote_balance_after", ud(py, quote_balance_after)?)?;
            f.set_item("base_amount_max", ud(py, base_amount_max)?)?;
            f.set_item("quote_amount_max", ud(py, quote_amount_max)?)?;
            f.set_item("lower_quote_price", ud(py, lower_quote_price)?)?;
            f.set_item("upper_quote_price", ud(py, upper_quote_price)?)?;
            f.set_item("base_amount_actual", ud(py, base_amount_actual)?)?;
            f.set_item("quote_amount_actual", ud(py, quote_amount_actual)?)?;
            f.set_item("position", position_tuple(py, position)?)?;
            f.set_item("liquidity", *liquidity)?;
        }
        ActionKind::RemoveLiquidity {
            base_balance_after,
            quote_balance_after,
            position,
            base_amount,
            quote_amount,
            removed_liquidity,
            remain_liquidity,
        } => {
            f.set_item("base_balance_after", ud(py, base_balance_after)?)?;
            f.set_item("quote_balance_after", ud(py, quote_balance_after)?)?;
            f.set_item("position", position_tuple(py, position)?)?;
            f.set_item("base_amount", ud(py, base_amount)?)?;
            f.set_item("quote_amount", ud(py, quote_amount)?)?;
            f.set_item("removed_liquidity", *removed_liquidity)?;
            f.set_item("remain_liquidity", *remain_liquidity)?;
        }
        ActionKind::CollectFee {
            base_balance_after,
            quote_balance_after,
            position,
            base_amount,
            quote_amount,
        } => {
            f.set_item("base_balance_after", ud(py, base_balance_after)?)?;
            f.set_item("quote_balance_after", ud(py, quote_balance_after)?)?;
            f.set_item("position", position_tuple(py, position)?)?;
            f.set_item("base_amount", ud(py, base_amount)?)?;
            f.set_item("quote_amount", ud(py, quote_amount)?)?;
        }
        ActionKind::Swap {
            amount,
            price,
            fee,
            to_amount,
        } => {
            f.set_item("amount", ud(py, amount)?)?;
            f.set_item("price", ud(py, price)?)?;
            f.set_item("fee", ud(py, fee)?)?;
            f.set_item("to_amount", ud(py, to_amount)?)?;
        }
        ActionKind::Buy {
            base_balance_after,
            quote_balance_after,
            amount,
            price,
            fee,
            base_change,
            quote_change,
        }
        | ActionKind::Sell {
            base_balance_after,
            quote_balance_after,
            amount,
            price,
            fee,
            base_change,
            quote_change,
        } => {
            f.set_item("base_balance_after", ud(py, base_balance_after)?)?;
            f.set_item("quote_balance_after", ud(py, quote_balance_after)?)?;
            f.set_item("amount", ud(py, amount)?)?;
            f.set_item("price", ud(py, price)?)?;
            f.set_item("fee", ud(py, fee)?)?;
            f.set_item("base_change", ud(py, base_change)?)?;
            f.set_item("quote_change", ud(py, quote_change)?)?;
        }
        ActionKind::BrokerSwap {
            from_token,
            from_amount,
            to_token,
            to_amount,
            fee_rate,
            fee,
        } => {
            f.set_item("from_token", from_token)?;
            f.set_item("from_amount", ud(py, from_amount)?)?;
            f.set_item("to_token", to_token)?;
            f.set_item("to_amount", ud(py, to_amount)?)?;
            f.set_item("fee_rate", dec_to_py(py, fee_rate)?)?;
            f.set_item("fee", ud(py, fee)?)?;
        }
    }
    d.set_item("fields", f)?;
    Ok(d)
}

/// (timestamp, net_value, asset_value, [(token, balance)], [(market, balance tuple)])
fn account_row_tuple<'py>(py: Python<'py>, r: &AccountRow) -> PyResult<Bound<'py, PyTuple>> {
    let assets = PyList::empty(py);
    for (t, v) in &r.asset_balances {
        assets.append((t.name.clone(), t.decimal, dec_to_py(py, v)?))?;
    }
    let markets = PyList::empty(py);
    for (m, b) in &r.market_balances {
        markets.append((m.name.clone(), balance_tuple(py, b)?))?;
    }
    PyTuple::new(
        py,
        [
            ts_to_py(py, r.timestamp)?,
            dec_to_py(py, &r.net_value)?,
            dec_to_py(py, &r.asset_value)?,
            assets.into_any(),
            markets.into_any(),
        ],
    )
}

// ------------------------------------------------------------------ strategy adapter

struct Hooks {
    before_bar: bool,
    on_bar: bool,
    after_bar: bool,
    notify: bool,
}

struct PyAdapter {
    strategy: Py<PyAny>,
    hooks: Hooks,
    markets: Rc<Vec<SnapMarket>>,
    prices: Rc<PriceTable>,
    native_types: Vec<Py<PyAny>>,
    action_factory: Py<PyAny>,
    on_finished: Py<PyAny>,
    print_action: bool,
    legacy: bool,
    /// snapshot shared by before_bar / triggers / on_bar of the current iteration
    snap: Option<(Ts, Py<PySnapshot>)>,
}

impl PyAdapter {
    fn snapshot(&mut self, py: Python<'_>, s: &Snapshot, fresh: bool) -> PyResult<Py<PySnapshot>> {
        if !fresh {
            if let Some((ts, snap)) = &self.snap {
                if *ts == s.ts {
                    return Ok(snap.clone_ref(py));
                }
            }
        }
        let snap = Py::new(
            py,
            PySnapshot {
                row_id: s.row_id,
                ts: s.ts,
                price_row: s.price_row,
                prices: self.prices.clone(),
                markets: self.markets.clone(),
                timestamp_cache: None,
            },
        )?;
        if !fresh {
            self.snap = Some((s.ts, snap.clone_ref(py)));
        }
        Ok(snap)
    }

    fn call(&mut self, name: &str, s: &Snapshot, fresh: bool) -> demeter_core::Result<()> {
        Python::attach(|py| {
            let snap = self
                .snapshot(py, s, fresh)
                .map_err(|e| from_py_err(py, e))?;
            self.strategy
                .bind(py)
                .call_method1(name, (snap,))
                .map(|_| ())
                .map_err(|e| from_py_err(py, e))
        })
    }

    fn native_of<'py>(
        &self,
        py: Python<'py>,
        t: &Bound<'py, PyAny>,
    ) -> PyResult<Option<Bound<'py, NativeTrigger>>> {
        let ty = t.get_type();
        if self.native_types.iter().any(|n| ty.is(n.bind(py))) {
            let n = t.getattr("_native")?;
            return Ok(Some(n.cast_into::<NativeTrigger>()?));
        }
        Ok(None)
    }

    fn triggers(&mut self, py: Python<'_>, s: &Snapshot) -> PyResult<()> {
        let strat = self.strategy.bind(py).clone();
        let triggers = strat.getattr("triggers")?;
        if triggers.len()? == 0 {
            return Ok(());
        }
        let mut snap: Option<Py<PySnapshot>> = None;
        let mut i = 0;
        // index loop over the live list, like python's `for trigger in self._strategy.triggers`
        while i < triggers.len()? {
            let t = triggers.get_item(i)?;
            let fire = match self.native_of(py, &t)? {
                Some(n) => {
                    let mut n = n.borrow_mut();
                    n.legacy = self.legacy;
                    n.when_ts(s.ts)
                }
                None => {
                    // subclasses of built-in triggers keep native state too
                    if let Ok(n) = t.getattr("_native") {
                        if let Ok(n) = n.cast_into::<NativeTrigger>() {
                            n.borrow_mut().legacy = self.legacy;
                        }
                    }
                    let sn = match &snap {
                        Some(x) => x.clone_ref(py),
                        None => {
                            let x = self.snapshot(py, s, false)?;
                            snap = Some(x.clone_ref(py));
                            x
                        }
                    };
                    t.call_method1("when", (sn,))?.is_truthy()?
                }
            };
            if fire {
                let sn = self.snapshot(py, s, false)?;
                t.call_method1("do", (sn,))?;
            }
            i += 1;
        }
        // drop outdated triggers (python rebuilds the list every iteration)
        let triggers = strat.getattr("triggers")?;
        let n = triggers.len()?;
        let kept = PyList::empty(py);
        let mut dt: Option<Bound<'_, PyAny>> = None;
        for i in 0..n {
            let t = triggers.get_item(i)?;
            let out = match self.native_of(py, &t)? {
                Some(nt) => nt.borrow().is_out_date_ts(s.ts),
                None => {
                    if dt.is_none() {
                        dt = Some(ts_to_py(py, s.ts)?);
                    }
                    t.call_method1("is_out_date", (dt.as_ref().unwrap(),))?
                        .is_truthy()?
                }
            };
            if !out {
                kept.append(t)?;
            }
        }
        if kept.len() != n {
            strat.setattr("triggers", kept)?;
        }
        Ok(())
    }
}

impl Strategy for PyAdapter {
    fn initialize(&mut self, _ctx: &Ctx) -> demeter_core::Result<()> {
        Python::attach(|py| {
            self.strategy
                .bind(py)
                .call_method0("initialize")
                .map(|_| ())
                .map_err(|e| from_py_err(py, e))
        })
    }
    fn before_bar(&mut self, _ctx: &Ctx, s: &Snapshot) -> demeter_core::Result<()> {
        if self.hooks.before_bar {
            self.call("before_bar", s, false)?;
        }
        Ok(())
    }
    fn run_triggers(&mut self, _ctx: &Ctx, s: &Snapshot) -> demeter_core::Result<()> {
        Python::attach(|py| self.triggers(py, s).map_err(|e| from_py_err(py, e)))
    }
    fn on_bar(&mut self, _ctx: &Ctx, s: &Snapshot) -> demeter_core::Result<()> {
        if self.hooks.on_bar {
            self.call("on_bar", s, false)?;
        }
        Ok(())
    }
    fn after_bar(&mut self, _ctx: &Ctx, s: &Snapshot) -> demeter_core::Result<()> {
        if self.hooks.after_bar {
            self.call("after_bar", s, true)?;
        }
        Ok(())
    }
    fn notify(&mut self, _ctx: &Ctx, actions: &[Action]) -> demeter_core::Result<()> {
        if !self.hooks.notify && !self.print_action {
            return Ok(());
        }
        Python::attach(|py| -> PyResult<()> {
            for a in actions {
                let obj = self
                    .action_factory
                    .bind(py)
                    .call1((action_to_py(py, a)?,))?;
                if self.hooks.notify {
                    self.strategy.bind(py).call_method1("notify", (&obj,))?;
                }
                if self.print_action {
                    let s = obj.call_method0("get_output_str")?;
                    py.import("builtins")?.getattr("print")?.call1((s,))?;
                }
            }
            Ok(())
        })
        .map_err(|e| Python::attach(|py| from_py_err(py, e)))
    }
    fn finalize(&mut self, _ctx: &Ctx) -> demeter_core::Result<()> {
        Python::attach(|py| -> PyResult<()> {
            self.on_finished.bind(py).call0()?;
            self.strategy.bind(py).call_method0("finalize")?;
            Ok(())
        })
        .map_err(|e| Python::attach(|py| from_py_err(py, e)))
    }
    fn on_error(&mut self, _ctx: &Ctx, s: &Snapshot, e: DemeterError) -> demeter_core::Result<()> {
        Python::attach(|py| {
            let err = to_py_err(e);
            let snap = self
                .snapshot(py, s, false)
                .map_err(|e| from_py_err(py, e))?;
            self.strategy
                .bind(py)
                .call_method1("on_error", (snap, err.value(py)))
                .map(|_| ())
                .map_err(|e| from_py_err(py, e))
        })
    }
}

// ------------------------------------------------------------------ actuator

#[pyclass(name = "ActuatorCore", unsendable, module = "demeter._rs")]
pub struct PyActuatorCore {
    inner: RefCell<Actuator>,
    broker: Shared<Broker>,
    log: Shared<ActionLog>,
    account_status: Shared<Vec<AccountRow>>,
    prices: RefCell<Option<Rc<PriceTable>>>,
    /// settings live outside `inner`, which is mutably borrowed for the whole `run`, so strategy
    /// callbacks can read them while the backtest is running
    legacy: Cell<bool>,
    interval: Cell<i64>,
}

fn running_err() -> PyErr {
    PyRuntimeError::new_err("not allowed while the backtest is running")
}

impl PyActuatorCore {
    fn price_table(&self) -> PyResult<Rc<PriceTable>> {
        self.prices
            .borrow()
            .clone()
            .ok_or_else(|| PyRuntimeError::new_err("token prices is not set"))
    }
}

#[pymethods]
impl PyActuatorCore {
    #[new]
    #[pyo3(signature = (allow_negative_balance=false))]
    fn new(allow_negative_balance: bool) -> Self {
        let act = Actuator::new(allow_negative_balance);
        PyActuatorCore {
            broker: act.broker.clone(),
            log: act.log.clone(),
            account_status: act.account_status.clone(),
            prices: RefCell::new(None),
            legacy: Cell::new(act.compat.legacy_quirks),
            interval: Cell::new(act.interval_secs),
            inner: RefCell::new(act),
        }
    }
    fn broker(&self) -> PyBrokerCore {
        PyBrokerCore {
            inner: self.broker.clone(),
        }
    }
    fn add_market(&self, market: &PyMarketCore) -> PyResult<()> {
        let a = self.inner.try_borrow().map_err(|_| running_err())?;
        market.inner.borrow_mut().compat.legacy_quirks = self.legacy.get();
        a.add_market(market.inner.clone()).py()
    }
    #[getter]
    fn interval_secs(&self) -> i64 {
        self.interval.get()
    }
    #[setter]
    fn set_interval_secs(&self, v: i64) -> PyResult<()> {
        self.inner
            .try_borrow_mut()
            .map_err(|_| running_err())?
            .interval_secs = v;
        self.interval.set(v);
        Ok(())
    }
    #[getter]
    fn legacy_quirks(&self) -> bool {
        self.legacy.get()
    }
    #[setter]
    fn set_legacy_quirks(&self, v: bool) -> PyResult<()> {
        let mut a = self.inner.try_borrow_mut().map_err(|_| running_err())?;
        a.compat.legacy_quirks = v;
        self.legacy.set(v);
        for (_, m) in &self.broker.borrow().markets {
            m.borrow_mut().compat.legacy_quirks = v;
        }
        Ok(())
    }
    /// prices from Arrow IPC: a `timestamp` column plus one column per token
    fn set_price_ipc(&self, ipc: &[u8], quote_name: &str, quote_decimal: u32) -> PyResult<()> {
        use polars::prelude::*;
        let df = data::frame_from_ipc(ipc).py()?;
        let err = |e: PolarsError| PyValueError::new_err(e.to_string());
        let ts: Vec<Ts> = df
            .column("timestamp")
            .map_err(err)?
            .cast(&DataType::Datetime(TimeUnit::Milliseconds, None))
            .map_err(err)?
            .cast(&DataType::Int64)
            .map_err(err)?
            .i64()
            .map_err(err)?
            .iter()
            .map(|v| v.unwrap_or(0) / 1000)
            .collect();
        let mut names = vec![];
        let mut cols = vec![];
        for c in df.columns() {
            if c.name().as_str() == "timestamp" {
                continue;
            }
            let s = c.cast(&DataType::String).map_err(err)?;
            let v: Vec<Dec> = s
                .str()
                .map_err(err)?
                .iter()
                .map(|x| {
                    x.map(|x| dec::parse_lossy(x).unwrap_or(Dec::NAN))
                        .unwrap_or(Dec::NAN)
                })
                .collect();
            names.push(c.name().to_string());
            cols.push(v);
        }
        let table = PriceTable::new(ts, names, cols).py()?;
        let mut a = self.inner.try_borrow_mut().map_err(|_| running_err())?;
        a.set_price(table, TokenInfo::new(quote_name, quote_decimal))
            .py()?;
        *self.prices.borrow_mut() = a.prices.clone();
        Ok(())
    }
    /// fast path of `set_price(market.get_price_from_data())`
    fn set_price_from_market(&self, market: &PyMarketCore) -> PyResult<()> {
        let (table, quote) = {
            let m = market.inner.borrow();
            let d = m.data().py()?;
            let (names, cols) = data::price_from_data(d, &m.pool);
            (
                PriceTable::new(d.ts.clone(), names, cols).py()?,
                m.pool.quote_token.clone(),
            )
        };
        let mut a = self.inner.try_borrow_mut().map_err(|_| running_err())?;
        a.set_price(table, quote).py()?;
        *self.prices.borrow_mut() = a.prices.clone();
        Ok(())
    }
    fn prices_ipc<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        let p = self.price_table()?;
        let mut df = price_frame(&p.ts, &p.tokens, &p.cols)?;
        Ok(PyBytes::new(py, &data::frame_to_ipc(&mut df).py()?))
    }
    fn has_prices(&self) -> bool {
        self.prices.borrow().is_some()
    }

    /// Run the backtest with a python strategy.
    #[pyo3(signature = (strategy, markets, native_types, hooks, action_factory, on_finished, print_action=false))]
    #[allow(clippy::too_many_arguments)]
    fn run(
        &self,
        py: Python<'_>,
        strategy: Py<PyAny>,
        markets: Vec<(Py<PyAny>, PyRef<'_, PyMarketCore>)>,
        native_types: Vec<Py<PyAny>>,
        hooks: &Bound<'_, PyDict>,
        action_factory: Py<PyAny>,
        on_finished: Py<PyAny>,
        print_action: bool,
    ) -> PyResult<()> {
        let flag = |k: &str| -> PyResult<bool> {
            Ok(hooks
                .get_item(k)?
                .map(|v| v.is_truthy())
                .transpose()?
                .unwrap_or(true))
        };
        let snap_markets: Vec<SnapMarket> = markets
            .iter()
            .map(|(k, m)| -> PyResult<SnapMarket> {
                Ok(SnapMarket {
                    key: k.clone_ref(py),
                    name: k.bind(py).getattr("name")?.extract()?,
                    market: m.inner.clone(),
                })
            })
            .collect::<PyResult<_>>()?;
        let mut act = self
            .inner
            .try_borrow_mut()
            .map_err(|_| PyRuntimeError::new_err("backtest is already running"))?;
        let legacy = act.compat.legacy_quirks;
        for (_, m) in &act.broker.borrow().markets {
            m.borrow_mut().compat = act.compat;
        }
        // the price table may be replaced (resample) inside run, so give the adapter the final
        // one lazily: resampling happens before initialize, prices are read per iteration.
        let prices = match (&act.prices, act.interval_secs) {
            (Some(p), 60) => p.clone(),
            (Some(p), secs) => Rc::new(p.resample(secs).py()?),
            (None, _) => Rc::new(PriceTable::default()),
        };
        let mut adapter = PyAdapter {
            strategy,
            hooks: Hooks {
                before_bar: flag("before_bar")?,
                on_bar: flag("on_bar")?,
                after_bar: flag("after_bar")?,
                notify: flag("notify")?,
            },
            markets: Rc::new(snap_markets),
            prices,
            native_types,
            action_factory,
            on_finished,
            print_action,
            legacy,
            snap: None,
        };
        let result = act.run(&mut adapter);
        *self.prices.borrow_mut() = act.prices.clone();
        result.py()
    }

    #[getter]
    fn finished(&self) -> bool {
        self.inner.try_borrow().map(|a| a.finished).unwrap_or(false)
    }
    fn account_status_len(&self) -> usize {
        self.account_status.borrow().len()
    }
    fn account_status_row<'py>(&self, py: Python<'py>, i: usize) -> PyResult<Bound<'py, PyTuple>> {
        let rows = self.account_status.borrow();
        let r = rows
            .get(i)
            .ok_or_else(|| pyo3::exceptions::PyIndexError::new_err(i))?;
        account_row_tuple(py, r)
    }
    fn init_account_status<'py>(&self, py: Python<'py>) -> PyResult<Option<Bound<'py, PyTuple>>> {
        match self.inner.try_borrow() {
            Ok(a) => a
                .init_account_status
                .as_ref()
                .map(|r| account_row_tuple(py, r))
                .transpose(),
            Err(_) => Ok(None),
        }
    }
    /// account status history as Arrow IPC (flat `l1|l2` column names)
    fn account_status_ipc<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        let rows = self.account_status.borrow();
        let prices = self.prices.borrow().clone();
        let mut df = demeter_core::actuator::account_status_frame(&rows, prices.as_deref()).py()?;
        Ok(PyBytes::new(py, &data::frame_to_ipc(&mut df).py()?))
    }
    fn actions_len(&self) -> usize {
        self.log.borrow().actions.len()
    }
    #[pyo3(signature = (start=0))]
    fn actions<'py>(&self, py: Python<'py>, start: usize) -> PyResult<Vec<Bound<'py, PyDict>>> {
        let log = self.log.borrow();
        log.actions
            .iter()
            .skip(start)
            .map(|a| action_to_py(py, a))
            .collect()
    }
    fn logs<'py>(&self, py: Python<'py>) -> PyResult<Vec<(Bound<'py, PyAny>, String, i32)>> {
        let log = self.log.borrow();
        log.logs
            .iter()
            .map(|l| Ok((ts_to_py(py, l.time)?, l.message.clone(), l.level)))
            .collect()
    }
    #[pyo3(signature = (message, type_name=None))]
    fn comment_last_action(&self, message: &str, type_name: Option<&str>) {
        self.log
            .borrow_mut()
            .comment_last_action(message, type_name);
    }
    fn current_timestamp<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        ts_to_py(py, self.log.borrow().current_ts)
    }
}
