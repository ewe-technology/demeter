# EXP-174: v6.75 + +40% upper reach while F = 1 + refill-low lower edge while refilling (v6.159)

- Jira: QUAN-1080
- Status: fail
- Level: improvement (over spec v1; v6 on `0x4585`)
- Pre-registration commit: 783ad2a · Result commit: f3d8317
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

One invocation per pool, `opt:A,GQ,GR,GS`, one pool at a time, 2 workers (2026-10-08; raw runs in the main checkout's
`result/v6_validate/*-opt-AGQGRGS-*`), seven pools with `SPEC=v1` and `0x4585` with `BINANCE_WARM=1` (values in BTC). `A`
reproduces EXP-157's spec v1 numbers on every pool and v6's -1.40% on `0x4585`.

| pool | baseline total / CAGR / max DD / Calmar | this | rebuilds | win |
|---|---|---|---|---|
| ETH mainnet 0.05% `0x88e6` | +97.7% / 13.55% / -22.9% / 0.591 | +123.5% / 16.16% / -25.1% / 0.645 | 179 → 172 | **win** |
| ETH mainnet 0.3% `0x8ad5` | +100.0% / 13.78% / -21.0% / 0.657 | +123.3% / 16.15% / -24.0% / 0.671 | 178 → 169 | lose |
| ETH Base 0.05% `0xd0b5` | +54.9% / 16.96% / -34.7% / 0.489 | +62.1% / 18.86% / -36.7% / 0.514 | 84 → 83 | **win** |
| ETH Arbitrum 0.05% `0xc696` | +65.7% / 26.88% / -31.4% / 0.856 | +50.2% / 21.12% / -33.3% / 0.635 | 64 → 63 | lose |
| ETH Base 0.3% `0x6c56` | +29.8% / 16.48% / -24.6% / 0.671 | +40.4% / 21.98% / -21.3% / 1.033 | 55 → 53 | **win** |
| BTC mainnet WBTC 0.3% `0x99ac` | +62.2% / 10.43% / -30.1% / 0.346 | +44.0% / 7.77% / -31.3% / 0.248 | 129 → 132 | lose |
| BTC Base cbBTC 0.05% `0xfbb6` | +44.0% / 20.46% / -16.7% / 1.224 | +39.9% / 18.69% / -16.5% / 1.133 | 49 → 51 | lose |
| WBTC/ETH 0.05% `0x4585` (v6, BTC) | -1.4% / -0.29% / -32.7% / <0 | +3.8% / 0.78% / -31.2% / 0.025 | 100 → 105 | **win** |

Verdict: **fail** — seven-pool 3/7 (ETH 3 of 5, BTC 0 of 2); median CAGR gain +1.90 pt (the highest of the batch). The
refill-low edge took about 1 pt off GQ's drawdown on the mainnet ETH pools (26.2 → 25.1, 25.2 → 24.0), enough for `0x88e6`
but not `0x8ad5`; both BTC pools still lose 1.8..2.7 pts CAGR.

## Deviations

- Designed after batch 1: EXP-172 (refill-low edge + v6.75 + share 50%) won 3/7, losing the BTC and L2 0.05% pools on CAGR.
  A tier variant built from batch 1's per-pool results (EXP-172's switches on 0.3% pools, v6.75 on cheaper ones) was not
  registered: its 4/7 is known from earlier runs, so it would not be a test.
