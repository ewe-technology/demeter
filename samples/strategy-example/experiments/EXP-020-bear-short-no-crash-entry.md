# EXP-020: bear short leg without entries on crash days, pure strategy logic (v6.16)

- Version: v6.16
- Jira: [QUAN-871](https://ewetechnology.atlassian.net/browse/QUAN-871)
- Status: holdout-fail
- Pre-registration commit: 0108b0a · Result commit: a12e390
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

Development (A, M, O in one invocation each; no cash yield anywhere):

| pool, continuous | v6 total / CAGR / max DD / Sharpe / Calmar | v6.14 (M) | **v6.16 (O)** |
|---|---|---|---|
| ETH mainnet 2022-01..2026-09-17 | +85.4% / 14.0% / −22.8% / 0.73 / 0.61 | +219.3% / 28.0% / −23.4% / 1.05 / 1.20 | **+215.3% / 27.6% / −23.4% / 1.05 / 1.18** |
| WBTC mainnet 2022-11..2026-09-17 | +85.6% / 17.3% / −17.8% / 1.01 / 0.97 | +80.8% / 16.5% / −18.1% / 0.91 / 0.91 | **+96.7% / 19.1% / −17.8% / 1.04 / 1.07** |
| Base USDC/WETH 2024-01..2026-09-17 | +55.9% / 17.8% / −28.1% / 0.76 / 0.63 | +92.4% / 27.3% / −28.1% / 0.95 / 0.97 | **+89.8% / 26.7% / −28.1% / 0.94 / 0.95** |
| Base cbBTC 2025-01..2026-09-17 | +22.3% / 12.5% / −15.7% / 0.93 / 0.79 | +30.2% / 16.7% / −13.8% / 1.02 / 1.21 | **+31.4% / 17.3% / −13.8% / 1.06 / 1.25** |

ETH yearly (v6 → O): 2022 +7.6% → +46.9%, 2023 +32.2% → +33.8%, 2024 +36.4% → +36.4% (tie, never on), 2025 +16.3%
→ +21.7%, 2026 +18.7% → +36.9%: wins 4/5 + 1 tie, median +5.45 pts. ETH short days 152 (M 158), short PnL +$89.2k.

Dev rule: Calmar ≥ v6 on all four pools, max DD at most 0.6 pts deeper, ETH CAGR / Sharpe above, wins ≥ 3/5 →
**dev passes**. The crash-day rule fixes v6.14's WBTC failure (Calmar 0.91 → 1.07, now above v6's 0.97) at a
small cost on ETH (1.20 → 1.18).

Holdout, mainnet LINK/USDC 0.3%, 10,000 USDC, run once (A, M, O):

| test | v6 | v6.16 (O) | gain | max DD v6 → O | v6.14 (M) |
|---|---|---|---|---|---|
| 2022 | −59.2% | −44.8% | +14.4 | 67.7% → 73.8% | −53.8% |
| 2023 | +11.9% | −10.9% | −22.8 | 33.0% → 46.7% | −11.1% |
| 2024 | −1.4% | −6.5% | −5.1 | 36.9% → 36.9% | −5.8% |
| 2025 | −37.3% | −39.4% | −2.2 | 63.3% → 63.7% | −40.1% |
| 2026-01..09-17 | +14.6% | +43.8% | +29.2 | 16.0% → 16.2% | +40.9% |

Continuous 2022-01..2026-09-17: v6 −62.4% / CAGR −18.7% / max DD −81.2%; O −59.9% / −17.6% / −96.5%; M −69.1% /
−22.1% / −100.1%. Price impact charged: v6 $3.65k, O $6.28k, M $6.25k on a $10k book (215 rebuilds, $316k–$386k
of swaps); LP fees $5.3k–$6.1k; short PnL O +$3.85k, M +$2.82k.

Verdict: **holdout-fail** — CAGR above v6 (−17.6% vs −18.7%) but max DD 15.3 pts deeper and yearly wins 2/5.

What the holdout measured: the LINK pool is too thin for this book. The price-impact model (virtual reserves at the
active tick) charges 37–63% of starting capital over the window, more than all LP fees; v6 itself loses 62%. The
short leg's own PnL is positive (+$3.85k), but each short win enlarges the book and so the next rebuild's impact,
and the cumulative impact ledger drives the drawdown (M's equity touches −$18 in Aug 2023 from charges, not from
the short). The pool's price itself tracks Binance (median deviation 0.2%, 1 day > 20%). So this is a fail of the
registered test, and the test says little about the short logic; it does say that v6 and its variants cannot run
on a pool this thin.

## Deviations

- The entry rule and its constants were chosen after the screen above on the dev data; 2.0 / 30 were the only
  values computed (no grid). The holdout asset was chosen before any LINK data was loaded or any LINK price looked
  at beyond the pool's current liquidity.
- Holdout choice was poor: the pool's liquidity was checked only as today's active-tick L (~$1.5M virtual); its
  2022–23 activity (~100 swaps a month) and the impact model's cost at this size were not checked before
  registering. Recorded as the registered result anyway.
- A one-month smoke test (ETH 2023-03, M and O) ran after the pre-registration to check the code (O shorted 1 day vs
  M 2 around SVB; the 2-day crash makes the second day an ordinary entry). Deleted, not used.
- LINK minute data: May 2022 failed in the first pass (a day without swaps at a fetch-chunk start has no seed price)
  and was refetched from 2022-04-25; the pool's first data day is 2021-06-01 (FIRST_DATA corrected from 05-05).
