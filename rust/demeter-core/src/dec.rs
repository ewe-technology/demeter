//! Decimal helpers.
//!
//! The python engine works with `decimal.Decimal` at 35 significant digits. We use
//! [`fastnum::D128`], which keeps ~38 significant digits, so results agree with python to
//! roughly 1e-33 relative per operation (see README "Precision").
//!
//! D128 refuses to parse a literal with more than 38 significant digits, and python feeds us
//! values such as `sqrt_price_x96` (49 digits) or `liquidity * 2**96 * delta` (up to ~116 digits),
//! so every conversion into `Dec` goes through [`dec_from_digits`], which rounds half-even to 38
//! significant digits first.

use fastnum::bint::UInt;
use fastnum::decimal::{Context, Sign};
use fastnum::D128;
use ruint::aliases::{U256, U512};

pub type Dec = D128;

/// Max significant digits kept by `Dec`.
pub const MAX_DIGITS: usize = 38;

pub fn zero() -> Dec {
    Dec::ZERO
}

pub fn one() -> Dec {
    Dec::ONE
}

pub fn from_i64(v: i64) -> Dec {
    Dec::from(v)
}

const TEN38: u128 = 100_000_000_000_000_000_000_000_000_000_000_000_000;

/// `± m × 10^exp` for a mantissa that already fits (m < 10^38).
#[inline]
fn build(m: u128, exp: i32, negative: bool) -> Dec {
    let uint = UInt::<2>::from_digits([m as u64, (m >> 64) as u64]);
    Dec::from_parts(
        uint,
        exp,
        if negative { Sign::Minus } else { Sign::Plus },
        Context::default(),
    )
}

/// Round a u128 with 39 digits to 38 (half even).
#[inline]
fn build_u128(v: u128, negative: bool) -> Dec {
    if v < TEN38 {
        return build(v, 0, negative);
    }
    let (mut q, r) = (v / 10, v % 10);
    if r > 5 || (r == 5 && q % 2 == 1) {
        q += 1;
    }
    if q == TEN38 {
        return build(q / 10, 2, negative);
    }
    build(q, 1, negative)
}

pub fn from_i128(v: i128) -> Dec {
    build_u128(v.unsigned_abs(), v < 0)
}

pub fn from_u128(v: u128) -> Dec {
    build_u128(v, false)
}

macro_rules! big_to_dec {
    ($name:ident, $ty:ty, $bits:expr) => {
        /// Exact integer to Dec, rounding half-even to 38 significant digits (integer math only).
        pub fn $name(v: $ty) -> Dec {
            if v <= <$ty>::from(u128::MAX) {
                return from_u128(v.to::<u128>());
            }
            let bit_len = ($bits - v.leading_zeros()) as u32;
            // digits of v are floor(bit_len * log10 2) or one more
            let mut k = ((bit_len as f64 - 1.0) * std::f64::consts::LOG10_2) as u32 + 1;
            k = k.saturating_sub(38);
            let ten = <$ty>::from(10u8);
            let ten38 = <$ty>::from(TEN38);
            thread_local! {
                static POW: Vec<$ty> = {
                    let ten = <$ty>::from(10u8);
                    let mut v = vec![<$ty>::from(1u8)];
                    while let Some(x) = v.last().unwrap().checked_mul(ten) {
                        v.push(x);
                    }
                    v
                };
            }
            let mut p = POW.with(|t| t[k as usize]);
            let mut q = v / p;
            while q >= ten38 {
                k += 1;
                p *= ten;
                q = v / p;
            }
            let r = v - q * p;
            let half = p >> 1;
            let odd = q.bit(0);
            if r > half || (r == half && p.bit(0) == false && odd) {
                q += <$ty>::from(1u8);
            }
            if q == ten38 {
                return build(TEN38 / 10, k as i32 + 1, false);
            }
            build(q.to::<u128>(), k as i32, false)
        }
    };
}

big_to_dec!(from_u256, U256, 256);
big_to_dec!(from_u512, U512, 512);

/// Same value python gets from `Decimal(some_float)`: the float is converted exactly, then kept at 38 digits.
pub fn from_f64_exact(v: f64) -> Dec {
    if v == 0.0 {
        return Dec::ZERO;
    }
    // `{:e}` of an f64 prints the shortest repr, not the exact binary value; print with enough
    // digits (the exact expansion of a double has at most ~767 digits, 60 is plenty for 38 kept).
    let s = format!("{:.60e}", v);
    parse_lossy(&s).expect("formatted float must parse")
}

