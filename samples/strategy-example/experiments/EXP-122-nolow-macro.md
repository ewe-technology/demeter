# EXP-122: v6.75 plus macro pause with exact restore (one rule for both pools) (v6.109)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
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

(pending)

## Deviations

- Designed after EXP-112..116's dev and holdout results (EXP-112 / 114 / 115 passed as fee-tier pairs built from known H4 winners; their evidence is weak and correlated, see their verdicts). Same rule as before: each pair has at least one half not yet run on its holdout window; here every WBTC half is a new combination of known H4 winners (weak new evidence) and EXP-120 / 122 add a new ETH half for H5 (v6.75 + EXP-060's macro pause with exact restore). Smoke test ETH 2023-09-01..10-31 only (`A,DG,DH,DI,DJ,DK`; the WBTC pool was in use by the other session): all execute and equal v6 there, as does EXP-060's own variant `AW` in that window (checked), so the macro restore leaves that window unchanged.
