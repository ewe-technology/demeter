# EXP-060: scheduled FOMC / CPI pause with an exact restore of the ladder (v6.47)

- Jira: QUAN-942
- Status: holdout-fail
- Pre-registration commit: 1ac1ba4 · Result commit: c4f9b71
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

Same hypothesis as EXP-059: LVR is concentrated in jumps, FOMC statements and CPI releases are the largest scheduled jumps,
so pulling the ladder over them (30 min before to 2 h after, no swap at the pull) avoids the arbitrage of the repricing at
the cost of ~50 hours of fees a year. EXP-059 could not test it cleanly: its re-add put the pulled tokens back at the old
ticks without a swap, the moved price left part of the book idle, and the next daily follow check rebuilt the whole ladder
after almost every event (ETH 287 rebuilds vs 147, WBTC 241 vs 106). With that confound the ETH result was already better
than v6 (CAGR 15.8% vs 14.0%, Calmar 0.71 vs 0.61) and the WBTC result worse (extra 0.3% swaps and recentres). Restoring each
band's exact pre-pause liquidity with one net swap removes the extra rebuilds; what remains is the pause itself.

## Change

`MACRO_EVENTS = "csv"`, `MACRO_RESTORE = True` (variant `AW`): EXP-059's schedule and pull. At the re-add (2 h after the
release) every band's token amounts for its pre-pause liquidity at the current price are computed; one swap (pool fee and
price impact charged) turns the surplus token that came out into the missing one, using only the tokens that came out
(not the (1 − F) reserve, not the paid-out fees); the bands are minted at the same ticks with that liquidity (scaled down
pro rata by what the swap fee took). Constants as in EXP-059 (30 min, 2 h); no new constant.

## Pre-registration

Pre-registered alone and run in the same invocations as `A` (v6).

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev windows,
  warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC 0.3%
  2022-01-01..2022-10-31. v6's numbers there are known (EXP-040..052); neither EXP-059 nor this variant ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

Development (`A` and the variant in each invocation, tag `AAW`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +6.8% | -0.8 |
| 2023 | +32.2% | +32.6% | +0.4 |
| 2024 | +36.4% | +37.6% | +1.2 |
| 2025 | +16.3% | +16.4% | +0.1 |
| 2026-01..09-17 | +18.7% | +18.8% | +0.1 |

Wins 4/5, median +0.11 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +87.0% | 14.2% | -23.0% | 0.73 | 0.62 | $84.8k | $0.31k | 279 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +87.2% | 17.6% | -17.6% | 1.02 | 1.00 | $61.5k | $0.72k | 234 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +5.0% | 7.8% | -30.6% | 0.39 | 0.25 | $21.3k | $3.69k | 59 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +2.3% | 2.8% | -12.5% | 0.23 | 0.22 | $13.8k | $0.04k | 40 |

Verdict: **holdout-fail** — dev passed the improvement rule by small margins (ETH CAGR 14.2% vs 14.0%, Calmar 0.62 vs 0.61, max DD −23.0% vs −22.8%, wins 4/5; WBTC CAGR 17.6% vs 17.3%, Calmar 1.00 vs 0.97, max DD −17.6% vs −17.8%). Time-split holdout: H5 ETH 2021 wins (CAGR 7.8% vs 7.0%, Calmar 0.25 vs 0.23), H4 WBTC 2022 loses narrowly (CAGR 2.8% vs 2.9%, Calmar 0.22 vs 0.23, max DD equal) → fails the rule (both windows required). Reading: with the exact restore the pause is close to neutral (±0.2-0.8 pts a year, inside the noise of one path); the ETH gain of EXP-059 (CAGR 15.8%) came from its extra recentres, not from the pause. Scheduled macro releases are not toxic enough for a ±20% ladder to pay for being out of the pool. The holdout was run once; the improvement level fails.

## Deviations

- Designed after EXP-059's dev result (its confound is the motivation); the dev data has therefore been seen for the
  pause-plus-rebuild version of this rule. It is a repair of an implementation flaw, not a new constant: the schedule, the
  window and the pull are EXP-059's. Counted as a separate experiment and reported as a near-copy of EXP-059.
- Smoke test (variant only): WBTC 2024-03-01..03-25, 2 pauses, 300 minutes, no follow rebuild after either re-add.