/// Build `± digits × 10^exp`, rounding half-even to [`MAX_DIGITS`] significant digits.
/// `digits` must be ascii decimal digits (leading zeros allowed).
pub fn dec_from_digits(digits: &str, exp: i32, negative: bool) -> Dec {
    let digits = digits.trim_start_matches('0');
    if digits.is_empty() {
        return Dec::ZERO;
    }
    let bytes = digits.as_bytes();
    let (mantissa, exp) = if bytes.len() <= MAX_DIGITS {
        (digits.parse::<u128>().expect("digits"), exp)
    } else {
        let keep = &digits[..MAX_DIGITS];
        let dropped = bytes.len() - MAX_DIGITS;
        let mut m: u128 = keep.parse().expect("digits");
        let first_dropped = bytes[MAX_DIGITS] - b'0';
        let rest_nonzero = bytes[MAX_DIGITS + 1..].iter().any(|c| *c != b'0');
        let round_up = first_dropped > 5 || (first_dropped == 5 && (rest_nonzero || m % 2 == 1));
        let mut exp = exp + dropped as i32;
        if round_up {
            m += 1;
            if m == 10u128.pow(MAX_DIGITS as u32) {
                m /= 10;
                exp += 1;
            }
        }
        (m, exp)
    };
    let lo = mantissa as u64;
    let hi = (mantissa >> 64) as u64;
    let uint = UInt::<2>::from_digits([lo, hi]);
    Dec::from_parts(
        uint,
        exp,
        if negative { Sign::Minus } else { Sign::Plus },
        Context::default(),
    )
}

/// Parse any python `str(Decimal)` / `repr(float)` / int string, rounding to 38 digits.
/// Accepts `NaN`, `Infinity`, `-Infinity` (returned as `Dec::NAN` / `Dec::INFINITY`).
pub fn parse_lossy(s: &str) -> Result<Dec, String> {
    let s = s.trim();
    let (neg, body) = match s.as_bytes().first() {
        Some(b'-') => (true, &s[1..]),
        Some(b'+') => (false, &s[1..]),
        _ => (false, s),
    };
    let lower = body.to_ascii_lowercase();
    if lower == "nan" || lower == "snan" {
        return Ok(Dec::NAN);
    }
    if lower == "infinity" || lower == "inf" {
        return Ok(if neg {
            Dec::NEG_INFINITY
        } else {
            Dec::INFINITY
        });
    }
    let (mant, exp_part) = match lower.find('e') {
        Some(i) => (&lower[..i], Some(&lower[i + 1..])),
        None => (lower.as_str(), None),
    };
    let mut exp: i32 = match exp_part {
        Some(e) => e.parse().map_err(|_| format!("invalid decimal '{s}'"))?,
        None => 0,
    };
    let mut digits = String::with_capacity(mant.len());
    let mut seen_dot = false;
    for c in mant.chars() {
        match c {
            '0'..='9' => {
                digits.push(c);
                if seen_dot {
                    exp -= 1;
                }
            }
            '.' if !seen_dot => seen_dot = true,
            '_' => {}
            _ => return Err(format!("invalid decimal '{s}'")),
        }
    }
    if digits.is_empty() {
        return Err(format!("invalid decimal '{s}'"));
    }
    Ok(dec_from_digits(&digits, exp, neg))
}

/// Split a finite `Dec` into (negative, digits, exponent): value = ±digits × 10^exponent.
pub fn to_parts(d: &Dec) -> (bool, u128, i32) {
    let limbs = d.digits();
    let limbs = limbs.digits();
    let m = (limbs[0] as u128) | ((limbs[1] as u128) << 64);
    (
        d.is_sign_negative(),
        m,
        -(d.fractional_digits_count() as i32),
    )
}

/// String python's `Decimal(...)` constructor reads back exactly, e.g. `"-12345E-3"`.
pub fn to_py_string(d: &Dec) -> String {
    if d.is_nan() {
        return "NaN".into();
    }
    if d.is_infinite() {
        return if d.is_sign_negative() {
            "-Infinity".into()
        } else {
            "Infinity".into()
        };
    }
    let (neg, m, e) = to_parts(d);
    let sign = if neg && m != 0 { "-" } else { "" };
    if e == 0 {
        format!("{sign}{m}")
    } else {
        format!("{sign}{m}E{e}")
    }
}

