# EXP-162: v6.75 + two-day EMA exit confirmation on every pool on spec v1 (v6.147)

- Jira: QUAN-1049
- Status: fail
- Level: improvement (over spec v1)
- Pre-registration commit: c90d19c · Result commit: 3cdce86
- Scope: Dino, 2026-10-07, /goal "再繼續不斷的開發uni策略，找到五個打敗基準的策略" (keep developing Uniswap strategies until five
  beat the baseline). First batch on the spec v1 baseline (EXP-156): EXP-157..164, pre-registered together, one invocation per
  pool with `A` and all eight variants.

## Hypothesis

Two-day exit confirmation (EXP-044) passed the standalone level by skipping one-day EMA whipsaws (fewer exit / refill round trips). With the no-new-low refill the account also re-enters later after real breaks.

## Change

Variant `GF`: REFILL_NO_NEW_LOW + EXIT_CONFIRM = 2 (the EMA exit needs two consecutive closes below the EMA) on every pool. Everything else is spec v1 (`SPEC=v1`: Binance-close engine, spec weights in equal price steps, flat
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
| ETH mainnet 0.05% `0x88e6` from 2021-05-06 | +97.7% / 13.55% / -22.9% / 0.591 | +94.7% / 13.22% / -23.2% / 0.569 | 179 → 173 | lose |
| ETH mainnet 0.3% `0x8ad5` from 2021-05-06 | +100.0% / 13.78% / -21.0% / 0.657 | +102.3% / 14.03% / -21.6% / 0.651 | 178 → 169 | lose |
| ETH Base 0.05% `0xd0b5` from 2023-12-01 | +54.9% / 16.96% / -34.7% / 0.489 | +55.1% / 16.99% / -36.2% / 0.470 | 84 → 82 | lose |
| ETH Arbitrum 0.05% `0xc696` from 2023-06-09 | +65.7% / 26.88% / -31.4% / 0.856 | +65.0% / 26.63% / -32.2% / 0.828 | 64 → 64 | lose |
| ETH Base 0.3% `0x6c56` from 2025-01-01 | +29.8% / 16.48% / -24.6% / 0.671 | +35.7% / 19.58% / -20.4% / 0.961 | 55 → 51 | **win** |
| BTC mainnet WBTC 0.3% `0x99ac` from 2021-11-02 | +62.2% / 10.43% / -30.1% / 0.346 | +46.6% / 8.16% / -30.2% / 0.271 | 129 → 129 | lose |
| BTC Base cbBTC 0.05% `0xfbb6` from 2024-10-01 | +44.0% / 20.46% / -16.7% / 1.224 | +30.5% / 14.53% / -17.5% / 0.828 | 49 → 50 | lose |

Verdict: **fail** — wins 1/7 (ETH 1 of 5, BTC 0 of 2), median CAGR gain -0.25 pt.

Reading: Two-day exit confirmation costs CAGR almost everywhere (BTC cbBTC -5.9 pts); only Base ETH 0.3% (2025-26, one regime) wins, by a lot (+3.1 pts, DD -20.4% vs -24.6%).

## Deviations

- The batch was started on 2026-10-07 with two pool invocations of three workers, stopped by Dino (memory) before any result, and rerun from scratch one pool at a time with two workers; `v6_validate.py` gained `LEAN_STATUS` (identical numbers, `fddd2c4`) in between. The aborted partial outputs were deleted unread.
