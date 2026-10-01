# EXP-049: ETH share 50% + volatility-scaled ladder width (v6.36)

- Jira: QUAN-901
- Status: holdout-pass
- Pre-registration commit: 7ac9e72 · Result commit: 4773975
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

EXP-030's width rule passed the holdout with lower Calmar than v6; EXP-046's share rule passed with higher Calmar on two pools. Width sets how often the ladder exits; share sets how much ETH it holds when it does. Stacked: a less ETH-heavy ladder whose range follows the month's volatility.

## Change

`SHARE_ABOVE_EMA = 0.5` and `WIDTH_VOL = True` (variant `AL`), the two definitions unchanged (σ√30, clamp 10-30%, 5% grid). Everything else identical to v6.

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
| 2022 | +7.6% | +9.3% | +1.7 | 21.5% → 18.6% |
| 2023 | +32.2% | +21.3% | -10.9 | 13.9% → 11.7% |
| 2024 | +36.4% | +12.6% | -23.8 | 26.7% → 25.1% |
| 2025 | +16.3% | +15.2% | -1.1 | 26.9% → 25.3% |
| 2026-01..09-17 | +18.7% | +16.7% | -2.0 | 12.0% → 12.7% |

Wins 1/5, median -2.04 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +82.7% | 13.6% | -16.9% | 0.84 | 0.81 | $84.2k | $0.28k | 148 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +40.0% | 9.1% | -13.1% | 0.72 | 0.69 | $59.9k | $0.58k | 121 |

Holdout (`A` and the variant in the same invocation, one continuous run per window):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| Arbitrum WETH v6 | +57.0% | 33.6% | -25.1% | 1.24 | 1.34 | $40.8k | $0.30k | 47 |
| Arbitrum WETH this | +27.9% | 17.1% | -24.0% | 0.86 | 0.71 | $32.9k | $0.15k | 52 |
| Base WETH v6 | +55.9% | 17.8% | -28.1% | 0.76 | 0.63 | $43.1k | $3.96k | 83 |
| Base WETH this | +25.8% | 8.8% | -26.9% | 0.51 | 0.33 | $33.4k | $2.32k | 87 |
| Base cbBTC v6 | +22.3% | 12.5% | -15.7% | 0.93 | 0.79 | $15.9k | $0.43k | 40 |
| Base cbBTC this | +15.2% | 8.7% | -13.9% | 0.76 | 0.62 | $17.9k | $0.32k | 44 |
| WBTC 2022 out-of-time (H4) v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| WBTC 2022 out-of-time (H4) this | +1.9% | 2.3% | -11.8% | 0.21 | 0.19 | $13.4k | $0.03k | 18 |
| ETH 2021 bull (H5 reported) v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| ETH 2021 bull (H5 reported) this | +6.0% | 9.2% | -24.5% | 0.44 | 0.38 | $17.9k | $2.10k | 38 |

Verdict: **holdout-pass** (standalone; improvement level fails; weak) — dev: improvement fails (ETH CAGR 13.6% vs 14.0%, WBTC CAGR 9.1% vs 17.3%, wins 1/5); standalone screen passes (ETH Calmar 0.81, WBTC 0.69, max DDs −16.9% / −13.1%, ETH positive 5/5). Holdout: Calmar 0.71 / 0.33 / 0.62 (≥ 0.50 on 2 of 3, Base WETH fails), all returns positive, worst max DD −26.9%, H4 +1.9% vs v6 +2.4%. Returns are well below v6's on all pools (CAGR 17.1 / 8.8 / 8.7% vs 33.6 / 17.8 / 12.5%) and Calmar is below v6's on all three; it passes the absolute bar only. Not recommended over EXP-046 or EXP-048.

## Deviations

- The combinations were chosen after seeing EXP-046's holdout (Calmar above v6's on two of three pools, lower CAGR, shallower max DD) and the components' results (EXP-030/031/044); the combined variants themselves were not run before this file except for a 3.5-week smoke test (2023-06-01..06-25) that checks they execute. These four are variations of one family (shared signal, shared pools): they do not count as independent evidence of each other.
