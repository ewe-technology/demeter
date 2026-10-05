# EXP-115: fee tier: account tranches + intraday stop on 0.3%, v6.75 on 0.05% (v6.102)

- Jira: QUAN-1000
- Status: holdout-pass
- Pre-registration commit: 267ea44 · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

Account tranches (one sub-ladder per EMA account, rebuilt only when its account changes) cut whole-ladder rebuilds on the expensive pool and won H4; the intraday stop protects each tranche earlier. New evidence: the combination on H4.

## Change

Variant `DB`: fee >= 0.3%: `ACCOUNT_TRANCHES = True`, `INTRADAY_STOP = True`; below 0.3%: `REFILL_NO_NEW_LOW = True`. Constant: the 0.3% boundary.

## Pre-registration

Pre-registered together with EXP-112..116 (same commit), run with `A` (v6) in `A,CY,CZ,DA,DB,DC` per window.

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

Development (`A` and the variant in each invocation, tag `ACYCZDADBDC`):

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
| WBTC this | +98.3% | 19.3% | -17.8% | 1.10 | 1.09 | $65.7k | $0.79k | 120 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +13.5% | 21.4% | -27.0% | 0.71 | 0.79 | $25.0k | $3.34k | 33 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +7.6% | 9.2% | -11.4% | 0.50 | 0.81 | $14.5k | $0.02k | 20 |

Verdict: **holdout-pass (improvement level), fee-tier rule** — dev: ETH = v6.75, WBTC CAGR 19.3% vs 17.3%, Calmar 1.09, max DD −17.8% (= v6); wins 4/5. Holdout: H5 ETH = EXP-088; **H4 WBTC 2022 total +7.6% vs +2.4%, Calmar 0.81, max DD −11.4%** (20 vs 17 rebuilds, measured). Both WBTC halves (account tranches, EXP-063; intraday stop, EXP-101) were known H4 winners; correlated with EXP-103 / 112.

## Deviations

- Dino, 2026-10-05: 'keep searching until 10 passes'. Fee-tier passes are counted toward the 10 and labelled as such (his ruling on them is still open). Rule applied to every fee-tier pair from here on: at least one half must be new on its holdout window (a pair assembled from halves that already won their windows would pass by construction and is not registered). Which halves are known: on H4 WBTC 2022, EXP-063 (account tranches) +2.9%, EXP-066 (no lower stop) +3.7%, EXP-101 (intraday stop, inside EXP-103) +7.1%, EXP-087 (volume refill, inside EXP-104) +6.9% vs v6 +2.4%; on H5 ETH 2021, EXP-088 (v6.75) and EXP-073 (share 70%) won. The combinations registered here have not been run on any window. Smoke test WBTC 2023-09-01..10-31 (`A,CY,CZ,DA,DB,DC`): all execute; no stop fires there, so CY / CZ / DA equal the volume-refill result and DC equals v6.
