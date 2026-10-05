# EXP-089: engine on the daily TWAP instead of the 00:00 price (v6.76)

- Jira: QUAN-973
- Status: dropped-at-dev
- Pre-registration commit: 0f8cc14 · Result commit: b48fc64
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

Every engine input (EMAs, exits, stops, refill levels, share rule) is the price in one minute at 00:00 UTC; exits and refills triggered by that minute's noise are random. The daily time-weighted mean of the minute prices is the same information with less noise. Input change, not a new line: the EMA spans, stops and stages are v6's; the range-exit check and all rebuilds keep using the live price, so recentring is untouched.

## Change

`TWAP_ENGINE = True` (variant `CB`): the engine's daily series is the mean of the day's minute prices (warm-up days from Binance closes are unchanged). No constant.

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
| 2022 | +7.6% | +2.6% | -5.0 |
| 2023 | +32.2% | +37.3% | +5.1 |
| 2024 | +36.4% | +34.7% | -1.7 |
| 2025 | +16.3% | +18.4% | +2.1 |
| 2026-01..09-17 | +18.7% | +18.4% | -0.3 |

Wins 2/5, median -0.34 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +80.8% | 13.4% | -25.0% | 0.71 | 0.54 | $83.7k | $0.22k | 138 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +75.2% | 15.6% | -18.2% | 0.92 | 0.86 | $59.6k | $0.57k | 101 |

Verdict: **dropped-at-dev** — ETH CAGR 13.4% vs 14.0%, Calmar 0.54, max DD −25.0%, wins 2/5; WBTC CAGR 15.6% vs 17.3%, Calmar 0.86. Holdout not run. Reading: the daily mean lags the close by about half a day, so exits and refills come later on both assets; the 00:00 price is not the noise source the hypothesis assumed.

## Deviations

- Ideas 5, 7, 8, 9 and 15 of the 2026-10-05 literature pass (fourth agent run). Designed after EXP-082..086's dev results (all dropped: non-price refill gates help one asset and hurt the other). Smoke test WBTC 2023-09-01..10-31 (`BZ,CA,CB,CC,CD`, no v6 run): all execute, totals differ between variants.
- While the dev run was in progress the EXP-092..096 code (patch19) was written into the strategy files and reverted before the 2025 / 2026 segments started (they ran on commit 0f8cc14's code).
