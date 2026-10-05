# EXP-088: refill days count only without a new intraday low (v6.75)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

v6 measures the rebound on 00:00 closes; a day whose intraday low retests or breaks the low since the exit is not a rebound, whatever its close. Counting a day for a refill stage only when its intraday low (minute data) stays above the low since the exit uses information the daily engine discards and filters wick retests, symmetric for both pools.

## Change

`REFILL_NO_NEW_LOW = True` (variant `CA`): the stage-1 confirmation counter and stages 2-4 advance only on days whose minute low is above the account's lowest close since the exit. No constant.

## Pre-registration

Pre-registered together with EXP-087..091 (same commit), run with `A` (v6) in `A,BZ,CA,CB,CC,CD` per window.

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

- Ideas 5, 7, 8, 9 and 15 of the 2026-10-05 literature pass (fourth agent run). Designed after EXP-082..086's dev results (all dropped: non-price refill gates help one asset and hurt the other). Smoke test WBTC 2023-09-01..10-31 (`BZ,CA,CB,CC,CD`, no v6 run): all execute, totals differ between variants.
