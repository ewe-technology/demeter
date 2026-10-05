# EXP-101: lower stop on the intraday low (v6.88)

- Jira: QUAN-985
- Status: dropped-at-dev
- Pre-registration commit: 7fe7966 · Result commit: 89f53b2
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

The lower stop (0.8 x centre) is v6's crash protection, and v6 checks it on the close only. A crash day that wicks through the stop and closes back above it leaves the account exposed to the next leg; reading the stop on the day's minute low exits the account the morning after the first touch. The exit still executes at the next 00:00 rebuild, so this changes when the stop fires, not the price model.

## Change

`INTRADAY_STOP = True` (variant `CN`): the lower stop fires when the day's minute low (or close) is below 0.8 x the account's centre. No constant.

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
| 2022 | +7.6% | -0.8% | -8.4 |
| 2023 | +32.2% | +32.2% | +0.0 |
| 2024 | +36.4% | +25.8% | -10.6 |
| 2025 | +16.3% | +16.3% | +0.0 |
| 2026-01..09-17 | +18.7% | +18.7% | +0.0 |

Wins 0/5, median +0.00 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +61.7% | 10.7% | -24.3% | 0.60 | 0.44 | $75.7k | $0.25k | 157 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +96.5% | 19.0% | -18.0% | 1.10 | 1.06 | $64.0k | $0.78k | 106 |

Verdict: **dropped-at-dev** — WBTC improves (CAGR 19.0% vs 17.3%, Calmar 1.06) but ETH falls (10.7% vs 14.0%, Calmar 0.44), wins 0/5. Holdout not run. Reading (interpretation, not measured): ETH's intraday wicks through 0.8 x centre usually recover by the close, so stopping on the wick sells ETH low and refills higher; WBTC's touches more often continue.

## Deviations

- Designed after EXP-088 (v6.75) passed and while EXP-092..096's dev run was in progress (their results not seen). The family follows v6.75's reading: no new signal, v6's daily rules read on the day's minute path (open, high, low) instead of the close alone. Goal: Dino, 2026-10-05, continue until 10 improvement-level passes (attempt count reported with every pass). Smoke test WBTC 2023-09-01..10-31 (`A,CJ,CK,CL,CM,CN`) before registration: all execute; v6 +9.5%, CN identical to v6 there (no stop in that window), the others differ.
