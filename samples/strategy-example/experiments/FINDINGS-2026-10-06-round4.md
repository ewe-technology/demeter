# Findings 2026-10-06, round 4 (EXP-123..152; EXP-128 / 133 by another session)

Goal (Dino, 2026-10-06): "算，繼續找，30個": fee-tier rules count, keep searching for 30 more experiments (read as 30
attempts, EXP-123..152; the two other-session numbers in that range are not counted). Same bar as round 3: improvement level on
dev and on the time-split holdout (H5 ETH/USDC 0.05% 2021-05-06..12-31, H4 WBTC/USDC 0.3% 2022-01-01..10-31, `BINANCE_WARM=1`):
CAGR above v6, Calmar >= v6, max DD no more than 3 pts deeper, ETH yearly wins >= 3/5. Own rule for fee-tier pairs: at least
one half must not have run on its holdout window before.

## Result: 16 passes, 4 of them one rule for both pools

| EXP | version | rule | kind | H5 ETH 2021 total (v6 +4.5%) | H4 WBTC 2022 total (v6 +2.4%) |
|---|---|---|---|---|---|
| 123 | v6.110 | v6.75 + cheapest-tier swap routing | **clean** | +13.5% | +3.4% |
| 126 | v6.113 | v6.75 + macro restore + routing | **clean** | +14.0% | +3.3% |
| 137 | v6.123 | v6.75 + routing + rebuild on every F rise | **clean** | +13.6% | +3.7% |
| 142 | v6.128 | v6.75 + routing + macro restore + rise rebuild | **clean** | +14.0% | +3.4% |
| 124 | v6.111 | tier: stop + volume + routing on 0.3%, v6.75 on 0.05% | fee-tier | +13.5% | **+9.6%** |
| 125 | v6.112 | tier: no lower stop + routing on 0.3%, v6.75 | fee-tier | +13.5% | +4.2% |
| 130 | v6.116 | tier: EXP-124's WBTC half, v6.75 + cross-asset refill | fee-tier | +16.0% | +9.6% |
| 134 | v6.120 | tier: EXP-124's WBTC half, v6.75 + rise rebuild | fee-tier | +13.6% | +9.6% |
| 138 | v6.124 | tier: EXP-124's WBTC half, v6.75 + rise + share-flip rebuilds | fee-tier | +12.4% | +9.6% |
| 139 | v6.125 | tier: EXP-124's WBTC half, EXP-130's ETH half + rise | fee-tier | +16.0% | +9.6% |
| 140 | v6.126 | tier: EXP-124's WBTC half, EXP-130's ETH half + macro restore | fee-tier | +16.4% | +9.6% |
| 141 | v6.127 | tier: EXP-124's WBTC half + rise, EXP-130's ETH half | fee-tier | +16.0% | +7.5% |
| 147 | v6.133 | tier: EXP-124's WBTC half, EXP-130's ETH half + rise + macro | fee-tier | **+16.5%** | +9.6% |
| 149 | v6.135 | tier: EXP-124's WBTC half + macro restore, EXP-140's ETH half | fee-tier | +16.4% | +9.2% |
| 150 | v6.136 | tier: EXP-124's WBTC half + no-new-low refill, EXP-140's ETH half | fee-tier | +16.4% | **+10.1%** |
| 151 | v6.137 | tier: EXP-124's WBTC half, EXP-140's ETH half + account tranches | fee-tier (beats v6 only) | +6.1% | +9.6% |

Failed: EXP-127, 129, 132, 135, 136, 143, 144, 145, 148 (dropped at dev), EXP-131, 146 (holdout-fail), EXP-152 (dropped at dev). 30 attempts, 16 passes; with rounds 2-3, 27 passes since EXP-088.

## How much evidence this is (read before using any of it)

