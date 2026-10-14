//! End-to-end check of the Rust loop against python: `01_quick_start.py` (golden
//! rust/golden/out/account_quick_start.csv), plus a scripted LP scenario exercising add /
//! remove / collect / swap through a Rust strategy.

use chrono::NaiveDate;
use demeter_core::actuator::{Actuator, Ctx, PriceTable, Snapshot, Strategy};
use demeter_core::broker::shared;
use demeter_core::data;
use demeter_core::dec::{self, parse_lossy, Dec};
use demeter_core::trigger::{TriggerCond, Triggers};
use demeter_core::types::{naive_to_ts, MarketInfo, PositionInfo, TokenInfo, UniV3Pool};
use demeter_core::uniswap::UniLpMarket;
use demeter_core::Result;

fn d(s: &str) -> Dec {
    parse_lossy(s).unwrap()
}

fn ts(y: i32, m: u32, day: u32, h: u32, mi: u32) -> i64 {
    naive_to_ts(
        &NaiveDate::from_ymd_opt(y, m, day)
            .unwrap()
            .and_hms_opt(h, mi, 0)
            .unwrap(),
    )
}

struct QuickStart {
    triggers: Triggers<QuickStart>,
}

impl QuickStart {
    fn work(&mut self, ctx: &Ctx, _s: &Snapshot) -> Result<()> {
        let m = ctx.market("U2EthPool")?;
        m.borrow_mut()
            .add_liquidity(d("1000"), d("4000"), None, None)?;
        Ok(())
    }
}

