# EXP-183: IS-only search on top of k75_f2low_rvol (ETH-cbBTC MGL v2), `0x4585`, IS before 2025 / OOS after

- Jira: QUAN-1180 (subtask of QUAN-1107)
- Status: pass — `k100_f2low_rvol_reupE` beats `k75_f2low_rvol` on IS and OOS (CAGR +1.23 / +1.31 pts, DD 0.4 / 1.3 pts shallower)
- Pre-registration commit: 4052e44 · Result commit: (next commit)

Dino (/goal 2026-10-21): "切25年以前is 以後oos，只能分析is的結果優化策略，is有比較好的結果才可以看oos，直到btceth池找到
一個is oos績效都更好的策略。"

## Hypothesis

The base is EXP-182's best, `k75_f2low_rvol` (MGL v2 + ETH_KEEP 0.75 + F second-lowest account + rvol filter). An
IS-only look at it (2021-11-02..2024-12-31, in ETH) shows:

- P&L: +2.96 ETH from 1 ETH; USDC held +1.54 (2022 crash), BTC held +1.33, LP + kept ETH + costs +0.10 (fees included).
- Its four deepest drawdowns come from holding the retreat while the market turns back: USDC through ETH/USD rebounds
  (2022-08-29..11-05 −25.2%, 2024-05-17..08-01 −21.0%) and BTC through ETH/BTC rebounds (2022-06-17..08-14 −16.8%,
  2024-11-06..10 −10.0%).

So an element that limits the cost of a wrong exit, or spreads the retreat over BTC and USDC, may cut the IS drawdowns
without giving up the retreat's gains.

## Change

`experiments/v2_goal.py`; each variant = `k75_f2low_rvol` + ONE element. Batch 1 (written before any of it ran):

| variant | added element |
|---|---|
| `k75_f2low_rvol_reupG` | re-entry after a wrong exit: when the final F falls, remember G's close; while F < 1, a G close >= 1.15 x that level sets F = 1 until F falls again or reaches 1 |
| `k75_f2low_rvol_reupE` | same on ETH/USD, armed only while ETH is strong (the USDC retreat) |
| `k75_f2low_rvol_split50` | the (1 − F) reserve is always half BTC, half USDC (base: USDC while strong, BTC while weak) |
| `k75_f2low_rvol_ethmom` | EXP-179's `ethmom` on the new base: while strong and ETH/USD > EMA20 > EMA50, the USDC reserve is held as ETH |

Later batches, if needed, are added to this file and committed before they run; each one may use IS results only.

Batch 2 (written after batch 1, from IS numbers only): split by regime, the base's LP made +0.03 ETH over the 787 weak
IS days (LP 68% of the book) where a 50/50 ETH/BTC hold of the same money made +0.14 and BTC +0.28 (2022 −0.47,
2024 +0.71). The weak side is where the LP gives the least back.

| variant | added element |
|---|---|
| `k75_f2low_rvol_bkeep25` | while weak, 25% of F held as BTC outside the LP (mirror of ETH_KEEP) |
| `k75_f2low_rvol_bkeep50` | while weak, 50% of F held as BTC outside the LP |
| `k75_f2low_rvol_weakhold` | while weak, F held as 50% ETH / 50% BTC tokens, no LP |

Batch 3 (after batch 2's IS results, all three lost: the LP's fees matter more than the regime split suggested).
Collected fees (0.68 ETH over IS, 14% of the end book) sit in the wallet outside the strategy's capital and BTC fees
stay BTC; rebuild swap cost was 0.14 ETH over IS.

| variant | change |
|---|---|
| `k75_f2low_rvol_compound` | spec compound mode: collected fees count as capital, reinvested by the next rebuild |
| `k75_f2low_rvol_follow25` | drift-rebuild threshold 25% instead of 12.5% |

