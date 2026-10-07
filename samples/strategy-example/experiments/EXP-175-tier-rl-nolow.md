# EXP-175: fee tier: v6.75 + refill-low lower edge on 0.3% pools; v6.75 on cheaper pools (v6.160)

- Jira: QUAN-1081
- Status: pass
- Level: improvement (over spec v1; v6 on `0x4585`)
- Pre-registration commit: 783ad2a · Result commit: ______
- Scope: Dino, 2026-10-07, /goal "不斷的抽換v6裡面的概念，加上+-20的動態調整，直到找到總績效比v6好的策略". Batch 2 = EXP-173..175,
  pre-registered together after batch 1 (EXP-169..172) failed.

## Hypothesis

A narrower lower reach concentrates the refill legs' liquidity. That pays only where the pool's fees exceed its LVR: the repo's fee/LVR scans put the 0.3% tiers at 1.7-2.5 and the 5 bp ETH pool at 0.75 (EXP-117). So the refill-low edge belongs on the 0.3% pools; cheaper pools keep v6.75's ±20%. This is a fee-tier rule (one strategy, CLAUDE.md).

## Change

Variant `GS`: `TIER`: pools with fee >= 0.3% get `REFILL_NO_NEW_LOW = True` + `WIDTH_SIGNAL = "refill_low"`; cheaper pools `REFILL_NO_NEW_LOW = True` only. On 0.05% pools this is EXP-157's v6.75 exactly (re-run in the same invocation). Every constant is one an earlier EXP fixed; nothing is searched. Everything else is the baseline's.

## Pre-registration

- One invocation per pool, `opt:A,GQ,GR,GS`, one pool at a time, 2 workers, full history:
  - the seven pools of EXP-157..164 with `SPEC=v1` (`0x88e6`, `0x8ad5`, `0xd0b5`, `0xc696`, `0x6c56`, `0x99ac`, `0xfbb6`,
    same windows);
  - WBTC/ETH `0x4585` 2021-11-02..2026-09-17 (values in BTC, v6 baseline, `BINANCE_WARM=1`).
- Success rule (the goal's bar): `judge_full.py` on the seven pools passes (wins on >= 4 of 7 with at least one ETH and one BTC
  pool; per pool CAGR > spec v1, Calmar >= spec v1, max DD no more than 3 pts deeper) **and** the same per-pool test wins on
  `0x4585`. Both -> `pass`; otherwise `fail`. Every pool reported.
- Also reported (not deciding): v6.75 alone (EXP-157 `GA`) on the same pools.
- Gas is reported, not charged.

## Result

One invocation per pool, `opt:A,GQ,GR,GS`, one pool at a time, 2 workers (2026-10-08; raw runs in the main checkout's
`result/v6_validate/*-opt-AGQGRGS-*`), seven pools with `SPEC=v1` and `0x4585` with `BINANCE_WARM=1` (values in BTC). `A`
reproduces EXP-157's spec v1 numbers on every pool and v6's -1.40% on `0x4585`.

| pool | baseline total / CAGR / max DD / Calmar | this | rebuilds | win |
|---|---|---|---|---|
| ETH mainnet 0.05% `0x88e6` | +97.7% / 13.55% / -22.9% / 0.591 | +112.6% / 15.09% / -23.5% / 0.641 | 179 → 175 | **win** |
| ETH mainnet 0.3% `0x8ad5` | +100.0% / 13.78% / -21.0% / 0.657 | +114.3% / 15.26% / -20.6% / 0.740 | 178 → 178 | **win** |
| ETH Base 0.05% `0xd0b5` | +54.9% / 16.96% / -34.7% / 0.489 | +54.8% / 16.92% / -35.9% / 0.471 | 84 → 84 | lose |
| ETH Arbitrum 0.05% `0xc696` | +65.7% / 26.88% / -31.4% / 0.856 | +64.8% / 26.56% / -32.5% / 0.817 | 64 → 65 | lose |
| ETH Base 0.3% `0x6c56` | +29.8% / 16.48% / -24.6% / 0.671 | +34.4% / 18.88% / -24.5% / 0.771 | 55 → 56 | **win** |
| BTC mainnet WBTC 0.3% `0x99ac` | +62.2% / 10.43% / -30.1% / 0.346 | +60.4% / 10.18% / -29.9% / 0.340 | 129 → 135 | lose |
| BTC Base cbBTC 0.05% `0xfbb6` | +44.0% / 20.46% / -16.7% / 1.224 | +44.2% / 20.52% / -16.7% / 1.227 | 49 → 49 | **win** |
| WBTC/ETH 0.05% `0x4585` (v6, BTC) | -1.4% / -0.29% / -32.7% / <0 | -1.2% / -0.25% / -32.8% / <0 | 100 → 100 | **win** |

Verdict: **pass** — seven-pool 4/7 (ETH 3 of 5, BTC 1 of 2) and `0x4585` wins; median CAGR gain +0.05 pt.

What the pass is made of (read before using it):
- On the four 0.05% pools and `0x4585` this variant **is** v6.75 (identical numbers to EXP-157 `GA` on `0x88e6`). The BTC win
  (`0xfbb6`, +0.06 pt CAGR) and the `0x4585` win (+0.04 pt; Calmar compared on a negative CAGR, max DD 0.1 pt deeper) are
  v6.75's and within noise.
- The dynamic width acts on the three 0.3% pools only. Against v6.75 alone (EXP-157) it gains on Base 0.3% (CAGR 18.88% vs
  17.04%, Calmar 0.771 vs 0.694), trades CAGR for Calmar on mainnet 0.3% (15.26% / 0.740 vs 15.86% / 0.730) and loses on WBTC
  0.3% (10.18% vs 10.49%), which turns that pool from a v6.75 win into a loss.
- So this passes the bar but is not better than v6.75 alone (5/7). It is a v6.75 candidate with a fee-tier width that helps
  one pool; the forward window (after 2026-09-17) is the real test.

## Deviations

- Designed after batch 1: EXP-172 (refill-low edge + v6.75 + share 50%) won 3/7, losing the BTC and L2 0.05% pools on CAGR.
  A tier variant built from batch 1's per-pool results (EXP-172's switches on 0.3% pools, v6.75 on cheaper ones) was not
  registered: its 4/7 is known from earlier runs, so it would not be a test.
