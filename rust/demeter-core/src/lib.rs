//! Rust core of the demeter DeFi backtesting engine (Uniswap v3 only).
//!
//! Module map (python origin in brackets):
//! - [`dec`]: decimal helpers (`decimal.Decimal` at 35 digits -> `fastnum::D128`)
//! - [`math`]: tick / price / liquidity math (`uniswap/liquitidy_math.py`, `uniswap/helper.py`)
//! - [`data`]: minute data loading, filling and resampling (`uniswap/helper.py`, `uniswap/data.py`)
//! - [`uniswap`]: the LP market (`uniswap/market.py`, `uniswap/core.py`)
//! - [`broker`]: wallet, broker, account status (`broker/`)
//! - [`trigger`]: built-in triggers (`strategy/trigger.py`)
//! - [`actuator`]: the backtest loop and the `Strategy` trait (`core/actuator.py`, `strategy/strategy.py`)
//! - [`metrics`]: performance metrics (`result/metrics/`)

pub mod actions;
pub mod actuator;
pub mod broker;
pub mod data;
pub mod dec;
pub mod error;
pub mod math;
pub mod trigger;
pub mod types;
pub mod uniswap;

pub use dec::Dec;
pub use error::{DemeterError, Result};
