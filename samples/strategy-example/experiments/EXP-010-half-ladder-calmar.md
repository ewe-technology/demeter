# EXP-010: v6.6 half ladder re-registered under a Calmar rule (v6.6r)

- Version: v6.6r (same variant as EXP-006 / v6.6, new success rule)
- Jira: [QUAN-845](https://ewetechnology.atlassian.net/browse/QUAN-845)
- Status: holdout-fail
- Pre-registration commit: fd47677 · Result commit: d4fe0a3

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

Verdict: **holdout-fail** — return wins 2/4 (median −0.1 pts; the two wins are +1.1 and +0.1 pts); continuous Calmar −0.042 ≥ v6's −0.088 holds, the yearly-wins leg (≥ 3/4) does not.

## Deviations

- Rule changed after dev results were known. Shares the holdout with EXP-009 (two candidates, one holdout).
- The holdout pool's daily closes (other orientation) were looked at before EXP-001; see EXP-001 Deviations.
