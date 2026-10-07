# EXP-172: EXP-168's refill-low lower edge + v6.75 + ETH share 50% (v6.157)

- Jira: QUAN-1078
- Status: fail
- Level: improvement (over spec v1 on ETH/USDC, over v6 on WBTC/ETH; then the seven-pool bar)
- Pre-registration commit: ac4a870 · Result commit: ______
- Scope: Dino, 2026-10-07, /goal "不斷的抽換v6裡面的概念，加上+-20的動態調整，直到找到總績效比v6好的策略" (keep swapping v6's
  concepts, with a dynamic ±20%, until a strategy beats v6 overall). Batch 1 = EXP-169..172, pre-registered together.

## Hypothesis

Combines EXP-169's and EXP-170's swaps: refills only after the low holds (fewer edge breaks) and a 50% share (shallower drawdown), both around the refill-low edge.

## Change

Variant `GP`: `WIDTH_SIGNAL = "refill_low"` + `REFILL_NO_NEW_LOW = True` + `SHARE_ABOVE_EMA = 0.5`. Every constant is the one the cited EXP fixed; nothing is searched. Everything else is the baseline's
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

| pool | baseline total / CAGR / max DD / Calmar | this | rebuilds | win |
|---|---|---|---|---|
| ETH/USDC `0x88e6` (spec v1) | +97.7% / 13.55% / -22.9% / 0.591 | +101.4% / 13.94% / -18.7% / 0.745 | 179 → 181 | **win** |
| WBTC/ETH `0x4585` (v6, BTC) | -1.40% / -0.29% / -32.7% / <0 | -0.94% / -0.19% / -27.7% / <0 | 100 → 107 | **win** |

Stage 2: `opt-AGP` with `SPEC=v1` on the other six pools, one pool at a time, 2 workers (2026-10-07/08; raw runs
`result/v6_validate/*-opt-AGP-specv1-*`); `0x88e6`'s stage-1 rows copied into `0x88e6-opt-AGP-specv1-*.csv` (rows `A_v6`, `GP`
only) so `judge_full.py opt-AGP` reads all seven. `A` reproduces EXP-157's spec v1 numbers on every pool.

| pool | spec v1 CAGR / max DD / Calmar | this | win |
|---|---|---|---|
| ETH mainnet 0.05% `0x88e6` | 13.55% / -22.9% / 0.591 | 13.94% / -18.7% / 0.745 | **win** |
| ETH mainnet 0.3% `0x8ad5` | 13.78% / -21.0% / 0.657 | 14.57% / -17.3% / 0.841 | **win** |
| ETH Base 0.05% `0xd0b5` | 16.96% / -34.7% / 0.489 | 15.77% / -29.1% / 0.542 | lose |
| ETH Arbitrum 0.05% `0xc696` | 26.88% / -31.4% / 0.856 | 21.64% / -26.4% / 0.819 | lose |
| ETH Base 0.3% `0x6c56` | 16.48% / -24.6% / 0.671 | 17.12% / -20.6% / 0.831 | **win** |
| BTC mainnet WBTC 0.3% `0x99ac` | 10.43% / -30.1% / 0.346 | 8.41% / -26.2% / 0.321 | lose |
| BTC Base cbBTC 0.05% `0xfbb6` | 20.46% / -16.7% / 1.224 | 16.30% / -15.6% / 1.045 | lose |

Verdict: **fail** at stage 2 — 3/7 (ETH 3 of 5, BTC 0 of 2). Max DD is shallower on all seven pools (1.1..5.6 pts), but CAGR
drops 1.2..5.2 pts on the L2 0.05% ETH pools and both BTC pools: the 50% share gives up the trend tilt's return where the trend
carried it.

## Deviations

- The batch was chosen after EXP-165..168 (same two pools): EXP-168 was the closest width rule, so every variant here keeps it.
- The pre-registration commit `ac4a870` was made before the runs; its push failed on GitHub 500 errors and went through one
  minute after the stage-1 runs started (retry loop).
