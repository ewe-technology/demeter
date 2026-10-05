# Findings 2026-10-05, round 2 (EXP-082..091)

Goal (Dino, 2026-10-05, "find 30 more"): a pure-LP change that beats v6 at the improvement level on ETH and WBTC (CAGR above,
Calmar ≥, max DD no more than 3 pts deeper, ETH yearly wins ≥ 3/5) on dev and on the time-split holdout (H5 ETH/USDC 0.05%
2021-05-06..12-31, H4 WBTC/USDC 0.3% 2022-01-01..10-31). Stop at the first pass or after 30 experiments.

## Result: v6.75 (EXP-088) passes, after 10 experiments

**v6.75 — a refill day counts only if its intraday low stays above the low since the exit.** Every v6 rule stays; the only change
is that a day whose minute low retests or breaks the account's low since its last exit does not advance the stage-1 counter or
a later stage. Variant `CA`, switch `REFILL_NO_NEW_LOW`, commit 0f8cc14 (pre-registration), b48fc64 (result).

| window | v6 CAGR | v6.75 CAGR | v6 Calmar | v6.75 Calmar | v6 max DD | v6.75 max DD |
|---|---|---|---|---|---|---|
| dev ETH 2022-01..2026-09 | 14.0% | 15.4% | 0.61 | 0.64 | −22.8% | −24.3% |
| dev WBTC 2022-11..2026-09 | 17.3% | 17.6% | 0.97 | 0.97 | −17.8% | −18.2% |
| H5 ETH 2021-05..12 (holdout) | 7.0% | 21.4% | 0.23 | 0.79 | −30.7% | −27.0% |
| H4 WBTC 2022-01..10 (holdout) | 2.9% | 3.4% | 0.23 | 0.28 | −12.5% | −12.2% |

ETH yearly wins 4/5. Holdout total return +13.5% vs +4.5% (H5) and +2.8% vs +2.4% (H4).

How much to trust it:

- **The gain is ETH's.** On WBTC the rule almost never binds: dev 105 vs 106 rebuilds, mean F 0.666 vs 0.672; H4 17 vs 17
  rebuilds, mean F 0.63 both. WBTC's pass (+0.3 pt dev, +0.5 pt H4) is within noise: read v6.75 as "better on ETH, neutral on
  WBTC", not "better on both".
- **One out-of-time window per asset.** The H5 gain (+9 pts total) comes from one 8-month bull window with the May 2021 crash.
  ETH's dev DD is 1.5 pts deeper than v6's.
- **Multiple testing.** It is the 1st pass in 40 experiments under this rule (EXP-052..091); the earlier four dev passes all
  failed the holdout. v6's family has PBO 0.56. A pass at this rate is weak evidence on its own.
- **No look-ahead**: the intraday low of day D is known at the end of day D, when the engine reads day D's close; the rebuild
  happens at 00:00 of D+1.

The clean test is data the rule has never seen: ETH/USDC and WBTC/USDC after 2026-09-17 (forward window), and the Arbitrum /
Base pools in `INVENTORY.md`. Until then v6.75 is a candidate, not a replacement for v6.

## The other nine (all dropped at dev)

| EXP | version | change | ETH CAGR (v6 14.0%) | WBTC CAGR (v6 17.3%) | reading |
|---|---|---|---|---|---|
| 082 | v6.69 | refill only while DVOL falls | 13.9% | 11.7% | DVOL rises into good rebounds too |
| 083 | v6.70 | negative funding skips the 3-day hold | 11.7% | 17.4% | early re-entries fail |
| 084 | v6.71 | 083 + hot-funding brake | 11.7% | 17.4% | brake never fired on a later stage |
| 085 | v6.72 | F ≤ 50% while funding is hot | 14.9% | 13.7% | cuts WBTC's 2023-24 bull |
| 086 | v6.73 | refill needs the other asset's rebound | 15.4% | 15.6% | BTC leads: helps ETH only |
| 087 | v6.74 | refill needs pool volume ≥ 30-day median | 11.4% | 18.4% | helps WBTC (0.3%), hurts ETH (0.05%) |
| 089 | v6.76 | engine on the daily TWAP | 13.4% | 15.6% | the mean lags the close |
| 090 | v6.77 | one stage less while realised vol > DVOL | 13.1% | 15.5% | RV > IV is mostly the rebound itself |
| 091 | v6.78 | F ≤ mean(F, other asset's F) | 15.1% | 16.0% | cross-asset: helps ETH only |

## What round 2 adds to round 1's findings

1. **Outside information splits the assets.** Options (DVOL), leverage (funding), cross-asset state and pool volume each moved
   ETH and WBTC in opposite directions, the same split round 1 found for recentring: the 0.05% ETH pool wants fast refills, the
   0.3% WBTC pool wants fewer, better-paid rebuilds. A rule that helps one asset by changing how often or how early the ladder
   is rebuilt hurts the other.
2. **What passed uses the same price, more finely.** v6.75 adds no new signal; it reads the pool's own minute low to drop wick
   retests from the refill count. That leaves WBTC nearly untouched (its retests are rarer at daily resolution) and saves ETH
   from refills that the next day's low would have stopped out.
3. **Cross-asset rules help ETH only** (EXP-086, EXP-091): BTC leads both the sell-offs and the recoveries.

## Queued, not run (not pre-registered)

Designed during the EXP-087..091 run, dropped from the queue when v6.75 passed (stop rule). Trigger rates were checked, outcomes
were not looked at: gas-spike refill hold (spike day 1.4% of days), stablecoin-supply refill gate (7-day change < 0 on 40% of
days; data in `samples/flow_daily.csv`), no weekend refill, volume-confirmed EMA exit, pool order-flow refill gate (3-day net
selling 54% ETH / 47% WBTC). A Coinbase-premium gate was rejected before registration (USDT/USD basis noise). From the literature
pass: a wide guard band not rebuilt on range exits, execution at the deepest UTC hour, band weights from the pool's fee-per-
liquidity map, a crowding cap on F. Given point 1, the refill gates are unlikely to help both assets; the band-geometry ideas
are the more promising next round.

## Next step

Run v6 and v6.75 on the forward window (ETH/USDC and WBTC/USDC after 2026-09-17, `samples/fetch_uni_minute.py`) and on the
Arbitrum / Base pools, pre-registered with the same improvement rule, before any further variant is built on top of v6.75.
