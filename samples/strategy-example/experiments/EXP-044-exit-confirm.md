# EXP-044: range exit needs two consecutive daily checks outside the ladder (v6.31)

- Jira: QUAN-___
- Status: holdout-pass
- Pre-registration commit: 203850a · Result commit: ______
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

EXP-023 decomposed v6's IL: 86% comes from the 19 builds that ended with the price outside the ±20% span. A daily check that sees the price outside the ladder triggers a full rebuild (burn, swap to the share, re-mint) even when the move was a one-day spike that reverts. Requiring the price to be outside at two consecutive daily checks removes those spike exits and their round-trip swap costs; the cost is one more day with a one-sided ladder earning no fees.

## Change

`EXIT_CONFIRM = 2` (variant `AG`): `check_rebalance` counts consecutive daily checks with the price outside the ladder and allows the rebuild only at the second; a check back inside resets the count. The F-follow rebuild, the lower stop and everything else identical to v6.

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
| 2022 | +7.6% | +8.7% | +1.1 | 21.5% → 21.5% |
| 2023 | +32.2% | +18.6% | -13.6 | 13.9% → 14.5% |
| 2024 | +36.4% | +34.5% | -1.9 | 26.7% → 27.0% |
| 2025 | +16.3% | +25.8% | +9.6 | 26.9% → 23.0% |
| 2026-01..09-17 | +18.7% | +14.0% | -4.7 | 12.0% → 12.9% |

Wins 2/5, median -1.90 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +99.1% | 15.8% | -19.8% | 0.81 | 0.80 | $95.9k | $0.29k | 143 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +79.9% | 16.3% | -17.2% | 0.96 | 0.95 | $60.0k | $0.69k | 106 |

Holdout (`A` and the variant in the same invocation, one continuous run per window):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| Arbitrum WETH v6 | +57.0% | 33.6% | -25.1% | 1.24 | 1.34 | $40.8k | $0.30k | 47 |
| Arbitrum WETH this | +57.1% | 33.6% | -25.7% | 1.26 | 1.31 | $43.8k | $0.30k | 46 |
| Base WETH v6 | +55.9% | 17.8% | -28.1% | 0.76 | 0.63 | $43.1k | $3.96k | 83 |
| Base WETH this | +58.5% | 18.5% | -29.1% | 0.80 | 0.64 | $48.4k | $3.93k | 80 |
| Base cbBTC v6 | +22.3% | 12.5% | -15.7% | 0.93 | 0.79 | $15.9k | $0.43k | 40 |
| Base cbBTC this | +21.2% | 11.9% | -15.8% | 0.89 | 0.75 | $15.7k | $0.42k | 40 |
| WBTC 2022 out-of-time (H4) v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| WBTC 2022 out-of-time (H4) this | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| ETH 2021 bull (H5 reported) v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| ETH 2021 bull (H5 reported) this | -6.9% | -10.3% | -30.7% | -0.10 | -0.34 | $21.7k | $3.70k | 37 |

Verdict: **holdout-pass** (standalone; improvement level fails) — dev: the improvement rule fails (ETH CAGR 15.8% vs 14.0%, Calmar 0.80 vs 0.61, max DD −19.8% vs −22.8%, but WBTC CAGR 16.3% vs 17.3%, Calmar 0.95 vs 0.97 and ETH wins 2/5) while the standalone screen passes (ETH Calmar 0.80, WBTC Calmar 0.95, max DDs −19.8% / −17.2%, ETH positive in 5/5 segments). Holdout: Calmar 1.31 / 0.64 / 0.75 on Arbitrum / Base WETH / Base cbBTC (≥ 0.50 on 3 of 3), all returns positive, worst max DD −29.1%, H4 (WBTC 2022 out-of-time) +2.4% = v6. Improvement level on the holdout: CAGR above v6's on 1 of 3 pools (Base WETH 18.5% vs 17.8%), so it fails. Reading: statistically indistinguishable from v6 on every judged window (Calmar within ±0.04, H4 identical because no exit occurred); H5 (reported, not judged) ETH 2021 bull: −6.9% vs v6 +4.5%, the confirmation day costs on the way up.

## Deviations

- The code was smoke-tested on a 3.5-week window (2023-06-01..06-25) and v6 (`A`) 2026-01-01..09-17 re-run after the edit reproduces +18.706% exactly; those short runs are not evidence. The four mechanisms were chosen after batches 1-4 showed that signal changes (regime lines) do not beat v6 out-of-time, so this batch changes LP mechanics near v6 instead. The H4/H5 out-of-time windows were added to the generator's holdout after EXP-040..043 showed that a bull-market dev fit can lose them.
