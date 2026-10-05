# EXP-106: v6.75 plus two-day range-exit confirmation (v6.93)

- Jira: QUAN-990
- Status: dropped-at-dev
- Pre-registration commit: 89f53b2 · Result commit: 26a4143
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

Two structural rules that each passed a holdout, combined: v6.75's no-new-low refill (EXP-088, improvement level) and the two-day range-exit confirmation (EXP-044 / v6.31, standalone level, neutral vs v6). The first cleans the refill, the second removes one-day range-exit whipsaws; they act on different parts of v6 and should add.

## Change

Variant `CS`: `REFILL_NO_NEW_LOW = True` and `EXIT_CONFIRM = 2`. No new constant.

## Pre-registration

Pre-registered together with EXP-102..106 (same commit), run with `A` (v6) in `A,CO,CP,CQ,CR,CS` per window.

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

Development (`A` and the variant in each invocation, tag `ACOCPCQCRCS`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +9.3% | +1.7 |
| 2023 | +32.2% | +24.4% | -7.8 |
| 2024 | +36.4% | +33.9% | -2.4 |
| 2025 | +16.3% | +26.3% | +10.0 |
| 2026-01..09-17 | +18.7% | +14.4% | -4.3 |

Wins 2/5, median -2.42 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +110.7% | 17.2% | -21.2% | 0.87 | 0.81 | $99.2k | $0.33k | 142 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +82.2% | 16.7% | -17.5% | 0.97 | 0.95 | $58.5k | $0.71k | 105 |

Verdict: **dropped-at-dev** — ETH improves clearly (CAGR 17.2% vs 14.0%, Calmar 0.81, max DD −21.2%) but WBTC CAGR 16.7% < 17.3% (Calmar 0.95 vs 0.97), wins 2/5. Holdout not run. Reading (interpretation): the two-day exit confirmation helps ETH's range harvesting and costs WBTC fees ($58.5k vs $61.7k, measured).

## Deviations

- Designed after EXP-097..101's dev results. **EXP-102..104 are fee-tier rules built from rules whose dev results are known**: each switch set was seen to help one pool at dev (WBTC 0.3%: EXP-087 / 098 / 101; ETH 0.05%: EXP-088 / 099). Their dev pass is therefore expected and carries no evidence; only the time-split holdout (H5 ETH 0.05%, H4 WBTC 0.3%, never used by any of the component rules except EXP-088's ETH half) judges them. Whether a fee-tier rule counts as one strategy or as two single-asset versions is Dino's call; it is reported either way. Liquidity crowding (EXP-105) trigger rate checked before registration, outcomes not looked at: 7-day mean above 1.5x the 90-day median on 13% of ETH days, 22% of WBTC days (2022-2026). Execution at the deepest UTC hour (literature pass) was considered and not registered: active liquidity varies only ±4% by hour and price impact is $0.3k of ETH's 4-year cost. Smoke test WBTC 2023-09-01..10-31 (`A,CO,CP,CQ,CR,CS`): all execute; on WBTC the tier rules reproduce their 'hi' components (CO = EXP-098's CK, CP = CN).
