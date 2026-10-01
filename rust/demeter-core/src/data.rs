//! Uniswap v3 minute data: loading (python `load_uni_v3_data`), filling (`data.fillna`),
//! statistic columns (`_add_statistic_column`), resampling and conversion to/from polars.
//!
//! The backtest loop never touches polars: data is converted once into a `Vec<Bar>` indexed by
//! row, so a bar lookup is an array index instead of pandas' `df.loc[timestamp]`.

use crate::dec::{self, Dec};
use crate::error::{DemeterError, Result};
use crate::math;
use crate::types::{naive_to_ts, Ts, UniV3Pool};
use chrono::{Duration, NaiveDate, NaiveDateTime};
use polars::prelude::*;
use std::collections::HashMap;
use std::path::Path;

/// One minute of pool data (a row of python `market.data`).
#[derive(Clone, Debug)]
pub struct Bar {
    pub net_amount0: i128,
    pub net_amount1: i128,
    pub close_tick: i32,
    pub open_tick: i32,
    pub lowest_tick: i32,
    pub highest_tick: i32,
    pub in_amount0: i128,
    pub in_amount1: i128,
    pub current_liquidity: u128,
    /// price at the close of this minute
    pub close: Dec,
    /// price at the start of this minute (= previous close)
    pub price: Dec,
    pub volume0: Dec,
    pub volume1: Dec,
}

/// A user column (python `strategy.add_column`).
#[derive(Clone, Debug)]
pub enum ExtraColumn {
    Dec(Vec<Option<Dec>>),
    F64(Vec<f64>),
    I64(Vec<Option<i64>>),
    Bool(Vec<Option<bool>>),
    Str(Vec<Option<String>>),
}

impl ExtraColumn {
    pub fn len(&self) -> usize {
        match self {
            ExtraColumn::Dec(v) => v.len(),
            ExtraColumn::F64(v) => v.len(),
            ExtraColumn::I64(v) => v.len(),
            ExtraColumn::Bool(v) => v.len(),
            ExtraColumn::Str(v) => v.len(),
        }
    }
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
    fn take(&self, rows: &[usize]) -> ExtraColumn {
        match self {
            ExtraColumn::Dec(v) => ExtraColumn::Dec(rows.iter().map(|r| v[*r]).collect()),
            ExtraColumn::F64(v) => ExtraColumn::F64(rows.iter().map(|r| v[*r]).collect()),
            ExtraColumn::I64(v) => ExtraColumn::I64(rows.iter().map(|r| v[*r]).collect()),
            ExtraColumn::Bool(v) => ExtraColumn::Bool(rows.iter().map(|r| v[*r]).collect()),
            ExtraColumn::Str(v) => ExtraColumn::Str(rows.iter().map(|r| v[*r].clone()).collect()),
        }
    }
}

/// Market data table: timestamps, bars and optional user columns, all of the same length.
#[derive(Clone, Debug, Default)]
pub struct UniData {
    pub ts: Vec<Ts>,
    pub bars: Vec<Bar>,
    pub extra: Vec<(String, ExtraColumn)>,
    /// set when `ts` is an evenly spaced grid, so a row is found by arithmetic
    grid: Option<(Ts, Ts)>,
    lookup: HashMap<Ts, usize>,
}

pub const BASE_COLUMNS: [&str; 14] = [
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
    "timestamp",
];

impl UniData {
    pub fn new(ts: Vec<Ts>, bars: Vec<Bar>) -> Result<Self> {
        if ts.len() != bars.len() {
            return Err(DemeterError::data("timestamp and bar count differ"));
        }
        let mut d = UniData {
            ts,
            bars,
            extra: vec![],
            grid: None,
            lookup: HashMap::new(),
        };
        d.build_index()?;
        Ok(d)
    }

    fn build_index(&mut self) -> Result<()> {
        self.grid = None;
        self.lookup.clear();
        if self.ts.len() >= 2 {
            let step = self.ts[1] - self.ts[0];
            if step > 0 && self.ts.windows(2).all(|w| w[1] - w[0] == step) {
                self.grid = Some((self.ts[0], step));
                return Ok(());
            }
        } else if self.ts.len() == 1 {
            self.grid = Some((self.ts[0], 60));
            return Ok(());
        }
        for (i, t) in self.ts.iter().enumerate() {
            if self.lookup.insert(*t, i).is_some() {
                return Err(DemeterError::data(format!(
                    "duplicate timestamp {}",
                    crate::types::ts_to_string(*t)
                )));
            }
        }
        Ok(())
    }

