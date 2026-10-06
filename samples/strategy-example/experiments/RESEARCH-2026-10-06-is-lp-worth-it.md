# Research: is AMM liquidity provision worth doing, or is holding spot better? (2026-10-06)

Question from Dino: "研究一下amm到底值不值得做，會不會單純持有現貨更好". This note extends
`RESEARCH-2026-10-05-lp-vs-hold.md` (the 10-05 note) and `RESEARCH-2026-09-30-lp-literature.md` (the 09-30 note). It
does not repeat them. It adds:

- 2024–2026 measurements (Uniswap v2/v3/v4 markouts on Ethereum, Arbitrum and Base, 2025);
- mechanisms that could change the answer (v4 dynamic fees, am-AMM, CoW AMM, MEV taxes, JIT);
- where LPs structurally win, and the cost side for a small or medium book;
- a verdict: LP vs 100% coin vs 50/50 hold, and where v6 sits.

No new backtest. Evidence grades as in the 10-05 note: **A** paper with numbers, **B** practitioner or vendor data,
**R** this repo's runs (backtests, in-sample unless said). "Fetched" means the primary page was opened this session.
Most papers were read through a page-summarising fetch, not line by line (see Sources). Claims seen only in a search
snippet are marked **unverified**.

## What the earlier notes already establish (one line each)

| claim | where | grade |
|---|---|---|
| A v3 position is short volatility: it sells the coin as the price rises and buys it as the price falls | 10-05 §1.1 (v3 whitepaper §2, §6.4.1) | A |
| The right benchmark is LVR. LP P&L = rebalancing P&L + fees − LVR; LVR = σ²/8 of pool value per unit time for constant product; >99.99% of LP P&L variance is market risk | 10-05 §1.2 (Milionis et al. 2208.06046) | A |
| 2021: fees $199.3m vs IL $260.1m on 17 v3 pools; about half of LPs lost vs HODL | 10-05 §1.3 (Loesch et al. 2111.09192) | A |
| 2022–23: fees ≈ 80% of arbitrage losses on WETH-USDC 0.05%; WBTC-USDC 0.3% about break-even; smaller pairs up to +50% | 10-05 §1.4 (Fritsch & Canidio 2404.05803) | A |
| Repo: the plain ±20% LP on ETH 0.05% made −24.6% (2022-01..2026-09), vs 50/50 −17.5% and ETH −35.0%; on WBTC 0.3% the plain LP ≈ v6 | 10-05 §2.1, `V6_VALIDATION.md` §4 | R |
| v6's money is exposure timing (delta +$104.8k); its LP leg is −$20k..+$14k on $100k over 4.7 years, i.e. about zero | 10-05 §2.3, EXP-014 | R |
| v6 beats 100% ETH in falls and chop and lags in rallies (2023 +32% vs +90%; BTC 2022-11..2026-09 +85% vs +273%) | 10-05 §2.2 | R |
| Mainnet gas $61k for 147 rebuilds; fee share overstated 7% at $10M; price impact ~23% of AUM a year at $10M | `V6_VALIDATION.md` §4, §6 | R |
| Weak statistics: PBO 0.56, deflated Sharpe < 0.95 | `V6_VALIDATION.md` §3 | R |

## Short answer

- **For a passive LP on the big ETH and BTC concentrated pools, it is not worth it compared with holding the same
  coins.** The newest and largest measurement is Uniswap Labs / Columbia, Feb–Nov 2025. Passive v3 LPs in the 5 bp
  WETH-stable pools lost:

  | chain | passive markout (bps of volume) |
  |---|---|
  | Ethereum | −1.51 |
  | Arbitrum | −0.77 |
  | Base | −0.71 |

  In v4, Ethereum 5 bp USDC-WETH was −3.07 bps. The only clearly positive pools were Uniswap **v2** at 30 bp (+9.3 to
  +21.5 bps) and a few v3 30 bp pools (Sadeghi et al. 2026, Tables 2–4). Fees still roughly equal LVR (0.8–1.0×) on
  the 5 bp ETH pool (Bichuch & Feinstein 2025; Fritsch & Canidio 2024). On Base, retail concentrated WETH/USD LPs
  mostly lost: only 15.7% of 32,816 had positive P&L (Urusov et al. 2026).
