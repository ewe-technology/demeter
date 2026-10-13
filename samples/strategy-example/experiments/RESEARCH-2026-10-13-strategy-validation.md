# Research: how to tell a real edge from backtest luck (2026-10-13)

Jira QUAN-1129 ("[Uniswap] Research: strategy validation methods"). The strategy research has run 175 trials
(EXP-000..175, `registry.csv`) on the same few price histories. This note studies validation methods from their primary
sources, says which of them can run on the data the team already has, and ends with a recommended pipeline.

No backtest was run. A few indicative statistics were computed from the daily equity CSVs that already exist in the
main checkout (`result/v6_validate/`, spec v1 full-history runs of EXP-156..175); they show what the methods would say
and are not verdicts (section 2).

Evidence grades: **P** primary source opened this session (paper PDF, journal or author page, official library docs or
source code), **R** this repo's files or saved runs, **U** not verified from a primary source (citation found, text not
read, or only a search snippet). Formulas are quoted from the PDFs named in the references.

## 1. Summary and recommended validation approach

### 1.1 Short answer

- **The current rule cannot tell edge from luck, for three reasons.**
  1. **It counts pools that are the same test.** On the spec v1 full-history runs, the baseline's daily returns
     correlate 0.99–1.00 across the five ETH pools and 0.99 across the two BTC pools. The v6.75 gain (`GA_nolow` minus
     baseline) correlates 0.78–1.00 across the ETH pools (one short-overlap pair at 0.39) and 0.98 across the BTC
     pools (**R**, section 2). "Wins on 4 of
     7 pools" is about two independent observations, ETH and BTC, not seven.
  2. **It ignores the number of trials.** Bailey & López de Prado show that the expected best Sharpe ratio grows with
     the number of independent trials even when no strategy has skill (DSR paper, Eq. 1, **P**). The holdout method
     "assesses the generality of a model as if a single trial had taken place". If it is applied about 20 times at 95%
     confidence, false positives are "expected" (DSR paper, section "Backtest overfitting and the holdout method",
     **P**). Rounds 2–4 reused the H4 / H5 windows across about 70 trials (EXP-082..152) (`CLAUDE.md`, **R**), which is exactly this
     case. The registry records 44 passes out of 174 trials (38 `holdout-pass`, 6 `pass`; **R**).
  3. **It judges single-path point estimates.** CAGR, Calmar and max DD each come from one price path. A 1–3 pt CAGR
     gap has no standard error attached.
- **The tools exist and fit the data we have.** Each run already writes a daily net-value series per variant, with the
  baseline in the same invocation. That is exactly the input of Hansen's SPA test, Romano-Wolf StepM and the Model
  Confidence Set, all implemented in `arch.bootstrap` (**P**, source code). The same series feed PBO/CSCV (Bailey et al.
  2017, already used once in `V6_VALIDATION.md`), the Deflated Sharpe Ratio and the minimum track record length. All of
  them run in seconds on saved CSVs. They need no new backtests.
- **What they say today (indicative, section 2).** Take the latest batch on ETH mainnet 0.05% (20 variants against spec
  v1, 1,960 days). A Reality Check on the best variant's mean daily log-return gain gives p ≈ 0.62. On WBTC 0.3% it is
  p ≈ 0.50 and on Base ETH 0.05% p ≈ 0.38. None of the latest variants beats spec v1 once the search is accounted for.
  The best single information ratio vs baseline is 0.73 a year (ETH, the macro-restore family). Its minimum track
  record length at 95% is about 4.4 years of daily data, so **a forward window of a few months cannot confirm an edge
  of this size**. It can only catch a broken one.

### 1.2 Recommended pipeline (ranked; adopt for every experiment from the next one)

The bars below are proposals for Dino to confirm. Where a bar is the team's choice and not taken from a paper, it says
"team bar".

