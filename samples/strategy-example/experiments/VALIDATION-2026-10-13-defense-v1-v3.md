# Validation: is Maker's defense v1 / v2 / v3 (ETH/USDC) an edge or an overfit? (pre-registered 2026-10-13)

Jira QUAN-1129 (research: strategy validation methods). Methods and their sources:
`RESEARCH-2026-10-13-strategy-validation.md`. This is a validation of existing strategies, not a new v6.x version, so it
has no EXP number, Jira subtask or dashboard row.

Status: **done 2026-10-13** (pre-registered in f84083c before any test ran; results below). Slides:
https://claude.ai/artifact/1rmNEUAYUosctoz7sLVBwh

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

## Result (run 2026-10-13, `experiments/validate_v123.py`, tables in the main checkout's `result/validate_v123/`)

**Verdict: no version reaches "candidate".** Every pair fails T7: the gains are not larger than their own noise at
p <= 0.05. v3 is the best of the three on every test where they differ and is never worse, and its drawdown advantage
is consistent; its return advantage is not established. v2's ladder change has no edge outside this one history.

| test | v2 vs v1 | v3 vs v2 | v3 vs v1 |
|---|---|---|---|
| T1 decision hour (full / spec window) | pass / pass (22 / 18 of 24 hours) | pass / pass (23 / 24) | pass / pass (24 / 24) |
| T2 start date (68 starts, 3 y) | pass (94 % of starts) | **fail** (66.2 % < 66.7 %; max DD better in 100 %) | pass (82 %) |
| T3 2018-01..2021-05-04 | pass | pass | pass |
| T4 plateau | ladder × 1.5: pass (neighbours within 1.5 %) | trigger 0.40: pass on spec window (−9 / +6 %), **fail** on full window (−20 / +22 %) | — |
| T5 PBO (32 configs, S = 16) | 0.18, pass | (same batch) | |
| T6 DSR (N = 18 / 32) | v2 0.46 / 0.42 **fail** | v3 0.72 / 0.69 **fail** | v1 0.44 / 0.39 **fail** |
| T7 paired bootstrap, p (UTC 0 / 24-h mean) | 0.44 / 0.015 **fail** | 0.23 / 0.17 **fail** | 0.23 / 0.053 **fail** |
| T8a random timing (v3 rule rank) | — | pass: 99.1 % terminal, 100 % DD (spec window); 88 % / 97 % (full) | |
| T8b 1,000 bootstrap paths | **fail** (55.6 % of paths) | **fail** (65.4 %; DD better 76 %) | pass (67.6 %) |
| T9 cost stress | pass | pass | pass |
| T10 Demeter mainnet `0x88e6` (sign agrees) | pass (−15.7 vs sim −15.3) | pass (+43.8 vs +45.2) | pass (+28.1 vs +29.9) |

### T0 reproduction

v2 / v3 standard 2021-05-05..2026-08-31: 186.0 / 231.2 vs spec 186.2 / 231.9 (−0.1 / −0.3 %); compound 261.1 / 321.1
vs 262.5 / 323.7; 24-hour means 144.3 / 193.2 vs 142.8 / 193.4. v2 2022-25: 181.5 vs 185.9 (−2.4 %), compound −4.0 %.
Yearly v2 2019-2025 within −2.3 .. +5.5 %. **2018: 58.2 vs 78.9 (−26 %)**, so the full-window (2018-) numbers below
carry a 2018 the spec does not show; the spec window numbers do not.

### Decision hour (T1): the spec's UTC-0 figures are near the best of 24

| 2021-05-05..2026-08-31, $k | v1 | v2 | v3 |
|---|---|---|---|
| UTC 0 | 201.3 | 186.0 | 231.2 |
| 24-hour mean | 131.4 | 144.3 | 193.2 |
| worst hour | 100.2 | 101.7 | 137.5 |
| UTC 0's rank of 24 | 1 | 1 | 2 |
| max DD, 24-hour mean | −38.5 % | −36.5 % | −22.0 % |

Full window 2018-01..2026-08 (24-hour mean): v1 113.7, v2 153.7, v3 224.7; max DD −70 / −63 / −50 %.

### Significance (T6, T7)

Annual Sharpe at UTC 0, 2018-01..2026-08: v1 0.23, v2 0.25, v3 0.49. The expected best Sharpe of 18 tries with no
skill is 0.28, so v1 and v2 are below it and v3 only 0.2 above (DSR 0.72). Mean daily-return gain, annualised, with
its 90 % bootstrap interval (24-hour mean): v2 − v1 +3.8 pts [+1.0, +6.7]; v3 − v2 +4.6 pts [−3.3, +13.2]; v3 − v1
+8.3 pts [+0.2, +16.8]. At UTC 0 alone every interval includes 0.

