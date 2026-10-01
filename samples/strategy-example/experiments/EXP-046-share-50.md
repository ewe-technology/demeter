# EXP-046: ETH value share fixed at 50% (ablation of the EMA100 share rule) (v6.33)

- Jira: QUAN-___
- Status: holdout-pass
- Pre-registration commit: 203850a · Result commit: ______
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

v6 sets the ladder's ETH share to 70% above EMA100 and 50% below: a directional tilt on top of the F engine, which already decides how much is deployed. EXP-029 (graded share) was indistinguishable from v6, so the tilt may not matter. A 50% ladder holds less ETH on the way up, so it suffers less upside IL (75% of v6's IL comes from rallies through the ladder, EXP-006) and earns less on bull years.

## Change

`SHARE_ABOVE_EMA = 0.5` (variant `AI`): s = 0.5 in both trend states (SHARE_BELOW_EMA is already 0.5). F, ladder, thresholds identical to v6.

## Pre-registration

Pre-registered together with EXP-044..047 (four small structural LP-mechanic changes to v6, one constant each, none searched; EXP-046 is an ablation) and run in the same invocations as `A`. Both success levels are judged from the same runs; all four results are reported.

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and
  continuous 2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant; only if dev passes at least one level; numbers of all windows reported):
  - H1 Arbitrum WETH/USDC 0.05% `0xc6962004f452be9203591991d15f6b388e09e8d0` continuous 2024-01-01..2025-07-23 (EMA warm-up on mainnet ETH/USD);
  - H2 Base USDC/WETH 0.05% continuous 2024-01-01..2026-09-17; H3 Base USDC/cbBTC 0.05% continuous 2025-01-01..2026-09-17;
  - H4 **out-of-time**: WBTC/USDC 0.3% `0x99ac8ca7087fa4a2a1fb6357269965a2014abc35` 2022-01-01..2022-10-31, the bear window before the BTC dev window (Binance BTCUSDT warm-up, `BINANCE_WARM=1`);
  - H5 reported, not judged: ETH/USDC 0.05% mainnet out-of-time 2021-05-06..2021-12-31 (bull; the pool's first day is the start, warm-up from Binance ETHUSDT).
  The variant never ran on these windows. Honest limit: H1-H3 share the dev window's ETH/BTC price paths (other pools and chains); H4 is the only judged window with a different time period.
- Success rules (variant vs v6 `A`, daily equity net of price impact, Calmar = CAGR / |max DD|; two levels, README *Success levels*; the same runs decide both):
  - Improvement: dev: continuous ETH and WBTC CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper, ETH yearly wins ≥ 3 of 5.
    Holdout (H1-H3): on at least 2 of 3 CAGR above v6's **and** Calmar ≥ v6's (if v6's CAGR is negative: CAGR above and max DD not more than 3 pts deeper) **and**
    max DD no more than 3 pts deeper, **and** on the third pool Calmar ≥ v6's − 0.2; **and** H4 total return not below v6's by more than 3 pts → `holdout-pass`.
  - Standalone: dev: continuous ETH and WBTC Calmar ≥ 0.60 and max DD no deeper than −30%, ETH positive in ≥ 4 of 5 yearly segments.
    Holdout: H1-H3 total return > 0 on all three, Calmar ≥ 0.50 on at least 2 of 3, max DD no deeper than −35% on all three; **and** H4 total return > 0 with max DD no deeper than −35% → `holdout-pass` (standalone).
  - Dev failing both levels → `dropped-at-dev`; the holdout is run (once) when dev passes at least one level, and each level is judged on it separately.

## Result

Development (`A` and the variant in each invocation):

| test | v6 | this | gain | max DD v6 → this |
|---|---|---|---|---|
| 2022 | +7.6% | +13.6% | +5.9 | 21.5% → 19.3% |
| 2023 | +32.2% | +26.1% | -6.1 | 13.9% → 9.8% |
| 2024 | +36.4% | +29.2% | -7.2 | 26.7% → 22.5% |
| 2025 | +16.3% | +13.0% | -3.3 | 26.9% → 23.4% |
| 2026-01..09-17 | +18.7% | +18.2% | -0.5 | 12.0% → 12.0% |

Wins 1/5, median -3.29 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +84.9% | 13.9% | -18.7% | 0.80 | 0.75 | $84.5k | $0.27k | 147 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +65.1% | 13.8% | -12.3% | 1.03 | 1.12 | $46.9k | $0.40k | 106 |

Holdout (`A` and the variant in the same invocation, one continuous run per window):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| Arbitrum WETH v6 | +57.0% | 33.6% | -25.1% | 1.24 | 1.34 | $40.8k | $0.30k | 47 |
| Arbitrum WETH this | +45.2% | 27.1% | -20.6% | 1.25 | 1.31 | $34.1k | $0.20k | 47 |
| Base WETH v6 | +55.9% | 17.8% | -28.1% | 0.76 | 0.63 | $43.1k | $3.96k | 83 |
| Base WETH this | +48.2% | 15.6% | -22.3% | 0.80 | 0.70 | $40.1k | $2.16k | 83 |
| Base cbBTC v6 | +22.3% | 12.5% | -15.7% | 0.93 | 0.79 | $15.9k | $0.43k | 40 |
| Base cbBTC this | +18.8% | 10.6% | -12.9% | 0.95 | 0.82 | $12.5k | $0.24k | 40 |
| WBTC 2022 out-of-time (H4) v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| WBTC 2022 out-of-time (H4) this | +2.6% | 3.2% | -11.1% | 0.25 | 0.29 | $14.1k | $0.03k | 17 |
| ETH 2021 bull (H5 reported) v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| ETH 2021 bull (H5 reported) this | +7.6% | 11.8% | -23.6% | 0.54 | 0.50 | $18.9k | $2.10k | 37 |

Verdict: **holdout-pass** (standalone; improvement level fails) — dev: the improvement rule fails on CAGR (ETH 13.9% vs 14.0%, WBTC 13.8% vs 17.3%, ETH wins 1/5) while risk-adjusted it is better than v6 on both assets (ETH Calmar 0.75 vs 0.61, max DD −18.7% vs −22.8%; WBTC Calmar 1.12 vs 0.97, max DD −12.3% vs −17.8%; ETH positive in 5/5 segments). Holdout: Calmar 1.31 / 0.70 / 0.82 (≥ 0.50 on 3 of 3), all returns positive, worst max DD −22.3%, H4 (WBTC 2022 out-of-time) +2.6% vs v6 +2.4% (max DD −11.1% vs −12.5%). Improvement level on the holdout: CAGR below v6's on all three pools, so it fails by construction. Reading: a lower-risk, lower-return v6: Calmar above v6's on Base WETH (0.70 vs 0.63), Base cbBTC (0.82 vs 0.79), H4 (0.29 vs 0.23) and H5 ETH 2021 bull (0.50 vs 0.23, reported not judged), a little below on Arbitrum (1.31 vs 1.34), and max DD shallower on every window. The EMA100 tilt (70% ETH above) adds return and risk in the same proportion; a Calmar-based re-judge on a fresh holdout is the natural next step (the v6.1r / v6.6r precedent).

## Deviations

- The code was smoke-tested on a 3.5-week window (2023-06-01..06-25) and v6 (`A`) 2026-01-01..09-17 re-run after the edit reproduces +18.706% exactly; those short runs are not evidence. The four mechanisms were chosen after batches 1-4 showed that signal changes (regime lines) do not beat v6 out-of-time, so this batch changes LP mechanics near v6 instead. The H4/H5 out-of-time windows were added to the generator's holdout after EXP-040..043 showed that a bull-market dev fit can lose them.
