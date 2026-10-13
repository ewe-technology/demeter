# Validation addendum: defense v1 / v2 / v3 scorecards on Demeter (pre-registered 2026-10-13)

Follows `VALIDATION-2026-10-13-defense-v1-v3.md`. Dino's ruling (2026-10-13): the spec sheets give the logic only; the
real backtest performance is Maker's `maker-defense` branch run in Demeter. The daily spec simulator
(`spec_daily_sim.py`) is kept only where Demeter cannot run (synthetic price paths, random-timing null) and its
results are labelled "model". A four-agent review of the first scorecard removed five methods; eight remain, split
into generic checks (any strategy) and checks specific to v1 / v2 / v3.

Status: **pre-registered** (no run below has started when this file is committed).

## 1. Source of truth and runs

Maker's scripts at `maker-defense` 5cec767, standard mode, $100k, run with this branch's `demeter` (one-line `int`
cast fix). Changes applied by `experiments/demeter_runs_v123.py`, text replacements only, each asserted:
window, decision hour (trigger `pending` + Binance closes at that hour), pool, one parameter for the neighbour runs,
and a net-value CSV export for v1 (v2 / v3 already write one).

| set | runs | window |
|---|---|---|
| R0 | v1 / v2 / v3, mainnet WETH/USDC 0.05 % `0x88e6`, UTC 0 (v2 / v3 reuse the T10 runs; v1 rerun for its net value) | 2021-05-06..2026-08-31 |
| R1 decision hour | v1 / v2 / v3 at 04, 08, 12, 16, 20 UTC, mainnet | same |
| R2 second pool | v1 / v2 / v3, Base WETH/USDC 0.05 % `0xd0b5`, UTC 0 | 2023-12-02..2026-08-31 |
| R3 neighbours | v1 ladder ×0.9 / ×1.1; v2 ladder ×1.4 / ×1.6; v3 trigger 0.35 / 0.45 (release 0.20); mainnet, UTC 0 | 2021-05-06..2026-08-31 |

Hour h: the daily trigger fires at h:00 and judges the Binance ETHUSDT close at that h:00 (built from 1 h klines,
`samples/binance_ethusdt_1h.csv`); EMA, accounts and flag are computed on that series from 2017-08-17.

## 2. Methods and bars

"Team bar" = our choice, not from a paper. Max DD is the largest percentage drop of the minute net value (not
demeter's `max_draw_down`, which picks the largest dollar drop).

### A. Generic (any strategy)

| # | method | how | bar |
|---|---|---|---|
| A1 | real-data backtest | R0 + R2: terminal, CAGR, % max DD, fees, rebuilds | terminal > $100k on both pools |
| A2 | cost and gas stress | post hoc on R0 / R2: fees × 0.66 (Demeter / model ratio seen in 2025-26) and × 0.8; extra swap cost = rebuild swap notional × 0.1 %; gas = rebuilds × 11.5 M gas (16 removes + 16 adds + 1 swap, `v6_validate.py:126`) × mainnet hourly gwei × ETH price; Base gas taken as 0 | terminal > $100k after fees × 0.66 + swap × 2, on the pool's own chain (mainnet with gas) — team bar |
| A3 | parameter plateau | R3: profit (terminal − 100) of each neighbour vs the chosen value | both neighbours within ±25 % of the chosen profit — team bar |
| A4 | significance | daily log returns from the net value, each of the 6 hours of R0 + R1: one-sided stationary bootstrap (mean block 20 d), PSR, DSR with N = 18 × 6 and var(SR) over hours and neighbours, MinTRL against the DSR benchmark SR0 | median-hour DSR >= 0.95 |
| A5 | forward test with kill line | kill line = 5th percentile of 90-day returns from block-bootstrapped R0 daily returns; forward data after 2026-08-31 | rule only: the forward window (to 2026-09-17) is too short to judge |
| A6 | Monte Carlo (model) | `validate_v123.py` t8b paths; drawdown only, set against the 2018- simulator history | none (stress figure) |

### B. Specific to v1 / v2 / v3

| # | method | why specific | how | bar |
|---|---|---|---|---|
| B1 | decision hour | the versions judge once a day on one Binance close | R0 + R1 (6 hours): mean, worst, UTC 0's rank | worst hour terminal > $100k — team bar |
| B2 | random-timing null (model) | tests v3's divergence exit, its only rule beyond v2 | 1,000 random exits with v3's count and lengths, starting only on days with F' >= 0.9 and close > EMA100, the episode open at the window start excluded; spec window, UTC 0 | v3 terminal rank >= 0.95 |

## 3. Verdict per version

- **not for deployment**: fails A1, A2 or B1.
- **pilot (small size, forward kill line)**: passes A1, A2, A3 and B1; fails A4.
- **deployable**: also passes A4 (and B2 for v3).

## 4. Corrections to the first write-up (made with the results)

- T10 max DD: demeter's metric is a dollar drop; the minute percentage DD is v2 −29.4 %, v3 −21.9 % (was −24.7 / −17.7 %).
- T8a: the drawdown pass came from the episode open at the window start; with it excluded the rank is 0.06.
- v3 DSR: 0.72-0.87 depending on var(SR); MinTRL against SR0 about 12-17 years, not 6.9.

## Result

(empty until the runs are done)
