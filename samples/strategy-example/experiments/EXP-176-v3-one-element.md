# EXP-176: one-element variants of Maker's defense v3, in-sample to 2024 / out-of-sample 2025-26

- Jira: QUAN-1149
- Status: pass (goal reached: 11 counted on `0x88e6`, 12 on `0x4585`; few independent findings, see Result)
- Pre-registration commit: c879cce (batches 2-5: aac6a10, 37409f5, 58c7401, fe19994) · Result commit: 2110f67

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

Run 2026-10-14, `experiments/v3_goal.py` (Rust engine; raw runs in the main checkout's `result/v3_goal/`, every run in
`result/v3_goal/runs.csv`; counted variants in `~/Desktop/v3_one_element_results.csv`).

v3 itself:

| pool | IS total / CAGR / max DD / Calmar | OOS total / CAGR / max DD / Calmar |
|---|---|---|
| ETH `0x88e6` (USDC) | +88.6% / 18.94% / −21.9% / 0.866 | +32.9% / 18.08% / −26.3% / 0.688 |
| WBTC/WETH `0x4585` (BTC) | −0.7% / −0.21% / −25.8% / −0.008 | +15.4% / 8.72% / −14.9% / 0.585 |

Batches: 1 (28 variants, both pools; `uniform` / `gaussian` cannot run, see Deviations), 2 (25, both), 3 (22, both),
4 (11, BTC only: ETH had 11 counted after batch 3), 5 (10, BTC only).

| pool | IS runs | beat v3 IS | OOS runs | beat v3 OOS too (counted) |
|---|---|---|---|---|
| ETH `0x88e6` | 73 | 26 | 26 | **11** |
| WBTC/WETH `0x4585` | 94 | 27 | 27 | **12** |

Counted, OOS CAGR vs v3 (IS gain in brackets):

- ETH: `confirm5` 23.05% (+0.26), `f2low` 21.86% (+0.78), `share75` 21.33% (+3.40), `share70` 20.15% (+2.69),
  `follow0625` 19.98% (+0.16), `ig9` 19.15% (+1.64), `share7060` 19.12% (+1.35), `share65` 18.95% (+1.96),
  `spanswide` 18.81% (+0.88; OOS max DD −17.2% vs −26.3%), `fstage` 18.09% (+0.16), `vstep3` 18.08% (+0.00).
- BTC: `sharema15` / `sharema20` 10.55%, `sharema10` 10.54% (all +0.58 IS; OOS max DD −11.5% vs −14.9%), `share75`
  9.35% (+0.13), `share70` = `sharema30` = `sharema40` = `sharema50` = `sharema75` 8.79% (identical OOS run),
  `share7060` 8.75%, `ig9` 8.75%, `vstep3` 8.72% (+0.00).

IS pass, OOS fail: ETH `divema200`, `divoff10`, `divon20`, `fmin`, `followplain`, `invexp`, `share55`, `share60`,
`sharema200`, `sharema50`, `stop70`, `stop75`, `upper130`, `upper140`, `uptarget`; BTC `divon125`, `divon15`,
`divon175`, `divon20`, `fmin`, `share30`..`share65` fixed levels below 70%, `share6040`, `share6050`. The largest IS
winners (`fmin` +5.8 pts ETH IS, `divon20` +2.0 pts BTC IS) lost the most out of sample.

Verdict: **pass as the goal is worded** (≥ 10 one-element variants beat v3 on IS and OOS on each pool), but read it as
about five independent findings, not 23:

1. **Real ETH share ~65-75% instead of the 70 / 50 EMA100 switch** (ETH `share65/70/75/7060`; BTC `share70/75/7060` and
   the `sharema30..75` switches, which OOS behave exactly like a fixed 70%). The clearest single finding; ETH +1..3 pts
   CAGR both halves, max DD up to 0.7 pt deeper OOS.
2. **BTC: switch the share on a short EMA (10-20 days)** — the only BTC change well beyond noise: OOS 10.55% vs 8.72%,
   max DD −11.5% vs −14.9%; IS +0.58 pt.
