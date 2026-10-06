# EXP-156: spec sheet v1 as the baseline; v6.126 (EXP-140) re-run on spec v1's settings

- Jira: QUAN-___
- Status: pre-registered
- Level: improvement (over the new baseline, spec v1)
- Pre-registration commit: ______ · Result commit: ______
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

From this experiment on, `SPEC=v1` `A` is the baseline new experiments compare against (Dino, 2026-10-06); EXP-000..155 keep
their recorded verdicts.

## Result

| test | spec v1 | v6.126 | gain |
|---|---|---|---|

Verdict:

## Deviations

- The reproduction gate's baseline runs (`A` only, yearly 2022..2025) were started while this file was being written, before its
  commit; they contain no `EB` run.