- **LP pays only where fees per unit of LVR are high.** That means a higher fee tier, full-range or wide positions,
  faster blocks (L2), and lower volatility (stable or correlated pairs). Even there, the edge is a few basis points of
  volume, i.e. a few percent a year. That is small next to the coin's own move, which the LP gives away in a rally.
- **Against 100% spot the question is mostly about direction, not AMMs.** An LP is a roughly half-long, short-volatility
  position: it beats the coin in falls and loses in rallies (10-05 §1.3, §2.2). If you want coin upside, hold the coin.
- **The protocol fixes for LVR do not help today's passive Uniswap v3 LP.** v4 dynamic fees, am-AMM, CoW AMM batch
  auctions and MEV taxes are either theory or simulation, or have only vendor-reported, small-pool numbers. JIT takes
  < 2% of fees on the 5 bp ETH pool, so it is not the main problem.
- **v6 is not an LP-income product.** Its LP leg nets about zero on ETH 0.05%; its return is timing of ETH exposure.
  Its LP vehicle is worth keeping only where the pool's fee/LVR is high: in the repo's scans the 0.3% tiers (WBTC
  2.54, Base WETH 2.53, mainnet WETH 1.70) vs 0.75 on the 5 bp ETH pool (EXP-117). That matches round 4's
  routing/tier findings.

## 1. New measurements, 2024–2026

### 1.1 Uniswap v2/v3/v4 markouts by chain and tier, 2025 (A)

Sadeghi, Liu, Moallemi, Wan, Zhu, *Not All LPs Are Equal: The Active-Passive Gap in AMM Liquidity Provision*,
arXiv 2609.37963v1 (2026-09-29).

Method:
- Data: 2025-02-01..2025-11-30 (§3.2), Ethereum, Arbitrum and Base. Pools are WETH, WBTC or cbBTC against USDC or
  USDT, with ≥ $10M volume.
- Metric: LP markout at a **15-second horizon**, fees included, **gas excluded**, in bps of volume (§4.2).
- "Passive" is what is left after LIFO-matching mint/burn pairs within 20 s. An "infinitesimal" full-range LP is a
  second estimate.

Rows that matter for v6, as overall / passive LIFO in bps (Tables 2–4; fetched, every row listed):

| version, pool | Ethereum | Arbitrum | Base |
|---|---|---|---|
| v2 USDC-WETH 30 bp | +9.32 / +9.32 | +19.15 / +19.15 | +20.82 / +20.82 |
| v3 USDC-WETH 5 bp | −1.15 / **−1.51** | −0.73 / −0.77 | −0.68 / −0.71 |
| v3 USDC-WETH 30 bp | −0.71 / −0.87 | — | — |
| v3 USDT-WETH 30 bp | +1.19 / +1.00 | — | — |
| v3 USDC-WBTC 5 bp | +0.05 / −0.41 | −0.59 / −0.59 | (USDC-cbBTC) −0.57 / −0.57 |
| v3 USDC-WBTC 30 bp | +0.52 / +0.21 | — | — |
| v3 USDT-WBTC 30 bp | +2.71 / +2.52 | — | — |
| v4 USDC-WETH 5 bp | −3.03 / −3.07 | −1.43 / −1.43 | −0.98 / −0.98 |
| v4 USDC-WBTC 30 bp | −2.00 / −2.02 | — | — |

Reading:
- In concentrated pools (v3/v4) passive LPs earned fees slightly below what informed flow took, on every chain at
  5 bp. Total markout on Ethereum v3 USDC-WETH 5 bp was −$5.39m over ten months (Table 3).
- Full-range v2 at 30 bp was positive on all three chains.
- 30 bp beat 5 bp for passive LPs in most v3 pairs. The paper says "high-fee pools are generally better for passive
  LPs" (§5.2), but v4 30 bp ETH/BTC pools were negative.
