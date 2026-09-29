//! `remix_dao_gamma.py` written as a native Rust strategy (no python involved).
//!
//! Same trading logic as the python file: the range around the price is cut into 17 bands whose
//! liquidity follows a shape (triangle, gaussian, ...); every `rescale` period the strategy checks
//! whether the price left the whole range and, if so, withdraws everything, swaps to the ratio the
//! new range needs and places the bands again around the current tick.
//!
//!     cargo run --release -p demeter-core --example gamma -- 2022-01-01 2022-03-31 [triangle] [0.05] [3600]
//!
//! It is used to measure how much faster a Rust strategy is than the same strategy in python on
//! the Rust engine (see rust/README.md, "Performance").

use chrono::NaiveDate;
use demeter_core::actuator::{Actuator, Ctx, PriceTable, Snapshot, Strategy};
use demeter_core::broker::shared;
use demeter_core::data;
use demeter_core::dec::{self, parse_lossy, Dec};
use demeter_core::math;
use demeter_core::trigger::{TriggerCond, Triggers};
use demeter_core::types::{naive_to_ts, MarketInfo, PositionInfo, TokenInfo, UniV3Pool};
use demeter_core::uniswap::UniLpMarket;
use demeter_core::Result;
use std::time::Instant;

const BAND_COUNT: i32 = 17;

fn shape_weights(shape: &str) -> Vec<Dec> {
    let w: &[&str] = match shape {
        "triangle" => &[
            "0", "0.0088", "0.0263", "0.0439", "0.0614", "0.0789", "0.0965", "0.1140", "0.1404",
            "0.1140", "0.0965", "0.0789", "0.0614", "0.0439", "0.0263", "0.0088", "0",
        ],
        "gaussian" => &[
            "0.0017", "0.0048", "0.0119", "0.0258", "0.0486", "0.0796", "0.1131", "0.1396",
            "0.1498", "0.1396", "0.1131", "0.0796", "0.0486", "0.0258", "0.0119", "0.0048",
            "0.0017",
        ],
        "exponential" => &[
            "0.0096", "0.0140", "0.0204", "0.0296", "0.0431", "0.0627", "0.0912", "0.1328",
            "0.1932", "0.1328", "0.0912", "0.0627", "0.0431", "0.0296", "0.0204", "0.0140",
            "0.0096",
        ],
        "uniform" => &["0.0588"; 17],
        "inverted_gaussian" => &[
            "0.096979",
            "0.094757",
            "0.089643",
            "0.079964",
            "0.064624",
            "0.044438",
            "0.023057",
            "0.0063597",
            "0",
            "0.0063642",
            "0.023073",
            "0.044470",
            "0.064670",
            "0.080020",
            "0.089707",
            "0.094825",
            "0.097048",
        ],
        other => panic!("unknown shape {other}"),
    };
    w.iter().map(|s| parse_lossy(s).unwrap()).collect()
}

/// python `build_tick_bands`
fn build_tick_bands(ratio: f64, tick_spacing: i32) -> Vec<(i32, i32)> {
    let half_span = (1.0 + ratio).ln() / 1.0001f64.ln();
    let step = 2 * tick_spacing;
    let width = (half_span * 2.0 / BAND_COUNT as f64 / step as f64).round_ties_even() as i32 * step;
    assert!(width > 0, "band narrower than the tick spacing");
    let half = width.div_euclid(2);
    let first = -(BAND_COUNT / 2);
    (first..first + BAND_COUNT)
        .map(|i| (width * i - half, width * (i + 1) - half))
        .collect()
}

/// python `build_shape_config`: [(lower offset, upper offset, share of balance)]
fn build_shape_config(shape: &str, ratio: f64, tick_spacing: i32) -> Vec<(i32, i32, Dec)> {
    let bands = build_tick_bands(ratio, tick_spacing);
    let weights = shape_weights(shape);
    let total = weights.iter().fold(dec::zero(), |a, b| a + *b);
    let shares: Vec<Dec> = weights.iter().map(|w| *w / total).collect();
    let straddles: Vec<bool> = bands.iter().map(|(l, u)| *l < 0 && 0 < *u).collect();
    let sum = |f: &dyn Fn(usize) -> bool| {
        (0..bands.len())
            .filter(|i| f(*i))
            .fold(dec::zero(), |a, i| a + shares[i])
    };
    let centre = sum(&|i| straddles[i]);
    let below = sum(&|i| bands[i].1 <= 0);
    let above = sum(&|i| bands[i].0 >= 0);
    let mut out = vec![];
    for (i, (lo, up)) in bands.iter().enumerate() {
        let share = shares[i];
        if share.is_zero() {
            continue;
        }
        let band_share = if straddles[i] {
            share
        } else {
            let side = if *up <= 0 { below } else { above };
            share / side * (dec::one() - centre)
        };
        out.push((*lo, *up, band_share));
    }
    out
}

