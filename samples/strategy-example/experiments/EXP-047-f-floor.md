# EXP-047: F never below 25% (one refill stage always deployed) (v6.34)

- Jira: QUAN-___
- Status: dropped-at-dev
- Pre-registration commit: 203850a · Result commit: ______
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

When all four accounts are out (F = 0, e.g. ETH 2022 H2 and 2025 falls) v6's LP earns no fees at all, the defensive effect and its cost. Keeping the first refill stage (25% of equity) deployed always lets fees accrue through bears and chop at the price of 25% exposure to the fall.

## Change

`F_FLOOR = 0.25` (variant `AJ`): F = max(F, 0.25) in the daily frame. Everything else identical to v6.

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
| 2022 | +7.6% | -2.5% | -10.1 | 21.5% → 26.8% |
| 2023 | +32.2% | +36.0% | +3.8 | 13.9% → 13.3% |
| 2024 | +36.4% | +35.7% | -0.7 | 26.7% → 27.0% |
| 2025 | +16.3% | +11.3% | -5.0 | 26.9% → 26.3% |
| 2026-01..09-17 | +18.7% | +8.9% | -9.9 | 12.0% → 14.7% |

Wins 1/5, median -4.99 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +53.7% | 9.6% | -22.8% | 0.55 | 0.42 | $85.1k | $0.14k | 123 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +87.7% | 17.6% | -15.2% | 1.03 | 1.16 | $69.6k | $0.54k | 81 |

Verdict: **dropped-at-dev** (both levels) — ETH fails: CAGR 9.6% vs 14.0%, Calmar 0.42, wins 1/5, positive in 4/5 segments; WBTC is better than v6 (CAGR 17.6% vs 17.3%, Calmar 1.16 vs 0.97, max DD −15.2%) but the standalone screen needs both assets at Calmar ≥ 0.60. A permanent 25% deployment costs ETH more in the falls than the fees it earns. Holdout not run.

## Deviations

- The code was smoke-tested on a 3.5-week window (2023-06-01..06-25) and v6 (`A`) 2026-01-01..09-17 re-run after the edit reproduces +18.706% exactly; those short runs are not evidence. The four mechanisms were chosen after batches 1-4 showed that signal changes (regime lines) do not beat v6 out-of-time, so this batch changes LP mechanics near v6 instead. The H4/H5 out-of-time windows were added to the generator's holdout after EXP-040..043 showed that a bull-market dev fit can lose them.
