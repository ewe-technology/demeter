//! The backtest loop (python `demeter/core/actuator.py`).

use crate::actions::{Action, ActionLog};
use crate::broker::{shared, AccountRow, Broker, Shared};
use crate::dec::{self, Dec};
use crate::error::{DemeterError, Result};
use crate::types::{EngineCompat, TokenInfo, Ts};
use crate::uniswap::UniLpMarket;
use polars::prelude::*;
use std::collections::HashMap;
use std::rc::Rc;

/// Token prices per timestamp, in the broker's quote token (python `actuator.token_prices`).
#[derive(Clone, Debug, Default)]
pub struct PriceTable {
    pub ts: Vec<Ts>,
    pub tokens: Vec<String>,
    /// one column per token, aligned with `ts`
    pub cols: Vec<Vec<Dec>>,
    grid: Option<(Ts, Ts)>,
    lookup: HashMap<Ts, usize>,
}

impl PriceTable {
    pub fn new(ts: Vec<Ts>, tokens: Vec<String>, cols: Vec<Vec<Dec>>) -> Result<Self> {
        if tokens.len() != cols.len() || cols.iter().any(|c| c.len() != ts.len()) {
            return Err(DemeterError::data("price table columns do not match"));
        }
        let mut t = PriceTable {
            ts,
            tokens: tokens.iter().map(|x| x.to_uppercase()).collect(),
            cols,
            grid: None,
            lookup: HashMap::new(),
        };
        t.index();
        Ok(t)
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

    pub fn token_index(&self, name: &str) -> Option<usize> {
        self.tokens.iter().position(|t| t == name)
    }

    pub fn get(&self, row: usize, name: &str) -> Result<Dec> {
        let c = self
            .token_index(name)
            .ok_or_else(|| DemeterError::Data(format!("KeyError: price of {name} not found")))?;
        Ok(self.cols[c][row])
    }

    /// Set or add a column with a constant value (python `self._token_prices[USD.name] = 1`).
    pub fn set_constant(&mut self, name: &str, v: Dec) {
        let col = vec![v; self.ts.len()];
        match self.token_index(name) {
            Some(i) => self.cols[i] = col,
            None => {
                self.tokens.push(name.to_string());
                self.cols.push(col);
            }
        }
    }

    /// python `pd.concat([old, new])` (rows appended; columns missing on one side become NaN).
    pub fn concat(&self, other: &PriceTable) -> Result<PriceTable> {
        let mut tokens = self.tokens.clone();
        for t in &other.tokens {
            if !tokens.contains(t) {
                tokens.push(t.clone());
            }
        }
        let mut ts = self.ts.clone();
        ts.extend(other.ts.iter());
        let cols = tokens
            .iter()
            .map(|t| {
                let mut c: Vec<Dec> = match self.token_index(t) {
                    Some(i) => self.cols[i].clone(),
                    None => vec![Dec::NAN; self.len()],
                };
                match other.token_index(t) {
                    Some(i) => c.extend(other.cols[i].iter()),
                    None => c.extend(std::iter::repeat_n(Dec::NAN, other.len())),
                }
                c
            })
            .collect();
        PriceTable::new(ts, tokens, cols)
    }

    /// python `token_prices.resample(interval).first()`
    pub fn resample(&self, interval_secs: i64) -> Result<PriceTable> {
        if interval_secs <= 60 || self.is_empty() {
            return Ok(self.clone());
        }
        let day0 = self.ts[0] - self.ts[0].rem_euclid(86400);
        let bin_of = |t: Ts| day0 + (t - day0).div_euclid(interval_secs) * interval_secs;
        let mut ts = vec![];
        let mut firsts = vec![];
        for (i, t) in self.ts.iter().enumerate() {
            let b = bin_of(*t);
            if ts.last() != Some(&b) {
                ts.push(b);
                firsts.push(i);
            }
        }
        let cols = self
            .cols
            .iter()
            .map(|c| firsts.iter().map(|r| c[*r]).collect())
            .collect();
        PriceTable::new(ts, self.tokens.clone(), cols)
    }
}

/// Data of one iteration (python `Snapshot`). Market rows are read through the markets.
#[derive(Clone, Copy, Debug)]
pub struct Snapshot {
    pub ts: Ts,
    pub row_id: usize,
    /// row in the price table
    pub price_row: usize,
}

/// Handles a strategy uses to reach the engine. Cheap to clone.
#[derive(Clone)]
pub struct Ctx {
    pub broker: Shared<Broker>,
    pub prices: Rc<PriceTable>,
    pub log: Shared<ActionLog>,
    pub account_status: Shared<Vec<AccountRow>>,
    pub compat: EngineCompat,
}

impl Ctx {
    pub fn price(&self, snapshot: &Snapshot, token: &str) -> Result<Dec> {
        self.prices.get(snapshot.price_row, &token.to_uppercase())
    }
    pub fn market(&self, name: &str) -> Result<Shared<UniLpMarket>> {
        self.broker
            .borrow()
            .market_by_name(name)
            .ok_or_else(|| DemeterError::Data(format!("KeyError: market {name}")))
    }
}

/// User strategy. All hooks default to "do nothing", `on_error` re-raises (python default).
pub trait Strategy {
    fn initialize(&mut self, _ctx: &Ctx) -> Result<()> {
        Ok(())
    }
    fn before_bar(&mut self, _ctx: &Ctx, _s: &Snapshot) -> Result<()> {
        Ok(())
    }
    /// Evaluate triggers (python iterates `strategy.triggers`, then drops outdated ones).
    fn run_triggers(&mut self, _ctx: &Ctx, _s: &Snapshot) -> Result<()> {
        Ok(())
    }
    fn on_bar(&mut self, _ctx: &Ctx, _s: &Snapshot) -> Result<()> {
        Ok(())
    }
    fn after_bar(&mut self, _ctx: &Ctx, _s: &Snapshot) -> Result<()> {
        Ok(())
    }
    /// Called with the actions of the current iteration (only when there are some).
    fn notify(&mut self, _ctx: &Ctx, _actions: &[Action]) -> Result<()> {
        Ok(())
    }
    fn finalize(&mut self, _ctx: &Ctx) -> Result<()> {
        Ok(())
    }
    fn on_error(&mut self, _ctx: &Ctx, _s: &Snapshot, e: DemeterError) -> Result<()> {
        Err(e)
    }
}

/// python `Actuator`.
pub struct Actuator {
    pub broker: Shared<Broker>,
    pub log: Shared<ActionLog>,
    pub prices: Option<Rc<PriceTable>>,
    pub account_status: Shared<Vec<AccountRow>>,
    pub init_account_status: Option<AccountRow>,
    /// python `actuator.interval` in seconds (default 60 = "1min")
    pub interval_secs: i64,
    pub compat: EngineCompat,
    pub finished: bool,
}

impl Actuator {
    pub fn new(allow_negative_balance: bool) -> Self {
        let log = shared(ActionLog::default());
        Actuator {
            broker: shared(Broker::new(allow_negative_balance, log.clone())),
            log,
            prices: None,
            account_status: shared(vec![]),
            init_account_status: None,
            interval_secs: 60,
            compat: EngineCompat::default(),
            finished: false,
        }
    }