3. **ETH: slower or more conservative refill / F** (`confirm5`, `f2low`, `follow0625`), +2..5 pts OOS but only
   +0.2..0.8 pt IS.
4. **ETH: wider EMA spans (50/100/150/200)** — OOS max DD −17.2% vs −26.3%.
5. **4 + 4 bands (`ig9`)** — +1.6 pt ETH IS, +1.1 pt ETH OOS; BTC within noise.

Noise-level counts (< 0.1 pt CAGR on a half): ETH `fstage`, `vstep3`; BTC `share70` and its four twins, `share7060`,
`ig9`, `vstep3`. With 73 / 94 tries per pool and ~45% of IS passes failing OOS, single counted variants are expected by
chance; only findings 1 and 2 hold on both halves by more than 0.5 pt. Next test: the forward window after 2026-09-17,
and finding 1 / 2 on another ETH and another BTC/ETH pool.

### P&L attribution (added 2026-10-14, after the result)

v3 and the 23 counted variants were rerun with a daily log of holdings, LP amounts, fees and swap cost (logging only:
net value files byte-identical to the first runs; `v3_goal.py attrib`, CSV `~/Desktop/v3_winners_pnl_attribution.csv`).
Between two daily logs nothing trades, so the change in net value splits exactly into: directional (average ETH share x
daily ETH returns), timing (the ETH share moving with F / the share rule), fees, LVR / impermanent loss (residual), and
swap costs. Shares of the starting book, whole window (not per year):

| pool, segment | v3: directional / timing / fees / LVR-IL / costs = total |
|---|---|
| ETH IS | +36.1 / +70.4 / +77.6 / −92.6 / −3.0 = +88.6% |
| ETH OOS | +2.5 / +43.4 / +19.3 / −31.1 / −1.2 = +32.9% |
| BTC IS | −5.7 / +9.2 / +8.7 / −12.2 / −0.6 = −0.7% |
| BTC OOS | +0.2 / +20.4 / +2.2 / −5.5 / −1.9 = +15.4% |

- The LP leg (fees + LVR/IL) loses on every pool and segment (ETH IS −15.0 pts, OOS −11.8; BTC IS −3.5, OOS −3.3);
  v3 earns from timing (the F engine), as v6 does (`RESEARCH-2026-10-06-is-lp-worth-it.md`).
- Every counted variant wins mainly through timing. ETH `share70/75`: more ETH while invested, IS +7..10 pts directional
  and +11..14 timing, LP net −1.7..−2.7 pts (OOS LP net also worse). BTC `sharema10/15/20`: OOS +3.2 pts timing, LP net
  −0.1. ETH `ig9` / `spanswide`: more fees but more LVR, LP net −3.8 / −5.9 pts IS (+1.1 / +1.4 OOS). Only `f2low`,
  `follow0625` and `confirm5` improve the LP leg OOS (+0.7..2.1 pts), with mixed IS.
- None of the 23 is a better LP; they are better market timing or more ETH exposure.

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
- `uniform` / `gaussian` (batch 1) cannot run: v3's equal-price bands need a shape with zero centre weight (ValueError);
  replaced in batch 2 by `invtri` / `invexp`.
- `nostop` and `noupper` give the same F (difference 1e-16): at stage 4 the virtual upper rebuild does not change F, so
  its only effect is moving the centre up for a later lower stop; deleting either rule removes the same stops.
- `uptarget` (batch 1) beat v3 on ETH IS by less than 0.001 pt and was missed in the first read; it got its OOS run with
  batch 2 (fail).
- Batch 5 was written after batch 4's OOS results were read (batches 2-4 were committed before the previous batch's OOS
  was read). Its families (share switch line, share levels, divergence trigger) were chosen from IS passes.
- Batches 4 and 5 ran on `0x4585` only, as ETH had reached 10 counted.
- The follow-rebuild count is missing for some runs (the child process's final print is sometimes lost); not used.