/// Round to `digits` significant digits, half-even (python `Context(prec=digits).plus(d)`).
pub fn round_sig(d: &Dec, digits: u32) -> Dec {
    if d.is_nan() || d.is_infinite() || d.is_zero() {
        return *d;
    }
    let (neg, m, e) = to_parts(d);
    let n = if m == 0 { 1 } else { m.ilog10() + 1 };
    if n <= digits {
        return *d;
    }
    let drop = n - digits;
    let p = 10u128.pow(drop);
    let (mut q, r) = (m / p, m % p);
    let half = p / 2;
    if r > half || (r == half && q % 2 == 1) {
        q += 1;
    }
    let mut exp = e + drop as i32;
    if q == 10u128.pow(digits) {
        q /= 10;
        exp += 1;
    }
    build(q, exp, neg)
}

/// Human friendly plain string (no exponent), used for CSV output and Display.
pub fn to_plain_string(d: &Dec) -> String {
    if d.is_nan() || d.is_infinite() {
        return to_py_string(d);
    }
    let (neg, m, e) = to_parts(d);
    let sign = if neg && m != 0 { "-" } else { "" };
    let digits = m.to_string();
    if e >= 0 {
        if m == 0 {
            return "0".into();
        }
        return format!("{sign}{digits}{}", "0".repeat(e as usize));
    }
    let frac = (-e) as usize;
    if digits.len() > frac {
        let (i, f) = digits.split_at(digits.len() - frac);
        format!("{sign}{i}.{f}")
    } else {
        format!("{sign}0.{}{digits}", "0".repeat(frac - digits.len()))
    }
}

/// `int(d)` in python: truncate toward zero. Negative values give `None` (callers want unsigned).
pub fn trunc_to_u256(d: &Dec) -> Option<U256> {
    if d.is_nan() || d.is_infinite() || d.is_sign_negative() && !d.is_zero() {
        return None;
    }
    let (_, m, e) = to_parts(d);
    let m = U256::from(m);
    if e >= 0 {
        m.checked_mul(U256::from(10u8).checked_pow(U256::from(e as u32))?)
    } else {
        let div = (-e) as u32;
        if div > 77 {
            return Some(U256::ZERO);
        }
        Some(m / U256::from(10u8).pow(U256::from(div)))
    }
}

/// `int(d)` truncating toward zero, as i128 (saturating outside range).
pub fn trunc_to_i128(d: &Dec) -> i128 {
    if d.is_nan() {
        return 0;
    }
    let (neg, m, e) = to_parts(d);
    let v: u128 = if e >= 0 {
        m.saturating_mul(10u128.checked_pow(e as u32).unwrap_or(u128::MAX))
    } else if (-e) as u32 > 38 {
        0
    } else {
        m / 10u128.pow((-e) as u32)
    };
    let v = v.min(i128::MAX as u128) as i128;
    if neg {
        -v
    } else {
        v
    }
}

/// `Decimal(10 ** n)` as python evaluates it: exact for n >= 0, but for n < 0 `10 ** n` is a
/// python *float*, so the Decimal holds the float's exact binary expansion (e.g. 10**-12 becomes
/// 9.9999999999999997988e-13). The price conversions in helper.py rely on that.
pub fn py_pow10(n: i32) -> Dec {
    if n >= 0 {
        pow10(n)
    } else {
        thread_local! {
            static CACHE: std::cell::RefCell<std::collections::HashMap<i32, Dec>> = Default::default();
        }
        CACHE.with(|c| {
            *c.borrow_mut()
                .entry(n)
                .or_insert_with(|| from_f64_exact(10f64.powf(n as f64)))
        })
    }
}

/// Exact 10^n (no float detour).
#[inline]
pub fn pow10(n: i32) -> Dec {
    build(1, n, false)
}

/// 2^96 as Dec (exact: 29 digits).
pub const Q96: Dec = Dec::from_parts(
    UInt::<2>::from_digits([0, 1u64 << 32]),
    0,
    Sign::Plus,
    Context::default(),
);

#[inline]
pub fn q96() -> Dec {
    Q96
}

/// `python float(d)`.
pub fn to_f64(d: &Dec) -> f64 {
    d.to_f64()
}

