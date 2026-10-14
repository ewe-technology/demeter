//! Uniswap v3 math, ported from `demeter/uniswap/liquitidy_math.py` and `demeter/uniswap/helper.py`.
//!
//! Integer paths (TickMath, liquidity) are exact, like python's unbounded ints: products that do not
//! fit 256 bits are done in 512 bits. Decimal paths use [`Dec`] (38 digits vs python's 35).

use crate::dec::{self, Dec};
use crate::error::{DemeterError, Result};
use ruint::aliases::{U256, U512};

pub const MIN_TICK: i32 = -887272;
pub const MAX_TICK: i32 = 887272;

/// `sqrt(1.0001)` exactly as python computes `math.sqrt(Decimal(1.0001))` (float math).
fn sqrt_1p0001() -> f64 {
    1.0001f64.sqrt()
}

fn u256_hex(s: &str) -> U256 {
    U256::from_str_radix(s, 16).expect("hex constant")
}

/// Port of `get_sqrt_ratio_at_tick` (Solidity TickMath.getSqrtRatioAtTick). Result fits 160 bits.
pub fn get_sqrt_ratio_at_tick(tick: i32) -> Result<U256> {
    let abs_tick = tick.unsigned_abs();
    if abs_tick > MAX_TICK as u32 {
        return Err(DemeterError::assertion(format!("tick {tick} out of range")));
    }
    // cached constants
    thread_local! {
        static C: [U256; 20] = [
            u256_hex("fffcb933bd6fad37aa2d162d1a594001"),
            u256_hex("fff97272373d413259a46990580e213a"),
            u256_hex("fff2e50f5f656932ef12357cf3c7fdcc"),
            u256_hex("ffe5caca7e10e4e61c3624eaa0941cd0"),
            u256_hex("ffcb9843d60f6159c9db58835c926644"),
            u256_hex("ff973b41fa98c081472e6896dfb254c0"),
            u256_hex("ff2ea16466c96a3843ec78b326b52861"),
            u256_hex("fe5dee046a99a2a811c461f1969c3053"),
            u256_hex("fcbe86c7900a88aedcffc83b479aa3a4"),
            u256_hex("f987a7253ac413176f2b074cf7815e54"),
            u256_hex("f3392b0822b70005940c7a398e4b70f3"),
            u256_hex("e7159475a2c29b7443b29c7fa6e889d9"),
            u256_hex("d097f3bdfd2022b8845ad8f792aa5825"),
            u256_hex("a9f746462d870fdf8a65dc1f90e061e5"),
            u256_hex("70d869a156d2a1b890bb3df62baf32f7"),
            u256_hex("31be135f97d08fd981231505542fcfa6"),
            u256_hex("9aa508b5b7a84e1c677de54f3e99bc9"),
            u256_hex("5d6af8dedb81196699c329225ee604"),
            u256_hex("2216e584f5fa1ea926041bedfe98"),
            u256_hex("48a170391f7dc42444e8fa2"),
        ];
    }
    let mut ratio = C.with(|c| {
        let mut ratio = if abs_tick & 0x1 != 0 {
            c[0]
        } else {
            U256::from(1u8) << 128
        };
        for (i, k) in c.iter().enumerate().skip(1) {
            if abs_tick & (1u32 << i) != 0 {
                ratio = (ratio * *k) >> 128;
            }
        }
        ratio
    });
    if tick > 0 {
        ratio = U256::MAX / ratio;
    }
    let rem = ratio & U256::from(u32::MAX);
    Ok((ratio >> 32)
        + if rem.is_zero() {
            U256::ZERO
        } else {
            U256::from(1u8)
        })
}

fn sorted(a: U256, b: U256) -> (U256, U256) {
    if a > b {
        (b, a)
    } else {
        (a, b)
    }
}

use dec::int_pow10;

/// `get_amount0`: `(Decimal(L * 2**96 * (sqrtB - sqrtA)) / sqrtB / sqrtA) / 10**decimals`, step by
/// step like python (the big integers stay exact; each division rounds to 35 digits).
pub fn get_amount0(sqrt_a: U256, sqrt_b: U256, liquidity: u128, decimals: u32) -> Dec {
    let (a, b) = sorted(sqrt_a, sqrt_b);
    let prod: U512 = U512::from(liquidity) * (U512::from(1u8) << 96) * U512::from(b - a);
    let q = dec::py_div_int(prod, U512::from(b), 0, false);
    let (_, m, e) = dec::to_parts(&q);
    dec::py_div_int(U512::from(m), U512::from(a), e, false) / int_pow10(decimals)
}

