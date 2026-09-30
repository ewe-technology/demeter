# EXP-011: v6 and v6.4 on the Base cbBTC pool (go-live condition 5)

- Version: v6 / v6.4 on Base USDC/cbBTC 0.05% (validation, no new variant)
- Jira: [QUAN-859](https://ewetechnology.atlassian.net/browse/QUAN-859)
- Status: holdout-pass (both rules)
- Pre-registration commit: 024436c · Result commit: 10011a7

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

Base USDC/cbBTC 0.05%, 100,000 USDC, Base Aave v3 USDC rates for v6.4:

| test | v6 | v6.4 (cash yield) | plain valley LP |
|---|---|---|---|
| 2025 | +9.3% | +11.3% | +5.8% |
| 2026-01..09-17 | +13.8% | +15.0% | −17.3% |

Continuous 2025-01-01..2026-09-17 (daily equity):

| run | total | CAGR | max DD | Sharpe | Calmar | fees (incl. interest) |
|---|---|---|---|---|---|---|
| v6 | +22.3% | 12.5% | −15.7% | 0.93 | 0.80 | $15.9k |
| v6.4 | +25.8% | 14.4% | −14.0% | 1.06 | 1.03 | $19.4k |
| plain valley LP | +6.8% | 3.9% | −25.8% | 0.29 | 0.15 | $27.4k |

Rule 1: **v6 has value on cbBTC** — Calmar 0.80 vs 0.15, max DD −15.7% vs −25.8%. The plain LP earns more fees
(always deployed) but gives it all back in 2026's decline; mean F was 0.58. On mainnet WBTC (a mostly bullish
window) v6 had shown no edge; this window has a real down leg and the defence shows.

Rule 2: **cash yield confirmed on the BTC book** — wins 2/2 (+2.0 and +1.2 pts), continuous +25.8% vs +22.3% with a
shallower drawdown.

Verdict: go-live condition 5 answered: the cbBTC Growth pool is a valid v6 venue, and v6.4 improves it.

## Deviations

- The pool's last day of swaps (count only) was sampled to pick the fee tier before this file.