    pub fn add_market(&self, market: Shared<UniLpMarket>) -> Result<()> {
        market.borrow_mut().compat = self.compat;
        self.broker.borrow_mut().add_market(market)
    }

    /// python `set_price(prices, quote_token)`; a second call appends rows like `pd.concat`.
    pub fn set_price(&mut self, prices: PriceTable, quote_token: TokenInfo) -> Result<()> {
        let mut table = match &self.prices {
            None => prices,
            Some(old) => old.concat(&prices)?,
        };
        if quote_token == TokenInfo::usd() {
            table.set_constant("USD", dec::one());
        }
        self.broker.borrow_mut().quote_token = Some(quote_token);
        self.prices = Some(Rc::new(table));
        Ok(())
    }

    pub fn ctx(&self) -> Result<Ctx> {
        Ok(Ctx {
            broker: self.broker.clone(),
            prices: self
                .prices
                .clone()
                .ok_or_else(|| DemeterError::demeter("token prices is not set"))?,
            log: self.log.clone(),
            account_status: self.account_status.clone(),
            compat: self.compat,
        })
    }

    fn markets(&self) -> Vec<Shared<UniLpMarket>> {
        self.broker
            .borrow()
            .markets
            .iter()
            .map(|(_, m)| m.clone())
            .collect()
    }