    pub fn len(&self) -> usize {
        self.ts.len()
    }

    pub fn is_empty(&self) -> bool {
        self.ts.is_empty()
    }

    /// Row of a timestamp (python `ts in df.index` / `df.loc[ts]`).
    pub fn row_of(&self, ts: Ts) -> Option<usize> {
        match self.grid {
            Some((start, step)) => {
                if ts < start || (ts - start) % step != 0 {
                    return None;
                }
                let r = ((ts - start) / step) as usize;
                if r < self.ts.len() {
                    Some(r)
                } else {
                    None
                }
            }
            None => self.lookup.get(&ts).copied(),
        }
    }

    pub fn extra(&self, name: &str) -> Option<&ExtraColumn> {
        self.extra.iter().find(|(n, _)| n == name).map(|(_, c)| c)
    }

    /// Add or replace a user column. `col` must be aligned with the rows.
    pub fn set_extra(&mut self, name: &str, col: ExtraColumn) -> Result<()> {
        if col.len() != self.len() {
            return Err(DemeterError::data(format!(
                "column {name} has {} rows, data has {}",
                col.len(),
                self.len()
            )));
        }
        if let Some(slot) = self.extra.iter_mut().find(|(n, _)| n == name) {
            slot.1 = col;
        } else {
            self.extra.push((name.to_string(), col));
        }
        Ok(())
    }

    /// python `_add_statistic_column`: recompute `close`, `price`, `volume0`, `volume1`.
    pub fn add_statistic_columns(&mut self, pool: &UniV3Pool) -> Result<()> {
        let (d0, d1, q) = (
            pool.token0.decimal,
            pool.token1.decimal,
            pool.is_token0_quote,
        );
        let mut cache: HashMap<i32, Dec> = HashMap::new();
        let mut price_of = |tick: i32| -> Result<Dec> {
            if let Some(p) = cache.get(&tick) {
                return Ok(*p);
            }
            let p = math::tick_to_base_unit_price(tick, d0, d1, q)?;
            cache.insert(tick, p);
            Ok(p)
        };
        let scale0 = dec::pow10(d0 as i32);
        let scale1 = dec::pow10(d1 as i32);
        let mut prev_close: Option<Dec> = None;
        for (i, bar) in self.bars.iter_mut().enumerate() {
            bar.close = price_of(bar.close_tick)?;
            bar.price = match prev_close {
                Some(p) => p,
                None => {
                    debug_assert_eq!(i, 0);
                    price_of(bar.open_tick)?
                }
            };
            prev_close = Some(bar.close);
            bar.volume0 = dec::from_i128(bar.in_amount0) / scale0;
            bar.volume1 = dec::from_i128(bar.in_amount1) / scale1;
        }
        Ok(())
    }

    /// Keep only rows in [start, end] (inclusive).
    pub fn slice_time(&self, start: Ts, end: Ts) -> Result<UniData> {
        let rows: Vec<usize> = (0..self.len())
            .filter(|i| self.ts[*i] >= start && self.ts[*i] <= end)
            .collect();
        self.take(&rows)
    }

    fn take(&self, rows: &[usize]) -> Result<UniData> {
        let mut d = UniData::new(
            rows.iter().map(|r| self.ts[*r]).collect(),
            rows.iter().map(|r| self.bars[*r].clone()).collect(),
        )?;
        d.extra = self
            .extra
            .iter()
            .map(|(n, c)| (n.clone(), c.take(rows)))
            .collect();
        Ok(d)
    }

