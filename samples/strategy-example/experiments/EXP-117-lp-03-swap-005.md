# EXP-117: LP in the 0.3% fee tier, rebuild swaps routed through the 0.05% tier (v6.104)

- Jira: QUAN-1002
- Status: dropped-at-dev
- Pre-registration commit: 0180340 · Result commit: 66ec841
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

Development (code `6c57e80`; v6 = `A` on `0x88e6` tag `A`; this = `DD` on `0x8ad5` tag `ADD`, with `A` on `0x8ad5` as the
ablation; WBTC `A,DD` on `0x99ac` tag `ADD`). v6's ETH continuous run reproduces EXP-000 (+85.36%).

| year | v6 (`88e6`) | v6 in `8ad5`, swaps at 0.3% (ablation) | this | gain vs v6 |
|---|---|---|---|---|
| 2022 | +7.6% | +8.1% | +10.1% | +2.5 |
| 2023 | +32.2% | +18.2% | +20.1% | −12.1 |
| 2024 | +36.4% | +31.6% | +33.8% | −2.6 |
| 2025 | +16.3% | +14.1% | +17.0% | +0.7 |
| 2026-01..09-17 | +18.7% | +17.3% | +18.3% | −0.4 |

Wins 2/5, median −0.43 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | rebuilds | swap notional | route fee credit | impact (net ledger) |
|---|---|---|---|---|---|---|---|---|---|---|
| ETH v6 (`88e6`) | +85.4% | 14.0% | −22.8% | 0.73 | 0.61 | $86.5k | 147 | $3.52M | — | $0.29k |
| ETH v6 in `8ad5` (ablation) | +84.2% | 13.8% | −20.0% | 0.73 | 0.69 | $84.1k | 144 | $3.42M | — | $0.46k |
| ETH this | +92.9% | 15.0% | −18.9% | 0.79 | 0.79 | $84.1k | 144 | $3.42M | $8.6k | −$8.26k |
| WBTC v6 | +85.6% | 17.3% | −17.8% | 1.01 | 0.97 | $61.7k | 106 | $2.82M | — | $0.72k |
| WBTC this | +91.1% | 18.2% | −16.5% | 1.06 | 1.10 | $61.7k | 106 | $2.82M | $5.6k | −$4.98k |

Yearly fees, rebuilds and mean F (v6 `88e6` vs this): 2022 $20.1k / 41 / 0.55 vs $20.8k / 39 / 0.55; 2023 $23.3k / 24 / 0.73
vs $15.1k / 23 / 0.74; 2024 $30.9k / 29 / 0.77 vs $27.5k / 29 / 0.76; 2025 $20.8k / 32 / 0.58 vs $19.8k / 33 / 0.59; 2026
$6.2k / 24 / 0.61 vs $5.7k / 24 / 0.62. Capacity (median virtual reserve of `8ad5` on sampled days): $193M (2022-06),
$260M (2023-01), $526M (2024-06), $278M (2025-06), $60M (2026-06): a $100k ladder stays well below 1% of active liquidity.

`judge.py dev` (`JUDGE_ETH_POOL=0x8ad5 JUDGE_ETH_BASE_TAG=A`): ETH CAGR 15.0 vs 14.0, Calmar 0.79 vs 0.61, max DD −18.9 vs
−22.8; WBTC CAGR 18.2 vs 17.3, Calmar 1.10 vs 0.97, max DD −16.5 vs −17.8; **wins 2/5**.

Verdict: **dropped-at-dev** — four of five dev conditions pass (continuous CAGR and Calmar above v6 on both assets, shallower
drawdowns), the fifth fails: ETH yearly wins 2/5 (rule ≥ 3/5), driven by 2023 (−12.1 pts). Holdout not run. Standalone level
(reported, not registered for this EXP): passes at dev (Calmar 0.79 / 1.10, max DD −18.9 / −16.5, 5/5 positive years).

Reading (interpretation, partly measured):
- Comparing this with v6 isolates the pool: both pay the 0.05% swap fee (v6 natively, this after the credit), so the
  +7.5 pts total / +1.0 pt CAGR / −3.9 pts max DD over 4.7 years come from placing the ladder in the 0.3% pool. Fees are about
  equal on the continuous run ($84.1k vs $86.5k) while the result is higher, consistent with the lower LVR measured in the
  pool scan; not decomposed here (`decomp.py` needs the daily ETH-held log).
- The ablation shows why EXP-015 lost: without routing the same pool change costs ~$8.6k of extra swap fees and ends at
  13.8% CAGR. WBTC's gain is routing alone ($5.6k credit, its LP pool is unchanged).
- 2023 is the year the 0.3% tier lost volume share: the ladder's fees fell to $15.1k vs $23.3k in the 0.05% pool (about
  295 vs 2,600 swaps a day on sampled days), and the yearly-reset run trails by 12 pts. Fee share per unit of liquidity
  moves between tiers year by year; the fee/LVR scan (which favoured the 0.3% tier in 2023, 2.57 vs 1.39) does not see the
  ladder's share of a pool's volume.

## Deviations

- Smoke tests on dev data before the dev run, after the pre-registration: `0x8ad5` and `0x99ac` 2023-01-01..02-28 (`A,DD`), to
  check the ledger (fee credit = notional × fee difference, $312.16 and $340.25, as expected). The first ETH smoke test showed
  the route impact computed on both swap sides while v6's ledger charges only one (base side if any, else quote side); the
  route impact was changed to the same side before the dev run (the pre-registration says "same quadratic formula as
  `Checked.charge`"). The fee credit stays on the full notional (both sides paid the fee).
- Baseline v6 ran in a separate invocation from the variant (different pool) with the same code and windows, as
  pre-registered in the arms table.
