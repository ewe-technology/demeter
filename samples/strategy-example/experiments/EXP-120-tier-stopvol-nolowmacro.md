# EXP-120: fee tier: EXP-112's WBTC half, v6.75 + macro restore on 0.05% (v6.107)

- Jira: QUAN-1005
- Status: holdout-pass
- Pre-registration commit: 22402c1 · Result commit: ecb0b0e
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

EXP-112 with the ETH half extended by EXP-060's macro pause with exact restore (pull the ladder around FOMC / CPI releases and put back the same bands), which won H5 alone by a small margin. New evidence: the ETH combination on H5.

## Change

Variant `DI`: fee >= 0.3%: `INTRADAY_STOP = True`, `REFILL_VOL_CONFIRM = True`; below 0.3%: `REFILL_NO_NEW_LOW = True`, `MACRO_EVENTS = csv`, `MACRO_RESTORE = True`.

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
| WBTC this | +104.0% | 20.2% | -15.1% | 1.17 | 1.34 | $64.4k | $0.76k | 97 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +14.0% | 22.1% | -26.9% | 0.73 | 0.82 | $25.1k | $3.34k | 55 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +9.2% | 11.2% | -11.2% | 0.59 | 1.00 | $14.4k | $0.01k | 16 |

Verdict: **holdout-pass (improvement level), fee-tier rule** — dev: ETH CAGR 15.6% vs 14.0% (v6.75 + macro restore), WBTC = EXP-112's half (20.2%, Calmar 1.34); wins 4/5. Holdout: **H5 ETH 2021 total +14.0% vs +4.5% (CAGR 22.1%, Calmar 0.82)**, a little above v6.75 alone (+13.5%): the macro restore adds 0.5 pt on ETH out of time; H4 WBTC = EXP-112 (+9.2%). New ETH evidence is small; the macro restore adds many rebuilds (see EXP-122), and gas is reported, not charged.

## Deviations

- Designed after EXP-112..116's dev and holdout results (EXP-112 / 114 / 115 passed as fee-tier pairs built from known H4 winners; their evidence is weak and correlated, see their verdicts). Same rule as before: each pair has at least one half not yet run on its holdout window; here every WBTC half is a new combination of known H4 winners (weak new evidence) and EXP-120 / 122 add a new ETH half for H5 (v6.75 + EXP-060's macro pause with exact restore). Smoke test ETH 2023-09-01..10-31 only (`A,DG,DH,DI,DJ,DK`; the WBTC pool was in use by the other session): all execute and equal v6 there, as does EXP-060's own variant `AW` in that window (checked), so the macro restore leaves that window unchanged.
