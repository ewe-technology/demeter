# EXP-156: spec sheet v1 as the baseline; v6.126 (EXP-140) re-run on spec v1's settings

- Jira: QUAN-1041
- Status: fail
- Level: improvement (over the new baseline, spec v1)
- Pre-registration commit: 94737a3 · Result commit: ______
- Scope: Dino, 2026-10-06, shared the team's baseline sheet "USDC/ETH gamma maker defence v1 slippage 0.1/fee 0.05"
  (Mark: the spec sheet's ETH/USDC v1 backtest; Maker's `gamma_maker_defense_ethusdc_v1.py`, branch `maker-defense`
  `fb293bc`) and asked whether v6.126 beats it. The answer in this session was "+90.1% vs +83.5% on 2022-01-02..2025-12-31, but
  across two cost / signal models". Dino: "改" — make spec v1 the baseline and re-run v6.126 on it.

## Hypothesis

Spec v1 differs from this branch's v6 (EXP-000) in four settings, not in logic: (1) the EMA / F engine reads Binance ETHUSDT
daily closes instead of the pool's last minute price, (2) the 16 bands are cut in equal 2.5% price steps instead of equal tick
counts, with the spec's own weights (within 0.1 pt per band of v6's), (3) every swap costs a flat 0.1% (pool fee included, no
price impact), (4) windows start on 1/2. On 2022-01-02..2025-12-31 the sheet shows +83.5% / APR 16.4% / max DD −25.8%; this
branch's v6 on the same window +68.6% / 14.0% / −24.4% (`0x88e6-opt-AEB-2022-01-02-2025-12-31`). Maker's doc (§6) puts most of the
gap on the signal source (2022 +11.9% vs +7.6%, 2023 +38.9% vs +32.3%: the 2023-03 USDC depeg moved the pool price 4.5%).

v6.126's ETH half (no-new-low refill, cross-asset refill, macro restore) was measured against the pool-price engine. H1: its
gain survives on the Binance engine, because none of its rules target the pool-price error (they delay refills into wick
retests and single-asset bounces, and pull the ladder over scheduled releases). H0: part of the gain was the rules
compensating for the pool-price signal's mistakes (e.g. depeg days), so it shrinks or vanishes on spec v1.

## Change

Code, no new strategy logic: `SPEC=v1` in `v6_validate.py` runs every variant in the invocation on spec v1's settings:

