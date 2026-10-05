# EXP-099: refill days must close above their open (v6.86)

- Jira: QUAN-983
- Status: dropped-at-dev
- Pre-registration commit: 7fe7966 · Result commit: 89f53b2
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

A day that closes above its rebound threshold but below its own open was sold during the day: the bounce is fading. Counting only up days (close above the day's first minute price) for the 3-day confirmation and the later stages keeps the refill on rebounds that are still being bought.

## Change

`UP_DAY_REFILL = True` (variant `CL`): a day counts for the stage-1 counter, and a later stage fires, only if the day's close is above its open (first minute price of the UTC day). No constant.

## Pre-registration

Pre-registered together with EXP-097..101 (same commit), run with `A` (v6) in `A,CJ,CK,CL,CM,CN` per window.

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev windows,
  warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC 0.3%
  2022-01-01..2022-10-31. v6's numbers there are known (EXP-040..081) and both windows have been used for other variants; this
  variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

Development (`A` and the variant in each invocation, tag `ACJCKCLCMCN`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +11.6% | +4.0 |
| 2023 | +32.2% | +27.8% | -4.4 |
| 2024 | +36.4% | +31.3% | -5.0 |
| 2025 | +16.3% | +16.8% | +0.5 |
| 2026-01..09-17 | +18.7% | +17.3% | -1.4 |

Wins 2/5, median -1.42 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +99.2% | 15.8% | -23.3% | 0.82 | 0.68 | $85.2k | $0.33k | 124 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +69.6% | 14.6% | -17.7% | 0.86 | 0.82 | $51.9k | $0.54k | 95 |

Verdict: **dropped-at-dev** — ETH improves (CAGR 15.8% vs 14.0%, Calmar 0.68 vs 0.61, max DD −23.3%) but wins 2/5 and WBTC falls (14.6% vs 17.3%, Calmar 0.82). Holdout not run. Reading (interpretation, not measured): the up-day filter removes ETH's fading bounces but also delays WBTC refills, whose recoveries more often climb through red days.

## Deviations

- Designed after EXP-088 (v6.75) passed and while EXP-092..096's dev run was in progress (their results not seen). The family follows v6.75's reading: no new signal, v6's daily rules read on the day's minute path (open, high, low) instead of the close alone. Goal: Dino, 2026-10-05, continue until 10 improvement-level passes (attempt count reported with every pass). Smoke test WBTC 2023-09-01..10-31 (`A,CJ,CK,CL,CM,CN`) before registration: all execute; v6 +9.5%, CN identical to v6 there (no stop in that window), the others differ.
