# EXP-015: fee tier — v6 on the Base WETH/USDC 0.3% pool, and a 0.05% / 0.3% rotation estimate (v6.12)

- Version: v6.12 (deployment choice: which Base pool the unchanged v6 runs in)
- Jira: [QUAN-861](https://ewetechnology.atlassian.net/browse/QUAN-861)
- Status: fail (rule 1: 0.05% tier confirmed; rule 2: rotation not worth it)
- Pre-registration commit: 599f492 · Result commit: ______
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

Pool statistics, Base WETH/USDC (minute data; virtual reserve proxy = 2 L √P of the active liquidity):

| pool | year | median active L | virtual reserve proxy | daily volume | swaps/day | pool fees/yr | fee per unit L |
|---|---|---|---|---|---|---|---|
| 0.05% | 2024 | 2.5e18 | $257M | $48.5M | 1,371 | $8.9M | 1.53e-8 |
| 0.05% | 2025 | 2.8e18 | $290M | $71.7M | 1,439 | $13.1M | 1.68e-8 |
| 0.05% | 2026 | 1.2e18 | $106M | $24.2M | 1,426 | $3.1M | 1.17e-8 |
| 0.3% | 2024 | 2.4e16 | $2.6M | $0.4M | 243 | $0.46M | 1.78e-8 |
| 0.3% | 2025 | 8.4e17 | $89M | $4.9M | 448 | $5.3M | 1.95e-8 |
| 0.3% | 2026 | 2.7e19 | $2.4B | $62.8M | 1,052 | $49.0M | 1.21e-8 |

The 0.3% pool was a ~$3M pool in 2024 (a $100k ±20% ladder would have been several times its active liquidity),
grew through 2025 (a $100k ladder ≈ 1.2% of active liquidity in 2025-06 vs 0.3% in the 0.05% pool) and became
Base's main WETH/USDC pool in 2026 (10x the 0.05% pool's active liquidity, 2.6x its volume). Fee income per unit of
in-range liquidity is the same on both tiers within noise: median ratio 1.1x, the 0.3% pool higher on 61% of days,
never 1.5x apart (0.3% of days) — the 6x fee is paid on 1/6 of the volume per unit of liquidity.

v6 (A) and v6.4 (E, Base Aave rates) on both pools, yearly reset, 100,000 USDC:

| segment | v6 0.05% | v6 0.3% | gain | max DD 0.05% → 0.3% | fees 0.05% → 0.3% | impact 0.05% → 0.3% | v6.4 0.05% → 0.3% |
|---|---|---|---|---|---|---|---|
| 2024 | +19.4% | (−100.7%) | invalid | 30.3% → (224%) | $17.6k → $6.4k | $3.6k → $110.6k | +21.3% → (−99.2%) |
| 2025 | +13.9% | +9.9% | −4.0 | 24.4% → 24.4% | $18.2k → $16.5k | $0.3k → $2.0k | +16.2% → +12.2% |
| 2026-01..09-17 | +19.1% | +18.2% | −0.9 | 11.9% → 11.7% | $6.6k → $6.5k | $0.06k → $0.02k | +20.2% → +19.3% |

2024 on the 0.3% pool is outside the model: v6's rebuild swaps (up to $83k each) exceed the pool's virtual reserve,
the quadratic impact ledger charges $110.6k on $843k of notional and the equity goes negative; the fee-share model
(L_ours / L_pool with our L several times L_pool) is equally meaningless there. The row is kept as the capacity
finding it is, not as a return. Chained 2025-01-01..2026-09-17 (yearly-reset runs, daily equity): v6 on 0.05%
+34.5%, CAGR 18.9%, max DD −21.2%, Sharpe 0.79, Calmar 0.89; on 0.3% +30.0%, 16.6%, −22.0%, 0.71, 0.76. The
continuous 2024..2026 run on the 0.3% pool is unusable for the same reason (the 2024 leg drives its equity negative).

Rule 1 — **0.05% tier confirmed**: 0 of 3 yearly wins for the 0.3% pool (2024 invalid, 2025 −4.0, 2026 −0.9) and a
lower Calmar over the usable window (0.76 vs 0.89). Same fee income per unit of liquidity, but every rebuild swap
pays 6x the fee plus the thinner pool's impact ($2.0k vs $0.3k in 2025 — about 2 pts of the 4-pt gap). In 2026, with
the 0.3% pool now the deeper one, the gap closes to −0.9 pts: if Base liquidity keeps migrating to the 0.3% tier the
answer may flip, so this is "confirmed for now", to be re-checked on the go-live pool data.

Rule 2 — **not worth it**: with the 1.5x hysteresis the trailing fee densities never trigger a switch (0 switches in
2025–26), so the rotation degenerates into holding the 0.05% pool; the estimate's +31.8% vs +34.5% is a calendar
alignment artefact of the offline method (the 0.3% data has fewer days), not a cost. A rotation only pays when the
tiers' fee density diverges, and on Base they track each other.

## Deviations

- The 0.3% pool's minute data (2024-01-01..2026-09-17, 991 days) was fetched with `fetch_base_monthly.sh` after the
  pre-registration commit, via developer-access-mainnet.base.org, no failed months.
- Rule 2 as pre-registered would use the continuous 2024..2026 runs; the 0.3% pool's continuous equity is invalid
  (above), so the estimate uses the 2025 and 2026 yearly-reset runs chained, with the impact rate per unit of notional
  taken from those two runs. The fee-density signal is computed over the same window.
- No strategy code changed for this experiment; `v6_validate.py` gained the 0.3% pool entry (tick spacing 60, WETH as
  token0, EMA warm-up on mainnet).