    fn check_backtest(&mut self) -> Result<()> {
        if self.interval_secs < 60 {
            return Err(DemeterError::demeter(
                "interval should be larger than 1 minute",
            ));
        }
        if self.prices.is_none() {
            // python intends to take prices from the uniswap market automatically
            let default = self.broker.borrow().default_market();
            if let Some(m) = default {
                let (table, quote) = {
                    let m = m.borrow();
                    let (tokens, cols) = crate::data::price_from_data(m.data()?, &m.pool);
                    (
                        PriceTable::new(m.data()?.ts.clone(), tokens, cols)?,
                        m.pool.quote_token.clone(),
                    )
                };
                self.set_price(table, quote)?;
            }
        }
        self.broker.borrow().check_backtest()?;
        let prices = self
            .prices
            .clone()
            .ok_or_else(|| DemeterError::demeter("token prices is not set"))?;
        let broker = self.broker.borrow();
        let default = broker
            .default_market()
            .ok_or_else(|| DemeterError::assertion("No market assigned"))?;
        let d = default.borrow();
        let data = d.data()?;
        if prices.ts.first() > data.ts.first() || prices.ts.last() < data.ts.last() {
            return Err(DemeterError::demeter(
                "Time range of price doesn't cover market data",
            ));
        }
        for (info, m) in &broker.markets {
            if prices
                .token_index(&m.borrow().pool.quote_token.name)
                .is_none()
            {
                return Err(DemeterError::demeter(format!(
                    "Quote token price of market '{}' is not contained in price dataframe.",
                    info.name
                )));
            }
        }
        Ok(())
    }

    /// python `get_test_range`: timestamps of the market with the most rows.
    fn test_range(&self) -> Result<Vec<Ts>> {
        let mut best: Option<Vec<Ts>> = None;
        for m in self.markets() {
            let m = m.borrow();
            let ts = &m.data()?.ts;
            if best.as_ref().map(|b| ts.len() > b.len()).unwrap_or(true) {
                best = Some(ts.clone());
            }
        }
        best.ok_or_else(|| DemeterError::assertion("No market assigned"))
    }

    fn set_market_snapshot(&self, ts: Ts, update: bool) -> Result<()> {
        for m in self.markets() {
            let mut m = m.borrow_mut();
            if !update || m.has_update {
                m.set_market_status(ts)?;
            }
        }
        Ok(())
    }

    fn account_status_at(&self, price_row: usize, ts: Ts) -> Result<AccountRow> {
        let prices = self.prices.clone().unwrap();
        let price_of = |name: &str| prices.get(price_row, name);
        self.broker.borrow().get_account_status(&price_of, ts)
    }

    /// python `Actuator.run`.
    pub fn run(&mut self, strategy: &mut dyn Strategy) -> Result<()> {
        // reset
        {
            let mut log = self.log.borrow_mut();
            log.actions.clear();
            log.bar_start = 0;
        }
        self.account_status.borrow_mut().clear();
        self.finished = false;

        self.check_backtest()?;
        let mut index = self.test_range()?;
        if self.interval_secs != 60 {
            for m in self.markets() {
                m.borrow_mut().resample(self.interval_secs)?;
            }
            let p = self.prices.as_ref().unwrap().resample(self.interval_secs)?;
            self.prices = Some(Rc::new(p));
            index = self.test_range()?;
        }
        if index.is_empty() {
            return Err(DemeterError::data("no data to backtest"));
        }
        let ctx = self.ctx()?;

        self.set_market_snapshot(index[0], false)?;
        self.log.borrow_mut().set_ts(index[0]);
        // python uses the first row of the price table here, not the first backtest row
        self.init_account_status = Some(self.account_status_at(0, index[0])?);
        strategy.initialize(&ctx)?;

        let prices = ctx.prices.clone();
        self.account_status.borrow_mut().reserve(index.len());
        for (row_id, ts) in index.iter().copied().enumerate() {
            let price_row = prices.row_of(ts).ok_or_else(|| {
                DemeterError::Data(format!(
                    "KeyError: no price at {}",
                    crate::types::ts_to_string(ts)
                ))
            })?;
            self.set_market_snapshot(ts, false)?;
            self.log.borrow_mut().set_ts(ts);
            let snapshot = Snapshot {
                ts,
                row_id,
                price_row,
            };
            let result = (|| -> Result<()> {
                strategy.before_bar(&ctx, &snapshot)?;
                strategy.run_triggers(&ctx, &snapshot)?;
                strategy.on_bar(&ctx, &snapshot)?;
                self.set_market_snapshot(ts, true)?;
                for m in self.markets() {
                    m.borrow_mut().update()?;
                }
                strategy.after_bar(&ctx, &snapshot)?;
                self.notify(strategy, &ctx)
            })();
            if let Err(e) = result {
                if !e.is_recoverable() {
                    return Err(e);
                }
                self.notify(strategy, &ctx)?;
                strategy.on_error(&ctx, &snapshot, e)?;
            }
            // pushed every iteration so strategies can read the history while running
            let row = self.account_status_at(price_row, ts)?;
            self.account_status.borrow_mut().push(row);
            // python resets `_currents.actions` at the end of the iteration
            self.log.borrow_mut().end_bar();
        }
        self.finished = true;
        strategy.finalize(&ctx)?;
        Ok(())
    }

