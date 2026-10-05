# EXP-118: fee tier: account tranches + volume refill on 0.3%, v6.75 on 0.05% (v6.105)

- Jira: QUAN-1003
- Status: holdout-pass
- Pre-registration commit: 22402c1 · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

Account tranches (fewer whole-ladder rebuilds) and volume-confirmed refills (refills only into traded rebounds) both cut the rebuild cost that hurts the 0.3% pool, through different routes; v6.75 on the 0.05% pool.

## Change

Variant `DG`: fee >= 0.3%: `ACCOUNT_TRANCHES = True`, `REFILL_VOL_CONFIRM = True`; below 0.3%: `REFILL_NO_NEW_LOW = True`.

## Pre-registration

Pre-registered together with EXP-118..122 (same commit), run with `A` (v6) in `A,DG,DH,DI,DJ,DK` per window. EXP-117 belongs to another session.

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

Development (`A` and the variant in each invocation, tag `ADGDHDIDJDK`):

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
| WBTC this | +90.6% | 18.1% | -15.2% | 1.05 | 1.19 | $62.4k | $0.69k | 106 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +13.5% | 21.4% | -27.0% | 0.71 | 0.79 | $25.0k | $3.34k | 33 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +5.6% | 6.7% | -11.3% | 0.40 | 0.60 | $14.0k | $0.02k | 18 |

Verdict: **holdout-pass (improvement level), fee-tier rule** — dev: ETH = v6.75 (15.4%, Calmar 0.64), WBTC CAGR 18.1% vs 17.3%, Calmar 1.19, max DD −15.2%; wins 4/5. Holdout: H5 ETH = EXP-088; **H4 WBTC 2022 total +5.6% vs +2.4%, Calmar 0.60, max DD −11.3%** (18 vs 17 rebuilds, mean F 0.595 vs 0.630). Both WBTC halves (tranches, volume refill) were known H4 winners; weak, correlated evidence (see EXP-112..115).

## Deviations

- Designed after EXP-112..116's dev and holdout results (EXP-112 / 114 / 115 passed as fee-tier pairs built from known H4 winners; their evidence is weak and correlated, see their verdicts). Same rule as before: each pair has at least one half not yet run on its holdout window; here every WBTC half is a new combination of known H4 winners (weak new evidence) and EXP-120 / 122 add a new ETH half for H5 (v6.75 + EXP-060's macro pause with exact restore). Smoke test ETH 2023-09-01..10-31 only (`A,DG,DH,DI,DJ,DK`; the WBTC pool was in use by the other session): all execute and equal v6 there, as does EXP-060's own variant `AW` in that window (checked), so the macro restore leaves that window unchanged.
