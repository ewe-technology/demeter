use std::any::Any;
use std::fmt;

/// Errors raised by the engine.
///
/// The python engine distinguishes `DemeterError` (a `RuntimeError`) and `AssertionError`: the
/// actuator hands both to `strategy.on_error`, anything else aborts the backtest. `External`
/// carries errors from the host (e.g. a python exception raised inside a strategy callback).
pub enum DemeterError {
    /// python `DemeterError(RuntimeError)`
    Demeter(String),
    /// python `AssertionError` (e.g. insufficient balance, `require(...)`)
    Assertion(String),
    /// file / data loading problems (python raises IOError / ValueError)
    Data(String),
    /// error from the host language; `recoverable` mirrors "is RuntimeError or AssertionError"
    External {
        message: String,
        recoverable: bool,
        payload: Box<dyn Any>,
    },
}

pub type Result<T> = std::result::Result<T, DemeterError>;

impl DemeterError {
    pub fn demeter(msg: impl Into<String>) -> Self {
        DemeterError::Demeter(msg.into())
    }
    pub fn assertion(msg: impl Into<String>) -> Self {
        DemeterError::Assertion(msg.into())
    }
    pub fn data(msg: impl Into<String>) -> Self {
        DemeterError::Data(msg.into())
    }
    /// Would python's `except (RuntimeError, AssertionError)` in `Actuator.run` catch this?
    pub fn is_recoverable(&self) -> bool {
        match self {
            DemeterError::Demeter(_) | DemeterError::Assertion(_) => true,
            DemeterError::Data(_) => false,
            DemeterError::External { recoverable, .. } => *recoverable,
        }
    }
    pub fn message(&self) -> String {
        match self {
            DemeterError::Demeter(m) | DemeterError::Assertion(m) | DemeterError::Data(m) => {
                m.clone()
            }
            DemeterError::External { message, .. } => message.clone(),
        }
    }
}

impl fmt::Debug for DemeterError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            DemeterError::Demeter(m) => write!(f, "DemeterError({m})"),
            DemeterError::Assertion(m) => write!(f, "AssertionError({m})"),
            DemeterError::Data(m) => write!(f, "DataError({m})"),
            DemeterError::External { message, .. } => write!(f, "External({message})"),
        }
    }
}

impl fmt::Display for DemeterError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.message())
    }
}

impl std::error::Error for DemeterError {}

/// python's `require(condition, msg)`: raises AssertionError.
pub fn require(cond: bool, msg: &str) -> Result<()> {
    if cond {
        Ok(())
    } else {
        Err(DemeterError::assertion(msg))
    }
}