| # | gate | what it answers | inputs | pass bar | cost here |
|---|---|---|---|---|---|
| G0 | **Trial ledger and pre-registration** (keep the current practice; add a family tag and a trial counter) | how many tries stand behind a pass | `registry.csv` | prerequisite. Every run is logged, including crashed, abandoned and "quick look" runs. For a guided search, each search's final outcome counts as one trial (Bailey et al. 2017 §5.2, **P**) | trivial |
| G1 | **Cost and fill stress** (LP-specific) | is the gain an artefact of the simulator | `result_*.csv` (fees, gas, swap notional), `fees_*.csv` | the full-history gain keeps its sign after fee income × 0.8, swap cost × 2 and gas charged at the target chain's price (team bar; reasons in §8) | post-hoc on saved CSVs, ~½ day to script |
| G2 | **Paired differential test per asset** | is the gain larger than its own noise | daily log-return differential (variant − baseline, same invocation), averaged over the ETH pools and, separately, over the BTC pools | one-sided studentized stationary-bootstrap p ≤ 0.05 on the asset it targets. On the other asset, no significant loss (p ≥ 0.10 for "worse") (team bar) | `arch` + ~100 lines |
| G3 | **Data-snooping correction** | does the best of everything we tried still beat the baseline | the same differentials for **every** variant run in the current baseline epoch (EXP-156 onward) | Hansen SPA consistent p ≤ 0.10 for the family, the variant itself kept by Romano-Wolf StepM at 10% FWER, **and** Deflated Sharpe Ratio of the differential ≥ 0.95, with N̂ from the trial correlation (DSR App. A.3, Eq. 9). Report DSR also with M = 175 | `arch.bootstrap.SPA` / `StepM`, DSR ~40 lines |
| G4 | **PBO / CSCV on the batch** | does picking the in-sample best carry to the unseen half | T × N matrix of daily returns for the batch the variant was picked from (per asset composite) | PBO ≤ 0.25 (team bar; the paper sets none), S = 16 (paper's recommended value) | `pypbo` or ~60 lines |
| G5 | **Model Confidence Set (report, not a gate)** | which variants are statistically tied with the best | losses = −daily log return of baseline + all variants | if the baseline is inside the 90% MCS, the verdict says "tied with baseline" even after G2–G4 | `arch.bootstrap.MCS` |
| G6 | **Frozen forward incubation** | does the live or replayed forward path stay inside the backtest's range | forward minute data after 2026-09-17, same code hash | kill if the forward differential falls below the 5th percentile of same-length block-bootstrapped backtest windows. "Deployable" needs G3 + G4 + no kill for ≥ 3 months (team bar). It is not a proof of edge: MinTRL ≈ 4+ years at the observed IR | data refresh + one run per month |
| G7 | **Synthetic-path stress (optional, last)** | does the rule depend on one historical sequence | stitched real-data segments or simulated pool paths | gain keeps its sign on ≥ 2/3 of resampled paths (team bar) | high: demeter replays real swap events, so new paths need a fee/volume model (§6) |

Verdict ladder that replaces "pass / fail" for improvement claims:

- **fail**: fails G1 or G2.
- **candidate**: passes G1 and G2 only. This is what most current "passes" would be at best.
- **validated improvement**: passes G1–G4, and the baseline is outside the MCS or the verdict is labelled "tied".
- **deployable**: validated, then survives G6.

Two rules change in how verdicts are counted:

1. **Judge per asset composite, not per pool.** The 4/7-pool count should become "ETH composite and BTC composite".
   Per-pool tables stay as descriptive evidence (chain, fee tier), and the MCS/SPA run can use pools as extra columns
   if wanted.
2. **Max DD and Calmar stay as risk constraints, not evidence.** Max DD is the extreme of one path. Keep the "≤ 3 pts
   deeper" bar as a guardrail, and put the statistical weight on the mean differential (G2–G4).

## 2. What the methods say on data we already have (indicative)

Computed this session from the spec v1 full-history equity CSVs in the main checkout
(`result/v6_validate/<pool>-opt-*-specv1-<full-history start>-*/equity_*.csv`, **R**). The steps:

- daily log returns;
- differential = variant − `A_v6` (spec v1) from the same invocation;
- annualised over 365 days;
- PSR(0) and MinTRL at 95% per Bailey & López de Prado (2012) Eq. 13;
- White's Reality Check (non-studentized max of √T × mean differential), stationary bootstrap, mean block 20 days,
  500 resamples.

The script was a scratch file and is not in the repo. Duplicate variants (e.g. `EB` = `GG` = `GC` on 0x88e6) are
included as they were run, so they slightly overstate M. Treat every number as a rough indication only.

| pool | days | variants vs spec v1 | avg corr of daily returns (N̂ of M, Eq. 9) | avg corr of differentials (N̂) | best IR / yr | its PSR(0) | its MinTRL (yrs) | Reality Check p |
|---|---|---|---|---|---|---|---|---|
| 0x88e6 ETH mainnet 0.05% | 1,960 | 20 | 0.956 (1.9 of 21) | 0.319 (13.9 of 20) | 0.73 (`GC`/`EB`/`GG`, +3.1 pt/yr) | 0.965 | 4.4 | 0.62 |
| 0x99ac WBTC mainnet 0.3% | 1,780 | 13 | 0.969 (1.4 of 14) | 0.173 (10.9 of 13) | 0.72 (`GE` intraday stop, +2.3 pt/yr) | 0.997 | 1.8 | 0.50 |
| 0xd0b5 ETH Base 0.05% | 1,021 | 13 | 0.980 (1.3 of 14) | 0.329 (9.0 of 13) | 0.55 (`GH` wide top, +3.8 pt/yr) | 0.826 | 8.6 | 0.38 |

Readings:

- **Single-test significance shows up and then vanishes.** On WBTC the intraday stop (`GE`, EXP-161) has PSR(0) 0.997 on
  its own. It is the one rule the batch already rejected because it loses ETH (IR −0.23 on 0x88e6, −1.21 on Base).
  After picking the best of 13 the Reality Check p is 0.50. That is the winner's curse.
- **The variants are nearly one strategy.** Average daily-return correlation 0.96–0.98 puts the effective number of
  independent strategies at 1–2 (Eq. 9). The effective number of independent *differentials* is higher (9–14). That is
  the N to use when deflating an improvement claim.
- **v6.75 (`GA_nolow`, the core of every batch-1 pass)** has IR 0.40 / yr on ETH mainnet (PSR(0) 0.83, MinTRL 16.6
  years) and 0.11 on WBTC (MinTRL 234 years). The ETH gain is consistent in sign but statistically weak. The WBTC
  gain is noise, which matches the batch-1 note "BTC wins are mostly within noise" (`CLAUDE.md`, **R**).
- Cross-pool correlation of the `GA_nolow` differential: 0.78–1.00 among ETH pools (except Arbitrum vs Base 0.3% at 0.39
  on a short overlap) and 0.98 between the BTC pools; 0.15–0.56 between ETH and BTC pools. **The pools give two
  observations, not seven.**

## 3. Multiple-testing and data-snooping corrections

### 3.1 White's Reality Check (2000)

- **Tests:** H0 "the best model encountered in a specification search has no predictive superiority over a given
  benchmark model" (White 2000, abstract, **P**). Uses the bootstrap distribution of the maximum mean performance
  differential over all models tried.
- **Inputs:** T × k performance differentials vs one benchmark, for *all* k models tried, on the same dates.
- **Here:** benchmark = spec v1 (`A` in the same invocation); models = every variant in the epoch. The data exist (§2).
- **Limits:** a single p-value for "the best", with no list of which models are good. Not studentized, so poor or
  irrelevant models lower its power. Hansen (2005) addresses this with studentization and recentering, as implemented
  in `arch.bootstrap.SPA` (docstring, **P**). Hansen's own wording on this was not read (**U**). `arch` exposes
  `RealityCheck` as an alias of `SPA` (source, **P**).

### 3.2 Hansen's SPA test (2005)

- **Tests:** the same null as White, with studentized statistics. `arch` reports three p-values for three recentering
  choices: *upper* never recenters, *consistent* recenters only models within a log(log T) bound, *lower* never
  recenters a model worse than the benchmark (`arch` SPA docstring, **P**; paper: Hansen 2005, JBES 23(4) 365–380,
  citation **P**, text **U**).
- **Inputs:** benchmark losses (T), model losses (T × k), bootstrap type (stationary by default) and block size
  (default √T; `optimal_block_length` implements Politis & White 2004 with the Patton-Politis-White 2009 correction,
  **P**).
- **Here:** loss = −daily log return (or −differential). One call per asset composite. Use it as G3's family test.
- **Limits:** tests mean daily log return, i.e. growth rate, not Calmar or max DD. Drawdown constraints stay as
  separate guardrails. The answer depends on which models are in the family, which is why G0's ledger matters.

### 3.3 Romano-Wolf stepwise (StepM, 2005)

- **Tests:** which individual models beat the benchmark, controlling the family-wise error rate (FWER). The procedure
  is stepwise, "asymptotically controls the familywise error rate", is "more powerful" than single-step methods and
  "implicitly captures the joint dependence structure of the test statistics" (Econometrica 73(4) 1237–1282, abstract
  page, **P**).
- **Inputs:** as SPA. `arch.bootstrap.StepM(benchmark, models, size, block_size, reps, bootstrap, studentize, nested)`
  "uses SPA and the consistent selection procedure" (docstring, **P**).
- **Here:** names the variants that survive. This is the per-variant half of G3.
- **Limits:** FWER control is strict. With IR ≈ 0.4–0.7 and 3–5 years of data, expect it to keep nothing. That is a
  finding, not a failure of the method.

### 3.4 Harvey, Liu & Zhu (2016) and Harvey & Liu (2015): t > 3 and the haircut Sharpe ratio

- **What they say:** "a new factor needs to clear a much higher hurdle, with a t-statistic greater than 3.0"; "most
  claimed research findings in financial economics are likely false" (HLZ, RFS 29(1) 2016, abstract, **P**). Harvey &
  Liu turn a Sharpe ratio into a t-ratio, adjust its p-value for multiple tests with Bonferroni, Holm or BHY, and
  convert back. The "haircut" is the percentage drop. The usual 50% haircut "is only a rule of thumb", and the
  multiple-testing haircut "is nonlinear": high Sharpe ratios are only moderately penalized and marginal ones heavily
  (Harvey & Liu, JPM Fall 2015, pp. 12–13, **P**). They warn that high Sharpe ratios can come from option-like
  negatively skewed returns (p. 13, **P**), which applies to a short-volatility LP.
- **Inputs:** Sharpe ratio, sample length, number of tests, and an assumption about correlation between tests.
- **Here:** a quick sanity check with no bootstrap. The t-stat of a differential ≈ IR × √years. For IR 0.73 over 5.4
  years, t ≈ 1.7. That is below 2, let alone 3.
- **Limits:** built for factor discovery with many roughly independent tests. Our trials are highly correlated, which
  the BHY and correlation-aware variants handle only through an assumed parameter. Use it as a second opinion, not a
  gate.

## 4. Bailey & López de Prado: PBO, PSR, DSR, MinTRL, False Strategy theorem

### 4.1 Probability of Backtest Overfitting (CSCV)

- **Tests:** the probability that the configuration chosen as best in-sample ranks below the median out of sample.
  CSCV splits the T × N performance matrix into S equal row blocks and uses every combination of S/2 blocks as
  in-sample (the rest as out-of-sample). It records the logit of the chosen model's OOS rank, and PBO is the share of
  logits ≤ 0 (Bailey, Borwein, López de Prado & Zhu, J. Computational Finance 20(4), 2017, §2–3, **P**). It also gives
  performance degradation, probability of OOS loss and stochastic dominance (§3, **P**).
- **Parameters:** "we believe that S = 16 is a reasonable value to use in most cases". For 4 years of daily data that is
  quarterly blocks and preserves serial correlation (§4, **P**; the paper prints 12,780 combinations for S = 16, while
  C(16, 8) = 12,870). N must be "≫ 10" for a smooth logit distribution (§4, **P**).
- **Limits stated by the authors (§5, **P**):**
  - The researcher "must provide full information regarding the actual trials conducted", because hiding trials
    underestimates overfit.
  - For guided searches, the columns should be the final outcome of each search.
  - CSCV "does nothing to evaluate the correctness of a backtest" (costs, look-ahead).
  - It only covers structural breaks present in the sample.
  - Strong autocorrelation can make the symmetric split unsuitable.
- **Here:** already used once: PBO 0.56 on 15 parameter variants of v6 (`V6_VALIDATION.md` §3, **R**). It can run per
  batch on the spec v1 full-history CSVs: N = 13–21 variants, 1,000–1,960 days, S = 16 gives 60–120-day blocks.
  v6's EMA 90–120 state spans about one block, so blocks are not independent. That is a known weakness, so report PBO
  with S = 8 as well.

### 4.2 Probabilistic Sharpe Ratio and minimum track record length

- **PSR** is the probability that the true Sharpe ratio exceeds a threshold, given sample length, skewness and kurtosis
  (Bailey & López de Prado, "The Sharpe Ratio Efficient Frontier", J. Risk, 2012 version, §3, **P**). It "does not
  ... incorporate the effect of higher moments on preferences", only on estimation accuracy (§3, **P**).
- **MinTRL** (Eq. 13) is the number of observations needed for PSR to exceed the confidence level. It grows with
  smaller SR, more negative skew, fatter tails and higher confidence. It is "expressed in terms of number of
  observations", and the moments must come from samples long enough for the CLT (§4, **P**).
- **Here:** apply PSR and MinTRL to the *differential* series (variant − baseline). The Sharpe ratio of a differential
  is an information ratio. This adaptation is ours, not the paper's, but the formula only needs a return series. It
  turns "wait for the forward window" into a number: 4.4 years for the best ETH variant, 16.6 years for v6.75 (§2).

### 4.3 Deflated Sharpe Ratio and the expected maximum Sharpe

- **Expected maximum Sharpe ratio** after N independent trials with zero true skill, with γ the Euler-Mascheroni
  constant (Eq. 1, App. A.1, **P**):
  E[max SR] ≈ √V[SR] · ((1 − γ) Z⁻¹[1 − 1/N] + γ Z⁻¹[1 − 1/(N e)]).
- **DSR** is PSR evaluated at that threshold (Eq. 2, **P**). It corrects for selection bias, sample length, skew and
  kurtosis.
- **Effective number of independent trials** (App. A.3, **P**). Given M correlated trials with average correlation ρ̂,
  "interpolate" N̂ = ρ̂ + (1 − ρ̂) M (Eq. 9). López de Prado & Lewis (Quantitative Finance 19(9), 2019) estimate "the
  number of effectively uncorrelated trials" by clustering the trials' returns (abstract, **P**; algorithm text
  **U**).
