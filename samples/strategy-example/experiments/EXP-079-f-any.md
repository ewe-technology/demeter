# EXP-079: full ladder while any account is deployed (v6.66)

- Jira: QUAN-962
- Status: dropped-at-dev
- Pre-registration commit: d33e312 · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

Binarisation ablation: the ladder is either full or empty; full as soon as any account holds any stage. Removes fractional follow rebuilds (F changes 11 vs 35 on 2020-21 data), so the rebuild cost and the chop bleed of v6's drawdowns fall, at the cost of full exposure on the first refill stage.

## Change

`F_BINARY = "any"` (variant `BR`): F = 1 while any account's deployed fraction is > 0, else 0. No constant.

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
| 2022 | +7.6% | -14.6% | -22.2 |
| 2023 | +32.2% | +34.1% | +1.9 |
| 2024 | +36.4% | +41.1% | +4.7 |
| 2025 | +16.3% | +4.5% | -11.8 |
| 2026-01..09-17 | +18.7% | +10.8% | -7.9 |

Wins 2/5, median -7.92 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +29.8% | 5.7% | -24.3% | 0.36 | 0.23 | $75.7k | $0.38k | 69 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +83.6% | 17.0% | -18.9% | 0.93 | 0.90 | $74.4k | $1.52k | 44 |

Verdict: **dropped-at-dev** — ETH CAGR 5.7% vs 14.0%, Calmar 0.23, wins 2/5; WBTC CAGR 17.0%, Calmar 0.90. Holdout not run. Reading: a full ladder on the first refill stage of any account removes the gradual re-entry; on ETH the first stage is often wrong (bear rallies) and full exposure there is costly. The fractional F is part of v6's edge.

## Deviations

- Final batch of the goal (EXP-052..081, 30 experiments): ablations of how v6's engine turns its four accounts into F, chosen after the rule ablations EXP-066..069 and EXP-073..075. Sanity check on Binance ETH closes 2020-01..2021-04 (before every window used here; F statistics only): mean F / F changes v6 0.883 / 35, one account 0.888 / 29, min 0.868 / 33, max 0.888 / 29, any 0.920 / 11, all 0.813 / 11, one-stage refill 0.916 / 14.
