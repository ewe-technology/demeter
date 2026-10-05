# EXP-087: refill stages only while pool volume confirms the rebound (v6.74)

- Jira: QUAN-971
- Status: dropped-at-dev
- Pre-registration commit: 0f8cc14 · Result commit: b48fc64
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

Fees scale with swap volume, so redeploying into a thin-volume bounce is LVR without the fee income that pays for it. The pool's own volume (the variable the valley actually earns from) confirms whether a rebound is being traded. Requiring the 3-day swap volume to be at least its 30-day median when a refill stage fires keeps the refills where the LP gets paid; same rule on both pools, no external data (What drives liquidity on DEXs, arXiv 2410.19107).

## Change

`REFILL_VOL_CONFIRM = True` (variant `BZ`): a stage fires only if the pool's 3-day quote-token swap volume is ≥ the median of that 3-day sum over the last 30 days (unknown at the window start → no block). Constants: 3 days (the refill's own confirmation length) and the 30-day median.

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
| 2022 | +7.6% | +5.4% | -2.2 |
| 2023 | +32.2% | +33.3% | +1.1 |
| 2024 | +36.4% | +34.0% | -2.4 |
| 2025 | +16.3% | +9.1% | -7.2 |
| 2026-01..09-17 | +18.7% | +12.1% | -6.6 |

Wins 1/5, median -2.41 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +66.3% | 11.4% | -21.5% | 0.64 | 0.53 | $73.7k | $0.27k | 131 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +92.6% | 18.4% | -14.9% | 1.08 | 1.23 | $62.1k | $0.70k | 97 |

Verdict: **dropped-at-dev** — WBTC improves (CAGR 18.4% vs 17.3%, Calmar 1.23 vs 0.97, max DD −14.9% vs −17.8%) but ETH falls (CAGR 11.4% vs 14.0%, Calmar 0.53), wins 1/5. Holdout not run. Reading: on the 0.3% WBTC pool a thin-volume rebound earns too little to pay its rebuild, so waiting for volume helps; on the 0.05% ETH pool the gate delays refills into the rebounds that carry v6's edge. Same ETH/WBTC split as round 1's recentring results.

## Deviations

- Ideas 5, 7, 8, 9 and 15 of the 2026-10-05 literature pass (fourth agent run). Designed after EXP-082..086's dev results (all dropped: non-price refill gates help one asset and hurt the other). Smoke test WBTC 2023-09-01..10-31 (`BZ,CA,CB,CC,CD`, no v6 run): all execute, totals differ between variants.
- While the dev run was in progress the EXP-092..096 code (patch19) was written into the strategy files and reverted before the 2025 / 2026 segments started (they ran on commit 0f8cc14's code).
