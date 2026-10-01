# EXP-021: v6.16 re-judged on two fresh, deep pools — LINK/WETH and UNI/WETH (v6.16r)

- Version: v6.16r
- Jira: [QUAN-872](https://ewetechnology.atlassian.net/browse/QUAN-872)
- Status: holdout-fail
- Pre-registration commit: 9912117 · Result commit: ______
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

Holdout, run once (A and P per invocation, two workers; the two pools concurrently), all numbers in ETH:

| test | LINK/WETH v6 | LINK/WETH v6.16 (P) | short days | UNI/WETH v6 | UNI/WETH v6.16 (P) | short days |
|---|---|---|---|---|---|---|
| 2022 | −9.7% | +6.3% | 172 | −2.4% | −6.9% | 71 |
| 2023 | +8.6% | +9.4% | 107 | −16.6% | −19.8% | 138 |
| 2024 | −25.9% | −38.5% | 21 | −21.7% | −49.4% | 109 |
| 2025 | +10.8% | +4.9% | 30 | −25.7% | −22.6% | 95 |
| 2026-01..09-17 | −4.2% | −8.8% | 81 | +7.0% | +16.7% | 87 |

Wins: LINK 2/5 (median −4.6 pts), UNI 2/5 (median −3.1 pts).

Continuous 2022-01-01..2026-09-17 (daily equity in ETH):

| pool | run | total | CAGR | max DD | Sharpe | Calmar | short PnL / funding / fees | short days |
|---|---|---|---|---|---|---|---|---|
| LINK/WETH | v6 | −15.3% | −3.5% | −39.0% | −0.11 | −0.09 | | |
| | v6.16 | −26.3% | −6.3% | −51.2% | −0.21 | −0.12 | −1.09 / +0.61 / −1.54 ETH | 412 |
| UNI/WETH | v6 | −36.1% | −9.1% | −53.4% | −0.48 | −0.17 | | |
| | v6.16 | −54.6% | −15.4% | −71.8% | −0.54 | −0.22 | −10.52 / +0.54 / −1.20 ETH | 502 |

Verdict: **holdout-fail** on both pools and on every condition (CAGR lower, max DD 12 / 18 pts deeper, wins 2/5).

Reading: on the alt/ETH ratio the leg is on 2.7–3.3x as many days as on ETH/USD (412 / 502 vs 152), because both
ratios fell for most of 2022–26, and it loses: alt/ETH trends do not persist from a 12-month signal into the next
weeks the way ETH/USD's 2022 and 2025–26 bears did, and the late-2024 alt rally against ETH squeezed it (2024: −12.6
and −27.7 pts). With EXP-020's LINK/USDC result, the bear short has now failed on three fresh price paths
(LINK/USD, LINK/ETH, UNI/ETH) after passing on the ETH/USD and BTC/USD paths it was designed on. The evidence says
the leg's edge is specific to the 2022–26 ETH (and, with the crash rule, BTC) bear phases, not a general property
of the short side of this trend engine. Bear-short family closed; v6.14 / v6.16 not recommended.

## Deviations

- This is a second holdout for the same logic after EXP-020's failed one. Reason: EXP-020's pool could not host the
  book (cost-model dominated). Counted honestly: v6.16 has now been judged on two holdouts.
- Minute data: the first parallel pass hit Tenderly rate limits (HTTP 429) for 6–7 months per pool; those months were
  refetched with `ETH_RPC=https://rpc.mevblocker.io` before the run; both pools complete 2021-06-01..2026-09-17
  (May 2021, the pools' first days, has no seed price and is not used). `FIRST_DATA` set to 2021-06-01 for both after
  the pre-registration commit (configuration, not logic).
- No smoke test on these pools (it would have shown holdout numbers); the registered invocations were the first runs.