    /// python `uniswap.data.resample(df, freq)` with the default `origin="start_day"`, left closed
    /// and left labelled bins (pandas default for minute/hour rules).
    pub fn resample(&self, interval_secs: i64) -> Result<UniData> {
        if interval_secs <= 60 || self.is_empty() {
            return Ok(self.clone());
        }
        let day0 = self.ts[0] - self.ts[0].rem_euclid(86400);
        let bin_of = |t: Ts| day0 + ((t - day0).div_euclid(interval_secs)) * interval_secs;
        let first_bin = bin_of(self.ts[0]);
        let last_bin = bin_of(*self.ts.last().unwrap());
        let nbins = ((last_bin - first_bin) / interval_secs + 1) as usize;
        let mut groups: Vec<Vec<usize>> = vec![vec![]; nbins];
        for (i, t) in self.ts.iter().enumerate() {
            groups[((bin_of(*t) - first_bin) / interval_secs) as usize].push(i);
        }
        let mut ts = Vec::with_capacity(nbins);
        let mut bars = Vec::with_capacity(nbins);
        let mut firsts = Vec::with_capacity(nbins);
        for (g, rows) in groups.iter().enumerate() {
            if rows.is_empty() {
                // pandas would give NaN for first/last and 0 for sums; keep the grid dense by
                // carrying the previous bar with zero volume (python would fail later on NaN).
                let prev: &Bar = bars
                    .last()
                    .ok_or_else(|| DemeterError::data("empty first resample bin"))?;
                let mut b = prev.clone();
                b.net_amount0 = 0;
                b.net_amount1 = 0;
                b.in_amount0 = 0;
                b.in_amount1 = 0;
                b.volume0 = dec::zero();
                b.volume1 = dec::zero();
                b.open_tick = b.close_tick;
                b.lowest_tick = b.close_tick;
                b.highest_tick = b.close_tick;
                b.price = b.close;
                ts.push(first_bin + g as i64 * interval_secs);
                bars.push(b);
                firsts.push(*firsts.last().unwrap());
                continue;
            }
            let first = &self.bars[rows[0]];
            let last = &self.bars[*rows.last().unwrap()];
            let mut b = Bar {
                net_amount0: rows.iter().map(|r| self.bars[*r].net_amount0).sum(),
                net_amount1: rows.iter().map(|r| self.bars[*r].net_amount1).sum(),
                close_tick: last.close_tick,
                open_tick: first.open_tick,
                lowest_tick: rows
                    .iter()
                    .map(|r| self.bars[*r].lowest_tick)
                    .min()
                    .unwrap(),
                highest_tick: rows
                    .iter()
                    .map(|r| self.bars[*r].highest_tick)
                    .max()
                    .unwrap(),
                in_amount0: rows.iter().map(|r| self.bars[*r].in_amount0).sum(),
                in_amount1: rows.iter().map(|r| self.bars[*r].in_amount1).sum(),
                current_liquidity: last.current_liquidity,
                close: first.close, // "close" has no rule in LINE_RULES -> default "first"
                price: first.price,
                volume0: dec::zero(),
                volume1: dec::zero(),
            };
            for r in rows {
                b.volume0 += self.bars[*r].volume0;
                b.volume1 += self.bars[*r].volume1;
            }
            ts.push(first_bin + g as i64 * interval_secs);
            bars.push(b);
            firsts.push(rows[0]);
        }
        let mut out = UniData::new(ts, bars)?;
        // user columns have no rule -> "first"
        out.extra = self
            .extra
            .iter()
            .map(|(n, c)| (n.clone(), c.take(&firsts)))
            .collect();
        Ok(out)
    }

    // ------------------------------------------------------------ polars conversion

    /// Build a polars frame. Decimal columns use Decimal(38, s) with the largest scale that fits
    /// every value of the column (pyarrow turns them into python `Decimal` objects).
    pub fn to_polars(&self) -> Result<DataFrame> {
        let err = |e: PolarsError| DemeterError::data(e.to_string());
        let n = self.len();
        let ts_ms: Vec<i64> = self.ts.iter().map(|t| t * 1000).collect();
        let ts = Series::new("timestamp".into(), ts_ms)
            .cast(&DataType::Datetime(TimeUnit::Milliseconds, None))
            .map_err(err)?;
        let mut cols: Vec<Column> = vec![ts.into()];
        let dec_col = |name: &str, vals: Vec<Option<Dec>>| -> Result<Column> {
            decimal_series(name, &vals).map(|s| s.into())
        };
        let b = &self.bars;
        cols.push(dec_col(
            "netAmount0",
            b.iter()
                .map(|x| Some(dec::from_i128(x.net_amount0)))
                .collect(),
        )?);
        cols.push(dec_col(
            "netAmount1",
            b.iter()
                .map(|x| Some(dec::from_i128(x.net_amount1)))
                .collect(),
        )?);
        for (name, f) in [
            ("closeTick", (|x: &Bar| x.close_tick) as fn(&Bar) -> i32),
            ("openTick", |x: &Bar| x.open_tick),
            ("lowestTick", |x: &Bar| x.lowest_tick),
            ("highestTick", |x: &Bar| x.highest_tick),
        ] {
            // python keeps ticks as float64 after reindexing
            cols.push(
                Series::new(
                    name.into(),
                    b.iter().map(|x| f(x) as f64).collect::<Vec<f64>>(),
                )
                .into(),
            );
        }
        cols.push(dec_col(
            "inAmount0",
            b.iter()
                .map(|x| Some(dec::from_i128(x.in_amount0)))
                .collect(),
        )?);
        cols.push(dec_col(
            "inAmount1",
            b.iter()
                .map(|x| Some(dec::from_i128(x.in_amount1)))
                .collect(),
        )?);
        cols.push(dec_col(
            "currentLiquidity",
            b.iter()
                .map(|x| Some(dec::from_u128(x.current_liquidity)))
                .collect(),
        )?);
        cols.push(dec_col("close", b.iter().map(|x| Some(x.close)).collect())?);
        cols.push(dec_col("price", b.iter().map(|x| Some(x.price)).collect())?);
        cols.push(dec_col(
            "volume0",
            b.iter().map(|x| Some(x.volume0)).collect(),
        )?);
        cols.push(dec_col(
            "volume1",
            b.iter().map(|x| Some(x.volume1)).collect(),
        )?);
        for (name, c) in &self.extra {
            let s: Series = match c {
                ExtraColumn::Dec(v) => decimal_series(name, v)?,
                ExtraColumn::F64(v) => Series::new(name.as_str().into(), v.clone()),
                ExtraColumn::I64(v) => Series::new(name.as_str().into(), v.clone()),
                ExtraColumn::Bool(v) => Series::new(name.as_str().into(), v.clone()),
                ExtraColumn::Str(v) => Series::new(name.as_str().into(), v.clone()),
            };
            cols.push(s.into());
        }
        let _ = n;
        DataFrame::new_infer_height(cols).map_err(err)
    }

