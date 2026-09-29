//! Uniswap v3 LP market, ported from `demeter/uniswap/market.py` (`UniLpMarket`) and
//! `demeter/uniswap/core.py` (`V3CoreLib`).

use crate::actions::{ActionKind, ActionLog, Ud};
use crate::broker::{Shared, Wallet};
use crate::data::{self, Bar, UniData};
use crate::dec::{self, Dec};
use crate::error::{require, DemeterError, Result};
use crate::math::{self, py_pow10_f64, SqrtPrice};
use crate::types::{
    EngineCompat, MarketInfo, Position, PositionInfo, PositionStatus, TokenInfo, Ts, UniLpBalance,
    UniV3Pool,
};
use chrono::NaiveDate;
use ruint::aliases::U256;
use std::cell::Cell;
use std::sync::Arc;

/// Status of the current iteration (python `UniswapMarketStatus`): the data row with the user's
/// own liquidity added to `current_liquidity`.
#[derive(Clone, Debug)]
pub struct MarketStatus {
    pub ts: Ts,
    pub row: usize,
    pub bar: Bar,
    sqrt_price: Cell<Option<SqrtPrice>>,
}

pub struct UniLpMarket {
    pub info: MarketInfo,
    pub pool: UniV3Pool,
    pub compat: EngineCompat,
    pub data: Option<Arc<UniData>>,
    pub data_path: String,
    /// insertion ordered, like the python dict
    pub positions: Vec<(PositionInfo, Position)>,
    pub status: Option<MarketStatus>,
    /// close tick of the previous iteration (python `last_tick`); None = python NaN
    pub last_tick: Option<i32>,
    pub has_update: bool,
    pub is_open: bool,
    /// "BASE/QUOTE", unit of prices in actions
    pub price_unit: String,
    wallet: Option<Shared<Wallet>>,
    log: Option<Shared<ActionLog>>,
    /// price -> sqrt price. Bar prices come from ticks, so few distinct values repeat all the
    /// time and the 38 digit decimal sqrt is by far the most expensive per-iteration operation.
    sqrt_memo: std::cell::RefCell<std::collections::HashMap<(bool, u128, i32), SqrtPrice>>,
}

fn d0() -> Dec {
    dec::zero()
}

impl UniLpMarket {
    pub fn new(info: MarketInfo, pool: UniV3Pool) -> Self {
        let price_unit = format!("{}/{}", pool.base_token.name, pool.quote_token.name);
        UniLpMarket {
            info,
            pool,
            compat: EngineCompat::default(),
            data: None,
            data_path: "./data".into(),
            positions: vec![],
            status: None,
            last_tick: None,
            has_update: false,
            is_open: true,
            price_unit,
            wallet: None,
            log: None,
            sqrt_memo: Default::default(),
        }
    }

