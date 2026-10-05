# EXP-137: v6.75 + routing + rebuild on every F rise (one rule for both pools) (v6.123)

- Jira: QUAN-1021
- Status: holdout-pass
- Pre-registration commit: 2263c72 · Result commit: 50be075
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

EXP-134's rise rebuild on both pools, with routing making each extra WBTC rebuild cheaper (the reason faster refills hurt the 0.3% pool was the swap cost).

## Change

Variant `DY`: `REFILL_NO_NEW_LOW`, `SWAP_ROUTE = pool`, `REBUILD_ON_RISE` on every pool.

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
| 2022 | +7.6% | +10.2% | +2.5 |
| 2023 | +32.2% | +38.9% | +6.7 |
| 2024 | +36.4% | +38.0% | +1.6 |
| 2025 | +16.3% | +17.7% | +1.4 |
| 2026-01..09-17 | +18.7% | +18.6% | -0.1 |

Wins 4/5, median +1.60 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +104.5% | 16.4% | -24.5% | 0.82 | 0.67 | $91.2k | $0.36k | 156 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +95.4% | 18.9% | -16.2% | 1.08 | 1.16 | $60.4k | $-4.94k | 109 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +13.6% | 21.4% | -27.0% | 0.71 | 0.79 | $25.0k | $3.34k | 35 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +3.7% | 4.4% | -11.9% | 0.30 | 0.37 | $14.4k | $-0.62k | 19 |

Verdict: **holdout-pass (improvement level), one rule for both pools** — dev: ETH CAGR 16.4%, Calmar 0.67, wins 4/5; WBTC 18.9% vs 17.3%, Calmar 1.16 (EXP-123 without the rise rule: 18.5%, 1.10). Holdout: H5 ETH +13.6% vs +4.5%; H4 WBTC +3.7% vs +2.4% (EXP-123: +3.4%). Fifth clean pass. With routing, faster rebuilds no longer hurt the 0.3% pool (they did in round 1-3 without it), but the rise rule's own out-of-time effect is small on both pools (+0.1 / +0.3 pt).

## Deviations

- Ideas A1 and A3 of the 2026-10-06 literature pass (sixth agent run, rebuild mechanics). Designed after EXP-129..132's results (EXP-130's ETH half, v6.75 + cross-asset refill, passed H5 with new ETH evidence). A swap-tolerance rule (skip the rebuild swap when the held share is within 5 pts of target, idea B4) was coded and withdrawn before registration: a debug run showed the held share is always far from target at a rebuild (v6 rebuilds only after a >= 12.5% F move or a range exit), so the rule never fires. Smoke test WBTC 2023-01-01..06-30: the share-flip rule fires once there (on a day that also had an F rebuild, so no extra rebuild); the rise rule changes the result (`DY` +15.95% vs v6.75 + routing +15.99%).
