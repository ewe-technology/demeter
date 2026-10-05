# EXP-062: asymmetric follow: shrink in place when F falls, v6 recentre when F rises (v6.49)

- Jira: QUAN-944
- Status: pre-registered
- Pre-registration commit: c4f9b71 · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

EXP-055 changed both directions of v6's follow rule at once (resize in place on F up and on F down) and lost ETH fees while
cutting drawdowns. The two directions do different things. F falls when accounts exit (close below an EMA or the lower stop):
v6 then burns the whole ladder, swaps it back to the target share and re-mints a smaller ladder around the falling price —
a recentre into weakness that realises the IL of the drop on all of the remaining liquidity. Shrinking in place only removes
the liquidity that should go and leaves the rest where it is (no swap of the remaining book). F rises on staged refills during
a rebound: there v6's recentre at today's price is what ETH rewards (EXP-023, EXP-059's extra recentres). This variant keeps
v6 on the way up and shrinks in place on the way down: it isolates the down side of EXP-055. Expected: lower swap cost and less
realised IL in sell-offs (drawdown ↓ on both assets) with v6's fee capture in recoveries (CAGR ≥ v6).

## Change

`FOLLOW_ASYM = True` (variant `AY`): on a follow event with a deployed ladder and 0 < target < current, every band's liquidity
x target/current (EXP-055's shrink; withdrawn base sold for quote); target > current, F = 0, range exits and builds from an
empty book are v6's full rebuilds. No constants.

## Pre-registration

Pre-registered together with EXP-061 (same commit) and run in the same invocations as `A` (v6).

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

- Designed after EXP-055's result; a near-copy of EXP-055 and of EXP-061 (shared shrink step), not independent evidence.
- Smoke test (variant only): WBTC 2024-03-01..25 with `AX,AY` (no follow event, both equal).