/// python `RemixDaoUtils.round_tick`
fn round_tick(tick: i32, spacing: i32) -> i32 {
    let f = tick.div_euclid(spacing) * spacing;
    let c = f + spacing;
    if (tick - f) < (c - tick) {
        f
    } else {
        c
    }
}

struct Gamma {
    triggers: Triggers<Gamma>,
    market: String,
    base: TokenInfo,
    quote: TokenInfo,
    init_quote: Dec,
    shape: Vec<(i32, i32, Dec)>,
    tick_spacing: i32,
    rescale_secs: i64,
    start: i64,
    end: i64,
    positions: Vec<PositionInfo>,
    total_base_fee: Dec,
    total_quote_fee: Dec,
    total_base_swap_fee: Dec,
    total_quote_swap_fee: Dec,
    out_of_fund: bool,
    rescales: usize,
    final_net_value: Dec,
    total_fee: Dec,
}

impl Gamma {
    fn calculate_range(&self, current_tick: i32, lo_off: i32, up_off: i32) -> (i32, i32) {
        let s = self.tick_spacing;
        let center = round_tick(current_tick, s);
        let r = |off: i32| (off as f64 / s as f64).round_ties_even() as i32 * s;
        (center + r(lo_off), center + r(up_off))
    }

    /// python `BaseRemixDaoStrategy.calculate_swap_amount` (token0 is the quote token here)
    fn calculate_swap_amount(
        &self,
        m: &UniLpMarket,
        current_tick: i32,
        lower: i32,
        upper: i32,
        base: Dec,
        quote: Dec,
    ) -> Result<(Dec, Dec)> {
        let q0 = m.pool.is_token0_quote;
        let sqrt = math::get_sqrt_ratio_at_tick(current_tick)?;
        let (mut a, mut b) = (
            math::get_sqrt_ratio_at_tick(lower)?,
            math::get_sqrt_ratio_at_tick(upper)?,
        );
        if a > b {
            std::mem::swap(&mut a, &mut b);
        }
        let z = dec::zero();
        if sqrt <= a {
            return Ok(if q0 { (base, z) } else { (z, quote) });
        }
        if sqrt >= b {
            return Ok(if q0 { (z, quote) } else { (base, z) });
        }
        let (d0, d1) = (m.pool.token0.decimal as i32, m.pool.token1.decimal as i32);
        let ratio = dec::from_f64_exact(math::amounts_relation(current_tick, lower, upper, d0, d1));
        let s = dec::from_u256(sqrt) / dec::Q96;
        let p0 = s * s * dec::py_pow10(d0 - d1);
        if q0 {
            let delta_quote = (ratio * quote - base) / (ratio + p0);
            if delta_quote > z {
                Ok((z, delta_quote))
            } else {
                Ok(((base - ratio * quote) / (dec::one() + ratio / p0), z))
            }
        } else {
            let delta_base = (ratio * base - quote) / (ratio + p0);
            if delta_base > z {
                Ok((delta_base, z))
            } else {
                Ok((z, (quote - ratio * base) / (dec::one() + ratio / p0)))
            }
        }
    }

    /// python `BaseRemixDaoStrategy.execute_swap` -> (fee_base, fee_quote)
    fn execute_swap(
        m: &mut UniLpMarket,
        base_to_swap: Dec,
        quote_to_swap: Dec,
    ) -> Result<(Dec, Dec)> {
        let z = dec::zero();
        if base_to_swap > z {
            let (fee, _, _) = m.sell(base_to_swap, None)?;
            return Ok((fee, z));
        }
        if quote_to_swap > z {
            let price = m.price()?;
            let base_to_buy = quote_to_swap * (dec::one() - m.pool.fee_rate) / price;
            let (fee, _, _) = m.buy(base_to_buy, None)?;
            return Ok((z, fee));
        }
        Ok((z, z))
    }

