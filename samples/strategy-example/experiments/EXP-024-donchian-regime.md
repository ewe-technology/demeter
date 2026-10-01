# EXP-024: regime line = midpoint of the n-day Donchian channel instead of EMA(n) (v6.19)

- Jira: QUAN-___
- Status: dropped-at-dev
- Pre-registration commit: 5440347 · Result commit: ______
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

v6's exits and re-arms follow a lagging average. V6_VALIDATION shows the timing is the product (EXP-014: the F engine's timed exposure is worth about +$85k of v6's gain) and that it is sensitive to the line's speed (EMA spans ×0.8: 2022 −8.2% vs base +7.6%). The midpoint of the n-day high/low channel is a structurally different trend line (it reacts to the range edges, not to the average path) with the same lengths, so it tests whether the edge is specific to the EMA or to trend timing in general.

## Change

`REGIME = "donchian"` (variant `S`): each of the four virtual accounts (n = 90, 100, 110, 120) is armed while the daily close is above (max daily high over the last n days + min daily low over the last n days) / 2; daily high/low from the minute prices, current day included. Everything else identical to v6: exit/re-arm/stop/upper-rebuild/staged refill, F = mean of the accounts, the s rule on EMA100, ±20% valley ladder, daily 00:00 follow check.

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
| 2022 | +7.6% | +6.2% | -1.4 | 21.5% → 21.0% |
| 2023 | +32.2% | +42.6% | +10.4 | 13.9% → 14.3% |
| 2024 | +36.4% | +30.5% | -5.8 | 26.7% → 28.6% |
| 2025 | +16.3% | +36.3% | +20.1 | 26.9% → 21.1% |
| 2026-01..09-17 | +18.7% | +10.3% | -8.4 | 12.0% → 21.3% |

Wins 2/5, median -1.44 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +93.5% | 15.0% | -20.4% | 0.76 | 0.74 | $100.9k | $0.35k | 119 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +70.0% | 14.7% | -16.8% | 0.83 | 0.87 | $58.8k | $0.46k | 94 |

Verdict: **dropped-at-dev** — ETH passes (CAGR 15.0% vs 14.0%, Calmar 0.74 vs 0.61, max DD 2.4 pts shallower, fees $100.9k vs $86.5k with 119 rebuilds vs 147) but WBTC fails (CAGR 14.7% vs 17.3%, Calmar 0.87 vs 0.97) and ETH yearly wins are 2/5 (median −1.44 pts; the gains sit in 2023 and 2025, the losses in 2024 and 2026). The channel midpoint is a different trend line that happens to suit ETH 2023/2025, not an edge that carries to the second asset. Holdout not run.

## Deviations

- Before this file the signal-only F series of the four regimes were generated once on ETH/USDC 2021-2026 (mean F,
  correlation with v6's F, number of F changes) to check the code runs and the signals differ; no backtest, no P&L.
