# EXP-146: fee tier: EXP-124's WBTC half + cross-asset refill, EXP-130's ETH half (v6.132)

- Jira: QUAN-1031
- Status: holdout-fail
- Pre-registration commit: f35df2e · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

The cross-asset filter added to the best WBTC half (stop + volume + routing).

## Change

fee >= 0.3%: `INTRADAY_STOP`, `REFILL_VOL_CONFIRM`, `SWAP_ROUTE = pool`, `REFILL_GATE = xasset`; below 0.3%: `REFILL_NO_NEW_LOW`, `REFILL_GATE = xasset`. Variant `EH`.

## Pre-registration

Pre-registered together with EXP-144..148 (same commit), run with `A` (v6) in `A,EF,EG,EH,EI,EJ` per window.

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

Development (`A` and the variant in each invocation, tag `AEFEGEHEIEJ`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +13.7% | +6.1 |
| 2023 | +32.2% | +38.9% | +6.7 |
| 2024 | +36.4% | +34.9% | -1.4 |
| 2025 | +16.3% | +17.3% | +1.0 |
| 2026-01..09-17 | +18.7% | +19.1% | +0.4 |

Wins 4/5, median +1.04 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +108.6% | 16.9% | -24.7% | 0.85 | 0.68 | $94.5k | $0.34k | 136 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +90.0% | 18.0% | -15.0% | 1.04 | 1.20 | $53.3k | $-4.83k | 94 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +16.0% | 25.4% | -25.4% | 0.80 | 1.00 | $25.3k | $3.33k | 31 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +1.5% | 1.8% | -11.3% | 0.19 | 0.16 | $11.8k | $-0.52k | 15 |

Verdict: **holdout-fail (fee-tier rule)** — dev passed: ETH = EXP-130 (16.9%), WBTC 18.0% vs 17.3% (EXP-124 without the cross-asset filter: 21.0%). Holdout: H5 ETH = EXP-130 (+16.0%); H4 WBTC 2022 +1.5% vs v6 +2.4% (EXP-124: +9.6%). The cross-asset refill costs the WBTC half 8 pts out of time: it belongs on the ETH pool only.

## Deviations

- Designed after EXP-139..143's dev results and before their holdout results were read. EXP-130's cross-asset refill (a refill stage also needs the other asset >= 1.05 x its low since the exit) is the only ETH-side rule besides v6.75 with its own out-of-time gain; it has never run on the 0.3% WBTC pool together with v6.75 (EXP-086 ran it alone and was dropped at dev, H4 never run). EXP-144 / 145 / 148 apply it to both pools as one rule; EXP-146 adds it to EXP-124's WBTC half (new on H4); EXP-147 merges EXP-139's and EXP-140's ETH halves (new on H5).
