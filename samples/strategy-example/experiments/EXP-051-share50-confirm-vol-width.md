# EXP-051: ETH share 50% + exit confirmation + volatility-scaled width (v6.38)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

The three mechanisms that each passed a holdout without changing the regime signal, stacked: composition (EXP-046), exit timing (EXP-044) and range width (EXP-030). The most complete LP-mechanics variant of v6 tested in this series; it tests whether the three effects add or interfere.

## Change

`SHARE_ABOVE_EMA = 0.5`, `EXIT_CONFIRM = 2`, `WIDTH_VOL = True` (variant `AN`), the three definitions unchanged. Everything else identical to v6.

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

(not run)

## Deviations

- The combinations were chosen after seeing EXP-046's holdout (Calmar above v6's on two of three pools, lower CAGR, shallower max DD) and the components' results (EXP-030/031/044); the combined variants themselves were not run before this file except for a 3.5-week smoke test (2023-06-01..06-25) that checks they execute. These four are variations of one family (shared signal, shared pools): they do not count as independent evidence of each other.
