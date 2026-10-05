# EXP-116: fee tier: intraday stop on 0.3%, v6.75 + ETH share 70% on 0.05% (v6.103)

- Jira: QUAN-1001
- Status: dropped-at-dev
- Pre-registration commit: 267ea44 · Result commit: fa38c61
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

EXP-103 with the ETH half strengthened by the 70% share (as EXP-113). New evidence: the ETH combination on H5 (shared with EXP-113).

## Change

Variant `DC`: fee >= 0.3%: `INTRADAY_STOP = True`; below 0.3%: `REFILL_NO_NEW_LOW = True`, `SHARE_BELOW_EMA = 0.7`. Constant: the 0.3% boundary.

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
| 2022 | +7.6% | +13.0% | +5.4 |
| 2023 | +32.2% | +42.7% | +10.5 |
| 2024 | +36.4% | +34.5% | -1.9 |
| 2025 | +16.3% | +17.6% | +1.3 |
| 2026-01..09-17 | +18.7% | +25.1% | +6.4 |

Wins 4/5, median +5.37 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +123.2% | 18.6% | -26.1% | 0.82 | 0.71 | $93.1k | $0.44k | 146 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +96.5% | 19.0% | -18.0% | 1.10 | 1.06 | $64.0k | $0.78k | 106 |

Verdict: **dropped-at-dev (fee-tier rule)** — ETH as EXP-113 (CAGR 18.6%, max DD −26.1%, 3.3 pts deeper than v6), WBTC = EXP-101 (19.0%). Holdout not run.

## Deviations

- Dino, 2026-10-05: 'keep searching until 10 passes'. Fee-tier passes are counted toward the 10 and labelled as such (his ruling on them is still open). Rule applied to every fee-tier pair from here on: at least one half must be new on its holdout window (a pair assembled from halves that already won their windows would pass by construction and is not registered). Which halves are known: on H4 WBTC 2022, EXP-063 (account tranches) +2.9%, EXP-066 (no lower stop) +3.7%, EXP-101 (intraday stop, inside EXP-103) +7.1%, EXP-087 (volume refill, inside EXP-104) +6.9% vs v6 +2.4%; on H5 ETH 2021, EXP-088 (v6.75) and EXP-073 (share 70%) won. The combinations registered here have not been run on any window. Smoke test WBTC 2023-09-01..10-31 (`A,CY,CZ,DA,DB,DC`): all execute; no stop fires there, so CY / CZ / DA equal the volume-refill result and DC equals v6.