    /// Read a frame produced by [`to_polars`] or by python (pandas -> arrow). Numeric python
    /// columns may arrive as float, int, decimal or string; all are accepted.
    pub fn from_polars(df: &DataFrame, pool: Option<&UniV3Pool>) -> Result<UniData> {
        let err = |e: PolarsError| DemeterError::data(e.to_string());
        let n = df.height();
        let ts_col = df.column("timestamp").map_err(err)?;
        let ts_ms = ts_col
            .cast(&DataType::Datetime(TimeUnit::Milliseconds, None))
            .map_err(err)?
            .cast(&DataType::Int64)
            .map_err(err)?;
        let ts: Vec<Ts> = ts_ms
            .i64()
            .map_err(err)?
            .iter()
            .map(|v| v.unwrap_or(0) / 1000)
            .collect();

        let get_str = |name: &str| -> Result<Option<Vec<Option<String>>>> {
            match df.column(name) {
                Ok(c) => {
                    let s = c.cast(&DataType::String).map_err(err)?;
                    Ok(Some(
                        s.str()
                            .map_err(err)?
                            .iter()
                            .map(|v| v.map(|x| x.to_string()))
                            .collect(),
                    ))
                }
                Err(_) => Ok(None),
            }
        };
        let parse_dec = |name: &str, v: &Option<String>| -> Result<Option<Dec>> {
            match v {
                None => Ok(None),
                Some(s) => dec::parse_lossy(s)
                    .map(Some)
                    .map_err(|e| DemeterError::data(format!("{name}: {e}"))),
            }
        };
        let dec_column = |name: &str, required: bool| -> Result<Vec<Dec>> {
            match get_str(name)? {
                Some(v) => v
                    .iter()
                    .map(|x| parse_dec(name, x).map(|d| d.unwrap_or(Dec::NAN)))
                    .collect(),
                None if required => Err(DemeterError::data(format!("column {name} missing"))),
                None => Ok(vec![Dec::NAN; n]),
            }
        };
        let to_i128 = |d: &Dec| if d.is_nan() { 0 } else { dec::trunc_to_i128(d) };
        let to_tick = |d: &Dec| {
            if d.is_nan() {
                i32::MIN
            } else {
                dec::trunc_to_i128(d) as i32
            }
        };

        let close_tick = dec_column("closeTick", true)?;
        let open_tick = dec_column("openTick", false)?;
        let lowest = dec_column("lowestTick", false)?;
        let highest = dec_column("highestTick", false)?;
        let net0 = dec_column("netAmount0", false)?;
        let net1 = dec_column("netAmount1", false)?;
        let in0 = dec_column("inAmount0", true)?;
        let in1 = dec_column("inAmount1", true)?;
        let liq = dec_column("currentLiquidity", true)?;
        let close = dec_column("close", false)?;
        let price = dec_column("price", pool.is_none())?;
        let vol0 = dec_column("volume0", false)?;
        let vol1 = dec_column("volume1", false)?;

        let mut bars = Vec::with_capacity(n);
        for i in 0..n {
            let ct = to_tick(&close_tick[i]);
            let pick = |v: &Dec| if v.is_nan() { ct } else { to_tick(v) };
            bars.push(Bar {
                net_amount0: to_i128(&net0[i]),
                net_amount1: to_i128(&net1[i]),
                close_tick: ct,
                open_tick: pick(&open_tick[i]),
                lowest_tick: pick(&lowest[i]),
                highest_tick: pick(&highest[i]),
                in_amount0: to_i128(&in0[i]),
                in_amount1: to_i128(&in1[i]),
                current_liquidity: to_i128(&liq[i]).max(0) as u128,
                close: close[i],
                price: price[i],
                volume0: vol0[i],
                volume1: vol1[i],
            });
        }
        let mut out = UniData::new(ts, bars)?;
        let need_stats = out
            .bars
            .iter()
            .any(|b| b.price.is_nan() || b.close.is_nan() || b.volume0.is_nan());
        if need_stats {
            if let Some(pool) = pool {
                out.add_statistic_columns(pool)?;
            }
        }
        // any other column becomes a user column
        for c in df.columns() {
            let name = c.name().as_str();
            if BASE_COLUMNS.contains(&name) {
                continue;
            }
            let col = match c.dtype() {
                DataType::Float32 | DataType::Float64 => {
                    let s = c.cast(&DataType::Float64).map_err(err)?;
                    ExtraColumn::F64(
                        s.f64()
                            .map_err(err)?
                            .iter()
                            .map(|v| v.unwrap_or(f64::NAN))
                            .collect(),
                    )
                }
                DataType::Boolean => ExtraColumn::Bool(c.bool().map_err(err)?.iter().collect()),
                d if d.is_integer() => {
                    let s = c.cast(&DataType::Int64).map_err(err)?;
                    ExtraColumn::I64(s.i64().map_err(err)?.iter().collect())
                }
                DataType::Decimal(_, _) => {
                    let v = get_str(name)?.unwrap();
                    ExtraColumn::Dec(
                        v.iter()
                            .map(|x| parse_dec(name, x))
                            .collect::<Result<Vec<_>>>()?,
                    )
                }
                _ => ExtraColumn::Str(get_str(name)?.unwrap()),
            };
            out.set_extra(name, col)?;
        }
        Ok(out)
    }
}

