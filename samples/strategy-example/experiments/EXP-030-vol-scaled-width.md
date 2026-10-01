# EXP-030: ladder half-width = 30-day sigma x sqrt(30), 10..30%, instead of fixed ±20% (v6.25)

- Jira: QUAN-___
- Status: dropped-at-dev
- Pre-registration commit: 6907836 · Result commit: ______
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

v6's width is fixed while volatility is not: EXP-023's decomposition shows 86% of v6's IL comes from the 19 builds that ended with the price outside the ±20% span. A band sized to the expected one-month move (σ√T, the scaling in the optimal-width results of Cartea, Drissi, Monga 2024 and Elsts' vol-scaled rebalancing) exits about equally often in every regime: wider (fewer exits, less realised IL, less fee density) in volatile markets, narrower in calm ones.

## Change

`WIDTH_VOL = True` (variant `Z`): at every build the half-width = σ × √30 with σ the standard deviation of the last 30 completed daily log returns, clamped to [0.10, 0.30], rounded to the nearest 0.05, the same width up and down; no value searched (K = 1, T = 30 days, bounds and grid set here). Valley shape, F, s rule identical to v6; the range exit and rebuild use the width of the ladder in place.

## Pre-registration

Pre-registered together with EXP-028..031 (two regime-signal combinations and two LP-composition / width rules, one constant set each, none searched) and run in the same invocations as `A`. All four results are reported.

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and
  continuous 2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant; only if dev passes), numbers of all three reported:
  - H1 Arbitrum WETH/USDC 0.05% `0xc6962004f452be9203591991d15f6b388e09e8d0` continuous 2024-01-01..2025-07-23
    (EMA warm-up on mainnet ETH/USD): v6 never ran on it with this variant;
  - H2 Base USDC/WETH 0.05% continuous 2024-01-01..2026-09-17 and H3 Base USDC/cbBTC 0.05% continuous
    2025-01-01..2026-09-17 (v6 ran on them before, this variant never).
  Honest limit: H1 and H2 share mainnet ETH's price path; the clean forward window (2026-09-18..12-31) does not exist yet.
- Success rule (variant vs v6 `A`, daily equity net of price impact, Calmar = CAGR / |max DD|):
  - Dev: continuous ETH and WBTC CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly
    wins ≥ 3 of 5. Else `dropped-at-dev`.
  - Holdout (the three deciding pools, one continuous run each): on at least 2 of the 3 pools CAGR above v6's **and**
    Calmar ≥ v6's (if v6's CAGR is negative: CAGR above and max DD not more than 3 pts deeper) **and** max DD no more
    than 3 pts deeper; **and** on the third pool Calmar ≥ v6's Calmar − 0.2 → `holdout-pass`, else `holdout-fail`.

## Result

Development (`A` and the variant in each invocation):

| test | v6 | this | gain | max DD v6 → this |
|---|---|---|---|---|
| 2022 | +7.6% | +3.9% | -3.7 | 21.5% → 20.6% |
| 2023 | +32.2% | +24.2% | -8.1 | 13.9% → 13.8% |
| 2024 | +36.4% | +19.4% | -17.0 | 26.7% → 28.2% |
| 2025 | +16.3% | +20.2% | +4.0 | 26.9% → 28.0% |
| 2026-01..09-17 | +18.7% | +17.5% | -1.2 | 12.0% → 12.7% |

Wins 1/5, median -3.66 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +82.7% | 13.7% | -19.9% | 0.75 | 0.69 | $87.7k | $0.28k | 148 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +49.3% | 10.9% | -17.8% | 0.70 | 0.61 | $65.0k | $0.66k | 121 |

Verdict: **dropped-at-dev** — ETH CAGR 13.7% vs 14.0% (Calmar 0.69 vs 0.61 and max DD 2.9 pts shallower, but CAGR is below v6's and wins are 1/5, median −3.66 pts; 2024 −17.0); WBTC CAGR 10.9% vs 17.3%, Calmar 0.61 vs 0.97, rebuilds 121 vs 106. Width per build is in the `width_builds` column of the run CSV. Holdout not run.

## Deviations

- The code was smoke-tested on one-week and three-week windows (2026-09-01..09-10 and 2023-06-01..06-20) to catch errors and check that the width rule changes the ladder; v6 (`A`) 2026-01-01..09-17 re-run after the edit reproduces +18.706% exactly. Those short runs are not evidence for or against any variant. Batch 1 (EXP-024..027) found that lines faster than the 90-120 day EMA (Hull, ROC, Supertrend) lose and that Donchian wins on ETH only: EXP-028 and EXP-031 are the consequence, chosen after seeing that result.
