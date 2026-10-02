//! Wallet (python `Broker.assets` + `Asset`), broker and account status.

use crate::aave::AaveV3Market;
use crate::actions::{ActionKind, ActionLog, Ud};
use crate::dec::{self, Dec};
use crate::error::{require, DemeterError, Result};
use crate::market::{Market, MarketBalance};
use crate::types::{MarketInfo, MarketType, TokenInfo, Ts};
use crate::uniswap::UniLpMarket;
use std::cell::RefCell;
use std::rc::Rc;

pub type Shared<T> = Rc<RefCell<T>>;

pub fn shared<T>(v: T) -> Shared<T> {
    Rc::new(RefCell::new(v))
}

/// Token balances held by the broker. Insertion ordered like the python dict.
#[derive(Debug, Default)]
pub struct Wallet {
    pub assets: Vec<(TokenInfo, Dec)>,
    pub allow_negative_balance: bool,
}

impl Wallet {
    pub fn new(allow_negative_balance: bool) -> Self {
        Wallet {
            assets: vec![],
            allow_negative_balance,
        }
    }

    fn idx(&self, token: &TokenInfo) -> Option<usize> {
        self.assets.iter().position(|(t, _)| t == token)
    }

    pub fn contains(&self, token: &TokenInfo) -> bool {
        self.idx(token).is_some()
    }

    /// python `get_token_balance`: DemeterError if the token was never set.
    pub fn balance(&self, token: &TokenInfo) -> Result<Dec> {
        self.idx(token).map(|i| self.assets[i].1).ok_or_else(|| {
            DemeterError::demeter(format!("{} doesn't exist in assets dict", token.name))
        })
    }

    /// python `set_balance`: replaces the asset (keeps its position in the dict).
    pub fn set(&mut self, token: &TokenInfo, amount: Dec) {
        match self.idx(token) {
            Some(i) => self.assets[i] = (token.clone(), amount),
            None => self.assets.push((token.clone(), amount)),
        }
    }

    /// python `add_to_balance`
    pub fn add(&mut self, token: &TokenInfo, amount: Dec) {
        match self.idx(token) {
            Some(i) => self.assets[i].1 += amount,
            None => self.assets.push((token.clone(), amount)),
        }
    }

    /// python `subtract_from_balance` / `Asset.sub`.
    ///
    /// If the balance and the amount differ by less than 0.001% the balance becomes exactly 0,
    /// absorbing rounding noise from the liquidity math.
    pub fn sub(&mut self, token: &TokenInfo, amount: Dec) -> Result<()> {
        let allow_negative = self.allow_negative_balance;
        let i = match self.idx(token) {
            Some(i) => i,
            None => {
                if allow_negative {
                    self.assets.push((token.clone(), dec::zero() - amount));
                    return Ok(());
                }
                return Err(DemeterError::demeter(format!(
                    "{} doesn't exist in assets dict",
                    token.name
                )));
            }
        };
        let balance = self.assets[i].1;
        let base = if !balance.is_zero() { balance } else { amount };
        if base.is_zero() {
            return Ok(());
        }
        if allow_negative {
            self.assets[i].1 = balance - amount;
            return Ok(());
        }
        // python compares with the float 0.00001
        let threshold = dec::from_f64_exact(0.00001);
        if ((balance - amount) / base).abs() < threshold {
            self.assets[i].1 = dec::zero();
        } else if balance - amount < dec::zero() {
            return Err(DemeterError::assertion(format!(
                "insufficient balance, balance is {}{}, but sub amount is {}{}",
                dec::to_plain_string(&balance),
                token.name,
                dec::to_plain_string(&amount),
                token.name
            )));
        } else {
            self.assets[i].1 = balance - amount;
        }
        Ok(())
    }
}

/// Account status of one iteration (python `AccountStatus`).
#[derive(Clone, Debug)]
pub struct AccountRow {
    pub timestamp: Ts,
    pub net_value: Dec,
    pub asset_value: Dec,
    pub asset_balances: Vec<(TokenInfo, Dec)>,
    pub market_balances: Vec<(MarketInfo, MarketBalance)>,
}

/// Broker: owns the wallet and the markets. Python `Broker`.
pub struct Broker {
    pub wallet: Shared<Wallet>,
    pub log: Shared<ActionLog>,
    pub markets: Vec<(MarketInfo, Market)>,
    pub quote_token: Option<TokenInfo>,
}

impl Broker {
    pub fn new(allow_negative_balance: bool, log: Shared<ActionLog>) -> Self {
        Broker {
            wallet: shared(Wallet::new(allow_negative_balance)),
            log,
            markets: vec![],
            quote_token: None,
        }
    }

    /// python `add_market`
    pub fn add_market(&mut self, market: impl Into<Market>) -> Result<()> {
        let market = market.into();
        let info = market.info();
        if self.markets.iter().any(|(k, _)| *k == info) {
            return Err(DemeterError::demeter("market has exist"));
        }
        market.attach(self.wallet.clone(), self.log.clone());
        self.markets.push((info, market));
        Ok(())
    }

    /// The market with this key, of any kind.
    pub fn get(&self, info: &MarketInfo) -> Option<Market> {
        self.markets
            .iter()
            .find(|(k, _)| k == info)
            .map(|(_, m)| m.clone())
    }

    /// The market with this name, of any kind.
    pub fn get_by_name(&self, name: &str) -> Option<Market> {
        self.markets
            .iter()
            .find(|(k, _)| k.name == name)
            .map(|(_, m)| m.clone())
    }

    /// The uniswap market with this key.
    pub fn market(&self, info: &MarketInfo) -> Option<Shared<UniLpMarket>> {
        self.get(info).and_then(|m| m.as_uni().cloned())
    }

