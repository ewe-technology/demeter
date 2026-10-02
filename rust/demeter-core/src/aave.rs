//! Aave v3 market, ported from `demeter/aave/` (`market.py`, `core.py`, `helper.py`).
//!
//! Supplies and borrows are kept as base amounts (amount / index) and valued with the liquidity
//! index / variable borrow index of the current minute. Rates and indexes come from the market
//! data (one row per minute per token), prices from the actuator's price table, in USD.
//!
//! The python market caches token values between state changes and a few results depend on when
//! those caches are refreshed, so the caches are reproduced here (`Caches`). With
//! `legacy_quirks = false` every state change refreshes all of them.

use crate::actions::{ActionKind, ActionLog, Ud};
use crate::actuator::PriceTable;
use crate::broker::{Shared, Wallet};
use crate::dec::{self, Dec};
use crate::error::{require, DemeterError, Result};
use crate::types::{ts_to_string, AaveBalance, EngineCompat, MarketInfo, TokenInfo, Ts};
use chrono::{Duration, NaiveDate, NaiveDateTime};
use polars::prelude::*;
use std::cell::RefCell;
use std::collections::HashMap;
use std::path::Path;
use std::rc::Rc;
use std::sync::Arc;

/// python `AaveV3CoreLib.SECONDS_IN_A_YEAR`
pub const SECONDS_IN_A_YEAR: i32 = 31_536_000;

/// Columns every token needs in the market data (python `REQUIRED_DATA_COLUMN`).
pub const REQUIRED_DATA_COLUMN: [&str; 5] = [
    "liquidity_rate",
    "stable_borrow_rate",
    "variable_borrow_rate",
    "liquidity_index",
    "variable_borrow_index",
];

fn lit(s: &str) -> Dec {
    dec::parse_lossy(s).expect("valid decimal literal")
}

fn key_error(name: &str) -> DemeterError {
    DemeterError::Data(format!("KeyError: {name}"))
}

/// python raises `decimal.DivisionByZero` (not caught by the actuator)
fn div(a: Dec, b: Dec) -> Result<Dec> {
    if b.is_zero() {
        return Err(DemeterError::data(
            "decimal.DivisionByZero: [<class 'decimal.DivisionByZero'>]",
        ));
    }
    Ok(a / b)
}

fn sum(v: &[(TokenInfo, Dec)]) -> Dec {
    v.iter().fold(dec::zero(), |a, (_, x)| a + *x)
}

fn find<'a, T>(v: &'a [(TokenInfo, T)], k: &TokenInfo) -> Option<&'a T> {
    v.iter().find(|(t, _)| t == k).map(|(_, x)| x)
}

// ------------------------------------------------------------------ core lib

/// python `AaveV3CoreLib.rate_to_apy`: `(1 + rate / SECONDS_IN_A_YEAR) ** SECONDS_IN_A_YEAR - 1`
pub fn rate_to_apy(rate: &Dec) -> Dec {
    dec::py_compound(rate, SECONDS_IN_A_YEAR)
}

/// python `AaveV3CoreLib.safe_div`: infinity when `b` is 0
pub fn safe_div(a: Dec, b: Dec) -> Dec {
    if b.is_zero() {
        Dec::INFINITY
    } else {
        a / b
    }
}

/// python `AaveV3CoreLib.safe_div_zero`: 0 when `b` is 0
pub fn safe_div_zero(a: Dec, b: Dec) -> Dec {
    if b.is_zero() {
        dec::zero()
    } else if a.is_zero() {
        // python keeps the exponent of 0 / b at exp(a) - exp(b) (e.g. 0E-8 / 126.1250 = 0.0000)
        let (ea, eb) = (dec::to_parts(&a).2, dec::to_parts(&b).2);
        dec::quantize(&dec::zero(), (eb - ea) as i16)
    } else {
        a / b
    }
}

/// python `x.quantize(Decimal("0.0001"))`; `AaveV3CoreLib.safe_rounding` is the same here
/// because quantize keeps NaN and infinity.
fn q4(d: Dec) -> Dec {
    dec::quantize(&d, 4)
}

/// python `helper.sub_base_amount`: below one wei (1e-18) the base amount is 0.
fn sub_base_amount(old: Dec, value: Dec) -> Dec {
    let new = old - value;
    // python compares with the float `1e-18 - 1e-27`
    if new < dec::from_f64_exact(1e-18 - 1e-27) {
        dec::zero()
    } else {
        new
    }
}

// ------------------------------------------------------------------ risk parameters

/// One row of the risk parameter csv (python `RiskParameter`), scaled like python: ratios
/// / 10000, rates / 1e27, liquidation bonus as the part above 1.
#[derive(Clone, Debug)]
pub struct RiskParameter {
    pub symbol: String,
    pub usage_as_collateral_enabled: bool,
    pub base_ltv_as_collateral: Dec,
    pub reserve_liquidation_threshold: Dec,
    pub reserve_liquidation_bonus: Dec,
    pub reserve_factor: Dec,
    pub borrowing_enabled: bool,
    pub optimal_usage_ratio: Dec,
    pub variable_rate_slope1: Dec,
    pub variable_rate_slope2: Dec,
    pub base_variable_borrow_rate: Dec,
    pub supply_cap: Dec,
    pub borrow_cap: Dec,
    pub borrowable_in_isolation: bool,
    pub flash_loan_enabled: bool,
}

/// Risk parameters of a chain, indexed by symbol (python `risk_parameters` DataFrame).
#[derive(Clone, Debug, Default)]
pub struct RiskParameters {
    pub rows: Vec<RiskParameter>,
}

impl RiskParameters {
    /// python `risk_parameters.loc[symbol]`
    pub fn get(&self, symbol: &str) -> Result<&RiskParameter> {
        self.rows
            .iter()
            .find(|r| r.symbol == symbol)
            .ok_or_else(|| key_error(symbol))
    }

    pub fn contains(&self, symbol: &str) -> bool {
        self.rows.iter().any(|r| r.symbol == symbol)
    }
}

/// python `helper.load_risk_parameter`: the csv downloaded with `demeter-fetch aave`.
pub fn load_risk_parameters(path: &str) -> Result<RiskParameters> {
    if !Path::new(path).exists() {
        return Err(DemeterError::demeter(format!(
            "risk parameter file {path} not exist, please download csv with 'demeter-fetch aave -h'"
        )));
    }
    let err = |e: PolarsError| DemeterError::data(format!("{path}: {e}"));
    let df = CsvReadOptions::default()
        .with_has_header(true)
        .with_infer_schema_length(Some(0))
        .try_into_reader_with_file_path(Some(path.into()))
        .map_err(err)?
        .finish()
        .map_err(err)?;
    let col = |name: &str| -> Result<StringChunked> {
        Ok(df
            .column(name)
            .map_err(|_| key_error(name))?
            .str()
            .map_err(err)?
            .clone())
    };
    let get = |c: &StringChunked, i: usize| c.get(i).unwrap_or("").trim().to_string();
    // empty cells are NaN, like pandas
    let num = |c: &StringChunked, i: usize| -> Result<Dec> {
        let s = get(c, i);
        if s.is_empty() {
            return Ok(Dec::NAN);
        }
        dec::parse_lossy(&s).map_err(|e| DemeterError::data(format!("{path}: {e}")))
    };
    let flag = |c: &StringChunked, i: usize| -> bool {
        matches!(get(c, i).to_ascii_lowercase().as_str(), "true" | "1")
    };
    let symbol = col("symbol")?;
    let name = col("name")?;
    let collateral = col("usageAsCollateralEnabled")?;
    let ltv = col("baseLTVasCollateral")?;
    let lt = col("reserveLiquidationThreshold")?;
    let bonus = col("reserveLiquidationBonus")?;
    let factor = col("reserveFactor")?;
    let borrowing = col("borrowingEnabled")?;
    let optimal = col("optimalUsageRatio")?;
    let slope1 = col("variableRateSlope1")?;
    let slope2 = col("variableRateSlope2")?;
    let base_rate = col("baseVariableBorrowRate")?;
    let supply_cap = col("supplyCap")?;
    let borrow_cap = col("borrowCap")?;
    let isolation = col("borrowableInIsolation")?;
    let flash = col("flashLoanEnabled")?;
    let (e4, e27) = (dec::from_i64(10_000), dec::pow10(27));
    // NaN stays NaN (fastnum traps arithmetic on NaN)
    let scaled = |v: Dec, shift: Dec, div: Dec| {
        if v.is_nan() {
            v
        } else {
            (v - shift) / div
        }
    };
    let zero = dec::zero();
    let mut rows = Vec::with_capacity(df.height());
    for i in 0..df.height() {
        let mut sym = get(&symbol, i);
        if sym == "USDC" {
            // python tells native USDC and bridged USDC.e apart by name
            sym = if get(&name, i) == "USD Coin" {
                "USDC".into()
            } else {
                "USDC.E".into()
            };
        }
        rows.push(RiskParameter {
            symbol: sym,
            usage_as_collateral_enabled: flag(&collateral, i),
            base_ltv_as_collateral: scaled(num(&ltv, i)?, zero, e4),
            reserve_liquidation_threshold: scaled(num(&lt, i)?, zero, e4),
            reserve_liquidation_bonus: scaled(num(&bonus, i)?, e4, e4),
            reserve_factor: scaled(num(&factor, i)?, zero, e4),
            borrowing_enabled: flag(&borrowing, i),
            optimal_usage_ratio: scaled(num(&optimal, i)?, zero, e27),
            variable_rate_slope1: scaled(num(&slope1, i)?, zero, e27),
            variable_rate_slope2: scaled(num(&slope2, i)?, zero, e27),
            base_variable_borrow_rate: scaled(num(&base_rate, i)?, zero, e27),
            supply_cap: num(&supply_cap, i)?,
            borrow_cap: num(&borrow_cap, i)?,
            borrowable_in_isolation: flag(&isolation, i),
            flash_loan_enabled: flag(&flash, i),
        });
    }
    Ok(RiskParameters { rows })
}

