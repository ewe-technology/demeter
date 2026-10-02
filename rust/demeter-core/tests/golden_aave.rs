//! Aave market through the Rust loop, checked against the python engine:
//! `samples/strategy-example/22_aave_liquidate.py` (supply 10 WETH, borrow 7500 USDC, WETH falls
//! from 1000 to 800 at 00:07 and the debt is liquidated), plus loading the polygon sample data.

use chrono::NaiveDate;
use demeter_core::aave::{
    load_aave_data, AaveData, AaveTokenData, AaveTokenStatus, AaveV3Market, REQUIRED_DATA_COLUMN,
};
use demeter_core::actions::ActionKind;
use demeter_core::actuator::{Actuator, Ctx, PriceTable, Snapshot, Strategy};
use demeter_core::broker::shared;
use demeter_core::dec::{self, parse_lossy, Dec};
use demeter_core::market::MarketBalance;
use demeter_core::trigger::{TriggerCond, Triggers};
use demeter_core::types::{naive_to_ts, AaveBalance, MarketInfo, TokenInfo};
use demeter_core::Result;

fn d(s: &str) -> Dec {
    parse_lossy(s).unwrap()
}

fn ts(day: u32, h: u32, mi: u32) -> i64 {
    naive_to_ts(
        &NaiveDate::from_ymd_opt(2023, 8, day)
            .unwrap()
            .and_hms_opt(h, mi, 0)
            .unwrap(),
    )
}

const RISK_FILE: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../tests/aave_risk_parameters/demo.csv"
);

struct Liquidate {
    triggers: Triggers<Liquidate>,
}

impl Liquidate {
    fn supply_and_borrow(&mut self, ctx: &Ctx, _s: &Snapshot) -> Result<()> {
        let m = ctx.aave("aave")?;
        let mut m = m.borrow_mut();
        m.supply(&TokenInfo::new("weth", 18), d("10"), true)?;
        m.borrow(&TokenInfo::new("usdc", 6), Some(d("7500")))?;
        Ok(())
    }
}

