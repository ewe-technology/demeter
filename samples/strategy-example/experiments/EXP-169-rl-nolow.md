# EXP-169: EXP-168's refill-low lower edge + v6.75 no-new-low refill (v6.154)

- Jira: QUAN-1075
- Status: fail
- Level: improvement (over spec v1 on ETH/USDC, over v6 on WBTC/ETH; then the seven-pool bar)
- Pre-registration commit: ac4a870 · Result commit: ______
- Scope: Dino, 2026-10-07, /goal "不斷的抽換v6裡面的概念，加上+-20的動態調整，直到找到總績效比v6好的策略" (keep swapping v6's
  concepts, with a dynamic ±20%, until a strategy beats v6 overall). Batch 1 = EXP-169..172, pre-registered together.

## Hypothesis

EXP-168 (lower edge at the refill low while refilling) matched spec v1's Calmar on ETH/USDC with a 1.1-pt shallower drawdown but rebuilt 7 more times on each pool: the price broke below the refill low after a refill. v6.75 (EXP-157, 5/7 pools) refuses a refill stage on a day that makes a new intraday low, i.e. it refills only once the low has held. Refilling only after the low holds should cut the breaks below the edge, keep EXP-168's extra fees and drop its extra rebuilds.

## Change

Variant `GM`: `WIDTH_SIGNAL = "refill_low"` (EXP-168) + `REFILL_NO_NEW_LOW = True` (EXP-088 / 157). Every constant is the one the cited EXP fixed; nothing is searched. Everything else is the baseline's
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
| ETH/USDC `0x88e6` (spec v1) | +97.7% / 13.55% / -22.9% / 0.591 | +106.5% / 14.46% / -22.4% / 0.645 | 179 → 181 | **win** |
| WBTC/ETH `0x4585` (v6, BTC) | -1.40% / -0.29% / -32.7% / <0 | -3.16% / -0.66% / -33.6% / <0 | 100 → 107 | lose |

Verdict: **fail** at stage 1 (1/2). On ETH it beats spec v1 but not v6.75 alone (CAGR 14.46% vs 15.17%): the refill-low edge
costs v6.75 about 0.7 pt there. On WBTC/ETH the 7 extra rebuilds stay (100 → 107) with or without v6.75.

## Deviations

- The batch was chosen after EXP-165..168 (same two pools): EXP-168 was the closest width rule, so every variant here keeps it.
- The pre-registration commit `ac4a870` was made before the runs; its push failed on GitHub 500 errors and went through one
  minute after the stage-1 runs started (retry loop).
