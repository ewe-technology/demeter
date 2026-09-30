# EXP-006: half ladder — the base side stays spot, only the quote side is LP'd (v6.6)

- Version: v6.6
- Jira: [QUAN-840](https://ewetechnology.atlassian.net/browse/QUAN-840)
- Status: dropped-at-dev
- Pre-registration commit: 639a09c · Result commit: 53defd9

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

Development, ETH/USDC 0.05%, yearly reset:

| test | v6 | this | gain | max DD v6 → this | fees v6 → this |
|---|---|---|---|---|---|
| 2022 | +7.6% | +10.4% | +2.8 | 21.5% → 22.2% | $20.1k → $14.2k |
| 2023 | +32.2% | +32.4% | +0.2 | 13.9% → 15.8% | $23.3k → $2.5k |
| 2024 | +36.4% | +29.2% | −7.2 | 26.7% → 34.4% | $30.9k → $7.6k |
| 2025 | +16.3% | +40.4% | +24.1 | 26.9% → 28.9% | $20.8k → $9.9k |
| 2026-01..09-17 | +18.7% | +19.4% | +0.7 | 12.0% → 12.5% | $6.2k → $3.4k |

Wins 4/5, median gain +0.69 pts.

Continuous runs (daily equity):

| run | total | CAGR | max DD | Sharpe | Calmar |
|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | −22.8% | 0.73 | 0.61 |
| ETH this | +173.0% | 23.8% | **−28.9%** | 0.90 | 0.82 |
| WBTC/USDC v6 | +85.6% | 17.3% | −17.8% | 1.01 | 0.97 |
| WBTC/USDC this | +108.5% | 20.9% | −23.9% | 0.92 | 0.87 |

The upside-IL mechanism works (2025 +24 pts, continuous +87 pts), but the hypothesis that the downside is
"identical to v6" was wrong: v6's upper bands take profit on the way up, the spot base rides the whole move back
down until F or a range exit acts, so drawdowns from a peak are deeper (2024: 34.4% vs 26.7%). Fees fall by more
than half: after an up-exit rebuild the quote-side bands sit below the price and earn little while it keeps rising.

Verdict: **dropped at dev** — wins 4/5 and median +0.7 pts pass, continuous ETH max DD −28.9% misses the −27.8%
floor by 1.1 pts. Holdout not run. Best risk-adjusted numbers of the series so far (Sharpe 0.90, Calmar 0.82).

## Deviations

- Designed after EXP-001..005's dev results and the IL decomposition above (all dev data in-sample).
- The holdout pool's daily closes (other orientation) were looked at before EXP-001; see EXP-001 Deviations.
- Smoke tests before the pre-registration commit, outside every pre-registered window: ETH 2021-11-01..07 (F 1,
  rally week: LP holds only the 30k quote side, 70k spot; +5.17% vs v6 +5.38%, fees $4 vs $499) and 2021-05-10..06-30
  (crash: −32.0% vs −31.0%; price impact $2.4k vs $0.9k because exits sell the spot base in one market swap).
- `set_ladder_span` now records the span v6 would build at every build (was: the placed positions' bounds); for the
  REFILL_ORDER code path (EXP-005, already run) the two are the same ticks.
