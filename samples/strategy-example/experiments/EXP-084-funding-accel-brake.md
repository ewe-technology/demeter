# EXP-084: negative-funding accelerator plus a hot-funding brake on later stages (v6.71)

- Jira: QUAN-968
- Status: dropped-at-dev
- Pre-registration commit: 6a6721b · Result commit: 0f8cc14
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

EXP-083 plus the other side: a rebound financed by leverage that is already rebuilt (funding > 3 x Binance's 0.01% base rate per 8h) is fragile; holding stages 2-4 until funding normalises avoids redeploying into a squeeze-driven top. Near-copy of EXP-083 (same accelerator).

## Change

`FUND_REFILL = "accel_brake"` (variant `BW`): EXP-083's accelerator, and stages 2-4 do not fire while the 3-day mean funding is > 0.0003 per 8h (3 x the base rate, a convention). Everything else is v6's.

## Pre-registration

Pre-registered together with EXP-082..086 (same commit), run in one invocation per window with `A` (v6): `A,BU,BV,BW,BX,BY`. EXP-083 and EXP-084 share the accelerator and are near-copies.

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

Development (`A` and the variant in each invocation, tag `ABUBVBWBXBY`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | -1.3% | -8.9 |
| 2023 | +32.2% | +31.9% | -0.3 |
| 2024 | +36.4% | +36.1% | -0.2 |
| 2025 | +16.3% | +16.4% | +0.2 |
| 2026-01..09-17 | +18.7% | +19.9% | +1.2 |

Wins 2/5, median -0.25 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +68.3% | 11.7% | -22.4% | 0.63 | 0.52 | $80.9k | $0.24k | 149 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +86.0% | 17.4% | -17.8% | 1.01 | 0.98 | $61.9k | $0.71k | 107 |

Verdict: **dropped-at-dev** — identical to EXP-083 on both assets (ETH 11.7%, WBTC 17.4%): the hot-funding brake (3-day mean > 0.0003 per 8h) never coincided with a stage 2-4 refill in 2022-2026. Holdout not run.

## Deviations

- Ideas from a literature pass of 2026-10-05 (fourth agent run; it suggested screening the signals on dev refill events before pre-registering, which was not done, to keep dev unseen). New inputs: `samples/deribit_dvol_daily.csv` (`fetch_deribit_dvol.py`, Deribit DVOL from 2021-03-24), `binance_funding_{ETH,BTC}USDT_long.csv` (from 2020-06). Engine sanity check before this file (F statistics only, no strategy run): Binance ETH closes 2020-06..2021-04 and 2021-06..2023-06 (the second range overlaps dev: F means and change counts were seen, no returns). The first DVOL rule (3-day mean below the peak since exit) could never block — a mean cannot exceed the max it includes — and was replaced by the falling-DVOL rule below before this file.