/// `get_amount1`: `Decimal(L * (sqrtB - sqrtA)) / 2**96 / 10**decimals`, step by step like python.
pub fn get_amount1(sqrt_a: U256, sqrt_b: U256, liquidity: u128, decimals: u32) -> Dec {
    let (a, b) = sorted(sqrt_a, sqrt_b);
    let prod: U512 = U512::from(liquidity) * U512::from(b - a);
    dec::py_div_int(prod, U512::from(1u8) << 96, 0, false) / int_pow10(decimals)
}

/// [`get_amount0`] when python's `liquidity` is a Decimal (see `Position::liquidity_is_decimal`):
/// `liquidity * 2**96` and `* (sqrtB - sqrtA)` each round to 35 digits.
pub fn get_amount0_dec_liquidity(sqrt_a: U256, sqrt_b: U256, liquidity: u128, decimals: u32) -> Dec {
    let (a, b) = sorted(sqrt_a, sqrt_b);
    let t = dec::py_mul_int(dec::from_u128(liquidity), U512::from(1u8) << 96);
    let t = dec::py_mul_int(t, U512::from(b - a));
    let (_, m, e) = dec::to_parts(&t);
    let q = dec::py_div_int(U512::from(m), U512::from(b), e, false);
    let (_, m, e) = dec::to_parts(&q);
    dec::py_div_int(U512::from(m), U512::from(a), e, false) / int_pow10(decimals)
}

/// [`get_amount1`] when python's `liquidity` is a Decimal: `liquidity * (sqrtB - sqrtA)` rounds.
pub fn get_amount1_dec_liquidity(sqrt_a: U256, sqrt_b: U256, liquidity: u128, decimals: u32) -> Dec {
    let (a, b) = sorted(sqrt_a, sqrt_b);
    let t = dec::py_mul_int(dec::from_u128(liquidity), U512::from(b - a));
    let (_, m, e) = dec::to_parts(&t);
    dec::py_div_int(U512::from(m), U512::from(1u8) << 96, e, false) / int_pow10(decimals)
}

/// python `get_amounts` for a position whose liquidity is an int (`false`) or a Decimal (`true`).
pub fn get_amounts_typed(
    sqrt: &SqrtPrice,
    a: &SqrtPrice,
    b: &SqrtPrice,
    liquidity: u128,
    liquidity_is_decimal: bool,
    decimal0: u32,
    decimal1: u32,
) -> (Dec, Dec) {
    if !liquidity_is_decimal {
        return get_amounts_fast(sqrt, a, b, liquidity, decimal0, decimal1);
    }
    let (a, b) = if a.x96 > b.x96 { (b, a) } else { (a, b) };
    if sqrt.x96 <= a.x96 {
        (get_amount0_dec_liquidity(a.x96, b.x96, liquidity, decimal0), dec::zero())
    } else if sqrt.x96 < b.x96 {
        (
            get_amount0_dec_liquidity(sqrt.x96, b.x96, liquidity, decimal0),
            get_amount1_dec_liquidity(a.x96, sqrt.x96, liquidity, decimal1),
        )
    } else {
        (dec::zero(), get_amount1_dec_liquidity(a.x96, b.x96, liquidity, decimal1))
    }
}

/// A sqrt price x96 (positions and the market cache it per iteration).
#[derive(Clone, Copy, Debug)]
pub struct SqrtPrice {
    pub x96: U256,
}

impl SqrtPrice {
    pub fn new(x96: U256) -> Self {
        SqrtPrice { x96 }
    }
}

/// `get_amount0` on cached sqrt prices. It used to take 38-digit decimal shortcuts, which differed
/// from python in the last digit; it is the exact version now (python's rounding, see [`get_amount0`]).
#[inline]
pub fn get_amount0_fast(a: &SqrtPrice, b: &SqrtPrice, liquidity: u128, decimals: u32) -> Dec {
    get_amount0(a.x96, b.x96, liquidity, decimals)
}

