//! Conversions between python objects and core types, and error mapping.

use demeter_core::dec::{self, Dec};
use demeter_core::types::{naive_to_ts, ts_to_naive, Ts};
use demeter_core::DemeterError;
use pyo3::exceptions::{PyAssertionError, PyIOError, PyKeyError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyBool, PyFloat, PyInt, PyType};
use ruint::aliases::U256;
use std::str::FromStr;

static DECIMAL: PyOnceLock<Py<PyType>> = PyOnceLock::new();
static DEMETER_ERROR: PyOnceLock<Py<PyType>> = PyOnceLock::new();

/// python `decimal.Decimal` class
pub fn decimal_type(py: Python<'_>) -> PyResult<&Bound<'_, PyType>> {
    DECIMAL.import(py, "decimal", "Decimal")
}

/// Accepts int, float, Decimal (and subclasses such as UnitDecimal) or numeric strings, like
/// python's `@float_param_formatter` (`Decimal(str(x))`).
pub fn dec_from_py(obj: &Bound<'_, PyAny>) -> PyResult<Dec> {
    let s = if obj.is_instance_of::<PyFloat>() {
        // `{}` is the shortest round-trip form, like python repr(float); numpy float64 (a float
        // subclass whose repr is "np.float64(...)") is handled the same way
        format!("{}", obj.extract::<f64>()?)
    } else if obj.is_instance_of::<PyBool>() {
        if obj.extract::<bool>()? {
            "1".into()
        } else {
            "0".into()
        }
    } else if obj.is_instance_of::<PyInt>() {
        if let Ok(v) = obj.extract::<i64>() {
            return Ok(dec::from_i64(v));
        }
        obj.str()?.to_string()
    } else {
        obj.str()?.to_string()
    };
    dec::parse_lossy(&s).map_err(PyValueError::new_err)
}

pub fn opt_dec(obj: Option<&Bound<'_, PyAny>>) -> PyResult<Option<Dec>> {
    match obj {
        None => Ok(None),
        Some(o) if o.is_none() => Ok(None),
        Some(o) => dec_from_py(o).map(Some),
    }
}

/// Significant digits of Decimals handed to python: python demeter runs with
/// `getcontext().prec = 35`, so values are rounded to what python itself would have produced.
pub const PY_DIGITS: u32 = 35;

pub fn dec_to_py<'py>(py: Python<'py>, d: &Dec) -> PyResult<Bound<'py, PyAny>> {
    decimal_type(py)?.call1((dec::to_py_string(&dec::round_sig(d, PY_DIGITS)),))
}

pub fn u256_from_py(obj: &Bound<'_, PyAny>) -> PyResult<U256> {
    let s = obj.str()?.to_string();
    let s = s.split('.').next().unwrap_or("0").trim().to_string();
    U256::from_str(&s).map_err(|e| PyValueError::new_err(format!("invalid uint256 '{s}': {e}")))
}

pub fn opt_u256(obj: Option<&Bound<'_, PyAny>>) -> PyResult<Option<U256>> {
    match obj {
        None => Ok(None),
        Some(o) if o.is_none() => Ok(None),
        Some(o) => u256_from_py(o).map(Some),
    }
}

/// Python int/float/Decimal liquidity value to u128 (truncating like `int()`).
pub fn u128_from_py(obj: &Bound<'_, PyAny>) -> PyResult<u128> {
    if let Ok(v) = obj.extract::<u128>() {
        return Ok(v);
    }
    let d = dec_from_py(obj)?;
    let v = dec::trunc_to_i128(&d);
    if v < 0 {
        return Err(PyValueError::new_err("liquidity should large than 0"));
    }
    Ok(v as u128)
}

pub fn opt_u128(obj: Option<&Bound<'_, PyAny>>) -> PyResult<Option<u128>> {
    match obj {
        None => Ok(None),
        Some(o) if o.is_none() => Ok(None),
        Some(o) => u128_from_py(o).map(Some),
    }
}

/// Integral tick from an int or an integral float/Decimal (pandas keeps ticks as float64).
pub fn tick_from_py(obj: &Bound<'_, PyAny>) -> PyResult<i32> {
    if let Ok(v) = obj.extract::<i64>() {
        return Ok(v as i32);
    }
    let d = dec_from_py(obj)?;
    Ok(dec::trunc_to_i128(&d) as i32)
}

pub fn ts_to_py<'py>(py: Python<'py>, ts: Ts) -> PyResult<Bound<'py, PyAny>> {
    Ok(ts_to_naive(ts).into_pyobject(py)?.into_any())
}

/// datetime / pandas Timestamp / int seconds -> Ts
pub fn ts_from_py(obj: &Bound<'_, PyAny>) -> PyResult<Ts> {
    if let Ok(v) = obj.extract::<i64>() {
        return Ok(v);
    }
    if let Ok(dt) = obj.extract::<chrono::NaiveDateTime>() {
        return Ok(naive_to_ts(&dt));
    }
    // pandas Timestamp -> python datetime
    if let Ok(m) = obj.getattr("to_pydatetime") {
        let dt: chrono::NaiveDateTime = m.call0()?.extract()?;
        return Ok(naive_to_ts(&dt));
    }
    if let Ok(d) = obj.extract::<chrono::NaiveDate>() {
        return Ok(naive_to_ts(&d.and_hms_opt(0, 0, 0).unwrap()));
    }
    Err(PyValueError::new_err("expected a datetime"))
}

/// core error -> python exception
pub fn to_py_err(e: DemeterError) -> PyErr {
    match e {
        DemeterError::Demeter(m) => {
            Python::attach(
                |py| match DEMETER_ERROR.import(py, "demeter._typing", "DemeterError") {
                    Ok(t) => match t.call1((m.clone(),)) {
                        Ok(inst) => PyErr::from_value(inst),
                        Err(e) => e,
                    },
                    Err(_) => PyRuntimeError::new_err(m),
                },
            )
        }
        DemeterError::Assertion(m) => PyAssertionError::new_err(m),
        DemeterError::Data(m) => {
            if let Some(rest) = m.strip_prefix("KeyError: ") {
                PyKeyError::new_err(rest.to_string())
            } else if m.starts_with("resource file") {
                PyIOError::new_err(m)
            } else {
                PyValueError::new_err(m)
            }
        }
        DemeterError::External {
            payload, message, ..
        } => match payload.downcast::<PyErr>() {
            Ok(e) => *e,
            Err(_) => PyRuntimeError::new_err(message),
        },
    }
}

/// python exception raised inside a callback -> core error
pub fn from_py_err(py: Python<'_>, e: PyErr) -> DemeterError {
    let recoverable =
        e.is_instance_of::<PyRuntimeError>(py) || e.is_instance_of::<PyAssertionError>(py);
    DemeterError::External {
        message: e.to_string(),
        recoverable,
        payload: Box::new(e),
    }
}

pub trait IntoPyResult<T> {
    fn py(self) -> PyResult<T>;
}

impl<T> IntoPyResult<T> for demeter_core::Result<T> {
    fn py(self) -> PyResult<T> {
        self.map_err(to_py_err)
    }
}