- The passive vs active gap "is larger and more dispersed on Ethereum than on Arbitrum and Base" (§5.2). On L2s the
  5 bp loss is about half Ethereum's.
- Limits:
  - A 15-second markout measures adverse selection per trade. It is not a holding-period P&L vs HODL, and the paper
    reports no HODL comparison.
  - Many 30 bp confidence intervals straddle zero (e.g. v3 USDC-WBTC 30 bp passive CI [−1.40, +1.82]).
  - Converting bps of volume into an annual return needs volume/TVL, which this note did not take from the paper.
- Disagreement with the repo: the repo's fee/LVR scan has mainnet USDC/WETH 0.3% (`8ad5`) at 2.24 in 2025
  (`EXP-117-lp-03-swap-005.md`). The markout above is −0.87 bp. The repo ratio uses minute closes and the LP's own
  in-range liquidity, so it is an upper bound (10-05 §2.1). The ranking (0.3% > 0.05%) agrees. The sign for
  mainnet ETH 0.3% does not, and the markout CI [−2.63, +0.90] includes zero.

### 1.2 Fees vs LVR, 2023–24 (A)

- Bichuch & Feinstein, *The Price of Liquidity: Implied Volatility of AMM Fees*, arXiv 2509.23222, §2. On WETH/USDC v3
  5 bp, 2023–2024, rolling 30-day windows, "realized LVR is approximately 2.94% lower than the realized fees (i.e.,
  LVR ≈ 0.9706 × fees)". This confirms the 09-30 note's line, which had not been re-verified. Fees and LVR are 90%
  correlated: from the fetch summary, not checked separately.
- Together with Fritsch & Canidio (fees ≈ 0.8 × losses, 2022–23) and Sadeghi et al. (passive −1.5 bp, 2025), three
  methods over 2022–2025 put the 5 bp ETH pool's LP at **break-even to slightly negative before gas**.

### 1.3 Gross fee yield by chain is not net return (A)

Gogol, Schneider, Tessone, Livshits, *Liquidity Fragmentation or Optimization? Analyzing AMMs Across Ethereum and
Rollups*, arXiv 2410.10324, Table 2. Annualised WETH-USDC LP fee return as of 2024-04-30:

| chain | fee return |
|---|---|
| Ethereum | 3.03% |
| Arbitrum | 13.43% |
| Base | 17.16% |
| ZKsync | 16.72% |
| Optimism | 22.12% |

- These are **fees ÷ TVL, gross**. IL and LVR are not subtracted (the paper only says they should be).
- Mainnet LPs "often yield lower returns than staking Ether" (3.47%).
- The 09-30 note's numbers are confirmed, with this caveat: a high L2 fee APR is not evidence of profit. Sadeghi et
  al. show the same L2 5 bp pools at negative markout in 2025.

### 1.4 Retail LPs on Base (A)

Urusov, Berezovskiy, Krestenko, Kornilov, *Liquidity provision in CLMMs: evidence from transactions data*, arXiv
2604.22069 (abstract and HTML fetched):

- Base, 2024-09..2025-07, WETH/USD pools on Uniswap v3, Aerodrome Slipstream, PancakeSwap v3 and SushiSwap v3; 32,816 LPs.
- **15.7% (5,155) end with positive P&L** ("one out of six avoids losses").
- P&L is the change in USD value, gas not modelled, so this is **not vs HODL**. In a falling ETH window it mixes the
  price move with LP skill.
- Profitable LPs closed early, having crossed about 8% of their range, and had minted near the middle of the range.

### 1.5 Block time (A, theory + simulation)

- Milionis, Moallemi, Roughgarden, arXiv 2305.14604 (v2):
  - Theorem 3: in the fast-block limit, arbitrage profit is proportional to √(mean inter-block time).
  - Table 1 (σ = 5%/day), probability that a block has an arbitrage trade:

    | fee | 12 s | 2 s | 50 ms |
    |---|---|---|---|
    | 5 bp | 45.6% | 25.4% | 5.1% |
    | 30 bp | 12.3% | 5.4% | 0.9% |

  - A 2 s chain such as Base roughly halves arbitrage frequency at 5 bp.
