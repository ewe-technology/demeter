# EXP-050: ETH share 50% + EMA/Donchian consensus regime (v6.37)

- Jira: QUAN-___
- Status: dropped-at-dev
- Pre-registration commit: 7ac9e72 · Result commit: ______
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

EXP-031's consensus regime (armed only above both EMA(n) and Donchian mid(n)) was above v6 on the 2022 out-of-time window (+3.6% vs +2.4%) and below it on Base ETH and cbBTC; the 50% share lowers the ETH exposure that cost it on those pools' falls. Stacked: later entries and earlier exits with a neutral composition.

## Change

`SHARE_ABOVE_EMA = 0.5` and `REGIME = "max_ed"` (variant `AM`), the two definitions unchanged. Everything else identical to v6.

## Pre-registration

Pre-registered together with EXP-048..051 (four combinations of the ETH-share-50% change of EXP-046 with one other mechanism that passed a holdout, no new code, no constants searched) and run in the same invocations as `A`. Both success levels are judged from the same runs; all four results are reported.

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
| 2022 | +7.6% | +21.4% | +13.8 | 21.5% → 19.1% |
| 2023 | +32.2% | +30.0% | -2.2 | 13.9% → 10.4% |
| 2024 | +36.4% | +25.6% | -10.7 | 26.7% → 23.8% |
| 2025 | +16.3% | +13.1% | -3.2 | 26.9% → 23.4% |
| 2026-01..09-17 | +18.7% | +5.5% | -13.2 | 12.0% → 21.3% |

Wins 1/5, median -3.18 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +81.0% | 13.4% | -17.7% | 0.77 | 0.76 | $95.9k | $0.47k | 129 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +42.2% | 9.5% | -17.8% | 0.70 | 0.53 | $42.2k | $0.41k | 101 |

Verdict: **dropped-at-dev** (both levels) — ETH Calmar 0.76 (CAGR 13.4% vs 14.0%, max DD −17.7%, wins 1/5) but WBTC CAGR 9.5% vs 17.3% and Calmar 0.53 < 0.60 (max DD −17.8%); the improvement rule fails on CAGR and the standalone screen on WBTC Calmar. Holdout not run.

## Deviations

- The combinations were chosen after seeing EXP-046's holdout (Calmar above v6's on two of three pools, lower CAGR, shallower max DD) and the components' results (EXP-030/031/044); the combined variants themselves were not run before this file except for a 3.5-week smoke test (2023-06-01..06-25) that checks they execute. These four are variations of one family (shared signal, shared pools): they do not count as independent evidence of each other.