/// `get_amount1` on cached sqrt prices, see [`get_amount0_fast`].
#[inline]
pub fn get_amount1_fast(a: &SqrtPrice, b: &SqrtPrice, liquidity: u128, decimals: u32) -> Dec {
    get_amount1(a.x96, b.x96, liquidity, decimals)
}

/// Fast `get_amounts` used by the market on every iteration.
pub fn get_amounts_fast(
    sqrt: &SqrtPrice,
    a: &SqrtPrice,
    b: &SqrtPrice,
    liquidity: u128,
    decimal0: u32,
    decimal1: u32,
) -> (Dec, Dec) {
    let (a, b) = if a.x96 > b.x96 { (b, a) } else { (a, b) };
    if sqrt.x96 <= a.x96 {
        (get_amount0_fast(a, b, liquidity, decimal0), dec::zero())
    } else if sqrt.x96 < b.x96 {
        (
            get_amount0_fast(sqrt, b, liquidity, decimal0),
            get_amount1_fast(a, sqrt, liquidity, decimal1),
        )
    } else {
        (dec::zero(), get_amount1_fast(a, b, liquidity, decimal1))
    }
}

/// `get_amounts` with the tick sqrt prices already computed (positions cache them).
pub fn get_amounts_with_sqrt(
    sqrt_price_x96: U256,
    sqrt_a: U256,
    sqrt_b: U256,
    liquidity: u128,
    decimal0: u32,
    decimal1: u32,
) -> (Dec, Dec) {
    let (sqrt_a, sqrt_b) = sorted(sqrt_a, sqrt_b);
    let sqrt = sqrt_price_x96;
    if sqrt <= sqrt_a {
        (
            get_amount0(sqrt_a, sqrt_b, liquidity, decimal0),
            dec::zero(),
        )
    } else if sqrt < sqrt_b {
        (
            get_amount0(sqrt, sqrt_b, liquidity, decimal0),
            get_amount1(sqrt_a, sqrt, liquidity, decimal1),
        )
    } else {
        (
            dec::zero(),
            get_amount1(sqrt_a, sqrt_b, liquidity, decimal1),
        )
    }
}

pub fn get_amounts(
    sqrt_price_x96: U256,
    tick_a: i32,
    tick_b: i32,
    liquidity: u128,
    decimal0: u32,
    decimal1: u32,
) -> Result<(Dec, Dec)> {
    let sa = get_sqrt_ratio_at_tick(tick_a)?;
    let sb = get_sqrt_ratio_at_tick(tick_b)?;
    Ok(get_amounts_with_sqrt(
        sqrt_price_x96,
        sa,
        sb,
        liquidity,
        decimal0,
        decimal1,
    ))
}

/// `a * b // d` with a 512 bit intermediate.
pub fn mul_div(a: U512, b: U512, d: U512) -> U512 {
    (a * b) / d
}

fn u512(v: U256) -> U512 {
    U512::from(v)
}

fn clamp_u256(v: U512) -> U256 {
    if v > u512(U256::MAX) {
        U256::MAX
    } else {
        U256::from(v)
    }
}

pub fn get_liquidity_for_amount0(sqrt_a: U256, sqrt_b: U256, amount: U256) -> U256 {
    let (a, b) = sorted(sqrt_a, sqrt_b);
    if a == b {
        return U256::ZERO;
    }
    let intermediate = mul_div(u512(a), u512(b), U512::from(1u8) << 96);
    clamp_u256(mul_div(u512(amount), intermediate, u512(b - a)))
}

pub fn get_liquidity_for_amount1(sqrt_a: U256, sqrt_b: U256, amount: U256) -> U256 {
    let (a, b) = sorted(sqrt_a, sqrt_b);
    if a == b {
        return U256::ZERO;
    }
    clamp_u256(mul_div(u512(amount), U512::from(1u8) << 96, u512(b - a)))
}

/// `to_wei`: `int(amount * 10**decimals)`; negative amounts give 0.
pub fn to_wei(amount: &Dec, decimals: u32) -> U256 {
    let v = *amount * dec::int_pow10(decimals);
    dec::trunc_to_u256(&v).unwrap_or(U256::ZERO)
}

