# EXP-012: fee-vs-LVR gate — deploy only while the pool pays its liquidity (v6.9)

- Version: v6.9
- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Literature: `RESEARCH-2026-09-30-lp-literature.md` §1 (this direction), the whole file for the alternatives.

## Hypothesis

v6's return is fee income (fees $86.5k of the $85.4k gain, `V6_VALIDATION.md` §4), so the strategy only earns
when the fees a unit of in-range liquidity collects exceed what that unit loses to arbitrage — the loss-versus-
rebalancing (LVR) of Milionis, Moallemi, Roughgarden and Zhang (arXiv 2208.06046). On the ETH/USDC 0.05% pool the
two are close on average (LVR ≈ 0.97 x fees, 90% correlated, arXiv 2509.23222; CrocSwap's markout finds the 0.05%
pool persistently negative, Falkenstein fees $199M vs IL $260M to 2023-03), so whatever a passive LP earns comes
from the days when fees cover LVR and is given back on the days when they do not. The ±20% band study
(claudio1923) adds that the predictor of a losing week is net displacement relative to vol, not vol itself, which
is why a fee-coverage test, not a vol filter, is the right gate.

v6's EMA engine answers "which direction"; it never asks "is liquidity being paid right now". A second, orthogonal
gate that parks the ladder in USDC while the trailing week's fee income per unit of liquidity is below its LVR
should cut the fee-negative stretches (deep drawdowns in fast markets, the −9.2%/yr slow-grind regime where the
ladder collects little and pays displacement) while leaving the paid stretches — v6's +42.6%/yr range/high-vol
regime — untouched. Expected: drawdown and Calmar improve; total return flat to slightly up; more F switches, so
price impact and rebuild count are the risk and are reported.

## Change

`LVR_GATE = True` (v6: False), `LVR_GATE_DAYS = 7`, `LVR_GATE_MIN = 1.0`. All three fixed here; the threshold is
break-even by definition and the window is one week.

From the pool's own minute data (`inAmount0`, `inAmount1`, `closeTick`, `currentLiquidity`), per minute *m*:

- `P_m = 1.0001^closeTick` (raw token1 per raw token0), `s_m = √P_m`
- fee income per unit of in-range liquidity: `fee_m = φ x (inAmount1_m + inAmount0_m x P_m) / L_m`, φ the pool fee
  (0.0005 / 0.003), `L_m = currentLiquidity`; minutes with `L_m = 0` or no swaps contribute 0
- LVR per unit of in-range liquidity: `lvr_m = r_m² x s_m / 4`, `r_m = ln(P_m / P_{m-1})` (the v3 in-range
  position is a constant-product book with virtual reserves `L/√P`, `L√P`; LVR rate `σ² P² |x'(P)| / 2 = σ² L √P / 4`)

Both are raw token1 per unit liquidity, so their ratio is unit-free and the same for every band shape (fees and LVR
both scale with the position's liquidity at the current tick). Daily `Fee_d = Σ fee_m`, `LVR_d = Σ lvr_m` over UTC
day *d*; `R_d = Σ_{k=d-6..d} Fee_k / Σ_{k=d-6..d} LVR_k` over the last 7 completed days (fewer if the pool's data is
younger; undefined → gate open).

Gate: the daily signal frame's `F_d` becomes `F_d` if `R_d ≥ 1.0` else `0`. Everything downstream is v6: the
follow check (`|F − current| ≥ 0.125`), rebuild, s rule, exits, refills, all read the gated F through
`target_fraction_for`. The virtual accounts keep stepping on price only; the gate does not feed back into them.
`v6_validate.py` loads 8 extra days of the same pool before each window so `R` exists on day one; the EMA warm-up
is unchanged. Not modelled: nothing new (gate changes are ordinary v6 rebuilds; gas reported, not charged).

## Pre-registration

- Development data (in-sample): ETH/USDC 0.05% yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 (yearly
  reset, 100,000 USDC); continuous ETH 2022-01-01..2026-09-17 and WBTC/USDC 0.3% 2022-11-01..2026-09-17 reported.
  v6 (A) and this (I) in the same invocation.
- Holdout (run once, v6 + this only): Base USDC/WETH 0.05% (`0xd0b53d9277642d899df5c87a3966a349a798f224`), the
  deck's target pool; yearly segments 2024, 2025, 2026-01-01..09-17 plus the continuous 2024-01-01..2026-09-17
  run. EMA warm-up on mainnet ETH/USD as in EXP-004; the gate uses the Base pool's own swaps. v6's numbers on this
  pool are known from EXP-004's holdout; no run of this variant has touched it.
- Success rule (EXP-009's Calmar family):
  - Dev: return wins in ≥ 3 of 5 ETH segments, median gain > 0 pts, **and** continuous ETH Calmar (CAGR / |max DD|,
    daily equity) ≥ v6's 0.61. Otherwise `dropped-at-dev`.
  - Holdout: return wins in ≥ 2 of 3 Base segments **and** continuous Base Calmar ≥ v6's → `holdout-pass`, else
    `holdout-fail`.

## Result

| test | v6 | this | gain | max DD v6 → this |
|---|---|---|---|---|

Continuous run (reported, not deciding): total / CAGR / max DD / Sharpe / Calmar.

Verdict:

## Deviations

None yet.
