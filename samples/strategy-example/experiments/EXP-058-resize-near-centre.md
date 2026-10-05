# EXP-058: resize in place while the price is in the ladder's inner half, recentre otherwise (v6.45)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

EXP-055 (resize every band in place on all F changes) cut drawdowns on both assets (ETH −21.0% vs −22.8%, WBTC −13.3% vs
−17.8%, WBTC Calmar 1.22 vs 0.97) but lost ETH fees ($81.6k vs $86.5k): without recentring, the ladder kept sizing liquidity
around a centre the price had left. The two effects should separate by where the price is: near the build centre a recentre
changes little about where the liquidity sits but still realises the IL and pays the swap (the cost EXP-055 removed); far
from it the recentre re-concentrates liquidity at the price (the benefit EXP-055 lost). Resizing only while the price is in
the inner half of the ladder, and recentring as v6 does otherwise, should keep most of the drawdown gain and most of v6's fees.
This is a follow-up of a failed experiment with one new element (the position test); it is reported as a near-copy of EXP-055.

## Change

`RESIZE_NEAR_CENTRE = True` (variant `AU`): on a follow event (|F − deployed| ≥ 12.5%, ladder deployed, target > 0), if the
price tick is within a quarter of the ladder's tick span (half of each side's reach, about ±10% in price) of the tick of the last
full build, the ladder is resized in place exactly as in EXP-055; otherwise v6's full rebuild. Range exits, first builds and
builds from an empty book are v6's. The one constant (inner half of the ladder) is the ladder's own geometry, the same
half-width EXP-023 used; it was chosen over one band width (≈ ±2.3%, which would almost never trigger after the staged refills
of ≥ 5%) before any run of this variant on more than the 3.5-week smoke window.

## Pre-registration

Pre-registered together with EXP-059 (same commit) and run in the same invocations as `A` (v6).

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

- Designed after seeing EXP-055's dev result (that is its motivation). Smoke test ETH 2023-06-01..06-25 (`A,AU`): totals printed
  (both −4.2%), 2 resizes. The first draft used one band width as the threshold; it was replaced by the inner half before any
  longer run, for the reason given under *Change*.
