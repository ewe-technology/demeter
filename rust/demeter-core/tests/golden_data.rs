//! The Rust loader must reproduce python's `load_uni_v3_data` (reindex + fillna + statistic
//! columns). Golden file: rust/golden/out/market_data_eth_usdc_20220101_20220103.csv

use chrono::NaiveDate;
use demeter_core::data::{self, UniData};
use demeter_core::dec::{self, parse_lossy};
use demeter_core::types::{ts_to_string, TokenInfo, UniV3Pool};

fn pool() -> UniV3Pool {
    let usdc = TokenInfo::new("usdc", 6);
    let eth = TokenInfo::new("eth", 18);
    UniV3Pool::new(usdc.clone(), eth, parse_lossy("0.05").unwrap(), usdc, None)
}

fn load() -> UniData {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../samples/real-data/0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    );
    data::load_uni_v3_data(
        &pool(),
        "ethereum",
        "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
        NaiveDate::from_ymd_opt(2022, 1, 1).unwrap(),
        NaiveDate::from_ymd_opt(2022, 1, 3).unwrap(),
        path,
    )
    .unwrap()
}

#[test]
fn loader_matches_python() {
    let d = load();
    let golden = std::fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../golden/out/market_data_eth_usdc_20220101_20220103.csv"
    ))
    .unwrap();
    let mut lines = golden.lines();
    let header: Vec<&str> = lines.next().unwrap().split(',').collect();
    assert_eq!(header[1], "netAmount0");
    let rows: Vec<Vec<&str>> = lines.map(|l| l.split(',').collect()).collect();
    assert_eq!(rows.len(), d.len());
    for (i, r) in rows.iter().enumerate() {
        let b = &d.bars[i];
        assert_eq!(r[0], ts_to_string(d.ts[i]));
        let int = |s: &str| dec::trunc_to_i128(&parse_lossy(s).unwrap());
        assert_eq!(b.net_amount0, int(r[1]), "row {i}");
        assert_eq!(b.net_amount1, int(r[2]), "row {i}");
        assert_eq!(b.close_tick as i128, int(r[3]), "row {i}");
        assert_eq!(b.open_tick as i128, int(r[4]), "row {i}");
        assert_eq!(b.lowest_tick as i128, int(r[5]), "row {i}");
        assert_eq!(b.highest_tick as i128, int(r[6]), "row {i}");
        assert_eq!(b.in_amount0, int(r[7]), "row {i}");
        assert_eq!(b.in_amount1, int(r[8]), "row {i}");
        assert_eq!(b.current_liquidity as i128, int(r[9]), "row {i}");
        for (got, s, name) in [
            (&b.close, r[10], "close"),
            (&b.price, r[11], "price"),
            (&b.volume0, r[12], "volume0"),
            (&b.volume1, r[13], "volume1"),
        ] {
            let exp = parse_lossy(s).unwrap();
            assert!(
                dec::approx_eq(got, &exp, 1e-30),
                "row {i} {name}: {} vs {s}",
                dec::to_plain_string(got)
            );
        }
    }
}

#[test]
fn polars_roundtrip_and_ipc() {
    let d = load();
    let mut df = d.to_polars().unwrap();
    assert_eq!(df.height(), d.len());
    let bytes = data::frame_to_ipc(&mut df).unwrap();
    let back = data::frame_from_ipc(&bytes).unwrap();
    let d2 = UniData::from_polars(&back, None).unwrap();
    assert_eq!(d2.len(), d.len());
    for i in [0usize, 1, 17, 1000, d.len() - 1] {
        assert_eq!(d2.bars[i].close_tick, d.bars[i].close_tick);
        assert_eq!(d2.bars[i].current_liquidity, d.bars[i].current_liquidity);
        assert_eq!(d2.bars[i].in_amount1, d.bars[i].in_amount1);
        assert!(dec::approx_eq(&d2.bars[i].price, &d.bars[i].price, 1e-30));
    }
    assert_eq!(d2.row_of(d.ts[100]), Some(100));
}

#[test]
fn resample_hourly() {
    let d = load();
    let h = d.resample(3600).unwrap();
    assert_eq!(h.len(), 72);
    let first_hour: i128 = d.bars[..60].iter().map(|b| b.in_amount0).sum();
    assert_eq!(h.bars[0].in_amount0, first_hour);
    assert_eq!(h.bars[0].close_tick, d.bars[59].close_tick);
    assert_eq!(h.bars[0].price, d.bars[0].price);
}
