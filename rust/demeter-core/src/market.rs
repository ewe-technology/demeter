//! The markets a broker can hold (python `Market` subclasses), dispatched by kind.

use crate::aave::{AavePrices, AaveV3Market};
use crate::actions::ActionLog;
use crate::actuator::PriceTable;
use crate::broker::{Shared, Wallet};
use crate::dec::Dec;
use crate::error::Result;
use crate::types::{AaveBalance, EngineCompat, MarketInfo, TokenInfo, Ts, UniLpBalance};
use crate::uniswap::UniLpMarket;
use std::rc::Rc;

/// A market added to the broker.
#[derive(Clone)]
pub enum Market {
    Uni(Shared<UniLpMarket>),
    Aave(Shared<AaveV3Market>),
}

impl From<Shared<UniLpMarket>> for Market {
    fn from(m: Shared<UniLpMarket>) -> Self {
        Market::Uni(m)
    }
}

impl From<Shared<AaveV3Market>> for Market {
    fn from(m: Shared<AaveV3Market>) -> Self {
        Market::Aave(m)
    }
}

/// Balance of one market in the account status (python `MarketBalance` subclasses).
#[derive(Clone, Debug)]
pub enum MarketBalance {
    Uni(UniLpBalance),
    Aave(AaveBalance),
}

impl MarketBalance {
    pub fn net_value(&self) -> Dec {
        match self {
            MarketBalance::Uni(b) => b.net_value,
            MarketBalance::Aave(b) => b.net_value,
        }
    }

    pub fn as_uni(&self) -> Option<&UniLpBalance> {
        match self {
            MarketBalance::Uni(b) => Some(b),
            _ => None,
        }
    }

    pub fn as_aave(&self) -> Option<&AaveBalance> {
        match self {
            MarketBalance::Aave(b) => Some(b),
            _ => None,
        }
    }
}

impl Market {
    pub fn info(&self) -> MarketInfo {
        match self {
            Market::Uni(m) => m.borrow().info.clone(),
            Market::Aave(m) => m.borrow().info.clone(),
        }
    }

    pub fn as_uni(&self) -> Option<&Shared<UniLpMarket>> {
        match self {
            Market::Uni(m) => Some(m),
            _ => None,
        }
    }

    pub fn as_aave(&self) -> Option<&Shared<AaveV3Market>> {
        match self {
            Market::Aave(m) => Some(m),
            _ => None,
        }
    }

    /// python `market.quote_token`: the pool quote token, USD for aave
    pub fn quote_token(&self) -> TokenInfo {
        match self {
            Market::Uni(m) => m.borrow().pool.quote_token.clone(),
            Market::Aave(m) => m.borrow().quote_token.clone(),
        }
    }

    pub(crate) fn attach(&self, wallet: Shared<Wallet>, log: Shared<ActionLog>) {
        match self {
            Market::Uni(m) => m.borrow_mut().attach(wallet, log),
            Market::Aave(m) => m.borrow_mut().attach(wallet, log),
        }
    }

    pub fn set_compat(&self, compat: EngineCompat) {
        match self {
            Market::Uni(m) => m.borrow_mut().compat = compat,
            Market::Aave(m) => m.borrow_mut().compat = compat,
        }
    }

    pub fn has_update(&self) -> bool {
        match self {
            Market::Uni(m) => m.borrow().has_update,
            Market::Aave(m) => m.borrow().has_update,
        }
    }

    /// python `__set_market_snapshot` for one market. The aave market also takes the prices of
    /// this row, converted to its quote token (USD) when the broker is quoted in another token.
    pub fn set_market_status(
        &self,
        ts: Ts,
        prices: &Rc<PriceTable>,
        price_row: usize,
        broker_quote: &TokenInfo,
    ) -> Result<()> {
        match self {
            Market::Uni(m) => m.borrow_mut().set_market_status(ts),
            Market::Aave(m) => {
                let mut m = m.borrow_mut();
                let factor = if *broker_quote == m.quote_token {
                    None
                } else {
                    Some((
                        prices.get(price_row, &broker_quote.name)?,
                        prices.get(price_row, &m.quote_token.name)?,
                    ))
                };
                let p = AavePrices::Table {
                    table: prices.clone(),
                    row: price_row,
                    factor,
                };
                m.set_market_status(ts, p)
            }
        }
    }

    pub fn update(&self) -> Result<()> {
        match self {
            Market::Uni(m) => m.borrow_mut().update(),
            Market::Aave(m) => m.borrow_mut().update(),
        }
    }

    pub fn get_market_balance(&self) -> Result<MarketBalance> {
        Ok(match self {
            Market::Uni(m) => MarketBalance::Uni(m.borrow().get_market_balance()?),
            Market::Aave(m) => MarketBalance::Aave(m.borrow().get_market_balance()?),
        })
    }

    pub fn check_market(&self) -> Result<()> {
        match self {
            Market::Uni(m) => m.borrow().check_market(),
            Market::Aave(m) => m.borrow().check_market(),
        }
    }

    /// timestamps of the market data
    pub fn timestamps(&self) -> Result<Vec<Ts>> {
        Ok(match self {
            Market::Uni(m) => m.borrow().data()?.ts.clone(),
            Market::Aave(m) => m.borrow().data()?.ts.clone(),
        })
    }

    pub fn data_len(&self) -> Result<usize> {
        Ok(match self {
            Market::Uni(m) => m.borrow().data()?.len(),
            Market::Aave(m) => m.borrow().data()?.len(),
        })
    }

    /// (first, last) timestamp of the market data
    pub fn data_range(&self) -> Result<(Option<Ts>, Option<Ts>)> {
        let ts = |v: &[Ts]| (v.first().copied(), v.last().copied());
        Ok(match self {
            Market::Uni(m) => ts(&m.borrow().data()?.ts),
            Market::Aave(m) => ts(&m.borrow().data()?.ts),
        })
    }

    pub fn resample(&self, interval_secs: i64) -> Result<()> {
        match self {
            Market::Uni(m) => m.borrow_mut().resample(interval_secs),
            Market::Aave(m) => m.borrow_mut().resample(interval_secs),
        }
    }
}
