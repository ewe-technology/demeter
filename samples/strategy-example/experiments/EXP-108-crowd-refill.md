# EXP-108: no refill stage while pool liquidity is crowded (v6.95)

- Jira: QUAN-992
- Status: holdout-fail
- Pre-registration commit: 26a4143 · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

EXP-105 capped F while the pool's liquidity was crowded and cut risk on both pools, but the cap moved F back and forth and added rebuilds on WBTC (125 vs 106), costing return. Gating only the refill (no new stage while crowded; exits and deployed stages untouched) keeps the crowding information without forcing extra rebuilds.

## Change

`CROWD_REFILL = True` (variant `CU`): no refill stage fires on days whose 7-day mean active liquidity is above 1.5x its 90-day median (EXP-105's definition). No new constant.

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

Development (`A` and the variant in each invocation, tag `ACTCUCVCWCX`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +10.2% | +2.6 |
| 2023 | +32.2% | +32.2% | +0.0 |
| 2024 | +36.4% | +36.6% | +0.3 |
| 2025 | +16.3% | +26.6% | +10.4 |
| 2026-01..09-17 | +18.7% | +16.7% | -2.0 |

Wins 3/5, median +0.25 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +101.5% | 16.0% | -22.8% | 0.82 | 0.70 | $88.9k | $0.32k | 143 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +94.9% | 18.8% | -14.4% | 1.10 | 1.30 | $60.6k | $0.62k | 96 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | -9.9% | -11.8% | -13.0% | -0.45 | -0.91 | $10.9k | $0.15k | 18 |

Verdict: **holdout-fail** — dev passed the improvement level on both pools with one symmetric rule (ETH CAGR 16.0% vs 14.0%, Calmar 0.70; WBTC 18.8% vs 17.3%, Calmar 1.30, max DD −14.4%; wins 3/5). Time-split holdout (run once): H5 ETH 2021 identical to v6 (the window starts on the pool's first data day; the crowding flag needs 90 days of liquidity history and never fired afterwards, so H5 says nothing); **H4 WBTC 2022 total −9.9% vs +2.4%** (CAGR −11.8%, max DD −13.0%; mean F 0.484 vs 0.630, 18 vs 17 rebuilds, fees $10.9k vs $14.3k, measured). Blocking refills while the 2022 pool was crowded lowered exposure and still lost more than v6 (not decomposed). The dev gain does not hold out of time.

## Deviations

- Designed after EXP-102..106's dev and holdout results (EXP-103 / 104 passed the time-split holdout as fee-tier rules; EXP-105's crowding cap cut risk on both pools but lost WBTC return through extra rebuilds). EXP-110 / 111 are fee-tier rules built from rules whose dev results are known (only the holdout judges them; their WBTC halves, EXP-098 and EXP-087, and EXP-106's ETH half have not been run on H4 / H5 before, except EXP-087 inside EXP-104). Whether fee-tier rules count is Dino's call. Band shape (uniform / gaussian / exponential) was considered and not registered: classified as tuning in `RESEARCH-2026-09-30-lp-literature.md`. Smoke test WBTC 2023-09-01..10-31 (`A,CT,CU,CV,CW,CX`): all execute; CT, CU and CV end identical there (0.0581 vs v6 0.0952; CU rerun alone gives the same value), read as the window's one refill being delayed past the window end by each gate; to be checked on the dev run (they must differ over 4 years).
