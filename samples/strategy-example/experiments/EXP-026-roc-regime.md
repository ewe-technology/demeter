# EXP-026: regime = n-day return > 0 (time-series momentum) instead of price above EMA(n) (v6.21)

- Jira: QUAN-878
- Status: dropped-at-dev
- Pre-registration commit: 5440347 · Result commit: 8912e08
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

Time-series momentum (Moskowitz, Ooi, Pedersen 2012) uses the sign of the past n-day return, not the distance to an average. Its line is the close n days ago: it does not smooth, so it is blind to the path inside the window and re-arms the day the window return turns positive. Same lengths as v6, so it differs from v6 only in how the trend is read.

## Change

`REGIME = "roc"` (variant `U`): accounts n = 90, 100, 110, 120 armed while the daily close is above the close n days ago (line = close.shift(n)). Everything else identical to v6.

## Pre-registration

Pre-registered together with EXP-024..027 (four regime-line variants, same four lengths 90/100/110/120 as v6's EMA spans, one constant set each, none searched) and run in the same invocations as `A`. All four results are reported.

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and
  continuous 2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant; only if dev passes), numbers of all three reported:
  - H1 Arbitrum WETH/USDC 0.05% `0xc6962004f452be9203591991d15f6b388e09e8d0` continuous 2024-01-01..2025-07-23
    (EMA warm-up on mainnet ETH/USD): v6 never ran on it with this variant; EXP-022 and EXP-023 stopped at dev;
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
| 2022 | +7.6% | -19.9% | -27.5 | 21.5% → 33.9% |
| 2023 | +32.2% | +26.7% | -5.5 | 13.9% → 19.5% |
| 2024 | +36.4% | +43.5% | +7.1 | 26.7% → 19.8% |
| 2025 | +16.3% | +6.0% | -10.3 | 26.9% → 37.7% |
| 2026-01..09-17 | +18.7% | +11.3% | -7.4 | 12.0% → 21.3% |

Wins 1/5, median -7.42 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +20.2% | 4.0% | -32.6% | 0.29 | 0.12 | $68.2k | $0.22k | 152 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +137.7% | 25.0% | -17.3% | 1.27 | 1.44 | $72.2k | $0.42k | 97 |

Verdict: **dropped-at-dev** — ETH fails (CAGR 4.0% vs 14.0%, Calmar 0.12, max DD 9.8 pts deeper, wins 1/5; 2022 −27.5 pts); WBTC passes on its own (CAGR 25.0% vs 17.3%, Calmar 1.44 vs 0.97). Why ETH fails and WBTC wins was not diagnosed (mean F 0.70 vs 0.65, so it is deployed about as often as v6, at different times); whether the WBTC result is signal or luck was not tested. The rule requires both assets. Holdout not run.

## Deviations

- Before this file the signal-only F series of the four regimes were generated once on ETH/USDC 2021-2026 (mean F,
  correlation with v6's F, number of F changes) to check the code runs and the signals differ; no backtest, no P&L.