/// Scale decimals to a common scale and build a Decimal(38, scale) series.
fn decimal_series(name: &str, vals: &[Option<Dec>]) -> Result<Series> {
    let rounded: Vec<Option<Dec>> = vals
        .iter()
        .map(|v| v.map(|d| dec::round_sig(&d, EXPORT_DIGITS)))
        .collect();
    let vals = &rounded[..];
    let mut max_int = 1i32;
    let mut max_frac = 0i32;
    for v in vals.iter().flatten() {
        if v.is_nan() || v.is_infinite() {
            continue;
        }
        let (_, m, e) = dec::to_parts(v);
        if m == 0 {
            continue;
        }
        let digits = m.to_string().len() as i32;
        max_int = max_int.max(digits + e);
        max_frac = max_frac.max(-e);
    }
    let scale = max_frac.min(38 - max_int).clamp(0, 38);
    let scaled: Vec<Option<i128>> = vals
        .iter()
        .map(|v| match v {
            Some(d) if !d.is_nan() && !d.is_infinite() => scaled_i128(d, scale),
            _ => None,
        })
        .collect();
    let ca = Int128Chunked::from_iter_options(name.into(), scaled.into_iter());
    Ok(ca.into_decimal_unchecked(38, scale as usize).into_series())
}

/// round(d * 10^scale) as i128, half-even.
fn scaled_i128(d: &Dec, scale: i32) -> Option<i128> {
    let (neg, m, e) = dec::to_parts(d);
    let shift = e + scale;
    let v: i128 = if shift >= 0 {
        (m as i128).checked_mul(10i128.checked_pow(shift as u32)?)?
    } else {
        let div = (-shift) as u32;
        if div > 38 {
            0
        } else {
            let p = 10u128.pow(div);
            let (q, r) = (m / p, m % p);
            let half = p / 2;
            let up = r > half || (r == half && q % 2 == 1);
            (q + up as u128) as i128
        }
    };
    Some(if neg { -v } else { v })
}

// ---------------------------------------------------------------- loading CSV files

