# Findings 2026-10-05, round 3 (EXP-092..111), interim

Goal (Dino, 2026-10-05): continue until 10 improvement-level passes (dev + time-split holdout H5 ETH/USDC 0.05% 2021-05..12,
H4 WBTC/USDC 0.3% 2022-01..10; CAGR above v6, Calmar ≥ v6, max DD no more than 3 pts deeper, ETH wins ≥ 3/5, on both).

## Count after 70 attempts under this rule (EXP-052..111)

| | passes | experiments |
|---|---|---|
| clean (one rule for both pools) | **1** | EXP-088 v6.75 (no-new-intraday-low refill) |
| fee-tier rule (one rule per fee tier) | 2, **pending Dino's ruling** | EXP-103 v6.90, EXP-104 v6.91 |

Fee-tier rules apply one switch set on pools with fee >= 0.3% and another on cheaper pools. On the two test pools that is
"v6.75 on ETH, another rule on WBTC"; whether that counts as one strategy or as two single-asset versions is Dino's call.

## Round 3 results (20 experiments)

| EXP | version | change | outcome |
|---|---|---|---|
| 092 | v6.79 | no refill 3 days after a gas spike | dropped (≈ v6) |
| 093 | v6.80 | refill only while stablecoin supply grows | dropped (both worse) |
| 094 | v6.81 | no weekend refill | dropped (both worse) |
| 095 | v6.82 | EMA exit needs pool volume | dropped (ETH 11.2%) |
| 096 | v6.83 | refill only on pool net buying | dropped |
| 097 | v6.84 | EMA exit only on a full day below the EMA | dropped (ETH 7.8%) |
| 098 | v6.85 | refill from the intraday low | dropped (WBTC Calmar 1.32, ETH 4.2%) |
| 099 | v6.86 | up-day refill | dropped (ETH up, WBTC down) |
| 100 | v6.87 | strong-close refill | dropped (ETH up, WBTC down) |
| 101 | v6.88 | lower stop on the intraday low | dropped (WBTC up, ETH down) |
| 102 | v6.89 | tier: wick on 0.3%, up-day on 0.05% | dropped (ETH wins 2/5) |
| **103** | **v6.90** | **tier: intraday stop on 0.3%, v6.75 on 0.05%** | **holdout-pass (tier)**: H4 WBTC +7.1% vs +2.4% |
| **104** | **v6.91** | **tier: volume refill on 0.3%, v6.75 on 0.05%** | **holdout-pass (tier)**: H4 WBTC +6.9% vs +2.4% |
| 105 | v6.92 | F ≤ 50% while liquidity is crowded | dropped (risk down on both, WBTC CAGR −0.7 pt) |
| 106 | v6.93 | v6.75 + two-day exit confirmation | dropped (ETH 17.2%, WBTC 16.7%) |
| 107 | v6.94 | longer wait after a failed refill | dropped (both worse) |
| 108 | v6.95 | no refill while liquidity is crowded | **dev pass, holdout-fail** (H4 WBTC −9.9%) |
| 109 | v6.96 | 108 + v6.75 | **dev pass, holdout-fail** (H4 WBTC −9.5%) |
| 110 | v6.97 | tier: wick on 0.3%, v6.75 on 0.05% | **holdout-fail** (H4 WBTC −11.0%) |
| 111 | v6.98 | tier: volume on 0.3%, v6.75 + confirm on 0.05% | dropped (ETH wins 2/5) |

## What round 3 adds

1. **The ETH / WBTC split is the rule, not the exception.** Of 20 rules, every one that changed refill speed helped one pool
   and hurt the other: faster or cleaner refills help the 0.05% ETH pool, slower and fewer refills help the 0.3% WBTC pool
   (six times the swap cost per rebuild). Only rules that barely bind on one pool (v6.75 on WBTC) pass on both.
2. **H4 (WBTC 2022 bear) is a hard filter.** Three dev passes failed there (EXP-108, 109, 110), including the symmetric
   crowding gate and the strongest WBTC dev rule (wick-anchored refill, Calmar 1.32 at dev, −11% on H4). Two WBTC rules
   survived it: the intraday lower stop (EXP-101's rule) and the volume-confirmed refill (EXP-087's rule).
3. **Ideas rejected before registration**: Coinbase premium (USDT basis noise), execution at the deepest hour (±4% depth
   by hour, impact $0.3k of ETH's 4-year cost), band shape changes (tuning, per the 2026-09-30 literature note).

## Open decision (blocks the search direction)

If fee-tier rules count, the search continues with "WBTC rule x v6.75" pairs, each judged on H4 (new evidence per WBTC
rule) and the count is 3. If not, the search continues with symmetric rules only, where 70 attempts produced 1 pass.
Either way, before any of these replaces v6: a forward window (data after 2026-09-17) and the Arbitrum / Base pools.