/// python `AaveV3CoreLib.max_ltv`
fn max_ltv_of(collaterals: &[(TokenInfo, Dec)], rp: &RiskParameters) -> Result<Dec> {
    let mut all = dec::zero();
    for (t, s) in collaterals {
        all += *s * rp.get(&t.name)?.base_ltv_as_collateral;
    }
    Ok(safe_div(all, sum(collaterals)))
}

/// python `AaveV3CoreLib.health_factor`
fn health_factor_of(
    collaterals: &[(TokenInfo, Dec)],
    borrows: &[(TokenInfo, Dec)],
    rp: &RiskParameters,
) -> Result<Dec> {
    let mut a = dec::zero();
    for (t, s) in collaterals {
        a += *s * rp.get(&t.name)?.reserve_liquidation_threshold;
    }
    Ok(safe_div(a, sum(borrows)))
}

/// python `AaveV3CoreLib.total_liquidation_threshold`
fn total_liquidation_threshold_of(
    collaterals: &[(TokenInfo, Dec)],
    rp: &RiskParameters,
) -> Result<Dec> {
    let mut sum_amount = dec::zero();
    let mut rate = dec::zero();
    for (t, s) in collaterals {
        sum_amount += *s;
        rate += *s * rp.get(&t.name)?.reserve_liquidation_threshold;
    }
    Ok(safe_div(rate, sum_amount))
}

// ------------------------------------------------------------------ data

/// Pool status of one token in one minute (python `AaveTokenStatus`).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct AaveTokenStatus {
    pub liquidity_rate: Dec,
    pub stable_borrow_rate: Dec,
    pub variable_borrow_rate: Dec,
    pub liquidity_index: Dec,
    pub variable_borrow_index: Dec,
}

impl AaveTokenStatus {
    /// values in `REQUIRED_DATA_COLUMN` order
    pub fn from_values(v: [Dec; 5]) -> Self {
        AaveTokenStatus {
            liquidity_rate: v[0],
            stable_borrow_rate: v[1],
            variable_borrow_rate: v[2],
            liquidity_index: v[3],
            variable_borrow_index: v[4],
        }
    }

    /// values in `REQUIRED_DATA_COLUMN` order
    pub fn values(&self) -> [Dec; 5] {
        [
            self.liquidity_rate,
            self.stable_borrow_rate,
            self.variable_borrow_rate,
            self.liquidity_index,
            self.variable_borrow_index,
        ]
    }

    pub fn get(&self, column: &str) -> Option<Dec> {
        REQUIRED_DATA_COLUMN
            .iter()
            .position(|c| *c == column)
            .map(|i| self.values()[i])
    }
}

/// Minute data of one token.
#[derive(Clone, Debug, Default)]
pub struct AaveTokenData {
    /// upper case token name
    pub name: String,
    /// required columns present in the source (python `(token, col) in data.columns`)
    pub columns: Vec<String>,
    /// aligned with `AaveData::ts`; None where a value is missing (python NaN)
    pub rows: Vec<Option<AaveTokenStatus>>,
}

/// Market data of the aave market: all tokens on one time index (python: a DataFrame with
/// (token, column) MultiIndex columns). Columns other than `REQUIRED_DATA_COLUMN` are not kept.
#[derive(Clone, Debug, Default)]
pub struct AaveData {
    pub ts: Vec<Ts>,
    pub tokens: Vec<AaveTokenData>,
    grid: Option<(Ts, Ts)>,
    lookup: HashMap<Ts, usize>,
}

impl AaveData {
    /// Rows are sorted by timestamp (resample and the backtest index need ascending time).
    pub fn new(mut ts: Vec<Ts>, mut tokens: Vec<AaveTokenData>) -> Result<Self> {
        if tokens.iter().any(|t| t.rows.len() != ts.len()) {
            return Err(DemeterError::data(
                "aave data columns do not match the index",
            ));
        }
        if ts.windows(2).any(|w| w[0] > w[1]) {
            let mut order: Vec<usize> = (0..ts.len()).collect();
            order.sort_by_key(|i| ts[*i]);
            ts = order.iter().map(|i| ts[*i]).collect();
            for t in tokens.iter_mut() {
                t.rows = order.iter().map(|i| t.rows[*i]).collect();
            }
        }
        let mut d = AaveData {
            ts,
            tokens,
            grid: None,
            lookup: HashMap::new(),
        };
        d.index();
        Ok(d)
    }

    fn index(&mut self) {
        self.grid = None;
        self.lookup.clear();
        if self.ts.len() >= 2 {
            let step = self.ts[1] - self.ts[0];
            if step > 0 && self.ts.windows(2).all(|w| w[1] - w[0] == step) {
                self.grid = Some((self.ts[0], step));
                return;
            }
        } else if self.ts.len() == 1 {
            self.grid = Some((self.ts[0], 60));
            return;
        }
        for (i, t) in self.ts.iter().enumerate() {
            self.lookup.insert(*t, i);
        }
    }

    pub fn len(&self) -> usize {
        self.ts.len()
    }

    pub fn is_empty(&self) -> bool {
        self.ts.is_empty()
    }

    pub fn row_of(&self, ts: Ts) -> Option<usize> {
        match self.grid {
            Some((start, step)) => {
                if ts < start || (ts - start) % step != 0 {
                    return None;
                }
                let r = ((ts - start) / step) as usize;
                (r < self.ts.len()).then_some(r)
            }
            None => self.lookup.get(&ts).copied(),
        }
    }

    pub fn token(&self, name: &str) -> Option<&AaveTokenData> {
        self.tokens.iter().find(|t| t.name == name)
    }

    /// python `(token, column) in data.columns`
    pub fn has_column(&self, token: &str, column: &str) -> bool {
        self.token(token)
            .map(|t| t.columns.iter().any(|c| c == column))
            .unwrap_or(false)
    }

    /// python `data.loc[ts][token]`
    pub fn status(&self, row: usize, token: &str) -> Result<AaveTokenStatus> {
        let t = self.token(token).ok_or_else(|| key_error(token))?;
        t.rows.get(row).copied().flatten().ok_or_else(|| {
            DemeterError::data(format!(
                "aave data of {token} at {} is missing (NaN)",
                ts_to_string(self.ts[row])
            ))
        })
    }

    /// python `pd.concat([data, token_data], axis="columns")`: outer join on the timestamps.
    pub fn with_token(&self, token: AaveTokenData, ts: &[Ts]) -> Result<AaveData> {
        if self.token(&token.name).is_some() {
            return Err(DemeterError::demeter(format!(
                "{} has already set to data",
                token.name
            )));
        }
        if token.rows.len() != ts.len() {
            return Err(DemeterError::data(
                "aave data columns do not match the index",
            ));
        }
        let has_dup = |v: &[Ts]| {
            let mut s = v.to_vec();
            s.sort_unstable();
            s.windows(2).any(|w| w[0] == w[1])
        };
        if has_dup(ts) || (!self.tokens.is_empty() && has_dup(&self.ts)) {
            return Err(DemeterError::data(
                "cannot reindex on an axis with duplicate labels",
            ));
        }
        let new_ts: Vec<Ts> = if self.tokens.is_empty() || self.ts == ts {
            ts.to_vec()
        } else {
            let mut all: Vec<Ts> = self.ts.iter().chain(ts.iter()).copied().collect();
            all.sort_unstable();
            all.dedup();
            all
        };
        let realign = |old_ts: &[Ts], rows: &[Option<AaveTokenStatus>]| {
            if old_ts == new_ts.as_slice() {
                return rows.to_vec();
            }
            let pos: HashMap<Ts, usize> = old_ts.iter().enumerate().map(|(i, t)| (*t, i)).collect();
            new_ts
                .iter()
                .map(|t| pos.get(t).and_then(|i| rows[*i]))
                .collect()
        };
        let mut tokens: Vec<AaveTokenData> = self
            .tokens
            .iter()
            .map(|t| AaveTokenData {
                name: t.name.clone(),
                columns: t.columns.clone(),
                rows: realign(&self.ts, &t.rows),
            })
            .collect();
        tokens.push(AaveTokenData {
            rows: realign(ts, &token.rows),
            ..token
        });
        AaveData::new(new_ts, tokens)
    }