    /// The uniswap market with this name.
    pub fn market_by_name(&self, name: &str) -> Option<Shared<UniLpMarket>> {
        self.get_by_name(name).and_then(|m| m.as_uni().cloned())
    }

    /// The aave market with this name.
    pub fn aave_by_name(&self, name: &str) -> Option<Shared<AaveV3Market>> {
        self.get_by_name(name).and_then(|m| m.as_aave().cloned())
    }

    /// python `markets.default`: the first market added.
    pub fn default_market(&self) -> Option<Market> {
        self.markets.first().map(|(_, m)| m.clone())
    }

    /// python `check_backtest`
    pub fn check_backtest(&self) -> Result<()> {
        require(!self.markets.is_empty(), "No market assigned")?;
        for (_, m) in &self.markets {
            m.check_market()?;
        }
        require(self.quote_token.is_some(), "Quote token of broker not set")
    }

    /// python `get_account_status`. `price_of(token_name)` returns the price in the broker quote.
    pub fn get_account_status(
        &self,
        price_of: &dyn Fn(&str) -> Result<Dec>,
        ts: Ts,
    ) -> Result<AccountRow> {
        let quote = self
            .quote_token
            .clone()
            .ok_or_else(|| DemeterError::assertion("Quote token of broker not set"))?;
        let mut market_sum = dec::zero();
        let mut market_balances = Vec::with_capacity(self.markets.len());
        for (info, m) in &self.markets {
            let bal = m.get_market_balance()?;
            let market_quote = m.quote_token();
            if market_quote == quote {
                market_sum += bal.net_value();
            } else {
                market_sum +=
                    bal.net_value() * price_of(&market_quote.name)? / price_of(&quote.name)?;
            }
            market_balances.push((info.clone(), bal));
        }
        let wallet = self.wallet.borrow();
        let mut asset_sum = dec::zero();
        for (t, v) in &wallet.assets {
            asset_sum += *v * price_of(&t.name)?;
        }
        Ok(AccountRow {
            timestamp: ts,
            net_value: asset_sum + market_sum,
            asset_value: asset_sum,
            asset_balances: wallet.assets.clone(),
            market_balances,
        })
    }

    /// python `swap_by_from`
    pub fn swap_by_from(
        &self,
        from_token: &TokenInfo,
        to_token: &TokenInfo,
        amount: Dec,
        from_price: Dec,
        to_price: Dec,
        fee_rate: Dec,
    ) -> Result<()> {
        require(
            fee_rate >= dec::zero() && fee_rate < dec::one(),
            "fee rate out of range",
        )?;
        let from_value_without_fee = amount * from_price * (dec::one() - fee_rate);
        let to_amount = from_value_without_fee / to_price;
        self.wallet.borrow_mut().sub(from_token, amount)?;
        self.wallet.borrow_mut().add(to_token, to_amount);
        self.record_broker_swap(
            from_token,
            amount,
            to_token,
            to_amount,
            fee_rate,
            amount * fee_rate,
        );
        Ok(())
    }

    /// python `swap_by_to`
    pub fn swap_by_to(
        &self,
        from_token: &TokenInfo,
        to_token: &TokenInfo,
        amount: Dec,
        from_price: Dec,
        to_price: Dec,
        fee_rate: Dec,
    ) -> Result<()> {
        require(
            fee_rate >= dec::zero() && fee_rate < dec::one(),
            "fee rate out of range",
        )?;
        let to_value_with_fee = amount * to_price / (dec::one() - fee_rate);
        let from_amount = to_value_with_fee / from_price;
        self.wallet.borrow_mut().sub(from_token, from_amount)?;
        self.wallet.borrow_mut().add(to_token, amount);
        self.record_broker_swap(
            from_token,
            from_amount,
            to_token,
            amount,
            fee_rate,
            from_amount * fee_rate,
        );
        Ok(())
    }

    fn record_broker_swap(
        &self,
        from: &TokenInfo,
        from_amount: Dec,
        to: &TokenInfo,
        to_amount: Dec,
        fee_rate: Dec,
        fee: Dec,
    ) {
        let market = MarketInfo {
            name: "broker".into(),
            kind: MarketType::Broker,
        };
        self.log.borrow_mut().record(
            &market,
            ActionKind::BrokerSwap {
                from_token: from.name.clone(),
                from_amount: Ud::new(from_amount, &from.name),
                to_token: to.name.clone(),
                to_amount: Ud::new(to_amount, &to.name),
                fee_rate,
                fee: Ud::new(fee, &from.name),
            },
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn d(s: &str) -> Dec {
        dec::parse_lossy(s).unwrap()
    }

    #[test]
    fn sub_rules() {
        let usdc = TokenInfo::new("usdc", 6);
        let mut w = Wallet::new(false);
        w.set(&usdc, d("100"));
        w.sub(&usdc, d("99.99999")).unwrap(); // within 0.001%: becomes exactly zero
        assert!(w.balance(&usdc).unwrap().is_zero());
        w.set(&usdc, d("100"));
        assert!(w.sub(&usdc, d("101")).is_err());
        w.sub(&usdc, d("40")).unwrap();
        assert_eq!(w.balance(&usdc).unwrap(), d("60"));
        let eth = TokenInfo::new("eth", 18);
        assert!(w.sub(&eth, d("1")).is_err());
        w.sub(&usdc, d("0")).unwrap();
        let mut neg = Wallet::new(true);
        neg.sub(&eth, d("1")).unwrap();
        assert_eq!(neg.balance(&eth).unwrap(), d("-1"));
    }
}
