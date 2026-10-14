# Validation addendum: defense v1 / v2 / v3 scorecards on Demeter (pre-registered 2026-10-13)

Follows `VALIDATION-2026-10-13-defense-v1-v3.md`. Dino's ruling (2026-10-13): the spec sheets give the logic only; the
real backtest performance is Maker's `maker-defense` branch run in Demeter. The daily spec simulator
(`spec_daily_sim.py`) is kept only where Demeter cannot run (synthetic price paths, random-timing null) and its
results are labelled "model". A four-agent review of the first scorecard removed five methods; eight remain, split
into generic checks (any strategy) and checks specific to v1 / v2 / v3.

Status: **done 2026-10-13** (pre-registered in 88eeb21 before any run). Slides: https://claude.ai/artifact/1rmNEUAYUosctoz7sLVBwh

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

## Result (2026-10-13; `scorecard_demeter_v123.py`, `result/validate_v123/scorecard_demeter.json`, runs in `result/validate_v123/demeter/`)

**Verdict, per chain: mainnet — not for deployment (all three fail A2: gas). Base — pilot for all three (pass A1,
A2, A3, B1; fail A4). v3 is the best of the three on Base and at every decision hour; no version is deployable.**

| method | v1 | v2 | v3 |
|---|---|---|---|
| A1 mainnet UTC 0: terminal $k / CAGR / max DD | 196.8 / 13.6 % / −29.4 % | 181.1 / 11.8 % / −29.4 % | 224.9 / 16.5 % / −21.9 % |
| A1 Base 2023-12-02..2026-08-31 | 155.0 / 17.3 % / −34.7 % | 139.4 / 12.9 % / −37.5 % | 156.6 / 17.7 % / −25.8 % |
| A1 fees / rebuilds (mainnet) | 100.2 / 179 | 92.5 / 162 | 98.4 / 164 |
| A2 mainnet gas $k | 125.7 | 112.3 | 110.6 |
| A2 mainnet: fees × 0.66 + swap × 2 + gas | **33.0 fail** | **31.4 fail** | **76.8 fail** |
| A2 Base: fees × 0.66 + swap × 2 (gas ≈ 0) | 138.0 pass | 123.3 pass | 141.6 pass |
| A3 neighbour profit vs chosen | ×0.9 −10.5 %, ×1.1 +7.0 % pass | ×1.4 −6.6 %, ×1.6 +6.5 % pass | 0.35 +4.0 %, 0.45 −2.5 % pass |
| A4 median hour: Sharpe / 1 − p / DSR | 0.21 / 0.69 / 0.23 fail | 0.27 / 0.73 / 0.35 fail | 0.62 / 0.93 / 0.76 fail |
| A4 MinTRL vs SR0 (median hour) | never (SR < SR0 0.55) | never (SR < SR0 0.44) | ~30 years (SR0 0.31) |
| A5 kill line: 90-day return, 5th pct | −11.7 % | −11.8 % | −10.3 % |
| A6 Monte Carlo (model) max DD median / p5 | −40 % / −61 % | −40 % / −59 % | −34 % / −53 % |
| B1 terminal UTC 0 / mean of 6 / worst | 196.8 / 144.4 / 116.4 pass | 181.1 / 137.9 / 114.2 pass | 224.9 / 192.5 / 164.1 pass |
| B1 UTC 0's rank of 6 hours | 1 | 1 | 1 |
| B1 worst-hour max DD | −41.8 % | −42.0 % | −26.9 % |
| B2 random timing (model, v3) | — | — | rank 0.916, fail |

Decision hours (mainnet, $k, h0 / 4 / 8 / 12 / 16 / 20): v1 196.8 / 137.5 / 172.7 / 123.2 / 119.7 / 116.4;
v2 181.1 / 114.2 / 128.7 / 127.8 / 150.6 / 124.7; v3 224.9 / 164.1 / 181.2 / 201.1 / 209.8 / 174.0. Neighbour runs
(UTC 0, mainnet): v1 ×0.9 186.6, ×1.1 203.6; v2 ×1.4 175.8, ×1.6 186.4; v3 0.35 229.9, 0.45 221.9.

Reading:
1. **Chain decides.** A 16-band ladder rebuilt 160-180 times costs $110-126k of mainnet gas on $100k over 5.3 years,
   more than the fees. On Base the same logic keeps its profit under a fee haircut to 0.66 and double swap cost.
2. **UTC 0 is the best of six hours for all three.** Expect the six-hour mean: v1 −27 %, v2 −24 %, v3 −14 % below
   the UTC 0 figure.
3. **Parameters are on a plateau** for all three (profit within ±11 % one step away). The overfitting concern is not
   the parameters; it is the decision hour and the small sample.
4. **No edge is statistically established.** v3's Sharpe 0.62 sits above the expected best of 108 tries (0.31) but
   the DSR is 0.76; about 30 years of daily data would be needed. v3's divergence exits beat random exits on 92 % of
   draws (model), short of 95 %.
