# EXP-035: EMA/Donchian consensus regime (v6.26) judged standalone (v6.26r)

- Jira: QUAN-887
- Status: holdout-fail
- Pre-registration commit: d3559e1 · Result commit: ea4bd27
- Re-judged from EXP-031; level: standalone (README *Success levels*)
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

EXP-031 failed the improvement rule only on WBTC (CAGR 12.8% vs 17.3%, Calmar 0.72 vs 0.97); ETH Calmar 0.68, max DD −20.9%; WBTC max DD −17.8%; ETH positive in all five years.

## Change

`REGIME = "max_ed"` (variant `AA`), exactly EXP-031's definition. No change to the code since EXP-031.

## Pre-registration

Pre-registered together with EXP-032..035.

- Development (observed before this file, in the original experiment; not re-run): ETH/USDC 0.05% continuous 2022-01-01..2026-09-17 and yearly
  segments, WBTC/USDC 0.3% continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, numbers of all three reported):
  - H1 Arbitrum WETH/USDC 0.05% `0xc6962004f452be9203591991d15f6b388e09e8d0` continuous 2024-01-01..2025-07-23 (EMA warm-up on mainnet ETH/USD);
  - H2 Base USDC/WETH 0.05% continuous 2024-01-01..2026-09-17; H3 Base USDC/cbBTC 0.05% continuous 2025-01-01..2026-09-17.
  The variant never ran on these pools. Honest limit: H1 and H2 share mainnet ETH's price path; the clean forward window
  (2026-09-18..12-31) does not exist yet.
- Success rule (standalone, README *Success levels*; Calmar = CAGR / |max DD|, daily equity net of price impact):
  - Dev: continuous ETH and WBTC Calmar ≥ 0.60 and max DD no deeper than −30%; ETH positive in ≥ 4 of 5 yearly segments. Else `dropped-at-dev`.
  - Holdout: total return > 0 on all three pools **and** Calmar ≥ 0.50 on at least 2 of the 3 **and** max DD no deeper than −35% on all three → `holdout-pass` (standalone), else `holdout-fail`.

## Result

Holdout, one continuous run per pool, `A` and the variant in the same invocation:

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| Arbitrum WETH v6 | +57.0% | 33.6% | -25.1% | 1.24 | 1.34 | $40.8k | $0.30k | 47 |
| Arbitrum WETH this | +56.3% | 33.2% | -26.2% | 1.17 | 1.27 | $41.5k | $0.37k | 44 |
| Base WETH v6 | +55.9% | 17.8% | -28.1% | 0.76 | 0.63 | $43.1k | $3.96k | 83 |
| Base WETH this | +38.2% | 12.7% | -29.4% | 0.57 | 0.43 | $50.3k | $4.18k | 69 |
| Base cbBTC v6 | +22.3% | 12.5% | -15.7% | 0.93 | 0.79 | $15.9k | $0.43k | 40 |
| Base cbBTC this | +18.1% | 10.2% | -21.4% | 0.76 | 0.48 | $16.5k | $0.49k | 35 |

Verdict: **holdout-fail** (standalone) — Dev (from EXP-031, not re-run): ETH Calmar 0.68, max DD -20.9%; WBTC Calmar 0.72, max DD -17.8%; ETH positive in 5/5 yearly segments → dev passes the standalone screen. Holdout: Calmar ≥ 0.50 on 1 of 3 pools (Arbitrum WETH Calmar 1.267 (v6 1.337); Base WETH Calmar 0.432 (v6 0.634); Base cbBTC Calmar 0.478 (v6 0.795)); total return > 0 on 3/3; worst max DD -29.4%.

Reading: Arbitrum 1.267 (v6 1.337) passes; Base WETH 0.432 and cbBTC 0.478 miss the 0.50 threshold; the consensus rule gave up the Base ETH gain that EMA alone earned.

## Deviations

- The standalone rule was written on 2026-10-02 after the dev results of EXP-024, 028, 030 and 031 were seen (all four were `dropped-at-dev` under the improvement rule). Its thresholds (Calmar 0.60 / 0.50, max DD −30% / −35%) are v6's own levels rounded down, not fitted to these candidates; the holdout is the part not yet seen.
