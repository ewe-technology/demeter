# EXP-080: full ladder only while every account is fully deployed (v6.67)

- Jira: QUAN-963
- Status: dropped-at-dev
- Pre-registration commit: d33e312 · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

Binarisation ablation, strict side: the ladder is deployed only when the whole engine agrees fully, and pulled at the first partial exit. Fewest rebuilds and least time deployed; expected shallow drawdowns, lower fee income.

## Change

`F_BINARY = "all"` (variant `BS`): F = 1 only while all four accounts are at deployed = 1, else 0. No constant.

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

Development (`A` and the variant in each invocation, tag `ABRBSBT`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +20.8% | +13.2 |
| 2023 | +32.2% | +32.1% | -0.1 |
| 2024 | +36.4% | +25.6% | -10.7 |
| 2025 | +16.3% | +11.5% | -4.7 |
| 2026-01..09-17 | +18.7% | +10.5% | -8.2 |

Wins 1/5, median -4.74 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +86.7% | 14.2% | -24.7% | 0.76 | 0.57 | $85.6k | $0.68k | 50 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +58.4% | 12.6% | -24.1% | 0.82 | 0.52 | $50.1k | $1.79k | 33 |

Verdict: **dropped-at-dev** — ETH CAGR 14.2% vs 14.0% but Calmar 0.57 and max DD −24.7%, wins 1/5; WBTC CAGR 12.6% vs 17.3%, Calmar 0.52, max DD −24.1%. Holdout not run. Reading: all-or-nothing on full agreement deploys late and exits at the first partial exit; fewer rebuilds, but each full exit/entry lands at a worse price, deepening drawdowns on both assets.

## Deviations

- Final batch of the goal (EXP-052..081, 30 experiments): ablations of how v6's engine turns its four accounts into F, chosen after the rule ablations EXP-066..069 and EXP-073..075. Sanity check on Binance ETH closes 2020-01..2021-04 (before every window used here; F statistics only): mean F / F changes v6 0.883 / 35, one account 0.888 / 29, min 0.868 / 33, max 0.888 / 29, any 0.920 / 11, all 0.813 / 11, one-stage refill 0.916 / 14.
