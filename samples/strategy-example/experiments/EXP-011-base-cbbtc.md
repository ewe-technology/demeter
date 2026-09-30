# EXP-011: v6 and v6.4 on the Base cbBTC pool (go-live condition 5)

- Version: v6 / v6.4 on Base USDC/cbBTC 0.05% (validation, no new variant)
- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______

## Hypothesis

`V6_VALIDATION.md` go-live condition 5: the cbBTC "Growth" pool is unvalidated, and on mainnet WBTC/USDC 0.3%
(2022-11..2026-09, a mostly bullish window) v6 did not beat the plain valley LP (+85.6% vs +88.9%, max DD −17.8% vs
−20.0%). The deck's BTC product runs on Base USDC/cbBTC 0.05% (`0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef`, ~6,400
swaps a day). Two questions, both on data no test has seen:

1. Does v6 add anything over the plain valley LP on the pool it would actually run on?
2. Does EXP-004's cash yield (the one version that passed dev and holdout, on ETH) carry over to the BTC book?

## Change

None to the strategy. v6 (A), v6.4 cash yield (E, Base Aave v3 USDC rates) and the plain valley LP (bench grid)
on the Base cbBTC pool. EMA warm-up on mainnet WBTC/USDC before the Base window (cbBTC launched 2024-09).

## Pre-registration

- Data: Base USDC/cbBTC 0.05% minute data 2024-10-01..2026-09-17 (fetched after this commit with
  `samples/fetch_base_monthly.sh`), 100,000 USDC. Yearly segments 2025, 2026-01-01..09-17 and the continuous
  2025-01-01..2026-09-17 run.
- Rule 1 (v6 vs plain LP): v6's continuous Calmar ≥ the plain LP's **and** v6's max DD shallower → "v6 has value on
  cbBTC", else "no edge on cbBTC" (as on mainnet).
- Rule 2 (v6.4 vs v6): wins in both yearly segments and a higher continuous total → "cash yield confirmed on the
  BTC book", else "not confirmed".

## Result

Verdict:

## Deviations

- The pool's last day of swaps (count only) was sampled to pick the fee tier before this file.