/// Relative closeness used by tests: |a-b| <= tol * max(|a|,|b|), or both tiny.
pub fn approx_eq(a: &Dec, b: &Dec, rel_tol: f64) -> bool {
    if a == b {
        return true;
    }
    let fa = a.to_f64();
    let fb = b.to_f64();
    let scale = fa.abs().max(fb.abs());
    if scale == 0.0 {
        return true;
    }
    ((fa - fb).abs() / scale) <= rel_tol || (*a - *b).abs().to_f64() <= rel_tol * scale
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip() {
        for s in [
            "0",
            "1",
            "-1",
            "123.456",
            "-0.000001234",
            "1E+5",
            "3684.8756207340156869292450740806437",
        ] {
            let d = parse_lossy(s).unwrap();
            let back = parse_lossy(&to_py_string(&d)).unwrap();
            assert_eq!(d, back, "{s}");
        }
        assert_eq!(
            to_plain_string(&parse_lossy("123.4500").unwrap()),
            "123.4500"
        );
        assert_eq!(
            to_plain_string(&parse_lossy("-0.00012").unwrap()),
            "-0.00012"
        );
        assert_eq!(to_plain_string(&parse_lossy("12E3").unwrap()), "12000");
    }

    #[test]
    fn big_values_round() {
        let d = parse_lossy("1461501637330902918203684832716283019655932542975").unwrap();
        assert_eq!(
            to_py_string(&d),
            "14615016373309029182036848327162830197E11"
        );
        let u = trunc_to_u256(&d).unwrap();
        assert_eq!(
            u.to_string(),
            "1461501637330902918203684832716283019700000000000"
        );
        // half even
        assert_eq!(
            to_py_string(&dec_from_digits(
                "123456789012345678901234567890123456785",
                0,
                false
            )),
            "12345678901234567890123456789012345678E1"
        );
        assert_eq!(
            to_py_string(&dec_from_digits(
                "123456789012345678901234567890123456775",
                0,
                false
            )),
            "12345678901234567890123456789012345678E1"
        );
        assert_eq!(
            to_py_string(&dec_from_digits(
                "999999999999999999999999999999999999999",
                0,
                false
            )),
            "10000000000000000000000000000000000000E2"
        );
    }

    #[test]
    fn py_pow10_float_detour() {
        // python: Decimal(10 ** -12) == Decimal('9.999999999999999798866476292556153672528435500..E-13')
        let d = py_pow10(-12);
        assert!(
            to_plain_string(&d).starts_with("0.000000000000999999999999999979886647629255615367"),
            "{}",
            to_plain_string(&d)
        );
        assert_eq!(py_pow10(12), pow10(12));
    }

    #[test]
    fn fast_integer_conversion_matches_string_path() {
        let cases = [
            "0",
            "1",
            "99999999999999999999999999999999999999",
            "100000000000000000000000000000000000000",
            "340282366920938463463374607431768211455",
            "340282366920938463463374607431768211456",
            "1461501637330902918203684832716283019655932542975",
            "123456789012345678901234567890123456785",
            "123456789012345678901234567890123456775000",
            "999999999999999999999999999999999999995",
            "79228162514264337593543950336",
            "115792089237316195423570985008687907853269984665640564039457584007913129639935",
        ];
        for c in cases {
            let u = U256::from_str_radix(c, 10).unwrap();
            let expected = dec_from_digits(c, 0, false);
            assert_eq!(to_py_string(&from_u256(u)), to_py_string(&expected), "{c}");
            assert_eq!(
                to_py_string(&from_u512(U512::from(u))),
                to_py_string(&expected),
                "{c} u512"
            );
            if let Ok(v) = c.parse::<u128>() {
                assert_eq!(
                    to_py_string(&from_u128(v)),
                    to_py_string(&expected),
                    "{c} u128"
                );
            }
        }
        let big = U512::from(U256::MAX) * U512::from(U256::MAX);
        assert_eq!(
            to_py_string(&from_u512(big)),
            to_py_string(&dec_from_digits(&big.to_string(), 0, false))
        );
        assert_eq!(
            q96(),
            dec_from_digits("79228162514264337593543950336", 0, false)
        );
        assert_eq!(pow10(-6), parse_lossy("0.000001").unwrap());
    }

    #[test]
    fn trunc() {
        assert_eq!(trunc_to_i128(&parse_lossy("-12.9").unwrap()), -12);
        assert_eq!(trunc_to_i128(&parse_lossy("12.9").unwrap()), 12);
        assert_eq!(
            trunc_to_u256(&parse_lossy("12.9").unwrap()).unwrap(),
            U256::from(12)
        );
    }
}