    fn place_bands(
        &mut self,
        m: &mut UniLpMarket,
        current_tick: i32,
        base: Dec,
        quote: Dec,
    ) -> Result<(Dec, Dec)> {
        let (mut used_b, mut used_q) = (dec::zero(), dec::zero());
        for i in 0..self.shape.len() {
            let (lo, up, share) = self.shape[i];
            let (lt, ut) = self.calculate_range(current_tick, lo, up);
            let (p, b, q, _) = m.add_liquidity_by_tick(
                lt,
                ut,
                Some(base * share),
                Some(quote * share),
                None,
                Some(current_tick),
                true,
            )?;
            used_b += b;
            used_q += q;
            self.positions.push(p);
        }
        Ok((used_b, used_q))
    }

    fn balances(&self, m: &UniLpMarket) -> Result<(Dec, Dec)> {
        let w = m.wallet()?;
        let w = w.borrow();
        Ok((w.balance(&self.base)?, w.balance(&self.quote)?))
    }

    fn first_lp(&mut self, ctx: &Ctx, _s: &Snapshot) -> Result<()> {
        let mh = ctx.market(&self.market)?;
        let mut m = mh.borrow_mut();
        m.wallet()?.borrow_mut().add(&self.quote, self.init_quote);
        let price = m.price()?;
        let current_tick = m.price_to_raw_tick(&price);
        let (lo, hi) = (self.shape[0].0, self.shape.last().unwrap().1);
        let (lb, ub) = self.calculate_range(current_tick, lo, hi);
        let (b, q) = self.balances(&m)?;
        let (bs, qs) = self.calculate_swap_amount(&m, current_tick, lb, ub, b, q)?;
        let (fb, fq) = Self::execute_swap(&mut m, bs, qs)?;
        self.total_base_swap_fee += fb;
        self.total_quote_swap_fee += fq;
        let (b, q) = self.balances(&m)?;
        self.place_bands(&mut m, current_tick, b, q)?;
        Ok(())
    }

    fn rescale_work(&mut self, ctx: &Ctx, s: &Snapshot) -> Result<()> {
        let mh = ctx.market(&self.market)?;
        let mut m = mh.borrow_mut();
        if m.positions.is_empty() || self.out_of_fund {
            return Ok(());
        }
        let price = ctx.price(s, &self.base.name)?;
        let current_tick = m.price_to_raw_tick(&price);
        let (first, last) = (self.positions[0], *self.positions.last().unwrap());
        if first.lower_tick <= current_tick && current_tick < last.upper_tick {
            return Ok(());
        }
        self.rescales += 1;
        for p in std::mem::take(&mut self.positions) {
            let (bf, qf) = m.collect_fee(&p, None, None, true, true)?;
            m.remove_liquidity(&p, None, true, None, true)?;
            self.total_base_fee += bf;
            self.total_quote_fee += qf;
        }
        let (lo, hi) = (self.shape[0].0, self.shape.last().unwrap().1);
        let (lb, ub) = self.calculate_range(current_tick, lo, hi);
        let (b, q) = self.balances(&m)?;
        let (b, q) = (b - self.total_base_fee, q - self.total_quote_fee);
        let (bs, qs) = self.calculate_swap_amount(&m, current_tick, lb, ub, b, q)?;
        let (fb, fq) = Self::execute_swap(&mut m, bs, qs)?;
        self.total_base_swap_fee += fb;
        self.total_quote_swap_fee += fq;
        let (b, q) = self.balances(&m)?;
        let (b, q) = (b - self.total_base_fee, q - self.total_quote_fee);
        let (ub_, uq) = self.place_bands(&mut m, current_tick, b, q)?;
        if ub_.is_zero() && uq.is_zero() {
            self.out_of_fund = true;
        }
        Ok(())
    }

    fn calculate_final_result(&mut self, ctx: &Ctx, s: &Snapshot) -> Result<()> {
        let mh = ctx.market(&self.market)?;
        let mut m = mh.borrow_mut();
        let price = ctx.price(s, &self.base.name)?;
        for p in self.positions.clone() {
            let (bf, qf) = m.collect_fee(&p, None, None, true, true)?;
            self.total_base_fee += bf;
            self.total_quote_fee += qf;
        }
        let lp_value = m.get_market_balance()?.net_value;
        let (b, q) = self.balances(&m)?;
        self.final_net_value = lp_value + q + b * price;
        self.total_fee = self.total_quote_fee + self.total_base_fee * price;
        Ok(())
    }
}

