# EXP-010: v6.6 half ladder re-registered under a Calmar rule (v6.6r)

- Version: v6.6r (same variant as EXP-006 / v6.6, new success rule)
- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______

## Why a re-registration

EXP-006 was dropped at dev only by its drawdown guard: continuous ETH +173% vs +85%, Sharpe 0.90 vs 0.73, Calmar
0.82 vs 0.61, max DD −28.9% vs a floor of −27.8%. On 2026-09-30 Dino asked to judge these candidates on
risk-adjusted return (Calmar) instead and send them to the holdout. The rule changed **after** the dev data was
seen, so the dev stage is not evidence; the holdout is the test.

## Change

Identical to EXP-006: `HALF_LADDER = True`, candidate `G` in `v6_validate.py`.

## Pre-registration

- Development (already seen, EXP-006): ETH yearly wins 4/5, median +0.7 pts; continuous ETH Calmar 0.82 vs 0.61.
  Under the new rule (wins ≥ 3/5, median > 0, continuous ETH Calmar ≥ v6's) it passes.
- Holdout (run once): WBTC/WETH 0.05% mainnet (`0x4585fe77…`), ETH base, WBTC quote, 2 WBTC; yearly segments
  2023, 2024, 2025, 2026-01-01..09-17 plus the continuous 2022-11-01..2026-09-17. v6 (A), EXP-009's candidate (B)
  and this (G) in the same invocation.
- Success rule on the holdout: return wins in ≥ 3 of 4 yearly segments **and** continuous Calmar ≥ v6's →
  `holdout-pass`, else `holdout-fail`.

## Result

Verdict:

## Deviations

- Rule changed after dev results were known. Shares the holdout with EXP-009 (two candidates, one holdout).
- The holdout pool's daily closes (other orientation) were looked at before EXP-001; see EXP-001 Deviations.