/// Raw values of one row before filling (None = NaN in pandas).
#[derive(Clone, Default)]
struct RawRow {
    net0: Option<i128>,
    net1: Option<i128>,
    close_tick: Option<i32>,
    open_tick: Option<i32>,
    lowest: Option<i32>,
    highest: Option<i32>,
    in0: Option<i128>,
    in1: Option<i128>,
    liq: Option<u128>,
}

fn parse_int(s: Option<&str>) -> Result<Option<i128>> {
    match s {
        None | Some("") => Ok(None),
        Some(s) => {
            if let Ok(v) = s.parse::<i128>() {
                return Ok(Some(v));
            }
            let d = dec::parse_lossy(s).map_err(DemeterError::data)?;
            if d.is_nan() {
                Ok(None)
            } else {
                Ok(Some(dec::trunc_to_i128(&d)))
            }
        }
    }
}

fn parse_tick(s: Option<&str>) -> Result<Option<i32>> {
    match s {
        None | Some("") => Ok(None),
        Some(s) => {
            let f: f64 = s
                .parse()
                .map_err(|_| DemeterError::data(format!("invalid tick '{s}'")))?;
            if f.is_nan() {
                Ok(None)
            } else {
                Ok(Some(f as i32))
            }
        }
    }
}

fn read_day_csv(path: &Path) -> Result<Vec<(Ts, RawRow)>> {
    let err = |e: PolarsError| DemeterError::data(format!("{}: {e}", path.display()));
    let df = CsvReadOptions::default()
        .with_has_header(true)
        .with_infer_schema_length(Some(0)) // everything as string: amounts exceed i64
        .try_into_reader_with_file_path(Some(path.into()))
        .map_err(err)?
        .finish()
        .map_err(err)?;
    let n = df.height();
    let col = |name: &str| -> Result<Option<StringChunked>> {
        match df.column(name) {
            Ok(c) => Ok(Some(c.str().map_err(err)?.clone())),
            Err(_) => Ok(None),
        }
    };
    let ts = col("timestamp")?
        .ok_or_else(|| DemeterError::data(format!("{}: no timestamp column", path.display())))?;
    let (net0, net1) = (col("netAmount0")?, col("netAmount1")?);
    let (ct, ot, lt, ht) = (
        col("closeTick")?,
        col("openTick")?,
        col("lowestTick")?,
        col("highestTick")?,
    );
    let (in0, in1, liq) = (
        col("inAmount0")?,
        col("inAmount1")?,
        col("currentLiquidity")?,
    );
    let get = |c: &Option<StringChunked>, i: usize| -> Option<String> {
        c.as_ref().and_then(|c| c.get(i).map(|s| s.to_string()))
    };
    let mut rows = Vec::with_capacity(n);
    for i in 0..n {
        let t = ts
            .get(i)
            .ok_or_else(|| DemeterError::data("empty timestamp"))?;
        let dt = NaiveDateTime::parse_from_str(t, "%Y-%m-%d %H:%M:%S")
            .or_else(|_| NaiveDateTime::parse_from_str(t, "%Y-%m-%d %H:%M:%S%.f"))
            .or_else(|_| NaiveDateTime::parse_from_str(t, "%Y-%m-%dT%H:%M:%S"))
            .map_err(|e| DemeterError::data(format!("timestamp '{t}': {e}")))?;
        let row = RawRow {
            net0: parse_int(get(&net0, i).as_deref())?,
            net1: parse_int(get(&net1, i).as_deref())?,
            close_tick: parse_tick(get(&ct, i).as_deref())?,
            open_tick: parse_tick(get(&ot, i).as_deref())?,
            lowest: parse_tick(get(&lt, i).as_deref())?,
            highest: parse_tick(get(&ht, i).as_deref())?,
            in0: parse_int(get(&in0, i).as_deref())?,
            in1: parse_int(get(&in1, i).as_deref())?,
            liq: parse_int(get(&liq, i).as_deref())?.map(|v| v.max(0) as u128),
        };
        rows.push((naive_to_ts(&dt), row));
    }
    Ok(rows)
}

