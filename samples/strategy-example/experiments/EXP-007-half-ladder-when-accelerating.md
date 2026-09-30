# EXP-007: half ladder only in an accelerating uptrend — EMA100 first and second differences (v6.7)

- Version: v6.7 (Dino's idea: use the first / second difference as an indicator)
- Jira: [QUAN-841](https://ewetechnology.atlassian.net/browse/QUAN-841)
- Status: dropped-at-dev
- Pre-registration commit: 8ffecd2 · Result commit: see registry

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

Development, ETH/USDC 0.05%, yearly reset:

| test | v6 | this | gain | max DD v6 → this | half builds | fees v6 → this |
|---|---|---|---|---|---|---|
| 2022 | +7.6% | +7.5% | −0.1 | 21.5% → 21.5% | 4 of 41 | $20.1k → $20.0k |
| 2023 | +32.2% | +28.0% | −4.2 | 13.9% → 15.7% | 14 of 24 | $23.3k → $3.2k |
| 2024 | +36.4% | +26.1% | −10.3 | 26.7% → 33.7% | 9 of 29 | $30.9k → $12.8k |
| 2025 | +16.3% | +33.2% | +16.9 | 26.9% → 29.4% | 10 of 32 | $20.8k → $11.3k |
| 2026-01..09-17 | +18.7% | +18.3% | −0.4 | 12.0% → 12.0% | 2 of 24 | $6.2k → $5.8k |

Wins 1/5, median gain −0.37 pts.

Continuous runs (daily equity):

| run | total | CAGR | max DD | Sharpe |
|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | −22.8% | 0.73 |
| ETH this | +130.2% | 19.4% | −27.9% | 0.81 |
| WBTC/USDC v6 | +85.6% | 17.3% | −17.8% | 1.01 |
| WBTC/USDC this | +104.1% | 20.2% | −24.3% | 0.90 |

Why: a half build lasts until the next range exit, which in an uptrend is the whole rally, and during it the
quote-side bands sit below the price and earn almost nothing (2023: 14 of 24 builds half, fees $23.3k → $3.2k).
The upside IL saved does not pay for the fees lost except in 2025's straight rally. A follow-up check by trend x
volatility regime gives the same picture: v6's builds in "up, low vol" net −$17.9k over 4.7 years (IL −$57.6k,
fees +$39.7k), the other regimes are at break-even, so the whole upside-IL lever is worth at most ~$18k on
$100k — less than the fees a half ladder gives up. The half-ladder line (EXP-006, 007) is closed.

Verdict: **dropped at dev** — wins 1/5, median −0.4 pts; continuous max DD −27.9% (floor −27.8%). Holdout not run.

## Deviations

- Designed after EXP-001..006's dev results and the segment analysis above (all dev data in-sample). Four
  trend-state definitions were compared on v6's segments before choosing: EMA100 d1&d2 (picked: v6's own EMA),
  EMA100 d1 only, 7-day log-price d1&d2, EMA20 d1&d2 (captured 11 of 14 upward exits, but adds a new span).
- EXP-006 (unconditional half ladder) is still running its dev while this is registered; its first two segments
  were seen (2022 +10.4% vs +7.6%, 2023 +32.4% vs +32.2%).
- Smoke tests before the pre-registration commit, outside every pre-registered window: ETH 2021-05-10..06-30 (4 of
  11 builds half; −32.3% vs v6 −31.0%, price impact $2.4k vs $0.9k) and 2021-11-01..07 (no accelerating build;
  identical to v6).