    /// python `data.resample(freq).first()`: bins start at midnight of the first day, every bin
    /// between the first and the last row is kept, each takes the first non-missing row.
    pub fn resample(&self, interval_secs: i64) -> Result<AaveData> {
        if interval_secs <= 60 || self.is_empty() {
            return Ok(self.clone());
        }
        let day0 = self.ts[0] - self.ts[0].rem_euclid(86400);
        let bin_of = |t: Ts| day0 + (t - day0).div_euclid(interval_secs) * interval_secs;
        let first_bin = bin_of(self.ts[0]);
        let last_bin = bin_of(*self.ts.last().unwrap());
        let n = ((last_bin - first_bin) / interval_secs + 1) as usize;
        let ts: Vec<Ts> = (0..n)
            .map(|i| first_bin + i as i64 * interval_secs)
            .collect();
        let tokens = self
            .tokens
            .iter()
            .map(|t| {
                let mut rows: Vec<Option<AaveTokenStatus>> = vec![None; n];
                for (i, tt) in self.ts.iter().enumerate() {
                    let b = ((bin_of(*tt) - first_bin) / interval_secs) as usize;
                    if rows[b].is_none() {
                        rows[b] = t.rows[i];
                    }
                }
                AaveTokenData {
                    name: t.name.clone(),
                    columns: t.columns.clone(),
                    rows,
                }
            })
            .collect();
        AaveData::new(ts, tokens)
    }

    /// The data as a polars frame: `timestamp` plus one `"TOKEN|column"` column per value.
    pub fn to_polars(&self) -> Result<DataFrame> {
        let err = |e: PolarsError| DemeterError::data(e.to_string());
        let ts_ms: Vec<i64> = self.ts.iter().map(|t| t * 1000).collect();
        let mut cols: Vec<Column> = vec![Series::new("timestamp".into(), ts_ms)
            .cast(&DataType::Datetime(TimeUnit::Milliseconds, None))
            .map_err(err)?
            .into()];
        for t in &self.tokens {
            for (ci, c) in REQUIRED_DATA_COLUMN.iter().enumerate() {
                if !t.columns.iter().any(|x| x == c) {
                    continue;
                }
                let v: Vec<Option<Dec>> =
                    t.rows.iter().map(|r| r.map(|s| s.values()[ci])).collect();
                cols.push(
                    crate::data::decimal_series_pub(&format!("{}|{}", t.name, c), &v)?.into(),
                );
            }
        }
        DataFrame::new_infer_height(cols).map_err(err)
    }

    /// Read a frame with a `timestamp` column and `"TOKEN|column"` value columns (the layout of
    /// [`AaveData::to_polars`]). Other columns are ignored.
    pub fn from_polars(df: &DataFrame) -> Result<AaveData> {
        let ts = frame_timestamps(df)?;
        let mut names: Vec<String> = vec![];
        for c in df.columns() {
            if let Some((tok, _)) = c.name().as_str().split_once('|') {
                if !names.iter().any(|n| n == tok) {
                    names.push(tok.to_string());
                }
            }
        }
        let mut data = AaveData::new(ts.clone(), vec![])?;
        for name in names {
            let token = token_from_columns(df, &name, |c| format!("{name}|{c}"), ts.len())?;
            data = data.with_token(token, &ts)?;
        }
        Ok(data)
    }

    /// The frame python's `set_token_data(token, frame)` receives: a `timestamp` column and
    /// plain column names (`liquidity_rate`, ...). Returns (timestamps, token data).
    pub fn token_from_polars(name: &str, df: &DataFrame) -> Result<(Vec<Ts>, AaveTokenData)> {
        let ts = frame_timestamps(df)?;
        let token = token_from_columns(df, &name.to_uppercase(), |c| c.to_string(), ts.len())?;
        Ok((ts, token))
    }
}

fn frame_timestamps(df: &DataFrame) -> Result<Vec<Ts>> {
    let err = |e: PolarsError| DemeterError::data(e.to_string());
    Ok(df
        .column("timestamp")
        .map_err(|_| DemeterError::data("aave data has no timestamp column"))?
        .cast(&DataType::Datetime(TimeUnit::Milliseconds, None))
        .map_err(err)?
        .cast(&DataType::Int64)
        .map_err(err)?
        .i64()
        .map_err(err)?
        .iter()
        .map(|v| v.unwrap_or(0).div_euclid(1000))
        .collect())
}

fn token_from_columns(
    df: &DataFrame,
    name: &str,
    column_name: impl Fn(&str) -> String,
    n: usize,
) -> Result<AaveTokenData> {
    let err = |e: PolarsError| DemeterError::data(e.to_string());
    let mut columns = vec![];
    let mut values: Vec<Option<Vec<Option<Dec>>>> = vec![];
    for c in REQUIRED_DATA_COLUMN {
        match df.column(&column_name(c)) {
            Ok(col) => {
                columns.push(c.to_string());
                let s = col.cast(&DataType::String).map_err(err)?;
                let v: Vec<Option<Dec>> = s
                    .str()
                    .map_err(err)?
                    .iter()
                    .map(|x| {
                        x.and_then(|x| dec::parse_lossy(x).ok())
                            .filter(|d| !d.is_nan())
                    })
                    .collect();
                values.push(Some(v));
            }
            Err(_) => values.push(None),
        }
    }
    let rows = (0..n)
        .map(|i| {
            let mut v = [dec::zero(); 5];
            for (k, col) in values.iter().enumerate() {
                v[k] = col.as_ref()?[i]?;
            }
            Some(AaveTokenStatus::from_values(v))
        })
        .collect();
    Ok(AaveTokenData {
        name: name.to_string(),
        columns,
        rows,
    })
}

/// Append the rows of one day file; returns the required columns found in it.
fn read_token_csv(
    path: &Path,
    rows: &mut Vec<(Ts, Option<AaveTokenStatus>)>,
) -> Result<Vec<String>> {
    let err = |e: PolarsError| DemeterError::data(format!("{}: {e}", path.display()));
    let df = CsvReadOptions::default()
        .with_has_header(true)
        .with_infer_schema_length(Some(0))
        .try_into_reader_with_file_path(Some(path.into()))
        .map_err(err)?
        .finish()
        .map_err(err)?;
    // python reads with index_col=0 (`block_timestamp`)
    let ts_col = df
        .columns()
        .first()
        .ok_or_else(|| DemeterError::data(format!("{}: empty file", path.display())))?
        .str()
        .map_err(err)?
        .clone();
    let mut columns = vec![];
    let mut values: Vec<Option<StringChunked>> = vec![];
    for c in REQUIRED_DATA_COLUMN {
        match df.column(c) {
            Ok(col) => {
                columns.push(c.to_string());
                values.push(Some(col.str().map_err(err)?.clone()));
            }
            Err(_) => values.push(None),
        }
    }
    for i in 0..df.height() {
        let t = ts_col
            .get(i)
            .ok_or_else(|| DemeterError::data("empty timestamp"))?;
        let dt = NaiveDateTime::parse_from_str(t, "%Y-%m-%d %H:%M:%S")
            .or_else(|_| NaiveDateTime::parse_from_str(t, "%Y-%m-%d %H:%M:%S%.f"))
            .or_else(|_| NaiveDateTime::parse_from_str(t, "%Y-%m-%dT%H:%M:%S"))
            .map_err(|e| {
                DemeterError::data(format!("{}: bad timestamp {t}: {e}", path.display()))
            })?;
        let mut v = [dec::zero(); 5];
        let mut complete = true;
        for (k, col) in values.iter().enumerate() {
            match col.as_ref().and_then(|c| c.get(i)).map(dec::parse_lossy) {
                Some(Ok(x)) if !x.is_nan() => v[k] = x,
                _ => complete = false,
            }
        }
        rows.push((
            crate::types::naive_to_ts(&dt),
            complete.then(|| AaveTokenStatus::from_values(v)),
        ));
    }
    Ok(columns)
}

