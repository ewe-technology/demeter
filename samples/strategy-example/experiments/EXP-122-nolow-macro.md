# EXP-122: v6.75 plus macro pause with exact restore (one rule for both pools) (v6.109)

- Jira: QUAN-1007
- Status: holdout-pass
- Pre-registration commit: 22402c1 · Result commit: ecb0b0e
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

A symmetric rule: v6.75's refill filter and EXP-060's macro pause / restore (a dev pass that lost H4 by 0.1 pt). Both act rarely on WBTC, so the WBTC result should stay near v6 while ETH gains from both.

## Change

Variant `DK`: `REFILL_NO_NEW_LOW = True`, `MACRO_EVENTS = csv`, `MACRO_RESTORE = True` on every pool.

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
| 2022 | +7.6% | +7.3% | -0.3 |
| 2023 | +32.2% | +39.3% | +7.1 |
| 2024 | +36.4% | +37.1% | +0.7 |
| 2025 | +16.3% | +16.9% | +0.6 |
| 2026-01..09-17 | +18.7% | +19.2% | +0.5 |

Wins 4/5, median +0.58 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +98.3% | 15.6% | -24.4% | 0.79 | 0.64 | $87.9k | $0.34k | 276 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +88.6% | 17.8% | -17.8% | 1.03 | 1.00 | $60.1k | $0.73k | 231 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +14.0% | 22.1% | -26.9% | 0.73 | 0.82 | $25.1k | $3.34k | 55 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +2.7% | 3.2% | -12.2% | 0.25 | 0.26 | $13.9k | $0.04k | 40 |

Verdict: **holdout-pass (improvement level), one rule for both pools** — dev: ETH CAGR 15.6% vs 14.0%, Calmar 0.64, max DD −24.4%; WBTC 17.8% vs 17.3%, Calmar 1.00 vs 0.97; wins 4/5. Holdout: H5 ETH 2021 total +14.0% vs +4.5% (CAGR 22.1%, Calmar 0.82); H4 WBTC 2022 total +2.7% vs +2.4% (CAGR 3.2%, Calmar 0.26, max DD −12.2%). Second clean pass after EXP-088, with the same weakness: **the WBTC margin is near noise** (+0.5 pt dev, +0.3 pt H4) and the result is mostly ETH. **Cost caveat (measured): the macro pause / restore more than doubles rebuilds (WBTC dev 231 vs 106, H4 40 vs 17)**; gas is reported, not charged, so on chain the extra rebuilds would very likely erase the WBTC margin. Treat as v6.75 plus a cost-uncertain overlay.

## Deviations

- Designed after EXP-112..116's dev and holdout results (EXP-112 / 114 / 115 passed as fee-tier pairs built from known H4 winners; their evidence is weak and correlated, see their verdicts). Same rule as before: each pair has at least one half not yet run on its holdout window; here every WBTC half is a new combination of known H4 winners (weak new evidence) and EXP-120 / 122 add a new ETH half for H5 (v6.75 + EXP-060's macro pause with exact restore). Smoke test ETH 2023-09-01..10-31 only (`A,DG,DH,DI,DJ,DK`; the WBTC pool was in use by the other session): all execute and equal v6 there, as does EXP-060's own variant `AW` in that window (checked), so the macro restore leaves that window unchanged.