impl Strategy for Gamma {
    fn initialize(&mut self, _ctx: &Ctx) -> Result<()> {
        self.triggers
            .push(TriggerCond::at_time(self.start), Gamma::first_lp);
        self.triggers.push(
            TriggerCond::period(self.rescale_secs, false, 0).unwrap(),
            Gamma::rescale_work,
        );
        self.triggers.push(
            TriggerCond::at_time(self.end),
            Gamma::calculate_final_result,
        );
        Ok(())
    }
    fn run_triggers(&mut self, ctx: &Ctx, s: &Snapshot) -> Result<()> {
        let mut t = std::mem::take(&mut self.triggers);
        let r = t.run(self, ctx, s);
        self.triggers = t;
        r
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let start = NaiveDate::parse_from_str(
        args.get(1).map(|s| s.as_str()).unwrap_or("2022-01-01"),
        "%Y-%m-%d",
    )
    .unwrap();
    let end = NaiveDate::parse_from_str(
        args.get(2).map(|s| s.as_str()).unwrap_or("2022-03-31"),
        "%Y-%m-%d",
    )
    .unwrap();
    let shape = args.get(3).cloned().unwrap_or_else(|| "triangle".into());
    let ratio: f64 = args.get(4).map(|s| s.parse().unwrap()).unwrap_or(0.05);
    let rescale_secs: i64 = args.get(5).map(|s| s.parse().unwrap()).unwrap_or(3600);

    let usdc = TokenInfo::new("usdc", 6);
    let eth = TokenInfo::new("eth", 18);
    let contract = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640";
    let pool = UniV3Pool::new(
        usdc.clone(),
        eth.clone(),
        parse_lossy("0.05").unwrap(),
        usdc.clone(),
        Some(10),
    );
    let t0 = Instant::now();
    let mut market = UniLpMarket::new(MarketInfo::new("lp"), pool);
    market.data_path = format!(
        "{}/../../samples/real-data/{contract}",
        env!("CARGO_MANIFEST_DIR")
    );
    market
        .load_data("ethereum", contract, start, end)
        .expect("load data");
    let load = t0.elapsed();

    let market = shared(market);
    let mut act = Actuator::new(false);
    act.add_market(market.clone()).unwrap();
    act.broker
        .borrow()
        .wallet
        .borrow_mut()
        .set(&usdc, dec::zero());
    act.broker
        .borrow()
        .wallet
        .borrow_mut()
        .set(&eth, dec::zero());
    let (ts, tokens, cols) = {
        let m = market.borrow();
        let d = m.data().unwrap();
        let (tokens, cols) = data::price_from_data(d, &m.pool);
        (d.ts.clone(), tokens, cols)
    };
    let bars = ts.len();
    act.set_price(PriceTable::new(ts, tokens, cols).unwrap(), usdc.clone())
        .unwrap();

    let mut strategy = Gamma {
        triggers: Triggers::default(),
        market: "lp".into(),
        base: eth,
        quote: usdc,
        init_quote: parse_lossy("100000").unwrap(),
        shape: build_shape_config(&shape, ratio, 10),
        tick_spacing: 10,
        rescale_secs,
        start: naive_to_ts(&start.and_hms_opt(0, 0, 0).unwrap()),
        end: naive_to_ts(&end.and_hms_opt(23, 59, 0).unwrap()),
        positions: vec![],
        total_base_fee: dec::zero(),
        total_quote_fee: dec::zero(),
        total_base_swap_fee: dec::zero(),
        total_quote_swap_fee: dec::zero(),
        out_of_fund: false,
        rescales: 0,
        final_net_value: dec::zero(),
        total_fee: dec::zero(),
    };
    let t1 = Instant::now();
    act.run(&mut strategy).expect("backtest");
    let run = t1.elapsed();
    println!(
        "engine=rust strategy=rust bars={bars} load={:.2}s run={:.2}s ({:.1} us/bar) rescales={} total_net_value={} total_fee={}",
        load.as_secs_f64(),
        run.as_secs_f64(),
        run.as_secs_f64() / bars as f64 * 1e6,
        strategy.rescales,
        dec::to_plain_string(&dec::round_sig(&strategy.final_net_value, 35)),
        dec::to_plain_string(&dec::round_sig(&strategy.total_fee, 35)),
    );
}
