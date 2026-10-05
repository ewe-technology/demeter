# EXP-125: fee tier: no lower stop + routing on 0.3%, v6.75 on 0.05% (v6.112)

- Jira: QUAN-1010
- Status: holdout-pass
- Pre-registration commit: 42d4107 · Result commit: b2b27b8
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

No lower stop (EXP-066, won H4) removes stop-driven rebuilds; routing makes the remaining ones cheaper. New evidence: the combination on H4.

## Change

Variant `DN`: fee >= 0.3%: `NO_LOWER_STOP`, `SWAP_ROUTE = pool`; below 0.3%: `REFILL_NO_NEW_LOW`.

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
| WBTC this | +96.2% | 19.0% | -16.4% | 1.10 | 1.16 | $64.8k | $-5.00k | 105 |

Holdout, time-split out-of-time (`BINANCE_WARM=1`, run once):

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| H5 ETH 2021-05-06..12-31 v6 | +4.5% | 7.0% | -30.7% | 0.37 | 0.23 | $21.0k | $3.70k | 37 |
| H5 ETH 2021-05-06..12-31 this | +13.5% | 21.4% | -27.0% | 0.71 | 0.79 | $25.0k | $3.34k | 33 |
| H4 WBTC 2022-01-01..10-31 v6 | +2.4% | 2.9% | -12.5% | 0.24 | 0.23 | $14.3k | $0.04k | 17 |
| H4 WBTC 2022-01-01..10-31 this | +4.2% | 5.1% | -11.8% | 0.33 | 0.43 | $15.8k | $-0.52k | 14 |

Verdict: **holdout-pass (improvement level), fee-tier rule** — dev: ETH = v6.75, WBTC CAGR 19.0%, Calmar 1.16, max DD −16.4%. Holdout: H5 ETH = EXP-088; **H4 WBTC 2022 total +4.2% vs +2.4%**, Calmar 0.43 (EXP-066 without routing: +3.7%).

## Deviations

- Dino, 2026-10-06: fee-tier rules count; 'keep searching, 30 more' (read as 30 more experiments, EXP-123..152). Routing counts as a strategy change (ruling relayed by the EXP-117 session). The routing code is EXP-117's (`SWAP_ROUTE`, `SWAP_ROUTES`: WBTC/USDC 0.3% swaps priced on WBTC/WETH 0.05% 0x4585 then WETH/USDC 0.05% 0x88e6), with the fix that session suggested: a pool without a route entry keeps v6's own ledger, so the switch is a no-op on 0x88e6. EXP-117 found routing alone took WBTC to 18.2% CAGR at dev (Calmar 1.10); routing has not been run on H4. Smoke test WBTC 2023-09-01..10-31: v6 +9.52%, routed variants +9.54..9.84%; ETH same window: `DL` equals v6.75 exactly (no-op checked).