pub fn get_liquidity_with_sqrt(
    sqrt_price_x96: U256,
    sqrt_a: U256,
    sqrt_b: U256,
    amount0: &Dec,
    amount1: &Dec,
    decimal0: u32,
    decimal1: u32,
) -> U256 {
    let (sqrt_a, sqrt_b) = sorted(sqrt_a, sqrt_b);
    let sqrt = sqrt_price_x96;
    let a0 = to_wei(amount0, decimal0);
    let a1 = to_wei(amount1, decimal1);
    if sqrt <= sqrt_a {
        get_liquidity_for_amount0(sqrt_a, sqrt_b, a0)
    } else if sqrt < sqrt_b {
        let l0 = get_liquidity_for_amount0(sqrt, sqrt_b, a0);
        let l1 = get_liquidity_for_amount1(sqrt_a, sqrt, a1);
        if l0 < l1 {
            l0
        } else {
            l1
        }
    } else {
        get_liquidity_for_amount1(sqrt_a, sqrt_b, a1)
    }
}

pub fn get_liquidity(
    sqrt_price_x96: U256,
    tick_a: i32,
    tick_b: i32,
    amount0: &Dec,
    amount1: &Dec,
    decimal0: u32,
    decimal1: u32,
) -> Result<U256> {
    let sa = get_sqrt_ratio_at_tick(tick_a)?;
    let sb = get_sqrt_ratio_at_tick(tick_b)?;
    Ok(get_liquidity_with_sqrt(
        sqrt_price_x96,
        sa,
        sb,
        amount0,
        amount1,
        decimal0,
        decimal1,
    ))
}

/// `estimate_ratio` (pure float math, like python).
pub fn estimate_ratio(tick: i32, lower_tick: i32, upper_tick: i32) -> Result<f64> {
    if !(lower_tick < tick && tick < upper_tick) {
        return Err(DemeterError::demeter("tick should in tick range"));
    }
    let t = sqrt_1p0001();
    let (u, c, l) = (upper_tick as f64, tick as f64, lower_tick as f64);
    Ok((t.powf(u) - t.powf(c)) / (t.powf(c) * t.powf(u) * (t.powf(c) - t.powf(l))))
}

/// `amounts_relation` (float math).
pub fn amounts_relation(
    tick: i32,
    tick_a: i32,
    tick_b: i32,
    decimals0: i32,
    decimals1: i32,
) -> f64 {
    let scale = py_pow10_f64(decimals1 - decimals0);
    let sqrt = (1.0001f64.powf(tick as f64) / scale).powf(0.5);
    let sqrt_a = (1.0001f64.powf(tick_a as f64) / scale).powf(0.5);
    let sqrt_b = (1.0001f64.powf(tick_b as f64) / scale).powf(0.5);
    (sqrt - sqrt_a) / ((1.0 / sqrt) - (1.0 / sqrt_b))
}

// ------------------------------------------------------------------ price <-> tick (helper.py)

/// helper.py `_from_x96`: `Decimal(number) / Q96` (the integer stays exact, the quotient rounds).
pub fn from_x96(number: U256) -> Dec {
    dec::py_div_int(U512::from(number), U512::from(1u8) << 96, 0, false)
}

/// python `10 ** k`: an int for k >= 0, else a float (C pow). `Decimal()` of that float has 50+
/// digits, more than a `Dec` holds, so the float itself is kept (see `dec::py_f64_mul`).
enum PyPow10 {
    Int(Dec),
    Float(f64),
}

fn py_pow10_k(k: i32) -> PyPow10 {
    if k >= 0 {
        PyPow10::Int(dec::from_u128(10u128.pow(k as u32)))
    } else {
        PyPow10::Float(10f64.powf(k as f64)) // python's `10 ** k` is C pow(), as in dec::py_pow10
    }
}

pub fn to_x96(sqrt_price: &Dec) -> U256 {
    dec::trunc_to_u256(&(*sqrt_price * dec::q96())).unwrap_or(U256::ZERO)
}

pub fn sqrt_price_x96_to_base_unit_price(
    sqrt_price_x96: U256,
    d0: u32,
    d1: u32,
    is_token0_quote: bool,
) -> Dec {
    // helper.py, step by step with python's decimal arithmetic, so prices equal python's to the
    // last digit (a single 38-digit computation differed in the last digit on about half of all ticks):
    //   pool_price = _from_x96(x96) ** 2 * Decimal(10 ** (d0 - d1));  1 / pool_price if token0 is the quote
    if sqrt_price_x96.is_zero() {
        return dec::zero();
    }
    let p = dec::py_square(from_x96(sqrt_price_x96));
    let p = match py_pow10_k(d0 as i32 - d1 as i32) {
        PyPow10::Int(f) => p * f,
        PyPow10::Float(f) => dec::py_f64_mul(f, p),
    };
    if is_token0_quote {
        dec::one() / p
    } else {
        p
    }
}

