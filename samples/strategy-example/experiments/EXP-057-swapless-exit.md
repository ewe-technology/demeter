# EXP-057: range-exit rebuild from inventory, without the swap (base + limit) (v6.44)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

When the price leaves the ±20% ladder, the ladder has converted entirely into one token (all USDC after a rise, all ETH after a
fall). v6 then swaps back to the target ETH share (70% / 50%) and re-mints: after an upward exit it buys ETH at the top of the
move, after a downward exit it sells ETH at the bottom (`V6_VALIDATION.md` §5: rallies mostly given up). Charm Alpha Vaults and
Gamma hypervisors rebuild without swapping: the leftover token goes into one-sided liquidity the pool converts back while
paying the LP fees ("base + limit", https://learn.charm.fi/charm/alpha-vaults-overview/whitepaper). On v6's ladder this is a
rebuild with the swap skipped: each side's bands take all of that side's token (`build_shape_config` normalises the shares per
side), so the new ladder is bids below the price after an upward exit and asks above it after a downward exit. Expected: the
swap's fee and impact become fee income, and the ladder buys back below the exit price instead of at it → CAGR up; drawdown
risk: after a downward exit the book stays 100% ETH until the next follow rebuild or until the asks fill.
Different from EXP-005 (F refills as range orders) and EXP-006 (half ladder): this changes only the range-exit rebuild.

## Change

`SWAPLESS_EXIT = True` (variant `AT`): on a range-exit rebuild (price outside the ladder at the daily check) the swap to the
target ETH share is skipped; the reserve ((1 − F) x equity in quote) is set aside as in v6 and the 17-band valley is placed
around the current price with what is left. Follow rebuilds (F changes), the first build and builds from an empty book keep
v6's swap. No constants.

## Pre-registration

Pre-registered together with EXP-055 and EXP-056 and run in the same invocations as `A` (v6).

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

(pending)

## Deviations

- Smoke test before this file: ETH 2022-05-01..06-30 (inside the dev data), variants `A,AT`; totals printed (v6 −7.9%, this
  −13.3%: one downward exit in June 2022 left the book all ETH). The rule has no constant to adjust.
- Idea source: literature pass 2026-10-05 (second agent run, ranked ideas 1 "resize in place" = EXP-055 and 2 "base + limit" = this).
