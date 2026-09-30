# Defense v6: is the backtest trustworthy, and should it go live?

Date 2026-09-29. Scripts: `v6_validate.py` (runs), `v6_validate_report.py` (numbers below).
Gas ignored unless stated; pool fee and price impact of every rebuild swap charged. 100,000 USDC.

## Verdict

The engine is reproducible and the defensive effect is real and robust on ETH, but the edge is in-sample,
not statistically significant after multiple testing, absent on BTC, and ~100% of the return is fee income
whose level on the target chain is unverified. **Not ready for a full launch; a capped pilot is justified.**

## 1. Reproducibility

2024 and 2025 reproduce `PDFV6_COMPARISON_REPORT.md` exactly (net value 136,414 / 116,506). The signal engine
statistics for 2025 (mean F 0.585, 124 days at 0, 182 at 1) match too.

## 2. Parameter sensitivity (walk-forward skill: plateau vs peak)

One parameter moved at a time, 5 segments (2022, 2023, 2024, 2025, 2026-01-01..09-17), yearly reset:

| variant | 2022 | 2023 | 2024 | 2025 | 2026 | chained |
|---|---|---|---|---|---|---|
| refill thresholds ×1.2 | 16.6 | 37.9 | 29.7 | 19.9 | 16.8 | +192% |
| **base** | 7.6 | 32.2 | 36.4 | 16.3 | 18.7 | **+168%** |
| EMA spans ×0.8 | −8.2 | 34.9 | 21.0 | 11.2 | 12.6 | +88% |
| width ±15% | −4.3 | 25.3 | 11.2 | 12.3 | 22.6 | +84% |
| lower stop 0.85 | −15.9 | 32.2 | 2.3 | 11.5 | 20.2 | +53% |
| plain valley LP | −39.2 | 46.1 | 41.5 | −7.9 | −4.5 | +10% |

- All 14 perturbations stay positive over the whole period and all beat the plain LP in 2022, 2025 and 2026:
  the defensive effect is structural, not a lucky parameter set.
- The level is not: 34% of (variant, year) cells move more than 5 pts; width, lower stop and EMA spans are sensitive.
- In 2023 and 2024 (bull years) the plain LP beats every v6 variant.

## 3. Overfitting (walk-forward skill)

- PBO (CSCV, 15 v6 variants, 10 groups, 252 paths): **0.56**. Picking the in-sample best neighbour does not carry
  out of sample; further tuning inside this family is noise.
- Base Sharpe 0.91 (annualised, daily, 1,716 days), skew 0.24, kurtosis 8.8. Probabilistic SR (1 trial) 0.977.
  Deflated SR with the variants' SR dispersion: 0.92 (10 trials), 0.88 (50), 0.84 (200) — **below 0.95** for any
  plausible number of trials. The spec author iterated with AI on the same 2022–2025 history, so trials ≫ 10.
- Note: the skill's `deflated_sharpe_ratio` omits the √Var(SR) scale on the expected maximum, which would flag any
  daily strategy as overfit; the report uses the López de Prado form.

## 4. Continuous run and cross-asset out of sample (portfolio-analytics skill)

ETH/USDC 0.05%, 2022-01-01 → 2026-09-17, one continuous run (fees paid out in USDC, not reinvested):

| | total | CAGR | vol | max DD | Sharpe | Sortino | Calmar | longest underwater |
|---|---|---|---|---|---|---|---|---|
| **v6** | +85.4% | 14.0% | 21.1% | −22.8% | 0.73 | 0.85 | 0.61 | 491 d |
| plain valley LP | −24.6% | −5.8% | 19.4% | −47.9% | −0.21 | −0.21 | −0.12 | 1,719 d |
| hold ETH | −35.0% | −8.7% | 69.0% | −74.0% | 0.21 | 0.31 | −0.12 | 794 d |
| 50/50 hold | −17.5% | −4.0% | 26.6% | −38.0% | −0.02 | −0.03 | −0.11 | 794 d |

v6: beta to ETH 0.22, annual alpha 12.2%. Fees $86.5k of the $85.4k gain: **principal is flat, the return is fee income.**
Mainnet gas for this path would have been $61k (147 rebuilds × 16 positions).

WBTC/USDC 0.3%, 2022-11-01 → 2026-09-17 (v6 never fitted on BTC):

| | total | CAGR | max DD | Sharpe |
|---|---|---|---|---|
| v6 | +85.6% | 17.3% | −17.8% | 1.01 |
| plain valley LP | +88.9% | 17.8% | −20.0% | 1.04 |
| hold BTC | +273.8% | 40.5% | −53.2% | 0.96 |

On BTC v6 does not beat the plain LP (−3 pts, slightly lower drawdown). The window is mostly a bull market,
which is v6's weak regime, so this is "no edge shown", not "edge refuted".

## 5. Regimes (regime-detection skill)

30-day trend (±10%) × 30-day realised vol (above/below median), known at the start of each day, ETH continuous run:

| regime | days | v6 | plain LP | ETH |
|---|---|---|---|---|
| down, high vol | 371 | +9.4% | −15.0% | −62.7% |
| down, low vol | 121 | +2.4% | −22.4% | −46.0% |
| range, high vol | 227 | +42.6% | −4.5% | −22.5% |
| range, low vol | 489 | +14.4% | +9.4% | +57.5% |
| up, high vol | 246 | +46.3% | +13.3% | +214.9% |
| up, low vol | 236 | −9.2% | −1.1% | −15.9% |