Batch 4 (after batch 3's IS results, both lost). While ETH is strong the book is F x 75% ETH + F x 25% ETH/BTC LP +
(1 − F) USDC, an ETH/USD position, but F comes from G = sqrt(ETH x BTC); the base's two deepest IS drawdowns are USDC
held through ETH/USD rebounds. The same four accounts (second-lowest, then rvol) run on ETH/USD = G x sqrt(R).

| variant | change |
|---|---|
| `k75_f2low_rvol_fEstrong` | while strong, F from the four accounts on ETH/USD (weak: on G as before) |
| `k75_f2low_rvol_fEboth` | F from the accounts on ETH/USD on every day |

Batch 5 (after batch 4's IS results, both lost), picked from the IS ranking of every v2_goal run (IS numbers only):
keep100 beat keep75 on IS (59.26% / −23.0% vs 58.79% / −23.3%); f2low was the largest single IS gain (+4.1 pts on v2)
and its more conservative neighbour was never run; rlow20 had the best IS Calmar (3.076, DD −17.9%).

| variant | change |
|---|---|
| `k100_f2low_rvol` | ETH_KEEP 1.0 on the base (no LP while strong) |
| `k75_fmin_rvol` | F = lowest of the four accounts (base: second-lowest) |
| `k75_f2low_rvol_rlow20` | EXP-180's rlow20 BTC lock added to the base |

Batch 6 (after batch 5's IS results): fmin raised IS CAGR to 67.07% and k100 to 65.10%, both with a lower Calmar;
fmin's deepest IS drawdown is the 2022-08-29..11-05 episode (−27.0%), the one `reupE` cut on the base (−25.2% → −24.0%).

| variant | change |
|---|---|
| `k75_fmin_rvol_reupE` | ETH_KEEP 0.75 + F lowest account + rvol + reupE |
| `k100_f2low_rvol_reupE` | ETH_KEEP 1.0 + f2low + rvol + reupE |
| `k100_fmin_rvol_reupE` | ETH_KEEP 1.0 + F lowest account + rvol + reupE |

## Pre-registration

- Pool: mainnet WBTC/WETH 0.05% `0x4585`, 1 ETH start, net value in ETH incl. rewards (as EXP-178..182); USD ratio and
  USD max DD reported, not judged.
- IS: 2021-11-02..2024-12-31 (`is`). OOS: 2025-01-01..2026-09-30 (`oosf`, all minute data).
- Bar on a segment (`better()`, EXP-176..182): CAGR above the base AND Calmar >= the base AND max DD no more than 3 pts
  deeper.
- Order: every variant runs IS first. Only a variant that beats the base on IS runs OOS (the base runs OOS at the same
  time). No variant is designed, changed or ranked from any OOS number.
- **Goal reached** when a variant beats the base on IS and on OOS. Batches continue until then; every run is reported.

## Result

In ETH; base `k75_f2low_rvol`. IS 2021-11-02..2024-12-31, OOS 2025-01-01..2026-09-30.

Batch 1, IS:

| variant | CAGR | max DD | Calmar | USD x / USD DD | vs base |
|---|---|---|---|---|---|
| base | 64.45% | −25.2% | 2.558 | 3.719 / −48.8% | |
| `reupG` | 64.01% | −25.2% | 2.541 | 3.688 / −48.8% | loses |
| `reupE` | 64.96% | −24.1% | 2.698 | 3.757 / −48.8% | **beats** |
| `split50` | 41.67% | −31.9% | 1.306 | 2.320 / −49.9% | loses |
| `ethmom` | 50.25% | −28.1% | 1.791 | 2.795 / −48.8% | loses |

Batch 1, OOS (only `reupE` passed IS): base 24.49% / −30.0% / 0.818 (USD x1.180, USD DD −55.2%); `reupE` identical
to the base (its rule never fires after 2024): not better, fails.

Batch 2, IS (none passed, no OOS run):

| variant | CAGR | max DD | Calmar | USD x / USD DD | vs base |
|---|---|---|---|---|---|
| `bkeep25` | 62.66% | −25.5% | 2.461 | 3.593 / −48.9% | loses |
| `bkeep50` | 61.29% | −25.9% | 2.365 | 3.498 / −49.1% | loses |
| `weakhold` | 60.14% | −25.6% | 2.347 | 3.420 / −49.3% | loses |

Batch 3, IS (none passed, no OOS run):

| variant | CAGR | max DD | Calmar | USD x / USD DD | vs base |
|---|---|---|---|---|---|
| `compound` | 62.71% | −25.9% | 2.423 | 3.597 / −48.0% | loses |
| `follow25` | 63.32% | −25.7% | 2.465 | 3.640 / −49.0% | loses |

Batch 4, IS (none passed, no OOS run):

| variant | CAGR | max DD | Calmar | USD x / USD DD | vs base |
|---|---|---|---|---|---|
| `fEstrong` | 61.11% | −25.3% | 2.418 | 3.486 / −54.5% | loses |
| `fEboth` | 57.76% | −26.4% | 2.185 | 3.262 / −55.5% | loses |

Batch 5, IS (none passed, no OOS run):

| variant | CAGR | max DD | Calmar | USD x / USD DD | vs base |
|---|---|---|---|---|---|
| `k100_f2low_rvol` | 65.10% | −26.1% | 2.494 | 3.767 / −47.7% | loses (Calmar) |
| `k75_fmin_rvol` | 67.07% | −27.2% | 2.463 | 3.910 / −48.4% | loses (Calmar) |
| `k75_f2low_rvol_rlow20` | 60.89% | −22.4% | 2.720 | 3.471 / −55.8% | loses (CAGR) |

Batch 6, IS:

| variant | CAGR | max DD | Calmar | USD x / USD DD | vs base |
|---|---|---|---|---|---|
| `k75_fmin_rvol_reupE` | 67.94% | −27.2% | 2.495 | 3.975 / −48.4% | loses (Calmar) |
| `k100_f2low_rvol_reupE` | 65.68% | −24.8% | 2.643 | 3.809 / −47.8% | **beats** |
| `k100_fmin_rvol_reupE` | 69.14% | −28.3% | 2.441 | 4.067 / −47.4% | loses (Calmar) |

Batch 6, OOS (only `k100_f2low_rvol_reupE` passed IS; base OOS from batch 1):

| variant | CAGR | max DD | Calmar | USD x / USD DD | vs base |
|---|---|---|---|---|---|
| base | 24.49% | −30.0% | 0.818 | 1.180 / −55.2% | |
| `k100_f2low_rvol_reupE` | 25.80% | −28.7% | 0.898 | 1.202 / −57.5% | **beats** |

**Verdict: pass — goal reached.** `k100_f2low_rvol_reupE` (MGL v2 + ETH_KEEP 1.0 + F second-lowest account + rvol +
ETH/USD re-entry while strong) beats `k75_f2low_rvol` on IS (CAGR +1.23 pts, DD 0.4 pt shallower, Calmar 2.643 vs
2.558) and OOS (CAGR +1.31 pts, DD 1.3 pts shallower, Calmar 0.898 vs 0.818). 18 variants in 6 batches; 3 passed IS,
1 of those passed OOS.

Reading it:

- The gain is small, about +1.2..1.3 pts CAGR and 0.4..1.3 pts DD in ETH; USD max DD is deeper OOS (−57.5% vs −55.2%).
- `reupE` never fires after 2024 (batch 1: OOS identical to the base), so the OOS gain is ETH_KEEP 1.0's: no LP while ETH
  is strong. EXP-182 saw Arbitrum `0x2f5e` CAGR fall past a 75% keep; that pool was not part of this goal.
- 18 tries for one IS + OOS pass is close to what chance gives; the forward window after 2026-09-30 decides.

## Deviations

- The OOS period (2025 on) was already seen in EXP-178..182, and the base itself was assembled from components picked
  partly on that OOS. This search uses only IS to shape variants, but OOS is not untouched data.
- Batch 5's `rlow20` is an IS pick, but its family (rlow25) is known to have failed OOS on v2 (EXP-181); it is run as
  the IS ranking says, not dropped on that knowledge.