5. **Pilot on Base**: v3 first (Base 156.6 $k, max DD −25.8 %, mainnet worst hour still 164.1 $k). Size small; stop
   if a 90-day return falls below −10.3 %. Base has 2.75 years of data and no 2022-style bear market.

## Deviations

- The decision-hour runs (R1) crash in Maker's post-run metrics (benchmark length mismatch, 2,799,120 vs 2,799,359
  rows) after the backtest has finished and written net value, events and daily fees. Their fees come from the daily
  fee log and their swap cost is rebuilds × the version's UTC 0 swap cost per rebuild (swap cost is $4-6k, gas $77-188k).
- The neighbour runs (R3) skip Maker's `_self_check()`, which asserts the default parameters; first attempt failed on it.
- The pre-registration did not say whether A2 must pass on both chains. "On the pool's own chain" is read as a verdict
  per chain. B1 was run on mainnet only.
- A4 var(SR) is taken over the six hours and the two neighbours of each version.

## Final scorecard (2026-10-14, Dino's scope; supersedes the verdict above)

Dino's changes after reviewing the slides: keep only generic methods; drop the cost and gas stress (old A2) and the
two v1/v2/v3-specific checks (B1, B2); compute every remaining method from the method-1 Demeter backtests on both
pools; drop DSR and MinTRL from significance. Five methods, renumbered: 1 real-data backtest (old A1), 2 parameter
plateau (A3), 3 significance (A4 without DSR / MinTRL, bar PSR >= 0.95), 4 forward kill line (A5), 5 Monte Carlo
(A6, now a stationary block bootstrap of the method-1 daily returns, mean block 90 days, 10,000 one-year paths,
instead of the simulator). Script `scorecard_final_v123.py`, output `result/validate_v123/scorecard_final.json`.
All figures exclude gas and the spec's 25 % success fee. UTC 0.

**Reproduction of Maker's figures first.** Maker's scripts rerun unchanged on their default yearly windows (1/2 start,
$100k each year; only v2's `_compound` set to False, as in Maker's V3.md 6.1 table): all twelve yearly returns match
within 0.1 pt (v1 +11.8 / +40.4 / +32.3 / +16.3 %; v2 +20.7 / +21.9 / +19.6 / +22.6 %; v3 +20.7 / +21.9 / +23.2 /
+16.8 %), and so do fees, rebalance counts and minute drawdowns. Raw runs: `result/validate_v123/yearly/`.

| method (mainnet / Base) | v1 | v2 | v3 |
|---|---|---|---|
| 1 terminal $k | 196.8 / 155.0 | 181.1 / 139.4 | 224.9 / 156.6 |
| 1 CAGR / max DD | 13.6 % −29.4 % / 17.3 % −34.7 % | 11.8 % −29.4 % / 12.9 % −37.5 % | 16.5 % −21.9 % / 17.7 % −25.8 % |
| 2 plateau (mainnet), profit one step away | −10.5 / +7.0 % | −6.6 / +6.5 % | +4.0 / −2.5 % |
| 3 annual Sharpe | 0.60 / 0.58 | 0.58 / 0.48 | 0.78 / 0.74 |
| 3 PSR (bar 0.95) | 0.92 / 0.83 | 0.91 / 0.79 | **0.96** / 0.89 |
| 3 bootstrap 1 − p | 0.93 / 0.84 | 0.91 / 0.78 | 0.96 / 0.87 |
| 4 kill line, 90-day return | −12.0 % / −14.3 % | −12.0 % / −14.9 % | −10.5 % / −12.2 % |
| 5 one-year max DD median / 5th pct | −15 −28 % / −19 −33 % | −15 −28 % / −19 −36 % | −14 −23 % / −17 −28 % |
| 5 one-year loss probability | 21 % / 23 % | 23 % / 29 % | 19 % / 21 % |
| verdict mainnet / Base | pilot / pilot | pilot / pilot | **deployable\*** / pilot |

Verdict ladder: method 1 fails → not for deployment; 1 and 2 pass → pilot; 3 also passes → deployable. \*Without gas:
mainnet gas for v3's 164 rebuilds is about $110k on $100k over 5.3 years (estimate, `v6_validate.py:126` gas units,
not measured on chain), so the mainnet verdict needs a measured gas cost before any deployment.

Formulas: r_t = ln(V_t / V_t−1) on the daily net value; SR = mean(r) / std(r), annual × √365;
D = √(1 − skew·SR + (kurt − 1)/4·SR²); PSR = Φ(SR·√(T − 1) / D); 1 − p from 5,000 stationary-bootstrap means
(mean block 20 d), p = share(boot − mean ≥ mean); kill line = exp(P5 of 90-day sums of bootstrapped r) − 1 over
10,000 draws; Monte Carlo path E_t = exp(Σ r*), t = 1..365, max DD = min(E_t / max_(s≤t) E_s − 1),
loss probability = share(E_365 < 1).
