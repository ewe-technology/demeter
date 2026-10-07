# EXP-164: v6.75 + +40% / -20% ladder above EMA100 on every pool on spec v1 (v6.149)

- Jira: QUAN-1051
- Status: pre-registered
- Level: improvement (over spec v1)
- Pre-registration commit: c90d19c · Result commit: ______
- Scope: Dino, 2026-10-07, /goal "再繼續不斷的開發uni策略，找到五個打敗基準的策略" (keep developing Uniswap strategies until five
  beat the baseline). First batch on the spec v1 baseline (EXP-156): EXP-157..164, pre-registered together, one invocation per
  pool with `A` and all eight variants.

## Hypothesis

EXP-154 raised CAGR on every valid ETH pool (it keeps more ETH through rallies) but lost the BTC pools; v6.75's refill filter is the one rule that helped both assets. Together they target bull-market upside and bear-market refills.

## Change

Variant `GH`: REFILL_NO_NEW_LOW + WIDE_TOP_ABOVE_EMA = 0.40 (EXP-154's ladder: above EMA100 the top edge is +40%, below it ±20%) on every pool. Everything else is spec v1 (`SPEC=v1`: Binance-close engine, spec weights in equal price steps, flat
0.1% swap cost, no impact ledger). No constant is searched; every value is the one an earlier EXP fixed.

## Pre-registration

- Baseline: `A` under `SPEC=v1` (spec sheet v1), same invocation, `opt:A,GA,GB,GC,GD,GE,GF,GG,GH`.
- Pools (full history, one continuous run each; EXP-154 / 156's seven pools):
   - ETH: mainnet `0x88e6` 2021-05-06..2026-09-17; mainnet 0.3% `0x8ad5` 2021-05-06..2026-09-17; Base 0.05% `0xd0b5`
     2023-12-01..2026-09-17; Arbitrum 0.05% `0xc696` 2023-06-09..2025-07-23; Base 0.3% `0x6c56` 2025-01-01..2026-09-17.
   - BTC (Binance BTCUSDT signal): mainnet WBTC/USDC 0.3% `0x99ac` 2021-11-02..2026-09-17; Base USDC/cbBTC 0.05% `0xfbb6`
     2024-10-01..2026-09-17.
- Success rule (full-history bar, as EXP-156 part 2): on a pool the variant wins if CAGR > spec v1, Calmar >= spec v1 and max
  DD no more than 3 pts deeper. Pass: wins on at least 4 of 7 pools with at least one ETH and one BTC pool among them; `fail`
  otherwise. A pool whose `A` run errors or is invalid counts as a loss. Every pool is reported.
- Gas is reported, not charged.

## Result

Verdict:

## Deviations

None.
