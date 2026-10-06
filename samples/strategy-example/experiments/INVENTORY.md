# Data inventory (pools and series available for research)

What data exists for strategy research. **Update this file in the same commit whenever data is added, downloaded or
used as a holdout.** The pool table that the code reads is `POOLS` in `strategy-example/v6_validate.py`; this file is
the human/AI-readable view of it plus what is not yet wired in. Last verified: 2026-10-05.

Minute data is gitignored and lives in the main checkout `/Users/dinohuang/Desktop/demeter-momentum/samples/`
(a worktree symlinks the folders). One file per UTC day: `<chain>-<pool>-<YYYY-MM-DD>.minute.csv`, columns
`timestamp,netAmount0,netAmount1,closeTick,openTick,lowestTick,highestTick,inAmount0,inAmount1,currentLiquidity`.
The files carry no token info; token order, decimals and fee are in `POOLS`.

## A. Downloaded pool minute data (all end 2026-09-17 unless noted)

All of these are **in-sample** for v6 research now: a new pre-registration needs a fresh holdout (see D).

| Pool | Chain | Pair, fee | Data from | Folder | Used as |
|---|---|---|---|---|---|
| `0x88e6a0c2...` | Ethereum | WETH/USDC 0.05% | 2021-05-06 | `real-data` | v6 dev pool |
| `0x99ac8ca7...` | Ethereum | WBTC/USDC 0.3% | 2021-11-02 | `holdout-data` | dev (WBTC) |
| `0x4585fe77...` | Ethereum | WBTC/WETH 0.05% | 2021-11-02 | `holdout-data` | EXP-001/009/010 holdout |
| `0xd0b53d92...` | Base | WETH/USDC 0.05% | 2023-12-01 | `base-data` | EXP-004 holdout, later reruns |
| `0xfbb6eed8...` | Base | USDC/cbBTC 0.05% | 2024-10-01 | `base-data` | EXP-011 |
| `0x6c561b44...` | Base | WETH/USDC 0.3% | 2024-01-01 | `base-data` | EXP-015 |
| `0xfad57d20...` | Ethereum | LINK/USDC 0.3% | 2021-06-01 | `holdout-data` | EXP-020 holdout (pool too thin) |
| `0xa6cc3c25...` | Ethereum | LINK/WETH 0.3% | 2021-06-01 | `holdout-data` | EXP-021 holdout |
| `0x1d42064f...` | Ethereum | UNI/WETH 0.3% | 2021-06-01 | `holdout-data` | EXP-021 holdout |
| `0xc6962004...` | Arbitrum | WETH/USDC 0.05% | 2023-06-09, ends **2025-07-23** | `holdout-data` | EXP-022/023 holdout |
| `0x8ad599c3...` | Ethereum | USDC/WETH 0.3% | 2021-05-05 (RPC, `fetch_uni_minute.py`, 2026-10-05) | `holdout-data` | EXP-117 LP pool (fee/LVR 1.70 vs `88e6` 0.75) |
| `0x5ab53ee1...` | Ethereum | AAVE/WETH 0.3% | 2021-06-01, ends **2023-12-31** | `holdout-data` | EXP-022/023 holdout |
| `0x3416cf6c...` | Ethereum | USDC/USDT 0.01% | 2021-11-15 (S3 to 2025-11-30, RPC 2025-12-01..2026-09-17) | `stable-data` | EXP-052 stable LP (not a v6 pool) |
| `0x7858e59e...` | Ethereum | USDC/USDT 0.05% | 2021-05-05 to 2021-11-30 (RPC) | `stable-data` | EXP-052 stable LP before 2021-11-15 |

## B. Other committed or local series (`samples/`)