pub fn base_unit_price_to_sqrt_price_x96(
    price: &Dec,
    d0: u32,
    d1: u32,
    is_token0_quote: bool,
) -> U256 {
    // helper.py, step by step with python's decimal arithmetic (a 38-digit computation could land
    // one unit below a tick's sqrt ratio, leaving ~1e-29 of a token where python has none):
    //   price = 1 / price if token0 is the quote;  atomic = price / Decimal(10 ** (d0 - d1))
    //   int(atomic.sqrt() * Q96)
    if price.is_sign_negative() || price.is_zero() || !price.is_finite() {
        return U256::ZERO;
    }
    to_x96(&atomic_price(price, d0, d1, is_token0_quote).sqrt())
}

/// helper.py `price = 1 / price if is_token0_quote else price; price / Decimal(10 ** (d0 - d1))`.
fn atomic_price(price: &Dec, d0: u32, d1: u32, is_token0_quote: bool) -> Dec {
    let price = if is_token0_quote {
        dec::one() / *price
    } else {
        *price
    };
    match py_pow10_k(d0 as i32 - d1 as i32) {
        PyPow10::Int(f) => price / f,
        PyPow10::Float(f) => dec::py_div_f64(price, f),
    }
}

/// Convert a sqrt price (not x96) to a tick.
///
/// `legacy == true` reproduces python: `int(math.log(float(sqrt_price), sqrt(1.0001)))`, which
/// truncates toward zero (wrong by one for most negative ticks). `legacy == false` returns the
/// exact Uniswap `getTickAtSqrtRatio` result (floor).
pub fn sqrt_price_to_tick(sqrt_price: &Dec, legacy: bool) -> i32 {
    let f = sqrt_price.to_f64();
    let approx = f.ln() / sqrt_1p0001().ln();
    if legacy {
        return approx as i32; // `as` truncates toward zero, like python int()
    }
    let x96 = to_x96(sqrt_price);
    exact_tick_at_sqrt_ratio(x96, approx.floor() as i32)
}

/// Largest tick t with sqrt_ratio(t) <= x96, starting from a float guess.
pub fn exact_tick_at_sqrt_ratio(x96: U256, guess: i32) -> i32 {
    let mut t = guess.clamp(MIN_TICK, MAX_TICK);
    while t > MIN_TICK && get_sqrt_ratio_at_tick(t).map(|s| s > x96).unwrap_or(false) {
        t -= 1;
    }
    while t < MAX_TICK
        && get_sqrt_ratio_at_tick(t + 1)
            .map(|s| s <= x96)
            .unwrap_or(false)
    {
        t += 1;
    }
    t
}

pub fn sqrt_price_x96_to_tick(sqrt_price_x96: U256, legacy: bool) -> i32 {
    if legacy {
        sqrt_price_to_tick(&from_x96(sqrt_price_x96), true)
    } else {
        let guess = (from_x96(sqrt_price_x96).to_f64().ln() / sqrt_1p0001().ln()).floor() as i32;
        exact_tick_at_sqrt_ratio(sqrt_price_x96, guess)
    }
}

pub fn tick_to_base_unit_price(tick: i32, d0: u32, d1: u32, is_token0_quote: bool) -> Result<Dec> {
    Ok(sqrt_price_x96_to_base_unit_price(
        get_sqrt_ratio_at_tick(tick)?,
        d0,
        d1,
        is_token0_quote,
    ))
}

pub fn base_unit_price_to_tick(
    price: &Dec,
    d0: u32,
    d1: u32,
    is_token0_quote: bool,
    legacy: bool,
) -> i32 {
    sqrt_price_to_tick(&atomic_price(price, d0, d1, is_token0_quote).sqrt(), legacy)
}

/// `from_atomic_unit`: `Decimal(int(amount)) / Decimal(10**decimal)`.
pub fn from_atomic_unit(amount: i128, decimal: u32) -> Dec {
    dec::from_i128(amount) / dec::int_pow10(decimal)
}

