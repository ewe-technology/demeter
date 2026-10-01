# EXP-034: volatility-scaled ladder width (v6.25) judged standalone (v6.25r)

- Jira: QUAN-___
- Status: holdout-pass
- Pre-registration commit: d3559e1 · Result commit: ______
- Re-judged from EXP-030; level: standalone (README *Success levels*)
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

EXP-030 failed the improvement rule on CAGR (ETH 13.7% vs 14.0%, WBTC 10.9% vs 17.3%) but its ETH Calmar is 0.69 with max DD −19.9% and WBTC Calmar 0.61 with max DD −17.8%; it is the only candidate that changes the LP mechanics (width) and not the signal.

## Change

`WIDTH_VOL = True` (variant `Z`), exactly EXP-030's definition. No change to the code since EXP-030.

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
| Arbitrum WETH this | +39.3% | 23.7% | -27.0% | 0.98 | 0.88 | $40.7k | $0.21k | 52 |
| Base WETH v6 | +55.9% | 17.8% | -28.1% | 0.76 | 0.63 | $43.1k | $3.96k | 83 |
| Base WETH this | +36.2% | 12.1% | -30.2% | 0.57 | 0.40 | $39.2k | $3.92k | 87 |
| Base cbBTC v6 | +22.3% | 12.5% | -15.7% | 0.93 | 0.79 | $15.9k | $0.43k | 40 |
| Base cbBTC this | +17.5% | 9.9% | -16.0% | 0.74 | 0.62 | $20.3k | $0.47k | 44 |

Verdict: **holdout-pass** (standalone) — Dev (from EXP-030, not re-run): ETH Calmar 0.69, max DD -19.9%; WBTC Calmar 0.61, max DD -17.8%; ETH positive in 5/5 yearly segments → dev passes the standalone screen. Holdout: Calmar ≥ 0.50 on 2 of 3 pools (Arbitrum WETH Calmar 0.878 (v6 1.337); Base WETH Calmar 0.400 (v6 0.634); Base cbBTC Calmar 0.617 (v6 0.795)); total return > 0 on 3/3; worst max DD -30.2%.

Reading: standalone pass with the thinnest quality: Calmar is below v6's on all three pools (0.878/0.400/0.617 vs 1.337/0.634/0.795) and total return gains vs v6 are negative on all three. It clears the absolute bar (Calmar ≥ 0.50 on Arbitrum and cbBTC, all returns positive, worst max DD −30.2%) but is a weaker strategy than v6 wherever both ran.

## Deviations

- The standalone rule was written on 2026-10-02 after the dev results of EXP-024, 028, 030 and 031 were seen (all four were `dropped-at-dev` under the improvement rule). Its thresholds (Calmar 0.60 / 0.50, max DD −30% / −35%) are v6's own levels rounded down, not fitted to these candidates; the holdout is the part not yet seen.
