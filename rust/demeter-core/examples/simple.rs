//! The minimal example from rust/GUIDE.md section 4.5 (kept compiling).
//!
//!     cargo run --release -p demeter-core --example simple   (run from rust/)

use chrono::NaiveDate;
use demeter_core::actuator::{Actuator, Ctx, PriceTable, Snapshot, Strategy};
use demeter_core::broker::shared;
use demeter_core::data;
use demeter_core::dec::{self, parse_lossy};
use demeter_core::trigger::{TriggerCond, Triggers};
use demeter_core::types::{naive_to_ts, MarketInfo, TokenInfo, UniV3Pool};
use demeter_core::uniswap::UniLpMarket;
use demeter_core::Result;

/// Put all funds in a ±10% range at the start, collect fees every day.
struct Simple {
    triggers: Triggers<Simple>,
    start: i64,
}

impl Simple {
    fn open(&mut self, ctx: &Ctx, _s: &Snapshot) -> Result<()> {
        let m = ctx.market("lp")?;
        let mut m = m.borrow_mut();
        m.even_rebalance(None)?;
        let p = m.price()?;
        let lower = p * parse_lossy("0.9").unwrap();
        let upper = p * parse_lossy("1.1").unwrap();
        m.add_liquidity(lower, upper, None, None)?;
        Ok(())
    }

    fn collect(&mut self, ctx: &Ctx, _s: &Snapshot) -> Result<()> {
        let m = ctx.market("lp")?;
        let mut m = m.borrow_mut();
        let keys: Vec<_> = m.positions.iter().map(|(k, _)| *k).collect();
        for k in keys {
            m.collect_fee(&k, None, None, false, true)?;
        }
        Ok(())
    }
}

impl Strategy for Simple {
    fn initialize(&mut self, _ctx: &Ctx) -> Result<()> {
        self.triggers.push(TriggerCond::at_time(self.start), Simple::open);
        self.triggers.push(TriggerCond::period(86_400, false, 0).unwrap(), Simple::collect);
        Ok(())
    }
    fn run_triggers(&mut self, ctx: &Ctx, s: &Snapshot) -> Result<()> {
        let mut t = std::mem::take(&mut self.triggers);
        let r = t.run(self, ctx, s);
        self.triggers = t;
        r
    }
}

fn main() -> Result<()> {
    let usdc = TokenInfo::new("usdc", 6);
    let eth = TokenInfo::new("eth", 18);
    let pool = UniV3Pool::new(usdc.clone(), eth.clone(), parse_lossy("0.05").unwrap(), usdc.clone(), None);
    let (start, end) = (NaiveDate::from_ymd_opt(2022, 1, 1).unwrap(), NaiveDate::from_ymd_opt(2022, 1, 31).unwrap());

    let mut market = UniLpMarket::new(MarketInfo::new("lp"), pool);
    market.data_path = "../samples/real-data/0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640".into();
    market.load_data("ethereum", "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", start, end)?;
    let market = shared(market);

    let mut actuator = Actuator::new(false);
    actuator.add_market(market.clone())?;
    actuator.broker.borrow().wallet.borrow_mut().set(&usdc, dec::from_i64(10_000));
    actuator.broker.borrow().wallet.borrow_mut().set(&eth, dec::zero());

    // price table from the pool (python: actuator.set_price(market.get_price_from_data()))
    let table = {
        let m = market.borrow();
        let d = m.data()?;
        let (tokens, cols) = data::price_from_data(d, &m.pool);
        PriceTable::new(d.ts.clone(), tokens, cols)?
    };
    actuator.set_price(table, usdc)?;

    let mut strategy = Simple { triggers: Triggers::default(), start: naive_to_ts(&start.and_hms_opt(0, 0, 0).unwrap()) };
    actuator.run(&mut strategy)?;

    let last = actuator.account_status.borrow().last().cloned().unwrap();
    println!("final net value: {} USDC", dec::to_plain_string(&last.net_value));
    // full per-minute history as a polars DataFrame (columns like "net_value|", "lp|net_value", "price|ETH")
    let df = actuator.account_status_frame()?;
    println!("{}", df.head(Some(3)));
    Ok(())
}