1. **About four small new findings, not sixteen.** The independent out-of-time facts this round added:
   - **Routing the WBTC rebuild swap through the 0.05% tier** (EXP-123 / 124): +1.0 pt on H4 over v6.75 alone (+3.4% vs
     +2.8%), +0.4 pt on top of stop + volume (+9.6% vs EXP-112's +9.2%). It is a modelled fee rebate, so it is as good as
     the routing cost model (`route_frame`, 0x4585 WBTC/WETH 0.05% then 0x88e6).
   - **Cross-asset refill on ETH** (EXP-130): a refill stage also needs BTC >= 1.05 x its low since the exit. H5 +16.0% vs
     v6.75's +13.5% (+2.5 pts). The only new ETH-side rule this round with its own out-of-time gain. On WBTC (needing ETH's
     rebound) it fails: dev CAGR below v6 in EXP-144 / 145 / 148, H4 +1.5% in EXP-146.
   - **v6.75's no-new-low filter also helps the best WBTC half a little** (EXP-150): H4 +10.1% vs EXP-124's +9.6% (+0.5 pt),
     the same size as v6.75's own H4 gain over v6 (+0.4 pt). Small; one 10-month window.
   - **Macro restore adds a little on ETH** (EXP-140: +0.4 pt on H5 over EXP-130; EXP-120 / 122 in round 3: +0.5 pt), at the
     price of about twice the rebuilds (gas reported, not charged). On WBTC it costs a little out of time (EXP-149: H4 +9.2%
     vs +9.6%).
   Account tranches on ETH are harmful out of time (EXP-151: H5 +6.1% vs EXP-140's +16.4%; it clears the bar against v6 only).
   Everything else is a recombination: the WBTC half of 10 of the fee-tier passes is EXP-124's (the same H4 run, +9.6%).
2. **Rebuild timing (rise rebuild, share-flip rebuild) did not carry out of time.** The rise rebuild adds about 1 pt of ETH
   CAGR at dev every time, and +0.0 / +0.1 pt on H5 (EXP-134 / 137 / 139 / 142 / 147); on WBTC it costs 2.1 pts on H4
   (EXP-141). The share-flip rebuild lost yearly wins (EXP-135 / 136) or H5 (EXP-138 +12.4% < v6.75's +13.5%).
   Treat both as dev-only effects.
3. **The four clean passes are the same ETH result.** All four are v6.75 on ETH (+13.5..14.0% on H5) and v6.75 + routing on
   WBTC (+3.3..3.7% on H4, vs v6 +2.4% and v6.75 +2.8%): one finding (v6.75) plus one cost model (routing).
4. **Fee-tier rules are one rule per pool.** On the two test pools "fee >= 0.3%" means WBTC and "below 0.3%" means ETH; no
   third pool tests the split.
5. **Multiple testing.** About 100 attempts since EXP-052 have reused the same two holdout windows; H4 and H5 are each one
   8-10 month episode. The clean test is the forward window (after 2026-09-17) and the Arbitrum / Base pools
   (`INVENTORY.md`).

## What the round taught

- **Refill speed still splits the assets**, now with a second axis: what confirms a refill. Price-path filters on the asset
  itself (no new low) work on both pools; filters that look at the other asset (cross-asset) or at flow (volume) work on one
  pool only: cross-asset on ETH, volume on WBTC (EXP-152: volume on ETH dropped ETH to 13.7%, wins 1/5).
- **Rebuilding more often looks good at dev and does not hold.** Rise / share-flip rebuilds, the macro restore's doubled
  rebuild count and the two-day exit confirmation (EXP-143: highest dev ETH CAGR 18.4%, wins 2/5) all move gains between
  years rather than add them.
- **Best candidates to carry forward** (one per kind): clean EXP-126 (v6.75 + macro restore + routing) or EXP-123 without the
  macro restore if gas matters; fee-tier EXP-140 (EXP-124's WBTC half, v6.75 + cross-asset refill + macro restore on ETH), or EXP-150, the same with v6.75's no-new-low filter added on WBTC (best H4, +10.1%; no macro restore
  on WBTC, so no doubled WBTC rebuilds).

## Next step

The forward window (data after 2026-09-17; `samples/fetch_uni_minute.py`) and a third pool on another chain, run once for
v6, v6.75, EXP-126, EXP-140 and EXP-150, decide whether any of this is real. No more combinations on H4 / H5: the remaining
recombinations of known halves cannot add out-of-time evidence.
