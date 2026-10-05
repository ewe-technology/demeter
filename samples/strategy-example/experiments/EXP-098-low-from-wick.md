# EXP-098: refill measured from the intraday low since the exit (v6.85)

- Jira: QUAN-982
- Status: dropped-at-dev
- Pre-registration commit: 7fe7966 · Result commit: 89f53b2
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

The refill stages are fixed distances above the account's low since the exit (+5% x 3 days, +8.33/11.67/15%), and v6 measures that low on closes. The low the market actually printed is the minute low; measured from it, each stage needs the price to have moved further from the real bottom, so refills wait for a rebound off the true low instead of off a close that the next wick undercuts. Input change only: the stage distances are v6's.

## Change

`LOW_FROM_WICK = True` (variant `CK`): the low since the exit is the lowest minute price (at the exit day and every day after) instead of the lowest close. No constant.

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
| 2022 | +7.6% | -7.5% | -15.1 |
| 2023 | +32.2% | +37.2% | +5.0 |
| 2024 | +36.4% | +37.0% | +0.6 |
| 2025 | +16.3% | -17.8% | -34.1 |
| 2026-01..09-17 | +18.7% | +6.0% | -12.7 |

Wins 2/5, median -12.74 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +21.5% | 4.2% | -24.9% | 0.30 | 0.17 | $76.6k | $0.29k | 202 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +94.6% | 18.7% | -14.2% | 1.04 | 1.32 | $64.9k | $0.68k | 114 |

Verdict: **dropped-at-dev** — opposite effects: WBTC improves strongly (CAGR 18.7% vs 17.3%, Calmar 1.32 vs 0.97, max DD −14.2% vs −17.8%) while ETH collapses (4.2% vs 14.0%, Calmar 0.17), wins 2/5. Holdout not run. Reading (interpretation, not measured): measured from the wick, the stages sit higher above the close, so refills come later; WBTC (fewer, better-paid rebuilds on the 0.3% pool) gains, ETH (0.05%, earns from fast refills) misses most of its rebounds. The clearest instance of the ETH/WBTC split.

## Deviations

- Designed after EXP-088 (v6.75) passed and while EXP-092..096's dev run was in progress (their results not seen). The family follows v6.75's reading: no new signal, v6's daily rules read on the day's minute path (open, high, low) instead of the close alone. Goal: Dino, 2026-10-05, continue until 10 improvement-level passes (attempt count reported with every pass). Smoke test WBTC 2023-09-01..10-31 (`A,CJ,CK,CL,CM,CN`) before registration: all execute; v6 +9.5%, CN identical to v6 there (no stop in that window), the others differ.