impl Strategy for Liquidate {
    fn initialize(&mut self, _ctx: &Ctx) -> Result<()> {
        self.triggers.push(
            TriggerCond::at_time(ts(15, 0, 0)),
            Liquidate::supply_and_borrow,
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

fn minutes() -> Vec<i64> {
    (0..10).map(|i| ts(15, 0, i)).collect()
}

/// the inline data of 22_aave_liquidate.py: indexes grow 0.1% a minute, rates are 0
fn sample_22_data() -> AaveData {
    let rows: Vec<Option<AaveTokenStatus>> = (0..10)
        .map(|i| {
            let idx = d("1") + d("0.001") * dec::from_i64(i);
            Some(AaveTokenStatus::from_values([
                dec::zero(),
                dec::zero(),
                dec::zero(),
                idx,
                idx,
            ]))
        })
        .collect();
    let columns: Vec<String> = REQUIRED_DATA_COLUMN.iter().map(|c| c.to_string()).collect();
    let token = |name: &str| AaveTokenData {
        name: name.into(),
        columns: columns.clone(),
        rows: rows.clone(),
    };
    AaveData::default()
        .with_token(token("WETH"), &minutes())
        .unwrap()
        .with_token(token("USDC"), &minutes())
        .unwrap()
}

fn run(legacy_quirks: bool) -> Actuator {
    let weth = TokenInfo::new("weth", 18);
    let usdc = TokenInfo::new("usdc", 6);
    let mut m = AaveV3Market::from_risk_file(
        MarketInfo::aave("aave"),
        RISK_FILE,
        vec![weth.clone(), usdc.clone()],
    )
    .unwrap();
    m.set_data(std::sync::Arc::new(sample_22_data()));
    let mut act = Actuator::new(false);
    act.compat.legacy_quirks = legacy_quirks;
    act.add_market(shared(m)).unwrap();
    act.broker.borrow().wallet.borrow_mut().set(&weth, d("10"));
    let weth_price: Vec<Dec> = (0..10)
        .map(|i| if i < 7 { d("1000") } else { d("800") })
        .collect();
    let prices = PriceTable::new(
        minutes(),
        vec!["WETH".into(), "USDC".into()],
        vec![weth_price, vec![d("1"); 10]],
    )
    .unwrap();
    act.set_price(prices, TokenInfo::usd()).unwrap();
    let mut s = Liquidate {
        triggers: Triggers::default(),
    };
    act.run(&mut s).unwrap();
    act
}

fn aave_balance(act: &Actuator, row: usize) -> AaveBalance {
    let rows = act.account_status.borrow();
    match &rows[row].market_balances[0].1 {
        MarketBalance::Aave(b) => b.clone(),
        other => panic!("expected an aave balance, got {other:?}"),
    }
}

#[test]
fn liquidation_matches_python() {
    let act = run(true);
    {
        let rows = act.account_status.borrow();
        assert_eq!(rows.len(), 10);
        // python account_status_df net_value at 00:00, 00:07 and 00:09
        assert_eq!(rows[0].net_value, d("10000"));
        assert_eq!(rows[7].net_value, d("7625.875"));
        assert_eq!(rows[9].net_value, d("7626.125"));
    }

    let b0 = aave_balance(&act, 0);
    assert_eq!(b0.net_value, d("2500"));
    assert_eq!(b0.health_factor, d("1.1"));
    assert_eq!(b0.max_ltv, d("0.8"));
    assert_eq!(b0.ltv, d("0.75"));
    assert_eq!(b0.liquidation_threshold, d("0.825"));
    let b7 = aave_balance(&act, 7);
    assert_eq!(b7.net_value, d("125.875"));
    assert_eq!(b7.borrows_count, 0);
    assert!(b7.health_factor.is_infinite());

    let log = act.log.borrow();
    let kinds: Vec<&str> = log.actions.iter().map(|a| a.kind.type_name()).collect();
    // python labels the liquidation `aave_repay`
    assert_eq!(kinds, ["aave_supply", "aave_borrow", "aave_repay"]);
    match &log.actions[2].kind {
        ActionKind::AaveLiquidation {
            collateral_token,
            debt_token,
            delt_to_cover,
            collateral_used,
            variable_delt_liquidated,
            health_factor_before,
            collateral_after,
            variable_debt_after,
            ..
        } => {
            assert_eq!(collateral_token, "WETH");
            assert_eq!(debt_token, "USDC");
            assert_eq!(delt_to_cover.value, d("7552.5"));
            assert_eq!(collateral_used.value, d("9.91265625"));
            assert_eq!(variable_delt_liquidated.value, d("7552.5"));
            assert_eq!(*health_factor_before, d("0.88"));
            assert_eq!(collateral_after.value, d("0.15734375"));
            assert!(variable_debt_after.value.is_zero());
        }
        other => panic!("expected a liquidation, got {other:?}"),
    }
    assert_eq!(log.actions[2].timestamp, ts(15, 0, 7));
}

#[test]
fn corrected_mode_labels_liquidation() {
    let act = run(false);
    let log = act.log.borrow();
    assert_eq!(log.actions[2].kind.type_name(), "aave_liquidation");
    // both tokens share one index here, so the collateral index fix leaves the numbers unchanged
    assert_eq!(act.account_status.borrow()[9].net_value, d("7626.125"));
}

#[test]
fn loads_polygon_sample_data() {
    let weth = TokenInfo::with_address("weth", 18, "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619");
    let data = load_aave_data(
        "polygon",
        &[weth],
        NaiveDate::from_ymd_opt(2023, 8, 14).unwrap(),
        NaiveDate::from_ymd_opt(2023, 8, 17).unwrap(),
        concat!(env!("CARGO_MANIFEST_DIR"), "/../../samples/data"),
    )
    .unwrap();
    assert_eq!(data.len(), 1440 * 4);
    assert_eq!(data.ts[0], ts(14, 0, 0));
    assert_eq!(*data.ts.last().unwrap(), ts(17, 23, 59));
    let s = data.status(0, "WETH").unwrap();
    assert_eq!(s.liquidity_index, d("1.005645819576767014923645209"));
    assert_eq!(s.variable_borrow_rate, d("0.020641903947336903838838715"));
    assert!(data.has_column("WETH", "stable_borrow_rate"));
}

// ------------------------------------------------------------ market operations
// numbers from tests/aave_market_test.py (python engine)

use demeter_core::aave::AavePrices;
use demeter_core::actions::ActionLog;
use demeter_core::broker::Broker;

fn weth() -> TokenInfo {
    TokenInfo::new("weth", 18)
}
fn dai() -> TokenInfo {
    TokenInfo::new("dai", 6)
}

fn status(lr: &str, sbr: &str, vbr: &str, li: &str, vbi: &str) -> Option<AaveTokenStatus> {
    Some(AaveTokenStatus::from_values([
        d(lr),
        d(sbr),
        d(vbr),
        d(li),
        d(vbi),
    ]))
}

/// python `get_test_market`: 5 WETH in the wallet, WETH at 1000, liquidity index 1.6
fn test_market(legacy: bool, weth_price: &str) -> (AaveV3Market, Broker) {
    let mut m =
        AaveV3Market::from_risk_file(MarketInfo::aave("aave_test"), RISK_FILE, vec![weth()])
            .unwrap();
    m.compat.legacy_quirks = legacy;
    set_prices(&mut m, weth_price);
    let broker = Broker::new(false, shared(ActionLog::default()));
    broker.wallet.borrow_mut().set(&weth(), d("5"));
    m.set_broker(&broker);
    (m, broker)
}

fn set_prices(m: &mut AaveV3Market, weth_price: &str) {
    m.set_market_status_values(
        ts(1, 0, 0),
        vec![
            ("WETH".into(), status("0.05", "0.1", "0.08", "1.6", "1")),
            ("DAI".into(), status("0.08", "0.12", "0.1", "1.6", "1.6")),
        ],
        AavePrices::Values(vec![("WETH".into(), d(weth_price)), ("DAI".into(), d("1"))]),
    );
}

#[test]
fn max_withdraw_and_borrow() {
    let (mut m, _b) = test_market(true, "1000");
    m.supply(&weth(), d("5"), true).unwrap();
    m.borrow(&dai(), Some(d("3300"))).unwrap();
    let max = m.get_max_withdraw_amount(&weth()).unwrap();
    assert_eq!(max, d("1"));
    m.withdraw(&weth(), Some(max)).unwrap();
    assert_eq!(m.health_factor().unwrap(), d("1"));

    let (mut m, _b) = test_market(true, "1000");
    m.supply(&weth(), d("1"), true).unwrap();
    assert_eq!(m.get_max_borrow_amount(&weth()).unwrap(), d("0.792"));
}

#[test]
fn repay_with_collateral() {
    let (mut m, b) = test_market(true, "1000");
    m.supply(&weth(), d("5"), true).unwrap();
    m.borrow(&dai(), Some(d("1000"))).unwrap();
    let debt = m.get_max_repay_amount(&dai()).unwrap();
    m.repay(&dai(), Some(debt), true, Some(&weth())).unwrap();
    assert!(m.borrow_infos().is_empty());
    assert_eq!(b.wallet.borrow().balance(&dai()).unwrap(), d("1000"));
    assert_eq!(m.get_supply(&weth()).unwrap().amount, d("4"));
}

#[test]
fn liquidate_half() {
    let (mut m, _b) = test_market(true, "1000");
    m.supply(&weth(), d("4.2"), true).unwrap();
    m.borrow(&dai(), Some(d("3300"))).unwrap();
    assert_eq!(m.health_factor().unwrap(), d("1.05"));
    set_prices(&mut m, "920");
    assert_eq!(m.health_factor().unwrap(), d("0.966"));
    m.update().unwrap();
    assert_eq!(dec::quantize(&m.health_factor().unwrap(), 9), d("1.06575"));
    assert_eq!(
        dec::quantize(&m.get_supply(&weth()).unwrap().value, 9),
        d("2131.5")
    );
    assert_eq!(m.get_borrow(&dai()).unwrap().value, d("1650"));
}

#[test]
fn rejected_withdraw_quirk() {
    for (legacy, left) in [(true, "3"), (false, "5")] {
        let (mut m, _b) = test_market(legacy, "1000");
        m.supply(&weth(), d("5"), true).unwrap();
        m.borrow(&dai(), Some(d("3300"))).unwrap();
        assert!(m.withdraw(&weth(), Some(d("2"))).is_err());
        set_prices(&mut m, "1000"); // refreshes the cached values
                                    // python (legacy) leaves the supply reduced by the rejected withdraw
        assert_eq!(
            m.get_supply(&weth()).unwrap().amount,
            d(left),
            "legacy={legacy}"
        );
    }
}

#[test]
fn change_collateral_is_checked() {
    let (mut m, _b) = test_market(true, "1000");
    m.supply(&weth(), d("3"), false).unwrap();
    m.change_collateral(&weth(), true).unwrap();
    m.borrow(&dai(), Some(d("1000"))).unwrap();
    let hf = m.health_factor().unwrap();
    assert!(m.change_collateral(&weth(), false).is_err());
    assert_eq!(m.health_factor().unwrap(), hf);
}

#[test]
fn deep_liquidation_with_different_indexes() {
    // WETH collateral (liquidity index 1.6), DAI debt (liquidity index 2), WETH falls to 500.
    // python (legacy) reduces the collateral with the DAI index, leaves some of it, the health
    // factor stays in (0, 1) with every debt liquidated once and `_liquidate` fails with
    // AttributeError. Corrected mode takes all the collateral and stops.
    for legacy in [true, false] {
        let (mut m, _b) = test_market(legacy, "1000");
        m.supply(&weth(), d("5"), true).unwrap();
        m.borrow(&dai(), Some(d("3300"))).unwrap();
        m.set_market_status_values(
            ts(1, 0, 1),
            vec![
                ("WETH".into(), status("0.05", "0.1", "0.08", "1.6", "1")),
                ("DAI".into(), status("0.08", "0.12", "0.1", "2", "1.6")),
            ],
            AavePrices::Values(vec![("WETH".into(), d("500")), ("DAI".into(), d("1"))]),
        );
        let r = m.update();
        if legacy {
            let e = r.unwrap_err().message();
            assert!(e.starts_with("AttributeError"), "{e}");
        } else {
            r.unwrap();
            assert!(m.supply_infos().is_empty());
            assert!(m.health_factor().unwrap().is_zero());
        }
    }
}

// ------------------------------------------------------------ data

fn token_rows(name: &str, idx: &[&str]) -> AaveTokenData {
    AaveTokenData {
        name: name.into(),
        columns: REQUIRED_DATA_COLUMN.iter().map(|c| c.to_string()).collect(),
        rows: idx.iter().map(|i| status("0", "0", "0", i, i)).collect(),
    }
}

#[test]
fn unsorted_data_is_sorted_and_resamples() {
    // rows given out of order (python sorts nothing, but resample / the index need time order)
    let t = [ts(15, 0, 2), ts(15, 0, 0), ts(15, 0, 3), ts(15, 0, 1)];
    let data = AaveData::default()
        .with_token(token_rows("WETH", &["1.2", "1.0", "1.3", "1.1"]), &t)
        .unwrap();
    assert_eq!(
        data.ts,
        [ts(15, 0, 0), ts(15, 0, 1), ts(15, 0, 2), ts(15, 0, 3)]
    );
    assert_eq!(data.status(0, "WETH").unwrap().liquidity_index, d("1.0"));
    let r = data.resample(120).unwrap();
    assert_eq!(r.ts, [ts(15, 0, 0), ts(15, 0, 2)]);
    assert_eq!(r.status(1, "WETH").unwrap().liquidity_index, d("1.2"));
}

#[test]
fn tokens_are_outer_joined() {
    let data = AaveData::default()
        .with_token(
            token_rows("WETH", &["1", "2"]),
            &[ts(15, 0, 0), ts(15, 0, 1)],
        )
        .unwrap()
        .with_token(
            token_rows("USDC", &["3", "4"]),
            &[ts(15, 0, 1), ts(15, 0, 2)],
        )
        .unwrap();
    assert_eq!(data.ts, [ts(15, 0, 0), ts(15, 0, 1), ts(15, 0, 2)]);
    assert!(data.status(2, "WETH").is_err()); // missing (python NaN)
    assert_eq!(data.status(1, "USDC").unwrap().liquidity_index, d("3"));
    assert!(AaveData::default()
        .with_token(token_rows("WETH", &["1"]), &[ts(15, 0, 0)])
        .unwrap()
        .with_token(token_rows("WETH", &["1"]), &[ts(15, 0, 0)])
        .is_err());
}
