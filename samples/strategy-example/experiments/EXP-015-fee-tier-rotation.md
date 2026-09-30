# EXP-015: fee tier — v6 on the Base WETH/USDC 0.3% pool, and a 0.05% / 0.3% rotation estimate (v6.12)

- Version: v6.12 (deployment choice: which Base pool the unchanged v6 runs in)
- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Literature: `RESEARCH-2026-09-30-lp-literature.md` §3.

## Hypothesis

v6's return is fee income, and the fee tier decides how much of the pool's volume is toxic: on ETH/USDC the
ethresear.ch CEX–DEX arbitrage simulation has 29.9% of blocks arbed at 5 bps against 2.0% at 100 bps, with LPs
losing 44% vs 3.8% of the arbitrage's LVR-nominal; CrocSwap's markout finds the 0.05% pool negative and the 0.3%
pool about flat; arXiv 2410.10324 finds 2024 WETH-USDC fee returns of 3.0% on mainnet vs 13–22% on rollups.
EXP-004 already ran v6 on the deck's Base 0.05% pool (+55.9% 2024..2026-09 vs ~+86% mainnet: thinner pool, 50x the
price impact) and sampled three days of fee income per unit of liquidity, finding Base 0.3% "no better" — three
days. This experiment runs it properly: the same v6 on the Base 0.3% pool over the same years, then estimates
whether rotating between the two tiers by trailing fee density would have added anything.

Expected: a 6x fee per swap but a fraction of the volume; the open question is fee income per unit of liquidity,
and the rebuild swap costs 6x more. No strong prior.

## Change

None to the strategy for the decisive test. Two pools, same v6 (A) and v6.4 cash yield (E, Base Aave rates), same
years:

- Base WETH/USDC 0.05% `0xd0b53d9277642d899df5c87a3966a349a798f224` (EXP-004's numbers, rerun in the same
  invocation family for identical costs), and
- Base WETH/USDC 0.3% `0x6c561B446416E1A00E8E93E221854d6eA4171372` (factory `getPool(WETH, USDC, 3000)`, resolved
  before this commit; minute data fetched with `samples/fetch_base_monthly.sh` **after** this commit), tick spacing
  60, so the ladder's bands snap to 60-tick multiples.

Rotation estimate (reported, not deciding — demeter runs one pool per backtest, so the rotation is computed offline
from the two runs): daily fee income per unit of in-range liquidity per pool (`fee_lvr_ratio`'s numerator, same
formula both pools), trailing 7 days; hold the pool with the higher density, switch only when the other pool's
density is ≥ 1.5x the current one's (one hysteresis constant); the rotation's daily return is the chosen pool's v6
daily equity return, and every switch charges one full rebuild swap at the destination pool: s × F × equity ×
(pool fee + the destination pool's price impact from the runs' impact-per-notional).

## Pre-registration

- Data: Base 0.3% pool minute data 2024-01-01..2026-09-17 (or from the pool's first swap if later), 100,000 USDC,
  yearly segments 2024, 2025, 2026-01-01..09-17 and the continuous 2024-01-01..2026-09-17 run, EMA warm-up on
  mainnet ETH/USD as for the 0.05% pool. The 0.05% pool is rerun in the same invocation family.
- Rule 1 (fee tier, decisive): v6 on 0.3% beats v6 on 0.05% if continuous Calmar is higher **and** yearly return
  wins in ≥ 2 of 3 segments → "0.3% tier preferred", else "0.05% tier confirmed".
- Rule 2 (rotation, reported): the rotation estimate's continuous total return and Calmar against the better single
  pool; ≥ +2 pts total and Calmar not lower → "worth a real two-pool implementation", else "not worth it".
- This experiment has no holdout of its own: both Base pools are the deployment target and the 0.3% pool is data
  no test has seen.

## Result

Verdict:

## Deviations

None yet.