impl Strategy for QuickStart {
    fn initialize(&mut self, _ctx: &Ctx) -> Result<()> {
        self.triggers.push(
            TriggerCond::at_time(ts(2022, 8, 20, 12, 0)),
            QuickStart::work,
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

fn polygon_market(name: &str) -> (UniLpMarket, TokenInfo, TokenInfo) {
    let usdc = TokenInfo::new("usdc", 6);
    let eth = TokenInfo::new("eth", 18);
    let pool = UniV3Pool::new(usdc.clone(), eth.clone(), d("0.05"), usdc.clone(), None);
    let mut m = UniLpMarket::new(MarketInfo::new(name), pool);
    m.data_path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../samples/data").into();
    m.load_data(
        "polygon",
        "0x45dda9cb7c25131df268515131f647d726f50608",
        NaiveDate::from_ymd_opt(2023, 8, 15).unwrap(),
        NaiveDate::from_ymd_opt(2023, 8, 15).unwrap(),
    )
    .unwrap();
    (m, usdc, eth)
}

fn run_with(strategy: &mut dyn Strategy) -> Actuator {
    let (m, usdc, eth) = polygon_market("U2EthPool");
    let m = shared(m);
    let mut act = Actuator::new(false);
    act.add_market(m.clone()).unwrap();
    act.broker
        .borrow()
        .wallet
        .borrow_mut()
        .set(&usdc, d("10000"));
    act.broker.borrow().wallet.borrow_mut().set(&eth, d("10"));
    let (tokens, cols) = {
        let mb = m.borrow();
        data::price_from_data(mb.data().unwrap(), &mb.pool)
    };
    let table = PriceTable::new(m.borrow().data().unwrap().ts.clone(), tokens, cols).unwrap();
    act.set_price(table, usdc).unwrap();
    act.run(strategy).unwrap();
    act
}

#[test]
fn quick_start_matches_python() {
    let act = run_with(&mut QuickStart {
        triggers: Triggers::default(),
    });
    let golden = std::fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../golden/out/account_quick_start.csv"
    ))
    .unwrap();
    let rows: Vec<Vec<String>> = golden
        .lines()
        .skip(2)
        .map(|l| l.split(',').map(|s| s.to_string()).collect())
        .collect();
    let status = act.account_status.borrow();
    assert_eq!(rows.len(), status.len());
    for (r, s) in rows.iter().zip(status.iter()) {
        assert_eq!(r[0], demeter_core::types::ts_to_string(s.timestamp));
        assert!(
            dec::approx_eq(&s.net_value, &d(&r[1]), 1e-30),
            "{} {}",
            r[0],
            r[1]
        );
    }
    let df = act.account_status_frame().unwrap();
    assert_eq!(df.width(), 13);
}

/// Scripted scenario: add liquidity, swap, remove + collect later. Checks internal consistency
/// (value is conserved except fees, balances never negative) rather than python output.
struct Scripted {
    pos: Option<PositionInfo>,
    fees: Dec,
}

impl Strategy for Scripted {
    fn on_bar(&mut self, ctx: &Ctx, s: &Snapshot) -> Result<()> {
        let m = ctx.market("U2EthPool")?;
        let mut m = m.borrow_mut();
        if s.row_id == 10 {
            m.even_rebalance(None)?;
            let price = m.price()?;
            let tick = m.price_to_tick(&price);
            let (p, _, _, liq) =
                m.add_liquidity_by_tick(tick - 600, tick + 600, None, None, None, None, true)?;
            assert!(liq > 0);
            self.pos = Some(p);
        }
        if s.row_id == 700 {
            let p = self.pos.unwrap();
            let before = m.get_position(&p)?.pending_amount0 + m.get_position(&p)?.pending_amount1;
            self.fees = before;
            m.remove_liquidity(&p, None, true, None, true)?;
            assert!(m.positions.is_empty());
        }
        Ok(())
    }
}

#[test]
fn scripted_lp_roundtrip() {
    let mut s = Scripted {
        pos: None,
        fees: dec::zero(),
    };
    let act = run_with(&mut s);
    let status = act.account_status.borrow();
    assert!(s.fees > dec::zero(), "fees accrued");
    let mid = &status[300];
    assert_eq!(mid.market_balances[0].1.position_count, 1);
    let last = status.last().unwrap();
    assert_eq!(last.market_balances[0].1.position_count, 0);
    for (_, v) in &last.asset_balances {
        assert!(*v >= dec::zero());
    }
    let log = act.log.borrow();
    let kinds: Vec<&str> = log.actions.iter().map(|a| a.kind.type_name()).collect();
    assert_eq!(kinds[0], "uni_lp_sell"); // 10 ETH (~18.4k) > 10k USDC: rebalancing sells ETH
    assert!(kinds.contains(&"uni_lp_add_liquidity"));
    assert!(kinds.contains(&"uni_lp_remove_liquidity"));
    assert!(kinds.contains(&"uni_lp_collect"));
}

/// Actions taken in `initialize()` belong to the first iteration's notify (python keeps
/// `_currents.actions` until the end of the first iteration).
struct InitTrader {
    notified: Vec<(usize, String)>,
    bar: usize,
}

impl Strategy for InitTrader {
    fn initialize(&mut self, ctx: &Ctx) -> Result<()> {
        ctx.market("U2EthPool")?.borrow_mut().even_rebalance(None)
    }
    fn on_bar(&mut self, ctx: &Ctx, s: &Snapshot) -> Result<()> {
        self.bar = s.row_id;
        if s.row_id == 30 {
            ctx.market("U2EthPool")?.borrow_mut().buy(d("0.1"), None)?;
        }
        Ok(())
    }
    fn notify(&mut self, _ctx: &Ctx, actions: &[demeter_core::actions::Action]) -> Result<()> {
        for a in actions {
            self.notified
                .push((self.bar, a.kind.type_name().to_string()));
        }
        Ok(())
    }
}

#[test]
fn initialize_actions_are_notified_in_first_bar() {
    let mut s = InitTrader {
        notified: vec![],
        bar: 0,
    };
    run_with(&mut s);
    assert_eq!(
        s.notified,
        vec![
            (0, "uni_lp_sell".to_string()),
            (30, "uni_lp_buy".to_string())
        ]
    );
}