- Fritsch & Canidio, arXiv 2404.05803 §4.2, Figs. 4–5: 100 ms blocks would cut arbitrage losses by 20–70% vs 12 s,
  depending on the pair (Binance perps, 2023-06..11).
- Sadeghi et al. agree in direction: L2 5 bp passive markouts are about half Ethereum's, but still negative.

## 2. Mechanisms that could change the answer

| mechanism | what it does | evidence on LP outcomes | grade |
|---|---|---|---|
| Uniswap v4 dynamic fees | A hook may set the LP fee per swap (`beforeSwap` override flag) or periodically (`updateDynamicLPFee`); dynamic or not is fixed at pool creation (v4 docs; `LPFeeLibrary.sol`: `DYNAMIC_FEE_FLAG = 0x800000`, `MAX_LP_FEE = 1000000`) | No on-chain measurement found. Campbell, Bergault, Milionis, Nutz, arXiv 2508.08152 (simulation calibrated to Binance/Uniswap): optimal fees are "remarkably stable" in normal markets, higher in high volatility; a threshold dynamic fee "improves LP outcomes". The docs only say "potentially improving" | A (sim), docs |
| am-AMM (auction-managed AMM) | A Harberger-lease auction sells the pool-manager role. The manager sets the fee, arbitrages at zero fee and pays rent to LPs (Adams, Moallemi, Reynolds, Robinson, arXiv 2403.03367) | Theorem 1: an equilibrium exists in which the am-AMM has more liquidity than any fixed-fee AMM. **Theory only**, no data. Deployed in Bunni v2 (docs list it, no performance data). Bunni's 2025-09 exploit and shutdown is from news, **unverified** | A (theory) |
| CoW AMM / FM-AMM (batch trading) | Trades clear in batches at one price, so arbitrageurs compete away LVR and sandwiching (Canidio & Fritsch, arXiv 2307.02074) | Paper backtest on 11 pairs: LP returns "for the most part, slightly higher than" v3. Live numbers are **vendor-reported** (CoW forum, 2024-05): COW/WETH +6.1%, USDC/WETH +0.7% vs a Balancer benchmark (the author says this overstates). 2025-09 forum: "equally or better" than comparable v2 pools at much smaller TVL. Landing-page figures ("$1.2M surplus", "10 of 11 pairs") **unverified** | A (backtest), B |
| MEV taxes | Under priority ordering (OP Stack: Base, OP Mainnet), the app charges a fee proportional to the priority fee, capturing about 99% of competitive MEV, with an AMM variant (Robinson & White, Paradigm, 2024-06) | No data. Not applicable to L1 builder auctions | theory |
| Angstrom (Sorella), Diamond | App-specific sequencing, batched into one tx on v4 (Angstrom docs). Block producers bid for the arbitrage right and part is rebated to the pool (Diamond, McMenamin, Daza, Mazorra, arXiv 2210.10601) | No LVR or LP data on the docs page; Diamond is simulation only | docs, A (sim) |
| JIT liquidity (threat) | A same-block mint/burn around a large swap takes its fees | Observed on 0x88e6 (5 bp), 2024-01..06: JIT LPs took **< 2% of total fees** (Llacer Trotti et al., AFT 2025, §6.1.3). The "up to 44% per trade" is the paper's **simulation** of optimised JIT with a large budget, not observed (correction to the 09-30 note's phrasing). 2021-05..2022-07: JIT filled ~0.3% of v3 volume (Wan & Adams, Uniswap Labs blog) | A, B |

Reading: none of these is something a passive LP on a standard v3 pool can use today with measured benefit. The
designs that would recapture LVR (am-AMM, batch auctions, MEV taxes) live in their own pools. Those pools have small
liquidity and little independent data, and one prominent deployment (Bunni) is reported shut after an exploit
(unverified). For v6 they are a venue question for later, not a reason to change the verdict.

## 3. Where LPs structurally win