### Parameter plateau (T4, 24-hour mean, $k)

- Ladder multiplier, full window: ×1.0 113.7, ×1.3 149.8, ×1.4 153.9, **×1.5 153.7**, ×1.6 152.4, ×1.8 162.3 (max),
  ×2.2 141.4. A plateau from ×1.3 to ×1.9, as the spec says.
- Divergence trigger (release 0.20), full window: 0.30 169.4, 0.35 193.7, **0.40 224.7**, 0.45 251.6, 0.55 283.6 (max).
  Spec window: 0.35 186.2, **0.40 193.2**, 0.45 196.3. On the spec's own window it is a plateau; with 2018-2021 added
  the result climbs steeply with the trigger, so the rule's value depends on which bubbles are in the sample.

### Monte Carlo (T8)

- (a) v3's divergence exits against 1,000 runs that leave for the same number and lengths of episodes at random dates:
  v3 beats 99.1 % on terminal assets and 100 % on max DD in the spec window (88.3 % / 96.6 % on the full window). The
  timing is not luck: exits at stretched prices beat random exits.
- (b) On 1,000 stationary-bootstrap ETH paths (mean block 90 days, 8 years each), median terminal v1 148.0, v2 152.8,
  v3 174.9; median max DD −40 / −40 / −34 %. v3 beats v2 on 65.4 % of paths (DD better on 76 %), v2 beats v1 on 55.6 %.

### T10 real pool (Demeter, mainnet `0x88e6`, 2021-05-06..2026-08-31, UTC 0, standard mode)

Maker's scripts (`maker-defense` 5cec767, window changed only; v2 with `_compound = False`), run with this branch's
`demeter` (the `maker-defense` copy lacks the `core.py:167` int cast and crashes on this window). v1 flat 0.1 % swap
cost; v2 / v3 pool fee + depth slippage, as on the branch. Max DD is per minute.

| $k | Demeter | simulator (UTC 0) | spec |
|---|---|---|---|
| v1 | 196.8 (max DD −22.7 %, 179 rebuilds) | 201.3 (−28.8 %) | — |
| v2 | 181.1 (−24.7 %, 162) | 186.0 (−27.6 %) | 186.2 (−28 %) |
| v3 | 224.9 (−17.7 %, 164) | 231.2 (−18.2 %) | 231.9 (−19 %) |
| v2 − v1 | −15.7 | −15.3 | |
| v3 − v2 | +43.8 | +45.2 | |
| v3 − v1 | +28.1 | +29.9 | |

**Pass for all three pairs**: every sign agrees and every difference is within $2k of the simulator. The simulator
runs about 3 % above Demeter on this pool. On the real pool at UTC 0, v1 ends $15.7k above v2 with a shallower max DD.

## Reading

1. **Report 24-hour means, not UTC 0.** UTC 0 ranks first or second of 24 for all three versions; the spec's headline
   figures are 20-53 % above what a randomly chosen hour gives (v1 −35 %, v2 −22 %, v3 −16 %).
2. **v2 over v1 is not an edge.** Its ladder plateau is real, but on new price paths it wins 56 % of the time and its
   gain is significant only on the 24-hour mean (p 0.015), not at UTC 0 (p 0.44). On the real pool at UTC 0 over
   2021-05..2026-08, v1 ends above v2 (196.8 vs 181.1, T10).
3. **v3's rule does real work on risk, not proven on return.** It cuts max DD in every start date, 24 of 24 hours and
   76 % of synthetic paths, and its exits beat random timing. Its return gain rests on about 4 independent bubble
   events (2021-04, 2021-09, 2024-03, 2025-07/08) and is not significant (p 0.17-0.23); its size swings ±20 % with the
   trigger once 2018-2021 is included.
4. **Deploy decision.** None is "validated". If one is deployed, v3 is the least bad choice, sized small, with the
   forward kill line of section 4, and with the spec's return figures replaced by the 24-hour means (v3 standard
   ~$193k on 2021-05..2026-08, max DD ~−22 %).

## Deviations

- T1 named no window in the pre-registration; both windows were run and both are reported (the verdict holds on
  both).
- The simulator's 2018 is 26 % below the spec's (T0); full-window figures include it. The spec-window figures do not.
- T10 runs Maker's scripts from copies in the job scratch folder with only the window changed (2021-05-06..2026-08-31)
  and v2 set to standard mode; Base `0xd0b5` was not run (the scripts hard-code `0x88e6`). They import this branch's
  `demeter` (one-line `int` cast difference from `maker-defense`). Raw results: job scratch folder, copied to the main
  checkout's `result/validate_v123/t10/`.
