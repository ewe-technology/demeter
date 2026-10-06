# Findings 2026-10-05, round 3 (EXP-092..122, EXP-117 by another session)

Goal (Dino, 2026-10-05): continue until 10 improvement-level passes (dev + time-split holdout H5 ETH/USDC 0.05% 2021-05..12,
H4 WBTC/USDC 0.3% 2022-01..10; CAGR above v6, Calmar ≥ v6, max DD no more than 3 pts deeper, ETH yearly wins ≥ 3/5, on both).
Dino later said "keep searching until 10 passes" without ruling on fee-tier rules; they were counted toward the 10 and labelled.
(Update 2026-10-06: Dino ruled that fee-tier rules count; see `FINDINGS-2026-10-06-round4.md`. The text below is as written on
2026-10-05.)

## Result: 11 passes, of which 2 are one rule for both pools

| EXP | version | rule | kind | H5 ETH 2021 total (v6 +4.5%) | H4 WBTC 2022 total (v6 +2.4%) |
|---|---|---|---|---|---|
| 088 | v6.75 | refill days count only without a new intraday low | **clean** | +13.5% | +2.8% |
| 122 | v6.109 | v6.75 + macro pause with exact restore | **clean** | +14.0% | +2.7% |
| 103 | v6.90 | tier: intraday stop on 0.3%, v6.75 on 0.05% | fee-tier | +13.5% | +7.1% |
| 104 | v6.91 | tier: volume-confirmed refill on 0.3%, v6.75 on 0.05% | fee-tier | +13.5% | +6.9% |
| 112 | v6.99 | tier: stop + volume on 0.3%, v6.75 on 0.05% | fee-tier | +13.5% | **+9.2%** |
| 114 | v6.101 | tier: no lower stop + volume on 0.3%, v6.75 | fee-tier | +13.5% | +7.8% |
| 115 | v6.102 | tier: tranches + stop on 0.3%, v6.75 | fee-tier | +13.5% | +7.6% |
| 118 | v6.105 | tier: tranches + volume on 0.3%, v6.75 | fee-tier | +13.5% | +5.6% |
| 119 | v6.106 | tier: no lower stop + tranches on 0.3%, v6.75 | fee-tier | +13.5% | +5.4% |
| 120 | v6.107 | tier: stop + volume on 0.3%, v6.75 + macro restore | fee-tier | +14.0% | +9.2% |
| 121 | v6.108 | tier: stop + volume + tranches on 0.3%, v6.75 | fee-tier | +13.5% | +7.8% |

Attempts under this rule: EXP-052..122 (70 by this goal series, plus EXP-117 by the other session) = 71.

## How much evidence this is (read before using any of it)

1. **It is about four findings, not eleven.** Every pass uses v6.75 on ETH (EXP-120 / 122 add the macro restore, +0.5 pt on
   H5). The nine fee-tier passes differ only in the WBTC half, which is always a combination of four rules that each won H4
   alone: intraday lower stop (EXP-101), volume-confirmed refill (EXP-087), no lower stop (EXP-066), account tranches (EXP-063).
   The independent out-of-time facts are: v6.75 wins H5 on ETH; each of those four WBTC rules wins H4 on WBTC; combinations
   mostly do not add (best: stop + volume, +9.2%; adding tranches lowers it to +7.8%).
2. **The two clean passes are ETH improvements.** On WBTC both are within noise of v6 (+0.4 / +0.3 pt on H4, +0.3 / +0.5 pt
   at dev). EXP-122 also more than doubles rebuilds (WBTC dev 231 vs 106); gas is reported, not charged, so on chain it would
   most likely lose the WBTC margin.
3. **Fee-tier rules are one rule per pool.** On the two test pools "fee >= 0.3%" means "WBTC" and "fee < 0.3%" means "ETH".
   The economic reason (a rebuild swap costs six times more on the 0.3% pool) is real, but nothing here tests it on a third
   pool; Dino's ruling on whether these count is still open.
4. **Multiple testing.** 71 attempts, each holdout window reused for every attempt; H4 and H5 are each one 8-10 month episode.
   The clean test for all of them is the forward window (data after 2026-09-17) and the Arbitrum / Base pools.

## What the round taught

- **Speed of refill splits the assets.** Every rule that changes refill speed helps one pool and hurts the other: the 0.05%
  ETH pool earns from fast, clean refills, the 0.3% WBTC pool from fewer, later ones. Only rules that barely bind on one pool
  (v6.75 on WBTC) pass on both. This is why the fee-tier route was taken.
- **H4 (WBTC 2022 bear) is the real filter**: three dev passes failed it (EXP-108 crowd-gated refill −9.9%, EXP-109,
  EXP-110 wick-anchored refill −11.0%). Four WBTC rules survived it (listed above).
- **Routing (EXP-117, other session):** routing WBTC rebuild swaps through the 0.05% tier alone took WBTC from 17.3% to 18.2%
  CAGR at dev (Calmar 1.10). Dino ruled routing a strategy change. It has not been run on H4, and "v6.75 + route every swap
  through the cheapest tier" would be one rule for both pools (a no-op on the 0.05% ETH pool): the most promising next
  clean candidate. Implementation note from that session: `SWAP_ROUTES.get(POOL)` must be used so that a pool without a
  route keeps v6's ledger.

## Queued, not registered

- v6.75 + cheapest-tier routing (one rule for both pools), and routing stacked on the four H4-winning WBTC rules.
- v6.75 + one ETH-only dev winner (breadth cap, cross-asset refill, up-day / strong-close refill, funding cap), each new on
  H5 (drafted as EXP-123..127, not registered: the goal was reached first).

## Next step

Before anything replaces v6: download ETH/USDC 0.05% and WBTC/USDC 0.3% minute data after 2026-09-17
(`samples/fetch_uni_minute.py`), pre-register one forward-window test of v6.75, EXP-112 and EXP-122 against v6, and decide
the fee-tier question.
