# EXP-100: refill days must close in the upper half of their range (v6.87)

- Jira: QUAN-984
- Status: dropped-at-dev
- Pre-registration commit: 7fe7966 · Result commit: 89f53b2
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

Where a day closes inside its own range says who won the day (close-location value). A rebound day that closes in the lower half of its range was rejected from its high; one that closes in the upper half was held. Counting only strong-close days for the refill is the range version of EXP-099 and catches days that opened low and faded.

## Change

`STRONG_CLOSE_REFILL = True` (variant `CM`): a day counts for the stage-1 counter, and a later stage fires, only if its close is at or above the midpoint of its minute low and high. No constant.

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
| 2022 | +7.6% | +20.4% | +12.8 |
| 2023 | +32.2% | +28.4% | -3.8 |
| 2024 | +36.4% | +27.2% | -9.2 |
| 2025 | +16.3% | +20.0% | +3.8 |
| 2026-01..09-17 | +18.7% | +12.7% | -6.0 |

Wins 2/5, median -3.76 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +95.2% | 15.3% | -22.9% | 0.80 | 0.67 | $83.5k | $0.34k | 129 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +53.7% | 11.7% | -25.5% | 0.73 | 0.46 | $44.7k | $0.48k | 91 |

Verdict: **dropped-at-dev** — ETH CAGR 15.3% vs 14.0%, Calmar 0.67, wins 2/5; WBTC falls hard (11.7% vs 17.3%, Calmar 0.46, max DD −25.5%). Holdout not run. Reading (interpretation, not measured): as EXP-099 but stricter; on WBTC the delayed refills miss rebounds and the later re-entries land closer to the next stop.

## Deviations

- Designed after EXP-088 (v6.75) passed and while EXP-092..096's dev run was in progress (their results not seen). The family follows v6.75's reading: no new signal, v6's daily rules read on the day's minute path (open, high, low) instead of the close alone. Goal: Dino, 2026-10-05, continue until 10 improvement-level passes (attempt count reported with every pass). Smoke test WBTC 2023-09-01..10-31 (`A,CJ,CK,CL,CM,CN`) before registration: all execute; v6 +9.5%, CN identical to v6 there (no stop in that window), the others differ.