1. **Higher fee tier, at least for passive liquidity.**
   - Fee income from arbitrage ≈ LVR × (1 − P_trade), and P_trade falls with the fee (Milionis et al. 2305.14604,
     Theorem 4, Table 1).
   - Measured: 30 bp > 5 bp for passive LPs in most v3 pairs (Sadeghi et al. §5.2). Fritsch & Canidio: WBTC-USDC 0.3%
     about break-even vs WETH-USDC 0.05% at 0.8.
   - Lehar, Parlour, Zoican, arXiv 2307.13772: high-fee pools hold 58% of liquidity but execute 21% of volume. Small
     LPs choose high-fee pools to avoid adverse selection, large LPs sit in low-fee pools and rebalance often. (A)
   - Repo: fee/LVR 2.54 (WBTC 0.3%), 2.53 (Base WETH 0.3%), 1.70 (mainnet WETH 0.3%), 1.13 (Base WETH 0.05%) vs
     0.75 (mainnet WETH 0.05%) (`EXP-117-lp-03-swap-005.md`). The plain LP on WBTC 0.3% ≈ v6 (10-05 §2.1). (R)
2. **Wide or full range.**
   - v2 30 bp markouts are +9 to +21 bps on every chain in 2025 (Sadeghi et al. Table 2). Fritsch & Canidio report
     v2 fees about 3× losses in 2023 (Fig. 3).
   - Concentration raises fees and LVR per dollar together. Heimbach et al. (10-05 §1.3) show IL grows faster with
     concentration. (A)
3. **Low volatility relative to the fee: stable and correlated pairs.**
   - LVR scales with σ² (10-05 §1.2).
   - Curve StableSwap (Egorov 2019, pp. 1–3) concentrates liquidity around 1:1; amplification A = 100 is "comparable
     to using Uniswap with 100x leverage". Its "300% APR" is a 2019 simulation, not data.
   - Repo: a USDC/USDT 0.01% ±0.1% LP earned 0.9–6.4% a year, 2021–2026 (`EXP-052-stable-lp-reserve.md`, Deviations).
     It is the reserve's yield, not a coin strategy, and does not count as an improvement (CLAUDE.md ruling). (A, R)
4. **Uninformed (retail) flow.**
   - The gap between total and passive markout comes from who trades against whom (Sadeghi et al.).
   - No primary source quantifying LP P&L by router or flow origin was found. Barbon & Ranaldo and Capponi & Jia are
     **unverified** (snippets only). Not usable yet.
5. **Emission-subsidised DEXes (Aerodrome / Velodrome, ve(3,3)).**
   - Per the Aerodrome contracts specification, LPs who stake their position "forgo their fee reward in exchange for
     a proportional distribution of emissions". The fees go to the voters of that pool, paid the next weekly epoch.
   - Slipstream (concentrated) pays gauge emissions only to in-range (active-tick) liquidity and charges unstaked LPs
     an unstaked-liquidity fee (default 10%, max 50%) (Slipstream specification).
   - So the staked LP's income is **AERO emissions, a subsidy paid in a token with its own price risk, not a trading
     edge**. The position still carries the LVR of the WETH/USD pool.
   - No primary study separates Aerodrome emissions from fee P&L. The "one in six" Base result (§1.4) includes
     Slipstream LPs.
   - Liquidity-mining evidence elsewhere is vendor-reported. Gauntlet on Uniswap's Arbitrum programme: 1.8M ARB, $725k
     LP revenue during and $114k after, TVL $9.11 per $1 during and $5.99 after. No net-of-LVR result. (B)
   - Under the repo's rules an emission yield is income on top of the ladder, like idle-capital yield. It is not a
     strategy improvement. (docs, B)

## 4. Costs for a small or medium book (repo numbers, R)

- **Gas.** Mainnet $61k for 147 rebuilds × 16 positions over 4.7 years (`V6_VALIDATION.md` §4).
  - This note's arithmetic: about $13k a year, i.e. 13% of AUM a year at $100k, 1.3% at $1M and 0.13% at $10M, against
    a LP leg worth about zero (10-05 §2.3).
  - On mainnet, an actively rebuilt ladder is not viable below about $1M.
  - On L2 the gas term is far smaller. Base rebuild price impact was $3.6k in 2024, $0.3k in 2025 and $0.06k in 2026
    per $100k (`V6_VALIDATION.md` status §1). This note did not verify a current Base gas price from a primary source.