/// python `helper.load_aave_data`: one csv per token and day,
/// `[chain]-aave_v3-[token address]-[date].minute.csv`. (The python feather cache is not used.)
pub fn load_aave_data(
    chain: &str,
    tokens: &[TokenInfo],
    start: NaiveDate,
    end: NaiveDate,
    data_path: &str,
) -> Result<AaveData> {
    let mut data = AaveData::default();
    for t in tokens {
        if t.address.is_empty() {
            return Err(DemeterError::demeter(format!(
                "address of {} not set",
                t.name
            )));
        }
        let mut rows = vec![];
        let mut columns: Vec<String> = REQUIRED_DATA_COLUMN.iter().map(|c| c.to_string()).collect();
        let mut day = start;
        while day <= end {
            let path = Path::new(data_path).join(format!(
                "{}-aave_v3-{}-{}.minute.csv",
                chain.to_lowercase(),
                t.address,
                day.format("%Y-%m-%d")
            ));
            if !path.exists() {
                return Err(DemeterError::data(format!(
                    "resource file {} not found, please download with demeter-fetch: https://github.com/zelos-alpha/demeter-fetch",
                    path.display()
                )));
            }
            columns = read_token_csv(&path, &mut rows)?;
            day += Duration::days(1);
        }
        let ts: Vec<Ts> = rows.iter().map(|(t, _)| *t).collect();
        let token = AaveTokenData {
            name: t.name.clone(),
            columns,
            rows: rows.into_iter().map(|(_, r)| r).collect(),
        };
        data = data.with_token(token, &ts)?;
    }
    Ok(data)
}

// ------------------------------------------------------------------ positions

/// python `SupplyInfo`: what the market keeps for a supplied token.
#[derive(Clone, Debug, PartialEq)]
pub struct SupplyInfo {
    /// amount / liquidity index at supply time
    pub base_amount: Dec,
    pub collateral: bool,
    pub begin_supply_index: Dec,
}

/// python `BorrowInfo`
#[derive(Clone, Debug, PartialEq)]
pub struct BorrowInfo {
    /// amount / variable borrow index at borrow time
    pub base_amount: Dec,
    pub begin_borrow_index: Dec,
}

/// python `Supply`: a supply valued at the current minute.
#[derive(Clone, Debug)]
pub struct Supply {
    pub token: TokenInfo,
    pub base_amount: Dec,
    pub collateral: bool,
    pub amount: Dec,
    pub apy: Dec,
    /// in USD
    pub value: Dec,
    pub begin_supply_index: Dec,
}

/// python `Borrow`: a borrow valued at the current minute.
#[derive(Clone, Debug)]
pub struct Borrow {
    pub token: TokenInfo,
    pub base_amount: Dec,
    pub amount: Dec,
    pub apy: Dec,
    /// in USD
    pub value: Dec,
    pub begin_borrow_index: Dec,
}

/// Prices the market values tokens with (python `market._price_status`), in USD.
#[derive(Clone, Debug, Default)]
pub enum AavePrices {
    #[default]
    Unset,
    /// a row of the actuator's price table; `factor` = (broker quote price, USD price) when the
    /// broker is not quoted in USD (python `price * broker_quote_price / market_quote_price`)
    Table {
        table: Rc<PriceTable>,
        row: usize,
        factor: Option<(Dec, Dec)>,
    },
    Values(Vec<(String, Dec)>),
}

impl AavePrices {
    pub fn get(&self, name: &str) -> Result<Dec> {
        match self {
            AavePrices::Unset => Err(DemeterError::demeter("price of aave market is not set")),
            AavePrices::Table { table, row, factor } => {
                let p = table.get(*row, name)?;
                Ok(match factor {
                    Some((bq, mq)) => div(p * *bq, *mq)?,
                    None => p,
                })
            }
            AavePrices::Values(v) => v
                .iter()
                .find(|(n, _)| n == name)
                .map(|(_, p)| *p)
                .ok_or_else(|| key_error(name)),
        }
    }

    /// token names with a price (python `price.index`)
    pub fn names(&self) -> Vec<String> {
        match self {
            AavePrices::Unset => vec![],
            AavePrices::Table { table, .. } => table.tokens.clone(),
            AavePrices::Values(v) => v.iter().map(|(n, _)| n.clone()).collect(),
        }
    }
}

/// Where the pool status of the current minute comes from.
#[derive(Clone, Debug)]
pub enum AaveStatusData {
    /// a row of the market data (python `data.loc[timestamp]`)
    Row { data: Arc<AaveData>, row: usize },
    /// given explicitly (python `set_market_status` with `data` set); None = missing values
    Values(Vec<(String, Option<AaveTokenStatus>)>),
}

/// python `AaveMarketStatus`
#[derive(Clone, Debug)]
pub struct AaveStatus {
    pub ts: Ts,
    pub data: AaveStatusData,
}

impl AaveStatus {
    /// python `market_status.data[token]`
    pub fn token(&self, name: &str) -> Result<AaveTokenStatus> {
        match &self.data {
            AaveStatusData::Row { data, row } => data.status(*row, name),
            AaveStatusData::Values(v) => v
                .iter()
                .find(|(n, _)| n == name)
                .ok_or_else(|| key_error(name))?
                .1
                .ok_or_else(|| {
                    DemeterError::data(format!("aave status of {name} is missing (NaN)"))
                }),
        }
    }

    /// (token, status) of every token in the row; None = missing values
    pub fn tokens(&self) -> Vec<(String, Option<AaveTokenStatus>)> {
        match &self.data {
            AaveStatusData::Row { data, row } => data
                .tokens
                .iter()
                .map(|t| (t.name.clone(), t.rows[*row]))
                .collect(),
            AaveStatusData::Values(v) => v.clone(),
        }
    }
}

type Values = Rc<Vec<(TokenInfo, Dec)>>;
type Supplies = Rc<Vec<(TokenInfo, Supply)>>;
type Borrows = Rc<Vec<(TokenInfo, Borrow)>>;

/// python's `DictCache`s. None = empty (python keeps a cache "empty" until a value is set, so a
/// computation without entries is redone next time).
#[derive(Default)]
struct Caches {
    supplies_amount: RefCell<Option<Values>>,
    collaterals_amount: RefCell<Option<Values>>,
    borrows_amount: RefCell<Option<Values>>,
    supplies: RefCell<Option<Supplies>>,
    borrows: RefCell<Option<Borrows>>,
}

impl Caches {
    fn reset_all(&self) {
        *self.supplies_amount.borrow_mut() = None;
        *self.collaterals_amount.borrow_mut() = None;
        *self.borrows_amount.borrow_mut() = None;
        *self.supplies.borrow_mut() = None;
        *self.borrows.borrow_mut() = None;
    }
}

type Cache<T> = RefCell<Option<Rc<Vec<T>>>>;

fn cached<T>(cell: &Cache<T>, build: impl FnOnce() -> Result<Vec<T>>) -> Result<Rc<Vec<T>>> {
    if let Some(v) = cell.borrow().as_ref() {
        return Ok(v.clone());
    }
    let v = Rc::new(build()?);
    if !v.is_empty() {
        *cell.borrow_mut() = Some(v.clone());
    }
    Ok(v)
}

// ------------------------------------------------------------------ market

/// python `AaveV3Market`. One market per chain; values are in USD.
pub struct AaveV3Market {
    pub info: MarketInfo,
    pub compat: EngineCompat,
    pub risk_parameters: RiskParameters,
    /// tokens used in this market (python `tokens` set, kept in insertion order)
    pub tokens: Vec<TokenInfo>,
    pub data: Option<Arc<AaveData>>,
    pub data_path: String,
    pub status: Option<AaveStatus>,
    pub prices: AavePrices,
    pub has_update: bool,
    pub is_open: bool,
    /// always USD (python `Market.quote_token`)
    pub quote_token: TokenInfo,
    supplies: Vec<(TokenInfo, SupplyInfo)>,
    borrows: Vec<(TokenInfo, BorrowInfo)>,
    wallet: Option<Shared<Wallet>>,
    log: Option<Shared<ActionLog>>,
    cache: Caches,
    /// rate -> apy; rates only change with ReserveDataUpdated events and the power is expensive
    apy_memo: RefCell<HashMap<Dec, Dec>>,
}

impl AaveV3Market {
    pub fn new(info: MarketInfo, risk_parameters: RiskParameters, tokens: Vec<TokenInfo>) -> Self {
        let mut m = AaveV3Market {
            info,
            compat: EngineCompat::default(),
            risk_parameters,
            tokens: vec![],
            data: None,
            data_path: "./data".into(),
            status: None,
            prices: AavePrices::Unset,
            has_update: false,
            is_open: true,
            quote_token: TokenInfo::usd(),
            supplies: vec![],
            borrows: vec![],
            wallet: None,
            log: None,
            cache: Caches::default(),
            apy_memo: Default::default(),
        };
        for t in tokens {
            m.add_token(t);
        }
        m
    }

    /// python `AaveV3Market(market_info, risk_parameters_path, tokens)`
    pub fn from_risk_file(
        info: MarketInfo,
        risk_parameters_path: &str,
        tokens: Vec<TokenInfo>,
    ) -> Result<Self> {
        Ok(Self::new(
            info,
            load_risk_parameters(risk_parameters_path)?,
            tokens,
        ))
    }

    pub(crate) fn attach(&mut self, wallet: Shared<Wallet>, log: Shared<ActionLog>) {
        self.wallet = Some(wallet);
        self.log = Some(log);
    }

    /// Use the wallet and action log of a broker without adding the market to it (python
    /// `market.broker = broker`).
    pub fn set_broker(&mut self, broker: &crate::broker::Broker) {
        self.attach(broker.wallet.clone(), broker.log.clone());
    }

