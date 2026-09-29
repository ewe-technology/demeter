//! Basic value types: tokens, markets, pool definition and positions.

use crate::dec::{self, Dec};
use chrono::{DateTime, NaiveDateTime};
use std::hash::{Hash, Hasher};

/// Timestamps are naive (like pandas without tz) and stored as seconds since the epoch.
pub type Ts = i64;

pub fn ts_to_naive(ts: Ts) -> NaiveDateTime {
    DateTime::from_timestamp(ts, 0)
        .expect("timestamp in range")
        .naive_utc()
}

pub fn naive_to_ts(dt: &NaiveDateTime) -> Ts {
    dt.and_utc().timestamp()
}

pub fn ts_to_string(ts: Ts) -> String {
    ts_to_naive(ts).format("%Y-%m-%d %H:%M:%S").to_string()
}

/// Token identity. Like python, equality and hashing use the (upper-cased) name only.
#[derive(Clone, Debug)]
pub struct TokenInfo {
    pub name: String,
    pub decimal: u32,
    pub address: String,
}

impl TokenInfo {
    pub fn new(name: &str, decimal: u32) -> Self {
        TokenInfo {
            name: name.to_uppercase(),
            decimal,
            address: String::new(),
        }
    }
    pub fn with_address(name: &str, decimal: u32, address: &str) -> Self {
        TokenInfo {
            name: name.to_uppercase(),
            decimal,
            address: address.to_lowercase(),
        }
    }
    pub fn usd() -> Self {
        TokenInfo::new("USD", 0)
    }
}

impl PartialEq for TokenInfo {
    fn eq(&self, other: &Self) -> bool {
        self.name == other.name
    }
}
impl Eq for TokenInfo {}
impl Hash for TokenInfo {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.name.hash(state)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum MarketType {
    Broker = 0,
    UniswapV3 = 1,
}

impl MarketType {
    pub fn name(&self) -> &'static str {
        match self {
            MarketType::Broker => "broker",
            MarketType::UniswapV3 => "uniswap_v3",
        }
    }
}

/// Key of a market (python `MarketInfo(name, type)` NamedTuple).
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct MarketInfo {
    pub name: String,
    pub kind: MarketType,
}

impl MarketInfo {
    pub fn new(name: &str) -> Self {
        MarketInfo {
            name: name.to_string(),
            kind: MarketType::UniswapV3,
        }
    }
}

/// Uniswap v3 pool definition (python `UniV3Pool`).
#[derive(Clone, Debug)]
pub struct UniV3Pool {
    pub token0: TokenInfo,
    pub token1: TokenInfo,
    pub quote_token: TokenInfo,
    pub base_token: TokenInfo,
    pub is_token0_quote: bool,
    pub tick_spacing: i32,
    /// fee in hundredths of a bip (python `fee * 10000`, e.g. 500 for 0.05%)
    pub fee: Dec,
    /// fee as a fraction, e.g. 0.0005
    pub fee_rate: Dec,
}

impl UniV3Pool {
    /// `fee_percent` is the pool fee in percent, e.g. 0.05 for the 0.05% pool.
    pub fn new(
        token0: TokenInfo,
        token1: TokenInfo,
        fee_percent: Dec,
        quote_token: TokenInfo,
        tick_spacing: Option<i32>,
    ) -> Self {
        let is_token0_quote = quote_token == token0;
        let base_token = if is_token0_quote {
            token1.clone()
        } else {
            token0.clone()
        };
        // python: int(fee * 200)
        let tick_spacing = tick_spacing
            .unwrap_or_else(|| dec::trunc_to_i128(&(fee_percent * dec::from_i64(200))) as i32);
        UniV3Pool {
            token0,
            token1,
            quote_token,
            base_token,
            is_token0_quote,
            tick_spacing,
            fee: fee_percent * dec::from_i64(10000),
            fee_rate: fee_percent / dec::from_i64(100),
        }
    }
}

/// Key of a position: its tick range. Python `PositionInfo(lower_tick, upper_tick)`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct PositionInfo {
    pub lower_tick: i32,
    pub upper_tick: i32,
}

/// Mutable state of a position. Python `Position` dataclass plus cached tick sqrt prices.
#[derive(Clone, Debug)]
pub struct Position {
    pub pending_amount0: Dec,
    pub pending_amount1: Dec,
    pub liquidity: u128,
    pub lower_price: Dec,
    pub upper_price: Dec,
    pub init_price: Dec,
    pub transferred: bool,
    pub sqrt_lower: crate::math::SqrtPrice,
    pub sqrt_upper: crate::math::SqrtPrice,
    /// token amounts while the price is outside the range (they do not depend on the price then)
    pub out_of_range_cache: std::cell::Cell<Option<OutOfRangeAmounts>>,
}

/// Cached (amount0, amount1) of an out-of-range position for a given liquidity and side.
#[derive(Clone, Copy, Debug)]
pub struct OutOfRangeAmounts {
    pub liquidity: u128,
    /// -1: price below the range (all token0), 1: price above the range (all token1)
    pub side: i8,
    pub amounts: (Dec, Dec),
}

/// Market balance of the uniswap market (python `UniLpBalance`).
#[derive(Clone, Debug)]
pub struct UniLpBalance {
    pub net_value: Dec,
    pub liquidity_value: Dec,
    pub base_uncollected: Dec,
    pub quote_uncollected: Dec,
    pub base_in_position: Dec,
    pub quote_in_position: Dec,
    pub position_count: usize,
}

/// python `PositionStatus`.
#[derive(Clone, Debug)]
pub struct PositionStatus {
    pub liquidity: u128,
    pub liquidity_amount0: Dec,
    pub liquidity_amount1: Dec,
    pub liquidity_value: Dec,
    pub pending_amount0: Dec,
    pub pending_amount1: Dec,
    pub pending_value: Dec,
    pub amount0: Dec,
    pub amount1: Dec,
    pub value: Dec,
    pub h: Dec,
    pub l: Dec,
    pub p: Dec,
}

/// Switches between "behave exactly like the python engine" and "corrected behaviour".
/// See README, section "Python engine quirks".
#[derive(Clone, Copy, Debug)]
pub struct EngineCompat {
    /// true (default): reproduce python quirks 1-3, 7. false: corrected behaviour.
    pub legacy_quirks: bool,
}

impl Default for EngineCompat {
    fn default() -> Self {
        EngineCompat {
            legacy_quirks: true,
        }
    }
}
