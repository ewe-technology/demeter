# EXP-097: EMA exit only on a full day below the EMA (v6.84)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

v6 exits an account on a close below its EMA, even when the price traded above the EMA earlier that day. A day that reclaimed the EMA intraday and closed just below it is a test of the line, not a breakdown; exiting there pays a rebuild and often refills higher. Requiring the day's minute high to be below the EMA as well keeps exits for days the market spent entirely under the line. The lower stop is not gated, so crash protection is unchanged.

## Change

`EXIT_FULL_DAY = True` (variant `CJ`): the EMA exit of an armed account fires only if the day's close and its minute high are both below that account's EMA; otherwise the account stays armed and is checked again the next day. No constant.

## Pre-registration

Pre-registered together with EXP-097..101 (same commit), run with `A` (v6) in `A,CJ,CK,CL,CM,CN` per window.

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev windows,
  warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC 0.3%
  2022-01-01..2022-10-31. v6's numbers there are known (EXP-040..081) and both windows have been used for other variants; this
  variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

(pending)

## Deviations

- Designed after EXP-088 (v6.75) passed and while EXP-092..096's dev run was in progress (their results not seen). The family follows v6.75's reading: no new signal, v6's daily rules read on the day's minute path (open, high, low) instead of the close alone. Goal: Dino, 2026-10-05, continue until 10 improvement-level passes (attempt count reported with every pass). Smoke test WBTC 2023-09-01..10-31 (`A,CJ,CK,CL,CM,CN`) before registration: all execute; v6 +9.5%, CN identical to v6 there (no stop in that window), the others differ.
