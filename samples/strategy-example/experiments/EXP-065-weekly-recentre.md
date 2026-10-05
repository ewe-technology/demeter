# EXP-065: weekly time-based recentre on top of v6's triggers (v6.52)

- Jira: QUAN-947
- Status: dropped-at-dev
- Pre-registration commit: 9ea5296 · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

The LP literature compares event-triggered rebalancing (rebuild when the price leaves the range, v6's rule) with time-triggered
rebalancing; Panoptic's ETH/USDC backtests (https://panoptic.xyz/research/uniswap-lp-width) found weekly rebalancing at moderate
widths better than both daily rebalancing and waiting. In this goal's experiments extra recentres raised ETH's return (EXP-023:
CAGR 18.3%; EXP-059's extra rebuilds: 15.8%) and cost WBTC (0.3% swaps, the valley's thin centre). A fixed weekly recentre is the
plain, parameter-free time-based version: it tests whether time-based recentring is worth its cost on both pools. Expected:
ETH CAGR up; WBTC uncertain (the swap bill rises); the experiment is reported either way as the time-vs-event test.

## Change

`WEEKLY_RECENTRE = True` (variant `BC`): every Sunday at the 00:00 UTC follow check, a deployed ladder (current > 2%, F > 0) gets
v6's full rebuild (burn, swap to the target ETH share, re-mint F x equity centred on the current price). v6's range exits and
follow rule stay. The one constant is the weekly cadence (Panoptic's best case, not searched here).

## Pre-registration

Pre-registered together with EXP-064 (same commit) and run in the same invocations as `A` (v6).

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev windows,
  warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC 0.3%
  2022-01-01..2022-10-31. v6's numbers there are known (EXP-040..063); this variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

Development (`A` and the variant in each invocation, tag `ABBBC`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +8.5% | +0.9 |
| 2023 | +32.2% | +26.9% | -5.3 |
| 2024 | +36.4% | +30.8% | -5.6 |
| 2025 | +16.3% | +21.3% | +5.0 |
| 2026-01..09-17 | +18.7% | +16.8% | -1.9 |

Wins 2/5, median -1.95 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +109.9% | 17.1% | -23.9% | 0.81 | 0.71 | $76.6k | $0.40k | 311 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +90.6% | 18.1% | -22.0% | 0.90 | 0.82 | $31.6k | $0.87k | 259 |

Verdict: **dropped-at-dev** — ETH improves strongly (CAGR 17.1% vs 14.0%, Calmar 0.71 vs 0.61, max DD −23.9% vs −22.8%) but the ETH yearly wins are 2/5 and WBTC fails Calmar and drawdown (CAGR 18.1% vs 17.3%, Calmar 0.82 vs 0.97, max DD −22.0% vs −17.8%, 4.2 pts deeper). Holdout not run. Reading: weekly recentring cuts fee income on both pools (ETH .6k vs .5k; WBTC .6k vs .7k, the valley's thin centre again) and raises the return through realised-IL savings and trend-following (the ladder stays centred on a moving price), with deeper WBTC drawdowns. It is the strongest ETH result of this goal and confirms the time-vs-event result of the literature on the 0.05% pool; on the 0.3% pool the fee loss turns it into a riskier, not better, strategy.

## Deviations

- Designed after EXP-023 and EXP-059 (their ETH gains from extra recentres are the motivation). Smoke test WBTC 2024-03-01..25
  (`BB,BC`, no v6 run): 4 weekly recentres; a `dayofweek` attribute error was fixed before this file.
