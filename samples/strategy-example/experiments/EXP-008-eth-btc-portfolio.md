# EXP-008: v6 on ETH and BTC as one 50/50 portfolio (v6.8)

- Version: v6.8
- Jira: QUAN-___
- Status: dev-done (dev seen before registration; forward holdout pending)
- Pre-registration commit: ______ · Result commit: ______

## Hypothesis

EXP-001..007 show that every way of getting more out of F on one asset (spot sleeve, half ladder) raises the
drawdown past the 5-pt budget, and that v6's LP layer nets roughly zero (fees ≈ IL). Drawdown can instead be
cut by diversification: v6's daily returns on ETH/USDC and WBTC/USDC correlate 0.67, so two independent v6 books
split 50/50 should keep the return and lower the drawdown and volatility. v6 showed no edge over the plain LP on
BTC (`V6_VALIDATION.md` §4), but it did cut BTC's drawdown, which is what a portfolio needs from it.

## Change

Two v6 books, unchanged: ETH/USDC 0.05% and WBTC/USDC 0.3%, each started with half the capital, daily equity
combined as a 50/50 portfolio rebalanced daily (between two USDC-denominated vaults this is a USDC transfer; its
cost is not modelled). No change to v6 itself.

## Pre-registration

- Development data: **already seen** — computed from the continuous runs of EXP-004's invocation
  (`0x88e6-opt-AE-2022-01-01-2026-09-17`, `0x99ac-opt-AE-2022-11-01-2026-09-17`), common window 2022-11-01..2026-09-17:

  | book | total | CAGR | max DD | Sharpe | Calmar |
  |---|---|---|---|---|---|
  | v6 ETH | +65.7% | 13.9% | −22.8% | 0.78 | 0.61 |
  | v6 BTC | +87.1% | 17.5% | −17.8% | 1.02 | 0.98 |
  | 50/50 | +78.0% | 16.0% | −18.7% | 0.98 | 0.86 |

  The same combination of EXP-001/004/006/007's variants was computed at the same time (v6.4 cash 50/50: Sharpe
  1.10, max DD −17.0%; v6.1 50/50: +147%, −27.6%; v6.6 50/50: +128%, −25.2%).
- Holdout (fresh, run once): **forward data** 2026-09-18..2026-12-31 on both pools (fetched with
  `samples/fetch_uni_minute.py` in January 2027), v6 ETH alone vs the 50/50 portfolio, continuous from
  2022-11-01 so the engine and books carry over.
- Success rule on the holdout window: the portfolio's max DD shallower than v6 ETH's and its daily-return Sharpe
  ≥ v6 ETH's − 0.1 → `holdout-pass`, else `holdout-fail`. (Three months is short; the rule only guards against the
  diversification benefit disappearing, not for statistical significance.)

## Result

Verdict: pending forward holdout.

## Deviations

- Not a clean pre-registration: the development numbers above were computed before this file (exploration after
  EXP-007). Only the forward holdout is untouched.