- **Here:** `V6_VALIDATION.md` §3 already reports DSR 0.92 / 0.88 / 0.84 for 10 / 50 / 200 trials for v6 itself
  (**R**). It notes that the walk-forward skill's implementation omits √V[SR] and that the report uses the paper's form
  (**R**). For improvement claims, run DSR on the differential series with V[SR] taken across the epoch's variants and
  N̂ from Eq. 9 (≈ 9–14 today, §2). Report it with M = 175 as well.
- **Limits:** needs V[SR] across trials, which is only known if every trial is logged (G0). It also assumes the trials
  are draws from one family, so a radically different strategy should start a new family.

### 4.4 False Strategy theorem

The published statement is in López de Prado & Bailey, *The False Strategy Theorem: A Financial Application of
Experimental Mathematics*, American Mathematical Monthly (2021). Its text was not opened this session (**U**). The
quantitative content used here is Eq. 1 of the DSR paper (**P**): the expected best Sharpe ratio of skill-less trials
rises with N and with the dispersion of trial results. This is why a pass rate of 44/174 is not evidence by itself.

## 5. Walk-forward, purged / embargoed k-fold, CPCV

- **What they are.** López de Prado, *Advances in Financial Machine Learning* (Wiley 2018):
  - ch. 7 "Cross-Validation in Finance": why k-fold fails, purging the training set, embargo;
  - ch. 11 "The Dangers of Backtesting";
  - ch. 12 "Backtesting through Cross-Validation": the walk-forward method and its pitfalls, and the combinatorial
    purged CV (CPCV) method;
  - ch. 13 "Backtesting on Synthetic Data".

  These are table-of-contents headings from the publisher's excerpt (**P**); the chapter text was not read (**U**). In
  `skfolio`'s implementation, purging removes "from the training set all observations whose labels overlapped in time
  with those labels included in the testing set". Embargo removes training observations "that immediately follow an
  observation in the testing set". CPCV forms C(n_folds, n_test_folds) splits and reconstructs several test paths
  (skfolio `CombinatorialPurgedCV` docs, **P**).
