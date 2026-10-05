# EXP-129: fee tier: EXP-124's WBTC half, v6.75 + breadth cap on 0.05% (v6.115)

- Jira: QUAN-1014
- Status: dropped-at-dev
- Pre-registration commit: 88d31f3 · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

v6.75 plus EXP-091's breadth cap (ETH's F at most the mean of its own and BTC's engine F) on the cheap pool.

## Change

fee >= 0.3%: `INTRADAY_STOP`, `REFILL_VOL_CONFIRM`, `SWAP_ROUTE = pool` (EXP-124's WBTC half); below 0.3%: `REFILL_NO_NEW_LOW`, `BREADTH_CAP`. Variant `DQ`.

## Pre-registration

Pre-registered together with EXP-129..132 (same commit), run with `A` (v6) in `A,DQ,DR,DS,DT` per window. EXP-128 belongs to another session.

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

Development (`A` and the variant in each invocation, tag `ADQDRDSDT`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +4.6% | -3.0 |
| 2023 | +32.2% | +34.1% | +1.9 |
| 2024 | +36.4% | +26.8% | -9.5 |
| 2025 | +16.3% | +19.7% | +3.4 |
| 2026-01..09-17 | +18.7% | +16.4% | -2.3 |

Wins 2/5, median -2.28 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +93.9% | 15.1% | -22.2% | 0.82 | 0.68 | $84.2k | $0.28k | 169 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +109.6% | 21.0% | -13.8% | 1.22 | 1.52 | $64.4k | $-5.05k | 97 |

Verdict: **dropped-at-dev (fee-tier rule)** — WBTC = EXP-124 (21.0%, Calmar 1.52); ETH CAGR 15.1% vs 14.0%, Calmar 0.68, max DD −22.2%, but yearly wins 2/5. Holdout not run. The breadth cap does not add to v6.75 across years.

## Deviations

- Designed after EXP-123..127's results. Every fee-tier pass so far uses v6.75 alone as its ETH half, so the ETH side has one out-of-time finding. These pairs fix the WBTC half to EXP-124's (H4 +9.6%, known) and add to v6.75 one rule that raised ETH CAGR at dev but failed the ETH yearly-wins test alone (EXP-091 breadth cap, EXP-086 cross-asset refill, EXP-085 funding cap, EXP-100 strong-close refill). The ETH combination is new on H5 in every pair; a pass is new ETH evidence, a fail says that rule does not add to v6.75 out of time. Four, not five: the remaining ETH candidates either cannot act on H5 (crowding rules need 90 days of pool liquidity history, H5 starts on the pool's first day) or lost ETH return at dev.
