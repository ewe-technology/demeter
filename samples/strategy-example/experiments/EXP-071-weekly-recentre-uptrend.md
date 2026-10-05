# EXP-071: weekly recentre only above EMA100 (v6.58)

- Jira: QUAN-954
- Status: dropped-at-dev
- Pre-registration commit: fee36c2 · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

EXP-065's weekly recentre raised ETH's CAGR to 17.1% but cost WBTC its fee income ($31.6k vs $61.7k) and drawdown (−22.0%). The engine ablations showed v6 earns as a range harvester below the EMA (staged refills on rebounds) and steps aside in trends. Recentring pays in trends (the ladder follows the price instead of selling it all and rebuying at the exit) and costs in ranges (the valley earns at its thick edges, a recentre puts the price back into the thin centre). Restricting the weekly recentre to the uptrend state v6 already uses for its ETH share (close > EMA100) should keep the trend gain and drop the range cost on both pools.

## Change

`WEEKLY_RECENTRE_UP = True` (variant `BI`): EXP-065's Sunday 00:00 full recentre, only when the last completed close is above EMA100. Everything else is v6's. No new constant (the weekly cadence is EXP-065's).

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
| 2022 | +7.6% | +8.5% | +0.9 |
| 2023 | +32.2% | +29.5% | -2.8 |
| 2024 | +36.4% | +33.1% | -3.3 |
| 2025 | +16.3% | +18.9% | +2.6 |
| 2026-01..09-17 | +18.7% | +18.7% | +0.0 |

Wins 3/5, median +0.02 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +114.0% | 17.5% | -24.5% | 0.82 | 0.72 | $81.1k | $0.40k | 236 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +92.7% | 18.4% | -21.9% | 0.91 | 0.84 | $32.9k | $0.88k | 215 |

Verdict: **dropped-at-dev** — ETH passes every part of the rule (CAGR 17.5% vs 14.0%, Calmar 0.72 vs 0.61, max DD −24.5% vs −22.8%, within 3 pts; wins 3/5) but WBTC fails Calmar and drawdown (CAGR 18.4% vs 17.3%, Calmar 0.84 vs 0.97, max DD −21.9% vs −17.8%). Holdout not run. Reading: restricting the weekly recentre to the uptrend state kept all of ETH's gain and improved its yearly consistency (3/5 vs EXP-065's 2/5), but WBTC spent most of 2023-25 above its EMA100, so it still recentred 117 times and lost half its fee income (.9k vs .7k) to the valley's thin centre and 0.3% swaps.

## Deviations

- Designed after EXP-065 (weekly recentre: ETH CAGR 17.1% but WBTC Calmar 0.82), EXP-055/058/062 (resizing) and the engine ablations EXP-066..068 (the staged refill below the EMA is v6's edge: a range harvester that steps aside in trends); the state split uses v6's own EMA100 share state, no new constant. Smoke test ETH 2022-05-01..06-30 (`BI,BJ`, no v6 run on this invocation; v6's total on this window was seen in EXP-055's smoke test): BJ resized 3 times, BI made no weekly recentre (below EMA100 throughout). A numpy-bool comparison bug (`is False`) was fixed before this file.
