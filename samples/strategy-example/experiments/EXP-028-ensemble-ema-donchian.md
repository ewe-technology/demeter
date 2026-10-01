# EXP-028: F = mean of 8 accounts (4 on EMA(n), 4 on the Donchian midpoint(n)) (v6.23)

- Jira: QUAN-880
- Status: dropped-at-dev
- Pre-registration commit: 6907836 · Result commit: 7c9ea34
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

EXP-024 (Donchian) beat v6 on ETH (Calmar 0.74 vs 0.61) and lost on WBTC (0.87 vs 0.97); v6's own EMA does the opposite ordering. Two different slow trend lines disagree on some days; averaging their deployed fractions is the standard way to cut single-indicator model risk and should land between them on each asset, ideally above v6 on both.

## Change

`REGIME = "ens_ed"` (variant `X`): eight virtual accounts, n = 90/100/110/120 on the EMA line and n = 90/100/110/120 on the Donchian midpoint line (EXP-024's definition); F = mean of the eight deployed fractions. Everything else identical to v6 (the s rule on EMA100, follow threshold 12.5%, ±20% valley ladder).

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
| 2022 | +7.6% | +12.1% | +4.5 | 21.5% → 16.2% |
| 2023 | +32.2% | +37.1% | +4.9 | 13.9% → 13.1% |
| 2024 | +36.4% | +28.8% | -7.6 | 26.7% → 29.6% |
| 2025 | +16.3% | +24.8% | +8.5 | 26.9% → 24.4% |
| 2026-01..09-17 | +18.7% | +5.7% | -13.0 | 12.0% → 17.3% |

Wins 3/5, median +4.53 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +98.9% | 15.7% | -21.5% | 0.80 | 0.73 | $97.2k | $0.33k | 142 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +66.9% | 14.1% | -16.0% | 0.81 | 0.88 | $56.8k | $0.53k | 102 |

Verdict: **dropped-at-dev** — ETH passes (CAGR 15.7% vs 14.0%, Calmar 0.73 vs 0.61, max DD 1.3 pts shallower, yearly wins 3/5, median +4.53 pts) but WBTC fails (CAGR 14.1% vs 17.3%, Calmar 0.88 vs 0.97). Same split as the Donchian line alone (EXP-024): the ensemble is better than it on ETH (CAGR 15.7% vs 15.0%) and no better on WBTC (14.1% vs 14.7%), so the WBTC shortfall is not removed by averaging. Holdout not run under this rule.

## Deviations

- The code was smoke-tested on one-week and three-week windows (2026-09-01..09-10 and 2023-06-01..06-20) to catch errors and check that the width rule changes the ladder; v6 (`A`) 2026-01-01..09-17 re-run after the edit reproduces +18.706% exactly. Those short runs are not evidence for or against any variant. Batch 1 (EXP-024..027) found that lines faster than the 90-120 day EMA (Hull, ROC, Supertrend) lose and that Donchian wins on ETH only: EXP-028 and EXP-031 are the consequence, chosen after seeing that result.
