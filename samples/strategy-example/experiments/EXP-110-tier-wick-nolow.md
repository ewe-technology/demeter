# EXP-110: fee tier: wick-anchored refill on 0.3%, no-new-low refill on 0.05% (v6.97)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

Fee-tier rule (as EXP-103 / 104): on pools with fee >= 0.3% the refill is measured from the intraday low (EXP-098, the strongest WBTC dev result, Calmar 1.32), on cheaper pools v6.75. Tests the wick anchor out of time on WBTC.

## Change

Variant `CW`: fee >= 0.3%: `LOW_FROM_WICK = True`; below 0.3%: `REFILL_NO_NEW_LOW = True`. Constant: the 0.3% boundary.

## Pre-registration

Pre-registered together with EXP-107..111 (same commit), run with `A` (v6) in `A,CT,CU,CV,CW,CX` per window.

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

- Designed after EXP-102..106's dev and holdout results (EXP-103 / 104 passed the time-split holdout as fee-tier rules; EXP-105's crowding cap cut risk on both pools but lost WBTC return through extra rebuilds). EXP-110 / 111 are fee-tier rules built from rules whose dev results are known (only the holdout judges them; their WBTC halves, EXP-098 and EXP-087, and EXP-106's ETH half have not been run on H4 / H5 before, except EXP-087 inside EXP-104). Whether fee-tier rules count is Dino's call. Band shape (uniform / gaussian / exponential) was considered and not registered: classified as tuning in `RESEARCH-2026-09-30-lp-literature.md`. Smoke test WBTC 2023-09-01..10-31 (`A,CT,CU,CV,CW,CX`): all execute; CT, CU and CV end identical there (0.0581 vs v6 0.0952; CU rerun alone gives the same value), read as the window's one refill being delayed past the window end by each gate; to be checked on the dev run (they must differ over 4 years).