    pub fn wallet(&self) -> Result<Shared<Wallet>> {
        self.wallet.clone().ok_or_else(|| {
            DemeterError::demeter(format!(
                "market {} is not added to a broker",
                self.info.name
            ))
        })
    }

    fn record(&self, kind: ActionKind) {
        if let Some(log) = &self.log {
            log.borrow_mut().record(&self.info, kind);
        }
    }

    fn legacy(&self) -> bool {
        self.compat.legacy_quirks
    }

    /// python `add_token` (a set: adding a token twice keeps the first one)
    pub fn add_token(&mut self, token: TokenInfo) {
        if !self.tokens.contains(&token) {
            self.tokens.push(token);
        }
    }

    /// python `write_func`: operations need the market to be open
    fn check_open(&self) -> Result<()> {
        if self.is_open {
            Ok(())
        } else {
            Err(DemeterError::demeter(format!(
                "{} is not open.",
                self.info.name
            )))
        }
    }

    /// python `write_func`, after the operation succeeded
    fn after_write(&mut self) {
        self.has_update = true;
    }

    fn risk(&self, name: &str) -> Result<&RiskParameter> {
        self.risk_parameters.get(name)
    }

    // ------------------------------------------------------------ positions (python dicts)

    /// python `market._supplies` (insertion ordered)
    pub fn supply_infos(&self) -> &[(TokenInfo, SupplyInfo)] {
        &self.supplies
    }

    /// python `market._borrows` (insertion ordered)
    pub fn borrow_infos(&self) -> &[(TokenInfo, BorrowInfo)] {
        &self.borrows
    }

    fn supply_pos(&self, token: &TokenInfo) -> Option<usize> {
        self.supplies.iter().position(|(t, _)| t == token)
    }

    fn borrow_pos(&self, token: &TokenInfo) -> Option<usize> {
        self.borrows.iter().position(|(t, _)| t == token)
    }

    /// python `market._supplies[token] = info`. Like the python dict, cached values are not
    /// refreshed (they are on the next market status or operation).
    pub fn set_supply_info(&mut self, token: &TokenInfo, info: SupplyInfo) {
        match self.supply_pos(token) {
            Some(i) => self.supplies[i].1 = info,
            None => self.supplies.push((token.clone(), info)),
        }
    }

    /// python `del market._supplies[token]`
    pub fn remove_supply_info(&mut self, token: &TokenInfo) -> Option<SupplyInfo> {
        self.supply_pos(token).map(|i| self.supplies.remove(i).1)
    }

    /// python `market._borrows[token] = info`. Like the python dict, cached values are not
    /// refreshed (they are on the next market status or operation).
    pub fn set_borrow_info(&mut self, token: &TokenInfo, info: BorrowInfo) {
        match self.borrow_pos(token) {
            Some(i) => self.borrows[i].1 = info,
            None => self.borrows.push((token.clone(), info)),
        }
    }

    /// python `del market._borrows[token]`
    pub fn remove_borrow_info(&mut self, token: &TokenInfo) -> Option<BorrowInfo> {
        self.borrow_pos(token).map(|i| self.borrows.remove(i).1)
    }

    pub fn supply_keys(&self) -> Vec<TokenInfo> {
        self.supplies.iter().map(|(t, _)| t.clone()).collect()
    }

    pub fn borrow_keys(&self) -> Vec<TokenInfo> {
        self.borrows.iter().map(|(t, _)| t.clone()).collect()
    }

    // ------------------------------------------------------------ data

    pub fn data(&self) -> Result<&Arc<AaveData>> {
        self.data
            .as_ref()
            .ok_or_else(|| DemeterError::demeter("data must be type of data frame"))
    }

    pub fn set_data(&mut self, d: Arc<AaveData>) {
        self.data = Some(d);
    }

    /// python `set_token_data`
    pub fn set_token_data(&mut self, ts: &[Ts], token: AaveTokenData) -> Result<()> {
        let base = self.data.as_deref().cloned().unwrap_or_default();
        self.data = Some(Arc::new(base.with_token(token, ts)?));
        Ok(())
    }

    /// python `load_data(chain, tokens, start, end)`, reading from `data_path`
    pub fn load_data(
        &mut self,
        chain: &str,
        tokens: &[TokenInfo],
        start: NaiveDate,
        end: NaiveDate,
    ) -> Result<()> {
        let d = load_aave_data(chain, tokens, start, end, &self.data_path)?;
        self.data = Some(Arc::new(d));
        Ok(())
    }

    pub fn resample(&mut self, interval_secs: i64) -> Result<()> {
        let d = self.data()?.resample(interval_secs)?;
        self.data = Some(Arc::new(d));
        Ok(())
    }

    // ------------------------------------------------------------ status

    pub fn status(&self) -> Result<&AaveStatus> {
        self.status.as_ref().ok_or_else(|| {
            DemeterError::demeter(format!("{} market status is not set", self.info.name))
        })
    }

    /// python `market_status.data[token]`
    pub fn token_status(&self, name: &str) -> Result<AaveTokenStatus> {
        self.status()?.token(name)
    }

    /// python `_price_status[token]`
    pub fn price(&self, name: &str) -> Result<Dec> {
        self.prices.get(name)
    }

    fn begin_status(&mut self, ts: Ts, prices: AavePrices) {
        self.prices = prices;
        self.is_open = match &self.data {
            None => true,
            Some(d) => d.row_of(ts).is_some(),
        };
        self.has_update = false;
    }

    /// python `set_market_status(MarketStatus(ts, None), price)`: the row comes from the data.
    pub fn set_market_status(&mut self, ts: Ts, prices: AavePrices) -> Result<()> {
        self.begin_status(ts, prices);
        let data = self
            .data
            .clone()
            .ok_or_else(|| DemeterError::demeter("data must be type of data frame"))?;
        let row = data
            .row_of(ts)
            .ok_or_else(|| key_error(&format!("Timestamp('{}')", ts_to_string(ts))))?;
        self.status = Some(AaveStatus {
            ts,
            data: AaveStatusData::Row { data, row },
        });
        self.cache.reset_all();
        Ok(())
    }

    /// python `set_market_status(MarketStatus(ts, data), price)` with the pool status given.
    pub fn set_market_status_values(
        &mut self,
        ts: Ts,
        tokens: Vec<(String, Option<AaveTokenStatus>)>,
        prices: AavePrices,
    ) {
        self.begin_status(ts, prices);
        self.status = Some(AaveStatus {
            ts,
            data: AaveStatusData::Values(tokens),
        });
        self.cache.reset_all();
    }

    // ------------------------------------------------------------ values

    fn rate_to_apy(&self, rate: Dec) -> Dec {
        if let Some(v) = self.apy_memo.borrow().get(&rate) {
            return *v;
        }
        let v = rate_to_apy(&rate);
        self.apy_memo.borrow_mut().insert(rate, v);
        v
    }

    /// python `supplies_value`: USD value of every supply
    pub fn supplies_value(&self) -> Result<Values> {
        cached(&self.cache.supplies_amount, || {
            let mut out = Vec::with_capacity(self.supplies.len());
            for (k, s) in &self.supplies {
                let st = self.token_status(&k.name)?;
                out.push((
                    k.clone(),
                    s.base_amount * st.liquidity_index * self.price(&k.name)?,
                ));
            }
            Ok(out)
        })
    }

    pub fn total_supply_value(&self) -> Result<Dec> {
        Ok(sum(&self.supplies_value()?))
    }

    /// python `collateral_value`: USD value of every collateral supply
    pub fn collateral_value(&self) -> Result<Values> {
        cached(&self.cache.collaterals_amount, || {
            let mut out = vec![];
            for (k, s) in &self.supplies {
                if s.collateral {
                    let sv = self.supplies_value()?;
                    out.push((k.clone(), *find(&sv, k).ok_or_else(|| key_error(&k.name))?));
                }
            }
            Ok(out)
        })
    }

    pub fn total_collateral_value(&self) -> Result<Dec> {
        Ok(sum(&self.collateral_value()?))
    }

    /// python `borrows_value`: USD value of every borrow
    pub fn borrows_value(&self) -> Result<Values> {
        cached(&self.cache.borrows_amount, || {
            let mut out = Vec::with_capacity(self.borrows.len());
            for (k, b) in &self.borrows {
                let st = self.token_status(&k.name)?;
                out.push((
                    k.clone(),
                    b.base_amount * st.variable_borrow_index * self.price(&k.name)?,
                ));
            }
            Ok(out)
        })
    }

    pub fn total_borrows_value(&self) -> Result<Dec> {
        Ok(sum(&self.borrows_value()?))
    }

    /// python `supplies`
    pub fn supplies(&self) -> Result<Supplies> {
        cached(&self.cache.supplies, || {
            self.supply_keys()
                .into_iter()
                .map(|k| {
                    let s = self.get_supply(&k)?;
                    Ok((k, s))
                })
                .collect()
        })
    }

