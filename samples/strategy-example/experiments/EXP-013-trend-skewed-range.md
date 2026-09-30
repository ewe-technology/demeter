# EXP-013: trend-skewed range — the ±20% valley shifts 5 pts in the direction of the EMA100 trend (v6.10)

- Version: v6.10
- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Literature: `RESEARCH-2026-09-30-lp-literature.md` §4.

## Hypothesis

v6 places the same symmetric ±20% valley whatever the trend. Its two weakest regimes are the directional ones
(`V6_VALIDATION.md` §5): in strong rallies it gives up most of the upside (up/high-vol +46% a year against ETH
+215%), and in slow grinds up it loses (up/low-vol −9.2% a year); EXP-006 measured that three quarters of v6's IL
(−75.5k of −101k, ETH 2022–26) is rallies running through the upper bands, which sell ETH on the way up. The
mirror holds on the way down: a falling price runs through the lower bands, which buy ETH into the fall.

Cartea, Drissi and Monga ("Predictable Loss and Optimal Liquidity Provision", arXiv 2309.08431) derive the
optimal concentrated range for an LP facing drift μ and choosing spread δ: the range is not centred on the price
but shifted in the direction of the drift, with the closed-form skew ρ = ½ + μ/δ; their drift-aware strategy beat
the average LP out of sample on ETH/USDC 2021–22. The ±20% band study (claudio1923) agrees on the mechanism: what
kills a symmetric band is net displacement, not vol. v6 already carries a trend sign at every build — the EMA100 s
rule (close > EMA100 → ETH share 0.7, else 0.5) — so the skew can reuse it with one new constant. Expected: less IL
per rally (fewer upper-band sells before the price leaves), more fees on the side the price is going, the same
deployed fraction F and ETH share; the cost is a shorter side against the trend (−15% in an uptrend), so
range-exit rebuilds on pullbacks come 5 pts earlier. Drawdown should not worsen; return in the up regimes should.

This is borderline structural: the signal is v6's own, what it controls is new (range centre, not size). One
constant, fixed below; no search over it.

## Change

`SKEW = 0.05` (v6: 0). At every build (first build, follow rebuild, range-exit rebuild) the ladder's reaches are:

- last completed daily close **> EMA100** (the s rule's own variable, judged on the same day): lower reach
  20% − 5% = **−15%**, upper reach 20% + 5% = **+25%**
- close **≤ EMA100**: lower **−25%**, upper **+15%**

The state is read once per build and stays for the life of that ladder: range exits, the refill span and the
follow check judge the ladder that was placed. Band value weights (inverted gaussian, 8 bands), the ETH share
(s × F), F itself, the engine, exits, refills: all identical to v6. Total width stays 40 pts, so this is a shift of
the centre by 5 pts, not a change of size. Not modelled: nothing new (gas reported, not charged).

Implementation: the strategy builds three shape configs (flat / up / down) once; `shape_config` becomes the
current state's config; `resolve_skew(timestamp)` sets the state right before the reach is read in `first_lp` and
`rescale_work`. `SKEW = 0` reproduces v6 exactly (single "flat" config).

## Pre-registration

- Development data (in-sample): ETH/USDC 0.05% yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 (yearly
  reset, 100,000 USDC); continuous ETH 2022-01-01..2026-09-17 and WBTC/USDC 0.3% 2022-11-01..2026-09-17 reported.
  v6 (A) and this (J) in the same invocation.
- Holdout (run once, v6 + this only): Base USDC/WETH 0.05% (`0xd0b53d9277642d899df5c87a3966a349a798f224`), the
  deck's target pool; yearly segments 2024, 2025, 2026-01-01..09-17 plus the continuous 2024-01-01..2026-09-17
  run. EMA warm-up on mainnet ETH/USD as in EXP-004. v6's numbers on this pool are known from EXP-004's holdout;
  no run of this variant has touched it.
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