    fn notify(&self, strategy: &mut dyn Strategy, ctx: &Ctx) -> Result<()> {
        let actions: Vec<Action> = self.log.borrow().current_actions().to_vec();
        if actions.is_empty() {
            return Ok(());
        }
        strategy.notify(ctx, &actions)
    }

    /// Account status history as a flat polars frame. Column names are `"<l1>|<l2>"` of the
    /// python MultiIndex (`net_value|`, `tokens|USDC`, `lp|net_value`, `price|ETH`, ...).
    pub fn account_status_frame(&self) -> Result<DataFrame> {
        let rows = self.account_status.borrow();
        let prices = self.prices.clone();
        account_status_frame(&rows, prices.as_deref())
    }
}

/// See [`Actuator::account_status_frame`].
pub fn account_status_frame(rows: &[AccountRow], prices: Option<&PriceTable>) -> Result<DataFrame> {
    let err = |e: PolarsError| DemeterError::data(e.to_string());
    let ts: Vec<i64> = rows.iter().map(|r| r.timestamp * 1000).collect();
    let mut cols: Vec<Column> = vec![Series::new("timestamp".into(), ts)
        .cast(&DataType::Datetime(TimeUnit::Milliseconds, None))
        .map_err(err)?
        .into()];
    let dec_col = |cols: &mut Vec<Column>, name: String, v: Vec<Option<Dec>>| -> Result<()> {
        cols.push(decimal_column(&name, &v)?);
        Ok(())
    };
    dec_col(
        &mut cols,
        "net_value|".into(),
        rows.iter().map(|r| Some(r.net_value)).collect(),
    )?;
    // token columns: union of tokens in order of first appearance
    let mut tokens: Vec<TokenInfo> = vec![];
    for r in rows {
        for (t, _) in &r.asset_balances {
            if !tokens.contains(t) {
                tokens.push(t.clone());
            }
        }
    }
    for t in &tokens {
        dec_col(
            &mut cols,
            format!("tokens|{}", t.name),
            rows.iter()
                .map(|r| {
                    r.asset_balances
                        .iter()
                        .find(|(k, _)| k == t)
                        .map(|(_, v)| *v)
                })
                .collect(),
        )?;
    }
    if let Some(first) = rows.first() {
        for (mi, (info, _)) in first.market_balances.iter().enumerate() {
            let get = |f: fn(&crate::types::UniLpBalance) -> Dec| -> Vec<Option<Dec>> {
                rows.iter()
                    .map(|r| r.market_balances.get(mi).map(|(_, b)| f(b)))
                    .collect()
            };
            dec_col(
                &mut cols,
                format!("{}|net_value", info.name),
                get(|b| b.net_value),
            )?;
            dec_col(
                &mut cols,
                format!("{}|liquidity_value", info.name),
                get(|b| b.liquidity_value),
            )?;
            dec_col(
                &mut cols,
                format!("{}|base_uncollected", info.name),
                get(|b| b.base_uncollected),
            )?;
            dec_col(
                &mut cols,
                format!("{}|quote_uncollected", info.name),
                get(|b| b.quote_uncollected),
            )?;
            dec_col(
                &mut cols,
                format!("{}|base_in_position", info.name),
                get(|b| b.base_in_position),
            )?;
            dec_col(
                &mut cols,
                format!("{}|quote_in_position", info.name),
                get(|b| b.quote_in_position),
            )?;
            let counts: Vec<Option<i64>> = rows
                .iter()
                .map(|r| {
                    r.market_balances
                        .get(mi)
                        .map(|(_, b)| b.position_count as i64)
                })
                .collect();
            cols.push(
                Series::new(
                    format!("{}|position_count", info.name).as_str().into(),
                    counts,
                )
                .into(),
            );
        }
    }
    if let Some(p) = prices {
        for (ci, name) in p.tokens.iter().enumerate() {
            let v: Vec<Option<Dec>> = rows
                .iter()
                .map(|r| p.row_of(r.timestamp).map(|i| p.cols[ci][i]))
                .collect();
            cols.push(decimal_column(&format!("price|{name}"), &v)?);
        }
    }
    DataFrame::new_infer_height(cols).map_err(err)
}

fn decimal_column(name: &str, vals: &[Option<Dec>]) -> Result<Column> {
    // reuse the data module's adaptive-scale decimal builder through a tiny UniData-free path
    crate::data::decimal_series_pub(name, vals).map(|s| s.into())
}
