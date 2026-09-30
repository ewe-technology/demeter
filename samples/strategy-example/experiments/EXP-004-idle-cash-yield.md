# EXP-004: idle USDC earns the Aave supply rate (v6.4)

- Version: v6.4
- Jira: [QUAN-838](https://ewetechnology.atlassian.net/browse/QUAN-838)
- Status: dev-done (holdout paused)
- Pre-registration commit: 58d94b1 · Result commit: 70d58bc

## Hypothesis

v6 keeps a large share of its capital idle in USDC: the reserve (1 − F) averages 35% of principal (mean F 0.65,
ETH 2022..2026-09) and the collected fees, paid out in USDC and never reinvested, reach $86.5k on a $100k start by
2026 (`V6_VALIDATION.md` §4). None of it earns anything. Supplying that USDC to Aave (a standard, liquid money
market on every target chain) should add the supply rate on roughly half of the book without touching the signal,
the ladder or the drawdown (USDC does not move with ETH).

This is not a search for edge: the gain is non-negative by construction whenever the rate is. The experiment sizes
it on real historical rates and puts it through the same gates as any other version, and the holdout doubles as
the first v6 run on the deck's target pool (go-live condition 1).

## Change

`CASH_APR` = the daily Aave USDC supply APR of the pool's chain (v6: none).

- Once a day, before the F follow check, every USDC held outside the ladder (reserve, collected fees, earlier
  interest) earns one day of the previous day's supply APR (`currentLiquidityRate` at ~12:00 UTC, simple daily
  accrual, i.e. daily compounding of the interest itself).
- Interest is booked as income like the fees: it is not deployed into the ladder, so F sizing is unchanged.
- Rates: mainnet Aave v2 USDC until the v3 USDC market opened (2023-01-27), v3 after; Base Aave v3 USDC.
  Fetched with `samples/fetch_aave_rates.py`.
- Not modelled: Aave deposit/withdraw gas (reported-not-charged policy), withdrawal liquidity at 100% utilisation,
  smart-contract risk. Deposits/withdrawals are assumed instant at every rebuild.
- Everything else identical to v6.

## Pre-registration

- Development data (in-sample): ETH/USDC 0.05% yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 (yearly
  reset, 100,000 USDC), mainnet rates; continuous ETH 2022-01-01..2026-09-17 and WBTC/USDC 0.3%
  2022-11-01..2026-09-17 reported.
- Holdout (run once, v6 + this only): Base USDC/WETH 0.05% (`0xd0b53d9277642d899df5c87a3966a349a798f224`), never
  run by any test, Base Aave v3 USDC rates (fetched only after this commit). Yearly segments 2024, 2025,
  2026-01-01..09-17 plus the continuous 2024-01-01..2026-09-17 run (reported). The EMA engine warms up on mainnet
  ETH/USD before 2024 (the Base pool has minute data from 2023-12). Mainnet gas is still what the gas column shows.
- Success rule:
  - Dev: wins in ≥ 3 of 5 ETH segments, median gain > 0 pts, continuous ETH max DD ≥ −27.8% (≤ 5 pts worse
    than v6). Otherwise `dropped-at-dev`.
  - Holdout: wins in ≥ 2 of 3 Base segments and median gain > 0 pts → `holdout-pass`, else `holdout-fail`.

## Result

Development, ETH/USDC 0.05%, yearly reset, mainnet Aave USDC rates:

| test | v6 | this | gain | max DD v6 → this |
|---|---|---|---|---|
| 2022 | +7.6% | +8.3% | +0.7 | 21.5% → 21.2% |
| 2023 | +32.2% | +33.7% | +1.5 | 13.9% → 12.9% |
| 2024 | +36.4% | +38.9% | +2.5 | 26.7% → 25.5% |
| 2025 | +16.3% | +18.4% | +2.1 | 26.9% → 26.6% |
| 2026-01..09-17 | +18.7% | +19.9% | +1.2 | 12.0% → 11.5% |

Wins 5/5, median gain +1.46 pts.

Continuous runs (daily equity):

| run | total | CAGR | max DD | Sharpe | interest |
|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | −22.8% | 0.73 | |
| ETH this | +101.0% | 16.0% | −20.7% | 0.82 | $15.6k |
| WBTC/USDC v6 | +85.6% | 17.3% | −17.8% | 1.01 | |
| WBTC/USDC this | +96.6% | 19.0% | −16.3% | 1.10 | |

Verdict: **dev passed** (5/5, median +1.5 pts, drawdown shallower). The holdout (Base USDC/WETH 0.05% with Base
Aave rates) has **not been run**: the Base minute data stopped at 2024-03 (the public gateway rate-limited the
fetch) and on 2026-09-30 Dino redirected the work to new strategy logic, so the Base fetch was stopped. Resume with
`samples/fetch_base_monthly.sh 2024-04 2026-09-17 samples/base-data` (THREADS=3) and
`fetch_aave_rates.py base ...`, then run the holdout once as pre-registered.

## Deviations

- Holdout paused after dev (see Verdict); no Base backtest and no Base rate series exist yet. A first Base rate
  fetch failed on HTTP 429 before returning any rate.

- Mainnet rates were fetched for 3 test days (2022-01-01..03 ~3.2%, 2024-03-01..02 ~7.6%) and Base rates for
  2024-01-01..02 (8.1%, 3.7%) while writing the fetcher, before this commit. The full mainnet series was fetched
  before this commit too (dev data). No backtest with CASH_APR ran on a pre-registered window before this commit.
- Smoke test before the pre-registration commit, outside every pre-registered window: ETH 2021-12-20..26 (F ~0):
  interest $48.75 over 6 accrual days on ~$95k idle at ~3% APR, net return +0.049 pts vs v6, as expected.
