# EXP-088: refill days count only without a new intraday low (v6.75)

- Jira: QUAN-972
- Status: holdout-pass
- Pre-registration commit: 0f8cc14 · Result commit: ______
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

Development (`A` and the variant in each invocation, tag `ABZCACBCCCD`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +8.1% | +0.5 |
| 2023 | +32.2% | +38.9% | +6.7 |
| 2024 | +36.4% | +35.8% | -0.5 |
| 2025 | +16.3% | +16.7% | +0.5 |
| 2026-01..09-17 | +18.7% | +19.1% | +0.4 |

Wins 4/5, median +0.47 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +96.6% | 15.4% | -24.3% | 0.78 | 0.64 | $89.5k | $0.33k | 146 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +87.8% | 17.6% | -18.2% | 1.01 | 0.97 | $60.2k | $0.74k | 105 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +13.5% | 21.4% | -27.0% | 0.71 | 0.79 | $25.0k | $3.34k | 33 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +2.8% | 3.4% | -12.2% | 0.26 | 0.28 | $14.3k | $0.04k | 17 |

Verdict: **holdout-pass (improvement level)** — dev: ETH CAGR 15.4% vs 14.0%, Calmar 0.64 vs 0.61, max DD −24.3% vs −22.8% (within 3 pts), wins 4/5; WBTC CAGR 17.6% vs 17.3%, Calmar 0.97 vs 0.97, max DD −18.2% vs −17.8%. Time-split holdout (run once): H5 ETH 2021-05..12 total +13.5% vs +4.5%, CAGR 21.4% vs 7.0%, Calmar 0.79 vs 0.23, max DD −27.0% vs −30.7%; H4 WBTC 2022-01..10 total +2.8% vs +2.4%, CAGR 3.4% vs 2.9%, Calmar 0.28 vs 0.23, max DD −12.2% vs −12.5%. First improvement-level pass of the two goals (EXP-052..091). Reading: the rule only removes refill days whose intraday low retests the low since the exit, so it delays refills into wick retests and keeps every other v6 rule; the rule barely touches WBTC (dev: 105 vs 106 rebuilds, mean F 0.666 vs 0.672; H4: 17 vs 17 rebuilds, mean F 0.63 both), so WBTC's pass (+0.3 pt CAGR dev, +0.5 pt H4) is near noise and the result is an ETH improvement that does not hurt WBTC. On ETH the H5 window shows fewer rebuilds (33 vs 37) and more LP fees ($25.0k vs $21.0k). Not yet checked: a third, later window (data after 2026-09-17).

## Deviations

- Ideas 5, 7, 8, 9 and 15 of the 2026-10-05 literature pass (fourth agent run). Designed after EXP-082..086's dev results (all dropped: non-price refill gates help one asset and hurt the other). Smoke test WBTC 2023-09-01..10-31 (`BZ,CA,CB,CC,CD`, no v6 run): all execute, totals differ between variants.
- While the dev run was in progress the EXP-092..096 code (patch19) was written into the strategy files and reverted before the 2025 / 2026 segments started (they ran on commit 0f8cc14's code). The holdout was run once, after the dev judge.