- **Capacity.**
  - Rebuild price impact: 0.23% of AUM a year at $100k, ~2.3% at $1M, ~23% at $10M (no routing).
  - Fee share overstated by 0.7% at $1M, 7% at $10M and 36% at $50M (`V6_VALIDATION.md` §6).
  - The cheap window is therefore about $0.25M–$1M on mainnet (gas falls, impact rises) and lower bounds on L2.
    Spot holding has none of these costs beyond one entry trade.
- **Swap fees and rebuild tier.** WBTC 0.3% rebuild swaps cost ~$8.5k, 14% of its LP fees (`FINDINGS-2026-10-05.md`
  point 2). Routing them through the 0.05% tier is one of the round-4 findings (`FINDINGS-2026-10-06-round4.md`).
- **Operational risk.** Contract and hook risk (the Bunni case above, unverified), MEV on the 00:00 UTC rebuild
  (`V6_VALIDATION.md` §6) and the monitoring burden. Spot holding has only custody risk.

## 5. Verdict: when is LP worth it, vs 100% spot and vs 50/50 hold

| you would otherwise hold | passive LP on 5 bp ETH/BTC concentrated pool | passive LP on 30 bp / wide range / L2 | timed LP (v6) |
|---|---|---|---|
| **100% coin** | Worse in rallies, better in falls. That is direction, not LP edge. Expected edge slightly negative (A: −0.7 to −3 bps of volume, 2025) | Same direction trade-off. Small positive fee edge possible (A: v2 +9 to +21 bps; v3 30 bp mixed) | Lower return in bull runs (R: ~31–36% of the move), far lower drawdown (R: −22.8% vs −74% ETH 2022–26). A risk product, not a coin substitute |
| **50/50 hold** (the LP's natural benchmark) | **Not worth it.** Fees ≈ 0.8–1.0 × LVR (A), passive markout negative on all three chains (A), repo plain LP −24.6% vs 50/50 −17.5% (R) | **Marginally worth it** if fee/LVR is clearly > 1 (repo ≥ ~1.7 on the 0.3% tiers) and gas is small (L2 or size ≥ ~$1M on mainnet). The edge is a few % a year at best | Beats 50/50 on ETH 2022–26 (R: +85% vs −17%), but via timing. Its ETH LP leg is about zero (R) |
| **stablecoins / cash** | Adds coin beta and LVR. Not an income product | Same | v6's intended comparison: a partly invested, defended position (R) |

Conditions under which providing liquidity is worth it, all needed together:

1. You would hold both coins anyway. The LP's benchmark is HODL or rebalancing, not 100% coin.
2. The pool's fee/LVR is clearly above 1: a higher fee tier, a wide range, low σ, or fast blocks.
3. Costs are small relative to AUM: an L2, or a book large enough that gas is negligible but small enough for low
   impact and fee-share dilution.
4. Any emission or idle-capital yield is counted as a subsidy, separately from trading P&L.

**Where v6 sits.** v6's return is a timed coin exposure (10-05 §2.3; EXP-014). The LP is only the vehicle for that
exposure: on the 5 bp ETH pool it earns about as much as it loses to arbitrage, and on the 0.3% WBTC pool it adds a
real but modest fee edge. Two implications for the research programme (suggestions, not run):

- A decomposition test would settle "is the AMM worth it for v6": hold v6's own exposure path (F × ladder delta) as
  spot, with no LP, in the same invocation. If timed spot ≈ v6 on ETH 0.05%, the AMM adds cost and complexity there
  but little return. The 10-05 bracket (−$20k..+$14k) predicts roughly that. Pre-register it as a validation-level
  experiment if Dino wants the number.
- The literature and the repo both point to the pool, not the shape, as what decides the LP leg. This is consistent
  with round 4's surviving findings (0.3% tier, cheap-tier routing). Further LP-mechanics tuning on the 5 bp ETH pool
  should not be expected to produce LP income.

## Caveats

- **Markouts are not holding-period returns.** Sadeghi et al.'s 15-second markouts measure adverse selection per unit
  of volume, gas excluded, with no HODL comparison. Several 30 bp CIs include zero. Turning them into annual
  returns needs volume/TVL, which was not done here.
- **Different benchmarks.** Urusov et al. measure USD P&L, Gogol et al. gross fee yield, Fritsch & Canidio and Bichuch
  & Feinstein fees vs LVR, Loesch et al. vs HODL. They agree on direction, not on a single number.
- **Read through a summariser.** Most papers were read through a fetch that summarises. The Sadeghi et al. table rows
  were extracted twice and agreed with the subagent extraction. Section and figure locations from summaries
  (Fritsch & Canidio Figs., Bichuch & Feinstein §2) were not checked line by line.
- **Vendor data.** CoW AMM and Gauntlet numbers are vendor-reported (B). The CoW landing-page figures and the Bunni
  shutdown are unverified.
- **Repo numbers are in-sample backtests** with gas excluded (10-05 §4, `V6_VALIDATION.md` §3).
- **Not found** (dropped): router- or flow-level LP P&L, Aerodrome emissions vs fee net returns, an empirical LVR
  measurement on L2 pools outside markouts, measured v4 dynamic-fee hook outcomes.

## Bottom line

- Providing liquidity on the big ETH and BTC concentrated pools does not beat simply holding the same coins. In 2025
  passive LPs lost about 0.7–1.5 bps of every dollar traded on v3 5 bp pools (Ethereum worst), and fees only about
  match arbitrage losses.
- It can pay a little on higher-fee or full-range pools, on faster chains, and on low-volatility pairs. The edge is a
  few percent a year, and gas, rebuild costs and size limits eat it quickly for a small book.
- Compared with 100% spot the answer is about direction: an LP sells into rallies. If you want the upside, hold the
  coin.
- Emissions (Aerodrome) and new designs (v4 hooks, am-AMM, CoW AMM) are subsidies or unproven. They do not change
  this today.
- v6 is worth doing only as a timing and risk product: its gain is when it holds ETH, not the LP fees. The AMM earns
  its keep in v6 only on high fee/LVR pools (the 0.3% tiers). A "timed spot" control run would show how much the
  AMM adds on ETH.

## Sources

Primary, fetched this session (arXiv HTML/PDF read via a summarising fetch unless noted):

- Sadeghi, Liu, Moallemi, Wan, Zhu, *Not All LPs Are Equal: The Active-Passive Gap in Automated Market Maker Liquidity Provision*, https://arxiv.org/abs/2609.37963 (v1, HTML https://arxiv.org/html/2609.37963v1) — §3.2, §4.2, §5.2, §6; Tables 2–4 (every row extracted).
- Bichuch, Feinstein, *The Price of Liquidity: Implied Volatility of AMM Fees*, https://arxiv.org/abs/2509.23222 — §2.
- Gogol, Schneider, Tessone, Livshits, *Liquidity Fragmentation or Optimization? Analyzing AMMs Across Ethereum and Rollups*, https://arxiv.org/abs/2410.10324 — Table 2.
- Urusov, Berezovskiy, Krestenko, Kornilov, *Liquidity provision in CLMMs: evidence from transactions data*, https://arxiv.org/abs/2604.22069 — abstract, results.
- Milionis, Moallemi, Roughgarden, *Automated Market Making and Arbitrage Profits in the Presence of Fees*, https://arxiv.org/abs/2305.14604 (v2, PDF text) — Theorems 3, 4; §4.1 Table 1.
- Fritsch, Canidio, *Measuring Arbitrage Losses and Profitability of AMM Liquidity*, https://arxiv.org/abs/2404.05803 — §3.2 Figs. 1–3; §4.2 Figs. 4–5.
- Lehar, Parlour, Zoican, *Fragmentation and optimal liquidity supply on decentralized exchanges*, https://arxiv.org/abs/2307.13772 (v7) — abstract.
- Adams, Moallemi, Reynolds, Robinson, *am-AMM: An Auction-Managed Automated Market Maker*, https://arxiv.org/abs/2403.03367 (PDF text) — Theorem 1, p. 8.
- Canidio, Fritsch, *Arbitrageurs' profits, LVR, and sandwich attacks: batch trading as an AMM design response*, https://arxiv.org/abs/2307.02074 — abstract.
- McMenamin, Daza, Mazorra, *An AMM Minimizing Loss-Versus-Rebalancing* (Diamond), https://arxiv.org/abs/2210.10601 .
- Campbell, Bergault, Milionis, Nutz, *Optimal Fees for Liquidity Provision in AMMs*, https://arxiv.org/abs/2508.08152 — abstract.
- Llacer Trotti, Tang, El-Azouzi, Fanti, Menasché, *Strategic Analysis of Just-In-Time Liquidity Provision in CLMMs*, AFT 2025, https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.AFT.2025.8 (PDF text; also arXiv 2509.16157) — §6, §6.1.3.
- Egorov, *StableSwap – efficient mechanism for Stablecoin liquidity* (2019), https://classic.curve.finance/files/stableswap-paper.pdf — pp. 1–3 (PDF read).
- Uniswap v4 docs, Dynamic fees, https://developers.uniswap.org/docs/protocols/v4/concepts/dynamic-fees ; source https://github.com/Uniswap/v4-core/blob/main/src/libraries/LPFeeLibrary.sol .
- Aerodrome contracts specification, https://raw.githubusercontent.com/aerodrome-finance/contracts/main/SPECIFICATION.md ; Slipstream specification, https://raw.githubusercontent.com/aerodrome-finance/slipstream/main/SPECIFICATION.md .
- Robinson, White, *Priority Is All You Need*, Paradigm, https://www.paradigm.xyz/2024/06/priority-is-all-you-need .
- Angstrom docs, https://docs.angstrom.xyz/l1/core-mechanisms/app-specific-sequencing ; Bunni v2 docs, https://docs.bunni.xyz/docs/v2/overview/ .

Practitioner / vendor (B), fetched:

- Wan, Adams, *JIT Liquidity*, Uniswap Labs blog, https://blog.uniswap.org/jit-liquidity .
- CoW DAO forum, *4 months of CoW AMM*, https://forum.cow.fi/t/4-months-of-cow-amm-what-we-have-learned-and-the-next-steps/2432 .
- Gauntlet, *Results and Analysis: Uniswap Arbitrum Liquidity Mining Program*, https://www.gauntlet.xyz/resources/results-and-analysis-arbitrum-liquidity-mining-program .

Unverified (search snippets or news only; not used for numbers): Bunni exploit / shutdown
(https://coinmarketcap.com/academy/article/bunni-dex-announces-permanent-closure-after-dollar84m-exploit); CoW AMM
landing-page figures (https://cow.fi/cow-amm); Capponi & Jia, arXiv 2103.08842; Barbon & Ranaldo, arXiv 2112.07386;
McAMM, https://ethresear.ch/t/mev-capturing-amm-mcamm/13336 . Dropped: L2 gas comparison from l2fees.info (no date,
Base not listed).

Repo (paths relative to `samples/strategy-example/`):

- `experiments/RESEARCH-2026-10-05-lp-vs-hold.md` (§1.1–1.4, §2.1–2.3, §4), `experiments/RESEARCH-2026-09-30-lp-literature.md`.
- `V6_VALIDATION.md` §3, §4, §6, status §1, addendum.
- `experiments/EXP-117-lp-03-swap-005.md` (fee/LVR by pool and year), `experiments/EXP-052-stable-lp-reserve.md` (stable LP yield),
  `experiments/EXP-011-base-cbbtc.md` (Base cbBTC plain LP vs v6), `experiments/FINDINGS-2026-10-05.md` (point 2),
  `experiments/FINDINGS-2026-10-06-round4.md`.
