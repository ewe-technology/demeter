# EXP-048: ETH share 50% + range exit needs two consecutive daily checks (v6.35)

- Jira: QUAN-900
- Status: holdout-pass
- Pre-registration commit: 7ac9e72 · Result commit: 4773975
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

EXP-046 lowered risk by removing the 70% ETH tilt (shallower max DD on every window, CAGR lower); EXP-044 removed one-day spike exits without changing the holdout Calmar. The two act on different parts of the loop (composition vs exit timing), so their effects should add: a lower-ETH ladder that does not rebuild on spikes.

## Change

`SHARE_ABOVE_EMA = 0.5` and `EXIT_CONFIRM = 2` (variant `AK`), the two definitions unchanged. Everything else identical to v6.

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
| 2022 | +7.6% | +14.8% | +7.2 | 21.5% → 19.3% |
| 2023 | +32.2% | +16.5% | -15.7 | 13.9% → 10.1% |
| 2024 | +36.4% | +28.0% | -8.4 | 26.7% → 22.8% |
| 2025 | +16.3% | +18.4% | +2.2 | 26.9% → 20.8% |
| 2026-01..09-17 | +18.7% | +14.6% | -4.1 | 12.0% → 12.9% |

Wins 2/5, median -4.14 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +95.7% | 15.3% | -16.1% | 0.89 | 0.95 | $86.8k | $0.24k | 143 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +61.3% | 13.1% | -11.8% | 0.99 | 1.11 | $46.0k | $0.39k | 106 |

Holdout (`A` and the variant in the same invocation, one continuous run per window):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| Arbitrum WETH v6 | +57.0% | 33.6% | -25.1% | 1.24 | 1.34 | $40.8k | $0.30k | 47 |
| Arbitrum WETH this | +44.9% | 26.9% | -20.8% | 1.26 | 1.29 | $35.2k | $0.20k | 46 |
| Base WETH v6 | +55.9% | 17.8% | -28.1% | 0.76 | 0.63 | $43.1k | $3.96k | 83 |
| Base WETH this | +49.1% | 15.9% | -23.0% | 0.83 | 0.69 | $41.0k | $2.11k | 80 |
| Base cbBTC v6 | +22.3% | 12.5% | -15.7% | 0.93 | 0.79 | $15.9k | $0.43k | 40 |
| Base cbBTC this | +18.0% | 10.2% | -12.9% | 0.91 | 0.79 | $12.4k | $0.24k | 40 |
| WBTC 2022 out-of-time (H4) v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| WBTC 2022 out-of-time (H4) this | +2.6% | 3.2% | -11.1% | 0.25 | 0.29 | $14.1k | $0.03k | 17 |
| ETH 2021 bull (H5 reported) v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| ETH 2021 bull (H5 reported) this | -1.4% | -2.1% | -23.6% | 0.07 | -0.09 | $21.4k | $2.10k | 37 |

Verdict: **holdout-pass** (standalone; improvement level fails) — dev: the improvement rule fails on WBTC CAGR and wins (WBTC CAGR 13.1% vs 17.3%, ETH wins 2/5) while the standalone screen passes with the best ETH result of the series (ETH CAGR 15.3% vs 14.0%, Calmar 0.95 vs 0.61, max DD −16.1% vs −22.8%; WBTC Calmar 1.11 vs 0.97, max DD −11.8% vs −17.8%; ETH positive in 5/5 segments). Holdout: Calmar 1.29 / 0.69 / 0.79 on Arbitrum / Base WETH / Base cbBTC (≥ 0.50 on 3 of 3; v6 1.34 / 0.63 / 0.79), all returns positive, worst max DD −23.0%, H4 (WBTC 2022 out-of-time) +2.6% vs v6 +2.4%. Improvement level on the holdout: CAGR below v6's on all three pools (26.9 / 15.9 / 10.2% vs 33.6 / 17.8 / 12.5%), so it fails. Reading: v6's holdout Calmar with max DD 2.8-5.1 pts shallower on each pool and total return 4-12 pts lower; H5 (reported, not judged) ETH 2021 bull −1.4% vs v6 +4.5%, the exit confirmation's cost on the way up (EXP-044 −6.9%) only partly offset by the 50% share.

## Deviations

- The combinations were chosen after seeing EXP-046's holdout (Calmar above v6's on two of three pools, lower CAGR, shallower max DD) and the components' results (EXP-030/031/044); the combined variants themselves were not run before this file except for a 3.5-week smoke test (2023-06-01..06-25) that checks they execute. These four are variations of one family (shared signal, shared pools): they do not count as independent evidence of each other.