- **Fit to this project: low.** These methods validate a *fitted model* (train on part, test on the rest). v6 variants
  are fixed rules with constants frozen by pre-registration (`README.md`, **R**). Nothing is trained, so there is
  nothing to purge. Walk-forward would only matter if the team re-selected a variant or parameters periodically. If
  that ever happens, use anchored walk-forward with the selection rule itself as the "model", and an embargo of at
  least the EMA span (120 days) so the test window's signal does not depend on training-window prices.
- **Where the idea still helps.** CPCV's point is to evaluate many test paths instead of one. For fixed rules, PBO/CSCV
  (§4.1) and block bootstrap of the differential (§6.1) deliver that at lower cost. Dino's 2026-10-06 rule (no IS/OOS
  split, full history on all pools) agrees with Bailey et al.'s argument against a single holdout (§1.1) only if it is
  paired with a trial-count correction (G3). Without one, it just moves the selection bias onto more data.

## 6. Synthetic data and simulation tests

### 6.1 Block bootstrap of returns (stationary bootstrap)

- Politis & Romano (1994, JASA 89(428) 1303–1313) resample blocks of random (geometric) length, keeping serial
  dependence. Optimal block length follows Politis & White (2004) with the 2009 correction (cited in `arch` source,
  **P**; papers' text **U**). `arch` provides `StationaryBootstrap`, `CircularBlockBootstrap`, `MovingBlockBootstrap`
  and `optimal_block_length` (**P**).
- **Here:** bootstrap the *daily differential* to get a confidence interval for the CAGR gain and the G2 p-value. It
  also gives the distribution of the gain over any window length, which is the G6 kill band. It is cheap and runs on
  saved CSVs.
- **Limits:** it resamples the strategy's outputs, not the market. Path-dependent effects (EMA state, refill stages)
  are only kept within blocks. Use blocks of ≥ 20 days and check sensitivity to 60.

### 6.2 Synthetic price paths (GBM, regime-switching, bootstrapped price blocks)

- AFML ch. 13 fits trading rules on simulated paths (heading **P**, content **U**). Regime-switching models (Hamilton
  1989, Econometrica 57(2), **U**) are the usual way to keep bull/bear/chop sequences.
- **Fit: low priority, high cost.** demeter replays real pool swap and liquidity events to earn fees (V6_VALIDATION
  §6, **R**). A synthetic price path needs a matching synthetic volume, fee and liquidity process, and LP P&L is
  dominated by market beta (>99.99% of LP return variance; Milionis et al., arXiv 2208.06046, abstract, **P**). Any fee
  model would decide the answer. Two cheaper substitutes:
  - (a) more real paths: a third pool or chain, and the forward window, which `CLAUDE.md` already lists as next;
  - (b) stitched real segments with Binance warm-up (`BINANCE_WARM=1` exists), e.g. yearly segments reordered. This
    only tests sensitivity to sequence and is still a backtest per path.

### 6.3 Parameter-sensitivity / plateau tests

- Already done for v6 (`V6_VALIDATION.md` §2, **R**). All 14 one-at-a-time perturbations stay positive, but 34% of
  (variant, year) cells move > 5 pts. The defensive effect is structural; the level is not.
- **For structural variants:** pre-register one neighbour per fixed constant (e.g. the "no new low" lookback ±1 day) and
  require the gain's sign to hold on the neighbours. A peak that disappears at the neighbour is overfit. This needs a
  few backtests per variant, so it applies only to variants that reach "candidate".

### 6.4 Model Confidence Set (Hansen, Lunde & Nason 2011)

- **Tests:** builds "a set of models expected to contain the best-performing model at a specified confidence level",
  like a confidence interval. Uninformative data give larger sets (Econometrica 79(2) 453–497, abstract page, **P**).
- **Inputs:** T × k losses. `arch.bootstrap.MCS(losses, size, reps, block_size, method='R'|'max', bootstrap)` (source,
  **P**).
- **Here:** the honest summary statistic for the team dashboard: "these N variants, including spec v1, cannot be told
  apart". With correlations of 0.96+ it will most likely include the baseline. That is the message to carry, not a
  reason to skip it.

## 7. Forward testing, incubation, pre-registration

- **Pre-registration** is already the team's practice: hypothesis, constants, pools and rule are committed before the
  run (`README.md`, `TEMPLATE.md`, **R**). Literature that makes the same case:
  - Arnott, Harvey & Markowitz, "A Backtesting Protocol in the Era of Machine Learning", JFDS 1(1) 64–74, 2019
    (citation **P**, protocol text **U**);
  - Harvey's 2017 AFA presidential address, JF 72(4) (citation from search, **U**).

  What pre-registration does not fix is the *count*: 175 pre-registered trials are still 175 trials. G0 + G3 close
  that gap.
- **Forward / incubation.** MinTRL (§4.2) gives the honest expectation: at the observed IRs, several years of forward
  data would be needed to confirm an improvement statistically. So the forward window's job is:
  - (a) to detect a broken rule early: the G6 kill band from the block bootstrap;
  - (b) to check implementation: replay the same forward window in demeter and compare with paper or live fills. The
    gap is the implementation shortfall that AFML ch. 14 lists as a backtest statistic (heading, **P**).

  The open Jira items waiting for the forward window (QUAN-842 EXP-008, QUAN-1013 EXP-128; `CLAUDE.md`, **R**) should
  be read this way: a pass after a few months is "not broken", not "confirmed".

## 8. What is LP-specific about validating a Uniswap v3 strategy

The statistical methods above are generic. These are the parts of an LP backtest that can create a fake edge. They
should be G1 (fix before testing significance), because CSCV and SPA cannot see them (Bailey et al. 2017 §5.2: the
procedure "does nothing to evaluate the correctness of a backtest", **P**).

| issue | evidence | effect on a v6 variant | G1 treatment |
|---|---|---|---|
| Market beta dominates LP P&L | >99.99% of LP return variance is market risk (Milionis et al. 2022, **P**). v6's money is exposure timing; its LP leg is about zero (`RESEARCH-2026-10-06`, **R**) | a variant that changes F timing changes beta. Its "gain" can be a different bet on ETH's path, not skill | report the differential's beta to ETH. A gain that is all beta is a market call |
| Fee share overstated | demeter credits L_ours / L_pool without our own liquidity in the denominator: +0.1% at $100k, +7% at $10M (`V6_VALIDATION.md` §6, **R**) | small at $100k; grows with size | scale fees by L_pool / (L_pool + L_ours) when AUM > $1M |
| JIT liquidity not modelled | 36,671 JIT attacks in 20 months on Ethereum; existing LPs suffer "an average dilution of 85%" in attacked swaps (Xiong et al., IACR ePrint 2023/973, **P**). Minute-close liquidity misses JIT (`V6_VALIDATION.md` §6, **R**) | fee income on mainnet 0.05% overstated by an unknown share | fee × 0.8 stress (team bar); compare variants whose fee share differs |
| Gas reported, not charged | mainnet gas ~$200k vs $122k on $100k for rebuild-heavy variants (`CLAUDE.md` batch 1, **R**) | rebuild-heavy rules win only gross of gas | charge gas at the target chain's price; report mainnet as an upper bound |
| Swap cost and MEV | v6 swaps up to ~90% of AUM at 00:00 UTC, predictable and MEV-exposed (`V6_VALIDATION.md` §6, **R**). Spec v1 uses a flat 0.1% (`CLAUDE.md`, **R**) | rules that add swaps look cheaper than they are | swap cost × 2 stress |
| Arbitrage depends on block time and fee | arbitrage profit scales with the fraction of blocks with a profitable trade; faster blocks reduce LP losses (Milionis, Moallemi & Roughgarden, arXiv 2305.14604, abstract, **P**) | mainnet vs Base / Arbitrum results are not interchangeable. Chain is a variable, not a replicate | judge on the target chain; keep chains as separate rows |
| Few, correlated price paths | ETH pools' differentials correlate 0.78–1.00 (§2, **R**) | "N of 7 pools" overstates evidence | per-asset composite (G2) |

## 9. Comparison table

| method | question | needs new backtests? | runs on existing CSVs? | handles correlated trials | main limit here | priority |
|---|---|---|---|---|---|---|
| Trial ledger + pre-registration | how many tries | no | n/a | n/a | only as good as completeness | **G0, keep** |
| LP cost / fill stress | is the gain a simulator artefact | no (post-hoc), yes for exact | yes, approximately | n/a | post-hoc ignores compounding | **G1** |
| Paired block-bootstrap test of the differential | is the gain bigger than noise | no | yes | n/a (one variant) | ignores the search | **G2** |
| White Reality Check | does the best beat the benchmark | no | yes | yes (joint bootstrap) | low power with junk models | via SPA |
| Hansen SPA | same, studentized and recentred | no | yes | yes | mean return only | **G3** |
| Romano-Wolf StepM | which ones beat it, FWER | no | yes | yes | strict, likely empty | **G3** |
| Deflated Sharpe Ratio | is SR above the expected max of N trials | no | yes | via N̂ (Eq. 9 / clustering) | needs every trial's SR | **G3** |
| HLZ t > 3 / haircut SR | quick hurdle | no | yes | through an assumed correlation | built for independent factors | sanity check |
| PBO / CSCV | does IS-best stay good OOS | no | yes | yes (rank-based) | serial dependence across blocks; N ≫ 10 | **G4** |
| Model Confidence Set | which are tied with the best | no | yes | yes | descriptive | **G5, report** |
| PSR / MinTRL | how long until significant | no | yes | no | asymptotic; CLT on moments | inputs to G2/G6 |
| Walk-forward / purged k-fold / CPCV | does a fitted model generalise | yes | no | partly | nothing is fitted in v6 variants | only if re-selection is added |
| Synthetic price paths | is the rule tied to one history | yes, plus a fee model | no | n/a | the fee model decides the answer | G7, optional |
| Sensitivity / plateau | peak or plateau | yes (few) | no | n/a | cost per variant | for candidates |
| Forward incubation | does it break live | yes (monthly) | n/a | n/a | MinTRL: years to confirm | **G6** |

## 10. What we already have vs gaps

| area | have (R) | gap |
|---|---|---|
| Pre-registration, commit before run | yes, every EXP since EXP-001 | a family tag and a running trial count per baseline epoch; runs outside the registry (crashed reruns, ad hoc looks) are not counted |
| Baseline in the same invocation | yes (`A`, spec v1 since EXP-157) | — |
| Daily equity per variant | yes, `equity_*.csv` for every run (676 files in the main checkout; full-history spec v1 sets of 13–21 variants per pool) | some earlier raw CSVs were lost with a removed worktree (`CLAUDE.md`). Keep results in the main checkout |
| Costs | pool fee + flat 0.1% swap (spec v1), gas reported | gas not charged; JIT / fee-share and MEV not stressed |
| PBO | once, 15 parameter variants of v6 (0.56) | never run on structural batches |
| DSR / PSR | once for v6 itself (0.84–0.92) | never run on improvement differentials; N̂ never estimated from trial correlations |
| Multiple-comparison tests (SPA, StepM, MCS) | none | `arch` not installed in `.venv-lab`; needs `arch` added to `requirements-lab.txt` and a `validate_stats.py` that reads a run folder |
| Verdict rule | per-pool win count (≥ 4/7, one ETH and one BTC), CAGR / Calmar / DD point estimates (`judge_full.py`) | treats correlated pools as independent; no standard errors; no search correction |
| Forward window | planned (after 2026-09-17) | no kill band, no MinTRL-based expectation, no replay-vs-live comparison |
| Sensitivity | v6 parameters (`V6_VALIDATION.md` §2) | no neighbour check for structural variants |

Concrete next step (not done here, needs Dino's go): add `experiments/validate_stats.py`. Input: one run folder per
pool. Output: G1 stress table, G2 per-asset p-values, G3 SPA / StepM / DSR, G4 PBO, G5 MCS. Then re-score EXP-157..175
as a test of the pipeline. Estimated 1 day. It needs no backtests.

## References

Primary, opened this session (**P**):

- White, H. (2000). A Reality Check for Data Snooping. *Econometrica* 68(5), 1097–1126. Abstract page:
  https://www.econometricsociety.org/publications/econometrica/2000/09/01/reality-check-data-snooping
- Romano, J. P., Wolf, M. (2005). Stepwise Multiple Testing as Formalized Data Snooping. *Econometrica* 73(4),
  1237–1282. https://www.econometricsociety.org/publications/econometrica/2005/07/01/stepwise-multiple-testing-formalized-data-snooping
- Hansen, P. R., Lunde, A., Nason, J. M. (2011). The Model Confidence Set. *Econometrica* 79(2), 453–497.
  https://www.econometricsociety.org/publications/econometrica/2011/03/01/model-confidence-set
- Harvey, C. R., Liu, Y., Zhu, H. (2016). … and the Cross-Section of Expected Returns. *Review of Financial Studies*
  29(1). PDF on the author's page: https://people.duke.edu/~charvey/Research/Published_Papers/P118_and_the_cross.PDF
  (abstract).
- Harvey, C. R., Liu, Y. (2015). Backtesting. *Journal of Portfolio Management*, Fall 2015, 12–28. PDF:
  https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF (pp. 12–15).
- Bailey, D. H., López de Prado, M. (2014). The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest
  Overfitting and Non-Normality. *Journal of Portfolio Management* (July 2014 version). PDF:
  https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf (Eq. 1, Eq. 2, App. A.1, A.3, holdout section).
- Bailey, D. H., Borwein, J. M., López de Prado, M., Zhu, Q. J. (2017). The Probability of Backtest Overfitting.
  *Journal of Computational Finance* 20(4), doi:10.21314/JCF.2016.322. PDF (Feb 2015 revision):
  https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf (§2–5). Journal page:
  https://www.risk.net/journal-of-computational-finance/2471206/the-probability-of-backtest-overfitting
- Bailey, D. H., López de Prado, M. (2012). The Sharpe Ratio Efficient Frontier. *Journal of Risk* (July 2012
  version). PDF: https://www.davidhbailey.com/dhbpapers/sharpe-frontier.pdf (§3, §4, Eq. 13).
- López de Prado, M., Lewis, M. J. (2019). Detection of false investment strategies using unsupervised learning
  methods. *Quantitative Finance* 19(9), 1555–1565. https://ideas.repec.org/a/taf/quantf/v19y2019i9p1555-1565.html
  (abstract).
- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley. Table of contents excerpt:
  https://media.wiley.com/product_data/excerpt/89/11194820/1119482089-118.pdf
- Milionis, J., Moallemi, C. C., Roughgarden, T., Zhang, A. L. Automated Market Making and Loss-Versus-Rebalancing.
  https://arxiv.org/abs/2208.06046 (abstract).
- Milionis, J., Moallemi, C. C., Roughgarden, T. Automated Market Making and Arbitrage Profits in the Presence of Fees.
  https://arxiv.org/abs/2305.14604 (abstract).
- Xiong, X., Wang, Z., Knottenbelt, W., Huth, M. Demystifying Just-in-Time (JIT) Liquidity Attacks on Uniswap V3.
  https://eprint.iacr.org/2023/973 (abstract).
- Heimbach, L., Schertenleib, E., Wattenhofer, R. Risks and Returns of Uniswap V3 Liquidity Providers.
  https://arxiv.org/abs/2205.08904 (abstract).

Libraries (official docs or source, **P**):

- `arch` (K. Sheppard), version 8.0.0 on PyPI (https://pypi.org/project/arch/). Source of `SPA`, `RealityCheck`,
  `StepM`, `MCS`:
  https://github.com/bashtage/arch/blob/main/arch/bootstrap/multiple_comparison.py ; bootstraps and
  `optimal_block_length`: https://github.com/bashtage/arch/blob/main/arch/bootstrap/base.py ; docs:
  https://bashtage.github.io/arch/
- `pypbo` (PBO, PSR, MinTRL, MinBTL, DSR; AGPL-3.0): https://github.com/esvhd/pypbo . Note the AGPL licence if the code
  is ever shipped. For internal research use it is fine, or reimplement CSCV in ~60 lines.
- `skfolio` `CombinatorialPurgedCV`: https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html
- `mlfinlab` (Hudson & Thames): proprietary, "all rights reserved", paid
  (https://github.com/hudson-and-thames/mlfinlab README). Not on PyPI any more (PyPI JSON returned "Not Found" this
  session). Not recommended.

Cited but not verified from a primary text (**U**):

- Hansen, P. R. (2005). A Test for Superior Predictive Ability. *JBES* 23(4), 365–380. Citation confirmed on RePEc
  (https://ideas.repec.org/a/bes/jnlbes/v23y2005p365-380.html), paper text not read. Its behaviour is described from
  the `arch` implementation.
- Politis, D. N., Romano, J. P. (1994). The Stationary Bootstrap. *JASA* 89(428), 1303–1313. Politis & White (2004),
  *Econometric Reviews* 23(1); Patton, Politis & White (2009) correction, *Econometric Reviews* 28(4). Cited from
  `arch` source.
- López de Prado, M., Bailey, D. H. (2021). The False Strategy Theorem: A Financial Application of Experimental
  Mathematics. *American Mathematical Monthly*.
- Arnott, R., Harvey, C. R., Markowitz, H. (2019). A Backtesting Protocol in the Era of Machine Learning. *JFDS* 1(1),
  64–74, doi:10.3905/jfds.2019.1.064 (citation via https://scholars.duke.edu/publication/1518184).
- Harvey, C. R. (2017). Presidential Address: The Scientific Outlook in Financial Economics. *Journal of Finance*
  72(4), 1399–1440.
- Hamilton, J. D. (1989). A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle.
  *Econometrica* 57(2).
- Bailey, Borwein, López de Prado, Zhu (2014), "Pseudo-Mathematics and Financial Charlatanism", *Notices of the AMS*
  61(5) (minimum backtest length). The PDF could not be fetched (403).

Repo (paths relative to `samples/strategy-example/`, **R**): `V6_VALIDATION.md` §2, §3, §4, §6;
`experiments/README.md`; `experiments/registry.csv`; `experiments/judge_full.py`; repo-root `CLAUDE.md` (Rules for
experiments, batch 1 notes, Handoff 2026-10-06); `experiments/RESEARCH-2026-10-06-is-lp-worth-it.md`; daily equity and
result CSVs under the main checkout's `result/v6_validate/` (spec v1 full-history runs of EXP-156..175).
