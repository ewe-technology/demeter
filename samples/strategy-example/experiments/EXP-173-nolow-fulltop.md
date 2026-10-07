# EXP-173: v6.75 + +40% upper reach only while F = 1 (v6.158)

- Jira: QUAN-1079
- Status: fail
- Level: improvement (over spec v1; v6 on `0x4585`)
- Pre-registration commit: 783ad2a · Result commit: ______
- Scope: Dino, 2026-10-07, /goal "不斷的抽換v6裡面的概念，加上+-20的動態調整，直到找到總績效比v6好的策略". Batch 2 = EXP-173..175,
  pre-registered together after batch 1 (EXP-169..172) failed.

## Hypothesis

EXP-164 (v6.75 + +40% top whenever the close is above EMA100) raised CAGR on every ETH pool but its max DD was 3.3-4.2 pts deeper on both mainnet ETH pools and it lost both BTC pools: above EMA100 also covers early, fragile rebounds. F = 1 means all four accounts (EMA 90..120) are armed and fully deployed, the engine's own strongest-trend state. Widening the top only there keeps the coin through the strong trends and leaves the fragile rebounds on v6's ±20%.

## Change

Variant `GQ`: `REFILL_NO_NEW_LOW = True` + `WIDTH_SIGNAL = "full_widetop"`: at a build whose judged F = 1 the upper reach is +40% (EXP-154's value), the lower reach v6's 20%; otherwise v6's ±20%. Every constant is one an earlier EXP fixed; nothing is searched. Everything else is the baseline's.

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
| ETH mainnet 0.05% `0x88e6` | +97.7% / 13.55% / -22.9% / 0.591 | +130.4% / 16.83% / -26.2% / 0.642 | 179 → 166 | lose |
| ETH mainnet 0.3% `0x8ad5` | +100.0% / 13.78% / -21.0% / 0.657 | +130.2% / 16.81% / -25.2% / 0.667 | 178 → 163 | lose |
| ETH Base 0.05% `0xd0b5` | +54.9% / 16.96% / -34.7% / 0.489 | +58.5% / 17.91% / -36.9% / 0.485 | 84 → 81 | lose |
| ETH Arbitrum 0.05% `0xc696` | +65.7% / 26.88% / -31.4% / 0.856 | +50.1% / 21.08% / -33.5% / 0.629 | 64 → 62 | lose |
| ETH Base 0.3% `0x6c56` | +29.8% / 16.48% / -24.6% / 0.671 | +36.7% / 20.06% / -21.3% / 0.941 | 55 → 51 | **win** |
| BTC mainnet WBTC 0.3% `0x99ac` | +62.2% / 10.43% / -30.1% / 0.346 | +45.6% / 8.01% / -31.5% / 0.254 | 129 → 126 | lose |
| BTC Base cbBTC 0.05% `0xfbb6` | +44.0% / 20.46% / -16.7% / 1.224 | +39.6% / 18.55% / -15.3% / 1.215 | 49 → 48 | lose |
| WBTC/ETH 0.05% `0x4585` (v6, BTC) | -1.4% / -0.29% / -32.7% / <0 | +5.9% / 1.19% / -30.2% / 0.039 | 100 → 98 | **win** |

Verdict: **fail** — seven-pool 1/7 (ETH 1 of 5, BTC 0 of 2); median CAGR gain +0.96 pt. Restricting the +40% top to F = 1 did
not fix EXP-164: mainnet ETH CAGR +3.0 pts but max DD still 3.3 / 4.2 pts deeper (the slack is 3), and both BTC pools lose
2.4 / 1.9 pts. It is the best WBTC/ETH result of any variant so far (+1.5 pt CAGR, shallower DD).

## Deviations

- Designed after batch 1: EXP-172 (refill-low edge + v6.75 + share 50%) won 3/7, losing the BTC and L2 0.05% pools on CAGR.
  A tier variant built from batch 1's per-pool results (EXP-172's switches on 0.3% pools, v6.75 on cheaper ones) was not
  registered: its 4/7 is known from earlier runs, so it would not be a test.
