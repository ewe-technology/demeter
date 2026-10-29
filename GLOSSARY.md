# Uniswap LP strategy research

Backtesting and validating the team's Uniswap v3 LP strategies (ETH-USDC MGL, ETH-cbBTC MGL, defense v6) before any of
them goes live.

## Validation

**Validation layer**:
One rung of Maker's 11-rung ladder of checks a strategy must pass before deployment, numbered L0 (plain backtest) to
L10 (6-12 months of paper trading). The rungs are L0 backtest, L1 walk-forward, L2 MCPT, L3 block bootstrap,
L4 multiple-testing correction, L5 out-of-sample, L6 regime split, L7 combinatorial purged CV, L8 probabilistic Sharpe,
L9 reality check, L10 paper trading.
_Avoid_: method (the old 1-5 numbering of `strategy_validation.py`), level, test

**Scorecard**:
The per-layer pass / fail table for one strategy on one pool.
_Avoid_: report, verdict table

## Accounting

**Reward valuation**:
How claimed LP fees that are not reinvested are priced in the net value: *fixed* (in the unit token on the claim day,
as the specs do) or *marked* (held as tokens and marked to market each day). The two give different drawdowns.
_Avoid_: fee accounting, reward mode
