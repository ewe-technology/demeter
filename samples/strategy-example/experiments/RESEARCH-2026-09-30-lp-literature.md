# Literature pass: structural optimisation directions for defense v6 (2026-09-30)

Web/literature research done before EXP-012, on request. Ranked by expected impact x testability in demeter
(minute bars, pool swaps only). "Structural" = a new mechanism or information source; "tuning" = moving width,
shape or EMA inside v6's family (rejected, PBO 0.56). Evidence: **A** paper with numbers, **B** practitioner
analysis with data, **C** theory or marketing. v6 weaknesses it is matched against (`../V6_VALIDATION.md`): the
return is 100% fee income; up/low-vol regime −9.2% a year (EMA whipsaw); rallies mostly given up; 147 rebuilds =
$61k mainnet gas.

## 1. Fee-vs-LVR (markout) gate — chosen for EXP-012 (v6.9)

Before deploying F, require that the pool is currently paying LPs: trailing fee income per unit of in-range
liquidity ≥ trailing LVR per unit of liquidity (σ² x position gamma). If not, stay in cash regardless of trend.
Orthogonal to the EMA engine (direction) — this gate answers "is liquidity being paid".

- LVR (loss-versus-rebalancing) is the cost of being the arbitrageur's counterparty: Milionis, Moallemi,
  Roughgarden, Zhang (2022), https://arxiv.org/abs/2208.06046 . For an in-range v3 position with liquidity L the
  instantaneous LVR is σ² L √P / 4 (token1 per unit time).
- CrocSwap markout study: ETH/USDC 0.05% persistently negative, 0.3% about flat.
  https://crocswap.medium.com/usage-of-markout-to-calculate-lp-profitability-in-uniswap-v3-e32773b1a88e (B)
- Falkenstein, ~600 daily observations to 2023-03: fees $199M vs IL $260M; the 0.05% pool loses more.
  https://efalken.substack.com/p/uniswap-lp-profitability (B)
- ±20% band study 2021–2026: a ±20% band needed 22% nominal / 56.6% active-day APR to break even in 2024; the
  predictor of loss is net displacement / vol (ρ 0.83), not vol alone (ρ 0.37) — a vol-only filter is the wrong
  variable, a fee-coverage filter is the right one. https://github.com/claudio1923/uniswap-v3-lp-risk (B)
- Fee-implied vol vs LVR on WETH/USDC 5 bps 2023–24: LVR ≈ 0.97 x fees, 90% correlated — on average fees just cover
  LVR, so the edge is in the dispersion across days, which a gate exploits. https://arxiv.org/abs/2509.23222 (A)
- Testability: easy — fees, active liquidity and realised variance all come from the minute swaps data.

## 2. Partial perp delta hedge (50–70%) of the LP's residual delta

Short ETH-perp against the deployed LP's delta on a band, keep the EMA engine for sizing: turns "long ETH + short
gamma" into "short gamma + fees + funding". LP variance is ~all market exposure (Milionis et al.). Lipton, Lucic,
Sepp (2024) give the unified static (Deribit vanillas) / dynamic (perps) IL hedge and note short perps historically
earn funding, https://arxiv.org/abs/2407.05146 (A). With collateralised hedging the optimal hedge ratio is 50–70%,
not 100%, because of liquidation risk, https://arxiv.org/abs/2603.19716 (A). Elsts: hedge cost ∝ position gamma,
https://atise.medium.com/liquidity-provider-strategies-for-uniswap-v3-dynamic-hedging-9e6858bea8fa (B).
Panoptic / Block Scholes "gamma scalping" numbers are marketing for the long side, not applicable.
Testability: medium — needs Binance/Bybit ETHUSDT 8h funding and mark price (free). Expect DD ↓↓, return depends on
the funding regime. Different from the dropped EXP-001 sleeve: that added delta, this removes it.

## 3. Fee-tier / venue rotation by fee per unit liquidity

Fee tier dominates arb toxicity: ethresear.ch simulation, ETH/USDC — at 5 bps 29.9% of blocks are arbed and LPs
lose 44% of LVR-nominal; at 100 bps 2.0% / 3.8%, https://ethresear.ch/t/cex-dex-arbitrage-transaction-fees-block-times-and-lp-profits/19444 (B).
WETH-USDC LP fee return 2024: mainnet 3.03%, Arbitrum 13.4%, Base 17.2%, Optimism 22.1%,
https://arxiv.org/html/2410.10324v2 (A). Caveat: Base LVR is also the highest (~260 bps/day vs mainnet ~100 on v2
pools, https://dev.to/chainparser/quantifying-lvr-on-uniswap-v2-1k1g ), and only 1 in 6 Base LPs avoids loss,
https://arxiv.org/pdf/2604.22069 (A). EXP-004's own one-day fee-density check found Base 0.05% ≈ mainnet per unit
of liquidity. Testability: medium — new minute data, doubles as a fresh holdout.

## 4. Trend-skewed asymmetric range using the existing EMA sign

