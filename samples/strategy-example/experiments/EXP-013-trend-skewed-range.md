# EXP-013: trend-skewed range — the ±20% valley shifts 5 pts in the direction of the EMA100 trend (v6.10)

- Version: v6.10
- Jira: [QUAN-858](https://ewetechnology.atlassian.net/browse/QUAN-858)
- Status: dropped-at-dev
- Pre-registration commit: 124d383 (implementation 0816abd) · Result commit: ______
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

Development, ETH/USDC 0.05%, yearly reset, 100,000 USDC (builds = ladders built in the up / down state):

| test | v6 | this | gain | max DD v6 → this | rebuilds v6 → this | fees v6 → this | builds up / down |
|---|---|---|---|---|---|---|---|
| 2022 | +7.6% | +3.6% | −4.0 | 21.5% → 21.0% | 41 → 41 | $20.1k → $18.5k | 10 / 31 |
| 2023 | +32.2% | +31.3% | −0.9 | 13.9% → 14.2% | 24 → 24 | | 16 / 8 |
| 2024 | +36.4% | +26.8% | −9.6 | 26.7% → 29.9% | 29 → 29 | $30.9k → $24.7k | 14 / 15 |
| 2025 | +16.3% | +19.3% | +3.0 | 26.9% → 24.8% | 32 → 31 | $20.8k → $24.3k | 14 / 17 |
| 2026-01..09-17 | +18.7% | +18.4% | −0.3 | 12.0% → 11.9% | 24 → 23 | | 5 / 18 |

Wins 1/5, median gain −0.9 pts.

Continuous runs (daily equity):

| run | total | CAGR | max DD | Sharpe | Calmar | fees | rebuilds | builds up / down |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | −22.8% | 0.73 | 0.61 | $86.5k | 147 | |
| ETH this | +79.2% | 13.2% | −22.6% | 0.69 | 0.58 | $80.9k | 144 | 57 / 87 |
| WBTC/USDC v6 | +85.6% | 17.3% | −17.8% | 1.01 | 0.97 | $61.7k | 106 | |
| WBTC/USDC this | +79.7% | 16.3% | −19.2% | 0.93 | 0.85 | $50.0k | 105 | 53 / 52 (fees −19%, same mechanism) |

Verdict: **dropped at dev** — wins 1/5, median −0.9 pts, continuous ETH Calmar 0.58 vs 0.61 (return −6.2 pts for
the same drawdown). The mechanism the hypothesis feared did not bite: rebuild counts are unchanged (the shorter side
against the trend did not trigger earlier range exits). What bit is the fee side of the shift: the same band value
spread over a 25% reach is 20% less liquidity per tick on the side the price is going, and v6's return is fees. In
the trend years that is the whole story — 2024 fees $30.9k → $24.7k with the LP principal also lower ($105.5k →
$102.1k), so the IL saved by the longer upper side did not cover the fees it cost; 2022 (31 of 41 builds "down")
lost 8% of fees the same way. The one win, 2025 (+3.0 pts, fees +17%, max DD 26.9% → 24.8%), is a choppy year in
which the extra reach kept the ladder in range through the swings. Cartea et al.'s skew is ρ = ½ + μ/δ: a 5-pt shift
of a 40-pt range is ρ = 0.625, i.e. a drift/spread ratio of 0.125, far above what a ±20% ladder rebuilt every ~12
days sees; at realistic drift the optimal shift is a few tenths of a point, inside tick rounding. Holdout not run.

What survives: the drift-aware range is not wrong, it is too small to matter at this width; the fee density of the
side the price is on is what v6 lives on, and anything that thins it must earn more IL than it costs in fees.

## Deviations

- After the pre-registration commit (124d383) and before the implementation commit (0816abd) one smoke run outside
  every pre-registered window: ETH 2021-11-01..12-31, v6 −4.81% (bit-identical to EXP-012's smoke run of v6, so
  `SKEW = 0` reproduces v6), this −5.04%, 2 up / 3 down builds; the exported actions were read to confirm the placed
  reaches (down: −22%/+13%, up: −13%/+22% — the outer zero-weight band is dropped, so v6's own effective reach is
  ±17.5%, and the shift is 4.4 pts of price, not 5). No pre-registered window ran before 0816abd.
- Yearly segments and continuous runs ran as two parallel chains (yearly; ETH then WBTC continuous), each
  invocation v6 + this with 2 workers. No reruns.
- 2022, 2023 and 2024 (0/3) decided the outcome; the remaining segments and continuous runs were completed for the
  record. The Base holdout was not run.
