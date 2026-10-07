# EXP-158: v6.75 + cross-asset refill on every pool on spec v1 (v6.143)

- Jira: QUAN-1045
- Status: pass
- Level: improvement (over spec v1)
- Pre-registration commit: c90d19c · Result commit: 3cdce86
- Scope: Dino, 2026-10-07, /goal "再繼續不斷的開發uni策略，找到五個打敗基準的策略" (keep developing Uniswap strategies until five
  beat the baseline). First batch on the spec v1 baseline (EXP-156): EXP-157..164, pre-registered together, one invocation per
  pool with `A` and all eight variants.

## Hypothesis

EXP-130 / 140's ETH half without the macro restore, so no doubled rebuilds. Under the old model the cross-asset gate hurt WBTC 0.3% (EXP-144..148); EXP-156 showed the 0.3% half was the problem on ETH 0.3% pools and Base cbBTC won with this gate. A market-wide rebound filter should help wherever refills follow single-asset bounces.

## Change

Variant `GB`: REFILL_NO_NEW_LOW + REFILL_GATE = xasset (each stage also needs the other asset's Binance close >= 1.05 x its low since the exit: BTC for ETH pools, ETH for BTC pools), on every pool. Everything else is spec v1 (`SPEC=v1`: Binance-close engine, spec weights in equal price steps, flat
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
| ETH mainnet 0.05% `0x88e6` from 2021-05-06 | +97.7% / 13.55% / -22.9% / 0.591 | +130.8% / 16.87% / -24.1% / 0.698 | 179 → 165 | **win** |
| ETH mainnet 0.3% `0x8ad5` from 2021-05-06 | +100.0% / 13.78% / -21.0% / 0.657 | +124.2% / 16.23% / -22.4% / 0.724 | 178 → 167 | **win** |
| ETH Base 0.05% `0xd0b5` from 2023-12-01 | +54.9% / 16.96% / -34.7% / 0.489 | +54.5% / 16.84% / -36.4% / 0.462 | 84 → 82 | lose |
| ETH Arbitrum 0.05% `0xc696` from 2023-06-09 | +65.7% / 26.88% / -31.4% / 0.856 | +63.8% / 26.20% / -33.0% / 0.795 | 64 → 65 | lose |
| ETH Base 0.3% `0x6c56` from 2025-01-01 | +29.8% / 16.48% / -24.6% / 0.671 | +31.5% / 17.36% / -24.4% / 0.711 | 55 → 52 | **win** |
| BTC mainnet WBTC 0.3% `0x99ac` from 2021-11-02 | +62.2% / 10.43% / -30.1% / 0.346 | +59.5% / 10.06% / -30.2% / 0.333 | 129 → 122 | lose |
| BTC Base cbBTC 0.05% `0xfbb6` from 2024-10-01 | +44.0% / 20.46% / -16.7% / 1.224 | +44.4% / 20.62% / -16.7% / 1.233 | 49 → 44 | **win** |

Verdict: **pass** — wins 4/7 (ETH 3 of 5, BTC 1 of 2), median CAGR gain +0.15 pt.

Reading: Largest ETH gains of the gas-neutral variants (mainnet 0.05% +3.3 pts CAGR) and fewer rebuilds than spec v1, but the cross-asset gate loses WBTC 0.3% (as EXP-144..148 found under the old model); its BTC win is Base cbBTC (+0.2 pt).

## Deviations

- The batch was started on 2026-10-07 with two pool invocations of three workers, stopped by Dino (memory) before any result, and rerun from scratch one pool at a time with two workers; `v6_validate.py` gained `LEAN_STATUS` (identical numbers, `fddd2c4`) in between. The aborted partial outputs were deleted unread.
