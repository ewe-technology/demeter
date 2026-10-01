# EXP-038: regime = Aroon Up(n) > Aroon Down(n), n = 90/100/110/120 (v6.29)

- Jira: QUAN-___
- Status: dropped-at-dev
- Pre-registration commit: 0edc010 · Result commit: ______
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

All earlier lines compare the close with a price level. Aroon (Chande 1995) reads the time since the n-day high and low: an uptrend is when the high is more recent than the low. It is a different information source with the same window lengths as v6, blind to the size of the move, so it should disagree with v6 on slow grinds and V-shaped reversals, the regimes where v6 is weakest (V6_VALIDATION).

## Change

`REGIME = "aroon"` (variant `AE`): accounts n = 90, 100, 110, 120 armed while Aroon Up(n) > Aroon Down(n), Aroon Up = 100 × (n − days since the highest daily high of the last n+1 days) / n, Down likewise on daily lows. Everything else identical to v6.

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
| 2022 | +7.6% | -34.8% | -42.4 | 21.5% → 38.1% |
| 2023 | +32.2% | +58.3% | +26.1 | 13.9% → 11.4% |
| 2024 | +36.4% | +26.1% | -10.3 | 26.7% → 31.6% |
| 2025 | +16.3% | +27.8% | +11.5 | 26.9% → 37.7% |
| 2026-01..09-17 | +18.7% | +5.1% | -13.6 | 12.0% → 21.9% |

Wins 2/5, median -10.31 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +10.2% | 2.1% | -37.6% | 0.21 | 0.06 | $67.2k | $0.18k | 109 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +138.5% | 25.1% | -17.5% | 1.18 | 1.43 | $86.3k | $0.40k | 61 |

Verdict: **dropped-at-dev** (both levels) — ETH fails: CAGR 2.1% vs 14.0%, Calmar 0.06, max DD −37.6%, wins 2/5, 4/5 positive years. WBTC is the best of the four: CAGR 25.1% vs 17.3%, Calmar 1.43 vs 0.97, max DD −17.5% vs −17.8%. Holdout not run.

## Deviations

- The code was smoke-tested on a three-week window (2023-06-01..06-20) and the signal-only F series checked once on ETH/USDC (mean F, correlation with v6's F, number of F changes); no P&L evidence. A first KAMA variant (slow constant = n) was dropped before pre-registration because its signal was degenerate (mean F 0.32): it was replaced by the drawdown-from-high regime (EXP-039). The candidates were chosen after seeing batches 1-3: lines faster than the EMA(90-120) lost, range-structure lines (Donchian) won on ETH only, so this batch tries slower and structurally different lines.
