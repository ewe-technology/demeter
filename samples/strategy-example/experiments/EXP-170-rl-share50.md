# EXP-170: EXP-168's refill-low lower edge + ETH share fixed at 50% (v6.155)

- Jira: QUAN-___
- Status: pre-registered
- Level: improvement (over spec v1 on ETH/USDC, over v6 on WBTC/ETH; then the seven-pool bar)
- Pre-registration commit: ______ · Result commit: ______
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

## Deviations

- The batch was chosen after EXP-165..168 (same two pools): EXP-168 was the closest width rule, so every variant here keeps it.
