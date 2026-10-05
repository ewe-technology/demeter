# EXP-078: F = the highest account's deployed fraction (v6.65)

- Jira: QUAN-961
- Status: dropped-at-dev
- Pre-registration commit: d33e312 · Result commit: 5baddb3
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

Aggregation ablation, aggressive side: deploy what the most optimistic account says. More time deployed in the range-harvesting state that carries v6's edge (EXP-067/068), later cuts; expected higher fee income and deeper drawdowns.

## Change

`F_AGG = "max"` (variant `BQ`): F = max over the four accounts. No constant.

## Pre-registration

Pre-registered together with the other five engine ablations of the same commit (EXP-076..081); two invocations, each with `A`
(v6): `A,BO,BP,BQ` and `A,BR,BS,BT`. The six are ablations of one engine and are not independent evidence of each other.

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

Development (`A` and the variant in each invocation, tag `ABOBPBQ`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +2.0% | -5.6 |
| 2023 | +32.2% | +31.8% | -0.4 |
| 2024 | +36.4% | +32.7% | -3.7 |
| 2025 | +16.3% | +20.7% | +4.4 |
| 2026-01..09-17 | +18.7% | +9.1% | -9.6 |

Wins 1/5, median -3.71 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +63.9% | 11.1% | -23.1% | 0.60 | 0.48 | $88.3k | $0.33k | 119 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +69.1% | 14.5% | -17.8% | 0.83 | 0.81 | $63.2k | $0.82k | 81 |

Verdict: **dropped-at-dev** — ETH CAGR 11.1% vs 14.0%, Calmar 0.48, wins 1/5; WBTC CAGR 14.5% vs 17.3%, Calmar 0.81. Holdout not run. Reading: following the most optimistic account deploys earlier into rebounds that fail; more exposure in the range-harvesting state is not more income when the refills are premature.

## Deviations

- Final batch of the goal (EXP-052..081, 30 experiments): ablations of how v6's engine turns its four accounts into F, chosen after the rule ablations EXP-066..069 and EXP-073..075. Sanity check on Binance ETH closes 2020-01..2021-04 (before every window used here; F statistics only): mean F / F changes v6 0.883 / 35, one account 0.888 / 29, min 0.868 / 33, max 0.888 / 29, any 0.920 / 11, all 0.813 / 11, one-stage refill 0.916 / 14.
