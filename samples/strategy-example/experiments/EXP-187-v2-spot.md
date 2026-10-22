# EXP-187: k100_f2low_rvol_reupE as a spot-only strategy (no LP) vs with its LP, `0x4585` IS / OOS / sheet 2022-25 + Arbitrum

- Jira: QUAN-1186 (subtask of QUAN-1107)
- Status: done — spot only beats the LP version on OOS, 2022-25 and Arbitrum (CAGR +7.3 / +2.0 / +2.9 pts, DD 3-4 pts shallower), loses IS (−4.6 pts)
- Pre-registration commit: 3dab11f · Result commit: (next commit)

Dino (2026-10-22): "目前btc那個策略，如果改成直接操作現貨的話績效是如何？兩者比較一下"

## Hypothesis

The current best BTC/ETH strategy (`k100_f2low_rvol_reupE`, EXP-183) already holds spot while ETH is strong (F as ETH,
the rest USDC); its only LP is the weak side (F at +-20%). EXP-186 found that replacing v2's LP by 50/50 tokens ties
in-sample and wins out of sample and on Arbitrum. The same may hold for the current best: its LP edge was +0.32 ETH
IS but −0.12 ETH OOS (EXP-185).

## Change

`experiments/v2_goal.py`, `k100_reupE_spot`: while weak, F is held as 50% ETH / 50% BTC tokens instead of a +-20% LP
(about what a centred +-20% LP holds when built); the rest BTC as before. No LP and no fees; signals, rebuild rules
and the 0.1% swap cost unchanged.

## Pre-registration

- Runs (1 ETH start, in ETH incl. rewards): `0x4585` IS 2021-11-02..2024-12-31, OOS 2025-01-01..2026-09-30, the BTC/ETH
  sheet window 2022-01-02..2025-12-31 (`c2225`), Arbitrum `0x2f5e` 2023-01-01..2026-01-13. The LP version's runs are
  reused where they exist (`is`, `oosf`, `c2225`); Arbitrum full window is run for both.
- A comparison, not a search: report CAGR, max DD, Calmar, USD ratio and USD max DD for both on every segment, and say
  per segment which one beats the other on `better()`. No follow-up variant inside this experiment.

## Result

In ETH (1 ETH start); USD = net value in USD / USD invested. LP edge = the LP version's fees + IL from its LP log.

| segment | LP version (k100_f2low_rvol_reupE) | spot only (k100_reupE_spot) | LP edge | better() |
|---|---|---|---|---|
| IS 2021-11..2024 | 65.68% / −24.8% / 2.643 · USD x3.809, DD −47.8% | 61.08% / −25.3% / 2.419 · USD x3.484, DD −48.3% | +0.324 | LP |
| OOS 2025..2026-09-30 | 25.80% / −28.7% / 0.898 · USD x1.202, DD −57.5% | **33.05% / −25.6% / 1.291** · USD x1.325, DD −58.2% | −0.118 | **spot** |
| sheet 2022-01-02..2025-12-31 | 52.67% / −30.0% / 1.756 · USD x4.270, DD −47.8% | **54.65% / −25.6% / 2.134** · USD x4.495, DD −48.3% | −0.221 | **spot** |
| Arbitrum 2023-01..2026-01-13 | 16.39% / −29.7% / 0.552 · USD x4.406, DD −48.0% | **19.28% / −25.3% / 0.763** · USD x4.746, DD −47.7% | −0.112 | **spot** |

(CAGR / max DD / Calmar.) Rebuilds: spot 105 / 58 / 136 / 102 vs LP 118 / 66 / 155 / 115.

**Verdict: spot only beats the LP version on 3 of 4 segments** (OOS +7.25 pts, 2022-25 +1.98 pts, Arbitrum +2.89 pts
CAGR, max DD 3.1 / 4.4 / 4.4 pts shallower) and loses in-sample (−4.60 pts). The difference is the LP edge: positive
only in IS (+0.324 ETH, R mean-reverting 2021-24), negative on every other window (−0.118 / −0.221 / −0.112). USD max DD
is about the same either way (−48..−58%): the LP is not what drives the USD drawdown.

Reading it: with keep100 the LP only runs while ETH is weak against BTC, and in those periods ETH/BTC has trended more
often than it reverted since 2024, so the LP's IL exceeds its fees. The strategy's edge is the timing (F, strength
switch); the LP adds risk of the wrong kind out of sample. Spot only is also simpler to run (no positions, no range
rebuilds, no pool dependency; any venue with ETH / BTC / USDC spot works).

## Deviations

- The IS / OOS-gated rule of EXP-183..185 would have stopped `spot` at IS (it loses there); this experiment was
  pre-registered as a plain comparison on all four windows, so every window was run.
