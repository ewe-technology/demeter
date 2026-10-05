# EXP-076: one EMA100 account instead of four (ensemble ablation) (v6.63)

- Jira: QUAN-959
- Status: dropped-at-dev
- Pre-registration commit: d33e312 · Result commit: 5baddb3
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

v6's F is the mean of four accounts on EMA 90 / 100 / 110 / 120. The ensemble diversifies the timing of exits and refills (F moves in 1/16 steps instead of quarters) at the price of more F changes and therefore more full-ladder rebuilds. A single EMA100 account (the share rule's own line) tests whether the diversification earns its rebuild cost: fewer, larger F steps.

## Change

`EMA_SPANS = (100,)` (variant `BO`): one virtual account on EMA100; F = its deployed fraction (0, 1/4 ... 1). Everything else is v6's. No constant (100 is the span v6 already uses for its share rule).

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
| 2022 | +7.6% | +1.8% | -5.8 |
| 2023 | +32.2% | +32.3% | +0.1 |
| 2024 | +36.4% | +39.1% | +2.7 |
| 2025 | +16.3% | +20.9% | +4.7 |
| 2026-01..09-17 | +18.7% | +19.5% | +0.8 |

Wins 4/5, median +0.80 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +80.8% | 13.4% | -21.3% | 0.70 | 0.63 | $83.9k | $0.32k | 125 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +96.9% | 19.1% | -18.4% | 1.09 | 1.04 | $63.9k | $1.16k | 86 |

Verdict: **dropped-at-dev** — ETH CAGR 13.4% vs 14.0% (Calmar 0.63 vs 0.61, max DD −21.3%, wins 4/5); WBTC CAGR 19.1% vs 17.3%, Calmar 1.04. Holdout not run (ETH CAGR below v6's). Reading: a single EMA100 account does about as well as the four-span ensemble — slightly less ETH return with a shallower drawdown, more WBTC return. The ensemble's diversification is worth little either way; its cost (more F changes) and benefit (smoother timing) roughly cancel.

## Deviations

- Final batch of the goal (EXP-052..081, 30 experiments): ablations of how v6's engine turns its four accounts into F, chosen after the rule ablations EXP-066..069 and EXP-073..075. Sanity check on Binance ETH closes 2020-01..2021-04 (before every window used here; F statistics only): mean F / F changes v6 0.883 / 35, one account 0.888 / 29, min 0.868 / 33, max 0.888 / 29, any 0.920 / 11, all 0.813 / 11, one-stage refill 0.916 / 14.
