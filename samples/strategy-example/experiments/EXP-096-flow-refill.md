# EXP-096: refill stages only while the pool's traders are net buyers (v6.83)

- Jira: QUAN-980
- Status: dropped-at-dev
- Pre-registration commit: 893063f · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

The pool's own order flow says who trades the rebound: if traders keep selling the base token into the pool while the price bounces, the LP is absorbing distribution (toxic flow, the LVR source); if they are net buyers, the bounce has demand. A refill stage fires only if the pool's 3-day net base-token flow is buying; same rule on both pools, pool data only.

## Change

`FLOW_REFILL = True` (variant `CI`): a stage fires only if the sum of the pool's daily net base-token amount swapped in (`netAmount` of the base token) over the last 3 days is <= 0 (unknown -> no block). Constant: 3 days.

## Pre-registration

Pre-registered together with EXP-092..096 (same commit), run with `A` (v6) in `A,CE,CF,CG,CH,CI` per window.

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

Development (`A` and the variant in each invocation, tag `ACECFCGCHCI`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +6.7% | -0.9 |
| 2023 | +32.2% | +31.2% | -1.0 |
| 2024 | +36.4% | +34.7% | -1.7 |
| 2025 | +16.3% | +14.9% | -1.3 |
| 2026-01..09-17 | +18.7% | +18.4% | -0.3 |

Wins 0/5, median -1.04 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +81.3% | 13.5% | -24.4% | 0.70 | 0.55 | $84.8k | $0.28k | 147 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +85.4% | 17.3% | -18.0% | 1.01 | 0.96 | $61.3k | $0.72k | 106 |

Verdict: **dropped-at-dev** — ETH CAGR 13.5% vs 14.0%, Calmar 0.55, wins 0/5; WBTC ≈ v6 (17.3%, Calmar 0.96). Holdout not run. Reading: requiring net buying delayed ETH refills without filtering the failed ones; a likely reason (not tested) is that the pool's net flow mostly follows the CEX price through arbitrage rather than carrying independent demand.

## Deviations

- Designed while EXP-087..091's dev run was in progress (their results not seen), first drafted then and withdrawn uncommitted when v6.75 passed (round-2 stop rule); re-registered unchanged after EXP-087..091's results were known, for Dino's new goal of 2026-10-05 (continue until 10 improvement-level passes). Smoke test WBTC 2023-09-01..10-31 (`CE,CF,CG,CH,CI`, no v6 run): all execute; CE and CI identical there (gates not triggered in that window). Trigger rates checked before registration, outcomes not looked at (2022-01..2026-09): gas spike day 1.4% of days; stablecoin 7-day change < 0 on 40% (2022 56%, 2023 62%, 2024 17%, 2025 20%); pool 3-day net selling 54% (ETH pool) / 47% (WBTC pool). A Coinbase-premium refill gate was considered and not registered: the premium's median is 0.2 bp with 7 bp std and is negative on 83% of 2026 days (USDT/USD basis, not US demand). New data: `samples/flow_daily.csv` (`samples/fetch_flow_daily.py`: DefiLlama stablecoin market cap, Coinbase closes).
