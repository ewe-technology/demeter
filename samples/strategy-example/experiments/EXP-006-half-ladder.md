# EXP-006: half ladder — the base side stays spot, only the quote side is LP'd (v6.6)

- Version: v6.6
- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______

## Hypothesis

A segment-by-segment decomposition of v6's continuous ETH run (each ladder from its build to the next rebuild;
EXP-000 ledger, `result_A_v6.csv`) shows where the principal goes. Total IL against holding the placed tokens is
−$101k, fees +$86k:

| segment ends with | n | IL | fees |
|---|---|---|---|
| range exit upward | 14 | −$75.5k | $39.4k |
| F follow | 103 | −$14.4k | $40.9k |
| range exit downward | 5 | −$11.4k | $5.9k |

Three quarters of the IL comes from rallies that run through the ladder: the bands above the price sell all their
ETH on the way up (a covered call) and the upward exit then rebuilds and buys ETH back at the top. On the way down
the bands above the price are all ETH anyway, i.e. they behave like spot. So holding that ETH as spot instead of
LP'ing it above the price should keep the downside identical to v6, remove the upside IL, and give up only the fees
the upper bands earn while a rally passes through them. v6's ETH share at build (s x F) is unchanged.

## Change

`HALF_LADDER = True` (v6: False):

- Every (re)build swaps to v6's target (s x F of equity in base, (1 − s) x F in quote, reserve (1 − F) in quote)
  and places only the ladder's quote-side bands (the lower half in ETH price, v6's own band shares); the base stays
  in the account as spot.
- Range exits are judged on the full ±20% span v6 would have built at that price (the placed bands cover only the
  lower half).
- F follow: deployed = (LP value + spot base value) / equity, v6's thresholds.
- No new constant. Everything else identical to v6 (engine, s rule, width, shape, costs).

## Pre-registration

- Development data (in-sample): ETH/USDC 0.05% yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 (yearly
  reset, 100,000 USDC); continuous ETH 2022-01-01..2026-09-17 and WBTC/USDC 0.3% 2022-11-01..2026-09-17 reported.
  v6 (A) and this (G) in the same invocation.
- Holdout (run once, v6 + this only): WBTC/WETH 0.05% mainnet (`0x4585fe77…`), ETH base, WBTC quote, 2 WBTC,
  yearly segments 2023, 2024, 2025, 2026-01-01..09-17 plus the continuous 2022-11-01..2026-09-17 (reported).
  No strategy run has touched this pool (EXP-001..003, 005 dropped at dev; EXP-004 uses Base).
- Success rule (as EXP-001..005, against v6):
  - Dev: wins in ≥ 3 of 5 ETH segments, median gain > 0 pts, and continuous ETH max DD (daily equity) ≥ −27.8%.
    Otherwise `dropped-at-dev`.
  - Holdout: wins in ≥ 3 of 4 segments and median gain > 0 pts → `holdout-pass`, else `holdout-fail`.

## Result

| test | v6 | this | gain |
|---|---|---|---|

Verdict:

## Deviations

- Designed after EXP-001..005's dev results and the IL decomposition above (all dev data in-sample).
- The holdout pool's daily closes (other orientation) were looked at before EXP-001; see EXP-001 Deviations.
- Smoke tests before the pre-registration commit, outside every pre-registered window: ETH 2021-11-01..07 (F 1,
  rally week: LP holds only the 30k quote side, 70k spot; +5.17% vs v6 +5.38%, fees $4 vs $499) and 2021-05-10..06-30
  (crash: −32.0% vs −31.0%; price impact $2.4k vs $0.9k because exits sell the spot base in one market swap).
- `set_ladder_span` now records the span v6 would build at every build (was: the placed positions' bounds); for the
  REFILL_ORDER code path (EXP-005, already run) the two are the same ticks.