    /// python `borrows`
    pub fn borrows(&self) -> Result<Borrows> {
        cached(&self.cache.borrows, || {
            self.borrow_keys()
                .into_iter()
                .map(|k| {
                    let b = self.get_borrow(&k)?;
                    Ok((k, b))
                })
                .collect()
        })
    }

    /// python `get_supply`
    pub fn get_supply(&self, token: &TokenInfo) -> Result<Supply> {
        let info = find(&self.supplies, token)
            .ok_or_else(|| key_error(&token.name))?
            .clone();
        let st = self.token_status(&token.name)?;
        let sv = self.supplies_value()?;
        Ok(Supply {
            token: token.clone(),
            base_amount: info.base_amount,
            collateral: info.collateral,
            amount: info.base_amount * st.liquidity_index,
            apy: self.rate_to_apy(st.liquidity_rate),
            value: *find(&sv, token).ok_or_else(|| key_error(&token.name))?,
            begin_supply_index: info.begin_supply_index,
        })
    }

    /// python `get_borrow`
    pub fn get_borrow(&self, token: &TokenInfo) -> Result<Borrow> {
        let info = find(&self.borrows, token)
            .ok_or_else(|| key_error(&token.name))?
            .clone();
        let st = self.token_status(&token.name)?;
        let bv = self.borrows_value()?;
        Ok(Borrow {
            token: token.clone(),
            base_amount: info.base_amount,
            amount: info.base_amount * st.variable_borrow_index,
            apy: self.rate_to_apy(st.variable_borrow_rate),
            value: *find(&bv, token).ok_or_else(|| key_error(&token.name))?,
            begin_borrow_index: info.begin_borrow_index,
        })
    }

    pub fn liquidation_threshold(&self) -> Result<Dec> {
        total_liquidation_threshold_of(&self.collateral_value()?, &self.risk_parameters)
    }

    pub fn max_ltv(&self) -> Result<Dec> {
        max_ltv_of(&self.collateral_value()?, &self.risk_parameters)
    }

    /// borrows / supplies (infinity without supplies)
    pub fn ltv(&self) -> Result<Dec> {
        if self.total_supply_value()?.is_zero() {
            return Ok(Dec::INFINITY);
        }
        Ok(self.total_borrows_value()? / self.total_supply_value()?)
    }

    pub fn health_factor(&self) -> Result<Dec> {
        let c = self.collateral_value()?;
        let b = self.borrows_value()?;
        health_factor_of(&c, &b, &self.risk_parameters)
    }

    /// python `AaveV3CoreLib.get_apy`
    fn get_apy(&self, amounts: &[(TokenInfo, Dec)], rates: &[(TokenInfo, Dec)]) -> Result<Dec> {
        if amounts.is_empty() {
            return Ok(dec::zero());
        }
        let mut a = dec::zero();
        for (k, v) in amounts {
            let r = *find(rates, k).ok_or_else(|| key_error(&k.name))?;
            a += *v * self.rate_to_apy(r);
        }
        Ok(safe_div_zero(a, sum(amounts)))
    }

    pub fn supply_apy(&self) -> Result<Dec> {
        let supplies = self.supplies()?;
        let mut rates = Vec::with_capacity(supplies.len());
        for (k, _) in supplies.iter() {
            rates.push((k.clone(), self.token_status(&k.name)?.liquidity_rate));
        }
        self.get_apy(&self.supplies_value()?, &rates)
    }

    pub fn borrow_apy(&self) -> Result<Dec> {
        let mut rates = Vec::with_capacity(self.borrows.len());
        for (k, _) in &self.borrows {
            rates.push((k.clone(), self.token_status(&k.name)?.variable_borrow_rate));
        }
        self.get_apy(&self.borrows_value()?, &rates)
    }

    /// python `total_apy`
    pub fn total_apy(&self) -> Result<Dec> {
        let ts = self.total_supply_value()?;
        let tb = self.total_borrows_value()?;
        let sa = self.supply_apy()?;
        let ba = self.borrow_apy()?;
        Ok(safe_div_zero(sa * ts - ba * tb, ts - tb))
    }

    /// python `get_market_balance` (rounded to 4 decimals like python)
    pub fn get_market_balance(&self) -> Result<AaveBalance> {
        let total_supplies = q4(self.total_supply_value()?);
        let total_borrows = q4(self.total_borrows_value()?);
        let supply_apy = q4(self.supply_apy()?);
        let borrow_apy = q4(self.borrow_apy()?);
        let net_apy = safe_div_zero(
            supply_apy * total_supplies - borrow_apy * total_borrows,
            total_supplies - total_borrows,
        );
        Ok(AaveBalance {
            net_value: total_supplies - total_borrows,
            supplies_count: self.supplies.len(),
            borrows_count: self.borrows.len(),
            liquidation_threshold: q4(self.liquidation_threshold()?),
            health_factor: q4(self.health_factor()?),
            borrows_value: total_borrows,
            supplies_value: total_supplies,
            collaterals_value: q4(self.total_collateral_value()?),
            max_ltv: q4(self.max_ltv()?),
            ltv: self.ltv()?,
            supply_apy,
            borrow_apy,
            net_apy,
        })
    }

    /// python `check_market`
    pub fn check_market(&self) -> Result<()> {
        let d = self.data()?;
        require(!self.tokens.is_empty(), "should set tokens")?;
        require(
            self.quote_token == TokenInfo::usd(),
            "Quote token of AAVE market must be USD",
        )?;
        for t in &self.tokens {
            require(
                self.risk_parameters.contains(&t.name),
                &format!(
                    "According to risk_parameter, {} is not supported in this chain. ",
                    t.name
                ),
            )?;
            for c in REQUIRED_DATA_COLUMN {
                require(
                    d.has_column(&t.name, c),
                    &format!("{}.{} not found in data", t.name, c),
                )?;
            }
        }
        Ok(())
    }

    /// python `update`: liquidate when the health factor is below 1
    pub fn update(&mut self) -> Result<()> {
        self.liquidate()
    }

    // ------------------------------------------------------------ operations

    /// python `supply(token, amount, collateral)`
    pub fn supply(&mut self, token: &TokenInfo, amount: Dec, collateral: bool) -> Result<()> {
        self.check_open()?;
        if collateral {
            require(
                self.risk(&token.name)?.usage_as_collateral_enabled,
                "Can not supplied as collateral",
            )?;
        }
        let st = self.token_status(&token.name)?;
        let pool_amount = div(amount, st.liquidity_index)?;
        let existing = self.supply_pos(token);
        let check = |m: &Self| match existing {
            Some(i) => require(
                m.supplies[i].1.collateral == collateral,
                "Collateral different from existing supply",
            ),
            None => Ok(()),
        };
        if !self.legacy() {
            check(self)?;
        }
        self.wallet()?.borrow_mut().sub(token, amount)?;
        if self.legacy() {
            // QUIRK (aave): python checks the collateral flag after taking the tokens
            check(self)?;
        }
        let i = existing.unwrap_or_else(|| {
            self.supplies.push((
                token.clone(),
                SupplyInfo {
                    base_amount: dec::zero(),
                    collateral,
                    begin_supply_index: st.liquidity_index,
                },
            ));
            self.supplies.len() - 1
        });
        self.supplies[i].1.base_amount += pool_amount;
        self.reset_supplies(true);
        let deposit_after = self.supplies[i].1.base_amount * st.liquidity_index;
        self.record(ActionKind::AaveSupply {
            token: token.name.clone(),
            amount: Ud::new(amount, &token.name),
            collateral,
            deposit_after: Ud::new(deposit_after, &token.name),
        });
        self.after_write();
        Ok(())
    }

    /// python `change_collateral`
    pub fn change_collateral(&mut self, token: &TokenInfo, collateral: bool) -> Result<()> {
        self.check_open()?;
        let i = self
            .supply_pos(token)
            .ok_or_else(|| key_error(&token.name))?;
        let old = self.supplies[i].1.collateral;
        if old == collateral {
            self.after_write();
            return Ok(());
        }
        self.supplies[i].1.collateral = collateral;
        self.reset_after_collateral_change();
        if !collateral && self.health_factor()? < dec::one() {
            self.supplies[i].1.collateral = old;
            self.reset_after_collateral_change();
            return Err(DemeterError::assertion(
                "health factor lower than liquidation threshold",
            ));
        }
        self.after_write();
        Ok(())
    }

    fn reset_after_collateral_change(&self) {
        if self.legacy() {
            // QUIRK (aave): python refreshes only the collateral values, so `supplies` shows the
            // old collateral flag until the next refresh
            *self.cache.collaterals_amount.borrow_mut() = None;
        } else {
            self.cache.reset_all();
        }
    }

