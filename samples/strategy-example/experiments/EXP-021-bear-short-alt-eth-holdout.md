# EXP-021: v6.16 re-judged on two fresh, deep pools — LINK/WETH and UNI/WETH (v6.16r)

- Version: v6.16r
- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Parent: `EXP-020-bear-short-no-crash-entry.md` (v6.16: dev pass on all four ETH/BTC pools, holdout-fail on
  LINK/USDC because the pool is too thin for the book — impact 37–63% of capital, v6 itself −62%). Pure strategy
  logic, no cash yield (Dino, 2026-10-01).

## Hypothesis

EXP-020's holdout could not test the short logic: the only USDC-quoted pools for assets other than ETH/BTC are thin
(LINK/USDC ~$1.5M virtual at the active tick today and ~100 swaps a month in 2022; ARB/USDC on Arbitrum ~$47k;
WMATIC/USDC on Polygon $0.15–0.76M), so the price-impact ledger dominates. The deep pools for other assets are
ETH-quoted: LINK/WETH 0.3% (~19,700 ETH virtual per side, ≈ $49M) and UNI/WETH 0.3% (~6,500 ETH, ≈ $16M). In ETH
numeraire v6 times the alt/ETH ratio — the same machinery EXP-009 used on WBTC/WETH. If the bear short without
crash-day entries is a real trend-following edge rather than an ETH-2022–26 accident, it should beat v6 on these two
price paths, which no run in this repo has touched.

## Change

None to the logic: v6.16 (`BEAR_SHORT = 0.5`, 12-month filter, `BEAR_CRASH_SIGMA = 2.0`, `BEAR_CRASH_WINDOW = 30`).
What the venue forces:

- The short is a synthetic ALT/ETH perp: short ALTUSDT + long ETHUSDT of equal notional. Price PnL settles daily at
  the pool's ALT/ETH price into WETH; funding per 8h = rate(ALT) − rate(ETH) (`samples/make_synthetic_funding.py`,
  annualised +2.0% LINK, +2.3% UNI for the short over 2021-12..2026-09); taker fee 0.05% on each leg, so
  `HEDGE_FEE = 0.001` per traded notional. Variant `P` = `O` with that fee.
- 12-month return from Binance daily closes, ALTUSDT / ETHUSDT.
- 40 WETH starting book (≈ $100k), WETH is the numeraire; all metrics in ETH.

## Pre-registration

- Holdout (run once, v6 `A` and `P` only), mainnet:
  - LINK/WETH 0.3% `0xa6cc3c2531fdaa6ae1a3ca84c2855806728693e8`
  - UNI/WETH 0.3% `0x1d42064fc4beb5f8aaf85f4617ae8b3b5b8bd801`
  - each: continuous 2022-01-01..2026-09-17 and yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17; EMA
    warm-up from the pool's own minutes (from its first data day, 2021-05). Minute data fetched 2026-10-01 with
    `samples/fetch_uni_minute.py`; nothing loaded or looked at before this commit except today's pool liquidity.
- Success rule, on **each** pool (`P` vs `A`, daily equity in ETH, Calmar = CAGR / |max DD|):
  - continuous CAGR above v6's, **and** Calmar ≥ v6's (if v6's CAGR is negative: `P`'s CAGR above and max DD not
    deeper), **and** max DD no more than 3 pts deeper than v6's, **and** yearly wins ≥ 3 of 5
  → `holdout-pass` only if both pools pass; else `holdout-fail`.
- No dev stage: EXP-020's dev (four ETH/BTC pools) stands.

## Result

Pending.

## Deviations

- This is a second holdout for the same logic after EXP-020's failed one. Reason: EXP-020's pool could not host the
  book (cost-model dominated). Counted honestly: v6.16 has now been judged on two holdouts.
