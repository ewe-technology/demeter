# EXP-072: follow events below EMA100 resize in place; v6 recentre above (v6.59)

- Jira: QUAN-955
- Status: dropped-at-dev
- Pre-registration commit: fee36c2 · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

Same state split applied to the follow rule. Below EMA100 v6 is harvesting a range (staged refills on rebounds, F moving in quarter steps): each F change recentres the whole ladder into the valley's thin centre and swaps it back to the target share. Resizing in place there keeps the liquidity at the ticks where the range has been trading (the thick edges) and skips the swap; above EMA100 v6's recentre keeps following the trend. EXP-055 resized everywhere (ETH fees −6%, WBTC Calmar 1.22); EXP-062 resized only on F decreases. This tests the trend-state version.

## Change

`RESIZE_BELOW_EMA = True` (variant `BJ`): a follow event (|F − deployed| ≥ 12.5%, ladder deployed, target > 0) on a day whose last completed close is ≤ EMA100 is handled by EXP-055's resize in place; above EMA100 by v6's full rebuild. No constant.

## Pre-registration

Pre-registered together with the other experiment of the same commit (EXP-071 / EXP-072) and run in the same invocations as
`A` (v6).

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

Development (`A` and the variant in each invocation, tag `ABIBJ`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | -1.2% | -8.8 |
| 2023 | +32.2% | +32.2% | -0.0 |
| 2024 | +36.4% | +34.5% | -1.9 |
| 2025 | +16.3% | +12.9% | -3.4 |
| 2026-01..09-17 | +18.7% | +18.6% | -0.1 |

Wins 0/5, median -1.87 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +62.2% | 10.8% | -22.1% | 0.62 | 0.49 | $81.7k | $0.22k | 150 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +84.8% | 17.2% | -17.7% | 1.00 | 0.97 | $61.5k | $0.67k | 106 |

Verdict: **dropped-at-dev** — ETH CAGR 10.8% vs 14.0%, Calmar 0.49, wins 0/5; WBTC = v6 (17.2% vs 17.3%, Calmar 0.97). Holdout not run. Reading: below EMA100 the follow events are the staged refills (46 ETH resizes); adding the refill capital at the old ticks instead of around the rebound price loses ETH fees (.7k vs .5k). The refill's recentre at the rebound is part of v6's edge, consistent with EXP-067/068.

## Deviations

- Designed after EXP-065 (weekly recentre: ETH CAGR 17.1% but WBTC Calmar 0.82), EXP-055/058/062 (resizing) and the engine ablations EXP-066..068 (the staged refill below the EMA is v6's edge: a range harvester that steps aside in trends); the state split uses v6's own EMA100 share state, no new constant. Smoke test ETH 2022-05-01..06-30 (`BI,BJ`, no v6 run on this invocation; v6's total on this window was seen in EXP-055's smoke test): BJ resized 3 times, BI made no weekly recentre (below EMA100 throughout). A numpy-bool comparison bug (`is False`) was fixed before this file.
