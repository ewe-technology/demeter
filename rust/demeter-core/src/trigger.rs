//! Built-in trigger conditions (python `demeter/strategy/trigger.py`), evaluated natively.
//!
//! A condition only answers "does it fire at this timestamp"; what to do when it fires is up to
//! the caller (a Rust closure via [`Triggers`], or a python callable in the bindings).

use crate::types::Ts;

/// python `to_minute`: drop seconds.
pub fn to_minute(ts: Ts) -> Ts {
    ts - ts.rem_euclid(60)
}

#[derive(Clone, Debug)]
pub enum TriggerCond {
    /// `AtTimeTrigger`
    AtTime { time: Ts },
    /// `AtTimesTrigger` (the python version raises TypeError; this one works as documented)
    AtTimes { times: Vec<Ts> },
    /// `TimeRangeTrigger`, end excluded
    TimeRange { start: Ts, end: Ts },
    /// `TimeRangesTrigger`
    TimeRanges { ranges: Vec<(Ts, Ts)> },
    /// `PeriodTrigger`
    Period {
        delta: i64,
        pending: i64,
        trigger_immediately: bool,
        next: Option<Ts>,
    },
    /// `PeriodsTrigger`
    Periods {
        deltas: Vec<i64>,
        pending: i64,
        trigger_immediately: bool,
        next: Option<Vec<Ts>>,
    },
    /// never fires (python base `Trigger`)
    Never,
}

impl TriggerCond {
    pub fn at_time(time: Ts) -> Self {
        TriggerCond::AtTime {
            time: to_minute(time),
        }
    }
    pub fn at_times(times: &[Ts]) -> Self {
        TriggerCond::AtTimes {
            times: times.iter().map(|t| to_minute(*t)).collect(),
        }
    }
    pub fn time_range(start: Ts, end: Ts) -> Self {
        TriggerCond::TimeRange {
            start: to_minute(start),
            end: to_minute(end),
        }
    }
    pub fn time_ranges(ranges: &[(Ts, Ts)]) -> Self {
        TriggerCond::TimeRanges {
            ranges: ranges
                .iter()
                .map(|(s, e)| (to_minute(*s), to_minute(*e)))
                .collect(),
        }
    }
    /// `delta` and `pending` in seconds; delta must be a whole number of minutes.
    pub fn period(delta: i64, trigger_immediately: bool, pending: i64) -> Result<Self, String> {
        if delta % 60 != 0 {
            return Err("min time span is 1 minute".into());
        }
        Ok(TriggerCond::Period {
            delta,
            pending,
            trigger_immediately,
            next: None,
        })
    }
    pub fn periods(
        deltas: &[i64],
        trigger_immediately: bool,
        pending: i64,
    ) -> Result<Self, String> {
        if deltas.iter().any(|d| d % 60 != 0) {
            return Err("min time span is 1 minute".into());
        }
        Ok(TriggerCond::Periods {
            deltas: deltas.to_vec(),
            pending,
            trigger_immediately,
            next: None,
        })
    }

    /// python `when(snapshot)`.
    ///
    /// `legacy == true`: periodic triggers need an exact timestamp match (python behaviour; a
    /// gap in the data stops them forever, QUIRK 7). `legacy == false`: they fire on the first
    /// timestamp at or after the scheduled one and then reschedule past it.
    pub fn when(&mut self, ts: Ts, legacy: bool) -> bool {
        match self {
            TriggerCond::AtTime { time } => ts == *time,
            TriggerCond::AtTimes { times } => times.contains(&ts),
            TriggerCond::TimeRange { start, end } => *start <= ts && ts < *end,
            TriggerCond::TimeRanges { ranges } => ranges.iter().any(|(s, e)| *s <= ts && ts < *e),
            TriggerCond::Period {
                delta,
                pending,
                trigger_immediately,
                next,
            } => match next {
                None => {
                    *next = Some(ts + *delta + *pending);
                    *trigger_immediately
                }
                Some(n) => {
                    if *n == ts || (!legacy && ts >= *n) {
                        let mut v = *n + *delta;
                        if !legacy {
                            while v <= ts {
                                v += *delta;
                            }
                        }
                        *next = Some(v);
                        true
                    } else {
                        false
                    }
                }
            },
            TriggerCond::Periods {
                deltas,
                pending,
                trigger_immediately,
                next,
            } => match next {
                None => {
                    *next = Some(deltas.iter().map(|d| ts + d + *pending).collect());
                    *trigger_immediately
                }
                Some(ns) => {
                    for (i, n) in ns.iter_mut().enumerate() {
                        if *n == ts || (!legacy && ts >= *n) {
                            *n += deltas[i];
                            if !legacy {
                                while *n <= ts {
                                    *n += deltas[i];
                                }
                            }
                            return true;
                        }
                    }
                    false
                }
            },
            TriggerCond::Never => false,
        }
    }

