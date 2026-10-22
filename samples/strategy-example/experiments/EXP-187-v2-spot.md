# EXP-187: k100_f2low_rvol_reupE as a spot-only strategy (no LP) vs with its LP, `0x4585` IS / OOS / sheet 2022-25 + Arbitrum

- Jira: QUAN-1186 (subtask of QUAN-1107)
- Status: pre-registered
- Pre-registration commit: (this commit) · Result commit: (pending)

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

(pending)

## Deviations

(none yet)
