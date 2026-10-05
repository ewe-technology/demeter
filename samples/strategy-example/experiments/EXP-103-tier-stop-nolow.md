# EXP-103: fee tier: intraday stop on 0.3%, no-new-low refill on 0.05% (v6.90)

- Jira: QUAN-987
- Status: holdout-pass
- Pre-registration commit: 89f53b2 · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

Same fee-tier reasoning on the stop side: on an expensive pool a wick through the lower stop is worth acting on early (EXP-101 helped WBTC), on a cheap pool the refill is the lever and v6.75's no-new-low filter is the rule that passed (EXP-088).

## Change

Variant `CP`: pools with fee >= 0.3% run `INTRADAY_STOP = True`; pools below 0.3% run `REFILL_NO_NEW_LOW = True` (v6.75). Constant: the 0.3% tier boundary.

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
| WBTC this | +96.5% | 19.0% | -18.0% | 1.10 | 1.06 | $64.0k | $0.78k | 106 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +13.5% | 21.4% | -27.0% | 0.71 | 0.79 | $25.0k | $3.34k | 33 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +7.1% | 8.6% | -12.6% | 0.48 | 0.69 | $14.4k | $0.02k | 17 |

Verdict: **holdout-pass (improvement level), fee-tier rule** — dev (expected, components known): ETH = v6.75 (15.4%, Calmar 0.64), WBTC = EXP-101 (19.0% vs 17.3%, Calmar 1.06), wins 4/5. Time-split holdout (run once): H5 ETH 2021 identical to EXP-088 (CAGR 21.4% vs 7.0%); **H4 WBTC 2022 total +7.1% vs +2.4%, CAGR 8.6% vs 2.9%, Calmar 0.69 vs 0.23, max DD −12.6% vs −12.5%**. The new evidence is the WBTC half: the intraday lower stop (EXP-101), so far seen only at dev, wins the 2022 bear window. Same 17 rebuilds, mean F 0.612 vs 0.630: the gain comes from a few earlier stops, probably one crash episode (not decomposed). The ETH half adds nothing beyond EXP-088. **Counts as an improvement-level pass only if Dino accepts fee-tier rules** (it is v6.75 on 0.05% pools and an intraday stop on 0.3% pools).

## Deviations

- Designed after EXP-097..101's dev results. **EXP-102..104 are fee-tier rules built from rules whose dev results are known**: each switch set was seen to help one pool at dev (WBTC 0.3%: EXP-087 / 098 / 101; ETH 0.05%: EXP-088 / 099). Their dev pass is therefore expected and carries no evidence; only the time-split holdout (H5 ETH 0.05%, H4 WBTC 0.3%, never used by any of the component rules except EXP-088's ETH half) judges them. Whether a fee-tier rule counts as one strategy or as two single-asset versions is Dino's call; it is reported either way. Liquidity crowding (EXP-105) trigger rate checked before registration, outcomes not looked at: 7-day mean above 1.5x the 90-day median on 13% of ETH days, 22% of WBTC days (2022-2026). Execution at the deepest UTC hour (literature pass) was considered and not registered: active liquidity varies only ±4% by hour and price impact is $0.3k of ETH's 4-year cost. Smoke test WBTC 2023-09-01..10-31 (`A,CO,CP,CQ,CR,CS`): all execute; on WBTC the tier rules reproduce their 'hi' components (CO = EXP-098's CK, CP = CN).
