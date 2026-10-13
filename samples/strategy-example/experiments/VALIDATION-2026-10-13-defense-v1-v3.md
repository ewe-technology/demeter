# Validation: is Maker's defense v1 / v2 / v3 (ETH/USDC) an edge or an overfit? (pre-registered 2026-10-13)

Jira QUAN-1129 (research: strategy validation methods). Methods and their sources:
`RESEARCH-2026-10-13-strategy-validation.md`. This is a validation of existing strategies, not a new v6.x version, so it
has no EXP number, Jira subtask or dashboard row.

Status: **pre-registered** (no test below has been run when this file is committed).

## 1. What is tested

| version | rule set (spec sheets on Drive, code on `maker-defense`) |
|---|---|
| v1 | four-EMA (90/100/110/120) virtual accounts, refill ladder +5 / 8.33 / 11.67 / 15 % (first stage 3 days), F = stage / 4, ±20 % 16-band valley, share 70 % above EMA100 else 50 %, follow threshold 12.5 % |
| v2 | v1 with ladder × 1.5 (+7.5 / 12.5 / 17.5 / 22.5 %), F by virtual LP value, virtual share 25 % below EMA100 × 0.95, Binance UTC-0 signal |
| v3 | v2 plus divergence rule: all LP to USDC while close >= EMA100 × 1.40, back to normal when close < EMA100 × 1.20 |

Primary mode: **standard** (rewards paid out, not compounded). Compound mode is reported, not judged. Comparisons: v2 vs
v1, v3 vs v2, v3 vs v1, and each vs ETH hold and plain LP 40 % (±20 % uniform, rebuild on exit).

cbBTC/ETH (`gamma_maker_defense_btceth_v1.py`, which runs on WBTC/WETH `0x4585`; cbBTC/ETH only exists on Base
`0x7aea` from 2024-09) is out of scope for this round and gets its own file.

## 2. Tools

- **Daily spec simulator** (new, `experiments/spec_daily_sim.py`): implements spec sheet v2 / v3 sections 2-5 on daily
  closes, with the spec reward model (daily reward = year coefficient × active liquidity at the current price × √price,
  calibrated so that a flat valley 40 % without signal earns $25,898 / 29,796 / 46,687 / 34,867 in 2022 / 23 / 24 / 25,
  other years at the 2022-25 mean) and 0.1 % swap cost. Closes at each of the 24 UTC hours are built from Binance
  ETHUSDT 1 h klines (data.binance.vision, 2017-08..2026-08).
- **Demeter** (`maker-defense` scripts, minute pool data) for the real-pool check T10 only.

## 3. Tests and bars (fixed before running)

"Team bar" = our choice, not from a paper. Every number below is reported whether it passes or not.

| # | test | how | pass bar |
|---|---|---|---|
| T0 | reproduction | simulator vs spec tables: v2 / v3 standard 2021-05-05..2026-08-31 (186.2 / 231.9 $k), v2 2022-25 (185.9), v2 yearly 2018-2025, 24-hour means (142.8 / 193.4) | within 3 % of each spec number; if not, the gap is reported and tests T1-T9 run on the simulator as built (they compare versions inside one model) |
| T1 | decision-hour shift | run each version at all 24 UTC hours | report mean / median / worst. Pass for "vN beats vN-1": mean terminal assets higher **and** higher in >= 18 of 24 hours (team bar) |
| T2 | start-date shift | starts on the 1st of every month 2018-01..2023-08, 3-year horizon, 24-hour mean | vN beats vN-1 in >= 2/3 of starts and median difference > 0 (team bar) |
| T3 | out-of-period | 2018-01-01..2021-05-04 (before v3's window; v3's rule was chosen on 2021-05..2026-08) | vN not worse than vN-1 on terminal assets and max DD (24-hour mean) |
| T4 | parameter plateau | v2 ladder multiplier 1.0..2.2 step 0.1; v3 trigger 0.20..0.60 step 0.05 with release = trigger / 2 and with release fixed at 0.20; 24-hour mean, 2018-01..2026-08 | chosen value's neighbours (±1 step) within 10 % of its terminal assets, and chosen value not the single grid maximum by > 10 % (team bar) |
| T5 | PBO / CSCV | configurations = T4 grids (+ v1), daily log returns 2018-01..2026-08 (UTC 0), S = 16 | PBO <= 0.25 (team bar) |
| T6 | Deflated Sharpe | Sharpe of v3 (and v2) daily returns; N = trials Maker reported (13 ladder values + >= 4 thresholds + signal-source change ≈ 18) and N = full T4 grid | DSR >= 0.95 |
| T7 | paired block bootstrap | daily log-return differential vN − vN-1, stationary bootstrap (mean block 20 d, 10,000 draws), 2018-01..2026-08, every hour | one-sided p <= 0.05 for the mean differential at UTC 0 **and** on the 24-hour average differential |
| T8 | Monte Carlo | (a) random-timing null for v3's rule: 1,000 runs that exit to USDC for the same number of episodes with the same durations at random dates; v3's rank. (b) 1,000 ETH paths by stationary block bootstrap of daily log returns (mean block 90 d), reward coefficient = 2022-25 mean; share of paths where vN beats vN-1 | (a) v3 in the top 5 % of the random-timing runs on terminal assets or max DD. (b) vN beats vN-1 on >= 2/3 of paths (team bar) |
| T9 | cost stress | reward × 0.8 (CTO saw 13-25 % less in Demeter), swap cost × 2 | sign of vN − vN-1 unchanged at the 24-hour mean |
| T10 | real pools (Demeter) | v1 / v2 / v3 continuous on mainnet `0x88e6` 2021-05-06..2026-08-31, and Base `0xd0b5` from 2023-12; UTC 0 only | sign of vN − vN-1 agrees with the simulator |

## 4. Verdict ladder (per version, against its predecessor)

- **fail**: fails T1, T7 or T9.
- **candidate**: passes T1, T7 and T9.
- **validated**: candidate and passes T2, T3, T4, T5, T6 and T8 (one miss allowed if reported, team bar).
- **deployable**: validated and T10 agrees; then the frozen forward test (spec section 9 stages 4-5) with a kill line at the
  5th percentile of same-length bootstrapped backtest windows.

## 5. Known caveats, written before running

- The spec reward model is calibrated on mainnet 0.05 %; CTO's Demeter runs saw 13-25 % less fee in some years (T9).
- v3's rule fired 5 times in 2021-05..2026-08 (spec v3 section 8), two of them adjacent (2025-07 / 2025-08): about four
  independent events. Its evidence is thin by construction; T3, T4 and T8a target that.
- v3's window starts 2021-05-05 while the divergence flag was already ON (fired 2021-04-02), so v3 starts in USDC just
  before the May 2021 crash, whereas v2 starts fully in LP. T2 targets that.
- The 24 decision hours share one price history; they are not independent samples.

## Result

(empty until the tests are run)

## Deviations

(none yet)
