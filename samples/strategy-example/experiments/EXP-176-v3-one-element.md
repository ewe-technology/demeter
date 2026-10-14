# EXP-176: one-element variants of Maker's defense v3, in-sample to 2024 / out-of-sample 2025-26

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______

/goal 2026-10-14 (Dino): "在 mainnet 0x88e6 WETH/USDC 0.05% and 0x4585 WBTC/WETH，資料 20241231 以前都是 is，之後都是 oos，
你只能看著 is 去操作，如果 is 績效比較好，就可以看 oos 是否也比較好。每次調整只 v3 的其中一個元素就好，你可以刪除新增或替換其中
一個元素，但每個版本就只能有一個元素變動。直到在這兩池中各自找到十個比 v3 更好的策略。"

## Hypothesis

v3 is ten rules on one price series (`VALIDATION-2026-10-13-defense-v1-v3.md`: DSR 0.72 fail, v3 − v2 return gain not
established). Some of its rules may be dead weight or set in a way that a single change improves both before and after
2025. A change that wins in-sample and again out-of-sample on the same pool is a candidate; one that only wins in-sample
is noise.

## Change

Base: Maker's `gamma_maker_defense_ethusdc_v3.py` at `maker-defense` 5cec767, run as is (standard mode, pool fee 0.05% +
depth slippage, Binance daily closes for the engine, ±20% spec valley, $100k), with the window changed only. Each variant
changes **one** element of v3: deletes it, adds one, or replaces it. The catalogue and the exact text replacements are in
`experiments/v3_goal.py` (`VARIANTS`); later batches are added there and listed under *Result* with the date they were
written, before their in-sample run.

WBTC/WETH `0x4585`: v3 has no BTC/ETH version (Maker's `gamma_maker_defense_btceth_v1.py` is a different four-asset
spec). v3 runs unchanged with ETH as the base token and WBTC in USDC's place (quote token, 2 WBTC book, every number in
BTC), its engine on Binance ETHBTC daily closes. This is how v6 runs on `0x4585` too.

Batch 1 (28 variants, written 2026-10-14 before any variant run):

| element of v3 | variants |
|---|---|
| 1 EMA exit | `exit2d` two closes below; `exitslope` also needs a falling EMA (below its value 20 days earlier); `sma` SMA instead of EMA |
| 2 re-arm | `norearm` deleted: any close below the EMA empties a holding account |
| 3 lower stop | `nostop` deleted |
| 4 virtual upper rebuild | `noupper` deleted |
| 5 staged refill | `confirm1` stage 1 after 1 close (not 3); `ladderv1` v1 steps +5/8.33/11.67/15%; `multistage` several stages a day; `refillabove` a stage advances only above the account's EMA |
| 6 real ETH share | `share50` fixed 50%; `share70` fixed 70%; `share3` 25% below EMA100 × 0.95, else 70/50 |
| 7 follow | `follow25` threshold 25%; `followplain` full / empty top-up conditions deleted |
| 8 real range exit | `lowrecentre` lower exit recentres at the current share (not all to USDC); `uptarget` upper exit rebuilds at F'; `hourly` range checked hourly |
| real LP geometry | `width30` ±30%; `width15` ±15%; `uniform` uniform weights; `gaussian` centre-peaked weights |
| 9 virtual weak share | `noweak` deleted (no 25% level) |
| 10 divergence | `nodiv` deleted (= v2); `divhalf` flag ON halves F instead of F' = 0 |
| F | `fstage` stage / 4 instead of value share; `fmin` minimum of the four accounts; `fmax` maximum |

## Pre-registration

- Pools: mainnet WETH/USDC 0.05% `0x88e6` (USDC), mainnet WBTC/WETH 0.05% `0x4585` (BTC).
- In-sample (IS): `0x88e6` 2021-05-06..2024-12-31 (v3's own start), `0x4585` 2021-11-02 (first data day)..2024-12-31.
- Out-of-sample (OOS): 2025-01-01..2026-09-17 (last data day) on both pools.
- IS and OOS are separate runs, each starting from the full book ($100k / 2 WBTC); the signal engine is warmed up on
  Binance closes from 2017-08 either way. v3 runs in the same batch on the same segment.
- Metrics from the per-minute net value in the quote token: CAGR, max drawdown, Calmar = CAGR / |max DD|.
- **Beats v3** on a segment: CAGR above v3, Calmar ≥ v3, max DD no more than 3 pts deeper (the team's working bar).
- Procedure: variants are designed and judged on IS only. Only a variant that beats v3 on a pool's IS gets an OOS run on
  that pool. A variant **counts** for a pool when it beats v3 on that pool's IS and OOS. New batches may only use IS
  results. The search stops when each pool has 10 counted variants; every run (IS and OOS, pass or fail) is reported.
- Output: `~/Desktop/v3_one_element_results.csv` (element changed, what it became, IS / OOS numbers vs v3) and
  `result/v3_goal/runs.csv` in the main checkout.

## Result

## Deviations

- Binance closes: Maker's ETHUSDT file ends 2026-08-31 and ETHBTC 2025-12-31; both are extended to 2026-09-17 from
  `samples/binance_daily_closes.csv` (same date convention, identical values where they overlap; ETHBTC = ETHUSDT /
  BTCUSDT, 0.03390 on 2025-12-31 either way).
- The v3 IS run on both pools was run once before this file was written, to test the runner (ETH +88.6% / CAGR 18.94% /
  max DD −21.9%; BTC −0.7% / −0.21% / −25.8%). The divergence flag never fires on ETHBTC in-sample, so `nodiv` / `divhalf`
  cannot beat v3 on `0x4585` IS.
- Each version changes one element, as the goal asks; several variants set a value (threshold, width, ladder), which is
  parameter tuning inside v3's family. With ~30+ tries per pool, single passes are expected by chance (see the
  multiple-testing note under *Result*).
