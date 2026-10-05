# EXP-059: pull the ladder around scheduled FOMC and CPI releases (v6.46)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal 2026-10-05 "beat v6 at the improvement level, pure LP, time-split out-of-time holdout" (Dino); idle-capital
  yield excluded (ruling 2026-10-05).

## Hypothesis

An LP's loss-versus-rebalancing is concentrated in price jumps (Milionis et al. 2022): the arbitrageur trades the stale pool
price against the new CEX price, and the larger the jump the larger the loss per unit of fee. US macro releases (FOMC policy
statements, CPI) are the largest scheduled jumps in crypto, and their times are known in advance. EXP-016 pulled the ladder
*after* a large 5-minute move (reactive, too late: the jump had already been arbitraged); this pulls it *before* the scheduled
jump and re-adds it after the repricing, with no swap (burn and re-mint at the same ticks, gas reported only). Expected: a
small, path-independent saving of LVR on ~20 events a year, at the cost of the fees of ~50 hours a year: CAGR and Calmar up on
both assets if the release hours are net-toxic for LPs. Honest counter-evidence: fees spike in those hours too, and a ±20%
ladder loses little on a 1-3% jump (second-order IL), so the effect may be near zero.

## Change

`MACRO_EVENTS = "csv"` (variant `AV`): from `samples/macro_events_utc.csv` (107 releases 2021-05..2026-09: 43 FOMC statements at
2:00 pm ET, 64 CPI releases at 8:30 am ET, each date checked against its official release page; 2025's shutdown-delayed and
cancelled CPI releases as published; builder `samples/fetch_macro_events.py`). The ladder is pulled 30 minutes before each
release (EXP-016's `pause_ladder`: fees collected, all bands burned, no swap) and re-added 2 hours after it at the same ticks
from the tokens that came out (the (1 − F) reserve is not added: EXP-016's resume deployed it; fixed here). The daily checks
skip while paused (no release is near 00:00 UTC). Constants fixed here, not searched: 30 minutes before, 2 hours after.

## Pre-registration

Pre-registered together with EXP-058 (same commit) and run in the same invocations as `A` (v6).

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

- Idea source: literature pass 2026-10-05 (first agent run, idea 5). Calendar built by a subagent from federalreserve.gov and
  bls.gov pages; it left out the 2025-08-22 FOMC strategy statement (not a policy decision).
- Smoke tests (variant only, no v6 numbers seen on the same window): ETH 2023-06-01..06-25 (`A,AV`: identical totals −4.2%,
  no pause because F was 0 over both releases) and ETH 2024-03-01..03-25 (`AV` alone: 2 pauses, 300 minutes; total not compared).