/// python `load_uni_v3_data`: read one csv per day, reindex to a full minute grid, fill gaps and
/// add statistic columns. (The python feather cache in ~/.demeter is not used: reading csv here
/// is fast enough.)
pub fn load_uni_v3_data(
    pool: &UniV3Pool,
    chain: &str,
    contract_addr: &str,
    start: NaiveDate,
    end: NaiveDate,
    data_path: &str,
) -> Result<UniData> {
    if start > end {
        return Err(DemeterError::demeter(format!(
            "start date {start} should earlier than end date {end}"
        )));
    }
    let grid_start = naive_to_ts(&start.and_hms_opt(0, 0, 0).unwrap());
    let grid_end = naive_to_ts(
        &(end.and_hms_opt(0, 0, 0).unwrap() + Duration::days(1) - Duration::minutes(1)),
    );
    let n = ((grid_end - grid_start) / 60 + 1) as usize;
    let mut raw: Vec<RawRow> = vec![RawRow::default(); n];

    let mut day = start;
    while day <= end {
        let d = day.format("%Y-%m-%d");
        let new_path = Path::new(data_path).join(format!(
            "{}-{}-{}.minute.csv",
            chain.to_lowercase(),
            contract_addr,
            d
        ));
        let path = if new_path.exists() {
            new_path.clone()
        } else {
            Path::new(data_path).join(format!("{chain}-{contract_addr}-{d}.csv"))
        };
        if !path.exists() {
            return Err(DemeterError::data(format!(
                "resource file {} not found, please download with demeter-fetch: https://github.com/zelos-alpha/demeter-fetch",
                new_path.display()
            )));
        }
        for (t, row) in read_day_csv(&path)? {
            if t >= grid_start && t <= grid_end && (t - grid_start) % 60 == 0 {
                raw[((t - grid_start) / 60) as usize] = row;
            }
        }
        day += Duration::days(1);
    }
    let ts: Vec<Ts> = (0..n).map(|i| grid_start + i as i64 * 60).collect();
    let bars = fill_rows(raw)?;
    let mut data = UniData::new(ts, bars)?;
    data.add_statistic_columns(pool)?;
    Ok(data)
}

/// python `data.fillna` followed by `df.bfill()` when the first close tick is missing.
fn fill_rows(mut raw: Vec<RawRow>) -> Result<Vec<Bar>> {
    // closeTick: ffill
    let mut last = None;
    for r in raw.iter_mut() {
        if r.close_tick.is_none() {
            r.close_tick = last;
        }
        last = r.close_tick;
    }
    // open/lowest/highest: fill with closeTick; currentLiquidity: ffill; amounts: 0
    let mut last_liq = None;
    for r in raw.iter_mut() {
        if r.open_tick.is_none() {
            r.open_tick = r.close_tick;
        }
        if r.lowest.is_none() {
            r.lowest = r.close_tick;
        }
        if r.highest.is_none() {
            r.highest = r.close_tick;
        }
        if r.liq.is_none() {
            r.liq = last_liq;
        }
        last_liq = r.liq;
        r.net0.get_or_insert(0);
        r.net1.get_or_insert(0);
        r.in0.get_or_insert(0);
        r.in1.get_or_insert(0);
    }
    // leading gap: bfill every column
    if raw.first().map(|r| r.close_tick.is_none()).unwrap_or(false) {
        macro_rules! bfill {
            ($f:ident) => {{
                let mut next = None;
                for r in raw.iter_mut().rev() {
                    if r.$f.is_none() {
                        r.$f = next;
                    }
                    next = r.$f;
                }
            }};
        }
        bfill!(close_tick);
        bfill!(open_tick);
        bfill!(lowest);
        bfill!(highest);
        bfill!(liq);
    }
    raw.into_iter()
        .map(|r| {
            let ct = r
                .close_tick
                .ok_or_else(|| DemeterError::data("no data: closeTick is empty"))?;
            Ok(Bar {
                net_amount0: r.net0.unwrap(),
                net_amount1: r.net1.unwrap(),
                close_tick: ct,
                open_tick: r.open_tick.unwrap_or(ct),
                lowest_tick: r.lowest.unwrap_or(ct),
                highest_tick: r.highest.unwrap_or(ct),
                in_amount0: r.in0.unwrap(),
                in_amount1: r.in1.unwrap(),
                current_liquidity: r
                    .liq
                    .ok_or_else(|| DemeterError::data("no data: currentLiquidity is empty"))?,
                close: Dec::NAN,
                price: Dec::NAN,
                volume0: Dec::NAN,
                volume1: Dec::NAN,
            })
        })
        .collect()
}

/// python `get_price_from_data`: base token price per row, quote token price 1.
pub fn price_from_data(data: &UniData, pool: &UniV3Pool) -> (Vec<String>, Vec<Vec<Dec>>) {
    let base: Vec<Dec> = data.bars.iter().map(|b| b.price).collect();
    let quote = vec![dec::one(); data.len()];
    (
        vec![pool.base_token.name.clone(), pool.quote_token.name.clone()],
        vec![base, quote],
    )
}

