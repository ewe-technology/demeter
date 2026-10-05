# EXP-086: refill stages need the other asset's rebound too (v6.73)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

A rebound in one asset alone (an idiosyncratic bounce) is less likely to be a market-wide range than one shared by ETH and BTC, whose lows coincide in most crashes (cross-crypto predictability, JEDC 2024). Requiring the other asset to be ≥ 5% above its own low since the account's exit before a stage fires filters single-asset bounces; symmetric for both pools.

## Change

`REFILL_GATE = "xasset"` (variant `BY`): a stage fires only if the other asset's Binance daily close (BTC for ETH pools, ETH for BTC pools) is ≥ 1.05 x its lowest close since the exit. Constant: 1.05 (the engine's own first-stage level).

## Pre-registration

Pre-registered together with EXP-082..086 (same commit), run in one invocation per window with `A` (v6): `A,BU,BV,BW,BX,BY`. EXP-083 and EXP-084 share the accelerator and are near-copies.

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev windows,
  warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC 0.3%
  2022-01-01..2022-10-31. v6's numbers there are known (EXP-040..081) and both windows have been used for other variants; this
  variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

(pending)

## Deviations

- Ideas from a literature pass of 2026-10-05 (fourth agent run; it suggested screening the signals on dev refill events before pre-registering, which was not done, to keep dev unseen). New inputs: `samples/deribit_dvol_daily.csv` (`fetch_deribit_dvol.py`, Deribit DVOL from 2021-03-24), `binance_funding_{ETH,BTC}USDT_long.csv` (from 2020-06). Engine sanity check before this file (F statistics only, no strategy run): Binance ETH closes 2020-06..2021-04 and 2021-06..2023-06 (the second range overlaps dev: F means and change counts were seen, no returns). The first DVOL rule (3-day mean below the peak since exit) could never block — a mean cannot exceed the max it includes — and was replaced by the falling-DVOL rule below before this file.
