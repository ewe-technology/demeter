# Research: does a Uniswap LP make money, and does it beat holding ETH? (2026-10-05)

Question from Dino. This note answers it from two kinds of evidence: primary papers (read in full this time, sections cited)
and the repo's own v6 runs (read from saved outputs; no new backtest). It extends
`RESEARCH-2026-09-30-lp-literature.md` (which ranked optimisation directions) and does not repeat it: that note's
secondary sources are cited from there and marked "via 09-30 note, not re-verified". Evidence grades as in that note:
**A** paper with numbers, **B** practitioner data, **R** this repo's own runs (backtest, in-sample unless said).

## Question

1. Does passive Uniswap liquidity provision (no timing) make money compared with holding?
2. Does v6 (a timed ±20% Uniswap v3 ETH/USDC LP) beat simply holding ETH?
3. Where does v6's money come from?

Three benchmarks are used below and they must not be mixed:

| benchmark | what it compares | who uses it |
|---|---|---|
| **vs HODL** (impermanent loss, IL) | LP value + fees vs holding the tokens deposited at the start (≈ 50/50 bought once) | Loesch et al.; Heimbach et al. |
| **vs rebalancing** (loss-versus-rebalancing, LVR) | LP vs a strategy that holds the same ETH amount as the pool at every moment, trading at CEX prices | Milionis et al.; Fritsch & Canidio |
| **vs 100% ETH** | LP vs putting all the money in ETH | Dino's question; `benchmark_return` in the repo's run CSVs |

## Short answer

- **Passive LP, on average, does not beat holding the deposited tokens on the big ETH pools.** Across 17 v3 pools in
  May–Sep 2021, fees were $199.3m and IL $260.1m, and about half of LPs ended with negative returns (Loesch et al.).
  Against the stricter rebalancing benchmark, fees on WETH-USDC 0.05% covered about 80% of arbitrage losses in 2022–23,
  and WBTC-USDC 0.3% roughly broke even (Fritsch & Canidio). The repo agrees: a plain ±20% valley LP on ETH/USDC 0.05%
  lost −24.6% over 2022-01..2026-09, worse than a 50/50 buy-and-hold (−17.5%) and better only than 100% ETH (−35.0%).
  LP pays where fees per unit of LVR are high: pools with higher fee tiers or less arbitrage-heavy pairs.
