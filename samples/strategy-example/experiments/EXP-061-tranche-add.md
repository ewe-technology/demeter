# EXP-061: F increases add a new tranche at today's price; existing liquidity is never recentred (v6.48)

- Jira: QUAN-943
- Status: pre-registered
- Pre-registration commit: c4f9b71 · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

Two findings of this goal pull in opposite directions. (1) On the 0.3% WBTC pool every full rebuild is expensive: v6 pays about
$8.5k of pool fee on $2.8M of rebuild swaps against $61.7k of LP fees (≈ 14%; ETH 0.05%: $1.8k of $86.5k), and keeping the old
ticks helped WBTC's drawdown (EXP-055: max DD −13.3% vs −17.8%). (2) On ETH, liquidity placed around today's price pays
(EXP-055 lost ETH fees by adding to the old ticks; EXP-023 and EXP-059's extra recentres raised ETH's return). Placing only
the *new* money at today's price serves both: when F rises (staged refills, usually on a rebound) the increment becomes a new
17-band tranche centred on the current price at the target ETH share (one swap for the increment, not for the whole book);
when F falls the bands shrink in place (no recentre, no realised IL on the rest); the existing liquidity is rebuilt only at a
range exit. Overlapping tranches built at different prices also spread the liquidity (staggered ladders, Newfound Research's
"rebalance timing luck"; Fan et al. 2023 multi-position allocations). Expected: rebuild swap notional falls sharply (cost ↓, most
on WBTC), new capital still sits at the price (ETH fees kept) → CAGR up on both, drawdown similar or shallower.

## Change

`TRANCHE_ADD = True` (variant `AX`). On a follow event (|F − deployed| ≥ 12.5%) with a deployed ladder:
- target > current: (target − current) x equity is placed as a new 17-band valley centred on today's price, ETH share by v6's
  rule (70% / 50%); the base it needs is bought with quote (pool fee and impact charged); bands with identical ticks merge.
- 0 < target < current: every band's liquidity x target/current (EXP-055's shrink; the withdrawn base sold for quote).
The range-exit check uses the union of all tranches (lowest lower tick to highest upper tick); a range exit, a first build, a
build from an empty book and F = 0 stay v6's full rebuilds (which merge everything back into one ladder). No constants.

## Pre-registration

Pre-registered together with EXP-062 (same commit) and run in the same invocations as `A` (v6).

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev windows,
  warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC 0.3%
  2022-01-01..2022-10-31. v6's numbers there are known (EXP-040..060); this variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

(pending)

## Deviations

- Designed after EXP-055..060 (their results are the motivation). EXP-061 and EXP-062 are near-copies of EXP-055 (they share its
  shrink step) and of each other; they are not independent evidence.
- Smoke test (variant only): ETH 2023-06-01..06-25, two tranche adds (15 → 31 → 46 bands); WBTC 2024-03-01..25 with `AX,AY`
  (no follow event there, both equal). No v6 number was printed on a new window.
