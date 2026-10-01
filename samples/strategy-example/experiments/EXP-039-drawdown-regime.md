# EXP-039: regime = close within 20% of its n-day high, n = 90/100/110/120 (v6.30)

- Jira: QUAN-891
- Status: dropped-at-dev
- Pre-registration commit: 0edc010 · Result commit: fcf6540
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

A drawdown filter asks a different question from a moving average: how far is the price from its recent peak. 20% is the ladder's own half-width and v6's lower-stop distance, so the exit rule matches the unit the LP already uses: when the price is 20% under its n-day high the ladder is already beyond its lower edge. Re-arm is automatic when the high rolls out of the window or the price recovers.

## Change

`REGIME = "dd"`, `DD_FRAC = 0.20` (variant `AF`): accounts n = 90, 100, 110, 120 armed while the daily close is above 0.8 × the highest daily close of the last n days. Everything else identical to v6.

## Pre-registration

Pre-registered together with EXP-036..039 (four regime lines of different structure, one constant set each, none searched) and run in the same invocations as `A`. Both success levels are judged from the same runs; all four results are reported.

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and
  continuous 2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant; only if dev passes), numbers of all three reported:
  - H1 Arbitrum WETH/USDC 0.05% `0xc6962004f452be9203591991d15f6b388e09e8d0` continuous 2024-01-01..2025-07-23
    (EMA warm-up on mainnet ETH/USD): v6 never ran on it with this variant;
  - H2 Base USDC/WETH 0.05% continuous 2024-01-01..2026-09-17 and H3 Base USDC/cbBTC 0.05% continuous
    2025-01-01..2026-09-17 (v6 ran on them before, this variant never).
  Honest limit: H1 and H2 share mainnet ETH's price path; the clean forward window (2026-09-18..12-31) does not exist yet.
- Success rules (variant vs v6 `A`, daily equity net of price impact, Calmar = CAGR / |max DD|; two levels, README *Success levels*; the same runs decide both):
  - Improvement: dev: continuous ETH and WBTC CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper, ETH yearly wins ≥ 3 of 5.
    Holdout (three pools): on at least 2 of 3 CAGR above v6's **and** Calmar ≥ v6's (if v6's CAGR is negative: CAGR above and max DD
    not more than 3 pts deeper) **and** max DD no more than 3 pts deeper, **and** on the third pool Calmar ≥ v6's − 0.2 → `holdout-pass`.
  - Standalone: dev: continuous ETH and WBTC Calmar ≥ 0.60 and max DD no deeper than −30%, ETH positive in ≥ 4 of 5 yearly segments.
    Holdout: total return > 0 on all three pools, Calmar ≥ 0.50 on at least 2 of 3, max DD no deeper than −35% on all three → `holdout-pass` (standalone).
  - Dev failing both levels → `dropped-at-dev`; the holdout is run (once) when dev passes at least one level, and each level is judged on it separately.

## Result

Development (`A` and the variant in each invocation):

| test | v6 | this | gain | max DD v6 → this |
|---|---|---|---|---|
| 2022 | +7.6% | +15.0% | +7.4 | 21.5% → 18.7% |
| 2023 | +32.2% | +26.0% | -6.2 | 13.9% → 26.4% |
| 2024 | +36.4% | +20.9% | -15.4 | 26.7% → 34.5% |
| 2025 | +16.3% | +17.7% | +1.4 | 26.9% → 24.5% |
| 2026-01..09-17 | +18.7% | -8.2% | -26.9 | 12.0% → 22.2% |

Wins 2/5, median -6.19 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +59.9% | 10.5% | -27.9% | 0.60 | 0.38 | $92.6k | $0.43k | 131 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +63.7% | 13.6% | -31.5% | 0.75 | 0.43 | $69.3k | $1.09k | 68 |

Verdict: **dropped-at-dev** (both levels) — worse than v6 on both: ETH CAGR 10.5% vs 14.0%, Calmar 0.38, max DD −27.9%, wins 2/5; WBTC CAGR 13.6% vs 17.3%, Calmar 0.43, max DD −31.5%. Holdout not run.

## Deviations

- The code was smoke-tested on a three-week window (2023-06-01..06-20) and the signal-only F series checked once on ETH/USDC (mean F, correlation with v6's F, number of F changes); no P&L evidence. A first KAMA variant (slow constant = n) was dropped before pre-registration because its signal was degenerate (mean F 0.32): it was replaced by the drawdown-from-high regime (EXP-039). The candidates were chosen after seeing batches 1-3: lines faster than the EMA(90-120) lost, range-structure lines (Donchian) won on ETH only, so this batch tries slower and structurally different lines.
