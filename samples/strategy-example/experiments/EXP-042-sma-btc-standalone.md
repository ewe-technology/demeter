# EXP-042: SMA(200 family) regime (v6.27) judged standalone as a BTC-pool strategy (v6.27r)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Re-judged from EXP-036; level: standalone, BTC-pool (README *Success levels*)
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending. Claimed for BTC pools only: it failed the ETH dev screen.

## Hypothesis

EXP-036 failed dev on ETH (CAGR 1.8% vs 14.0%) and beat v6 on WBTC (CAGR 21.1%, Calmar 1.19 vs 0.97, max DD −17.8%). Slow time-structure regime lines (SMA, Ichimoku, Aroon, ROC) all beat v6 on WBTC and all lose on ETH (EXP-026, 036, 037, 038), so they are judged here for the asset they suit, on the one BTC window the dev data never contained: the 2022 bear market.

## Change

`REGIME = "sma"` (variant `AB`), exactly EXP-036's definition. No change to the code since EXP-036; the holdout needs the `BINANCE_WARM` option of `v6_validate.py` (warm-up days before the pool's data from Binance daily closes, default off, existing runs unchanged: v6 2026-01-01..09-17 still +18.706%).

## Pre-registration

Pre-registered together with EXP-040..043 and run in the same invocations as `A`; all results reported.

- Development (observed before this file, in the original experiment; not re-run): WBTC/USDC 0.3% continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant in the same invocation; the baseline numbers are reported, not judged):
  - H-a WBTC/USDC 0.3% `0x99ac8ca7087fa4a2a1fb6357269965a2014abc35`, **out-of-time** 2022-01-01..2022-10-31: the BTC window before the dev window (dev starts 2022-11-01 because the engine needs 360 days of warm-up), bear market. Warm-up: pool minutes from 2021-11-02 plus Binance BTCUSDT daily closes for the earlier days (`BINANCE_WARM=1`; the high and low of those days equal the close); the Binance close is within 0.4% of the pool's on the overlap day checked (2021-11-10);
  - H-b Base USDC/cbBTC 0.05% continuous 2025-01-01..2026-09-17 (another chain and pool; the BTC price path overlaps the dev window's tail).
  The variant never ran on these windows. Honest limit: two windows only; H-b shares the dev window's BTC path.
- Success rule (standalone, BTC-pool, README *Success levels*; Calmar = CAGR / |max DD|, daily equity net of price impact):
  - Dev (observed): continuous WBTC Calmar ≥ 0.60 and max DD no deeper than −30%. ETH is not required: this is a BTC-pool strategy.
  - Holdout: H-a total return > 0 and max DD no deeper than −35%; H-b total return > 0, Calmar ≥ 0.50 and max DD no deeper than −35%. All of it → `holdout-pass` (standalone, BTC-pool), else `holdout-fail`.

## Result

(not run)

## Deviations

- The standalone BTC-pool rule was written on 2026-10-02 after the dev results of EXP-026, 036, 037, 038 were seen. Its thresholds are those of the two-asset standalone rule (README), not fitted to these candidates.
- Before this file a smoke run of the new `BINANCE_WARM` code on WBTC 2021-11-02..2021-12-31 (A and AE only) printed A −11.1% and AE −15.7%; H-a starts on 2022-01-01 to keep that window out of the holdout. That peek is the only holdout-adjacent number seen.
