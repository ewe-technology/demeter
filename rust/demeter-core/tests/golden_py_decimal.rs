//! dec::Dec arithmetic against python `decimal` at prec 35 (`rust/golden/make_py_decimal_ops.py` ->
//! `rust/golden/out/py_decimal_ops.txt`): value, coefficient digits, exponent and sign must all match.

use demeter_core::dec::{self, Dec};

fn parse(t: &str) -> Dec {
    // sign:coefficient:exponent, python's Decimal.as_tuple()
    let mut it = t.split(':');
    let neg = it.next().unwrap() == "1";
    let digits = it.next().unwrap();
    let exp: i32 = it.next().unwrap().parse().unwrap();
    dec::dec_from_digits(digits, exp, neg)
}

fn tuple(d: &Dec) -> String {
    let (neg, m, e) = dec::to_parts(d);
    format!("{}:{}:{}", neg as u8, m, e)
}

#[test]
fn arithmetic_equals_python_decimal() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../golden/out/py_decimal_ops.txt");
    let text = std::fs::read_to_string(path).expect("run rust/golden/make_py_decimal_ops.py first");
    let (mut n, mut bad) = (0, Vec::new());
    for line in text.lines() {
        let f: Vec<&str> = line.split(' ').collect();
        let (a, b) = (parse(f[1]), parse(f[2]));
        let r = match f[0] {
            "add" => a + b,
            "sub" => a - b,
            "mul" => a * b,
            "div" => a / b,
            "sqrt" => a.sqrt(),
            op => panic!("unknown op {op}"),
        };
        n += 1;
        if tuple(&r) != f[3] {
            bad.push(format!("{line} -> rust {}", tuple(&r)));
        }
    }
    assert!(n > 1000, "too few vectors: {n}");
    assert!(bad.is_empty(), "{} of {n} differ, e.g.\n{}", bad.len(), bad[..bad.len().min(8)].join("\n"));
}
