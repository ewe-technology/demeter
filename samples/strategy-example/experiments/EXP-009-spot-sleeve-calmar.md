# EXP-009: v6.1 spot sleeve re-registered under a Calmar rule (v6.1r)

- Version: v6.1r (same variant as EXP-001 / v6.1, new success rule)
- Jira: QUAN-___
- Status: holdout-fail
- Pre-registration commit: fd47677 · Result commit: see registry

## Why a re-registration

EXP-001 was dropped at dev only by the drawdown guard it registered (continuous ETH max DD no more than 5 pts worse
than v6): +198% vs +85%, Sharpe 0.86 vs 0.73, Calmar 0.78 vs 0.61, but max DD −33.6% vs −22.8%. On 2026-09-30 Dino
asked to judge these candidates on risk-adjusted return (Calmar) instead of an absolute drawdown budget, and to send
them to the holdout. The change of rule comes **after** the dev data was seen, so the dev stage below is not
evidence; the holdout is the test.

## Change

Identical to EXP-001: `SPOT_SLEEVE = 0.5`, candidate `B` in `v6_validate.py`.

## Pre-registration

- Development (already seen, EXP-001): ETH yearly wins 4/5, median +8.5 pts; continuous ETH Calmar 0.78 vs 0.61.
  Under the new rule (wins ≥ 3/5, median > 0, continuous ETH Calmar ≥ v6's) it passes.
- Holdout (run once): WBTC/WETH 0.05% mainnet (`0x4585fe77…`), ETH base, WBTC quote, 2 WBTC; yearly segments
  2023, 2024, 2025, 2026-01-01..09-17 plus the continuous 2022-11-01..2026-09-17. v6 (A), this (B) and EXP-010's
  candidate (G) in the same invocation. No strategy run has touched this pool.
- Success rule on the holdout: return wins in ≥ 3 of 4 yearly segments **and** continuous Calmar (CAGR / |max DD|,
  daily equity) ≥ v6's → `holdout-pass`, else `holdout-fail`.

## Result

Holdout, WBTC/WETH 0.05%, ETH base, WBTC quote (returns in WBTC), yearly reset from 2 WBTC:

| segment | v6 | v6.1r | v6.6r |
|---|---|---|---|
| 2023 | −15.2% | −19.9% | −15.5% |
| 2024 | −2.5% | −5.2% | −4.4% |
| 2025 | −23.3% | −27.0% | −22.2% |
| 2026-01..09-17 | −11.0% | −13.6% | −10.9% |

Continuous 2022-11-01..2026-09-17 (daily equity, WBTC):

| run | total | CAGR | max DD | Sharpe | Calmar |
|---|---|---|---|---|---|
| v6 | −8.7% | −2.3% | −26.1% | −0.17 | −0.088 |
| v6.1r (EXP-009) | −7.0% | −1.8% | −32.3% | −0.06 | −0.056 |
| v6.6r (EXP-010) | −4.1% | −1.1% | −26.4% | −0.03 | −0.042 |

ETH fell against BTC over the whole window (0.071 → 0.032 BTC), mean F was only 0.24, and the pool's fees
(0.13 WBTC for v6 over four years) are small against the price moves. Both candidates lose less than v6 over the
continuous run, but per year they lose more in the down years, which is where the sleeve / spot base hurts.

Verdict: **holdout-fail** — return wins 0/4 (median −3.2 pts); continuous Calmar −0.056 ≥ v6's −0.088 holds, the yearly-wins leg does not.

## Deviations

- Rule changed after dev results were known (see above). EXP-010 tests a sibling variant on the same holdout in
  the same invocation: two candidates on one holdout, count both in any multiple-testing correction.
- The holdout pool's daily closes (other orientation) were looked at before EXP-001; see EXP-001 Deviations.
