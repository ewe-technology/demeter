# EXP-126: v6.75 + macro restore + cheapest-tier routing (one rule for both pools) (v6.113)

- Jira: QUAN-1011
- Status: holdout-pass
- Pre-registration commit: 42d4107 · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

EXP-122 passed with one rule but doubled rebuilds (WBTC 231 vs 106); routing makes each WBTC rebuild cheaper, the main doubt about EXP-122. One rule for both pools. New evidence: the combination on H4.

## Change

Variant `DO`: `REFILL_NO_NEW_LOW`, `MACRO_EVENTS = csv`, `MACRO_RESTORE`, `SWAP_ROUTE = pool` on every pool.

## Pre-registration

Pre-registered together with EXP-123..127 (same commit), run with `A` (v6) in `A,DL,DM,DN,DO,DP` per window.

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

Development (`A` and the variant in each invocation, tag `ADLDMDNDODP`):

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
| WBTC this | +94.4% | 18.7% | -16.5% | 1.08 | 1.13 | $60.1k | $-5.20k | 231 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +14.0% | 22.1% | -26.9% | 0.73 | 0.82 | $25.1k | $3.34k | 55 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +3.3% | 4.0% | -11.8% | 0.29 | 0.34 | $13.9k | $-0.67k | 40 |

Verdict: **holdout-pass (improvement level), one rule for both pools** — dev: ETH CAGR 15.6% (v6.75 + macro restore), WBTC 18.7% vs 17.3%, Calmar 1.13. Holdout: H5 ETH 2021 +14.0% vs +4.5%; **H4 WBTC 2022 +3.3% vs +2.4%** (EXP-122 without routing +2.7%). Fourth clean pass. Routing makes each of EXP-122's extra rebuilds cheaper in swap fees, but it still rebuilds 2x (WBTC dev 231 vs 106, H4 40 vs 17) and gas is not charged: the gas doubt about EXP-122 remains.

## Deviations

- Dino, 2026-10-06: fee-tier rules count; 'keep searching, 30 more' (read as 30 more experiments, EXP-123..152). Routing counts as a strategy change (ruling relayed by the EXP-117 session). The routing code is EXP-117's (`SWAP_ROUTE`, `SWAP_ROUTES`: WBTC/USDC 0.3% swaps priced on WBTC/WETH 0.05% 0x4585 then WETH/USDC 0.05% 0x88e6), with the fix that session suggested: a pool without a route entry keeps v6's own ledger, so the switch is a no-op on 0x88e6. EXP-117 found routing alone took WBTC to 18.2% CAGR at dev (Calmar 1.10); routing has not been run on H4. Smoke test WBTC 2023-09-01..10-31: v6 +9.52%, routed variants +9.54..9.84%; ETH same window: `DL` equals v6.75 exactly (no-op checked).