- **v6 beats holding ETH over 2022–2026, but not in strong rallies.** ETH continuous: v6 +85.4% (CAGR 14.0%, max DD
  −22.8%) vs ETH −33.7% (CAGR −8.3%, max DD −74.0%). It loses to ETH in the bull years 2023 (+32% vs +90%) and 2024 (+36% vs
  +46%), in the 2021 window (+1.6% to +4.5% vs +4.7%), and on WBTC 2022-11..2026-09 (+85% vs +273%). It wins clearly on risk-adjusted
  terms (Calmar above the asset's in 7 of the 9 windows below, 8 of 9 with the recorded EXP-088 H5 run).
- **v6's money is exposure timing, not LP income.** On ETH 0.05%, fees (+$86.4k) do not cover the range's IL/gamma
  (−$102.5k) and swap costs (−$3.9k): the LP leg alone is about −$20k over 4.7 years. The gain comes from holding ETH
  when it rises (+$104.8k delta P&L while ETH fell 34%). The perp-hedge test (EXP-014) gives the same split.
- **All of this is a backtest with weak statistics:** PBO 0.56, deflated Sharpe < 0.95, 90+ experiments on the same two
  pools, and mainnet gas ($61k on $100k) is not charged.

## 1. Literature

### 1.1 Mechanics: a v3 position is short volatility

- Uniswap v3 Core whitepaper (Adams, Zinsmeister, Salem, Keefer, Robinson, 2021), §2: a position on [pa, pb] acts like
  a constant-product pool with larger virtual reserves. Its real reserves follow (x + L/√pb)(y + L√pa) = L² (eq. 2.2,
  Fig. 2). Outside its range it "is composed entirely of a single asset". §6.4.1 (eqs. 6.29/6.30) gives the amounts:
  below the range all token0, above the range all token1. (**A**)
- What this means for ETH/USDC: as ETH rises through the range the position sells ETH for USDC, and as it falls it
  buys ETH. It ends up all-USDC above the range and all-ETH below it. That is the payoff of a covered call / short put
  (concave in price), which is why it loses against holding whenever the price moves far and stays there. On mainnet
  0x88e6, token0 = USDC and token1 = WETH because tokens are ordered by address, so "token0" is not the volatile asset
  here. That is general Uniswap knowledge, not a statement in the whitepaper.
- §3.1: the fee tiers at launch are 0.05% / 0.30% / 1% (tick spacing 10 / 60 / 200). The whitepaper gives no
  capital-efficiency multiple. The often-quoted "4000x" comes from the launch blog (not read here).

### 1.2 The right benchmark: LVR

Milionis, Moallemi, Roughgarden, Zhang, "Automated Market Making and Loss-Versus-Rebalancing", arXiv 2208.06046 (read v6):

- Theorem 1 (§5.1–5.2) splits LP P&L into three parts: (a) the P&L of a rebalancing strategy holding the pool's ETH
  amount at CEX prices (pure market risk, hedgeable), (b) plus fees, (c) minus LVR. Corollary 1: the rebalancing
  strategy is the variance-minimising hedge. (**A**)
- §6, Example 3, eq. 19: for a constant-product pool, LVR per unit of pool value per unit time is **σ²/8**. At 5% daily
  vol that is ≈ 3.125 bp of pool value per day. A concentrated v3 range has more gamma per dollar, so its LVR per dollar
  is higher. The repo's EXP-012 uses the v3 in-range form σ²L√P/4 (`EXP-012-fee-lvr-gate.md`, Change). (**A**)
- §7, Uniswap v2 WETH-USDC, 2021-08..2022-07: **99.991%** of LP P&L variance is market risk (§7.2, Table 1). (**A**)
- §5.1 and §8: loss-versus-holding (IL) from a fixed start date equals LVR plus accumulated market risk. It is "almost
  as polluted by market risk as raw LP P&L" (§7.2) and is not additive across sub-periods (§8.1). In other words, "LP vs
  HODL" mostly measures where the price went, and "fees − LVR" measures whether liquidity was paid. (**A**)

Milionis, Moallemi, Roughgarden, "Automated Market Making and Arbitrage Profits in the Presence of Fees", arXiv
2305.14604: fee income from arbitrageurs ≈ LVR × (1 − P_trade) (§1.2, Theorem 4). In a model with 5% daily vol, the
probability of an arbitrage trade per 12 s block is 45.6% at a 5 bp fee and 12.3% at 30 bp (§4.1, Table 1). Higher fee
tiers are arbitraged less often. This is a model output, not data. (**A**, theory)

### 1.3 Measured: LP vs HODL

- Loesch, Hindman, Richardson, Welch, "Impermanent Loss in Uniswap v3", arXiv 2111.09192 (benchmark: holding the
  initial tokens):
  - 17 pools (43% of TVL), 2021-05-05..2021-09-20: fees **$199.3m**, IL **$260.1m**, so LPs were **$60.8m** better off
    holding (Abstract, Introduction). "Half (49.5%) of liquidity providers" had negative returns (Introduction, p.3).
  - USDC/WETH 0.3%: IL > $90m vs fees ≈ $80m (p.25). IL was 1.1× fees for positions held over a month and 1.8× for
    positions held up to a day (Abstract). Only JIT ("flash") LPs beat holding.
  - The paper is internally inconsistent on how many pools had fees above IL: "only two" (p.25) vs "3 of the 17"
    (Conclusion, p.37). (**A**)
  - Correction to the 09-30 note: its "fees $199M vs IL $260M" line is attributed to Falkenstein's Substack, but these
    are Loesch et al.'s figures.
- Heimbach, Schertenleib, Wattenhofer, "Risks and Returns of Uniswap V3 Liquidity Providers", arXiv 2205.08904 (AFT
  2022; benchmark: holding, R = (V_pos + F − V_hold)/V_hold, §4.2 eq. 3):
  - Sample 2021-05-04..2022-03-31, USDC/WETH and WBTC/WETH at 0.05% / 0.3%, plus stable pools (§5).
  - Narrow ranges have far larger mean daily returns in both directions; some USDC/WETH positions lost about −20% in a
    day in May 2021 (§5.3, Fig. 14).
  - Fewer than 30% of volatile-pool positions are rewarded for their extra risk relative to stable pools (Fig. 17).
  - They give no headline "share below HODL" figure of their own; their ~50% is a citation of Loesch et al. (**A**)
- Cartea, Drissi, Monga, "Predictable Loss and Optimal Liquidity Provision", arXiv 2309.08431, §5.2 Table 2: ETH/USDC
  0.05%, 5,156 LPs, 2021-05..2022-08. Mean position value change −1.64% per operation, mean fee +0.155%, net **−1.49%
  per operation** (gas excluded). This is mark-to-market vs initial value, so it includes ETH's move; it is not a HODL
  or LVR comparison. (**A**)

### 1.4 Measured: fees vs LVR, by pool tier

- Fritsch & Canidio, "Measuring Arbitrage Losses and Profitability of AMM Liquidity", arXiv 2404.05803: simulated
  full-range position, 2022-01..2023-12, arbitraged against Binance (§3.1).
  - In most ETH and BTC v3 pools fees fall short of arbitrage losses. **WETH-USDC 0.05%: fees ≈ 80% of losses.**
    WETH-USDT 0.05% and **WBTC-USDC 0.3%: roughly break even** (§3.2, Fig. 1). Smaller pairs often run fees > losses,
    up to +50% (Fig. 2).
  - Faster blocks (12 s → 100 ms) cut arbitrage losses by 20–70% (Abstract). (**A**)
- Fee-implied vol vs LVR on WETH/USDC 5 bp 2023–24, LVR ≈ 0.97 × fees (arXiv 2509.23222). CrocSwap markout: the 0.05%
  pool persistently negative, 0.3% about flat. Both via 09-30 note §1, not re-verified. (**A**/**B**)
- JIT liquidity dilutes passive LPs' fees by up to 44% on affected trades, but takes < 2% of total fees (AFT 2025, via
  09-30 note, not re-verified).

**Literature verdict.** A passive LP on ETH/USDC is, on average, roughly break-even to negative against holding the
deposited tokens. It is more clearly negative against the rebalancing benchmark on the busiest, lowest-fee pool
(0.05%), and closer to break-even on 0.3% pools. Against 100% ETH the answer depends entirely on ETH's path: an LP is
roughly half-long ETH, so it beats ETH in falls and loses in rallies. No source shows a passive ETH/USDC LP that beats
holding after fees in a lasting way.

## 2. Repo evidence (v6 and plain LP, backtests)

Setup: $100k USDC. Pool fee and rebuild price impact are charged; gas is reported, not charged (CLAUDE.md, Rules).
Pools: ETH/USDC 0.05% `0x88e6`, WBTC/USDC 0.3% `0x99ac`.

**What `benchmark_return` in the run CSVs is.** In `gamma_ig_gap_bands_defense_v6.py` (around line 2212),
`benchmark_series = actuator.account_status_df["price"][BASE]`. `remix_dao_utils.performance_metrics_for_dca` then sets
`benchmark_rate = return_rate(benchmark.iloc[0], benchmark.iloc[-1])`. So it is the base asset's price change from the
first to the last actuator row: **100% ETH (or WBTC) bought at the window start, no fees, no rebalancing**.
`V6_VALIDATION.md` §4 uses its own report (`v6_validate_report.py`, `continuous()`), in which "50/50 hold" means
`50000 + 50000·px/px0`: **bought once, not rebalanced**, entry at the first day's close.

### 2.1 Passive LP vs holding (the repo's "plain valley LP", always fully deployed)

`V6_VALIDATION.md` §4 (R):

| run | plain valley LP | v6 | 100% asset | 50/50 hold (buy once) |
|---|---|---|---|---|
| ETH 0.05%, 2022-01..2026-09-17 | −24.6% (CAGR −5.8%, DD −47.9%) | +85.4% | −35.0% | −17.5% |
| WBTC 0.3%, 2022-11..2026-09-17 | +88.9% (CAGR 17.8%, DD −20.0%) | +85.6% | +273.8% | +136.5%¹ |

¹ This note's computation (appendix, Binance closes); not in V6_VALIDATION.

- On ETH the plain LP finishes 7 points behind its own HODL benchmark, the same sign as Loesch et al. Plain LP by year:
  2022 −39.2, 2023 +46.1, 2024 +41.5, 2025 −7.9, 2026 −4.5% (`V6_VALIDATION.md` §2). It beats v6 in the two bull years.
- On WBTC 0.3% the plain LP returns ≈ v6 with no timing at all. This matches the pool's higher fee/LVR: trailing 7-day
  fee/LVR median **3.49 on WBTC vs 1.23 on ETH**, and ≥ 1 on 100% vs 80% of days (`FINDINGS-2026-10-05.md`, point 2;
  EXP-012 median R 3.50, `EXP-012-fee-lvr-gate.md` Result).
- The repo's ratio is higher than Fritsch & Canidio's (≈ 0.8 on ETH 0.05%, ≈ 1 on WBTC 0.3%). It uses minute-close
  variance on the LP's own in-range liquidity, without fees-in-arbitrage or per-block discretisation, so it is an upper
  bound. The ranking of the two pools agrees.

### 2.2 v6 vs 100% ETH vs 50/50 per window

Computed in the appendix from each run's daily `equity_A_v6.csv` and from `samples/eth_usd_hourly.csv` (ETH) or
`samples/binance_daily_closes.csv` (BTC). Hold entry is at the window's first instant. "50/50 rebal" is rebalanced daily
at no cost. It is a crude stand-in for the rebalancing idea, but not the LVR benchmark, which tracks the pool's own
delta. (R)

| window | v6 total / CAGR / max DD / Calmar | 100% asset | 50/50 buy once | 50/50 daily rebal |
|---|---|---|---|---|
| ETH 2022-01-01..2026-09-17 | **+85.4% / 14.0% / −22.8% / 0.61** | −33.7% / −8.3% / −74.0% / −0.11 | −16.9% / −3.8% / −38.3% / −0.10 | +7.7% / 1.6% / −46.6% / 0.03 |
| ETH 2022 | **+7.6%** / −17.0% / 0.45 | −67.6% / −74.0% / −0.91 | −33.8% / −37.7% | −37.5% / −46.6% |
| ETH 2023 | +32.2% / −12.7% / 2.54 | **+90.4%** / −27.7% / **3.27** | +45.2% / −17.7% / 2.55 | +41.7% / −14.2% / 2.95 |
| ETH 2024 | +36.4% / −24.5% / **1.48** | **+46.1%** / −45.7% / 1.00 | +23.0% / −29.3% / 0.79 | +27.3% / −24.2% / 1.13 |
| ETH 2025 | **+16.3%** / −20.4% / 0.80 | −10.8% / −60.2% / −0.18 | −5.4% / −31.6% | +1.5% / −35.4% / 0.04 |
| ETH 2026-01..09-17 | **+18.7%** / −9.9% / 2.75 | −17.7% / −53.6% / −0.45 | −8.8% / −28.4% | −6.0% / −30.2% |
| ETH 2021-05-06..12-31 (H5) | +1.6% / 2.4% / −30.7% / 0.08 ² | **+4.7%** / 7.2% / −57.7% / 0.13 | +2.3% / 3.6% / −31.3% / 0.11 | **+11.2% / 17.5% / −31.8% / 0.55** |
| WBTC 2022-11-01..2026-09-17 | +85.2% / 17.2% / −17.8% / **0.97** | **+272.9% / 40.4%** / −53.0% / 0.76 | +136.5% / 24.8% / −45.5% / 0.55 | +114.9% / 21.8% / −30.0% / 0.73 |
| WBTC 2022-01-01..10-31 (H4) | **+3.1%** / 3.7% / −12.5% / 0.29 ² | −55.7% / −62.3% / −61.3% | −27.8% / −31.1% | −30.4% / −35.8% |

Yearly rows show total / max DD / Calmar. Bold marks the best of the four. Max DD is on daily closes. The run CSVs'
`max_draw_down` is intraday and deeper, for example 24.4% for ETH continuous (`0x88e6-opt-A-2022-01-01-2026-09-17.csv`).

² The saved H5/H4 runs in the main checkout (`0x88e6-opt-AAO-2021-05-06-2021-12-31`, `0x99ac-opt-AAO-2022-01-01-2022-10-31`)
differ from the recorded EXP-088 holdout runs. Those used `BINANCE_WARM=1` (`EXP-088-no-new-low-refill.md`, Result):
H5 v6 +4.5%, CAGR 7.0%, DD −30.7%, Calmar 0.23; H4 v6 +2.4%, CAGR 2.9%, DD −12.5%. The saved files are most likely
runs without the Binance warm-up (same fees $21.0k and 37 rebuilds on H5). That explanation is **unverified**. Both
versions trail ETH on H5 in return.

Reading:

- **Raw return:** v6 beats 100% ETH in the down and sideways years (2022, 2025, 2026) and over the whole of 2022–26. It
  loses in the up years (2023, 2024), in 2021 H5, and on WBTC over 2022-11..2026-09, where it captures 31% of BTC's gain
  (85/273).
- **Risk-adjusted:** v6's Calmar beats 100% asset in 7 of 9 windows. The exceptions are ETH 2023
  (2.54 vs 3.27) and H5 in the saved run (0.08 vs 0.13; the recorded EXP-088 warm-up run has 0.23, which beats it). On H5, the daily-rebalanced 50/50 (Calmar 0.55) beats v6 (0.08–0.23) and ETH (0.13): in a choppy
  bull with a crash, plain rebalancing did best.
- **In strong rallies v6 lags far behind.** By regime, annualised (`V6_VALIDATION.md` §5): up/high-vol v6 +46.3% vs
  ETH +214.9%; up/low-vol v6 −9.2% vs ETH −15.9%; down/high-vol v6 +9.4% vs ETH −62.7%. The 2021 H5 window is not a
  clean "strong bull" end to end: ETH was +4.7% overall, with a May crash and a November peak.

### 2.3 Where v6's money comes from (daily P&L decomposition, ETH continuous)

Source: `result/v6_validate/0x88e6-opt-A-2022-01-01-2026-09-17/decomp_daily.csv`, built by `decomp.py` in the same
folder. The columns are:

- `fee`: change in collected + pending fees.
- `delta`: prior-day ETH units held × the day's price change.
- `swap`: rebuild swap fees.
- `rest`: dnv − fee − delta − swap, i.e. the range's IL/gamma plus the intraday timing of rebuilds.

Regime is 30-day trend ±10% × 30-day vol vs median, shifted one day. Verified here by re-summing the CSV (1,719 days,
2022-01-02..2026-09-16). (R)

| regime | days | net | fees | delta | IL/gamma (rest) | swaps | mean ETH exposure³ |
|---|---|---|---|---|---|---|---|
| down, high vol | 364 | +$5.2k | +$10.1k | +$7.4k | −$11.9k | −$0.4k | 16% |
| down, low vol | 155 | −$3.2k | +$2.9k | −$2.7k | −$3.3k | −$0.1k | 11% |
| range, high vol | 189 | +$15.6k | +$9.6k | +$15.6k | −$9.4k | −$0.3k | 32% |
| range, low vol | 530 | +$36.9k | +$15.7k | +$43.6k | −$21.6k | −$0.8k | 28% |
| up, high vol | 227 | +$27.7k | +$21.6k | +$38.1k | −$31.0k | −$1.1k | 38% |
| up, low vol | 254 | +$2.5k | +$26.4k | +$2.8k | −$25.3k | −$1.3k | 34% |
| **total** | 1,719 | **+$84.8k** | **+$86.4k** | **+$104.8k** | **−$102.5k** | **−$3.9k** | 27% |

³ ETH value / net value at the prior day's close, from `fees_A_v6.csv` (this note's computation).

The regime day counts differ from `V6_VALIDATION.md` §5 (for example, up/low 254 vs 236) because the date alignment
differs; the cause is **unverified**.

- **The LP leg alone loses:** fees − IL/gamma − swaps = 86.4 − 102.5 − 3.9 ≈ **−$20k** over 4.7 years. This matches the
  literature for ETH/USDC 0.05%: fees cover roughly 80–100% of LVR.
- **The return is the delta term, +$104.8k, earned while ETH itself fell 33.7%.** v6 held ETH (27% on average, 38% in
  up/high-vol) mostly on rising days. That is timing.
- **Independent check, EXP-014:** a 60% perp hedge of the ladder's ETH lost $51.3k on ETH and $44.3k on BTC, in every
  year including 2022. Implied timing value ≈ 51.3/0.6 ≈ +$85k, essentially all of v6's gain. Hedged v6 returned +24.1%
  (CAGR 4.7%, DD −11.0%), with fees − IL ≈ +$14k over the window (`EXP-014-perp-delta-hedge.md`, Result;
  `V6_VALIDATION.md` addendum).
- The two attributions bracket the LP leg at **about −$20k to +$14k on $100k over 4.7 years, i.e. roughly zero**. The
  accounting differs: the decomposition is unhedged, while EXP-014 hedges 60% and adds +$6.1k of funding.
- **up/low-vol is where the LP leg is exposed:** fees +$26.4k almost exactly pay IL −$25.3k, and with only 34% ETH
  exposure in a slow rise the delta adds just +$2.8k. Net is +$2.5k over 254 days. In up/high-vol IL (−$31.0k) exceeds
  fees (+$21.6k), and only the delta (+$38.1k) makes it positive.
- **Corollary from the experiment series:** v6 is a range harvester. Its edge is the staged refill below the EMA
  (`FINDINGS-2026-10-05.md` point 1). Changes that traded exposure for fee density all lost (EXP-012 gate, EXP-013 skew,
  EXP-014 hedge, EXP-016 pause; `V6_VALIDATION.md` addendum). The only improvement-level pass so far, v6.75 (EXP-088),
  refines refill timing again, not the LP leg (`FINDINGS-2026-10-05-round2.md`).

## 3. Synthesis

1. **Passive LP vs holding.** Not reliably profitable relative to holding on ETH/USDC. The literature (Loesch:
   fees/IL ≈ 0.77; Fritsch & Canidio: fees/LVR ≈ 0.8 on 0.05%) and the repo (plain LP −24.6% vs 50/50 −17.5%) agree.
   It can pay where fees per unit of LVR are high: higher fee tier (0.3% WBTC ≈ break-even per Fritsch & Canidio, repo
   fee/LVR 3.49 and plain LP ≈ v6 on WBTC), smaller pairs (Fritsch & Canidio Fig. 2), or low arbitrage intensity
   (Milionis et al. 2305.14604: fewer arbitrage blocks at higher fees). High vol raises LVR as σ², so fees must rise
   faster than variance.
2. **v6 vs holding ETH.** Yes over 2022–26 (+85% vs −34%) and in every down or sideways year. No in the bull years 2023
   and 2024, the 2021 H5 window and the BTC 2022–26 bull. Risk-adjusted it wins almost everywhere (Calmar 0.61 vs −0.11
   on ETH continuous; 0.97 vs 0.76 on WBTC). As a substitute for "being long ETH in a bull market" it is poor: about 30%
   of BTC's gain, 36% of ETH's 2023 gain.
3. **Source of the money.** Exposure timing (+$105k delta, ≈ +$85k by the hedge test). The ETH 0.05% LP leg is
   −$20k..+$14k, i.e. roughly zero, and fees pay for IL and little more. So v6 on ETH is in substance "a timed,
   partially invested ETH position that is paid in fees to sell ETH on the way up". Its value depends on the timing
   engine, whose statistics are weak (next section). On high fee/LVR pools (WBTC 0.3%) the LP leg itself is positive
   and timing adds little (v6 ≈ plain LP).

## 4. Caveats

- **Backtest only, in-sample.** ETH 0.05% 2021-05..2026-09-17 and WBTC 0.3% 2021-11..2026-09-17 are in-sample
  (CLAUDE.md, Rules). The time-split holdouts H4/H5 have been used for many variants (`FINDINGS-2026-10-05.md`, "Holdouts
  are used up").
- **Overfitting statistics** (`V6_VALIDATION.md` §3): PBO 0.56 across 15 v6 variants; Sharpe 0.91; deflated Sharpe 0.92
  / 0.88 / 0.84 at 10 / 50 / 200 trials, all below 0.95. The spec was iterated with AI on 2022–2025 data, so the number
  of trials is ≫ 10.
- **Multiple testing:** 96 experiments registered (EXP-001..096, `registry.csv`) on the same two pools. One
  improvement-level pass (v6.75) out of 40 under the current rule (`FINDINGS-2026-10-05-round2.md`).
- **Gas not charged:** $61.0k on mainnet over 2022–26 for 147 rebuilds (`gas_if_mainnet`, run CSV). That would erase
  ~70% of the $85k gain at $100k (rough: ~4.7% CAGR instead of 14.0%, ignoring compounding effects; this note's
  arithmetic). It matters less on an L2 or at larger size (Base holdout: `V6_VALIDATION.md` status §1).
- **JIT / MEV / capacity** (`V6_VALIDATION.md` §6): JIT liquidity is not modelled, so the fee share is overstated.
  v6's F-switch swaps up to ~90% of AUM at 00:00 UTC, which is MEV-exposed. Fee-share overstatement is 0.1% at $100k,
  7% at $10M and 36% at $50M; price impact is ~23% of AUM a year at $10M.
- **Benchmarks:** the repo has no true LVR benchmark (a same-delta rebalancer); the "50/50 daily rebal" column is not
  one. `benchmark_return` is 100% asset, price only.
- **Data notes:** small differences in the hold numbers (ETH −33.6% in the CSV, −33.7% here, −35.0% in V6_VALIDATION)
  come from entry timing (00:00 open vs first close) and price source. The saved H5/H4 equity differs from the EXP-088
  numbers (footnote ²).

## 5. Bottom line

- Simply providing liquidity to the big ETH/USDC pool does not, on average, beat holding the coins you put in. Fees
  cover roughly 80–100% of what arbitrageurs take. Pools with higher fees per unit of risk (e.g. WBTC/USDC 0.3%) can pay.
- v6 made +85% over 2022–26 while ETH lost a third, with a third of ETH's drawdown. In bull runs it captures a fraction
  of the move (2023: +32% vs +90%; BTC 2022–26: +85% vs +273%).
- v6's profit comes from when it holds ETH, not from the LP fees. On ETH the fees roughly pay for the LP's built-in
  losses and little more.
- If you want ETH upside, hold ETH. v6 is a lower-risk, timed product that wins in falls and chop and lags in rallies.
- These are backtests on data the strategy was tuned on, with gas excluded and weak overfitting statistics. The forward
  window after 2026-09-17 is the real test.

## Sources

Primary literature (read in full for this note; section numbers refer to the arXiv version noted):

- Adams, Zinsmeister, Salem, Keefer, Robinson, *Uniswap v3 Core* (2021), https://uniswap.org/whitepaper-v3.pdf — §2, eq. 2.2, Fig. 2; §3.1; §6.4.1 eqs. 6.29/6.30.
- Milionis, Moallemi, Roughgarden, Zhang, *Automated Market Making and Loss-Versus-Rebalancing*, https://arxiv.org/abs/2208.06046 (v6) — Thm 1 §5; eq. 19 §6; §7 Table 1, Fig. 7; §8.
- Milionis, Moallemi, Roughgarden, *Automated Market Making and Arbitrage Profits in the Presence of Fees*, https://arxiv.org/abs/2305.14604 — §1.2, Thm 4; §4.1 Table 1.
- Loesch, Hindman, Richardson, Welch, *Impermanent Loss in Uniswap v3*, https://arxiv.org/abs/2111.09192 — Abstract; Introduction p.3; p.25; Conclusion p.37.
- Heimbach, Schertenleib, Wattenhofer, *Risks and Returns of Uniswap V3 Liquidity Providers*, https://arxiv.org/abs/2205.08904 (v2, AFT 2022) — §4.2 eq. 3; §5.3 Figs. 14, 16, 17.
- Fritsch, Canidio, *Measuring Arbitrage Losses and Profitability of AMM Liquidity*, https://arxiv.org/abs/2404.05803 (v2) — §3.1; §3.2 Figs. 1–3; Abstract.
- Cartea, Drissi, Monga, *Decentralised Finance and Automated Market Making: Predictable Loss and Optimal Liquidity Provision*, https://arxiv.org/abs/2309.08431 (v3) — §5.2 Table 2.
- Fritsch, *Concentrated Liquidity in Automated Market Makers*, https://arxiv.org/abs/2110.01368 — read; fee income only (no IL/LVR), not used for numbers.

Via `RESEARCH-2026-09-30-lp-literature.md`, not re-verified: arXiv 2509.23222 (LVR ≈ 0.97 × fees); CrocSwap markout
https://crocswap.medium.com/usage-of-markout-to-calculate-lp-profitability-in-uniswap-v3-e32773b1a88e ; JIT, AFT 2025
https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.AFT.2025.8 .

Not opened (dropped): Capponi & Jia and Wan & Adams on JIT; Uniswap Labs LVR/JIT blog posts; Uniswap v3 launch blog
("4000x").

Repo (paths relative to `samples/strategy-example/` unless absolute):

- `V6_VALIDATION.md` — §2 (plain LP by year), §3 (PBO, DSR), §4 (continuous v6 / plain LP / hold / 50/50), §5 (regimes), §6 (capacity, JIT, MEV), status §1, addendum (EXP-014 attribution).
- `experiments/FINDINGS-2026-10-05.md` (point 1 range harvester; point 2 fee/LVR 3.49 vs 1.23), `experiments/FINDINGS-2026-10-05-round2.md` (v6.75), `experiments/FINDINGS-2026-10-02.md`.
- `experiments/EXP-012-fee-lvr-gate.md` (LVR formula, WBTC median R 3.50), `experiments/EXP-014-perp-delta-hedge.md` (hedge P&L), `experiments/EXP-088-no-new-low-refill.md` (warm-up H5/H4 numbers), `experiments/registry.csv`.
- `v6_validate.py` (result row, `benchmark_return`, `BINANCE_WARM`), `gamma_ig_gap_bands_defense_v6.py` (~l.2212, benchmark series), `remix_dao_utils.py` (`performance_metrics_for_dca`, `benchmark_rate`), `v6_validate_report.py` (`continuous()`, 50/50 definition).
- Run outputs (gitignored, main checkout only), `/Users/dinohuang/Desktop/demeter-momentum/samples/strategy-example/result/v6_validate/`:
  `0x88e6-opt-A-2022-01-01-2026-09-17{.csv,/equity_A_v6.csv,/fees_A_v6.csv,/decomp_daily.csv,/decomp.py}`;
  `0x88e6-opt-AAOAPAQ-{2022..2026}-*{.csv,/equity_A_v6.csv}`; `0x88e6-opt-AAO-2021-05-06-2021-12-31`;
  `0x99ac-opt-AAOAPAQ-2022-11-01-2026-09-17`; `0x99ac-opt-AAO-2022-01-01-2022-10-31` (variant `A_v6` rows).
- Prices: `/Users/dinohuang/Desktop/demeter-momentum/samples/eth_usd_hourly.csv`, `.../samples/binance_daily_closes.csv`.

## Appendix A: v6 vs hold vs 50/50 script

Run with `/Users/dinohuang/Desktop/demeter-momentum/.venv-lab/bin/python` (read-only; output = the table in §2.2).

```python
# v6 vs 100% hold vs 50/50 (buy-and-hold and daily-rebalanced), from saved daily equity; no new backtest.
import numpy as np, pandas as pd
R = "/Users/dinohuang/Desktop/demeter-momentum/samples/strategy-example/result/v6_validate"
S = "/Users/dinohuang/Desktop/demeter-momentum/samples"
INIT = 100_000.0
eth_h = pd.read_csv(f"{S}/eth_usd_hourly.csv", parse_dates=["timestamp"]).set_index("timestamp")["usd"].sort_index()
btc_d = pd.read_csv(f"{S}/binance_daily_closes.csv", parse_dates=["date"]).set_index("date")["BTCUSDT"]

def price_path(asset, start, end):
    """Entry price at the window's first instant, then one close per calendar day."""
    if asset == "ETH":
        entry = eth_h.loc[start:].iloc[0]                                   # 00:00 UTC of the start day
        daily = eth_h.loc[start:end + " 23:59"].resample("1D").last()
    else:
        entry = btc_d.loc[:pd.Timestamp(start) - pd.Timedelta(days=1)].iloc[-1]   # prior day's close = start open
        daily = btc_d.loc[start:end]
    return entry, daily

def stats(nv):
    nv = nv.dropna(); yrs = (nv.index[-1] - nv.index[0]).days / 365.0
    tot = nv.iloc[-1] / nv.iloc[0] - 1; cagr = (1 + tot) ** (1 / yrs) - 1
    mdd = (nv / nv.cummax() - 1).min(); r = nv.pct_change().dropna()
    sharpe = r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else np.nan
    return dict(total=tot, cagr=cagr, mdd=mdd, calmar=cagr / abs(mdd), sharpe=sharpe)

def window(tag, asset, start, end):
    eq = pd.read_csv(f"{R}/{tag}/equity_A_v6.csv", index_col=0, parse_dates=True)["net_value"]
    entry, px = price_path(asset, start, end)
    t0 = pd.Timestamp(start) - pd.Timedelta(days=1)                         # synthetic "open" point
    px = pd.concat([pd.Series([entry], index=[t0]), px]).loc[:end]
    v6 = pd.concat([pd.Series([INIT], index=[t0]), eq]).reindex(px.index).ffill()
    hold = INIT * px / entry
    bh5050 = INIT * 0.5 + INIT * 0.5 * px / entry                           # 50/50 bought once, never rebalanced
    rb = pd.Series(INIT * np.cumprod(np.r_[1, 1 + 0.5 * px.pct_change().dropna().values]), index=px.index)  # daily rebal, no costs
    rows = {k: stats(v) for k, v in [("v6", v6), ("hold 100%", hold), ("50/50 buy&hold", bh5050), ("50/50 daily rebal", rb)]}
    print(f"\n== {asset} {start}..{end}  ({tag}) ==")
    print(pd.DataFrame(rows).T.round(3).to_string())

window("0x88e6-opt-A-2022-01-01-2026-09-17", "ETH", "2022-01-01", "2026-09-17")
for y, e in [(2022, "12-31"), (2023, "12-31"), (2024, "12-31"), (2025, "12-31"), (2026, "09-17")]:
    window(f"0x88e6-opt-AAOAPAQ-{y}-01-01-{y}-{e}", "ETH", f"{y}-01-01", f"{y}-{e}")
window("0x88e6-opt-AAO-2021-05-06-2021-12-31", "ETH", "2021-05-06", "2021-12-31")
window("0x99ac-opt-AAOAPAQ-2022-11-01-2026-09-17", "BTC", "2022-11-01", "2026-09-17")
window("0x99ac-opt-AAO-2022-01-01-2022-10-31", "BTC", "2022-01-01", "2022-10-31")
```

## Appendix B: decomposition check and exposure

```python
import pandas as pd
D = ".../result/v6_validate/0x88e6-opt-A-2022-01-01-2026-09-17"
d = pd.read_csv(f"{D}/decomp_daily.csv", index_col=0, parse_dates=True)
print(d[["dnv", "fee", "delta", "swap", "rest"]].sum())          # 84775 / 86448 / 104762 / -3948 / -102487
f = pd.read_csv(f"{D}/fees_A_v6.csv", parse_dates=["date"]).set_index("date"); f.index -= pd.Timedelta(days=1)
f["nv"] = f.lp_value + f.free_base * f.price + f.free_quote
f["expo"] = (f.lp_base + f.free_base) * f.price / f.nv
d["expo_prev"] = f.expo.shift(1).reindex(d.index)
g = d.groupby(["trend", "vol"])
print(g[["dnv", "fee", "delta", "swap", "rest"]].sum().assign(days=g.size(), expo=g.expo_prev.mean()))
```