| File | Content | Range |
|---|---|---|
| `gas_ethereum_hourly.csv`, `data/gas_price.csv` | Ethereum gas price (gas is reported, not charged) | see file |
| `eth_usd_hourly.csv` | ETH/USD hourly, used for gas in USD and EMA warm-up | 2021-05-06 to 2026-09-17 |
| `stable_lp_daily.csv` | EXP-052: daily net return of $1 LP'd in USDC/USDT ±0.1% (`make_stable_lp_series.py`) | 2021-05-05 to 2026-09-17 |
| `deribit_dvol_daily.csv` | Deribit DVOL (30-day implied vol index), ETH and BTC, daily close (`fetch_deribit_dvol.py`); EXP-082 | 2021-03-24 to 2026-10-01 |
| `binance_funding_{ETHUSDT,BTCUSDT}_long.csv` | USDT-M perp funding, 8h, longer history for the time-split holdouts; EXP-083..085 | 2020-06-01 to 2026-09-30 |
| `flow_daily.csv` | total stablecoin market cap (DefiLlama) and Coinbase ETH-USD / BTC-USD daily closes (`fetch_flow_daily.py`); EXP-093 | 2020-06-01 to 2026-10-05 |
| `binance_daily_closes.csv` | Binance daily closes | 2019-01-01 to 2026-10-01 |
| `binance_funding_{ETHUSDT,BTCUSDT,LINKUSDT,UNIUSDT}.csv` | USDT-M perp funding, 8h | from 2021-12-01 to 2026-09-17 |
| `binance_funding_{LINKETH,UNIETH}_synth.csv` | synthetic ALT/ETH funding (short ALT + long ETH) | see file |
| `aave_usdc_ethereum_daily.csv` | Aave v3 USDC supply APR, Ethereum | 2021-12-01 to 2026-09-17 |
| `aave_usdc_base_daily.csv` | Aave v3 USDC supply APR, Base | 2023-12-01 to 2026-09-17 |

Regenerate with `fetch_gas.py`, `fetch_binance_daily.py`, `fetch_binance_funding.py`, `fetch_aave_rates.py`.
`samples/data/` also holds older GMX / Polygon files from other strategies; v6 does not use them.

## C. Team S3 bucket (one pool downloaded since: `0x56534741...` WBTC/USDT 0.05% to `samples/holdout-data`, 89 MB; most days of 2021-22 are empty (sampled 2021-06..2022-10, 2023-03: 0-11 non-empty days per month), so it is unusable for out-of-time windows; later years not checked)

`s3://demeter-900103508088-ap-northeast-1-an/<pool>/<chain>-<pool>-<date>.minute.csv` (same format as above; access
with the `aws` CLI). Pairs below come from DexScreener, **fee tier is not known**: determine it before adding to `POOLS`.
Overlap with section A: `4585`, `88e6` (S3 ends 2026-09-09, local is longer: do not overwrite), `c696`, `d0b5`
(S3 reaches 2026-09-30: fetch the days after 09-17 only).

| Pool | Chain | Pair | S3 range | Fit for v6 |
|---|---|---|---|---|
| `0x7AeA2E8A...` | Base | cbBTC/WETH | 2024-09-13 to 2026-09-29 | yes; has days after 2026-09-17 |
| `0x2f5e87C9...` | Arbitrum | WBTC/WETH | 2023-01-01 to 2026-01-13 | yes |
| `0x56534741...` | Ethereum | WBTC/USDT | 2021-06-11 to 2025-10-21 | yes, same price path as `99ac` |
| `0xCBCdF962...` | Ethereum | WBTC/WETH (likely 0.3%) | 2021-05-04 to 2024-10-01 | yes, low volume |
| `0xc473e2aE...` | Arbitrum | USDC/WETH | 2023-06-09 to 2024-08-13 (2023-09-09 missing) | short |
| `0x109830a1...` | Ethereum | wstETH/WETH | 2022-08-25 to 2025-12-01 | no: pegged ratio, no trend |
| `0xe8f7c89C...` | Ethereum | cbBTC/WBTC | 2024-09-20 to 2025-11-09 | no: pegged ratio |
| `0x3416cF6C...` | Ethereum | USDC/USDT | 2021-11-15 to 2025-11-30 | not for v6 (stablecoin pair); downloaded for EXP-052 |
| `0x48DA0965...` | Ethereum | DAI/USDT | 2022-07-20 to 2026-01-31 | no: stablecoin pair |

Files for a pool's first days can be 111 bytes (header only, no trades yet); readers must tolerate empty days.

## D. Choosing pools (since 2026-10-06: no in-sample / out-of-sample split)

Dino, 2026-10-06: every pool in A and C may be used and judged on its full history; S3 pools may be downloaded without asking
(add them to `POOLS` and this file in the same commit). The note below still matters for how much a multi-pool result says:
pools that share a price path are not independent evidence.

### Price paths (written for fresh holdouts, before 2026-10-06)

A different pool is not a different price path: `7aea`, `2f5e`, `CBCd` are BTC/ETH like `4585`; `5653` is WBTC like
`99ac`; Arbitrum/Base WETH/USDC follow ETH like `88e6`. They vary liquidity, fee and chain, not the price sample.
Genuinely new price paths are other assets (LINK, UNI, AAVE were used for that) or data after 2026-09-17
(forward holdout 2026-09-18..12-31, Jan 2027). Say which kind of freshness a holdout gives in its pre-registration.
