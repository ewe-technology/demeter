# EXP-117: LP in the 0.3% fee tier, rebuild swaps routed through the 0.05% tier (v6.104)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: Dino, 2026-10-05: "算，開始下載資料並寫 pre-registration" — moving the liquidity to another pool and routing the
  rebuild swap through a cheaper pool counts as a strategy change (it changes where the ETH/BTC liquidity is placed).
  Number EXP-117 / v6.104 and OPT key `DD` reserved with the goal3 session.

## Hypothesis

v6's LP leg does not pay on the ETH pool: on ETH/USDC 0.05% mainnet 2022-01..2026-09 the ladder earned fees +$86.4k against
IL/gamma −$102.5k and swap costs −$3.9k; the whole return is exposure timing (+$104.8k delta P&L)
(`RESEARCH-2026-10-05-lp-vs-hold.md` §2.3, `decomp_daily.csv`). An LP earns where fees per unit of LVR are high, and that
ratio is a property of the pool, not of the band shape (Milionis et al. 2022; Fritsch & Canidio 2024, cited in the research
note). Per-pool scan with `fee_lvr_ratio`'s formula (`result/fee_lvr_scan/`, sums over each pool's data):

| pool | fee/LVR (all days) | trailing 7-day median |
|---|---|---|
| WBTC/USDC 0.3% mainnet (`99ac`) | 2.54 | 3.13 |
| WETH/USDC 0.3% Base (`6c56`) | 2.53 | 2.89 |
| WETH/USDC 0.05% Base (`d0b5`) | 1.13 | 1.14 |
| WETH/USDC 0.05% mainnet (`88e6`, v6's ETH pool) | 0.75 | 1.19 |
| USDC/WETH 0.3% mainnet (`8ad5`, this variant's ETH pool; scanned after the download, before any backtest) | 1.70 | 2.76 |

Mainnet `8ad5` vs `88e6` by year: 2021 1.83 vs 0.38, 2022 1.15 vs 0.72, 2023 2.57 vs 1.39, 2024 2.31 vs 1.11, 2025 2.24 vs
1.06, 2026 2.39 vs 1.04; over the dev window 2022-01..2026-09 1.66 vs 0.92. These are pool statistics (no strategy run).

On the same ETH/USD price path the 0.3% tier has about twice the fee/LVR of the 0.05% tier: fees per unit of liquidity are
the same within noise (EXP-015), but the 0.3% pool's price moves less (arbitrage only pays beyond the fee), so its LPs lose
less to LVR. EXP-015 found v6 worse on Base 0.3% for a different reason: every rebuild swap paid 6x the fee in a pool that
was thin in 2024–25 (2025: −4.0 pts, about 2 pts of it swap fee and impact). Routing the rebuild swaps through the 0.05%
tier removes that cost and keeps the 0.3% tier's lower LVR. Expected: ETH CAGR up (lower IL for similar fees); WBTC up a
little (its LP already sits in the 0.3% tier; the swap bill, ~$8.5k of pool fee on $2.8M of swaps, 14% of its LP fees per
`FINDINGS-2026-10-05.md`, falls by about two thirds).

## Change

Variant `DD` (`SWAP_ROUTE`), one rule for both assets: **the ladder lives in the pair's 0.3% pool; every swap the strategy
makes (rebuild, refill, follow, first build) is charged as if executed through the 0.05% route at the same minute.**

- ETH: LP pool mainnet USDC/WETH 0.3% `0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8` (new data, `samples/holdout-data`,
  2021-05-05..2026-09-17, fetched with `fetch_uni_minute.py`). Swap route: USDC/WETH 0.05% `0x88e6` (one hop).
- WBTC: LP pool unchanged, WBTC/USDC 0.3% `0x99ac`. Swap route: WBTC/WETH 0.05% `0x4585` then WETH/USDC 0.05% `0x88e6`
  (two hops; there is no usable WBTC/USDC 0.05% series, `5653` is mostly empty).
- Cost model per swap: the backtest still executes the swap in the LP pool (demeter has one market); the ledger then
  (1) credits back the fee difference, notional × (LP pool fee − sum of route fees), and (2) replaces the price impact
  computed on the LP pool's virtual reserves with the sum over the route's hops of notional² / (that hop's virtual reserve of
  the input token in USD), at the hop pool's `closeTick` and `currentLiquidity` of the same minute (as-of). Same quadratic
  formula as `Checked.charge`. Gas: one extra swap hop for WBTC reported (not charged), as all gas.
- Constants: the route pools and their fees above; nothing else. Signal engine, F, ladder shape (±20% inverted gaussian),
  share rule, triggers: identical to v6. The engine reads the LP pool's own minute prices, as v6 does.
- Known approximations: the credited fee stays in the ledger (not re-deployed), as the impact charge already does; the
  route's execution price is taken equal to the LP pool's (the two tiers track within their fees).

Arms (all on the same code, same windows):

| arm | ETH | WBTC | role |
|---|---|---|---|
| `A` on `88e6` / `99ac` | v6 as is | v6 as is | baseline (EXP-000) |
| `A` on `8ad5` | v6 in the 0.3% pool, swaps at 0.3% | — | ablation, reported only (pool effect without routing) |
| `DD` on `8ad5` / `99ac` | this variant | this variant (routing only) | judged |

## Pre-registration

- Development (in-sample price paths; the `8ad5` pool data is new): ETH yearly segments 2022, 2023, 2024, 2025,
  2026-01-01..09-17 and continuous 2022-01-01..2026-09-17 (`DD` and `A` on `8ad5`, `A` on `88e6`); WBTC continuous
  2022-11-01..2026-09-17 (`A,DD` on `99ac`).
- Holdout (run once, only if dev passes): **time-split out-of-time**, warm-up from Binance daily closes (`BINANCE_WARM=1`):
  H5 ETH 2021-05-06..2021-12-31 (`DD` on `8ad5` vs `A` on `88e6`); H4 WBTC 2022-01-01..2022-10-31 (`A,DD` on `99ac`).
  v6's numbers there are known and both windows were used for other variants; this variant and the `8ad5` pool never ran
  there. Reported, not deciding: Base WETH/USDC 0.3% LP with swaps routed through Base 0.05% (`6c56` → `d0b5`)
  2025-01-01..2026-09-17 vs v6 on `d0b5`, and the forward window after 2026-09-17 when it exists.
- Success rule (improvement level; `judge.py dev` / `oot` with the ETH variant read from the `8ad5` run and v6 from the
  `88e6` run of the same window and code):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.
- Capacity check (reported): the $100k ladder's share of the `8ad5` pool's active liquidity per year (EXP-015's 2024 Base
  failure was a pool too thin for the ladder).

## Result

| test | v6 | this | gain |
|---|---|---|---|

Continuous run (reported, not deciding): total / CAGR / max DD / Sharpe.

Verdict: pass / fail / dropped at dev — and the one-line reason.

## Deviations

None.
