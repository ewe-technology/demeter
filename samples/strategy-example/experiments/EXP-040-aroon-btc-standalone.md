# EXP-040: Aroon regime (v6.29) judged standalone as a BTC-pool strategy (v6.29r)

- Jira: QUAN-___
- Status: holdout-fail
- Pre-registration commit: 5dad516 · Result commit: ______
- Re-judged from EXP-038; level: standalone, BTC-pool (README *Success levels*)
- Scope: the Uniswap strategy itself (Dino, 2026-10-01 and /goal 2026-10-02): LP mechanics and the regime signal only, no perps, no lending. Claimed for BTC pools only: it failed the ETH dev screen.

## Hypothesis

EXP-038 failed dev on ETH (CAGR 2.1% vs 14.0%) and was the best of its batch on WBTC (CAGR 25.1% vs 17.3%, Calmar 1.43 vs 0.97, max DD −17.5%). Slow time-structure regime lines (SMA, Ichimoku, Aroon, ROC) all beat v6 on WBTC and all lose on ETH (EXP-026, 036, 037, 038), so they are judged here for the asset they suit, on the one BTC window the dev data never contained: the 2022 bear market.

## Change

`REGIME = "aroon"` (variant `AE`), exactly EXP-038's definition. No change to the code since EXP-038; the holdout needs the `BINANCE_WARM` option of `v6_validate.py` (warm-up days before the pool's data from Binance daily closes, default off, existing runs unchanged: v6 2026-01-01..09-17 still +18.706%).

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

Holdout, `A` and the variant in the same invocation:

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| WBTC 2022 out-of-time v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| WBTC 2022 out-of-time this | -12.1% | -14.4% | -23.0% | -0.51 | -0.63 | $11.0k | $0.04k | 21 |
| Base cbBTC v6 | +22.3% | 12.5% | -15.7% | 0.93 | 0.79 | $15.9k | $0.43k | 40 |
| Base cbBTC this | +9.1% | 5.2% | -19.0% | 0.41 | 0.28 | $17.6k | $0.50k | 31 |

Verdict: **holdout-fail** (standalone, BTC-pool) — dev passes the screen (from EXP-038: WBTC Calmar ≥ 0.60) but H-a, the out-of-time 2022 bear window, ends -12.1% (max DD -23.0%) where v6 ends +2.4% (max DD -12.5%): the rule needs a positive return. H-b Base cbBTC: +9.1%, Calmar 0.276 (v6 +22.3%, 0.795), below the 0.50 bar. The WBTC dev edge of this line was a bull-market fit: it lost the 2022 window the dev data never held, and lagged v6 on the other BTC pool.

## Deviations

- The standalone BTC-pool rule was written on 2026-10-02 after the dev results of EXP-026, 036, 037, 038 were seen. Its thresholds are those of the two-asset standalone rule (README), not fitted to these candidates.
- Before this file a smoke run of the new `BINANCE_WARM` code on WBTC 2021-11-02..2021-12-31 (A and AE only) printed A −11.1% and AE −15.7%; H-a starts on 2022-01-01 to keep that window out of the holdout. That peek is the only holdout-adjacent number seen.
