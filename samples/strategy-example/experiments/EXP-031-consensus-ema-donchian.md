# EXP-031: account armed only while the close is above both EMA(n) and the Donchian midpoint(n) (v6.26)

- Jira: QUAN-883
- Status: dropped-at-dev
- Pre-registration commit: 6907836 · Result commit: 7c9ea34
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

Where EXP-028 averages two trend lines, this takes their agreement: an account re-arms and stays armed only when both lines say up, and exits when either says down. It is the conservative composition: later entries, earlier exits than either line alone, aimed at the drawdowns that came from one line being slow.

## Change

`REGIME = "max_ed"` (variant `AA`): four accounts n = 90/100/110/120 with the line = max(EMA(n), Donchian midpoint(n)); armed while the daily close is above it. Everything else identical to v6.

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
| 2022 | +7.6% | +16.8% | +9.2 | 21.5% → 19.1% |
| 2023 | +32.2% | +37.8% | +5.5 | 13.9% → 14.5% |
| 2024 | +36.4% | +30.5% | -5.8 | 26.7% → 28.6% |
| 2025 | +16.3% | +16.4% | +0.1 | 26.9% → 26.9% |
| 2026-01..09-17 | +18.7% | +8.1% | -10.6 | 12.0% → 21.3% |

Wins 3/5, median +0.12 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +86.7% | 14.2% | -20.9% | 0.73 | 0.68 | $99.6k | $0.51k | 129 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +59.4% | 12.8% | -17.8% | 0.75 | 0.72 | $54.2k | $0.64k | 101 |

Verdict: **dropped-at-dev** — ETH passes (CAGR 14.2% vs 14.0%, Calmar 0.68 vs 0.61, max DD 1.9 pts shallower, wins 3/5, median +0.12 pts) but WBTC fails (CAGR 12.8% vs 17.3%, Calmar 0.72 vs 0.97). WBTC trails v6 as the Donchian line alone did (EXP-024); why the agreement rule does not help there was not diagnosed. Holdout not run under this rule.

## Deviations

- The code was smoke-tested on one-week and three-week windows (2026-09-01..09-10 and 2023-06-01..06-20) to catch errors and check that the width rule changes the ladder; v6 (`A`) 2026-01-01..09-17 re-run after the edit reproduces +18.706% exactly. Those short runs are not evidence for or against any variant. Batch 1 (EXP-024..027) found that lines faster than the 90-120 day EMA (Hull, ROC, Supertrend) lose and that Donchian wins on ETH only: EXP-028 and EXP-031 are the consequence, chosen after seeing that result.