    /// python `is_out_date(t)`: the trigger can be dropped.
    pub fn is_out_date(&self, ts: Ts) -> bool {
        match self {
            TriggerCond::AtTime { time } => ts >= *time,
            TriggerCond::AtTimes { times } => times.iter().max().map(|m| ts >= *m).unwrap_or(true),
            TriggerCond::TimeRange { end, .. } => ts >= *end,
            TriggerCond::TimeRanges { ranges } => ranges
                .iter()
                .map(|(_, e)| *e)
                .max()
                .map(|m| ts >= m)
                .unwrap_or(true),
            _ => false,
        }
    }

    /// python `reset()` of the periodic triggers
    pub fn reset(&mut self) {
        match self {
            TriggerCond::Period { next, .. } => *next = None,
            TriggerCond::Periods { next, .. } => *next = None,
            _ => {}
        }
    }
}

/// A list of (condition, action) pairs for Rust strategies.
///
/// ```ignore
/// let mut triggers = std::mem::take(&mut self.triggers);
/// triggers.run(self, ctx, snapshot)?;
/// self.triggers = triggers;
/// ```
pub struct Triggers<S> {
    #[allow(clippy::type_complexity)]
    pub items: Vec<(
        TriggerCond,
        fn(&mut S, &crate::actuator::Ctx, &crate::actuator::Snapshot) -> crate::Result<()>,
    )>,
}

impl<S> Default for Triggers<S> {
    fn default() -> Self {
        Triggers { items: vec![] }
    }
}

impl<S> Triggers<S> {
    pub fn push(
        &mut self,
        cond: TriggerCond,
        action: fn(&mut S, &crate::actuator::Ctx, &crate::actuator::Snapshot) -> crate::Result<()>,
    ) {
        self.items.push((cond, action));
    }

    /// Evaluate every trigger, run the ones that fire, then drop outdated ones (python order).
    pub fn run(
        &mut self,
        strategy: &mut S,
        ctx: &crate::actuator::Ctx,
        snapshot: &crate::actuator::Snapshot,
    ) -> crate::Result<()> {
        let legacy = ctx.compat.legacy_quirks;
        for (cond, action) in self.items.iter_mut() {
            if cond.when(snapshot.ts, legacy) {
                action(strategy, ctx, snapshot)?;
            }
        }
        self.items.retain(|(c, _)| !c.is_out_date(snapshot.ts));
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn period_exact_match() {
        let mut p = TriggerCond::period(3600, false, 0).unwrap();
        assert!(!p.when(0, true));
        assert!(!p.when(1800, true));
        assert!(p.when(3600, true));
        // gap: 7200 missing -> legacy never fires again
        assert!(!p.when(7260, true));
        assert!(!p.when(10800, true));
        let mut f = TriggerCond::period(3600, false, 0).unwrap();
        f.when(0, false);
        assert!(f.when(3600, false));
        assert!(f.when(7260, false)); // catches up
        assert!(!f.when(7320, false));
        assert!(f.when(10800, false));
    }

    #[test]
    fn at_time() {
        let mut t = TriggerCond::at_time(125);
        assert!(!t.when(60, true));
        assert!(t.when(120, true));
        assert!(t.is_out_date(120));
        assert!(!t.is_out_date(60));
    }
}
