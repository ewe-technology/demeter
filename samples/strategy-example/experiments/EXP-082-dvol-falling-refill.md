# EXP-082: refill stages only while implied volatility is falling (v6.69)

- Jira: QUAN-966
- Status: dropped-at-dev
- Pre-registration commit: 6a6721b · Result commit: 0f8cc14
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

An LP is short volatility (LVR grows with σ², Milionis et al. 2022). v6's staged refill — its core edge (EXP-067/068) — fires on price alone, so it also redeploys into dead-cat bounces while the options market still prices a further shock. Requiring Deribit's DVOL to be falling when a stage fires keeps the refills on rebounds where the shock is being priced out (after the May 2021 crash and the June 2022 Celsius / 3AC lows DVOL peaked after the price low). New information (options market), acts only on refill timing, not on recentring.

## Change

`REFILL_GATE = "dvol_turn"` (variant `BU`): a refill stage (any of the four) fires only if the 3-day mean of the asset's DVOL is below its value 3 days earlier; days without DVOL never block. Everything else is v6's. Constants: the 3-day window (the refill's own confirmation length).

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
| 2022 | +7.6% | +7.2% | -0.4 |
| 2023 | +32.2% | +28.7% | -3.5 |
| 2024 | +36.4% | +27.9% | -8.5 |
| 2025 | +16.3% | +18.6% | +2.3 |
| 2026-01..09-17 | +18.7% | +18.6% | -0.1 |

Wins 1/5, median -0.37 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +84.7% | 13.9% | -22.0% | 0.73 | 0.63 | $84.2k | $0.32k | 142 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +53.5% | 11.7% | -17.5% | 0.74 | 0.67 | $47.1k | $0.54k | 99 |

Verdict: **dropped-at-dev** — ETH CAGR 13.9% vs 14.0% (Calmar 0.63, max DD −22.0%), wins 1/5; WBTC CAGR 11.7% vs 17.3%, Calmar 0.67. Holdout not run. Reading: waiting for falling implied vol delays the refills on the rebounds that carry v6's edge; on WBTC the delay costs a third of the return. DVOL keeps rising into many good rebounds (vol of a rally is still vol), so 'falling DVOL' is not a dead-cat filter.

## Deviations

- Ideas from a literature pass of 2026-10-05 (fourth agent run; it suggested screening the signals on dev refill events before pre-registering, which was not done, to keep dev unseen). New inputs: `samples/deribit_dvol_daily.csv` (`fetch_deribit_dvol.py`, Deribit DVOL from 2021-03-24), `binance_funding_{ETH,BTC}USDT_long.csv` (from 2020-06). Engine sanity check before this file (F statistics only, no strategy run): Binance ETH closes 2020-06..2021-04 and 2021-06..2023-06 (the second range overlaps dev: F means and change counts were seen, no returns). The first DVOL rule (3-day mean below the peak since exit) could never block — a mean cannot exceed the max it includes — and was replaced by the falling-DVOL rule below before this file.
