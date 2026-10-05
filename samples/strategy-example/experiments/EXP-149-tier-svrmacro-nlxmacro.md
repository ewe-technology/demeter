# EXP-149: fee tier: EXP-124's WBTC half + macro restore, EXP-140's ETH half (v6.135)

- Jira: QUAN-1034
- Status: holdout-pass
- Pre-registration commit: 8428450 · Result commit: 32f78f4
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

Macro restore on both pools (it added +0.4 / +0.5 pt on H5 in EXP-140 / 120 and kept WBTC within noise in EXP-126), with the refill filters chosen by fee tier.

## Change

fee >= 0.3%: `INTRADAY_STOP`, `REFILL_VOL_CONFIRM`, `SWAP_ROUTE = pool`, `MACRO_EVENTS = csv`, `MACRO_RESTORE`; below 0.3%: `REFILL_NO_NEW_LOW`, `REFILL_GATE = xasset`, `MACRO_EVENTS = csv`, `MACRO_RESTORE` (EXP-140's ETH half). Variant `EK`.

## Pre-registration

Pre-registered together with EXP-149..152 (same commit), run with `A` (v6) in `A,EK,EL,EM,EN` per window. The last four of the 30-experiment round EXP-123..152.

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

Development (`A` and the variant in each invocation, tag `AEKELEMEN`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +12.9% | +5.3 |
| 2023 | +32.2% | +39.3% | +7.1 |
| 2024 | +36.4% | +36.1% | -0.2 |
| 2025 | +16.3% | +17.4% | +1.1 |
| 2026-01..09-17 | +18.7% | +19.2% | +0.5 |

Wins 4/5, median +1.15 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +110.4% | 17.1% | -24.9% | 0.86 | 0.69 | $92.9k | $0.36k | 266 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +112.4% | 21.4% | -13.6% | 1.25 | 1.58 | $64.4k | $-5.43k | 217 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +16.4% | 26.2% | -25.3% | 0.82 | 1.03 | $25.5k | $3.32k | 53 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +9.2% | 11.2% | -11.0% | 0.59 | 1.01 | $13.7k | $-0.50k | 36 |

Verdict: **holdout-pass (improvement level), fee-tier rule** — dev: ETH = EXP-140 (17.1%, Calmar 0.69); WBTC 21.4% vs 17.3%, Calmar 1.58 (EXP-124 21.0%, 1.52). Holdout: H5 ETH = EXP-140 (+16.4%); H4 WBTC 2022 +9.2% vs +2.4%, 0.4 pt below EXP-124's +9.6%: the macro restore helps the WBTC half at dev and costs a little out of time, as on WBTC in round 3 (EXP-122). No gain over EXP-140.

## Deviations

- Designed after EXP-144..148's dev results and before their holdout results were read. EXP-140's ETH half (v6.75 + cross-asset refill + macro restore) has the best H5 so far (+16.4%); the cross-asset refill hurts the 0.3% WBTC pool (EXP-144 / 145 / 148: WBTC dev CAGR 16.8-17.0% < v6 17.3%; EXP-146: 18.0% vs EXP-124's 21.0%), so it stays on the cheap pool. EXP-149 / 150 pair EXP-140's ETH half with WBTC halves new on H4 (EXP-124's half + macro restore; + v6.75's no-new-low refill); EXP-151 adds EXP-063's account tranches to EXP-140's ETH half (new on H5); EXP-152 is a one-rule candidate: EXP-126 plus the volume-confirmed refill on every pool. Account tranches (EXP-115 / 118 / 121) were checked as a WBTC addition and skipped: with routing it would repeat EXP-121's H4 run.
