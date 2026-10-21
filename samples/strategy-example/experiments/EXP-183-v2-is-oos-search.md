# EXP-183: IS-only search on top of k75_f2low_rvol (ETH-cbBTC MGL v2), `0x4585`, IS before 2025 / OOS after

- Jira: (pending)
- Status: pre-registered
- Pre-registration commit: (this commit) · Result commit: (pending)

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

## Deviations

- The OOS period (2025 on) was already seen in EXP-178..182, and the base itself was assembled from components picked
  partly on that OOS. This search uses only IS to shape variants, but OOS is not untouched data.
