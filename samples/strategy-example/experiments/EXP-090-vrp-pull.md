# EXP-090: one refill stage less while realised vol exceeds implied vol (v6.77)

- Jira: QUAN-974
- Status: dropped-at-dev
- Pre-registration commit: 0f8cc14 · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

When 7-day realised volatility is above DVOL, the market is in a shock the options market did not price, and an LP's LVR exceeds its fee budget. Unlike EXP-053 (scaling F by vol level, which cut where v6 earns) this uses the sign of the implied-minus-realised spread, a rarer state.

## Change

`VRP_PULL = True` (variant `CC`): F = max(0, F − 0.25) on days whose 7-day realised vol (std of daily log returns x √365, %) is above the asset's DVOL. Constants: 7 days and one stage (0.25).

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
| 2022 | +7.6% | -2.8% | -10.4 |
| 2023 | +32.2% | +34.0% | +1.8 |
| 2024 | +36.4% | +17.2% | -19.1 |
| 2025 | +16.3% | +26.5% | +10.2 |
| 2026-01..09-17 | +18.7% | +17.4% | -1.3 |

Wins 2/5, median -1.29 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +78.7% | 13.1% | -21.7% | 0.71 | 0.61 | $72.3k | $0.28k | 237 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +74.6% | 15.5% | -22.4% | 0.84 | 0.69 | $34.0k | $0.90k | 178 |

Verdict: **dropped-at-dev** — ETH CAGR 13.1% vs 14.0%, Calmar 0.61 = v6, wins 2/5; WBTC CAGR 15.5% vs 17.3%, Calmar 0.69, max DD −22.4% vs −17.8%. Holdout not run. Reading: realised vol above DVOL is most often a rebound's own move, so pulling a stage cuts the refill where v6 earns; on WBTC the extra F changes also add rebuilds.

## Deviations

- Ideas 5, 7, 8, 9 and 15 of the 2026-10-05 literature pass (fourth agent run). Designed after EXP-082..086's dev results (all dropped: non-price refill gates help one asset and hurt the other). Smoke test WBTC 2023-09-01..10-31 (`BZ,CA,CB,CC,CD`, no v6 run): all execute, totals differ between variants.
- While the dev run was in progress the EXP-092..096 code (patch19) was written into the strategy files and reverted before the 2025 / 2026 segments started (they ran on commit 0f8cc14's code).
