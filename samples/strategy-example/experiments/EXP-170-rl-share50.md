# EXP-170: EXP-168's refill-low lower edge + ETH share fixed at 50% (v6.155)

- Jira: QUAN-1076
- Status: fail
- Level: improvement (over spec v1 on ETH/USDC, over v6 on WBTC/ETH; then the seven-pool bar)
- Pre-registration commit: ac4a870 · Result commit: ______
- Scope: Dino, 2026-10-07, /goal "不斷的抽換v6裡面的概念，加上+-20的動態調整，直到找到總績效比v6好的策略" (keep swapping v6's
  concepts, with a dynamic ±20%, until a strategy beats v6 overall). Batch 1 = EXP-169..172, pre-registered together.

## Hypothesis

v6 holds 70% of the ladder in ETH above EMA100 and 50% below; EXP-046 (share 50% always) lowered drawdown on every window with lower CAGR. The refill-low edge adds fee income on the refill legs. A 50% share removes v6's trend tilt (the swapped concept) and lets the edge's extra fees make up the return the tilt gave.

## Change

Variant `GN`: `WIDTH_SIGNAL = "refill_low"` (EXP-168) + `SHARE_ABOVE_EMA = 0.5` (EXP-046). Every constant is the one the cited EXP fixed; nothing is searched. Everything else is the baseline's
(spec v1 on USD-quoted pools, v6 on `0x4585`).

## Pre-registration

- Stage 1 (single pools, full history, one continuous run each, baseline `A` in the same invocation, `opt:A,GM,GN,GO,GP`):
  ETH/USDC mainnet 0.05% `0x88e6` 2021-05-06..2026-09-17 with `SPEC=v1`; WBTC/ETH mainnet 0.05% `0x4585` 2021-11-02..2026-09-17
  (values in BTC, v6 baseline, `BINANCE_WARM=1`). Per pool win: CAGR > baseline, Calmar >= baseline, max DD no more than 3 pts
  deeper. Win on both -> stage 2; otherwise `fail`.
- Stage 2 (the goal's bar, the team's full-history rule): `judge_full.py` on the seven pools of EXP-157..164 with `SPEC=v1`
  (`0x88e6` reused from stage 1). Pass: wins on >= 4 of 7 with at least one ETH and one BTC pool -> `pass`; otherwise `fail`.
- Also reported (not deciding): the same numbers for v6.75 (EXP-157), to show what the dynamic edge adds.
- Gas is reported, not charged.

## Result

Stage 1: run `opt-AGMGNGOGP` on `0x88e6` with `SPEC=v1` and on `0x4585` with `BINANCE_WARM=1` (values in BTC), 2 workers
(2026-10-07; raw runs in the main checkout's `result/v6_validate/0x88e6-opt-AGMGNGOGP-specv1-*`, `0x4585-opt-AGMGNGOGP-*`).
`A` reproduces spec v1 (+97.7%) and v6 on `0x4585` (-1.40%). v6.75 alone (EXP-157 `GA`, same `0x88e6` window): +112.6% /
15.17% CAGR / -23.5% / 0.645.

| pool | baseline total / CAGR / max DD / Calmar | this | rebuilds | win |
|---|---|---|---|---|
| ETH/USDC `0x88e6` (spec v1) | +97.7% / 13.55% / -22.9% / 0.591 | +94.3% / 13.17% / -18.0% / 0.733 | 179 → 186 | lose |
| WBTC/ETH `0x4585` (v6, BTC) | -1.40% / -0.29% / -32.7% / <0 | -1.06% / -0.22% / -27.7% / <0 | 100 → 107 | **win** |

Verdict: **fail** at stage 1 (1/2): ETH CAGR 0.38 pt below spec v1 (Calmar 0.733 vs 0.591, max DD 4.9 pts shallower).

## Deviations

- The batch was chosen after EXP-165..168 (same two pools): EXP-168 was the closest width rule, so every variant here keeps it.
- The pre-registration commit `ac4a870` was made before the runs; its push failed on GitHub 500 errors and went through one
  minute after the stage-1 runs started (retry loop).