    pub(crate) fn attach(&mut self, wallet: Shared<Wallet>, log: Shared<ActionLog>) {
        self.wallet = Some(wallet);
        self.log = Some(log);
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

    pub fn base_token(&self) -> &TokenInfo {
        &self.pool.base_token
    }

    pub fn quote_token(&self) -> &TokenInfo {
        &self.pool.quote_token
    }

    /// python `_convert_pair`: (token0, token1) <-> (base, quote)
    pub fn convert_pair<T>(&self, a0: T, a1: T) -> (T, T) {
        if self.pool.is_token0_quote {
            (a1, a0)
        } else {
            (a0, a1)
        }
    }

    fn balance(&self, token: &TokenInfo) -> Result<Dec> {
        self.wallet()?.borrow().balance(token)
    }

    fn balance_ud(&self, token: &TokenInfo) -> Result<Ud> {
        Ok(Ud::new(self.balance(token)?, &token.name))
    }

    // ------------------------------------------------------------ data

    pub fn load_data(
        &mut self,
        chain: &str,
        contract_addr: &str,
        start: NaiveDate,
        end: NaiveDate,
    ) -> Result<()> {
        let d = data::load_uni_v3_data(
            &self.pool,
            chain,
            contract_addr,
            start,
            end,
            &self.data_path,
        )?;
        self.data = Some(Arc::new(d));
        Ok(())
    }

    pub fn set_data(&mut self, d: Arc<UniData>) {
        self.data = Some(d);
    }

    pub fn data(&self) -> Result<&Arc<UniData>> {
        self.data
            .as_ref()
            .ok_or_else(|| DemeterError::demeter("data must be type of data frame"))
    }

    /// Mutable access to the data (copy on write when shared).
    pub fn data_mut(&mut self) -> Result<&mut UniData> {
        let d = self
            .data
            .as_mut()
            .ok_or_else(|| DemeterError::demeter("data must be type of data frame"))?;
        Ok(Arc::make_mut(d))
    }

    pub fn resample(&mut self, interval_secs: i64) -> Result<()> {
        let d = self.data()?.resample(interval_secs)?;
        self.data = Some(Arc::new(d));
        Ok(())
    }

    // ------------------------------------------------------------ status

    pub fn status(&self) -> Result<&MarketStatus> {
        self.status.as_ref().ok_or_else(|| {
            DemeterError::demeter(format!("{} market status is not set", self.info.name))
        })
    }

    /// python `self._market_status.data.price`
    pub fn price(&self) -> Result<Dec> {
        Ok(self.status()?.bar.price)
    }

    /// sqrt price x96 of the current price, cached per iteration.
    pub fn current_sqrt_price(&self) -> Result<U256> {
        Ok(self.current_sqrt()?.x96)
    }

    /// sqrt price (x96 + decimal) of the current price, cached per iteration.
    pub fn current_sqrt(&self) -> Result<SqrtPrice> {
        let st = self.status()?;
        if let Some(v) = st.sqrt_price.get() {
            return Ok(v);
        }
        let key = dec::to_parts(&st.bar.price);
        let cached = self.sqrt_memo.borrow().get(&key).copied();
        let v = match cached {
            Some(v) => v,
            None => {
                let v = SqrtPrice::new(math::base_unit_price_to_sqrt_price_x96(
                    &st.bar.price,
                    self.pool.token0.decimal,
                    self.pool.token1.decimal,
                    self.pool.is_token0_quote,
                ));
                let mut memo = self.sqrt_memo.borrow_mut();
                if memo.len() > 1_000_000 {
                    memo.clear();
                }
                memo.insert(key, v);
                v
            }
        };
        st.sqrt_price.set(Some(v));
        Ok(v)
    }

    /// python `set_market_status` (called by the actuator at the start of every iteration and
    /// again after `on_bar` when `has_update` is set).
    pub fn set_market_status(&mut self, ts: Ts) -> Result<()> {
        let data = self.data()?.clone();
        let row = data.row_of(ts);
        self.is_open = row.is_some();
        self.has_update = false;
        let total_virtual_liq: u128 = self.positions.iter().map(|(_, p)| p.liquidity).sum();
        match &self.status {
            None => self.last_tick = None,
            Some(prev) if prev.ts != ts => self.last_tick = Some(prev.bar.close_tick),
            Some(prev) => {
                // second refresh inside the same iteration
                if self.compat.legacy_quirks {
                    // QUIRK 2: python reads last_tick from the status set earlier in this very
                    // iteration, so it becomes the current close tick.
                    self.last_tick = Some(prev.bar.close_tick);
                }
            }
        }
        let row = row.ok_or_else(|| {
            DemeterError::Data(format!(
                "{} not in market data",
                crate::types::ts_to_string(ts)
            ))
        })?;
        let mut bar = data.bars[row].clone();
        bar.current_liquidity += total_virtual_liq;
        self.status = Some(MarketStatus {
            ts,
            row,
            bar,
            sqrt_price: Cell::new(None),
        });
        Ok(())
    }

    /// python `set_market_status` with an explicit row (`market_status.data` given by the caller,
    /// e.g. unit tests or live use without loaded data). `row` is usize::MAX when there is no data.
    pub fn set_market_status_bar(&mut self, ts: Ts, bar: Bar) -> Result<()> {
        // python: `is_open = self._data is None or data.timestamp in self._data.index`
        self.is_open = match &self.data {
            None => true,
            Some(d) => d.row_of(ts).is_some(),
        };
        self.has_update = false;
        let total_virtual_liq: u128 = self.positions.iter().map(|(_, p)| p.liquidity).sum();
        match &self.status {
            None => self.last_tick = None,
            Some(prev) if prev.ts != ts => self.last_tick = Some(prev.bar.close_tick),
            // same iteration refreshed again: QUIRK 2 in legacy mode, keep last_tick otherwise
            Some(prev) if self.compat.legacy_quirks => self.last_tick = Some(prev.bar.close_tick),
            Some(_) => {}
        }
        let row = self
            .data
            .as_ref()
            .and_then(|d| d.row_of(ts))
            .unwrap_or(usize::MAX);
        let mut bar = bar;
        bar.current_liquidity += total_virtual_liq;
        self.status = Some(MarketStatus {
            ts,
            row,
            bar,
            sqrt_price: Cell::new(None),
        });
        Ok(())
    }

    /// python `check_market`
    pub fn check_market(&self) -> Result<()> {
        let d = self.data()?;
        require(!d.is_empty(), "market data is empty")?;
        let w = self.wallet()?;
        let mut w = w.borrow_mut();
        if !w.contains(&self.pool.base_token) {
            w.set(&self.pool.base_token, d0());
        }
        if !w.contains(&self.pool.quote_token) {
            w.set(&self.pool.quote_token, d0());
        }
        Ok(())
    }

    /// python `update` -> `__update_fee` -> `V3CoreLib.update_fee` for every position.
    pub fn update(&mut self) -> Result<()> {
        if self.positions.is_empty() {
            return Ok(());
        }
        let st = self.status()?;
        let close_tick = st.bar.close_tick;
        let current_liquidity = dec::from_u128(st.bar.current_liquidity);
        let fee_rate = self.pool.fee_rate;
        let in0 = math::from_atomic_unit(st.bar.in_amount0, self.pool.token0.decimal);
        let in1 = math::from_atomic_unit(st.bar.in_amount1, self.pool.token1.decimal);
        let last_tick = self.last_tick;
        let legacy = self.compat.legacy_quirks;
        for (info, pos) in self.positions.iter_mut() {
            let in_range = |t: i32| {
                if t >= info.upper_tick {
                    1
                } else if t < info.lower_tick {
                    -1
                } else {
                    0
                }
            };
            let now = in_range(close_tick);
            let weight = match last_tick {
                None => {
                    // QUIRK 1: python's last_tick is NaN here and in_range(NaN) == 0
                    if now == 0 {
                        Some(dec::one())
                    } else if legacy {
                        return Err(DemeterError::Data(
                            "fee weight is NaN (no previous tick), python raises decimal.InvalidOperation here".into(),
                        ));
                    } else {
                        None
                    }
                }
                Some(last) => {
                    let prev = in_range(last);
                    if now == prev {
                        if now == 0 {
                            Some(dec::one())
                        } else {
                            None
                        }
                    } else {
                        let mut r = [info.lower_tick, info.upper_tick, last, close_tick];
                        r.sort();
                        if r[2] == r[1] {
                            None
                        } else {
                            let price_delta = (last as i64 - close_tick as i64).abs();
                            let w =
                                dec::from_i64((r[2] - r[1]) as i64) / dec::from_i64(price_delta);
                            if w > dec::one() {
                                return Err(DemeterError::demeter("weight must <=1"));
                            }
                            Some(w)
                        }
                    }
                }
            };
            if let Some(weight) = weight {
                if current_liquidity.is_zero() {
                    return Err(DemeterError::Data(
                        "division by zero: current liquidity is 0".into(),
                    ));
                }
                let share = dec::from_u128(pos.liquidity) / current_liquidity;
                pos.pending_amount0 += weight * in0 * share * fee_rate;
                pos.pending_amount1 += weight * in1 * share * fee_rate;
            }
        }
        Ok(())
    }

    // ------------------------------------------------------------ positions / valuation

    pub fn position_index(&self, info: &PositionInfo) -> Option<usize> {
        self.positions.iter().position(|(k, _)| k == info)
    }

    pub fn get_position(&self, info: &PositionInfo) -> Result<&Position> {
        self.position_index(info)
            .map(|i| &self.positions[i].1)
            .ok_or_else(|| DemeterError::Data(format!("KeyError: position {:?} not found", info)))
    }

    pub fn get_position_mut(&mut self, info: &PositionInfo) -> Result<&mut Position> {
        let i = self.position_index(info).ok_or_else(|| {
            DemeterError::Data(format!("KeyError: position {:?} not found", info))
        })?;
        Ok(&mut self.positions[i].1)
    }

    fn token_amounts(&self, pos: &Position, sqrt_price: &SqrtPrice, liquidity: u128) -> (Dec, Dec) {
        if liquidity == 0 {
            return (d0(), d0());
        }
        let (lo, hi) = if pos.sqrt_lower.x96 <= pos.sqrt_upper.x96 {
            (&pos.sqrt_lower, &pos.sqrt_upper)
        } else {
            (&pos.sqrt_upper, &pos.sqrt_lower)
        };
        let side = if sqrt_price.x96 <= lo.x96 {
            -1
        } else if sqrt_price.x96 >= hi.x96 {
            1
        } else {
            0
        };
        if side != 0 {
            // outside the range the amounts only depend on liquidity: most positions of a
            // multi-band strategy are out of range, so this avoids most of the decimal math
            if let Some(c) = pos.out_of_range_cache.get() {
                if c.liquidity == liquidity && c.side == side {
                    return c.amounts;
                }
            }
            let amounts = math::get_amounts_fast(
                sqrt_price,
                &pos.sqrt_lower,
                &pos.sqrt_upper,
                liquidity,
                self.pool.token0.decimal,
                self.pool.token1.decimal,
            );
            pos.out_of_range_cache
                .set(Some(crate::types::OutOfRangeAmounts {
                    liquidity,
                    side,
                    amounts,
                }));
            return amounts;
        }
        math::get_amounts_fast(
            sqrt_price,
            &pos.sqrt_lower,
            &pos.sqrt_upper,
            liquidity,
            self.pool.token0.decimal,
            self.pool.token1.decimal,
        )
    }

    fn value_of(&self, a0: Dec, a1: Dec, pool_price: Dec) -> Dec {
        let (base, quote) = self.convert_pair(a0, a1);
        base * pool_price + quote
    }

    /// python `get_position_amount`
    pub fn get_position_amount(&self, info: &PositionInfo) -> Result<(Dec, Dec)> {
        let Some(i) = self.position_index(info) else {
            return Ok((d0(), d0()));
        };
        let sqrt = self.current_sqrt()?;
        let pos = &self.positions[i].1;
        Ok(self.token_amounts(pos, &sqrt, pos.liquidity))
    }

    /// python `get_position_status`
    pub fn get_position_status(&self, info: &PositionInfo) -> Result<PositionStatus> {
        require(self.position_index(info).is_some(), "Position not exist")?;
        let price = self.price()?;
        let (l0, l1) = self.get_position_amount(info)?;
        let p = self.get_position(info)?;
        let (a0, a1) = (l0 + p.pending_amount0, l1 + p.pending_amount1);
        Ok(PositionStatus {
            liquidity: p.liquidity,
            liquidity_amount0: l0,
            liquidity_amount1: l1,
            liquidity_value: self.value_of(l0, l1, price),
            pending_amount0: p.pending_amount0,
            pending_amount1: p.pending_amount1,
            pending_value: self.value_of(p.pending_amount0, p.pending_amount1, price),
            amount0: a0,
            amount1: a1,
            value: self.value_of(a0, a1, price),
            h: p.upper_price / p.init_price,
            l: p.lower_price / p.init_price,
            p: price / p.init_price,
        })
    }

    /// python `get_market_balance`
    pub fn get_market_balance(&self) -> Result<UniLpBalance> {
        let price = self.price()?;
        let mut base_fee_sum = d0();
        let mut quote_fee_sum = d0();
        let mut dep0 = d0();
        let mut dep1 = d0();
        let mut count = 0usize;
        if self.positions.iter().any(|(_, p)| !p.transferred) {
            let sqrt = self.current_sqrt()?;
            for (_, pos) in &self.positions {
                if pos.transferred {
                    continue;
                }
                count += 1;
                let (bf, qf) = self.convert_pair(pos.pending_amount0, pos.pending_amount1);
                base_fee_sum += bf;
                quote_fee_sum += qf;
                let (a0, a1) = self.token_amounts(pos, &sqrt, pos.liquidity);
                dep0 += a0;
                dep1 += a1;
            }
        }
        let (liq_base, liq_quote) = self.convert_pair(dep0, dep1);
        let liquidity_value = liq_base * price + liq_quote * dec::one();
        let fee_value = base_fee_sum * price + quote_fee_sum * dec::one();
        Ok(UniLpBalance {
            net_value: fee_value + liquidity_value,
            liquidity_value,
            base_uncollected: base_fee_sum,
            quote_uncollected: quote_fee_sum,
            base_in_position: liq_base,
            quote_in_position: liq_quote,
            position_count: count,
        })
    }

    pub fn transfer_position_out(&mut self, info: &PositionInfo) -> Result<()> {
        match self.position_index(info) {
            Some(i) if !self.positions[i].1.transferred => {
                self.positions[i].1.transferred = true;
                Ok(())
            }
            _ => Err(DemeterError::demeter(
                "position not exist or has transferred out ",
            )),
        }
    }

    pub fn transfer_position_in(&mut self, info: &PositionInfo) -> Result<()> {
        match self.position_index(info) {
            Some(i) if self.positions[i].1.transferred => {
                self.positions[i].1.transferred = false;
                Ok(())
            }
            _ => Err(DemeterError::demeter(
                "position not exist or has not transferred yet ",
            )),
        }
    }

    // ------------------------------------------------------------ price <-> tick

    pub fn tick_to_price(&self, tick: i32) -> Result<Dec> {
        math::tick_to_base_unit_price(
            tick,
            self.pool.token0.decimal,
            self.pool.token1.decimal,
            self.pool.is_token0_quote,
        )
    }

    /// Tick of a price without snapping to the tick spacing (`UniLpMarketV2.price_to_raw_tick`).
    pub fn price_to_raw_tick(&self, price: &Dec) -> i32 {
        math::base_unit_price_to_tick(
            price,
            self.pool.token0.decimal,
            self.pool.token1.decimal,
            self.pool.is_token0_quote,
            self.compat.legacy_quirks,
        )
    }

    /// python `price_to_tick` (snapped to the nearest usable tick)
    pub fn price_to_tick(&self, price: &Dec) -> i32 {
        math::nearest_usable_tick(self.price_to_raw_tick(price), self.pool.tick_spacing)
    }

    // ------------------------------------------------------------ liquidity

    fn ensure_open(&self) -> Result<()> {
        if !self.is_open {
            return Err(DemeterError::demeter(format!(
                "{} is not open.",
                self.info.name
            )));
        }
        Ok(())
    }

    /// python `_add_liquidity_by_tick` (token0/token1 amounts, ticks must match the spacing).
    pub fn add_liquidity_by_tick_raw(
        &mut self,
        token0_amount: Dec,
        token1_amount: Dec,
        lower_tick: i32,
        upper_tick: i32,
        sqrt_price_x96: Option<U256>,
    ) -> Result<(PositionInfo, Dec, Dec, u128)> {
        self.ensure_open()?;
        let spacing = self.pool.tick_spacing;
        require(
            lower_tick % spacing == 0 && upper_tick % spacing == 0,
            "tick should match tick space",
        )?;
        let sqrt = match sqrt_price_x96 {
            Some(s) => SqrtPrice::new(s),
            None => self.current_sqrt()?,
        };
        if lower_tick > upper_tick {
            return Err(DemeterError::demeter(
                "lower tick should be less than upper tick",
            ));
        }
        let (d0_, d1_) = (self.pool.token0.decimal, self.pool.token1.decimal);
        let sqrt_lower = SqrtPrice::new(math::get_sqrt_ratio_at_tick(lower_tick)?);
        let sqrt_upper = SqrtPrice::new(math::get_sqrt_ratio_at_tick(upper_tick)?);
        let liq = math::get_liquidity_with_sqrt(
            sqrt.x96,
            sqrt_lower.x96,
            sqrt_upper.x96,
            &token0_amount,
            &token1_amount,
            d0_,
            d1_,
        );
        let liquidity: u128 = if liq > U256::from(u128::MAX) {
            u128::MAX
        } else {
            liq.to::<u128>()
        };
        let (used0, used1) =
            math::get_amounts_fast(&sqrt, &sqrt_lower, &sqrt_upper, liquidity, d0_, d1_);
        let info = PositionInfo {
            lower_tick,
            upper_tick,
        };
        match self.position_index(&info) {
            Some(i) => self.positions[i].1.liquidity += liquidity,
            None => {
                let mut lower_price = self.tick_to_price(lower_tick)?;
                let mut upper_price = self.tick_to_price(upper_tick)?;
                let init_price = math::sqrt_price_x96_to_base_unit_price(
                    sqrt.x96,
                    d0_,
                    d1_,
                    self.pool.is_token0_quote,
                );
                if self.pool.is_token0_quote {
                    std::mem::swap(&mut lower_price, &mut upper_price);
                }
                self.positions.push((
                    info,
                    Position {
                        pending_amount0: d0(),
                        pending_amount1: d0(),
                        liquidity,
                        lower_price,
                        upper_price,
                        init_price,
                        transferred: false,
                        sqrt_lower,
                        sqrt_upper,
                        out_of_range_cache: std::cell::Cell::new(None),
                    },
                ));
            }
        }
        let w = self.wallet()?;
        w.borrow_mut().sub(&self.pool.token0, used0)?;
        w.borrow_mut().sub(&self.pool.token1, used1)?;
        self.has_update = true;
        Ok((info, used0, used1, liquidity))
    }

    #[allow(clippy::too_many_arguments)]
    fn record_add(
        &self,
        base_max: Dec,
        quote_max: Dec,
        lower_quote_price: Dec,
        upper_quote_price: Dec,
        base_used: Dec,
        quote_used: Dec,
        position: PositionInfo,
        liquidity: u128,
    ) -> Result<()> {
        let (b, q) = (self.pool.base_token.clone(), self.pool.quote_token.clone());
        self.record(ActionKind::AddLiquidity {
            base_balance_after: self.balance_ud(&b)?,
            quote_balance_after: self.balance_ud(&q)?,
            base_amount_max: Ud::new(base_max, &b.name),
            quote_amount_max: Ud::new(quote_max, &q.name),
            lower_quote_price: Ud::new(lower_quote_price, &self.price_unit),
            upper_quote_price: Ud::new(upper_quote_price, &self.price_unit),
            base_amount_actual: Ud::new(base_used, &b.name),
            quote_amount_actual: Ud::new(quote_used, &q.name),
            position,
            liquidity,
        });
        Ok(())
    }

    /// python `add_liquidity(lower_quote_price, upper_quote_price, quote_max_amount, base_max_amount)`
    pub fn add_liquidity(
        &mut self,
        lower_quote_price: Dec,
        upper_quote_price: Dec,
        quote_max_amount: Option<Dec>,
        base_max_amount: Option<Dec>,
    ) -> Result<(PositionInfo, Dec, Dec, u128)> {
        let base_max = match base_max_amount {
            Some(v) => v,
            None => self.balance(&self.pool.base_token.clone())?,
        };
        let quote_max = match quote_max_amount {
            Some(v) => v,
            None => self.balance(&self.pool.quote_token.clone())?,
        };
        let (t0, t1) = self.convert_pair(base_max, quote_max);
        let legacy = self.compat.legacy_quirks;
        let (d0_, d1_, q) = (
            self.pool.token0.decimal,
            self.pool.token1.decimal,
            self.pool.is_token0_quote,
        );
        let lt = math::base_unit_price_to_tick(&lower_quote_price, d0_, d1_, q, legacy);
        let ut = math::base_unit_price_to_tick(&upper_quote_price, d0_, d1_, q, legacy);
        let (lt, ut) = if q { (ut, lt) } else { (lt, ut) };
        let lt = math::nearest_usable_tick(lt, self.pool.tick_spacing);
        let ut = math::nearest_usable_tick(ut, self.pool.tick_spacing);
        let (pos, u0, u1, liq) = self.add_liquidity_by_tick_raw(t0, t1, lt, ut, None)?;
        let (base_used, quote_used) = self.convert_pair(u0, u1);
        self.record_add(
            base_max,
            quote_max,
            lower_quote_price,
            upper_quote_price,
            base_used,
            quote_used,
            pos,
            liq,
        )?;
        Ok((pos, base_used, quote_used, liq))
    }

    /// python `add_liquidity_by_tick`. `sqrt_price_x96` / `tick` = None mean "use the current price"
    /// (python's `-1` sentinels).
    #[allow(clippy::too_many_arguments)]
    pub fn add_liquidity_by_tick(
        &mut self,
        lower_tick: i32,
        upper_tick: i32,
        base_max_amount: Option<Dec>,
        quote_max_amount: Option<Dec>,
        sqrt_price_x96: Option<U256>,
        tick: Option<i32>,
        trim_tick: bool,
    ) -> Result<(PositionInfo, Dec, Dec, u128)> {
        let (mut lower, mut upper) = (lower_tick, upper_tick);
        if trim_tick {
            lower = math::nearest_usable_tick(lower, self.pool.tick_spacing);
            upper = math::nearest_usable_tick(upper, self.pool.tick_spacing);
        }
        if lower > upper {
            std::mem::swap(&mut lower, &mut upper);
        }
        let sqrt = match (sqrt_price_x96, tick) {
            (Some(s), _) => Some(s),
            (None, Some(t)) => Some(math::get_sqrt_ratio_at_tick(t)?),
            (None, None) => None,
        };
        let base_max = match base_max_amount {
            Some(v) => v,
            None => self.balance(&self.pool.base_token.clone())?,
        };
        let quote_max = match quote_max_amount {
            Some(v) => v,
            None => self.balance(&self.pool.quote_token.clone())?,
        };
        let (t0, t1) = self.convert_pair(base_max, quote_max);
        let (pos, u0, u1, liq) = self.add_liquidity_by_tick_raw(t0, t1, lower, upper, sqrt)?;
        let (base_used, quote_used) = self.convert_pair(u0, u1);
        let (lp, up) = (self.tick_to_price(lower)?, self.tick_to_price(upper)?);
        self.record_add(base_max, quote_max, lp, up, base_used, quote_used, pos, liq)?;
        Ok((pos, base_used, quote_used, liq))
    }

    /// python `__remove_liquidity`: tokens go to the position's pending amounts.
    fn remove_liquidity_raw(
        &mut self,
        info: &PositionInfo,
        liquidity: Option<u128>,
        sqrt_price_x96: Option<U256>,
    ) -> Result<(Dec, Dec, u128)> {
        self.ensure_open()?;
        let sqrt = match sqrt_price_x96 {
            Some(s) => SqrtPrice::new(s),
            None => self.current_sqrt()?,
        };
        let i = self.position_index(info).ok_or_else(|| {
            DemeterError::Data(format!("KeyError: position {:?} not found", info))
        })?;
        let pos_liq = self.positions[i].1.liquidity;
        let delta = match liquidity {
            Some(l) if l < pos_liq => l,
            _ => pos_liq,
        };
        let (g0, g1) = self.token_amounts(&self.positions[i].1, &sqrt, delta);
        let pos = &mut self.positions[i].1;
        pos.liquidity = pos_liq - delta;
        pos.pending_amount0 += g0;
        pos.pending_amount1 += g1;
        self.has_update = true;
        Ok((g0, g1, delta))
    }

    /// python `remove_liquidity`. Returns (base, quote): collected amounts if `collect`, else
    /// the amounts moved to pending.
    pub fn remove_liquidity(
        &mut self,
        info: &PositionInfo,
        liquidity: Option<u128>,
        collect: bool,
        sqrt_price_x96: Option<U256>,
        remove_dry_pool: bool,
    ) -> Result<(Dec, Dec)> {
        let (g0, g1, delta) = self.remove_liquidity_raw(info, liquidity, sqrt_price_x96)?;
        let (base_get, quote_get) = self.convert_pair(g0, g1);
        let (b, q) = (self.pool.base_token.clone(), self.pool.quote_token.clone());
        let remain = self.get_position(info)?.liquidity;
        self.record(ActionKind::RemoveLiquidity {
            base_balance_after: self.balance_ud(&b)?,
            quote_balance_after: self.balance_ud(&q)?,
            position: *info,
            base_amount: Ud::new(base_get, &b.name),
            quote_amount: Ud::new(quote_get, &q.name),
            removed_liquidity: delta,
            remain_liquidity: remain,
        });
        if collect {
            self.collect_fee(info, None, None, remove_dry_pool, true)
        } else {
            Ok((base_get, quote_get))
        }
    }

    /// python `collect_fee`
    pub fn collect_fee(
        &mut self,
        info: &PositionInfo,
        max_collect_amount0: Option<Dec>,
        max_collect_amount1: Option<Dec>,
        remove_dry_pool: bool,
        collect_to_user: bool,
    ) -> Result<(Dec, Dec)> {
        let neg = |v: &Option<Dec>| v.map(|x| !x.is_zero() && x < d0()).unwrap_or(false);
        if neg(&max_collect_amount0) || neg(&max_collect_amount1) {
            return Err(DemeterError::demeter("collect amount should large than 0"));
        }
        // __collect_fee
        self.ensure_open()?;
        let i = self.position_index(info).ok_or_else(|| {
            DemeterError::Data(format!("KeyError: position {:?} not found", info))
        })?;
        let (p0, p1) = (
            self.positions[i].1.pending_amount0,
            self.positions[i].1.pending_amount1,
        );
        let f0 = match max_collect_amount0 {
            Some(m) if m < p0 => m,
            _ => p0,
        };
        let f1 = match max_collect_amount1 {
            Some(m) if m < p1 => m,
            _ => p1,
        };
        {
            let pos = &mut self.positions[i].1;
            pos.pending_amount0 -= f0;
            pos.pending_amount1 -= f1;
        }
        if collect_to_user {
            let w = self.wallet()?;
            w.borrow_mut().add(&self.pool.token0, f0);
            w.borrow_mut().add(&self.pool.token1, f1);
        }
        self.has_update = true;
        let (base_get, quote_get) = self.convert_pair(f0, f1);
        // QUIRK 8: python's `if self._positions[position]:` is always true -> always recorded
        let (b, q) = (self.pool.base_token.clone(), self.pool.quote_token.clone());
        self.record(ActionKind::CollectFee {
            base_balance_after: self.balance_ud(&b)?,
            quote_balance_after: self.balance_ud(&q)?,
            position: *info,
            base_amount: Ud::new(base_get, &b.name),
            quote_amount: Ud::new(quote_get, &q.name),
        });
        let pos = &self.positions[i].1;
        if pos.pending_amount0.is_zero()
            && pos.pending_amount1.is_zero()
            && pos.liquidity == 0
            && remove_dry_pool
        {
            self.positions.remove(i);
        }
        Ok((base_get, quote_get))
    }

    /// python `remove_all_liquidity`
    pub fn remove_all_liquidity(&mut self) -> Result<()> {
        let keys: Vec<PositionInfo> = self.positions.iter().map(|(k, _)| *k).collect();
        for k in keys {
            if self.position_index(&k).is_some() {
                self.remove_liquidity(&k, None, true, None, true)?;
            }
        }
        Ok(())
    }

    // ------------------------------------------------------------ swaps

    /// python `swap(from_amount, from_token, to_token, price, throw_action)` -> (fee_in_from, to_amount).
    /// Like python, `price` of 0 means "use the pool price" and swap does not check `is_open`.
    pub fn swap(
        &mut self,
        from_amount: Dec,
        from_token: &TokenInfo,
        to_token: &TokenInfo,
        price: Option<Dec>,
        throw_action: bool,
    ) -> Result<(Dec, Dec)> {
        if from_token == to_token {
            return Err(DemeterError::demeter("from and to token can not same"));
        }
        let (base, quote) = (self.pool.base_token.clone(), self.pool.quote_token.clone());
        let known = |t: &TokenInfo| *t == base || *t == quote;
        if !known(from_token) || !known(to_token) {
            return Err(DemeterError::demeter("from or to token not in pool"));
        }
        let price = match price {
            Some(p) if !p.is_zero() => p,
            _ => {
                if *from_token == base {
                    self.price()?
                } else {
                    dec::one() / self.price()?
                }
            }
        };
        let fee = from_amount * self.pool.fee_rate;
        let to_amount = (from_amount - fee) * price;
        let w = self.wallet()?;
        w.borrow_mut().sub(from_token, from_amount)?;
        w.borrow_mut().add(to_token, to_amount);
        if throw_action {
            self.record(ActionKind::Swap {
                amount: Ud::new(from_amount, &from_token.name),
                price: Ud::new(price, &format!("{}/{}", from_token.name, to_token.name)),
                fee: Ud::new(fee, &from_token.name),
                to_amount: Ud::new(to_amount, &to_token.name),
            });
        }
        Ok((fee, to_amount))
    }

    /// python `buy(base_token_amount, price)` -> (fee_in_quote, quote_spent, base_got)
    pub fn buy(&mut self, base_amount: Dec, price: Option<Dec>) -> Result<(Dec, Dec, Dec)> {
        if base_amount.is_zero() {
            return Ok((d0(), d0(), d0()));
        }
        let price = match price {
            Some(p) if !p.is_zero() => p,
            _ => self.price()?,
        };
        let quote_with_fee = base_amount * price / (dec::one() - self.pool.fee_rate);
        let (base, quote) = (self.pool.base_token.clone(), self.pool.quote_token.clone());
        let (fee, base_got) = self.swap(
            quote_with_fee,
            &quote,
            &base,
            Some(dec::one() / price),
            false,
        )?;
        self.record(ActionKind::Buy {
            base_balance_after: self.balance_ud(&base)?,
            quote_balance_after: self.balance_ud(&quote)?,
            amount: Ud::new(base_amount, &base.name),
            price: Ud::new(price, &self.price_unit),
            fee: Ud::new(fee, &quote.name),
            base_change: Ud::new(base_got, &base.name),
            quote_change: Ud::new(quote_with_fee, &quote.name),
        });
        Ok((fee, quote_with_fee, base_got))
    }

    /// python `sell(base_token_amount, price)` -> (fee_in_base, base_spent, quote_got)
    pub fn sell(&mut self, base_amount: Dec, price: Option<Dec>) -> Result<(Dec, Dec, Dec)> {
        if base_amount.is_zero() {
            return Ok((d0(), d0(), d0()));
        }
        let price = match price {
            Some(p) if !p.is_zero() => p,
            _ => self.price()?,
        };
        let (base, quote) = (self.pool.base_token.clone(), self.pool.quote_token.clone());
        let (fee, quote_got) = self.swap(base_amount, &base, &quote, Some(price), false)?;
        self.record(ActionKind::Sell {
            base_balance_after: self.balance_ud(&base)?,
            quote_balance_after: self.balance_ud(&quote)?,
            amount: Ud::new(base_amount, &base.name),
            price: Ud::new(price, &self.price_unit),
            fee: Ud::new(fee, &base.name),
            base_change: Ud::new(base_amount, &base.name),
            quote_change: Ud::new(quote_got, &quote.name),
        });
        Ok((fee, base_amount, quote_got))
    }

    /// python `even_rebalance`
    pub fn even_rebalance(&mut self, price: Option<Dec>) -> Result<()> {
        let price = match price {
            Some(p) => p,
            None => self.price()?,
        };
        let aq = self.balance(&self.pool.quote_token.clone())?;
        let ab = self.balance(&self.pool.base_token.clone())?;
        let two = dec::from_i64(2);
        let delta_base = (aq / price - ab) / (two + self.pool.fee_rate);
        if delta_base >= d0() {
            self.buy(delta_base, None)?;
            return Ok(());
        }
        let delta_quote = (ab - aq / price) / (two - self.pool.fee_rate);
        if delta_quote >= d0() {
            self.sell(delta_quote, None)?;
        }
        Ok(())
    }

    /// python `add_liquidity_by_value`
    pub fn add_liquidity_by_value(
        &mut self,
        lower_tick: i32,
        upper_tick: i32,
        value_to_use: Option<Dec>,
        trim_tick: bool,
    ) -> Result<(PositionInfo, Dec, Dec, u128)> {
        let (mut lower, mut upper) = (lower_tick, upper_tick);
        if trim_tick {
            lower = math::nearest_usable_tick(lower, self.pool.tick_spacing);
            upper = math::nearest_usable_tick(upper, self.pool.tick_spacing);
        }
        let price = self.price()?;
        let tick = self.price_to_tick(&price);
        let (price0, price1) = self.convert_pair(price, dec::one());
        let (base, quote) = (self.pool.base_token.clone(), self.pool.quote_token.clone());
        let (t0, t1) = (self.pool.token0.clone(), self.pool.token1.clone());
        let q0 = self.pool.is_token0_quote;
        let balance = self.balance(&quote)? + self.balance(&base)? * price;
        let value = value_to_use.unwrap_or(balance);
        if value > balance {
            return Err(DemeterError::demeter("Not enough balance to add liquidity"));
        }
        if lower >= upper {
            return Err(DemeterError::demeter(
                "Lower tick is larger than upper tick",
            ));
        }
        let min_error = dec::parse_lossy("1e-31").unwrap();
        if (q0 && tick > upper) || (!q0 && tick < lower) {
            // all base
            let base_amount = value / price;
            let diff = base_amount - self.balance(&base)?;
            let mut fee_in_quote = d0();
            if diff > min_error {
                fee_in_quote = self.swap(diff * price, &quote, &base, None, true)?.0;
            }
            return self.add_liquidity_by_tick(
                lower,
                upper,
                Some(base_amount - fee_in_quote / price),
                Some(d0()),
                None,
                None,
                true,
            );
        }
        if (q0 && tick < lower) || (!q0 && tick > upper) {
            // all quote
            let diff = value - self.balance(&quote)?;
            let mut fee_in_base = d0();
            if diff > d0() {
                fee_in_base = self.swap(diff / price, &base, &quote, None, true)?.0;
            }
            return self.add_liquidity_by_tick(
                lower,
                upper,
                Some(d0()),
                Some(value - fee_in_base * price),
                None,
                None,
                true,
            );
        }
        let ratio = math::estimate_ratio(tick, lower, upper)?;
        let ratio_in_amount =
            ratio * py_pow10_f64(self.pool.token1.decimal as i32 - self.pool.token0.decimal as i32);
        let ratio_amount = dec::from_f64_exact(ratio_in_amount);
        let ratio_in_value = if q0 {
            ratio_amount / price
        } else {
            ratio_amount * price
        };
        let token1_value = value / (ratio_in_value + dec::one());
        let token0_value = value - token1_value;
        let balance0_value = self.balance(&t0)? * price0;
        let balance1_value = self.balance(&t1)? * price1;
        if token0_value <= balance0_value && token1_value <= balance1_value {
            let (bv, qv) = self.convert_pair(token0_value, token1_value);
            self.add_liquidity_by_tick(lower, upper, Some(bv / price), Some(qv), None, None, true)
        } else if token0_value > balance0_value && token1_value > balance1_value {
            Err(DemeterError::demeter("Not enough balance to add liquidity"))
        } else if token0_value < balance0_value && token1_value > balance1_value {
            let (a0, a1, swap_value) = math::get_swap_value_with_part_balance_used(
                balance0_value,
                balance1_value,
                value,
                self.pool.fee_rate,
                ratio_in_value,
            )?;
            if q0 {
                self.swap(swap_value, &quote, &base, None, true)?;
            } else {
                self.swap(swap_value / price, &base, &quote, None, true)?;
            }
            let (bv, qv) = self.convert_pair(a0, a1);
            self.add_liquidity_by_tick(lower, upper, Some(bv / price), Some(qv), None, None, true)
        } else if token0_value > balance0_value && token1_value < balance1_value {
            let (a1, a0, swap_value) = math::get_swap_value_with_part_balance_used(
                balance1_value,
                balance0_value,
                value,
                self.pool.fee_rate,
                dec::one() / ratio_in_value,
            )?;
            if q0 {
                self.swap(swap_value / price, &base, &quote, None, true)?;
            } else {
                self.swap(swap_value, &quote, &base, None, true)?;
            }
            let (bv, qv) = self.convert_pair(a0, a1);
            self.add_liquidity_by_tick(lower, upper, Some(bv / price), Some(qv), None, None, true)
        } else {
            Err(DemeterError::demeter("NotImplementedError"))
        }
    }

    /// python `estimate_amount(value, lower_tick, upper_tick)` -> (token0_amount, token1_amount)
    pub fn estimate_amount(
        &self,
        value: Dec,
        lower_tick: i32,
        upper_tick: i32,
    ) -> Result<(Dec, Dec)> {
        let price = self.price()?;
        let current_tick = self.price_to_raw_tick(&price);
        let ratio = math::estimate_ratio(current_tick, lower_tick, upper_tick)?;
        let ratio_amount = dec::from_f64_exact(
            ratio * py_pow10_f64(self.pool.token1.decimal as i32 - self.pool.token0.decimal as i32),
        );
        let q0 = self.pool.is_token0_quote;
        let ratio_value = if q0 {
            ratio_amount / price
        } else {
            ratio_amount * price
        };
        let token1_value = value / (ratio_value + dec::one());
        let token0_value = value - token1_value;
        let a0 = if q0 {
            token0_value
        } else {
            token0_value / price
        };
        let a1 = if !q0 {
            token1_value
        } else {
            token1_value / price
        };
        Ok((a0, a1))
    }

    /// python `estimate_liquidity(value, position)` -> (liquidity, token0_amount, token1_amount)
    pub fn estimate_liquidity(&self, value: Dec, info: &PositionInfo) -> Result<(u128, Dec, Dec)> {
        let sqrt = self.current_sqrt_price()?;
        let price = self.price()?;
        let current_tick = math::sqrt_price_x96_to_tick(sqrt, self.compat.legacy_quirks);
        let lower = math::get_sqrt_ratio_at_tick(info.lower_tick)?;
        let upper = math::get_sqrt_ratio_at_tick(info.upper_tick)?;
        let to_u128 = |v: U256| {
            if v > U256::from(u128::MAX) {
                u128::MAX
            } else {
                v.to::<u128>()
            }
        };
        if current_tick <= info.lower_tick {
            let base_amount = value / price;
            let wei = math::to_wei(&base_amount, self.pool.base_token.decimal);
            let liq = to_u128(math::get_liquidity_for_amount0(lower, upper, wei));
            let (a0, a1) = self.convert_pair(base_amount, d0());
            Ok((liq, a0, a1))
        } else if current_tick >= info.upper_tick {
            let wei = math::to_wei(&value, self.pool.quote_token.decimal);
            let liq = to_u128(math::get_liquidity_for_amount1(lower, upper, wei));
            let (a0, a1) = self.convert_pair(d0(), value);
            Ok((liq, a0, a1))
        } else {
            let (a0, a1) = self.estimate_amount(value, info.lower_tick, info.upper_tick)?;
            let liq = math::get_liquidity_with_sqrt(
                sqrt,
                lower,
                upper,
                &a0,
                &a1,
                self.pool.token0.decimal,
                self.pool.token1.decimal,
            );
            Ok((to_u128(liq), a0, a1))
        }
    }
}
