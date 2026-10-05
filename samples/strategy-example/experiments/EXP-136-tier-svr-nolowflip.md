# EXP-136: fee tier: EXP-124's WBTC half, v6.75 + share-flip rebuild on 0.05% (v6.122)

- Jira: QUAN-1023
- Status: dropped-at-dev
- Pre-registration commit: 2263c72 · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

EXP-135's share-flip rebuild on the cheap pool only.

## Change

fee >= 0.3%: `INTRADAY_STOP`, `REFILL_VOL_CONFIRM`, `SWAP_ROUTE = pool` (EXP-124's WBTC half); below 0.3%: `REFILL_NO_NEW_LOW`, `SHARE_FLIP_REBUILD`. Variant `DX`.

## Pre-registration

Pre-registered together with EXP-134..138 (same commit), run with `A` (v6) in `A,DV,DW,DX,DY,DZ` per window. EXP-133 belongs to another session.

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

Development (`A` and the variant in each invocation, tag `ADVDWDXDYDZ`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +8.7% | +1.1 |
| 2023 | +32.2% | +28.3% | -3.9 |
| 2024 | +36.4% | +35.8% | -0.5 |
| 2025 | +16.3% | +16.9% | +0.6 |
| 2026-01..09-17 | +18.7% | +17.5% | -1.2 |

Wins 2/5, median -0.55 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +95.5% | 15.3% | -24.5% | 0.78 | 0.63 | $89.2k | $0.35k | 171 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +109.6% | 21.0% | -13.8% | 1.22 | 1.52 | $64.4k | $-5.05k | 97 |

Verdict: **dropped-at-dev (fee-tier rule)** — ETH as EXP-135 (15.3%, wins 2/5); WBTC = EXP-124. Holdout not run.

## Deviations

- Ideas A1 and A3 of the 2026-10-06 literature pass (sixth agent run, rebuild mechanics). Designed after EXP-129..132's results (EXP-130's ETH half, v6.75 + cross-asset refill, passed H5 with new ETH evidence). A swap-tolerance rule (skip the rebuild swap when the held share is within 5 pts of target, idea B4) was coded and withdrawn before registration: a debug run showed the held share is always far from target at a rebuild (v6 rebuilds only after a >= 12.5% F move or a range exit), so the rule never fires. Smoke test WBTC 2023-01-01..06-30: the share-flip rule fires once there (on a day that also had an F rebuild, so no extra rebuild); the rise rule changes the result (`DY` +15.95% vs v6.75 + routing +15.99%).
