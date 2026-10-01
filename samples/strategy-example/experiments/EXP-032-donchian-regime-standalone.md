# EXP-032: Donchian-midpoint regime line (v6.19) judged standalone (v6.19r)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Re-judged from EXP-024; level: standalone (README *Success levels*)
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending.

## Hypothesis

EXP-024 failed the improvement rule only on WBTC (CAGR 14.7% vs 17.3%, Calmar 0.87 vs 0.97); its absolute dev numbers are v6-family level (ETH Calmar 0.74, max DD −20.4%; WBTC Calmar 0.87, max DD −16.8%; ETH positive in all five years). Question here: is it a good strategy by itself on fresh pools.

## Change

`REGIME = "donchian"` (variant `S`), exactly EXP-024's definition. No change to the code since EXP-024.

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

(not run)

## Deviations

- The standalone rule was written on 2026-10-02 after the dev results of EXP-024, 028, 030 and 031 were seen (all four were `dropped-at-dev` under the improvement rule). Its thresholds (Calmar 0.60 / 0.50, max DD −30% / −35%) are v6's own levels rounded down, not fitted to these candidates; the holdout is the part not yet seen.
