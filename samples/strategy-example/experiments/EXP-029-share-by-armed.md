# EXP-029: ETH value share s moves with the share of EMA spans the close is above (v6.24)

- Jira: QUAN-881
- Status: dropped-at-dev
- Pre-registration commit: 6907836 · Result commit: 7c9ea34
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

v6 sets the ladder's ETH share to 70% if the close is above EMA100, else 50%: all or nothing on one average, so the share flips on a single crossing while the F engine's four accounts (90..120) disagree for weeks. Using the fraction of the four spans above makes s change in five steps (50, 55, 60, 65, 70%) with the same endpoints as v6, so the ladder's directional tilt follows the same evidence as F.

## Change

`SHARE_BY_ARMED = True` (variant `Y`): s = 0.5 + 0.2 × (number of spans in 90/100/110/120 with last completed daily close above the EMA) / 4. F, the ladder, thresholds identical to v6.

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
| 2022 | +7.6% | +8.6% | +1.0 | 21.5% → 21.5% |
| 2023 | +32.2% | +32.2% | -0.0 | 13.9% → 13.9% |
| 2024 | +36.4% | +36.0% | -0.4 | 26.7% → 26.9% |
| 2025 | +16.3% | +15.8% | -0.5 | 26.9% → 27.2% |
| 2026-01..09-17 | +18.7% | +18.7% | -0.0 | 12.0% → 12.3% |

Wins 1/5, median -0.02 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +86.2% | 14.1% | -23.1% | 0.73 | 0.61 | $87.0k | $0.29k | 147 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +85.8% | 17.3% | -17.7% | 1.01 | 0.98 | $61.7k | $0.70k | 106 |

Verdict: **dropped-at-dev** — indistinguishable from v6 on both assets: ETH CAGR 14.1% vs 14.0%, Calmar 0.61 vs 0.61, wins 1/5 (median −0.02 pts), rebuilds 147 = 147; WBTC CAGR 17.3% = 17.3%. Whether the s rule rarely moves off 0.5/0.7 under this change was not diagnosed. Holdout not run.

## Deviations

- The code was smoke-tested on one-week and three-week windows (2026-09-01..09-10 and 2023-06-01..06-20) to catch errors and check that the width rule changes the ladder; v6 (`A`) 2026-01-01..09-17 re-run after the edit reproduces +18.706% exactly. Those short runs are not evidence for or against any variant. Batch 1 (EXP-024..027) found that lines faster than the 90-120 day EMA (Hull, ROC, Supertrend) lose and that Donchian wins on ETH only: EXP-028 and EXP-031 are the consequence, chosen after seeing that result.
