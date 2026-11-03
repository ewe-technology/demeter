# Validation Layers L0-L10 for Two Uniswap v3 LP Strategies: ETH-USDC MGL v3.2 and ETH-cbBTC MGL v2.2

Written 2026-11-03 | Data period: 2021-05-06 to 2026-08-31 (pool minute data; Binance daily closes from 2017-08-17 for
signals and regime labels) | Tracking: Jira QUAN-1209 (stages QUAN-1211..1216)

Paths are relative to the repository root. The detailed record of every layer, with its full method, tables and
reproduction commands, is `samples/strategy-example/experiments/VALIDATION-2026-10-29-v3_2-v2_2.md` (called "the
validation record" below). Which layers can run, and why, is `samples/strategy-example/experiments/VALIDATION-LAYERS-FIT.md`
("the fit note"). This document summarises both; every number in it is copied from them or from the Jira stages
QUAN-1211..1216.

## Scorecard

Reference rules only, written before each layer's numbers; the team decides whether a strategy is good. Pools:
`0x88e6` = mainnet Uniswap v3 USDC/WETH 0.05% (v3.2, judged); `0x4585` = mainnet WBTC/WETH (v2.2, judged); `0x7aea` =
Base WETH/cbBTC 0.05% (v2.2's target pool, reported, not judged after L0). "on / off" = reward reinvest on / off.
Trial count (L4): N >= 29 for v3.2, N >= 8 for v2.2.

| layer | v3.2 `0x88e6` on / off | v2.2 `0x4585` on / off | v2.2 `0x7aea` (reported) |
|---|---|---|---|
| L0 backtest | pass / pass | pass / pass | pass / pass |
| L1 yearly stability | pass / pass | pass / pass | — |
| L2 decision test (circular shift, our substitute for the fit note's method) | pass / pass | pass / pass | p 0.014 / 0.014 |
| L2 decision test (shuffled change dates, the fit note's method) | pass / pass | pass / pass | p 0.012 / 0.016 |
| L3 block bootstrap | fail / fail | fail / fail | 1 − p < 0.95, loss 21-24% |
| L4 multiple testing (DSR at N) | fail / fail | fail / fail | DSR 0.39 / 0.33 |
| L5 pseudo-OOS | pass / pass | fail / fail | — |
| L6a every regime | fail / fail | pass / pass | all regimes > 0 |
| L6b best setting stable | fail / fail | fail / fail | EMA fail, width pass |
| L7 CPCV | not applicable | not applicable | — |
| L8 PSR | pass / pass | pass / pass | PSR 0.88 / 0.84 |
| L9 reality check / SPA | not applicable | not applicable | — |
| L10 paper trading | not done (decision 2026-11-03) | not done | — |

Terms: OOS = out-of-sample; PSR = probabilistic Sharpe ratio; DSR = deflated Sharpe ratio; 1 − p = one-sided bootstrap
confidence that the mean daily return is above 0; CPCV = combinatorial purged cross-validation; SPA = superior
predictive ability test. Sections 2 and 3 define each rule.

## Abstract

Two liquidity-provision (LP) strategies on Uniswap v3 were run through an eleven-layer validation ladder (L0-L10):
ETH-USDC MGL v3.2, valued in USD on the mainnet USDC/WETH 0.05% pool, and ETH-cbBTC MGL v2.2, valued in ETH on the
mainnet WBTC/WETH pool (judged) and on its Base WETH/cbBTC target pool (reported only). MGL is the name of the
strategy family; each version follows a written strategy specification ("the spec"), whose constants were frozen
on 2026-10-27, after all the data used here. Eight layers were run (L0-L6 and L8); L7 (combinatorial purged
cross-validation, CPCV) and L9 (reality check / superior predictive ability test, SPA) do not apply, and L10 (paper
trading) was not done by decision. Each layer had a reference pass rule written down before its numbers were
computed. Against those rules, v3.2 passes L0, L1, L2 (both decision tests), L5 and L8,
and fails L3, L4, L6a and L6b. v2.2 passes L0, L1, L2 (both), L6a and L8, and fails L3, L4, L5 and L6b. Headline
numbers: v3.2 CAGR 23.72% / max drawdown −24.25% (reinvest on, USD); v2.2 CAGR 46.25% / −36.00% (reinvest on, ETH);
whole-run probabilistic Sharpe ratio PSR(0) 0.969 and 0.999; deflated Sharpe ratio at the counted trial number 0.428 (N >= 29) and 0.926
(N >= 8); one-year bootstrap loss probability 16.94% and 10.41%. The reference rules inform; they are not a
conclusion. Whether either strategy is good enough to deploy is the team's decision, and this document does not make
it.

## 1. Introduction

**Context.** The two strategies are concentrated-liquidity LP books whose deployed share F comes from a set of
exponential moving averages (EMA spans 90-120) on Binance daily closes, with staged refills on a virtual price
ladder. v3.2 holds ETH and USDC, places its LP in ±20% ranges, has a +40% divergence exit rule (its daily
"divergence flag"), and is valued in USD. v2.2 holds ETH, cbBTC (or WBTC on mainnet) and USDC, adds a strength switch
on the ETH/BTC ratio, uses ±10% ranges while ETH is strong and ±20% while weak, keeps 25% of F as ETH while ETH is
strong, and is valued in ETH. Neither strategy refits any
parameter per window.

**Problem.** A backtest alone does not tell whether a result survives sampling noise, the number of versions tried,
other market regimes, nearby parameter values, or misaligned timing. An eleven-layer ladder (L0 backtest through L10
paper trading), proposed by a team member, was used to ask these questions one at a time.

**Scope and ruling.** A team ruling (2026-10-30) set the format: every layer reports its method, its theory with
sources, its results and an objective assessment. The pass / fail rules are references written before the results;
the team, not the scorecard, decides whether a strategy is good. This summary keeps that split. Section 2 gives the
setup, Section 3 each layer's result with what it cannot show, Section 4 the known errors and
corrections and the shared limitations.

## 2. Methods

### 2.1 Data and runs

| strategy | pool (Uniswap v3) | role | window | unit, start capital |
|---|---|---|---|---|
| v3.2 | mainnet USDC/WETH 0.05%, `0x88e6` | judged | 2021-05-06..2026-08-31 | USD, $100k |
| v2.2 | mainnet WBTC/WETH, `0x4585` (the pool the spec was calibrated on) | judged | 2021-11-02..2026-08-31 | ETH, 1 ETH |
| v2.2 | Base WETH/cbBTC 0.05%, `0x7aea` (the target pool) | reported, not judged (after L0) | 2024-09-14..2026-08-31 | ETH, 1 ETH |

Each run was done with reinvest on and reinvest off, so there are six L0 runs. Signals use Binance daily closes
(ETHUSDT, BTCUSDT, ETHBTC). The pool data reaches 2026-09-30, but all runs stop at 2026-08-31, the spec's window. The
Base contract's own LP pool (WETH/USDC 0.3%, `0x6c56`) was not run in any layer.

### 2.2 Setup

| setting | v3.2 | v2.2 |
|---|---|---|
| engine | demeter backtester, Rust port; fee share computed on in-range liquidity only (QUAN-1213 fee fix) | same; one LP position, so the fee fix changes nothing |
| swap cost | flat 0.1% | flat 0.1% |
| range break judged on | Binance close | pool price (the spec does not say which price) |
| daily reward claim | > $5 and estimated gas <= $0.2 (spec rule, modelled) | > $5; the gas condition is not modelled |
| gas | not charged (team ruling 2026-10-30) | not charged |
| JIT (just-in-time liquidity) dilution of fees | not modelled (a known optimism) | not modelled |

The gas condition matters for v3.2. A full-ladder claim (all 16 LP bands plus the ETH -> USDC swap, about 1.32M gas)
never costs <= $0.2 on mainnet. So rewards are claimed only at the 164 rebuilds (0 daily claims; 1,172 / 1,149 days
waited, reinvest on / off). Gas samples that were empty, zero or ~1e-7 gwei (38 of 45k) were dropped as data errors.

### 2.3 Procedure

All metrics are computed on the UTC-0 daily net value. CAGR uses calendar days; Calmar = CAGR / |max drawdown|.
Every reference rule below is judged on both reinvest modes of the judged runs; `0x7aea` is reported only in every
layer after L0.

| layer | what was done | reference rule (written before the results) |
|---|---|---|
| L0 backtest | six full-history runs | end value > start value |
| L1 walk-forward | nothing is refitted, so one yearly table with constants fixed | return > 0 in at least 3 of the 4 full years 2022-2025 |
| L5 out-of-sample (OOS) | pseudo-OOS: all data predates the 2026-10-27 freeze | 2024-01-01..end has CAGR > 0 and Calmar >= 0.5 x Calmar of 2022-2023 |
| L6a regime split | bull / bear / range labels from an EMA200 slope (±2% per 30 days) and a 20% drawdown from the 365-day high; v3.2 on ETH/USD, v2.2 on ETH/BTC | annualised return > 0 in every regime with >= 30 days |
| L6b neighbours | 12 extra runs: EMA spans shifted ±10 days, band widths x0.9 / x1.1 | the same setting is best in every regime, for both constants |
| L8 PSR | probabilistic Sharpe ratio on whole-run daily log returns, with autocorrelation checks | PSR(0) >= 0.95 |
| L4 multiple testing | trial ledger from git history and spec notes (lower bound), deflated Sharpe ratio (DSR) | DSR >= 0.95 at the ledger's N |
| L3 block bootstrap | stationary bootstrap of daily log returns (seed 14) | 1 − p >= 0.95 (block 20 days) and one-year loss probability <= 10% (block 90 days, 10,000 paths) |
| L2 decision test, shift | the daily decision series (v3.2 F and divergence flag; v2.2 F and strength switch) rotated by k days on the real price path, 569-658 shifts per run | p(CAGR) <= 0.05 |
| L2 decision test, shuffle | the same columns with their change dates drawn at random, levels kept in order, 500 draws per run | p(CAGR) <= 0.05 |

The fit note's reasons for the layers that were not run:

- **L7 CPCV**: not applicable. CPCV checks a fitting step on held-out folds; nothing is fitted, and 4-5 years of daily
  data give too few independent folds.
- **L9 reality check / SPA**: not applicable. No set of competing daily return series exists for these specs (the
  versions were not run side by side), and 4-5 years give little power.
- **L10 paper trading**: only a live dry run shows fills, slippage and gas, and it needs 6-12 months. It was first
  recorded as pending; on 2026-11-03 it was decided that L10 is not done.

## 3. Results

### 3.1 Scorecard

The scorecard is at the top of this document. Each subsection below gives one layer's result, a one-line theory with
its sources, and what the number cannot show.

### 3.2 L0 backtest

| run | end value | multiple | CAGR | max DD (daily) | Calmar | rebuilds |
|---|---|---|---|---|---|---|
| v3.2 `0x88e6` on | $310,233 | x3.102 | 23.72% | −24.25% | 0.98 | 164 |
| v3.2 `0x88e6` off | $227,343 | x2.273 | 16.69% | −17.03% | 0.98 | 164 |
| v2.2 `0x4585` on | 6.265 ETH | x6.265 | 46.25% | −36.00% | 1.28 | 211 |
| v2.2 `0x4585` off | 5.766 ETH | x5.766 | 43.76% | −44.70% | 0.98 | 211 |
| v2.2 `0x7aea` on | 1.549 ETH | x1.549 | 25.03% | −37.11% | 0.67 | 91 |
| v2.2 `0x7aea` off | 1.474 ETH | x1.474 | 21.88% | −40.49% | 0.54 | 91 |

Theory: method 1 of the team's validation module, terminal value above initial value; no external source.

All six end above the start. In other units, v2.2 `0x4585` (reinvest on) is x2.78 against holding BTC and x3.57 in
USD, with a USD max drawdown of −51.9%; `0x7aea` is x1.21 against BTC and x1.56 in USD (−51.8%).

**What this cannot show.** End value > start beats only the unit held still (USDC, ETH), not holding ETH or BTC.
The validation record attributes most of v2.2's ETH gain to the 2022 ETH/BTC fall that it sat out in BTC. Gas is not charged; v2.2's gas <= $0.2 claim
condition is not modelled (on mainnet its 701 / 611 daily claims would mostly wait); JIT dilution is not modelled.

### 3.3 L1 walk-forward and L5 pseudo-out-of-sample

Theory: L1 applies L0's test per year. Calmar is Young's (1991) ratio; expected maximum drawdown grows with window
length (Magdon-Ismail & Atiya 2004). PSR follows [1]. The Sharpe difference test uses the variance of the Sharpe
estimate under non-normal returns (Mertens 2002; Opdyke 2007). Walk-forward efficiency (WFE) follows Pardo [7].

Calendar-year returns (v3.2 in USD, v2.2 in ETH) were positive in all four full years 2022-2025 for both judged
strategies (4 of 4), so L1 passes for both. For L5:

| run | earlier 2022-23 CAGR / DD / Calmar | later 2024..2026-08-31 | L5 | Sharpe earlier / later | WFE (later CAGR / earlier CAGR) |
|---|---|---|---|---|---|
| v3.2 on | +22.4% / −15.1% / 1.48 | +22.5% / −24.3% / 0.93 | pass | 0.77 / 0.88 | 1.00 |
| v3.2 off | +17.0% / −11.5% / 1.48 | +13.3% / −16.0% / 0.83 | pass | 0.80 / 0.89 | 0.78 |
| v2.2 `0x4585` on | +93.7% / −21.5% / 4.36 | +21.3% / −36.0% / 0.59 | fail | 1.87 / 0.78 | 0.23 |
| v2.2 `0x4585` off | +89.1% / −22.2% / 4.02 | +19.8% / −44.7% / 0.44 | fail | 1.83 / 0.63 | 0.22 |

v2.2's record is dominated by 2022 (+186.4% / +172.8%). Its Sharpe drop between the halves is not significant at 5%
(one-sided p 0.103 / 0.085). `0x7aea` shows the same 2025 picture as mainnet (Sharpe 0.31 / 0.24, drawdown −37% / −40%).
Over 2022..2026-08 both strategies reach PSR 0.95 (v3.2 0.963 / 0.965, v2.2 0.999 / 0.997).

**What this cannot show.** Four years carry little evidence: a coin flip gives 3 or more up years of 4 with
probability 31%. No single v3.2 year reaches PSR 0.95; one year of daily returns cannot separate a Sharpe near 0.8
from 0. The later years are pseudo-OOS only, because the spec was frozen after them; clean OOS (from 2026-11) is not run, by decision. The
L5 threshold (0.5 x Calmar) is the analyst's choice, and a longer window tends to show a deeper drawdown, which biases
Calmar against the 2.7-year later window. WFE here measures decay only, since nothing is refitted.

### 3.4 L6 regime split and neighbouring settings

Theory: rule-based dating of bull and bear markets [8], with 20% moves as thresholds [9]; neighbouring parameter
values should perform similarly [7].

L6a, annualised return per regime (reinvest on / off):

| run (labels) | bull | bear | range | L6a |
|---|---|---|---|---|
| v3.2 `0x88e6` (ETH/USD) | +45.9% / +35.3% | +37.8% / +25.5% | −8.0% / −7.5% | fail |
| v2.2 `0x4585` (ETH/BTC) | +86.8% / +83.0% | +12.6% / +10.5% | +68.4% / +65.9% | pass |

v3.2's range loss comes from 239 days (24 episodes) on which the close is 20% or more below its 365-day high while the
EMA200 still rises; there it lost −41% / −34% a year. On flat-EMA range days it gained +24% / +17%. All five L6b
settings lose on range days (−1% to −12%). v2.2 gains in every ETH/BTC regime; on ETH/USD labels (reported) it loses
in ETH bull markets (−17% to −28% a year in ETH); the record attributes this to holding BTC / USDC through ETH rallies.

L6b: one step on either constant changes full-run CAGR by at most 4 pts (v3.2 22.6% to 27.7%, spec 23.7%; v2.2
`0x4585` 42.4% to 46.3%, spec 46.3%). On v3.2 two neighbours beat the spec on CAGR and Calmar (EMA +10, width x1.1).
On `0x4585` the spec is the best of the five. The best neighbour changes with the regime for both strategies, so
L6b fails for both.

**What this cannot show.** Per-regime Sharpes rest on 9-25 episodes and are not significant (v3.2 range Sharpe −0.31
over 595 days has a standard error near 0.78). The regime labels are this project's own rule, fixed after the fact
and not tradable; the range-part split was added after the main table was seen. L6b is strict: with equal settings
it passes by chance only 1 time in 9 per constant, so a fail says little alone. Three settings per constant test one
step, not a plateau, and the two constants were moved one at a time.

### 3.5 L8 probabilistic Sharpe ratio

Theory: PSR(0) is the probability that the true Sharpe is above 0, given sample length, skewness and kurtosis [1];
autocorrelation is checked with lag-1 autocorrelation rho1 and the Ljung-Box test [6], [5].

| run | days | Sharpe | skew / kurt | PSR(0) | minimum track record (MinTRL) days | rho1 / Ljung-Box p | L8 |
|---|---|---|---|---|---|---|---|
| v3.2 on | 1943 | 0.81 | −0.05 / 9.6 | 0.969 | 1,501 | +0.013 / 0.181 | pass |
| v3.2 off | 1943 | 0.80 | −0.10 / 10.9 | 0.966 | 1,570 | +0.018 / 0.300 | pass |
| v2.2 `0x4585` on | 1763 | 1.28 | 2.51 / 31.2 | 0.999 | 526 | +0.057 / 0.003 | pass |
| v2.2 `0x4585` off | 1763 | 1.16 | 1.62 / 22.4 | 0.996 | 677 | +0.051 / 0.041 | pass |
| v2.2 `0x7aea` on / off | 716 | 0.85 / 0.72 | | 0.882 / 0.841 | 1,378 / 1,942 | | reported |

v3.2 has 1,943 days and needs 1,501 / 1,570 to reach 0.95. An AR(1) correction for autocorrelation moves no
PSR by more than 0.02.

**What this cannot show.** PSR is at N = 1: it ignores how many versions were tried (that is L4). v2.2's PSR is
raised by fat right tails (a few large up days). On its target pool `0x7aea` v2.2 does not reach 0.95.

### 3.6 L4 multiple testing

Theory: the deflated Sharpe ratio is PSR measured against SR0, the expected maximum Sharpe of N trials whose true
Sharpe is 0 [2]; multiple-testing view [3]. Break-even N is the largest N at which DSR >= 0.95.

| run | N | SR0 at N (annualised) | DSR at N | break-even N | L4 |
|---|---|---|---|---|---|
| v3.2 on | 29 | 0.89 | 0.428 | 1 | fail |
| v3.2 off | 29 | 0.89 | 0.413 | 1 | fail |
| v2.2 `0x4585` on | 8 | 0.66 | 0.926 | 5 | fail |
| v2.2 `0x4585` off | 8 | 0.66 | 0.872 | 3 | fail |

With 29 trials, the best of 29 worthless strategies would show an annual Sharpe of about 0.89 by luck; v3.2 shows
0.81. v3.2 already fails at N = 2. v2.2 survives up to 5 / 3 trials.

**What this cannot show.** The true trial count. N is a lower bound counted from the repository: the spec PDFs, the
spec author's own iterations, uncommitted local sweeps and other teams' runs are not counted. The trials are variants
of one family and therefore correlated, so the effective N is smaller than the count. The variance of the trials'
Sharpes is taken under the null, because no daily return series exists for the other trials.

### 3.7 L3 block bootstrap

Theory: stationary bootstrap [4], which keeps short-run dependence within random-length blocks.

| run | 1 − p (block 20 / 5 / 60) | one-year loss probability | one-year return median / P5 | real worst 365-day return | L3 |
|---|---|---|---|---|---|
| v3.2 on | 0.967 / 0.967 / 0.983 | 16.94% | +22.9% / −12.9% | −12.5% | fail |
| v3.2 off | 0.961 / 0.963 / 0.977 | 17.65% | +15.9% / −9.9% | −8.2% | fail |
| v2.2 `0x4585` on | 0.987 / 0.992 / 0.991 | 10.41% | +41.0% / −10.3% | −10.5% | fail |
| v2.2 `0x4585` off | 0.982 / 0.987 / 0.986 | 13.00% | +40.1% / −17.2% | −23.3% | fail |

The mean return is positive at 95% for both judged strategies at every block length. Both fail on the 10% loss bar.
v2.2 reinvest on misses it by 0.4 pt, within simulation noise (standard error about 0.3 pt).

**What this cannot show.** The bootstrap resamples the strategy's own returns on one price path; it cannot test the
path-dependent LP rule on new price paths. It is more pessimistic than the real run (v3.2's real worst year −12.5%,
yet 17% of resampled years lose), because 90-day blocks break the ordering that the F engine creates. The 10% loss
bar is the analyst's choice.

### 3.8 L2 decision tests (circular shift and shuffle)

Theory: Monte Carlo permutation of a rule's outputs against the market [10]; exact p = (1 + b) / (1 + m) for m
random draws [11]; permutation tests lose exactness on dependent data [13], and circular shifts have known defects
(the wrap and the start state) [12]. A shift keeps the F values and their spacing; the shuffle keeps the levels in
order but draws their dates at random.

| run | mode | CAGR | shift: median / p(CAGR) | shuffle: median / p(CAGR) | L2 |
|---|---|---|---|---|---|
| v3.2 `0x88e6` | on | +23.7% | −2.8% / 0.013 | +2.6% / 0.002 | pass / pass |
| v3.2 `0x88e6` | off | +16.7% | −3.3% / 0.011 | +0.3% / 0.002 | pass / pass |
| v2.2 `0x4585` | on | +46.3% | +7.1% / 0.002 | +22.0% / 0.002 | pass / pass |
| v2.2 `0x4585` | off | +43.8% | +10.0% / 0.002 | +23.8% / 0.002 | pass / pass |
| v2.2 `0x7aea` | on / off | +25.0% / +21.9% | +5.0% / +5.1%, p 0.014 / 0.014 | +10.7% / +9.9%, p 0.012 / 0.016 | reported |

Both methods give the same reference result on the judged runs. No shift and no draw reaches the real v2.2 `0x4585`
run. On v3.2, 7 of 629 shifts (two groups of neighbouring shifts) reach the real run in reinvest-on mode; no shuffle
draw does. On v2.2 every shuffle draw is positive, and the best comes within 5 pts (on) and 2 pts (off) of the real
run.

**What this cannot show.** Both tests use one price path that the rules were developed on, and the p values are not
adjusted for the trials in L4. They do not test the LP rule itself, since every rerun keeps the same LP. Range-break
exits stay on their real dates, so a low p can also reward the agreement between F and the real exits, not timing
alone. v2.2's F and strength switch move together, so the test does not separate them. The two nulls differ: the
shift keeps the decision rhythm and the F values (not proven to keep the realised exposure), while the shuffle breaks the rhythm (median longest hold 16-22 days vs
94-120 real) and, on v2.2, lowers mean F (about 0.57 vs 0.724 real). Their agreement is not independent evidence.
The 500+ shifts are only about 31-97 independent alignments by a rough count.

## 4. Discussion

### 4.1 Known errors and corrections during the validation

Every error found during the work is listed, with its correction and whether it changed a number. The first group
was found in the stage 2 preconditions, before any scorecard; the second during the scorecards.

**Preconditions (QUAN-1212..1215)**

| # | error | found in | correction | effect on numbers |
|---|---|---|---|---|
| 1 | The engine's fee share counted the strategy's own out-of-range liquidity, so v3.2 fees were about 2.5% low | QUAN-1213 | flag that computes the fee share on in-range liquidity only (Python and Rust engines), on for every validation run | reinvest on: fees +6.34%, end value $297,167 -> $307,582, daily max DD −24.27% -> −24.21%; reinvest off: fees +2.51%, $222,744 -> $225,176, −17.22% -> −16.97% (flat 0.1% swap, before the gas claim condition) |
| 2 | The depth-based slippage model read the same pool liquidity, which includes the strategy's own bands, so the fee fix raised v3.2's swap cost ($3,189 -> $5,179, reinvest off) | QUAN-1213 | validation swap cost set to a flat 0.1%, as the spec says (decided with Steven, a team member) | all layers use flat 0.1% |
| 3 | v3.2 judged a range break on the pool tick; the spec says the Binance close | QUAN-1215 | break judged on the Binance close; the old pool-tick test kept behind a switch (`BREAK_ON_POOL_TICK=1`) | 1 of 16 breaks moves (2023-02-05 -> 02-08); daily max DD unchanged |
| 4 | v3.2's spec claim condition (estimated gas <= $0.2) was not modelled. The tickets expected live rewards and reinvests to be smaller than the backtest's | QUAN-1214, QUAN-1209, QUAN-1215 | modelled in L0 (`CLAIM_GAS_CAP=1`) | 0 daily claims on mainnet; rebuilds and swap cost unchanged; end value rose +0.86% / +0.96% (on / off): the same ETH fees are sold at the rebuild-day price instead of each day's price. The spec's own numbers assume daily claims, which cannot happen on mainnet |
| 5 | The fit note named `0xd0b5` as the Base contract's LP pool; it is the contract's 0.05% swap pool. The LP pool is `0x6c56` | QUAN-1209 comment 2026-10-30 | fit note corrected (taken from the script's docstring; the contract itself was not checked) | none; `0x6c56` was not run |
| 6 | The v2.2 code rests on two assumptions the spec does not state: with no LP position, the LP part goes to the asset the book retreats to (the v3.2 rule); the reinvested LP part is added to the existing range without recentring | QUAN-1212 | flagged in the code; both assumptions confirmed correct by Dino on 2026-11-03 | none: the code already follows them |

Also from QUAN-1215: v3.2 has 54 spec rules (44 same, 6 differ, 4 not modelled); v2.2 has 56, with no logic bug. Two
items were left for the spec owner: which price v2.2 uses for "out of range" (1 rebuild in 4 years differs on mainnet,
none on Base) and v3.2's LP-share valuation price (no effect). Dino settled both on 2026-11-03: the pool price, as the
code does, so no number changes. The look-ahead audit (QUAN-1214) passed 10 of 10
truncation tests and its positive control failed 10 of 10; it did not cover the reinvest-off modes.

**Scorecards (QUAN-1216)**

| # | error | layer | correction | effect on numbers or reference results |
|---|---|---|---|---|
| 7 | The circular shift was chosen over the fit note's shuffle because "F changes on most days". This was assumed, not measured, and is false: F changes on 28.2% (v3.2), 21.9% (`0x4585`) and 26.5% (`0x7aea`) of days | L2 | corrected in the record (pre-registered text kept, marked false); the shuffle was then run as a second test, by a decision of 2026-11-02, pre-registered before any draw | the shift's numbers stand; the shuffle gives the same reference results |
| 8 | The shift's theory said the median shifted run is "the same exposure with no timing". Holding the same F values does not prove the same realised exposure, because range breaks and v3.2's EMA share stay real | L2 | the assessment states that the claim is too strong; the theory text is kept as pre-registered | no number changed |
| 9 | The first assessment of the shuffle credited v2.2's result to "its levels (F mean 0.72)". The draws hold a mean F of about 0.57 | L2 shuffle | mean-F table added; claim corrected | no number changed |
| 10 | The L3 code drew the 90-day kill line before the one-year paths, against the pre-registered order | L3 | rerun in the pre-registered order | v2.2 `0x4585` reinvest on: one-year loss probability 9.98% (pass) -> 10.41% (fail). The pre-registered order decides; both numbers are near the 10% bar |
| 11 | In the first L8 / L4 / L3 tables, the `0x7aea` "reported" labels and the two-decimal loss probabilities were edited by hand | L8, L4, L3 | the code now prints both, and N, so the tables match its output | no number changed |
| 12 | Two L2 runs with the same label overwrote each other, so the first report printed only the reinvest-off rows | L2 | labels made unique; the command refuses duplicates | no number changed |
| 13 | The L2 grid formula could give one step too few | L2 | exact widest step | same grid on all three windows |
| 16 | Review fixes in the L2 code, after the runs: an unfinished batch was not marked; the runner accepted L6 switches and a pre-set `L2_SHIFT` / `L2_SHUFFLE`; the shuffle accepted a missing decision value (NaN would count a change every day) | L2, L2 shuffle | report marks a partial batch; runner refuses those switches; shuffle refuses NaN; a self-check with repeating levels (A-B-A-B) added | no number changed |
| 17 | The first L6 launch failed before any result was written: the runner had no `__main__` guard for the scripts' worker processes | L6 | fixed and rerun; the failed partial folders deleted | none |
| 18 | The first v3.2 L8 / L4 / L3 launch failed before any number was printed: a zsh path modifier cut `:reinvest` off an argument | L8, L4, L3 | rerun with the same code | none |
| 14 | An earlier L5 window with no drawdown has infinite Calmar, which the rule did not cover | L5 | returns "not judged" | applies to none of the six runs |
| 15 | v2.2's script did not skip its self-check under an L6 switch; L6b's "both constants" verdict was written by hand; a constant with no judged regime would have read "fail" | L6 | fixed in code; the L6 runner was committed | no reference result changed |

Departures from the pre-registration that are not errors, listed so a reader can weigh them:

- L4 counts N = 8 for v2.2, leaving out two cost stresses that would give N = 10 (DSR at N = 10: 0.907 / 0.845).
- Added after the results were seen and carrying no reference result: the L1 + L5 statistics table (PSR, Sharpe
  difference, WFE) and its theory table, the L6 range-part split, and the L2 descriptive and mean-F tables.
- Windows: the fit note plans 2026-01..09 for the yearly table, but the runs stop at 2026-08-31 (the spec window).
  The 2021 partial years are printed although the plan starts at 2022; they are marked partial and not judged.
- `0x7aea`: QUAN-1216 asks for its scorecard ("pass or fail both count"), but every pre-registration after L0 reports
  it without judging it. Its numbers are all in the record.
- L0: the gas ruling replaces the L0 cost list's "gas charged at the target chain's price". v2.2's daily file ends at
  the 2026-08-31 00:00 execution, one day short of its summary file (6.255 / 5.738 ETH at 23:59, on / off).
- L2 (shift and shuffle): range-break exits stay on their real dates, though the fit note names exits.
- L2: the decision memory is computed from the run's first to last day, not from start − 1 to end − 1 as for the
  rotation (one day in about 2,000 or 700).
- L2: the code's test seams were not confirmed with the user before the work, as the team's test-driven-development
  procedure asks; the work ran as a background job.
- L6: v3.2's daily signal file now carries the L6 tag, so variants do not overwrite each other; with the switches off
  its name is unchanged.
- L2 shuffle was run after the shift's results were known, on a decision made then; it was pre-registered before
  any draw. L2 interim tables for v3.2 and `0x7aea` were reported before `0x4585` finished; no rule or run code
  changed in between.
- The L2 batch stopped once mid-run; three unfinished run folders were deleted and the batch resumed with the same
  commit; no finished shift was rerun.
- The L2 shuffle draws depend on NumPy 1.26.4's random generator, which does not promise the same stream across
  versions.

### 4.2 Limitations shared by every layer

- **No clean out-of-sample data.** Every year of pool data predates the 2026-10-27 spec freeze. Clean OOS would start
  with 2026-11; on 2026-11-03 it was decided not to run it (Dino).
- **One price path per pool.** No layer tested the strategies on resampled or synthetic prices (the original L2
  design, permuted prices, needs a synthetic swap generator).
- **Costs.** Gas is not charged (team ruling); JIT dilution of fees is not modelled; v2.2's gas claim condition is not
  modelled on mainnet.
- **Pools not run.** v3.2 on Base `0x6c56`, the contract's own LP pool, was not run in any layer.
- **No benchmark per layer.** Return > 0 beats only the unit held still, not holding ETH (v3.2) or BTC (v2.2).
- **Many thresholds are the analyst's choice.** The L1 3-of-4, L5 0.5 x Calmar, L6 ±2% slope, L6b rule and L3 10% loss
  bar have no source fixing them; 0.95 for PSR, DSR and the bootstrap is the usual one-sided 5% level.

### 4.3 Conclusion

The ladder produced a full set of numbers for eight layers on both strategies and recorded why the other three
layers were not run. Against the reference rules, both strategies pass the decision tests (L2), yearly stability
(L1) and whole-run PSR (L8), and both fail multiple testing (L4), the bootstrap (L3) and neighbour stability (L6b).
L5 passes for v3.2 and fails for v2.2; L6a fails for v3.2 and passes for v2.2. These are references written before the results. The decision on whether either
strategy is good enough belongs to the team; clean out-of-sample months will not be added (decision 2026-11-03).

## References

1. Bailey, D. H., & López de Prado, M. (2012). The Sharpe ratio efficient frontier. *Journal of Risk*, 15(2).
2. Bailey, D. H., & López de Prado, M. (2014). The deflated Sharpe ratio. *Journal of Portfolio Management*, 40(5).
3. Harvey, C. R., & Liu, Y. (2015). Backtesting. *Journal of Portfolio Management*, 42(1).
4. Politis, D. N., & Romano, J. P. (1994). The stationary bootstrap. *JASA*, 89(428).
5. Lo, A. W. (2002). The statistics of Sharpe ratios. *Financial Analysts Journal*, 58(4).
6. Ljung, G. M., & Box, G. E. P. (1978). *Biometrika*, 65(2).
7. Pardo, R. (2008). *The Evaluation and Optimization of Trading Strategies*. Wiley.
8. Pagan, A. R., & Sossounov, K. A. (2003). *Journal of Applied Econometrics*, 18(1).
9. Lunde, A., & Timmermann, A. (2004). *Journal of Business & Economic Statistics*, 22(3).
10. Aronson, D. (2006). *Evidence-Based Technical Analysis*. Wiley.
11. Phipson, B., & Smyth, G. K. (2010). *Statistical Applications in Genetics and Molecular Biology*, 9(1), article 39.
    https://doi.org/10.2202/1544-6115.1585
12. Kalyuzhny, M. (2020). *Global Ecology and Biogeography*, 29(6), 1085-1093. https://doi.org/10.1111/geb.13083
13. Romano, J. P., & Tirlea, M. A. (2020). arXiv:2009.03170. https://arxiv.org/abs/2009.03170

Further sources cited by the validation record for single theory rows (Young 1991; Magdon-Ismail & Atiya 2004; Mertens
2002; Opdyke 2007; Ledoit & Wolf 2008; Hamilton 1989; Bailey, Borwein, López de Prado & Zhu 2014; Masters 2018; Wilks)
are listed there with what each supports. Page numbers were not checked for Pardo, Aronson, Masters and Wilks.

## Appendix

### A.1 Sources

| source | content |
|---|---|
| `samples/strategy-example/experiments/VALIDATION-2026-10-29-v3_2-v2_2.md` | method, theory, results, assessment, deviations and reproduction commands for every layer |
| `samples/strategy-example/experiments/VALIDATION-LAYERS-FIT.md` | which layers can run, why, and the stage 3 plan |
| Jira QUAN-1209 and its stages QUAN-1211..1216 | scope, stage 2 preconditions, rulings |
| `samples/strategy-example/strategy_layers.py`, `l2_runs.py`, `l6_runs.py` | code that computes the layers |
