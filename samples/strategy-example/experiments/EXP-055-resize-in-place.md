# EXP-055: follow F by resizing the ladder in place instead of rebuilding it (v6.42)

- Jira: QUAN-937
- Status: dropped-at-dev
- Pre-registration commit: 29b47c1 · Result commit: c02ec73
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

v6 handles every change of F (|F − deployed| ≥ 12.5%) with a full rebuild: it burns all 17 bands, swaps back to the target
ETH share (70% / 50%) and re-mints the ladder centred on the current price. A recentre inside the range turns the ladder's
impermanent loss into a realised trade: after a rise the bands hold more USDC and the rebuild buys ETH back higher; after a
fall they hold more ETH and the rebuild sells it lower ("permanent loss", Elsts; Panoptic's ETH/USDC backtests favour fewer
recentres). F changes in v6 are frequent on the way back up (staged refills at +5 / +8.3 / +11.7 / +15% from the low), so
these mid-range rebuilds buy ETH into rallies. Resizing in place — scaling every band's liquidity by target / current at
its own ticks — changes the size without the recentre and without the swap back to the target share: the ladder keeps the
composition the market gave it. Expected: fewer forced trades at local extremes → higher fee-minus-IL per rebuild, CAGR up,
drawdown the same or shallower.

## Change

`RESIZE_IN_PLACE = True` (variant `AR`). When the follow rule fires and the ladder is deployed (current > 2%) and the target
is > 0: fees of every band are collected (paid out as v6 does), then
- target < current: liquidity x (1 − target/current) is removed from every band; the withdrawn base is sold for quote so the
  reserve stays quote;
- target > current: the bands' current base and quote amounts x (target/current − 1) are added to the same ticks; the base
  missing for that is bought with quote first.
The deployed F is set to the target. Range exits (price outside the ladder at the daily check), the first build, builds from
an empty book (F was 0) and full exits to F = 0 stay v6's full rebuilds. Costs: pool fee and price impact of the one swap,
as for a rebuild; gas reported. No constants.

## Pre-registration

Pre-registered together with EXP-056 (and any other file of the same commit) and run in the same invocations as `A` (v6).

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev windows,
  warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC 0.3%
  2022-01-01..2022-10-31. v6's numbers there are known (EXP-040..052); this variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

Development (`A` and the variant in each invocation, tag `AARASAT`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +1.2% | -6.4 |
| 2023 | +32.2% | +33.1% | +0.9 |
| 2024 | +36.4% | +30.8% | -5.5 |
| 2025 | +16.3% | +10.3% | -5.9 |
| 2026-01..09-17 | +18.7% | +22.6% | +3.9 |

Wins 2/5, median -5.55 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +61.9% | 10.8% | -21.0% | 0.62 | 0.51 | $81.6k | $0.21k | 152 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +79.5% | 16.3% | -13.3% | 1.01 | 1.22 | $62.9k | $0.57k | 109 |

Verdict: **dropped-at-dev** — ETH CAGR 10.8% vs 14.0%, Calmar 0.51 vs 0.61 (max DD −21.0% vs −22.8%), yearly wins 2/5; WBTC CAGR 16.3% vs 17.3% with Calmar 1.22 vs 0.97 and max DD −13.3% vs −17.8%. Holdout not run. Reading: keeping the old ticks lowers risk on both assets (shallower drawdown, a large WBTC Calmar gain) but ETH fee income falls (.6k vs .5k) and ETH loses in 2022, 2024 and 2025. The mechanism of the fee loss was not isolated; the observation is that v6's recentre on F changes earns more than it costs on ETH.

## Deviations

- Smoke test before this file: ETH 2022-05-01..06-30 (inside the dev data, chosen because F moves there), variants `A,AR,AS`;
  the totals were printed (v6 −7.9%, this −6.7%, EXP-056 −8.0%). The rule has no constant, so nothing could be adjusted on it.