    /// python `withdraw(token, amount)`; None withdraws everything
    pub fn withdraw(&mut self, token: &TokenInfo, amount: Option<Dec>) -> Result<()> {
        self.check_open()?;
        let st = self.token_status(&token.name)?;
        let supply = self.get_supply(token)?;
        let amount = amount.unwrap_or(supply.amount);
        require(!amount.is_zero(), "invalid amount")?;
        require(amount <= supply.amount, "not enough available user balance")?;
        let i = self
            .supply_pos(token)
            .ok_or_else(|| key_error(&token.name))?;
        if self.supplies[i].1.collateral {
            // try the withdraw, reject it if the health factor drops below 1
            let old = self.supplies[i].1.base_amount;
            self.supplies[i].1.base_amount -= div(amount, st.liquidity_index)?;
            *self.cache.supplies_amount.borrow_mut() = None;
            *self.cache.collaterals_amount.borrow_mut() = None;
            if self.health_factor()? < dec::one() {
                if !self.legacy() {
                    self.supplies[i].1.base_amount = old;
                    self.cache.reset_all();
                }
                // QUIRK (aave): python leaves the supply reduced when it rejects the withdraw
                return Err(DemeterError::assertion(
                    "health factor lower than liquidation threshold",
                ));
            }
            self.supplies[i].1.base_amount = old;
            if !self.legacy() {
                self.cache.reset_all();
            }
        }
        let final_base = self.sub_supply_amount(token, amount)?;
        self.wallet()?.borrow_mut().add(token, amount);
        self.record(ActionKind::AaveWithdraw {
            token: token.name.clone(),
            amount: Ud::new(amount, &token.name),
            deposit_after: Ud::new(final_base * st.liquidity_index, &token.name),
        });
        self.after_write();
        Ok(())
    }

    /// python `get_max_withdraw_amount`
    pub fn get_max_withdraw_amount(&self, token: &TokenInfo) -> Result<Dec> {
        let supplies = self.supplies()?;
        let amount = find(&supplies, token)
            .ok_or_else(|| key_error(&token.name))?
            .amount;
        let collaterals = self.collateral_value()?;
        let borrows = self.borrows_value()?;
        let price = self.price(&token.name)?;
        // python `AaveV3CoreLib.get_min_withdraw_kept_amount`
        if find(&collaterals, token).is_none() {
            return Ok(amount);
        }
        let mut others = dec::zero();
        for (s, v) in collaterals.iter() {
            if s != token {
                others += self.risk(&s.name)?.reserve_liquidation_threshold * *v;
            }
        }
        let lt = self.risk(&token.name)?.reserve_liquidation_threshold;
        let kept = div(sum(&borrows) - others, lt)?;
        Ok(amount - div(kept, price)?)
    }

    /// python `get_max_borrow_amount`
    pub fn get_max_borrow_amount(&self, token: &TokenInfo) -> Result<Dec> {
        let collaterals = self.collateral_value()?;
        let borrows = self.borrows_value()?;
        // python `AaveV3CoreLib.get_max_borrow_value`; the 0.99 is what the aave web app uses
        let max_ltv = max_ltv_of(&collaterals, &self.risk_parameters)?;
        let total_borrow = sum(&borrows);
        let total_collateral = sum(&collaterals);
        if max_ltv.is_infinite() && total_collateral.is_zero() {
            // python: 0 * Infinity
            return Err(DemeterError::data(
                "decimal.InvalidOperation: [<class 'decimal.InvalidOperation'>]",
            ));
        }
        let value = (total_collateral * max_ltv - total_borrow) * lit("0.99");
        div(value, self.price(&token.name)?)
    }

    /// python `borrow(token, amount)`; None borrows the max amount
    pub fn borrow(&mut self, token: &TokenInfo, amount: Option<Dec>) -> Result<()> {
        self.check_open()?;
        let amount = match amount {
            Some(a) => a,
            None => self.get_max_borrow_amount(token)?,
        };
        let st = self.token_status(&token.name)?;
        require(
            self.risk(&token.name)?.borrowing_enabled,
            &format!("borrow is not enabled for {}", token.name),
        )?;
        let collateral_balance = sum(&self.collateral_value()?);
        require(!collateral_balance.is_zero(), "collateral balance is zero")?;
        let max_ltv = self.max_ltv()?;
        require(!max_ltv.is_zero(), "ltv validation failed")?;
        require(
            self.health_factor()? > dec::one(),
            "health factor lower than liquidation threshold",
        )?;
        let value = amount * self.price(&token.name)?;
        let borrowed = self
            .borrows()?
            .iter()
            .fold(dec::zero(), |a, (_, b)| a + b.value);
        let collateral_needed = div(borrowed + value, max_ltv)?;
        require(
            collateral_needed <= collateral_balance,
            "collateral cannot cover new borrow",
        )?;
        let base_amount = div(amount, st.variable_borrow_index)?;
        let i = self.borrow_pos(token).unwrap_or_else(|| {
            self.borrows.push((
                token.clone(),
                BorrowInfo {
                    base_amount: dec::zero(),
                    begin_borrow_index: st.variable_borrow_index,
                },
            ));
            self.borrows.len() - 1
        });
        self.borrows[i].1.base_amount += base_amount;
        self.wallet()?.borrow_mut().add(token, amount);
        self.reset_borrows();
        let debt_after = self.borrows[i].1.base_amount * st.variable_borrow_index;
        self.record(ActionKind::AaveBorrow {
            token: token.name.clone(),
            amount: Ud::new(amount, &token.name),
            debt_after: Ud::new(debt_after, &token.name),
        });
        self.after_write();
        Ok(())
    }

    /// python `get_max_repay_amount`
    pub fn get_max_repay_amount(&self, token: &TokenInfo) -> Result<Dec> {
        let b = find(&self.borrows, token).ok_or_else(|| key_error(&token.name))?;
        Ok(b.base_amount * self.token_status(&token.name)?.variable_borrow_index)
    }

    /// python `_get_swap_amount` (no fee)
    fn swap_amount(&self, from: &TokenInfo, to: &TokenInfo, amount: Dec) -> Result<Dec> {
        div(
            amount * dec::one() * self.price(&from.name)?,
            self.price(&to.name)?,
        )
    }

    /// python `repay(token, amount, repay_with_collateral, repay_collateral_token)`. Amount None
    /// repays the whole debt; with collateral the debt is paid with a supplied token.
    pub fn repay(
        &mut self,
        borrow_token: &TokenInfo,
        payback_amount: Option<Dec>,
        repay_with_collateral: bool,
        repay_collateral_token: Option<&TokenInfo>,
    ) -> Result<()> {
        self.check_open()?;
        let st = self.token_status(&borrow_token.name)?;
        let borrow = self.get_borrow(borrow_token)?;
        let mut payback = payback_amount.unwrap_or(borrow.amount);
        let mut collateral_token = None;
        if repay_with_collateral {
            let ct = repay_collateral_token.unwrap_or(borrow_token).clone();
            let supplies = self.supplies()?;
            let s = find(&supplies, &ct);
            require(s.is_some(), &format!("token {} is not in supply", ct.name))?;
            require(
                s.map(|s| s.collateral).unwrap_or(false),
                &format!("token {} is not in collateral", ct.name),
            )?;
            let required = self.swap_amount(borrow_token, &ct, payback)?;
            let supply = self.get_supply(&ct)?;
            if required > supply.amount {
                // the contract lowers the payback instead of failing
                payback = self.swap_amount(&ct, borrow_token, supply.amount)?;
            }
            collateral_token = Some(ct);
        }
        let payback_base = div(payback, st.variable_borrow_index)?;
        require(payback_base > dec::zero(), "invalid amount")?;
        let i = self
            .borrow_pos(borrow_token)
            .ok_or_else(|| key_error(&borrow_token.name))?;
        require(
            self.borrows[i].1.base_amount > dec::zero(),
            "no debt of selected type",
        )?;
        let debt = find(&self.borrows()?, borrow_token)
            .ok_or_else(|| key_error(&borrow_token.name))?
            .amount;
        // QUIRK (aave): python compares the debt amount with the payback *base* amount
        let left = if self.legacy() {
            debt - payback_base
        } else {
            debt - payback
        };
        require(
            dec::quantize(&left, 18) >= dec::zero(),
            "amount exceed debt",
        )?;
        match &collateral_token {
            Some(ct) => {
                let in_collateral = self.swap_amount(borrow_token, ct, payback)?;
                self.sub_supply_amount(ct, in_collateral)?;
            }
            None => self.wallet()?.borrow_mut().sub(borrow_token, payback)?,
        }
        let debt_base = self.sub_borrow_amount(borrow_token, payback)?;
        self.record(ActionKind::AaveRepay {
            token: borrow_token.name.clone(),
            amount: Ud::new(payback, &borrow_token.name),
            debt_after: Ud::new(debt_base * st.variable_borrow_index, &borrow_token.name),
        });
        self.after_write();
        Ok(())
    }

    /// cache refresh after a supply changed (python resets the collateral values only for
    /// collateral supplies)
    fn reset_supplies(&self, collateral: bool) {
        if collateral || !self.legacy() {
            *self.cache.collaterals_amount.borrow_mut() = None;
        }
        *self.cache.supplies_amount.borrow_mut() = None;
        *self.cache.supplies.borrow_mut() = None;
    }

