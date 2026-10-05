# EXP-105: F capped at 50% while pool liquidity is crowded (v6.92)

- Jira: QUAN-989
- Status: dropped-at-dev
- Pre-registration commit: 89f53b2 · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

When other LPs pile into a pool, the ladder's share of every swap fee falls while its LVR does not, so the same exposure earns less per unit of risk. Capping F at half while the pool's active liquidity is far above its normal level is a pool-data rule, the same on both pools, not tied to price.

## Change

`CROWD_CAP = True` (variant `CR`): F = min(F, 0.5) on days whose 7-day mean of the pool's active liquidity (currentLiquidity, daily mean) is above 1.5x its 90-day median. Constants: 7 / 90 days, 1.5x, 0.5.

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
| 2022 | +7.6% | +8.1% | +0.4 |
| 2023 | +32.2% | +20.0% | -12.2 |
| 2024 | +36.4% | +46.9% | +10.5 |
| 2025 | +16.3% | +16.0% | -0.3 |
| 2026-01..09-17 | +18.7% | +18.7% | -0.0 |

Wins 2/5, median -0.01 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +97.0% | 15.5% | -17.0% | 0.80 | 0.91 | $89.3k | $0.30k | 155 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +81.5% | 16.6% | -15.9% | 0.98 | 1.05 | $47.8k | $0.71k | 125 |

Verdict: **dropped-at-dev** — ETH much safer and better (CAGR 15.5% vs 14.0%, Calmar 0.91 vs 0.61, max DD −17.0% vs −22.8%) and WBTC Calmar up (1.05 vs 0.97, max DD −15.9%), but WBTC CAGR 16.6% < 17.3% and ETH wins 2/5. Holdout not run. Reading (interpretation): capping F while liquidity is crowded cuts risk on both pools; on WBTC it also adds rebuilds (125 vs 106, measured) and cuts fees ($47.8k vs $61.7k), which costs return. Strongest risk reduction of the series; a candidate for the standalone level, not registered as such.

## Deviations

- Designed after EXP-097..101's dev results. **EXP-102..104 are fee-tier rules built from rules whose dev results are known**: each switch set was seen to help one pool at dev (WBTC 0.3%: EXP-087 / 098 / 101; ETH 0.05%: EXP-088 / 099). Their dev pass is therefore expected and carries no evidence; only the time-split holdout (H5 ETH 0.05%, H4 WBTC 0.3%, never used by any of the component rules except EXP-088's ETH half) judges them. Whether a fee-tier rule counts as one strategy or as two single-asset versions is Dino's call; it is reported either way. Liquidity crowding (EXP-105) trigger rate checked before registration, outcomes not looked at: 7-day mean above 1.5x the 90-day median on 13% of ETH days, 22% of WBTC days (2022-2026). Execution at the deepest UTC hour (literature pass) was considered and not registered: active liquidity varies only ±4% by hour and price impact is $0.3k of ETH's 4-year cost. Smoke test WBTC 2023-09-01..10-31 (`A,CO,CP,CQ,CR,CS`): all execute; on WBTC the tier rules reproduce their 'hi' components (CO = EXP-098's CK, CP = CN).
