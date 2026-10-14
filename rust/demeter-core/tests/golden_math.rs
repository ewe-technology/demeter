//! Compare the Rust math port with vectors produced by the python engine
//! (`rust/golden/make_golden.py math` -> `rust/golden/out/math_vectors.json`).

use demeter_core::dec::{self, parse_lossy, Dec};
use demeter_core::math;
use ruint::aliases::U256;
use serde_json::Value;
use std::str::FromStr;

fn vectors() -> Value {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../golden/out/math_vectors.json"
    );
    let s = std::fs::read_to_string(path).expect("run rust/golden/make_golden.py math first");
    serde_json::from_str(&s).unwrap()
}

fn d(s: &str) -> Dec {
    parse_lossy(s).unwrap()
}

const TOL: f64 = 1e-30;

#[test]
fn sqrt_ratio_at_tick_exact() {
    let v = vectors();
    let m = v["sqrt_at_tick"].as_object().unwrap();
    for (tick, expected) in m {
        let t: i32 = tick.parse().unwrap();
        let got = math::get_sqrt_ratio_at_tick(t).unwrap();
        assert_eq!(got.to_string(), expected.as_str().unwrap(), "tick {t}");
    }
    assert!(m.len() > 500);
}

#[test]
fn tick_to_price() {
    let v = vectors();
    for row in v["tick_price"].as_array().unwrap() {
        let r = row.as_array().unwrap();
        let (t, d0, d1, q) = (
            r[0].as_i64().unwrap() as i32,
            r[1].as_u64().unwrap() as u32,
            r[2].as_u64().unwrap() as u32,
            r[3].as_bool().unwrap(),
        );
        let expected = d(r[4].as_str().unwrap());
        let got = math::tick_to_base_unit_price(t, d0, d1, q).unwrap();
        assert!(
            dec::approx_eq(&got, &expected, TOL),
            "tick {t} d0 {d0} d1 {d1} q {q}: {} vs {}",
            dec::to_plain_string(&got),
            dec::to_plain_string(&expected)
        );
    }
}

#[test]
fn price_to_tick_and_sqrt() {
    let v = vectors();
    for row in v["price_tick"].as_array().unwrap() {
        let r = row.as_array().unwrap();
        if r[4].is_null() {
            continue;
        }
        let p = d(r[0].as_str().unwrap());
        let (d0, d1, q) = (
            r[1].as_u64().unwrap() as u32,
            r[2].as_u64().unwrap() as u32,
            r[3].as_bool().unwrap(),
        );
        let tick = r[4].as_i64().unwrap() as i32;
        let sqrt = U256::from_str(r[5].as_str().unwrap()).unwrap();
        let back = d(r[6].as_str().unwrap());
        let stt = r[7].as_i64().unwrap() as i32;

        // legacy mode must reproduce python's tick exactly
        assert_eq!(
            math::base_unit_price_to_tick(&p, d0, d1, q, true),
            tick,
            "price {p} {d0} {d1} {q}"
        );
        let got_sqrt = math::base_unit_price_to_sqrt_price_x96(&p, d0, d1, q);
        // python truncates a 35 digit decimal, we a 38 digit one: compare relatively
        let rel = (dec::from_u256(got_sqrt) - dec::from_u256(sqrt)).abs() / dec::from_u256(sqrt);
        assert!(rel.to_f64() < 1e-33, "sqrt {p}: {got_sqrt} vs {sqrt}");
        let got_back = math::sqrt_price_x96_to_base_unit_price(sqrt, d0, d1, q);
        assert!(dec::approx_eq(&got_back, &back, TOL), "back {p}");
        assert_eq!(
            math::sqrt_price_x96_to_tick(sqrt, true),
            stt,
            "sqrt->tick {p}"
        );
        // fixed mode is exact floor, may differ from legacy by 1 only
        let fixed = math::sqrt_price_x96_to_tick(sqrt, false);
        assert!((fixed - stt).abs() <= 1, "fixed {fixed} vs legacy {stt}");
        assert!(math::get_sqrt_ratio_at_tick(fixed).unwrap() <= sqrt);
        assert!(math::get_sqrt_ratio_at_tick(fixed + 1).unwrap() > sqrt);
    }
}

#[test]
fn nearest_usable() {
    let v = vectors();
    for row in v["nearest"].as_array().unwrap() {
        let r = row.as_array().unwrap();
        let (t, s, e) = (
            r[0].as_i64().unwrap() as i32,
            r[1].as_i64().unwrap() as i32,
            r[2].as_i64().unwrap() as i32,
        );
        assert_eq!(math::nearest_usable_tick(t, s), e, "{t} {s}");
    }
}

#[test]
fn liquidity_and_amounts() {
    let v = vectors();
    for row in v["liquidity"].as_array().unwrap() {
        let r = row.as_array().unwrap();
        let (sp, lo, hi) = (
            r[0].as_i64().unwrap() as i32,
            r[1].as_i64().unwrap() as i32,
            r[2].as_i64().unwrap() as i32,
        );
        let (a0, a1) = (d(r[3].as_str().unwrap()), d(r[4].as_str().unwrap()));
        let (d0, d1) = (r[5].as_u64().unwrap() as u32, r[6].as_u64().unwrap() as u32);
        let liq = U256::from_str(r[7].as_str().unwrap()).unwrap();
        let (e0, e1) = (d(r[8].as_str().unwrap()), d(r[9].as_str().unwrap()));
        let sqrt = math::get_sqrt_ratio_at_tick(sp).unwrap();
        let got = math::get_liquidity(sqrt, lo, hi, &a0, &a1, d0, d1).unwrap();
        assert_eq!(got, liq, "liquidity case {row}");
        let (g0, g1) = math::get_amounts(sqrt, lo, hi, got.to::<u128>(), d0, d1).unwrap();
        assert!(
            dec::approx_eq(&g0, &e0, TOL),
            "amount0 {row}: {}",
            dec::to_plain_string(&g0)
        );
        assert!(
            dec::approx_eq(&g1, &e1, TOL),
            "amount1 {row}: {}",
            dec::to_plain_string(&g1)
        );
        // the per-iteration fast path (cached decimal sqrt prices) must agree as well
        let sp = |t: i32| math::SqrtPrice::new(math::get_sqrt_ratio_at_tick(t).unwrap());
        let (f0, f1) = math::get_amounts_fast(
            &math::SqrtPrice::new(sqrt),
            &sp(lo),
            &sp(hi),
            got.to::<u128>(),
            d0,
            d1,
        );
        assert!(
            dec::approx_eq(&f0, &e0, TOL),
            "fast amount0 {row}: {}",
            dec::to_plain_string(&f0)
        );
        assert!(
            dec::approx_eq(&f1, &e1, TOL),
            "fast amount1 {row}: {}",
            dec::to_plain_string(&f1)
        );
    }
}
