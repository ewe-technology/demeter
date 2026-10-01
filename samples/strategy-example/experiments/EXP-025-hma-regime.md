# EXP-025: regime line = Hull MA(n) instead of EMA(n) (v6.20)

- Jira: QUAN-___
- Status: dropped-at-dev
- Pre-registration commit: 5440347 · Result commit: ______
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

An EMA of 90-120 days lags: v6's 2022 and 2025 gains come from exiting before the falls, and its worst drawdowns are falls it was deployed into (EXP-014 diagnostic). The Hull MA (Hull 2005) has far less lag at the same length, so exits and re-arms come earlier. Cost: more F changes (264 vs 151 days with a change on ETH 2022-26 in a signal-only check), i.e. more rebuilds and impact.

## Change

`REGIME = "hma"` (variant `T`): accounts n = 90, 100, 110, 120 armed while the daily close is above HMA(n) = WMA(2·WMA(close, n/2) − WMA(close, n), round(√n)) (WMAs with linear weights, daily closes). Everything else identical to v6.

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
| 2022 | +7.6% | -15.7% | -23.3 | 21.5% → 28.1% |
| 2023 | +32.2% | +22.1% | -10.1 | 13.9% → 12.1% |
| 2024 | +36.4% | +6.3% | -30.1 | 26.7% → 29.1% |
| 2025 | +16.3% | +5.8% | -10.5 | 26.9% → 18.7% |
| 2026-01..09-17 | +18.7% | +13.7% | -5.0 | 12.0% → 11.3% |

Wins 0/5, median -10.53 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +16.2% | 3.2% | -24.1% | 0.27 | 0.13 | $51.3k | $0.16k | 240 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +65.6% | 13.9% | -17.9% | 0.97 | 0.78 | $28.0k | $0.98k | 162 |

Verdict: **dropped-at-dev** — every test is worse: ETH CAGR 3.2% vs 14.0%, Calmar 0.13 vs 0.61, wins 0/5 (2022 −23.3 pts); WBTC Calmar 0.78 vs 0.97. The less lagged line flips often (240 rebuilds vs 147 on ETH) and LP fees fall to $51.3k from $86.5k: the ladder is out of the pool on the days it would earn. Mean F falls to 0.47 from 0.65: this signal is out of the pool far more often than v6's. Holdout not run.

## Deviations

- Before this file the signal-only F series of the four regimes were generated once on ETH/USDC 2021-2026 (mean F,
  correlation with v6's F, number of F changes) to check the code runs and the signals differ; no backtest, no P&L.
