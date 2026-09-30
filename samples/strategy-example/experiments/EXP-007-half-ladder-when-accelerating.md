# EXP-007: half ladder only in an accelerating uptrend — EMA100 first and second differences (v6.7)

- Version: v6.7 (Dino's idea: use the first / second difference as an indicator)
- Jira: [QUAN-841](https://ewetechnology.atlassian.net/browse/QUAN-841)
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______

## Hypothesis

EXP-006's decomposition: three quarters of v6's IL (−$75.5k of −$101k, ETH 2022..2026-09) comes from ladders that a
rally runs through, because the bands above the price sell their ETH on the way up. EXP-006 holds that ETH as spot
at every build; this gives up the upper bands' fees in the chop, where the LP is at break-even (fees ≈ IL).

The first and second differences of the trend say when the upper bands are at risk. Classifying v6's 122 ladder
segments by the state on the last completed day before each build (EMA100 first difference > 0 and second
difference > 0, "accelerating up", 22% of days):

| state at build | segments | upward exits | IL | fees |
|---|---|---|---|---|
| accelerating up | 37 | 9 of 14 | −$64.8k | $48.3k |
| otherwise | 85 | 5 of 14 | −$36.6k | $37.9k |

So only the accelerating builds should keep the base as spot; the others keep v6's full ladder and its fees.

Using the differences to gate refills instead (block a refill while EMA slope < 0 and acceleration < 0) was checked
first on the F x ETH proxy and changes nothing (turnover 41.2 → 41.2): EMA100's second difference flips sign from day
to day, so a blocked refill just happens a day later. Gating on the first difference alone is EXP-003's "refill only
when armed" and destroys F's value (F x ETH +426% → +46%).

## Change

`HALF_WHEN_ACCEL = True` (v6: False):

- At every (re)build, judged on the last completed UTC day: d1 = EMA100(t) − EMA100(t−1), d2 = d1(t) − d1(t−1).
  If d1 > 0 and d2 > 0 the build is EXP-006's half ladder (base held as spot, only the quote-side bands placed),
  otherwise v6's full ladder. The state is only read at builds; nothing rebuilds because the state changes.
- Range exits are judged on the full ±20% span v6 would have built (identical to v6 for full-ladder builds).
- F follow counts spot base as deployed (as EXP-006).
- No new constant: EMA100 is v6's own s-rule EMA, one-day differences. Everything else identical to v6.

## Pre-registration

- Development data (in-sample): ETH/USDC 0.05% yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 (yearly
  reset, 100,000 USDC); continuous ETH 2022-01-01..2026-09-17 and WBTC/USDC 0.3% 2022-11-01..2026-09-17 reported.
  v6 (A) and this (H) in the same invocation.
- Holdout (run once, v6 + this only): WBTC/WETH 0.05% mainnet (`0x4585fe77…`), ETH base, WBTC quote, 2 WBTC,
  yearly segments 2023, 2024, 2025, 2026-01-01..09-17 plus the continuous 2022-11-01..2026-09-17 (reported).
  If EXP-006 reaches its holdout first, that run uses the same pool: this one then records it under Deviations
  (the pool will have been seen once by a sibling rule) and still runs it once.
- Success rule (as EXP-001..006, against v6):
  - Dev: wins in ≥ 3 of 5 ETH segments, median gain > 0 pts, and continuous ETH max DD (daily equity) ≥ −27.8%.
    Otherwise `dropped-at-dev`.
  - Holdout: wins in ≥ 3 of 4 segments and median gain > 0 pts → `holdout-pass`, else `holdout-fail`.

## Result

| test | v6 | this | gain |
|---|---|---|---|

Verdict:

## Deviations

- Designed after EXP-001..006's dev results and the segment analysis above (all dev data in-sample). Four
  trend-state definitions were compared on v6's segments before choosing: EMA100 d1&d2 (picked: v6's own EMA),
  EMA100 d1 only, 7-day log-price d1&d2, EMA20 d1&d2 (captured 11 of 14 upward exits, but adds a new span).
- EXP-006 (unconditional half ladder) is still running its dev while this is registered; its first two segments
  were seen (2022 +10.4% vs +7.6%, 2023 +32.4% vs +32.2%).
- Smoke tests before the pre-registration commit, outside every pre-registered window: ETH 2021-05-10..06-30 (4 of
  11 builds half; −32.3% vs v6 −31.0%, price impact $2.4k vs $0.9k) and 2021-11-01..07 (no accelerating build;
  identical to v6).