/// Write a frame to Arrow IPC bytes (used to hand data to python without pyo3-polars).
pub fn frame_to_ipc(df: &mut DataFrame) -> Result<Vec<u8>> {
    let mut buf = Vec::new();
    IpcWriter::new(&mut buf)
        .finish(df)
        .map_err(|e| DemeterError::data(e.to_string()))?;
    Ok(buf)
}

pub fn frame_from_ipc(bytes: &[u8]) -> Result<DataFrame> {
    IpcReader::new(std::io::Cursor::new(bytes))
        .finish()
        .map_err(|e| DemeterError::data(e.to_string()))
}

/// Public wrapper of the adaptive-scale Decimal(38, s) series builder.
pub fn decimal_series_pub(name: &str, vals: &[Option<Dec>]) -> Result<Series> {
    decimal_series(name, vals)
}

/// Significant digits of decimals exported to python frames (python demeter runs at 35).
pub const EXPORT_DIGITS: u32 = 35;

impl UniData {
    /// Names of all columns (base columns first, then user columns), like `df.columns`.
    pub fn column_names(&self) -> Vec<String> {
        let mut v: Vec<String> = BASE_COLUMNS[..13].iter().map(|s| s.to_string()).collect();
        v.extend(self.extra.iter().map(|(n, _)| n.clone()));
        v
    }

    /// One column as a polars frame `[timestamp, name]` (python `df[name]`).
    pub fn column_frame(&self, name: &str) -> Result<DataFrame> {
        let err = |e: PolarsError| DemeterError::data(e.to_string());
        let ts_ms: Vec<i64> = self.ts.iter().map(|t| t * 1000).collect();
        let ts = Series::new("timestamp".into(), ts_ms)
            .cast(&DataType::Datetime(TimeUnit::Milliseconds, None))
            .map_err(err)?;
        let b = &self.bars;
        let dec_of = |f: fn(&Bar) -> Dec| -> Result<Series> {
            decimal_series(name, &b.iter().map(|x| Some(f(x))).collect::<Vec<_>>())
        };
        let tick_of = |f: fn(&Bar) -> i32| -> Series {
            Series::new(
                name.into(),
                b.iter().map(|x| f(x) as f64).collect::<Vec<f64>>(),
            )
        };
        let col: Series = match name {
            "netAmount0" => dec_of(|x| dec::from_i128(x.net_amount0))?,
            "netAmount1" => dec_of(|x| dec::from_i128(x.net_amount1))?,
            "inAmount0" => dec_of(|x| dec::from_i128(x.in_amount0))?,
            "inAmount1" => dec_of(|x| dec::from_i128(x.in_amount1))?,
            "currentLiquidity" => dec_of(|x| dec::from_u128(x.current_liquidity))?,
            "close" => dec_of(|x| x.close)?,
            "price" => dec_of(|x| x.price)?,
            "volume0" => dec_of(|x| x.volume0)?,
            "volume1" => dec_of(|x| x.volume1)?,
            "closeTick" => tick_of(|x| x.close_tick),
            "openTick" => tick_of(|x| x.open_tick),
            "lowestTick" => tick_of(|x| x.lowest_tick),
            "highestTick" => tick_of(|x| x.highest_tick),
            _ => match self.extra(name) {
                Some(ExtraColumn::Dec(v)) => decimal_series(name, v)?,
                Some(ExtraColumn::F64(v)) => Series::new(name.into(), v.clone()),
                Some(ExtraColumn::I64(v)) => Series::new(name.into(), v.clone()),
                Some(ExtraColumn::Bool(v)) => Series::new(name.into(), v.clone()),
                Some(ExtraColumn::Str(v)) => Series::new(name.into(), v.clone()),
                None => return Err(DemeterError::Data(format!("KeyError: {name}"))),
            },
        };
        DataFrame::new_infer_height(vec![ts.into(), col.into()]).map_err(err)
    }

    /// Align a column given as (timestamps, values) to this table's rows (python index alignment
    /// in `df[name] = series`): rows without a matching timestamp get None.
    pub fn align_rows(&self, ts: &[Ts]) -> Vec<Option<usize>> {
        let map: HashMap<Ts, usize> = ts.iter().enumerate().map(|(i, t)| (*t, i)).collect();
        self.ts.iter().map(|t| map.get(t).copied()).collect()
    }
}