    fn reset_borrows(&self) {
        *self.cache.borrows_amount.borrow_mut() = None;
        *self.cache.borrows.borrow_mut() = None;
    }

    /// python `__sub_supply_amount`: returns the base amount left
    fn sub_supply_amount(&mut self, token: &TokenInfo, amount: Dec) -> Result<Dec> {
        let Some(i) = self.supply_pos(token) else {
            if amount.is_zero() {
                return Ok(dec::zero());
            }
            return Err(DemeterError::demeter(format!(
                "{} not exist in supplies",
                token.name
            )));
        };
        let idx = self.token_status(&token.name)?.liquidity_index;
        let s = &mut self.supplies[i].1;
        s.base_amount = sub_base_amount(s.base_amount, div(amount, idx)?);
        let (collateral, base) = (s.collateral, s.base_amount);
        self.reset_supplies(collateral);
        if base.is_zero() {
            self.supplies.remove(i);
            return Ok(dec::zero());
        }
        Ok(base)
    }

    /// python `__sub_borrow_amount`: returns the base amount left
    fn sub_borrow_amount(&mut self, token: &TokenInfo, amount: Dec) -> Result<Dec> {
        let Some(i) = self.borrow_pos(token) else {
            if amount.is_zero() {
                return Ok(dec::zero());
            }
            return Err(DemeterError::demeter(format!(
                "{} not exist in borrows",
                token.name
            )));
        };
        let idx = self.token_status(&token.name)?.variable_borrow_index;
        let b = &mut self.borrows[i].1;
        b.base_amount = sub_base_amount(b.base_amount, div(amount, idx)?);
        let base = b.base_amount;
        self.reset_borrows();
        if base.is_zero() {
            self.borrows.remove(i);
            return Ok(dec::zero());
        }
        Ok(base)
    }

    /// python `_liquidate`: while the health factor is between 0 and 1, liquidate the smallest
    /// debt (each debt token once) against the largest collateral.
    fn liquidate(&mut self) -> Result<()> {
        self.check_open()?;
        let one = dec::one();
        let mut hf = self.health_factor()?;
        let mut has_liquidated: Vec<Option<TokenInfo>> = vec![];
        while hf > dec::zero() && hf < one {
            let borrows = self.borrows()?;
            let supplies = self.supplies()?;
            let mut min_borrow_key = None;
            let mut min_borrow_value = dec::from_f64_exact(10e21);
            for (k, v) in borrows.iter() {
                let done = has_liquidated.iter().any(|h| h.as_ref() == Some(k));
                if min_borrow_value >= v.value && !done {
                    min_borrow_value = v.value;
                    min_borrow_key = Some(k.clone());
                }
            }
            let mut max_supply_key = None;
            let mut max_supply_value = dec::zero();
            for (k, v) in supplies.iter() {
                if v.collateral && max_supply_value <= v.value {
                    max_supply_value = v.value;
                    max_supply_key = Some(k.clone());
                }
            }
            if min_borrow_key.is_none() && !self.legacy() {
                // every debt was liquidated once and the health factor is still below 1
                // (QUIRK (aave): python goes on and fails with AttributeError)
                break;
            }
            has_liquidated.push(min_borrow_key.clone());
            match self.do_liquidate(
                max_supply_key.as_ref(),
                min_borrow_key.as_ref(),
                min_borrow_value,
            ) {
                // a rejected liquidation: the next round tries another debt token
                Ok(()) | Err(DemeterError::Assertion(_)) => {}
                Err(e) => return Err(e),
            }
            hf = self.health_factor()?;
        }
        self.after_write();
        Ok(())
    }

    /// python `_do_liquidate`
    fn do_liquidate(
        &mut self,
        collateral_token: Option<&TokenInfo>,
        delt_token: Option<&TokenInfo>,
        delt_value_to_cover: Dec,
    ) -> Result<()> {
        // python fails with AttributeError on `None.name` (not caught by the actuator)
        let none =
            || DemeterError::data("AttributeError: 'NoneType' object has no attribute 'name'");
        let old_health_factor = self.health_factor()?;
        let delt = delt_token.ok_or_else(none)?;
        let delt_status = self.token_status(&delt.name)?;
        let borrow_index = delt_status.variable_borrow_index;
        let collateral = collateral_token.ok_or_else(none)?;
        // QUIRK (aave): python reduces the collateral with the liquidity index of the debt token
        let supply_index = if self.legacy() {
            delt_status.liquidity_index
        } else {
            self.token_status(&collateral.name)?.liquidity_index
        };
        let bonus = self.risk(&collateral.name)?.reserve_liquidation_bonus;

        let variable_delt = if self.borrow_pos(delt).is_some() {
            self.get_borrow(delt)?.amount
        } else {
            dec::zero()
        };
        let total_debt = variable_delt;
        let close_factor = if old_health_factor > lit("0.95") {
            lit("0.5")
        } else {
            dec::one()
        };
        let max_liquidatable_debt = total_debt * close_factor;
        let mut actual_debt = if delt_value_to_cover > max_liquidatable_debt {
            max_liquidatable_debt
        } else {
            delt_value_to_cover
        };

        let ci = self.supply_pos(collateral);
        let enabled = !self
            .risk(&collateral.name)?
            .reserve_liquidation_threshold
            .is_zero()
            && self.supplies[ci.ok_or_else(|| key_error(&collateral.name))?]
                .1
                .collateral;
        require(enabled, "collateral cannot be liquidated")?;
        require(
            !total_debt.is_zero(),
            "specified currency not borrowed by user",
        )?;
        let ci = ci.ok_or_else(|| key_error(&collateral.name))?;

        let user_collateral_balance =
            self.supplies[ci].1.base_amount * self.token_status(&collateral.name)?.liquidity_index;
        let price_c = self.price(&collateral.name)?;
        let price_d = self.price(&delt.name)?;
        let should_collateral = div(price_d * actual_debt, price_c)?;
        let max_collateral = should_collateral * (dec::one() + bonus);
        let actual_collateral = if max_collateral > user_collateral_balance {
            actual_debt = div(
                price_c * user_collateral_balance,
                price_d * (dec::one() + bonus),
            )?;
            user_collateral_balance
        } else {
            max_collateral
        };
        let s = &mut self.supplies[ci].1;
        s.base_amount = sub_base_amount(s.base_amount, div(actual_collateral, supply_index)?);
        if s.base_amount.is_zero() {
            self.supplies.remove(ci);
        }
        if variable_delt < actual_debt {
            return Err(DemeterError::demeter(
                "variable_delt < actual_debt_to_liquidate",
            ));
        }
        let remaining_base = self.sub_borrow_amount(delt, actual_debt)?;
        self.cache.reset_all();

        let health_factor_after = self.health_factor()?;
        let collateral_after = self
            .supply_pos(collateral)
            .map(|i| self.supplies[i].1.base_amount)
            .unwrap_or_else(dec::zero);
        self.record(ActionKind::AaveLiquidation {
            collateral_token: collateral.name.clone(),
            debt_token: delt.name.clone(),
            delt_to_cover: Ud::new(delt_value_to_cover, &delt.name),
            collateral_used: Ud::new(actual_collateral, &collateral.name),
            variable_delt_liquidated: Ud::new(actual_debt, &delt.name),
            health_factor_before: old_health_factor,
            health_factor_after,
            collateral_after: Ud::new(collateral_after * supply_index, &collateral.name),
            variable_debt_after: Ud::new(remaining_base * borrow_index, &delt.name),
            legacy_type: self.legacy(),
        });
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn d(s: &str) -> Dec {
        dec::parse_lossy(s).unwrap()
    }

    #[test]
    fn apy_matches_python() {
        // tests/aave_market_test.py::test_apy_to_rate (python, prec 35)
        assert_eq!(
            rate_to_apy(&d("0.054385544255370350575778874")),
            d("0.0558916165865621190990895936500967")
        );
        assert_eq!(
            rate_to_apy(&d("1")),
            d("1.7182817853609708212635582654585362")
        );
        assert_eq!(rate_to_apy(&d("0")), d("0"));
    }

    #[test]
    fn quantize_half_even() {
        assert_eq!(dec::quantize(&d("1.00005"), 4), d("1.0000"));
        assert_eq!(dec::quantize(&d("1.00015"), 4), d("1.0002"));
        assert_eq!(
            dec::quantize(&d("0.0208564215143061067923752158582056"), 4),
            d("0.0209")
        );
        assert_eq!(dec::quantize(&d("-0.00335"), 4), d("-0.0034"));
        assert_eq!(dec::quantize(&d("1200"), 4), d("1200"));
        assert_eq!(
            dec::to_py_string(&dec::quantize(&d("1200"), 4)),
            "12000000E-4"
        );
    }

    #[test]
    fn sub_base_amount_floor() {
        assert!(sub_base_amount(d("1"), d("0.9999999999999999999")).is_zero());
        assert_eq!(sub_base_amount(d("1"), d("0.5")), d("0.5"));
    }
}