- `V.SIGNAL_CLOSE` = Binance daily closes of the pool's asset (`../binance_daily_closes.csv`, from 2019-01-01; equal to
  Maker's `binance_ethusdt_1d.csv` on all 2,557 shared days). The engine's close and EMAs come from it; the day's low / high /
  open (used by v6.75's no-new-low rule) still come from the pool's minutes.
- Shape `inverted_gaussian_spec_price` (Maker's `build_price_bands` and spec weights, copied with his self-check asserts).
- Each rebuild / restore swap is charged `notional x (0.1% − pool fee)` in the cost ledger on top of the pool fee demeter
  already takes; no price-impact ledger. (Fee-to-USDC sales go through the same ledger here; Maker does not charge them —
  about $40 over four years, reported, not corrected.)
- Windows start on 1/2 where the spec does (the sheet window), otherwise on the pool's first data day.

Variants: `A` (v6 = spec v1 under `SPEC=v1`) and `EB` (EXP-140, v6.126: on pools below 0.3% v6.75 + cross-asset refill + macro
restore; on 0.3% pools intraday stop + volume refill + 0.05% routing — under `SPEC=v1` the routing rebate is replaced by the
flat 0.1% cost, so the 0.3% half keeps only its stop and volume rules). Same invocation per pool.

## Pre-registration

0. Reproduction gate (baseline only, before judging): `A` under `SPEC=v1` on mainnet `0x88e6`, yearly 2022..2025 from 1/2,
   within ±1.0 pt of the sheet each year (+11.83 / +40.42 / +32.33 / +16.34%), and the continuous 2022-01-02..2025-12-31 run
   within ±2.0 pts of +83.47%. If it misses, the port is wrong: fix and rerun before any `EB` run, and record why.
1. Sheet window (answers Dino's question): `0x88e6` continuous 2022-01-02..2025-12-31 and the four yearly windows.
   Pass: continuous CAGR above spec v1, Calmar ≥ spec v1, max DD no more than 3 pts deeper, and ≥ 3 of 4 yearly wins.
2. Full history (the standing bar since 2026-10-06), same seven pools and windows as EXP-154, one continuous run each with
   `A` and `EB` under `SPEC=v1`:
   - ETH: mainnet `0x88e6` 2021-05-06..2026-09-17; mainnet 0.3% `0x8ad5` 2021-05-06..2026-09-17; Base 0.05% `0xd0b5`
     2023-12-01..2026-09-17; Arbitrum 0.05% `0xc696` 2023-06-09..2025-07-23; Base 0.3% `0x6c56` 2025-01-01..2026-09-17.
   - BTC (Binance BTCUSDT signal): mainnet WBTC/USDC 0.3% `0x99ac` 2021-11-02..2026-09-17; Base USDC/cbBTC 0.05% `0xfbb6`
     2024-10-01..2026-09-17.
   Pass: CAGR above spec v1, Calmar ≥ spec v1, max DD no more than 3 pts deeper on at least 4 of 7 pools, at least one ETH and
   one BTC pool among the wins. A pool whose `A` run is invalid (net value below zero, or a cost ledger above equity) counts
   as a loss for `EB` and is reported.
3. Verdict: `pass` if 1 and 2 pass; `fail` otherwise. Report every pool, including the ones lost.

From this experiment on, `SPEC=v1` `A` is the baseline new experiments compare against (Dino, 2026-10-06); EXP-000..154 keep
their recorded verdicts.

## Result

Code `94737a3`. Raw runs: `result/v6_validate/*-opt-A*-specv1-*` (main checkout).

### 0. Reproduction gate — passed

`A` under `SPEC=v1` (tag `opt-A-specv1`, then again inside every `AEB` invocation) against the sheet:

| window | sheet | `SPEC=v1` `A` | diff |
|---|---|---|---|
| 2022-01-02..12-31 | +11.83% | +11.84% | +0.00 |
| 2023-01-02..12-31 | +40.42% | +40.41% | −0.01 |
| 2024-01-02..12-31 | +32.33% | +32.28% | −0.05 |
| 2025-01-02..12-31 | +16.34% | +16.28% | −0.06 |
| continuous 2022-01-02..2025-12-31 | +83.47%, max DD −25.8% | +84.04%, max DD −25.9% | +0.57 |

The port reproduces Maker's v1. It is now this branch's baseline.

### 1. Sheet window (`0x88e6`) — passes

| yearly | spec v1 | v6.126 | gain | max DD v1 → v6.126 | LP fees | rebuilds |
|---|---|---|---|---|---|---|
| 2022 | +11.8% | +17.4% | +5.5 | −19.4% → −15.4% | $21.7k → $19.7k | 38 → 57 |
| 2023 | +40.4% | +40.8% | +0.4 | −10.7% → −10.6% | $22.4k → $22.4k | 23 → 51 |
| 2024 | +32.3% | +31.9% | −0.4 | −28.4% → −29.7% | $28.9k → $29.0k | 29 → 62 |
| 2025 | +16.3% | +17.5% | +1.2 | −27.0% → −26.9% | $21.3k → $21.1k | 32 → 51 |

Wins 3/4, median +0.8 pt.

| continuous 2022-01-02..2025-12-31 | total | CAGR | max DD | Calmar | rebuilds | gas if mainnet (not charged) |
|---|---|---|---|---|---|---|
| spec v1 | +84.0% | 16.5% | −25.9% | 0.64 | 120 | $56.3k |
| v6.126 | +97.6% | 18.6% | −27.6% | 0.67 | 219 | $90.6k |

CAGR +2.1 pts, Calmar ≥, max DD 1.7 pts deeper (within 3), wins 3/4 → part 1 passes.

### 2. Full history, 7 pools — fails (3/7)

| pool | spec v1 total / CAGR / max DD / Calmar | v6.126 | win |
|---|---|---|---|
| ETH mainnet WETH/USDC 0.05% `0x88e6` 2021-05-06..2026-09-17 | +97.7% / 13.6% / −22.9% / 0.59 | +133.5% / 17.1% / −24.3% / 0.71 | **win** |
| ETH mainnet USDC/WETH 0.3% `0x8ad5` 2021-05-06..2026-09-17 | +100.0% / 13.8% / −21.0% / 0.66 | +83.8% / 12.0% / −16.5% / 0.73 | lose (CAGR) |
| ETH Base WETH/USDC 0.05% `0xd0b5` 2023-12-01..2026-09-17 | +54.9% / 17.0% / −34.7% / 0.489 | +56.6% / 17.4% / −36.3% / 0.479 | lose (Calmar) |
| ETH Arbitrum WETH/USDC 0.05% `0xc696` 2023-06-09..2025-07-23 | +65.7% / 26.88% / −31.4% / 0.86 | +65.7% / 26.86% / −32.7% / 0.82 | lose (tie) |
| ETH Base WETH/USDC 0.3% `0x6c56` 2025-01-01..2026-09-17 | +29.8% / 16.5% / −24.6% / 0.67 | +21.1% / 11.9% / −23.3% / 0.51 | lose |
| BTC mainnet WBTC/USDC 0.3% `0x99ac` 2021-11-02..2026-09-17 | +62.2% / 10.4% / −30.1% / 0.35 | +64.8% / 10.8% / −29.7% / 0.36 | **win** |
| BTC Base USDC/cbBTC 0.05% `0xfbb6` 2024-10-01..2026-09-17 | +44.0% / 20.5% / −16.7% / 1.22 | +45.5% / 21.1% / −16.8% / 1.26 | **win** |

Wins 3/7 (ETH 1 of 5, BTC 2 of 2), median CAGR gain +0.4 pt → part 2 fails. Both pools that were invalid under the impact
ledger (`0xc696`, `0xfbb6`) are valid under the spec's flat cost.

Verdict: **fail** — v6.126 beats spec v1 on the sheet's own pool and window (+97.6% vs +84.0%, CAGR 18.6% vs 16.5%, Calmar
0.67 vs 0.64), but wins only 3 of 7 pools over their full history.

Reading:
- **The gain is mainnet ETH 0.05%, and mostly 2022.** On the Binance engine the gain on the sheet window is +13.6 pts total (it
  was +21.5 pts against this branch's pool-price v6): about a third of the old gain was the rules making up for the pool-price
  signal. 2022 alone is +5.5 of the four years' +6.7 yearly-sum.
- **The other 0.05% ETH pools are a tie** (Base +0.4 pt CAGR with Calmar −0.01, Arbitrum −0.02 pt). The ETH half does not
  generalise beyond mainnet on this evidence.
- **The 0.3% half hurts ETH 0.3% pools** (mainnet −1.8 pts, Base −4.6 pts CAGR): the intraday stop + volume refill was fitted
  on WBTC (EXP-112 / 124) and the fee-tier switch sends ETH 0.3% pools to it. On WBTC 0.3% it still wins, by +0.4 pt.
- **Gas.** v6.126 rebuilds about twice as often (macro restore). On the sheet window its mainnet gas estimate is $34.2k higher
  than spec v1's on a $100k book, more than its $13.6k extra return. Gas is reported, not charged (rule), but on mainnet at
  this size the gain does not survive it; on an L2 it would.

## Deviations

- The reproduction gate's baseline runs (`A` only, yearly 2022..2025) were started while this file was being written, before its
  commit; they contain no `EB` run.
- The three long full-history invocations (`0x88e6` 2021-, `0x8ad5`, `0x99ac`) were killed after their main loops at 16:21
  (three invocations of two workers next to another session's six; no output written) and rerun two at a time, unchanged.
- The yearly gate compares "Rate of Return"; the sheet's 2025 tab shows +16.34% there and +16.26% in "Rate of Return USD".