(annualised within each regime). v6 earns its keep in down and choppy markets; it gives up most of the upside in
strong rallies and loses in slow grinds up (whipsaw of the EMA exits).

## 6. Capacity and model limits (lp-math, impermanent-loss, slippage skills)

- 2025 pool LP fees $29.0M; v6 earned $20.8k = 0.072% of them. demeter credits `L_ours / L_pool` (own liquidity not
  in the denominator): overstatement 0.1% at $100k, 0.7% at $1M, 7% at $10M, 36% at $50M.
- Price impact (virtual reserve at the active tick, no routing): 0.23% of AUM a year at $100k, ~2.3% at $1M,
  ~23% at $10M. The model is conservative (a router would split), but v6 swaps up to ~90% of AUM in one go when
  F jumps 0↔1, always at 00:00 UTC — a predictable, MEV-exposed trade.
- Not modelled at all: JIT liquidity (heavy on this mainnet pool; the minute-close liquidity misses it, so fee share
  is overstated), sandwiching, and the target chain (the deck says Base; every fee number here is mainnet).

## Go-live conditions

1. Re-run on the actual target pool (Base USDC/WETH): the return is fee income, so this is the number that matters.
2. Execution: split the F-switch swap (TWAP / private relay), randomise the rebuild minute.
3. Pilot capped at ≤ $250k–$1M with a kill switch (e.g. drawdown > 25% or 3 months below the plain LP in a down market).
4. Freeze parameters (PBO 0.56: no more tuning), and market the real-fee numbers, not the spec's reward model
   (deck 2025 +22.3% vs +16.3% here).
5. The cbBTC "Growth" pool is unvalidated: v6 showed no edge over the plain LP on BTC.

## Status after EXP-001..013 (2026-09-30)

1. **Done** (EXP-004 holdout): Base USDC/WETH 0.05%, 2024-01..2026-09-17, v6 +55.9% (CAGR 17.8%, max DD −28.1%).
   Per year Base +19.4% / +13.9% / +19.1% vs mainnet +36.4% / +16.3% / +18.7%: the gap is the Base pool's first
   year; fee income per unit of liquidity is now about mainnet's (`samples/fee_density.py`). Base 0.3% is no better.
2. Open. On Base the rebuild price impact was $3.6k in 2024 but $0.3k in 2025 and $0.06k in 2026 (per $100k), so
   splitting swaps is worth little at pilot size; MEV exposure of the 00:00 rebuild is unchanged.
3. Open (operational).
4. Parameters untouched in all thirteen experiments (structural changes only). One version passed dev and holdout:
   **v6.4, idle USDC in Aave** (EXP-004: ETH dev +101% vs +85%, Base holdout +63.2% vs +55.9%, drawdown shallower).
   Nine structural variants of the signal / ladder failed (EXP-001..003, 005..007, 009, 010, 012, 013; see
   `experiments/`).
5. **Done** (EXP-011): on Base USDC/cbBTC 0.05% (2025..2026-09) v6 +22.3%, Calmar 0.80, vs plain LP +6.8%, 0.15;
   v6.4 +25.8%, Calmar 1.03. The Growth pool is a valid venue. A 50/50 ETH+BTC portfolio of
   v6 books (EXP-008, dev seen: Sharpe 0.78 → 0.98, max DD −22.8% → −18.7%) waits for its forward holdout
   (2026-09-18..12-31, run in Jan 2027).

**Deployment estimate on Base** (daily equity of EXP-004 and EXP-011 runs, 2025-01-01..2026-09-17, books rebalanced
daily, transfer cost not modelled; the weights were not fitted):

| book | CAGR | max DD | Sharpe | Calmar |
|---|---|---|---|---|
| v6 ETH | 14.4% | −19.4% | 0.70 | 0.74 |
| v6 ETH + cbBTC 50/50 | 13.3% | −15.7% | 0.84 | 0.85 |
| **v6.4 ETH + cbBTC 50/50** | **15.3%** | **−14.5%** | **0.96** | **1.05** |

Daily return correlation of the two books 0.61. Candidate for the pilot: v6.4 on both Base pools, 50/50.

## Addendum 2026-09-30 — attribution (EXP-014) and the literature pass (EXP-012..016)

§4's "principal is flat, the return is fee income" reads the fee ledger, not the attribution. EXP-014 hedged 60% of
the ladder's ETH delta with a perp and the short lost $51k on ETH over 2022–26 (and $44k on BTC), losing in every
year including 2022: the ladder holds ETH almost only while the price rises, because the F engine deploys into
confirmed rebounds and exits before the falls. That timing is worth ≈ +$85k, i.e. essentially all of v6's gain;
fees ($86k) pay for the IL. v6 is **trend-timed concentrated LP**: the engine's timing of ETH exposure is the
return, fees cover the impermanent loss. Every variant that traded the exposure or the fee density for something
else lost (EXP-012 fee-vs-LVR gate, EXP-013 trend-skewed range, EXP-014 hedge, EXP-016 toxicity pause); the
fee tier makes no difference per unit of liquidity (EXP-015). Details: `experiments/RESEARCH-2026-09-30-lp-literature.md`
and the EXP files.
