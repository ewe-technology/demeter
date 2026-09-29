//! Actions (python `BaseAction` subclasses) and the shared log they are recorded into.

use crate::dec::Dec;
use crate::types::{MarketInfo, PositionInfo, Ts};

/// A number with a unit, python `UnitDecimal`.
#[derive(Clone, Debug)]
pub struct Ud {
    pub value: Dec,
    pub unit: String,
}

impl Ud {
    pub fn new(value: Dec, unit: &str) -> Self {
        Ud {
            value,
            unit: unit.to_string(),
        }
    }
}

#[derive(Clone, Debug)]
pub enum ActionKind {
    AddLiquidity {
        base_balance_after: Ud,
        quote_balance_after: Ud,
        base_amount_max: Ud,
        quote_amount_max: Ud,
        lower_quote_price: Ud,
        upper_quote_price: Ud,
        base_amount_actual: Ud,
        quote_amount_actual: Ud,
        position: PositionInfo,
        liquidity: u128,
    },
    RemoveLiquidity {
        base_balance_after: Ud,
        quote_balance_after: Ud,
        position: PositionInfo,
        base_amount: Ud,
        quote_amount: Ud,
        removed_liquidity: u128,
        remain_liquidity: u128,
    },
    CollectFee {
        base_balance_after: Ud,
        quote_balance_after: Ud,
        position: PositionInfo,
        base_amount: Ud,
        quote_amount: Ud,
    },
    Swap {
        amount: Ud,
        price: Ud,
        fee: Ud,
        to_amount: Ud,
    },
    Buy {
        base_balance_after: Ud,
        quote_balance_after: Ud,
        amount: Ud,
        price: Ud,
        fee: Ud,
        base_change: Ud,
        quote_change: Ud,
    },
    Sell {
        base_balance_after: Ud,
        quote_balance_after: Ud,
        amount: Ud,
        price: Ud,
        fee: Ud,
        base_change: Ud,
        quote_change: Ud,
    },
    BrokerSwap {
        from_token: String,
        from_amount: Ud,
        to_token: String,
        to_amount: Ud,
        fee_rate: Dec,
        fee: Ud,
    },
}

impl ActionKind {
    /// python `ActionTypeEnum` member name
    pub fn type_name(&self) -> &'static str {
        match self {
            ActionKind::AddLiquidity { .. } => "uni_lp_add_liquidity",
            ActionKind::RemoveLiquidity { .. } => "uni_lp_remove_liquidity",
            ActionKind::CollectFee { .. } => "uni_lp_collect",
            ActionKind::Swap { .. } => "uni_lp_swap",
            ActionKind::Buy { .. } => "uni_lp_buy",
            ActionKind::Sell { .. } => "uni_lp_sell",
            ActionKind::BrokerSwap { .. } => "general_swap",
        }
    }
}

#[derive(Clone, Debug)]
pub struct Action {
    pub market: MarketInfo,
    pub timestamp: Ts,
    pub comment: String,
    pub kind: ActionKind,
}

/// Log entry (python `DemeterLog`)
#[derive(Clone, Debug)]
pub struct LogEntry {
    pub time: Ts,
    pub message: String,
    pub level: i32,
}

/// Shared action recorder (python `Actuator._record_action_list` + `Currents`).
#[derive(Debug, Default)]
pub struct ActionLog {
    /// timestamp of the current iteration, stamped on every recorded action
    pub current_ts: Ts,
    pub actions: Vec<Action>,
    /// index into `actions` where the current iteration starts
    pub bar_start: usize,
    pub logs: Vec<LogEntry>,
}

impl ActionLog {
    pub fn record(&mut self, market: &MarketInfo, kind: ActionKind) {
        let message = format!(
            "{}({}): {}, ",
            market.name,
            market.kind.name(),
            kind.type_name()
        );
        self.logs.push(LogEntry {
            time: self.current_ts,
            message,
            level: 20,
        });
        self.actions.push(Action {
            market: market.clone(),
            timestamp: self.current_ts,
            comment: String::new(),
            kind,
        });
    }

    pub fn current_actions(&self) -> &[Action] {
        &self.actions[self.bar_start.min(self.actions.len())..]
    }

    pub fn start_bar(&mut self, ts: Ts) {
        self.current_ts = ts;
        self.bar_start = self.actions.len();
    }

    /// Set the timestamp stamped on new actions without starting a new "current bar" (python
    /// keeps `_currents.actions` from `initialize()` until the end of the first iteration).
    pub fn set_ts(&mut self, ts: Ts) {
        self.current_ts = ts;
    }

    /// End of an iteration: the next iteration's `current_actions` starts empty.
    pub fn end_bar(&mut self) {
        self.bar_start = self.actions.len();
    }

    /// python `comment_last_action`
    pub fn comment_last_action(&mut self, message: &str, type_name: Option<&str>) {
        match type_name {
            None => {
                if let Some(a) = self.actions.last_mut() {
                    a.comment = message.to_string();
                }
            }
            Some(t) => {
                if let Some(a) = self
                    .actions
                    .iter_mut()
                    .rev()
                    .find(|a| a.kind.type_name() == t)
                {
                    a.comment = message.to_string();
                }
            }
        }
    }
}
