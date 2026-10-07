# EXP-164: v6.75 + +40% / -20% ladder above EMA100 on every pool on spec v1 (v6.149)

- Jira: QUAN-1051
- Status: fail
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

Run `opt-AGAGBGCGDGEGFGGGH` with `SPEC=v1`, one pool at a time, 2 workers (2026-10-07; raw runs in the main checkout's `result/v6_validate/*-opt-AGAGBGCGDGEGFGGGH-specv1-*`). `A` reproduces EXP-156's spec v1 numbers on every pool.

| pool (to 2026-09-17; Arbitrum to 2025-07-23) | spec v1 total / CAGR / max DD / Calmar | this | rebuilds | win |
|---|---|---|---|---|
| ETH mainnet 0.05% `0x88e6` from 2021-05-06 | +97.7% / 13.55% / -22.9% / 0.591 | +127.0% / 16.51% / -26.2% / 0.630 | 179 → 168 | lose |
| ETH mainnet 0.3% `0x8ad5` from 2021-05-06 | +100.0% / 13.78% / -21.0% / 0.657 | +129.6% / 16.75% / -25.2% / 0.665 | 178 → 165 | lose |
| ETH Base 0.05% `0xd0b5` from 2023-12-01 | +54.9% / 16.96% / -34.7% / 0.489 | +72.4% / 21.51% / -37.0% / 0.582 | 84 → 81 | **win** |
| ETH Arbitrum 0.05% `0xc696` from 2023-06-09 | +65.7% / 26.88% / -31.4% / 0.856 | +61.2% / 25.25% / -33.6% / 0.752 | 64 → 62 | lose |
| ETH Base 0.3% `0x6c56` from 2025-01-01 | +29.8% / 16.48% / -24.6% / 0.671 | +50.3% / 26.92% / -20.1% / 1.339 | 55 → 51 | **win** |
| BTC mainnet WBTC 0.3% `0x99ac` from 2021-11-02 | +62.2% / 10.43% / -30.1% / 0.346 | +48.3% / 8.42% / -31.2% / 0.270 | 129 → 126 | lose |
| BTC Base cbBTC 0.05% `0xfbb6` from 2024-10-01 | +44.0% / 20.46% / -16.7% / 1.224 | +39.6% / 18.56% / -15.3% / 1.215 | 49 → 48 | lose |

Verdict: **fail** — wins 2/7 (ETH 2 of 5, BTC 0 of 2), median CAGR gain +2.96 pt.

Reading: The wide top keeps more ETH in rallies: Base 0.3% +10.4 pts CAGR and Base 0.05% +4.6 pts, but max DD is 3.3-4.2 pts deeper on both mainnet ETH pools (just over the 3-pt slack) and it loses both BTC pools, as EXP-154 did.

## Deviations

- The batch was started on 2026-10-07 with two pool invocations of three workers, stopped by Dino (memory) before any result, and rerun from scratch one pool at a time with two workers; `v6_validate.py` gained `LEAN_STATUS` (identical numbers, `fddd2c4`) in between. The aborted partial outputs were deleted unread.
