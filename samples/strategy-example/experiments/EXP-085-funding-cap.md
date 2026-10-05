# EXP-085: F capped at 50% while funding is overheated (v6.72)

- Jira: QUAN-969
- Status: dropped-at-dev
- Pre-registration commit: 6a6721b · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

Crowded leveraged longs are the fuel of liquidation cascades, and v6's lower stop acts on daily closes only after a cascade has happened. Funding was extreme in April-May 2021 before the May 19 crash. Capping the deployed fraction at half while funding is hot reduces exposure into the cascades without touching the refill in normal conditions.

## Change

`FUND_CAP = True` (variant `BX`): F = min(F, 0.5) on days whose 3-day mean funding is > 0.0003 per 8h. Everything else is v6's. Constants: 0.0003 (3 x base rate) and the 50% cap (two of the engine's four quarters).

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
| 2022 | +7.6% | +7.6% | +0.0 |
| 2023 | +32.2% | +34.0% | +1.7 |
| 2024 | +36.4% | +29.9% | -6.5 |
| 2025 | +16.3% | +16.3% | +0.0 |
| 2026-01..09-17 | +18.7% | +18.7% | +0.0 |

Wins 1/5, median +0.00 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +92.5% | 14.9% | -19.4% | 0.77 | 0.77 | $84.7k | $0.32k | 156 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +64.5% | 13.7% | -19.7% | 0.80 | 0.70 | $44.5k | $0.77k | 113 |

Verdict: **dropped-at-dev** — ETH improves (CAGR 14.9% vs 14.0%, Calmar 0.77 vs 0.61, max DD −19.4% vs −22.8%) but wins 1/5 and WBTC falls (CAGR 13.7% vs 17.3%, Calmar 0.70, max DD −19.7%). Holdout not run. Reading: halving exposure while funding is hot cuts ETH's 2024 drawdown but also WBTC's return (not diagnosed; plausibly the long hot-funding stretches of the 2023-24 bull, when the LP kept earning); the yearly wins (1/5) show the ETH gain is concentrated in one episode.

## Deviations

- Ideas from a literature pass of 2026-10-05 (fourth agent run; it suggested screening the signals on dev refill events before pre-registering, which was not done, to keep dev unseen). New inputs: `samples/deribit_dvol_daily.csv` (`fetch_deribit_dvol.py`, Deribit DVOL from 2021-03-24), `binance_funding_{ETH,BTC}USDT_long.csv` (from 2020-06). Engine sanity check before this file (F statistics only, no strategy run): Binance ETH closes 2020-06..2021-04 and 2021-06..2023-06 (the second range overlaps dev: F means and change counts were seen, no returns). The first DVOL rule (3-day mean below the peak since exit) could never block — a mean cannot exceed the max it includes — and was replaced by the falling-DVOL rule below before this file.
