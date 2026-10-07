# EXP-174: v6.75 + +40% upper reach while F = 1 + refill-low lower edge while refilling (v6.159)

- Jira: QUAN-1080
- Status: pre-registered
- Level: improvement (over spec v1; v6 on `0x4585`)
- Pre-registration commit: 783ad2a · Result commit: ______
- Scope: Dino, 2026-10-07, /goal "不斷的抽換v6裡面的概念，加上+-20的動態調整，直到找到總績效比v6好的策略". Batch 2 = EXP-173..175,
  pre-registered together after batch 1 (EXP-169..172) failed.

## Hypothesis

Two state-dependent widths that act in different states: the +40% top at F = 1 (EXP-173, the upside of strong trends) and EXP-168's refill-low lower edge while 0 < F < 1 (shallower drawdown on every pool in EXP-172). The edge's drawdown cut should pay for the wide top's deeper drawdown, which is what lost EXP-164 on mainnet ETH.

## Change

Variant `GR`: `REFILL_NO_NEW_LOW = True` + `WIDTH_SIGNAL = "full_widetop_rl"`: F = 1 -> +40% / -20%; 0 < F < 1 -> lower edge at the refill low (EXP-168 rule), upper +20%; F = 0 -> v6's ±20%. Every constant is one an earlier EXP fixed; nothing is searched. Everything else is the baseline's.

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

## Deviations

- Designed after batch 1: EXP-172 (refill-low edge + v6.75 + share 50%) won 3/7, losing the BTC and L2 0.05% pools on CAGR.
  A tier variant built from batch 1's per-pool results (EXP-172's switches on 0.3% pools, v6.75 on cheaper ones) was not
  registered: its 4/7 is known from earlier runs, so it would not be a test.