/// `nearest_usable_tick`: python `round()` is half-to-even on the float quotient.
pub fn nearest_usable_tick(tick: i32, tick_spacing: i32) -> i32 {
    let rounded =
        ((tick as f64) / (tick_spacing as f64)).round_ties_even() as i64 * tick_spacing as i64;
    let rounded = if rounded < MIN_TICK as i64 {
        rounded + tick_spacing as i64
    } else if rounded > MAX_TICK as i64 {
        rounded - tick_spacing as i64
    } else {
        rounded
    };
    rounded as i32
}

/// `get_swap_value_with_part_balance_used`, returns (from_value_after, to_value_after, swap_value).
pub fn get_swap_value_with_part_balance_used(
    swap_from_token_val: Dec,
    swap_to_token_val: Dec,
    total_val_after: Dec,
    fee_rate: Dec,
    final_ratio: Dec,
) -> Result<(Dec, Dec, Dec)> {
    if total_val_after > swap_from_token_val + swap_to_token_val {
        return Err(DemeterError::demeter("Target value exceed your balance"));
    }
    let swap_value = (total_val_after - final_ratio * swap_to_token_val - swap_to_token_val)
        / (final_ratio - final_ratio * fee_rate + dec::one());
    let total_no_fee = total_val_after - swap_value * fee_rate;
    let to_after = total_no_fee / (final_ratio + dec::one());
    Ok((total_no_fee - to_after, to_after, swap_value))
}

/// python `10 ** n` used in float arithmetic: an exact int for n >= 0, libm `pow` for n < 0.
pub fn py_pow10_f64(n: i32) -> f64 {
    10f64.powf(n as f64)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tick_math_known() {
        assert_eq!(get_sqrt_ratio_at_tick(0).unwrap(), U256::from(1u8) << 96);
        assert_eq!(
            get_sqrt_ratio_at_tick(MIN_TICK).unwrap(),
            U256::from(4295128739u64)
        );
        assert_eq!(
            get_sqrt_ratio_at_tick(MAX_TICK).unwrap().to_string(),
            "1461446703485210103287273052203988822378723970342"
        );
    }

    #[test]
    fn nearest() {
        assert_eq!(nearest_usable_tick(5, 10), 0); // 0.5 -> 0 (half even)
        assert_eq!(nearest_usable_tick(15, 10), 20); // 1.5 -> 2
        assert_eq!(nearest_usable_tick(25, 10), 20); // 2.5 -> 2
        assert_eq!(nearest_usable_tick(-5, 10), 0);
        assert_eq!(nearest_usable_tick(887272, 60), 887220);
    }

    #[test]
    fn tick_price_equals_python_last_digit() {
        // python helper.tick_to_base_unit_price; a single 38-digit rounding got each one wrong in the last digit
        for (tick, d0, d1, q0, py) in [
            (40001, 8, 6, false, "5459.2690946025272552386090324769891"),
            (180015, 6, 18, true, "15220.844726019017158707246858685917"),
            (250000, 8, 18, false, "7.1914955436073249008050581274134523"),
            (-215000, 18, 6, false, "460.40016915998201286688086055409133"),
        ] {
            let p = tick_to_base_unit_price(tick, d0, d1, q0).unwrap();
            assert_eq!(dec::to_plain_string(&p), py, "tick {tick}");
        }
    }

    #[test]
    fn boundary_price_sqrt_equals_python() {
        // python base_unit_price_to_sqrt_price_x96 of a tick's own price gives that tick's sqrt ratio here;
        // 38-digit maths landed one unit lower at 201300, so a position ending there kept ~1e-29 USDC
        for (tick, d0, d1, q0, price, py) in [
            (201300, 6, 18, true, "1811.7120276473959931723748683800275", "1861379814583879847594565245307116"),
            (64168, 8, 6, false, "61184.512171250791020430712322607670", "1959748472454936833636349183439"),
        ] {
            let p = dec::parse_lossy(price).unwrap();
            assert_eq!(tick_to_base_unit_price(tick, d0, d1, q0).unwrap(), p);
            assert_eq!(base_unit_price_to_sqrt_price_x96(&p, d0, d1, q0).to_string(), py, "tick {tick}");
        }
    }
}
