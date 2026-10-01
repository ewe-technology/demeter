# EXP-032: Donchian-midpoint regime line (v6.19) judged standalone (v6.19r)

- Jira: QUAN-___
- Status: holdout-pass
- Pre-registration commit: d3559e1 · Result commit: ______
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

Holdout, one continuous run per pool, `A` and the variant in the same invocation:

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| Arbitrum WETH v6 | +57.0% | 33.6% | -25.1% | 1.24 | 1.34 | $40.8k | $0.30k | 47 |
| Arbitrum WETH this | +60.6% | 35.5% | -26.2% | 1.22 | 1.36 | $40.9k | $0.32k | 42 |
| Base WETH v6 | +55.9% | 17.8% | -28.1% | 0.76 | 0.63 | $43.1k | $3.96k | 83 |
| Base WETH this | +59.4% | 18.8% | -29.4% | 0.76 | 0.64 | $55.9k | $4.02k | 63 |
| Base cbBTC v6 | +22.3% | 12.5% | -15.7% | 0.93 | 0.79 | $15.9k | $0.43k | 40 |
| Base cbBTC this | +15.0% | 8.5% | -21.4% | 0.65 | 0.40 | $16.4k | $0.47k | 36 |

Verdict: **holdout-pass** (standalone) — Dev (from EXP-024, not re-run): ETH Calmar 0.74, max DD -20.4%; WBTC Calmar 0.87, max DD -16.8%; ETH positive in 5/5 yearly segments → dev passes the standalone screen. Holdout: Calmar ≥ 0.50 on 2 of 3 pools (Arbitrum WETH Calmar 1.356 (v6 1.337); Base WETH Calmar 0.639 (v6 0.634); Base cbBTC Calmar 0.400 (v6 0.795)); total return > 0 on 3/3; worst max DD -29.4%.

Reading: standalone pass, not an improvement on v6. On the two ETH pools it equals v6 (Arbitrum Calmar 1.356 vs 1.337, Base 0.639 vs 0.634); on Base cbBTC it is half of v6 (0.400 vs 0.795), the same WBTC/BTC weakness seen at dev. The pass margin is the cbBTC pool being the third one: the rule needs only two of three.

## Deviations

- The standalone rule was written on 2026-10-02 after the dev results of EXP-024, 028, 030 and 031 were seen (all four were `dropped-at-dev` under the improvement rule). Its thresholds (Calmar 0.60 / 0.50, max DD −30% / −35%) are v6's own levels rounded down, not fitted to these candidates; the holdout is the part not yet seen.