Shift the ±20% valley to −15/+25% in an uptrend (mirror in a downtrend) instead of only scaling F. Cartea, Drissi,
Monga, "Predictable Loss and Optimal Liquidity Provision": closed-form skew ρ = ½ + μ/δ; the drift-aware strategy
outperformed average LPs out of sample on ETH/USDC 2021–22, https://arxiv.org/html/2309.08431 (A). Real LP
liquidity surfaces carry a persistent slope component, https://arxiv.org/pdf/2509.05013 (A, descriptive).
Testability: easy; borderline structural (same signal, new control). Fix one skew tied to the engine's states.

## 5. Short-horizon toxicity pause (LP-side analogue of a v4 dynamic fee)

Pull liquidity for N minutes when 2–5 minute |momentum| or realised vol spikes. Empirical dynamic-fee study,
USDC-WETH 5 bps mainnet 2023: a 2-minute momentum fee cut LVR 20% at constant average fee,
https://hackmd.io/@anteroe/BkIbSfwmJx (B). Arrakis hook claims are marketing (C),
https://arrakis.finance/blog/the-amm-renaissance-how-mev-auctions-and-dynamic-fees-prevent-lvr . Every mint/burn
is mainnet gas (v6 already $61k); a lookback/threshold pair invites tuning.

## 6–9. Lower priority

- Vol-scaled rebalance trigger |ln(P/P₀)| > k σ √t: Elsts,
  https://atise.medium.com/liquidity-provider-strategies-for-uniswap-liquidity-rebalancing-f4430eec63a0 (B/C);
  borderline tuning.
- Options overlay (long straddle / static IL replication): Elsts,
  https://atise.medium.com/liquidity-provider-strategies-for-uniswap-v3-options-ce6748c5b1b4 ; Lipton–Sepp
  https://arxiv.org/abs/2407.05146 . Needs Deribit history (Tardis, paid). Hard.
- Time-of-day / weekday gating: vol peaks 16–17 UTC, https://arxiv.org/pdf/2109.12142 ; network dependent, high
  data-mining risk. Diagnostic only.
- Leverage / LP-NFT collateral: raises gamma and LVR one for one (Elsts on YLDR); expected DD ↑↑. Skip.

## Explicitly not recommended

- Range shape (uniform / gaussian / valley / bimodal): no source shows a fee or PnL advantage of any shape; the
  backtesting-framework paper https://arxiv.org/abs/2410.09983 models the pool's liquidity, not an LP shape
  comparison. Shape change = tuning.
- DVOL-conditioned width: Uniswap-implied vol tracks DVOL (ρ ≈ 0.62, Panoptic https://panoptic.xyz/research/panoptic-solves-lvr );
  still a width rule inside the family = tuning, and off-chain data.
- JIT / intent liquidity: JIT dilutes passive fees up to 44% per affected trade but takes < 2% of total fees
  (AFT 2025, USDC/WETH H1-2024, https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.AFT.2025.8 ); not
  executable by a passive LP. Only action: haircut backtest fees if the engine credits full pool volume.

## Benchmarks

No paper reports Sharpe / CAGR / max DD for a systematic ETH/USDC v3 LP over 2022–2025. Comparators: average LPs
lost money 2021–22 (Cartea et al.), 0.05% pool negative markout 2023 (CrocSwap), mainnet WETH-USDC fee APR 3.03%
in 2024 (arXiv 2410.10324), 1 in 6 Base LPs profitable (arXiv 2604.22069). Against that v6's +85% / −22.8% DD is
unusually good; most of it is the F engine's ETH beta (β 0.22, alpha 12.2%), which is why direction 2 (hedge) is the
key diagnostic of how much is fee alpha.

Other sources read: RvR https://arxiv.org/abs/2410.23404 ; optimal exit time https://arxiv.org/pdf/2509.06510 ;
Elsts on LVR https://atise.medium.com/liquidity-provider-strategies-for-uniswap-v3-loss-versus-rebalancing-lvr-ee0ffdf1f937 ;
Block Scholes x Panoptic https://blockscholesresearch.substack.com/p/block-scholes-x-panoptic-bridging .

| direction | expected effect (return / DD) | structural or tuning | testability | best source |
|---|---|---|---|---|
| 1. fee-vs-LVR gate | return ~flat to +, DD ↓ | structural | easy | CrocSwap markout; claudio1923; arXiv 2509.23222 |
| 2. partial perp delta hedge | return ↓ in bull, DD ↓↓, funding ± | structural | medium | arXiv 2407.05146, 2603.19716 |
| 3. 0.3% / L2 pool rotation | fee return ↑, LVR ↑ on Base | structural | medium | arXiv 2410.10324; ethresear.ch 19444 |
| 4. trend-skewed range | return +, DD ~ | structural (borderline) | easy | arXiv 2309.08431 |
| 5. toxicity pause | LVR −20% claimed, gas cost | structural | easy | hackmd @anteroe |
| 6. vol-scaled trigger | small | borderline tuning | easy | Elsts |
| 7. options overlay | DD ↓, theta cost | structural | hard | arXiv 2407.05146 |
| 8. time-of-day gating | small, mining risk | structural | easy | arXiv 2109.12142 |
| 9. leverage / NFT collateral | return ↑, DD ↑↑ | structural | medium | Elsts (YLDR) |
| shape / DVOL width | unknown | tuning | — | none supports it |
