# EXP-020: bear short leg without entries on crash days, pure strategy logic (v6.16)

- Version: v6.16
- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Parent: `EXP-018-bear-short-leg.md` (v6.14: dev pass on ETH, holdout-fail on WBTC). No cash yield: Dino asked
  (2026-10-01) to judge strategy logic only, so EXP-004's Aave yield is off in every run here.

## Hypothesis

v6.14's short leg fails on WBTC because its losing episodes are entries taken on the day of a one-day crash that
then reverts: FTX 2022-11-10, SVB 2023-03-10, SEC suit 2023-06-06 on BTC; COVID 2020-03-13, SVB 2023-03-10 on
ETH. A crash day pushes the close below all four EMAs and arms the short at the low; the rebound costs 3–12% of
equity at 0.5x. Momentum shorts lose most in "panic states" right after sharp declines (Daniel and Moskowitz 2016,
"Momentum crashes", JFE; Barroso and Santa-Clara 2015). Not opening a new short on a crash day, and letting the
next ordinary day decide, removes those entries while leaving the long bear episodes (2022, 2025, 2026: entries on
ordinary down days) untouched.

Screened before this file on Binance daily closes, standalone leg 2020–26 at 0.5x (dev data, seen):
ETH +45.8% / max DD −16.1% → +63.5% / −12.1%; BTC +11.9% / −14.4% → +23.3% / −7.2%. Two other fixes were seen and
rejected the same way: inverse-volatility sizing (30 / 126-day; BTC unchanged) and, earlier (EXP-019), a 3-day
entry confirmation and the Momentum Turning Points 1-month rule.

## Change

v6.14 (`BEAR_SHORT = 0.5`, 12-month filter, EXP-014 perp mechanics, Binance funding) plus one entry rule:

    crash(d)   = ln(close_d / close_{d−1}) < −2 x std(ln returns of the 30 days before d)
    short(d)   = cond(d) and (short(d−1) or not crash(d))        # cond = v6.14's condition

`BEAR_CRASH_SIGMA = 2.0` (the conventional two-sigma tail), `BEAR_CRASH_WINDOW = 30` (one month of daily returns,
the short horizon of the momentum-crash literature). Closes from the pool's own daily close, like the EMAs. An open
short is never closed by the rule. Variant `O`. Same invocation: v6 (`A`) and v6.14 (`M`). No `CASH_APR` anywhere.

## Pre-registration

- Development (all seen before; A, M, O in one invocation each):
  - ETH/USDC 0.05% mainnet: yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
    2022-01-01..2026-09-17;
  - WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17;
  - Base USDC/WETH 0.05% continuous 2024-01-01..2026-09-17;
  - Base USDC/cbBTC 0.05% continuous 2025-01-01..2026-09-17.
- Holdout (run once, A, M, O): **mainnet LINK/USDC 0.3%** (`0xfad57d2039c21811c8f2b5d5b65308aa99d31559`), an asset
  no strategy run in this repo has touched (minute data fetched 2026-10-01 with `samples/fetch_uni_minute.py`),
  10,000 USDC (thin pool: ~$1.5M virtual liquidity at the active tick, so the book stays a small fee share),
  Binance LINKUSDT funding and daily closes. Continuous 2022-01-01..2026-09-17 plus yearly segments 2022, 2023, 2024,
  2025, 2026-01-01..09-17. EMA warm-up from the pool's own minutes (from its first data day).
- Success rule (`O` vs v6 `A`; daily equity; Calmar = CAGR / |max DD|):
  - Dev: on all four pools continuous Calmar ≥ v6's and max DD no more than 2 pts deeper than v6's; on ETH CAGR and
    Sharpe above v6's and yearly wins ≥ 3 of 5 with median gain > 0. Else `dropped-at-dev`.
  - Holdout (LINK): continuous CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper than v6's, and
    yearly wins ≥ 3 of 5 → `holdout-pass`, else `holdout-fail`.
- Forward holdout (clean): ETH and BTC 2026-09-18..2026-12-31 in January 2027, same holdout rule.

## Result

Pending.

## Deviations

- The entry rule and its constants were chosen after the screen above on the dev data; 2.0 / 30 were the only
  values computed (no grid). The holdout asset was chosen before any LINK data was loaded or any LINK price looked
  at beyond the pool's current liquidity.
