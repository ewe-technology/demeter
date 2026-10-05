# EXP-127: fee tier: stop + volume + routing on 0.3%, v6.75 + up-day refill on 0.05% (v6.114)

- Jira: QUAN-1012
- Status: dropped-at-dev
- Pre-registration commit: 42d4107 · Result commit: b2b27b8
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

EXP-124's WBTC half and a new ETH half: v6.75 plus EXP-099's up-day refill (ETH 15.8% at dev alone, but 2/5 yearly wins). New evidence on both windows.

## Change

Variant `DP`: fee >= 0.3%: `INTRADAY_STOP`, `REFILL_VOL_CONFIRM`, `SWAP_ROUTE = pool`; below 0.3%: `REFILL_NO_NEW_LOW`, `UP_DAY_REFILL`.

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
| 2022 | +7.6% | +11.8% | +4.2 |
| 2023 | +32.2% | +26.8% | -5.4 |
| 2024 | +36.4% | +31.3% | -5.0 |
| 2025 | +16.3% | +15.4% | -0.8 |
| 2026-01..09-17 | +18.7% | +15.9% | -2.8 |

Wins 1/5, median -2.76 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +95.4% | 15.3% | -23.2% | 0.80 | 0.66 | $84.1k | $0.33k | 124 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +109.6% | 21.0% | -13.8% | 1.22 | 1.52 | $64.4k | $-5.05k | 97 |

Verdict: **dropped-at-dev (fee-tier rule)** — WBTC = EXP-124 (21.0%, Calmar 1.52); ETH CAGR 15.3% vs 14.0%, Calmar 0.66, but yearly wins 1/5: the up-day filter on top of v6.75 shifts ETH's gains into one year. Holdout not run.

## Deviations

- Dino, 2026-10-06: fee-tier rules count; 'keep searching, 30 more' (read as 30 more experiments, EXP-123..152). Routing counts as a strategy change (ruling relayed by the EXP-117 session). The routing code is EXP-117's (`SWAP_ROUTE`, `SWAP_ROUTES`: WBTC/USDC 0.3% swaps priced on WBTC/WETH 0.05% 0x4585 then WETH/USDC 0.05% 0x88e6), with the fix that session suggested: a pool without a route entry keeps v6's own ledger, so the switch is a no-op on 0x88e6. EXP-117 found routing alone took WBTC to 18.2% CAGR at dev (Calmar 1.10); routing has not been run on H4. Smoke test WBTC 2023-09-01..10-31: v6 +9.52%, routed variants +9.54..9.84%; ETH same window: `DL` equals v6.75 exactly (no-op checked).
